from __future__ import annotations

import csv
import json
import os
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from .arquivo_json import gravar as _save
from .arquivo_json import ler as _load


def _mangohud_samples(path: Path) -> list[tuple[float, float, float, float]]:
    """Lê as amostras que o MangoHud já gravou, inclusive de um CSV ainda aberto.

    O MangoHud acrescenta linhas enquanto o jogo roda. Linhas incompletas no fim são normais e
    deliberadamente ignoradas, em vez de fazer o monitor de uma partida parar por um erro de leitura.
    """
    try:
        with open(path, 'r') as f:
            reader = csv.reader(f)
            # o log começa com linhas de sistema (os, cpu, gpu...); o cabeçalho de dados é o que tem fps e frametime
            header = next((r for r in reader if 'fps' in r and 'frametime' in r), None)
            if header is None:
                # O monitor ao vivo pode pegar o arquivo entre a criação e a escrita do cabeçalho.
                # Mantenha o contrato de "sem amostras" para que live_stats() apenas tente de novo.
                return []

            samples = []

            for row in reader:
                if len(row) <= header.index('fps'):
                    continue
                try:
                    fps = float(row[header.index('fps')])
                    cpu_temp = float(row[header.index('cpu_temp')]) if 'cpu_temp' in header else 0.0
                    gpu_load = float(row[header.index('gpu_load')]) if 'gpu_load' in header else 0.0

                    elapsed = float(row[header.index('elapsed')]) / 1e9 if 'elapsed' in header else 0.0
                    samples.append((elapsed, fps, cpu_temp, gpu_load))
                except (ValueError, IndexError):
                    continue
    except (OSError, FileNotFoundError):
        return []
    return samples


