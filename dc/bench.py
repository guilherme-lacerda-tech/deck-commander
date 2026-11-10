"""Benchmark sem jogar: abre o jogo pelo Steam, deixa rodar a abertura/demonstração e fecha.

A medição é a mesma de uma partida normal (dc.perf, gravada pelo dc-launch). Não é igual à jogatina
(a abertura costuma ser mais leve ou mais pesada que o jogo), mas mostra se a resolução aguenta e quanto
consome. O resultado fica marcado como "simulação" no histórico.

    python3 -m dc x bench <game_id> [segundos]      (padrão 120 s; recusa se houver jogo aberto)
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from pathlib import Path

from . import perf
from .paths import Paths


def steam_gameid(appid: int) -> int:
    """ID que o steam:// usa para atalho não-Steam."""
    return ((int(appid) & 0xFFFFFFFF) << 32) | 0x02000000


def launcher_pids(game_id: str | None = None) -> list[int]:
    """Processos dc-launch rodando (de um jogo, ou de qualquer um)."""
    out = []
    for d in Path("/proc").iterdir():
        if not d.name.isdigit():
            continue
        try:
            args = (d / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        if any(a.endswith(b"dc-launch") for a in args[:2]) and (game_id is None or game_id.encode() in args):
            out.append(int(d.name))
    return out


def deck_ai_busy(url: str = "http://127.0.0.1:11434/api/ps") -> bool:
    """A IA do próprio Deck está com um modelo carregado (traduzindo)? Aí o FPS medido sairia baixo e o
    auto-ajuste baixaria a qualidade à toa."""
    import urllib.request
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            return bool(json.loads(r.read()).get("models"))
    except (OSError, ValueError):
        return False  # Ollama do Deck desligado/não instalado: livre


def run(paths: Paths, game_id: str, seconds: int = 120, log=print) -> dict | None:
    if launcher_pids():
        log("Tem um jogo aberto agora; o benchmark só roda com o Deck livre.")
        return None
    if deck_ai_busy():
        log("A IA do Deck está traduzindo agora; o benchmark mediria FPS baixo. Tente quando a tradução terminar "
            "(o modelo sai da memória uns 5 min depois).")
        return None
    done = json.loads((paths.data / "plugin-done.json").read_text("utf-8"))
    appid = (done.get(game_id) or {}).get("appid")
    if not appid:
        log(f"{game_id} não tem atalho no Steam ainda.")
        return None
    before = (paths.data / "perf-last.json").stat().st_mtime if (paths.data / "perf-last.json").exists() else 0
    # o dc-launch lê esta duração (o arquivo de FPS precisa ficar pronto antes de o teste fechar o jogo)
    (paths.data / "bench-seconds").write_text(str(max(20, seconds - 15)), "utf-8")
    subprocess.run(["steam", f"steam://rungameid/{steam_gameid(appid)}"], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    t0 = time.time()
    while time.time() - t0 < 40 and not launcher_pids(game_id):
        time.sleep(1)
    if not launcher_pids(game_id):
        log("O jogo não abriu pelo Steam (o Deck está no modo jogo?).")
        return None
    log(f"rodando {seconds} s…")
    time.sleep(seconds)
    for pid in launcher_pids(game_id):
        os.kill(pid, signal.SIGTERM)  # o dc-launch fecha o emulador e grava a medição
    for _ in range(30):
        last = paths.data / "perf-last.json"
        if last.exists() and last.stat().st_mtime > before:
            break
        time.sleep(1)
    else:
        log("O jogo fechou mas a medição não apareceu (veja logs/launch.log).")
        return None
    d = json.loads(last.read_text("utf-8"))
    d["simulacao"] = True
    hist = perf.history(paths.state, game_id)
    if hist:
        hist[-1]["simulacao"] = True
        f = paths.state / "perf" / f"{game_id}.json"
        f.write_text(json.dumps(hist, ensure_ascii=False, indent=1), "utf-8")
    log(perf.describe(d))
    return d


def calibrate(paths: Paths, game_id: str, seconds: int = 90, log=print, max_rounds: int = 6) -> str:
    """Roda benchmarks seguidos até o auto-ajuste fixar a qualidade do jogo (sobe até travar, volta um)."""
    from . import autotune
    lm = json.loads((paths.data / "launch-map.json").read_text("utf-8"))
    console = lm[game_id]["console"]
    autotune.ensure(paths, game_id, console)
    for i in range(max_rounds):
        if not autotune.needs_calibration(paths, game_id, console):
            break
        lvl = autotune.load(paths)[game_id]["level"]
        log(f"rodada {i + 1}: testando {lvl}x")
        d = run(paths, game_id, seconds, log)
        if d is None:
            return "calibração interrompida (Deck ocupado ou jogo não abriu)"
        if not d.get("verdict"):
            return "calibração interrompida: o FPS não foi medido neste emulador"
        time.sleep(5)
    st = autotune.load(paths)[game_id]
    return f"{lm[game_id]['title']}: qualidade automática {st['level']}x ({st['fase']})"
