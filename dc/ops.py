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


def safe_mode_on(paths: Paths, reason: str, store: Store | None = None) -> list[str]:
    done = []
    for u in dc_units(unit_dir()):
        _systemctl("disable", "--now", u)
        done.append(f"desativado {u}")
    paths.state.mkdir(parents=True, exist_ok=True)
    safe_mode_flag(paths).write_text(f"{_now()} {reason}\n", "utf-8")
    if store is not None:  # restauração das configs fica aguardando aprovação (F4)
        op = store.enqueue("safe-mode-restore", {"reason": reason}, requires_approval=True)
        done.append(f"restauração de configs aguardando aprovação: dc op approve {op}")
    return done


def safe_mode_off(paths: Paths) -> list[str]:
    safe_mode_flag(paths).unlink(missing_ok=True)
    done = []
    for u in dc_units(unit_dir()):
        if u.endswith(".timer") or "bot" in u or "power" in u:
            _systemctl("enable", "--now", u)
            done.append(f"reativado {u}")
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
def uninstall(paths: Paths, code_dir: Path, purge: bool, purge_backups: bool, confirm: str = "") -> list[str]:
    if purge and confirm != "APAGAR":
        raise PermissionError("--purge exige --confirm APAGAR")
    if purge_backups and confirm != "APAGAR" or purge_backups and not purge:
        raise PermissionError("--purge-backups exige --purge --confirm APAGAR")
    log = []
    for u in dc_units(unit_dir()):
        _systemctl("disable", "--now", u)
        (unit_dir() / u).unlink(missing_ok=True)
        log.append(f"removido serviço {u}")
    _systemctl("daemon-reload")
    if purge:
        for d in (paths.config, paths.data, paths.state):
            shutil.rmtree(d, ignore_errors=True); log.append(f"apagado {d}")
    if purge_backups:
        shutil.rmtree(paths.backups, ignore_errors=True); log.append(f"apagado {paths.backups}")
    else:
        log.append(f"backups preservados em {paths.backups}")
    log.append("ROMs, saves e atalhos do Steam NÃO foram tocados"
               + (" (o lançador foi apagado: os atalhos 'Deck Commander' param de abrir)" if purge else ""))
    shutil.rmtree(code_dir, ignore_errors=True); log.append(f"apagado código {code_dir}")
    return log