def _stats(samples: list[tuple[float, float, float, float]]) -> dict | None:
    if not samples:
        return None
    fps_values = [f for _, f, _, _ in samples]
    target = meta_quadros(fps_values)
    return {
        "target": target,
        "fps_avg": sum(fps_values) / len(fps_values),
        "fps_low": sorted(fps_values)[len(fps_values) // 100],  # com poucas amostras = mínimo
        "cpu_temp_max": max(t for _, _, t, _ in samples),
        "gpu_load_avg": sum(g for _, _, _, g in samples) / len(samples),
        "slow_share": sum(1 for f in fps_values if f < 0.9 * target) / len(fps_values),
        "samples": len(samples),
    }


def parse_mangohud(path: Path) -> dict | None:
    """Analisa o arquivo MangoHUD completo e extrai estatísticas da partida."""
    samples = _mangohud_samples(path)
    if not samples:
        return None
    # Os primeiros 15 s são carregamento/compilação de shaders: não contam como travada do jogo.
    t0 = samples[0][0]
    rest = [s for s in samples if s[0] - t0 >= 15]
    return _stats(rest if len(rest) >= 20 else samples)


def live_stats(path: Path, window: int = 48, target: float | None = None) -> dict | None:
    """Mede a janela mais recente de uma partida que ainda está rodando.

    O intervalo padrão do MangoHud é 250 ms; 48 amostras representam cerca de 12 s. Isso evita
    reagir a uma engasgada isolada, mas permite corrigir uma queda sustentada durante a jogatina,
    em vez de só acusá-la depois de ela já ter estragado a luta.
    """
    samples = _mangohud_samples(path)
    if len(samples) < 20 or samples[-1][0] - samples[0][0] < 15:
        return None
    recent = samples[-window:]
    stats = _stats(recent)
    # Depois de uma janela estável, a meta conhecida não pode cair junto com os FPS. Sem isso
    # 50 FPS em uma partida que vinha a 60 poderiam ser confundidos com um jogo PAL de 50.
    if stats and target and target > stats["target"]:
        stats["target"] = target
        stats["slow_share"] = sum(1 for _, fps, _, _ in recent if fps < 0.9 * target) / len(recent)
    return stats


def battery(sysfs_root: Path = Path('/sys/class/power_supply')) -> dict | None:
    """Obtém dados da bateria a partir do sysfs."""
    try:
        for d in sysfs_root.iterdir():
            if not d.is_dir():
                continue
            type_path = d / 'type'
            if type_path.exists() and type_path.read_text().strip() == 'Battery':
                # Encontrou a bateria
                power_now_path = d / 'power_now'
                energy_now_path = d / 'energy_now'
                charge_now_path = d / 'charge_now'
                voltage_now_path = d / 'voltage_now'
                status_path = d / 'status'

                # Watts
                if power_now_path.exists():
                    watts = float(power_now_path.read_text().strip()) / 1e6  # µW para W
                elif (d / 'current_now').exists():
                    current_now = float((d / 'current_now').read_text().strip())
                    voltage_now = float(voltage_now_path.read_text().strip()) if voltage_now_path.exists() else 8_000_000
                    watts = abs(current_now) * voltage_now / 1e12  # µA*µV para W
                else:
                    watts = None

                # Wh_left
                if energy_now_path.exists():
                    wh_left = float(energy_now_path.read_text().strip()) / 1e6  # µWh para Wh
                elif charge_now_path.exists():
                    charge_now = float(charge_now_path.read_text().strip())
                    voltage = float(voltage_now_path.read_text().strip()) if voltage_now_path.exists() else 0
                    voltage = voltage if voltage > 0 else 8_000_000  # sem leitura: 8 V (tensão nominal do Deck)
                    wh_left = (charge_now * voltage) / 1e12  # µAh*µV para Wh
                else:
                    wh_left = None

                # Status
                discharging = status_path.exists() and 'Discharging' in status_path.read_text()

                return {
                    "watts": watts,
                    "wh_left": wh_left,
                    "discharging": discharging
                }
        return None
    except Exception:
        return None


def summary(stats: dict, watts_samples: list, wh_left: float, target: int) -> dict:
    """Calcula o resumo do desempenho e bateria."""
    watts_avg = sum(watts_samples) / len(watts_samples)
    hours_left = round(wh_left / watts_avg, 1) if watts_avg > 0 else None
    verdict_value = verdict(stats["fps_avg"], stats["fps_low"], stats["slow_share"], target)
    return {
        "watts_avg": watts_avg,
        "hours_left": hours_left,
        "verdict": verdict_value
    }


def meta_quadros(fps_values: list[float]) -> int:
    """Quantos quadros por segundo o jogo QUER (25, 30, 50 ou 60), pelo ritmo que ele alcança na maior parte do tempo.
    Antes era "60 se a média passa de 35": jogo europeu (PAL) roda a 50 por natureza e era sempre julgado "travando"
    — o auto-ajuste prendia na resolução nativa (achado no Castlevania PAL em 13/11/2026)."""
    if not fps_values:
        return 60
    p90 = sorted(fps_values)[int(len(fps_values) * 0.9) - (1 if len(fps_values) > 1 else 0)]
    return next((t for t in (25, 30, 50, 60) if p90 <= t * 1.04), 60)


def verdict(fps_avg: float, fps_low: float, slow_share: float, target: int) -> str:
    """Determina o veredito com base nas estatísticas."""
    if slow_share <= 0.05 and fps_avg >= 0.95 * target:
        return "liso"
    elif slow_share >= 0.25 or fps_avg < 0.8 * target:
        return "travando"
    else:
        return "oscilando"


def wrap_command(cmd: list[str], home: Path=Path.home(), seconds: int | None = None) -> tuple[list[str], Path]:
    """Liga o MangoHud (sem mostrar nada na tela).

    A partida normal recebe quatro horas de telemetria, não apenas os primeiros cinco minutos. O
    benchmark ainda pode passar sua duração explícita. Assim uma queda que apareça numa fase tardia
    continua sendo vista pelo vigia ao vivo e o CSV também termina após uma saída forçada.
    """
    seconds = seconds or int(os.environ.get('DC_PERF_SECONDS', '14400'))
    # no_display desliga também o registro; por isso o HUD fica ligado, mas 100% transparente
    mh = f'alpha=0.0,background_alpha=0.0,fps_only=1,autostart_log=3,log_interval=250,log_duration={seconds}'
    if cmd[0].endswith('flatpak') and cmd[1] == 'run':
        app = cmd[2]
        log_dir = home / '.var/app' / app / 'dc-perf'
        # Inserimos os argumentos logo após 'run'
        # opções do flatpak vêm antes do nome do app
        # o carregador do Vulkan do sandbox não procura em /usr/lib/extensions: caminho e camada explícitos
        layer = '/usr/lib/extensions/vulkan/MangoHud/share/vulkan/implicit_layer.d'
        new_cmd = cmd[:2] + [f'--env=VK_ADD_LAYER_PATH={layer}', '--env=VK_INSTANCE_LAYERS=VK_LAYER_MANGOHUD_overlay_x86_64',
                             '--env=MANGOHUD=1', f'--env=MANGOHUD_CONFIG={mh},output_folder={log_dir}'] + cmd[2:]
    else:
        log_dir = home / '.local/share/deck-commander/perf-logs'
        new_cmd = ['/usr/bin/env', 'MANGOHUD=1', f'MANGOHUD_CONFIG={mh},output_folder={log_dir}'] + cmd
    log_dir.mkdir(parents=True, exist_ok=True)
    return (new_cmd, log_dir)


def apu_watts(hwmon_root: Path=Path('/sys/class/hwmon')) -> float | None:
    """Consumo do chip (CPU+GPU) em watts; funciona também na tomada, ao contrário da leitura da bateria."""
    if not hwmon_root.is_dir():
        return None
    for d in hwmon_root.iterdir():
        if not d.is_dir():
            continue
        name_path = d / 'name'
        if name_path.exists() and name_path.read_text().strip() == 'amdgpu':
            power_file = d / 'power1_average'
            if power_file.exists():
                return float(power_file.read_text().strip()) / 1e6  # µW para W
    return None


def audio_xruns(run=subprocess.run) -> dict[str, int] | None:
    """Lê os contadores de erro do PipeWire, sem capturar/gravar qualquer áudio.

    ``pw-top`` expõe o contador cumulativo ERR de cada nó de áudio. Só fazemos uma leitura curta
    durante uma partida, suficiente para correlacionar estalos/sumidas de som com a telemetria de
    vídeo; conteúdo de jogo, voz e microfone nunca entram no arquivo de diagnóstico.
    """
    try:
        r = run(["pw-top", "-b", "-n", "2"], capture_output=True, text=True, timeout=4)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode not in (0, 124):
        return None
    out: dict[str, int] = {}
    for ln in r.stdout.splitlines():
        cols = ln.split()
        # S ID QUANT RATE WAIT BUSY W/Q B/Q ERR FORMAT NAME — ERR é a coluna 8.
        if len(cols) < 10 or cols[0] not in ("R", "I") or not cols[8].isdigit():
            continue
        nome = " ".join(cols[10:]) or cols[9]
        out[nome] = int(cols[8])
    return out


class DiagnosticsSampler:
    """Diário leve da sessão: sensores, energia e saúde do áudio, sem conteúdo de áudio.

    A cadência de dois segundos é deliberadamente baixa para não competir com o emulador. O CSV do
    MangoHud continua guardando FPS/frametime a cada 250 ms; este JSONL guarda o contexto do Deck.
    """
    def __init__(self, paths, game_id: str, console: str, title: str, tdp_ctl=None, every: float = 2.0,
                 audio_every: float = 15.0, clock=time.monotonic):
        self.paths, self.game_id, self.console, self.title = paths, game_id, console, title
        self.tdp_ctl, self.every, self.audio_every, self.clock = tdp_ctl, every, audio_every, clock
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.path = paths.logs / "diagnosticos" / f"{game_id}-{stamp}.jsonl"
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)
        self._started = self.clock()
        self._last_audio = float("-inf")
        self._last_xruns: dict[str, int] | None = None

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n")

    def start(self):
        self._write({"event": "inicio", "at": datetime.now(timezone.utc).isoformat(), "game_id": self.game_id,
                     "console": self.console, "title": self.title, "audio_content_recorded": False})
        self._t.start()
        return self

    def sample(self) -> dict:
        agora = self.clock()
        data: dict = {"event": "amostra", "at": datetime.now(timezone.utc).isoformat(),
                      "seconds": round(agora - self._started, 1), "apu_watts": apu_watts(), "battery": battery()}
        if self.tdp_ctl:
            data["tdp_watts"] = self.tdp_ctl.ler()
        if agora - self._last_audio >= self.audio_every:
            self._last_audio = agora
            xruns = audio_xruns()
            if xruns is not None:
                data["pipewire_err"] = xruns
                if self._last_xruns is not None:
                    delta = {k: v - self._last_xruns.get(k, 0) for k, v in xruns.items()
                             if v > self._last_xruns.get(k, 0)}
                    if delta:
                        data["pipewire_err_new"] = delta
                self._last_xruns = xruns
        self._write(data)
        return data

    def _run(self) -> None:
        while not self._stop.wait(self.every):
            try:
                self.sample()
            except Exception:  # noqa: BLE001 - diagnóstico nunca pode interferir no jogo
                pass

    def stop(self) -> Path:
        self._stop.set()
        if self._t.is_alive():
            self._t.join(timeout=5)
        self._write({"event": "fim", "at": datetime.now(timezone.utc).isoformat(),
                     "seconds": round(self.clock() - self._started, 1)})
        return self.path


