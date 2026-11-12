"""M0.3 safe-mode · M15 uninstall · M19 índice/verify do banco · guarda do Steam (M0.2).

safe-mode (correção F4): o gatilho automático só DESATIVA (serviços/timers + flag); restaurar
configs é passo separado, manual ou aprovado. Nada é apagado.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from .paths import Paths
from .store import Store

UNIT_PREFIX = "deck-commander-"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _systemctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True)


def dc_units(unit_dir: Path) -> list[str]:
    return sorted(p.name for p in Path(unit_dir).glob(UNIT_PREFIX + "*") if p.suffix in (".service", ".timer"))


def unit_dir() -> Path:
    return Path.home() / ".config/systemd/user"


# ---------------------------------------------------------------- safe-mode
def safe_mode_flag(paths: Paths) -> Path:
    return paths.state / "SAFE_MODE"


def in_safe_mode(paths: Paths) -> bool:
    return safe_mode_flag(paths).exists()


def _safe_units_path(paths: Paths) -> Path:
    return paths.state / "safe-mode-units.json"


def _keeps_running(unit: str) -> bool:
    """O bot é o controle remoto: nunca é desligado pelo safe-mode (senão /sos off seria impossível
    longe do Deck). Ele mesmo recusa /add, /sync etc. enquanto o safe-mode estiver ativo."""
    return "-bot." in unit


def safe_mode_on(paths: Paths, reason: str, store: Store | None = None) -> list[str]:
    import json
    paths.state.mkdir(parents=True, exist_ok=True)
    units = [u for u in dc_units(unit_dir()) if not _keeps_running(u)
             and _systemctl("is-enabled", u).stdout.strip() == "enabled"]
    # registra ANTES de desligar: quem chamou pode ser um dos serviços que vai parar
    safe_mode_flag(paths).write_text(f"{_now()} {reason}\n", "utf-8")
    _safe_units_path(paths).write_text(json.dumps(units), "utf-8")
    done = []
    if store is not None:  # restauração das configs fica aguardando aprovação (F4)
        op = store.enqueue("safe-mode-restore", {"reason": reason}, requires_approval=True)
        done.append(f"restauração de configs aguardando aprovação: dc op approve {op}")
    me = f"{UNIT_PREFIX}power.service"  # o monitor pode ser quem chamou: desliga por último
    for u in sorted(units, key=lambda x: x == me):
        _systemctl("disable", "--now", u)
        done.append(f"desativado {u}")
    done.append("bot continua ligado (use /sos off para voltar)")
    return done


def safe_mode_off(paths: Paths) -> list[str]:
    import json
    try:
        units = json.loads(_safe_units_path(paths).read_text("utf-8"))
    except (OSError, ValueError):  # safe-mode antigo/sem registro: religa o essencial
        units = [u for u in dc_units(unit_dir()) if u.endswith(".timer")
                 or any(k in u for k in ("-power.", "-qbittorrent."))]
    done = []
    for u in units:
        _systemctl("enable", "--now", u)
        done.append(f"reativado {u}")
    safe_mode_flag(paths).unlink(missing_ok=True)
    _safe_units_path(paths).unlink(missing_ok=True)
    return done


# ---------------------------------------------------------------- Steam
def steam_running() -> bool:
    return subprocess.run(["pgrep", "-f", "ubuntu12_32/steam"], capture_output=True).returncode == 0


def game_running() -> bool:
    """Jogo aberto pelo Steam (reaper/SteamLaunch) ou emulador conhecido."""
    pats = ["SteamLaunch", "dc-launch", "pcsx2", "DuckStation", "Ryujinx", "dolphin-emu", "retroarch", "PPSSPP", "lichii"]
    for p in pats:
        if subprocess.run(["pgrep", "-f", p], capture_output=True).returncode == 0:
            return True
    return False


def gaming_mode() -> bool:
    return subprocess.run(["pgrep", "-x", "gamescope"], capture_output=True).returncode == 0 or \
        subprocess.run(["pgrep", "-f", "gamescope-session"], capture_output=True).returncode == 0


class SteamGuard:
    """Fecha o Steam antes de mexer em shortcuts.vdf/localconfig.vdf e reabre depois.
    No Gaming Mode a própria sessão reabre o Steam; no Desktop reabrimos via systemd --user."""

    def __init__(self, timeout: float = 60):
        self.timeout = timeout
        self.was_running = False

    def __enter__(self):
        if game_running():
            raise RuntimeError("há um jogo aberto — feche o jogo antes")
        self.was_running = steam_running()
        if self.was_running:
            subprocess.run(["steam", "-shutdown"], capture_output=True, timeout=30)
            t0 = time.monotonic()
            while steam_running():
                if time.monotonic() - t0 > self.timeout:
                    raise RuntimeError("o Steam não fechou a tempo")
                time.sleep(1)
        return self

    def __exit__(self, *exc):
        if self.was_running and not gaming_mode():
            time.sleep(2)
            if not steam_running():
                subprocess.run(["systemd-run", "--user", f"--unit=dc-steam-{int(time.time())}", "--collect",
                               "/usr/bin/steam"], capture_output=True)
        return False


def restart_steam() -> str:
    with SteamGuard():
        pass
    return "Steam reiniciado"


# ---------------------------------------------------------------- M19 índice e verify
def index_files(store: Store, games) -> int:
    """Registra jogos/arquivos no banco. Origem desconhecida => 'unknown' (nunca chuta)."""
    n = 0
    with store.tx() as c:
        for g in games:
            c.execute("INSERT OR IGNORE INTO games(id,title,console,created_at) VALUES(?,?,?,?)",
                      (g.game_id, g.title, g.console, _now()))
            st = os.stat(g.path)
            cur = c.execute("INSERT OR IGNORE INTO files(game_id,path,size,mtime,origin,origin_note)"
                            " VALUES(?,?,?,?,?,?)",
                            (g.game_id, g.path, st.st_size, st.st_mtime, "unknown",
                             "já existia antes do Deck Commander"))
            n += cur.rowcount
    return n


def db_verify(store: Store, games, shortcuts: list[dict]) -> dict:
    """missing / untracked / modified / shortcut_sem_provenance / provenance_sem_atalho. Não corrige nada."""
    rep = {"missing": [], "untracked": [], "modified": [], "shortcut_untracked": [], "shortcut_missing": []}
    db_files = {r[0]: (r[1], r[2]) for r in store.conn.execute("SELECT path,size,mtime FROM files")}
    disk = {g.path for g in games}
    for p, (size, mtime) in db_files.items():
        if not os.path.exists(p):
            rep["missing"].append(p)
        else:
            st = os.stat(p)
            if st.st_size != size or abs(st.st_mtime - mtime) > 1:
                rep["modified"].append(p)
    rep["untracked"] = sorted(disk - set(db_files))
    prov = {r[0] for r in store.conn.execute("SELECT appid FROM provenance WHERE source='dc'")}
    dc_sc = {str((r.get("appid") or 0) & 0xFFFFFFFF): r.get("AppName") for r in shortcuts
             if "dc-launch" in (r.get("exe") or "")}
    rep["shortcut_untracked"] = sorted(n for a, n in dc_sc.items() if a not in prov)
    rep["shortcut_missing"] = sorted(a for a in prov if a not in dc_sc)
    return rep


# ---------------------------------------------------------------- M15 uninstall
def uninstall(paths: Paths, code_dir: Path, purge: bool, purge_backups: bool, confirm: str = "",
              home: Path | None = None, esperar_plugin: float = 40, steam=None) -> list[str]:
    if purge and confirm != "APAGAR":
        raise PermissionError("--purge exige --confirm APAGAR")
    if purge_backups and confirm != "APAGAR" or purge_backups and not purge:
        raise PermissionError("--purge-backups exige --purge --confirm APAGAR")
    log = []
    home = home or Path.home()
    # Revisão de lançamento 12/11/2026: antes só saíam serviços e código. Ficavam os atalhos (quebrados: o
    # lançador importa o código apagado), os layouts/teclas dos botões de trás, o protetor de tela, o .zip e o
    # plugin do Decky rodando sem o Deck Commander. Cada passo é "melhor esforço": um que falhe não para os outros.
    log += _tirar_atalhos(paths, esperar_plugin)
    try:
        from . import retro
        log.append("retrô: " + retro.desfazer(home))
    except Exception as e:  # noqa: BLE001 — segue desinstalando
        log.append(f"retrô: não deu para desfazer ({e})")
    from .protetor import NOME
    prot = home / ".steam/root/config/uioverrides/screensavers" / NOME
    if prot.exists():
        shutil.rmtree(prot, ignore_errors=True); log.append("protetor de tela do Deck Commander removido")
    for u in dc_units(unit_dir()):
        _systemctl("disable", "--now", u)
        (unit_dir() / u).unlink(missing_ok=True)
        log.append(f"removido serviço {u}")
    _systemctl("daemon-reload")
    (home / "Downloads/deck-commander-plugin.zip").unlink(missing_ok=True)
    if purge:
        for d in (paths.config, paths.data, paths.state):
            shutil.rmtree(d, ignore_errors=True); log.append(f"apagado {d}")
        qbt = home / ".local/bin/qbittorrent-nox"  # baixado pelo Deck Commander (setup.install_qbittorrent)
        if qbt.exists():
            qbt.unlink(); log.append(f"apagado {qbt}")
    if purge_backups:
        shutil.rmtree(paths.backups, ignore_errors=True); log.append(f"apagado {paths.backups}")
    else:
        log.append(f"backups preservados em {paths.backups}")
    log.append("ROMs e saves NÃO foram tocados. Ficam (podem ser úteis sem o Deck Commander): os emuladores "
               "Flatpak, a Tailscale e as capas já aplicadas.")
    log.append(_pedir_ao_decky_desinstalar(steam))
    shutil.rmtree(code_dir, ignore_errors=True); log.append(f"apagado código {code_dir}")
    return log


def _tirar_atalhos(paths: Paths, esperar: float) -> list[str]:
    """Atalhos do Deck Commander saem do Steam (pelo plugin, ao vivo) antes de o código sumir."""
    from . import plugin_bridge
    from .arquivo_json import ler
    done = ler(plugin_bridge.done_path(paths), {})
    com_atalho = {g: v["appid"] for g, v in done.items() if v.get("appid")}
    if not com_atalho:
        return []
    if not plugin_bridge.active():
        return [f"atalhos: {len(com_atalho)} jogo(s) ficaram no Steam (o Decky não está rodando) — remova pelo "
                "Steam: Gerenciar → Remover atalho não-Steam"]
    for g, a in com_atalho.items():
        plugin_bridge.marcar_removido(paths, g, [a])
    fim = time.time() + esperar
    rq = paths.data / "plugin-remove.json"
    while time.time() < fim and ler(rq, []):
        time.sleep(1)
    sobrou = len(ler(rq, []))
    return [f"atalhos: {len(com_atalho) - sobrou} removido(s) do Steam"
            + (f"; {sobrou} ficaram (remova pelo Steam)" if sobrou else "")]


def _pedir_ao_decky_desinstalar(steam=None) -> str:
    """O plugin fica numa pasta do Decky (dono root): quem tira é o próprio Decky. Abre a pergunta dele na tela."""
    js = ('DeckyPluginLoader.uninstallPlugin("Deck Commander", "Desinstalar Deck Commander", "Desinstalar", '
          '"O Deck Commander foi removido. Tirar também o plugin do Decky?"), "ok"')
    try:
        if steam is None:
            from .steam_cdp import steam
        if steam(js) == "ok":
            return "plugin do Decky: confirme na tela do Deck para tirá-lo também"
    except Exception:  # noqa: BLE001 — Steam fechado/modo Desktop
        pass
    return "plugin do Decky: tire em Decky → ⚙️ → Plugins → Deck Commander → Desinstalar"