def record_session(state_dir: Path, game_id: str, data: dict) -> None:
    log_file = state_dir / 'perf' / f'{game_id}.json'
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        with open(log_file, 'r') as f:
            history = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        history = []
    
    data_with_time = {**data, "at": datetime.now(timezone.utc).isoformat()}
    history.append(data_with_time)
    history = history[-20:]  # Mantém apenas as últimas 20
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, dir=state_dir) as tmp:
        json.dump(history, tmp)
        tmp_path = tmp.name
    os.replace(tmp_path, log_file)


def history(state_dir: Path, game_id: str) -> list:
    log_file = state_dir / 'perf' / f'{game_id}.json'
    try:
        with open(log_file, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def newest_log(folder: Path, since: float) -> Path | None:
    latest = None
    latest_time = 0
    
    for p in folder.iterdir():
        if not p.is_file() or not p.name.endswith('.csv') or p.name.endswith('_summary.csv'):
            continue
        mtime = p.stat().st_mtime
        if mtime >= since and mtime > latest_time:
            latest = p
            latest_time = mtime
    
    return latest



def enabled(paths) -> bool:
    """Medição ligada por padrão; desliga com {"medir": false} em config/desempenho.json."""
    try:
        return bool(json.loads((paths.config / "desempenho.json").read_text("utf-8")).get("medir", True))
    except (OSError, ValueError):
        return True


def _live_path(paths) -> Path:
    return paths.data / "perf-live.json"


def live_status(paths, game_id: str | None = None) -> dict | None:
    """Alerta da partida atual, se houver; nunca devolve alerta de outro jogo."""
    data = _load(_live_path(paths), None)
    if not isinstance(data, dict) or not data.get("game_id"):
        return None
    if game_id and data.get("game_id") != game_id:
        return None
    return data


def live_message(paths) -> str | None:
    """Consome uma única notificação de travamento para o bot do Telegram."""
    p = _live_path(paths)
    data = live_status(paths)
    if not data or data.get("notified", False):
        return None
    data["notified"] = True
    _save(p, data)
    return data.get("message")


class LiveMonitor:
    """Observa o CSV do MangoHud enquanto o jogo está aberto.

    Não fecha o emulador e não grava no INI em uso. Quando a queda é sustentada, chama a função
    opcional para deixar a qualidade menor preparada para a próxima abertura e publica um aviso
    atômico que o painel e o Telegram podem mostrar.
    """

    def __init__(self, paths, game_id: str, console: str, title: str, log_dir: Path | None,
                 since: float, every: float = 3.0, on_stutter=None, on_stable=None,
                 adjustment_cooldown: float = 20.0, recovery_seconds: float = 300.0,
                 clock=time.monotonic):
        self.paths, self.game_id, self.console, self.title = paths, game_id, console, title
        self.log_dir, self.since, self.every = log_dir, since, every
        self.on_stutter, self.on_stable = on_stutter, on_stable
        self.adjustment_cooldown, self.recovery_seconds, self.clock = adjustment_cooldown, recovery_seconds, clock
        self.alerted = False
        self.adjusted = False
        # A primeira janela estável revela a meta do jogo (30/50/60). Não a reduza durante
        # uma queda: uma partida que vinha a 60 e cai para 42 não pode passar a parecer 50 FPS.
        self.reference_target: float | None = None
        self.missing_reported = False
        self.last_adjustment = float("-inf")
        self.stable_since: float | None = None
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)

    def start(self):
        _live_path(self.paths).unlink(missing_ok=True)
        if self.log_dir:
            self._t.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._t.is_alive():
            self._t.join(timeout=5)

    def check(self) -> dict | None:
        if not self.log_dir:
            return None
        log = newest_log(self.log_dir, self.since)
        stats = live_stats(log, target=self.reference_target) if log else None
        if not stats:
            # Sem CSV (ou sem FPS válido) não há como prometer que a detecção está ativa.
            # Espere a inicialização normal do Flatpak/MangoHud antes de avisar uma única vez.
            if not self.missing_reported and time.time() - self.since >= 45:
                self.missing_reported = True
                data = {"game_id": self.game_id, "console": self.console, "title": self.title,
                        "verdict": "indisponivel", "message":
                        "⚠️ A medição de desempenho não recebeu FPS do MangoHud. "
                        "O jogo continua aberto, mas não posso detectar travamentos nesta partida.",
                        "notified": False, "at": datetime.now(timezone.utc).isoformat()}
                _save(_live_path(self.paths), data)
                return data
            return None
        if self.missing_reported:
            # O aviso era apenas de inicialização; amostras válidas chegaram e a medição está ativa.
            _live_path(self.paths).unlink(missing_ok=True)
        if stats:
            self.reference_target = max(self.reference_target or 0, stats["target"])
            stats = dict(stats, target=self.reference_target)
        now = self.clock()
        # No relatório final 25% lento ainda é apenas um sinal. Ao vivo, 35% de uma janela de
        # 12 s abaixo de 90% da meta pede potência extra, mas em degraus: dá tempo para cada watt
        # surtir efeito antes de gastar o próximo.
        stuttering = stats and stats["slow_share"] >= 0.35 and stats["fps_avg"] < 0.90 * stats["target"]
        stable = stats and stats["slow_share"] <= 0.05 and stats["fps_avg"] >= 0.97 * stats["target"]
        if not stuttering:
            if stable:
                self.stable_since = self.stable_since or now
                if self.on_stable and now - self.stable_since >= self.recovery_seconds and now - self.last_adjustment >= self.adjustment_cooldown:
                    action = self.on_stable(stats)
                    if action:
                        self.last_adjustment = now
                        self.stable_since = now
                        return self._publish(stats, action, "estável")
            else:
                self.stable_since = None
            return None
        self.stable_since = None
        if now - self.last_adjustment < self.adjustment_cooldown:
            return None
        action = None
        if self.on_stutter:
            try:
                action = self.on_stutter(stats)
            except Exception:  # noqa: BLE001 - o aviso não pode derrubar o jogo
                action = None
        self.last_adjustment = now
        self.alerted = True
        self.adjusted = action is not None
        return self._publish(stats, action, "travando")

    def _publish(self, stats: dict, action: str | None, verdict: str) -> dict:
        level = None
        if action:
            import re
            m = re.search(r"fixado em (nativo|\d+x)", action)
            level = m.group(1) if m else None
        prefix = "⚠️" if verdict == "travando" else "✅"
        descr = "caiu de desempenho" if verdict == "travando" else "manteve desempenho estável"
        msg = (f"{prefix} {self.title} {descr}: {stats['fps_avg']:.0f} FPS "
               f"(meta {stats['target']}, {stats['slow_share']:.0%} da última janela abaixo do ritmo).")
        if action:
            msg += f" Ação durante a partida: {action}."
        if level:
            msg += f" Próxima abertura preparada em {level}."
        msg += " O jogo continua aberto. A resolução do PCSX2 não é regravada no meio da luta, pois isso pode causar outra travada."
        data = {"game_id": self.game_id, "console": self.console, "title": self.title,
                **{k: round(v, 3) if isinstance(v, float) else v for k, v in stats.items()},
                "verdict": verdict, "action": action, "next_level": level,
                "message": msg, "notified": False,
                "at": datetime.now(timezone.utc).isoformat()}
        _save(_live_path(self.paths), data)
        return data

    def _run(self) -> None:
        while not self._stop.wait(self.every):
            try:
                self.check()
            except Exception:  # noqa: BLE001 - observação nunca interfere no jogo
                pass


class Sampler:
    """Lê o consumo a cada `every` segundos enquanto o jogo está aberto (thread de fundo)."""

    def __init__(self, every: float = 5.0, hwmon_root: Path = Path("/sys/class/hwmon"),
                 sysfs_root: Path = Path("/sys/class/power_supply")):
        import threading
        self.every, self.hwmon_root, self.sysfs_root = every, hwmon_root, sysfs_root
        self.apu: list[float] = []
        self.bat: list[float] = []
        self.wh_left = None
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)

    def start(self) -> Sampler:
        self._t.start()
        return self

    def sample(self) -> None:
        w = apu_watts(self.hwmon_root)
        if w is not None:
            self.apu.append(w)
        b = battery(self.sysfs_root)
        if b:
            self.wh_left = b.get("wh_left")
            if b.get("discharging") and b.get("watts"):
                self.bat.append(b["watts"])

    def _run(self) -> None:
        while not self._stop.wait(self.every):
            try:
                self.sample()
            except Exception:  # noqa: BLE001
                pass

    def stop(self) -> None:
        self._stop.set()


def finish_session(paths, game_id: str, console: str, title: str, log_dir, t0: float, sampler: Sampler,
                   rec=None) -> str:
    """Fecha a medição de uma partida: lê o log de FPS, junta o consumo e guarda no histórico do jogo.
    O resumo também vai para data/perf-last.json (o bot avisa no Telegram e o plugin mostra)."""
    import time
    sampler.stop()
    dur = time.time() - t0
    if dur < 20:
        return "partida curta demais (<20 s), não registrada"
    log = newest_log(log_dir, t0) if log_dir else None
    stats = parse_mangohud(log) if log else None
    stats = stats or {}
    fps_avg = stats.get("fps_avg")
    target = stats.get("target") or (60 if (fps_avg or 0) > 35 else 30)
    # consumo: bateria quando está descarregando (o Deck inteiro); na tomada, só o chip
    watts = sampler.bat or sampler.apu
    data = {"title": title, "console": console, "minutos": round(dur / 60, 1),
            "fonte_watts": "bateria" if sampler.bat else "chip", "res": (rec or {}).get("new")}
    if watts:
        data.update(summary(stats or {"fps_avg": None}, watts, sampler.wh_left or 0, target)
                    if fps_avg else {"watts_avg": round(sum(watts) / len(watts), 1)})
        data["watts_avg"] = round(sum(watts) / len(watts), 1)
        data.pop("hours_left", None)  # na tomada o consumo do chip não dá a duração da bateria
        if sampler.bat and sampler.wh_left:
            data["hours_left"] = round(sampler.wh_left / data["watts_avg"], 1)
    data.update({k: stats[k] for k in ("fps_avg", "fps_low", "slow_share", "cpu_temp_max") if k in stats})
    if fps_avg:
        data["verdict"] = verdict(fps_avg, stats.get("fps_low", fps_avg), stats.get("slow_share", 0), target)
        data["target"] = target
    record_session(paths.state, game_id, data)
    last = paths.data / "perf-last.json"
    tmp = last.with_name(last.name + ".tmp")
    tmp.write_text(json.dumps(dict(data, game_id=game_id, notified=False), ensure_ascii=False), "utf-8")
    os.replace(tmp, last)
    return json.dumps(data, ensure_ascii=False)


VERDICT_TXT = {"liso": "✅ liso", "oscilando": "⚠️ oscilando", "travando": "❌ travando"}


def describe(d: dict) -> str:
    """Resumo de uma partida em português simples."""
    parts = [f"🎮 {d.get('title', d.get('game_id', '?'))} — {d.get('minutos', '?')} min"]
    if d.get("fps_avg"):
        parts.append(f"{VERDICT_TXT.get(d.get('verdict'), '')}: {d['fps_avg']:.0f} fps em média "
                     f"(pior momento {d.get('fps_low', 0):.0f}; meta {d.get('target')})")
    else:
        parts.append("FPS não medido (emulador sem Vulkan ou medição indisponível)")
    if d.get("watts_avg"):
        w = f"consumo {d['watts_avg']} W ({'Deck inteiro, na bateria' if d.get('fonte_watts') == 'bateria' else 'só o chip, na tomada'})"
        if d.get("hours_left"):
            w += f" → bateria cheia daria ~{d['hours_left']} h desse jogo"
        parts.append(w)
    if d.get("verdict") == "travando":
        parts.append("Sugestão: baixar a resolução deste jogo (/qualidade <jogo> 2x ou nativo).")
    return "\n".join(parts)


def pending_message(paths) -> str | None:
    """Mensagem da última partida ainda não avisada (marca como avisada)."""
    p = paths.data / "perf-last.json"
    try:
        d = json.loads(p.read_text("utf-8"))
    except (OSError, ValueError):
        return None
    if d.get("notified", True):
        return None
    d["notified"] = True
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False), "utf-8")
    os.replace(tmp, p)
    return describe(d)
