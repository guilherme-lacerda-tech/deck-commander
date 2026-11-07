"""M20 sensores · M21 diagnóstico/autorreparo · M7 disco · M6 saves · M10.1 status.

M20: cada sensor tem estado próprio (ok/indisponível/erro). Leitura ausente NUNCA vira zero:
decisões que dependem dela são adiadas.
M21: matriz auto/ask/alert; autorreparo só nos 'auto', máx. 3 tentativas por problema, depois /sos.
M7: "última sessão" vem de LastPlayTime do shortcuts.vdf (o localconfig.vdf não guarda isso para
atalhos não-Steam — achado do S4). Nunca apaga nada, só sugere.
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import backup, ops, power, quarantine, vdf
from .paths import Paths
from .store import Store

H = Path.home()


# ----------------------------------------------------------------- M20 sensores
@dataclass
class Sensor:
    name: str
    state: str           # ok / indisponivel / erro
    value: Optional[float]
    unit: str = ""


def _read(p) -> Optional[str]:
    try:
        return Path(p).read_text().strip()
    except OSError:
        return None


def read_sensors(sysroot: Path = Path("/")) -> dict[str, Sensor]:
    s: dict[str, Sensor] = {}
    try:
        a = [int(x) for x in _read(sysroot / "proc/stat").splitlines()[0].split()[1:]]
        time.sleep(0.2)
        b = [int(x) for x in _read(sysroot / "proc/stat").splitlines()[0].split()[1:]]
        busy = (sum(b) - b[3] - b[4]) - (sum(a) - a[3] - a[4]); tot = sum(b) - sum(a)
        s["cpu"] = Sensor("cpu", "ok", round(100 * busy / tot, 1) if tot else None, "%")
    except Exception:  # noqa: BLE001
        s["cpu"] = Sensor("cpu", "erro", None)
    try:
        mi = dict(l.split(":", 1) for l in _read(sysroot / "proc/meminfo").splitlines())
        tot, av = int(mi["MemTotal"].split()[0]), int(mi["MemAvailable"].split()[0])
        s["ram"] = Sensor("ram", "ok", round(100 * (tot - av) / tot, 1), "%")
    except Exception:  # noqa: BLE001
        s["ram"] = Sensor("ram", "erro", None)
    gpu = [_read(p) for p in glob.glob(str(sysroot / "sys/class/drm/card*/device/gpu_busy_percent"))]
    gpu = [g for g in gpu if g and g.isdigit()]
    s["gpu"] = Sensor("gpu", "ok", float(gpu[0]), "%") if gpu else Sensor("gpu", "indisponivel", None)
    temps = [int(t) / 1000 for t in (_read(p) for p in glob.glob(str(sysroot / "sys/class/thermal/thermal_zone*/temp")))
             if t and t.lstrip("-").isdigit()]
    s["temp"] = Sensor("temp", "ok", max(temps), "°C") if temps else Sensor("temp", "indisponivel", None)
    r = power.read_power(sysroot / "sys/class/power_supply")
    s["bateria"] = Sensor("bateria", "ok" if r.battery_pct is not None else "indisponivel", r.battery_pct, "%")
    s["carregador"] = Sensor("carregador", "ok" if r.ac_online is not None else "indisponivel",
                             None if r.ac_online is None else float(r.ac_online))
    s["tdp"] = Sensor("tdp", "indisponivel", None)   # Panel de Control não expõe interface legível
    s["fps"] = Sensor("fps", "indisponivel", None)   # exige MangoHud ativo no jogo
    s["jogo"] = Sensor("jogo", "ok", float(ops.game_running()))
    return s


RULES = {  # tarefa -> (bateria mínima %, pode com jogo aberto?, precisa carregador?)
    "extract_big": (20, True, False),
    "benchmark": (0, False, False),
    "backup_heavy": (30, True, False),
    "nonessential": (0, True, True),
}


def can_run(task: str, sensors: dict[str, Sensor]) -> tuple[bool, str]:
    min_bat, game_ok, need_ac = RULES[task]
    if not game_ok:
        if sensors["jogo"].state != "ok":
            return False, "estado do jogo desconhecido — adiado"
        if sensors["jogo"].value:
            return False, "jogo aberto — adiado"
    ac, bat = sensors["carregador"], sensors["bateria"]
    if need_ac or min_bat:
        if ac.state == "ok" and ac.value:
            return True, "no carregador"
        if need_ac:
            return False, "fora do carregador (ou desconhecido) — adiado até carregar"
        if bat.state != "ok":
            return False, "nível da bateria desconhecido — adiado"
        if bat.value < min_bat:
            return False, f"bateria {bat.value:.0f}% < {min_bat}% — adiado"
    return True, "ok"


# ----------------------------------------------------------------- M7 disco
def disk_report(roots: list[Path], shortcuts: list[dict], keep_recent_days: int = 30, top: int = 10) -> list[dict]:
    last = {}
    for r in shortcuts:
        if "dc-launch" in (r.get("exe") or ""):
            last[r.get("LaunchOptions")] = r.get("LastPlayTime") or 0
    try:
        lm = json.loads((H / ".local/share/deck-commander/launch-map.json").read_text("utf-8"))
    except (OSError, ValueError):
        lm = {}
    by_path = {v["rom"]: k for k, v in lm.items()}
    items = []
    for root in roots:
        for console in (root.iterdir() if root.exists() else []):
            for game in (console.iterdir() if console.is_dir() else []):
                size = sum(f.stat().st_size for f in ([game] if game.is_file() else game.rglob("*")) if f.is_file())
                gid = next((g for p, g in by_path.items() if p.startswith(str(game))), None)
                lp = last.get(gid, 0)
                items.append({"path": str(game), "console": console.name, "size": size, "game_id": gid,
                              "last_played": datetime.fromtimestamp(lp).date().isoformat() if lp else "nunca"})
    items.sort(key=lambda x: -x["size"])
    cutoff = time.time() - keep_recent_days * 86400
    for it in items:
        lp = last.get(it["game_id"], 0)
        it["suggest_remove"] = bool(lp == 0 or lp < cutoff) and it["console"] != "switch-outros-idiomas"
    return items[:top]


def stale_downloads(paths: Paths) -> list[str]:
    """ZIP/arquivo original já extraído com sucesso pelo /sync => pode ser removido (sugestão)."""
    try:
        st = json.loads((paths.state / "sync-state.json").read_text("utf-8"))
    except (OSError, ValueError):
        return []
    return sorted(v["name"] for v in st.get("ingested", {}).values() if v.get("files"))


# ----------------------------------------------------------------- M6 saves
SAVE_SETS = {
    "saves": {
        "duckstation": "~/.local/share/duckstation/memcards",
        "pcsx2": "~/.var/app/net.pcsx2.PCSX2/config/PCSX2/memcards",
        "dolphin_gc": "~/.var/app/org.DolphinEmu.dolphin-emu/data/dolphin-emu/GC",
        "dolphin_wii": "~/.var/app/org.DolphinEmu.dolphin-emu/data/dolphin-emu/Wii/title",
        "retroarch": "~/Emulation/saves/retroarch/saves",
        "ppsspp": "~/.var/app/org.ppsspp.PPSSPP/config/ppsspp/PSP/SAVEDATA",
        "ryujinx": "~/.config/Ryujinx/bis/user/save",
    },
    "states": {
        "duckstation": "~/.local/share/duckstation/savestates",
        "pcsx2": "~/.var/app/net.pcsx2.PCSX2/config/PCSX2/sstates",
        "dolphin": "~/.var/app/org.DolphinEmu.dolphin-emu/data/dolphin-emu/StateSaves",
        "retroarch": "~/Emulation/saves/retroarch/states",
        "ppsspp": "~/.var/app/org.ppsspp.PPSSPP/config/ppsspp/PSP/PPSSPP_STATE",
    },
    "controls": {
        "duckstation": "~/.local/share/duckstation/inputprofiles",
        "pcsx2": "~/.var/app/net.pcsx2.PCSX2/config/PCSX2/inputprofiles",
        "dolphin_gc": "~/.var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu/GCPadNew.ini",
        "dolphin_wii": "~/.var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu/WiimoteNew.ini",
        "retroarch": "~/.var/app/org.libretro.RetroArch/config/retroarch/config/remaps",
        "ppsspp": "~/.var/app/org.ppsspp.PPSSPP/config/ppsspp/PSP/SYSTEM/controls.ini",
        "ryujinx": "~/.config/Ryujinx/profiles",
    },
    "per_game": {
        "duckstation": "~/.local/share/duckstation/gamesettings",
        "pcsx2": "~/.var/app/net.pcsx2.PCSX2/config/PCSX2/gamesettings",
        "dolphin": "~/.var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu/GameSettings",
        "retroarch": "~/.var/app/org.libretro.RetroArch/config/retroarch/config",
        "ryujinx": "~/.config/Ryujinx/games",
    },
}


def backup_saves(paths: Paths, home: Path = H) -> dict[str, str]:
    out = {}
    for kind, srcs in SAVE_SETS.items():
        found = {n: Path(p.replace("~", str(home), 1)) for n, p in srcs.items() if Path(p.replace("~", str(home), 1)).exists()}
        if not found:
            out[kind] = "nada para copiar"; continue
        res = backup.create_snapshot(found, paths.backups / "saves", paths.quarantine, kind=kind, keep=10)
        out[kind] = str(res.path) if res.ok else f"FALHOU: {res.error}"
    return out


def import_saves(snapshot: Path, dry_run: bool = True) -> dict[str, list[str]]:
    """Importa saves de outro Deck/snapshot. Conflito (arquivo existe com conteúdo diferente) NUNCA
    é sobrescrito: grava ao lado como '<nome>.conflito-<data>' e lista para o usuário decidir."""
    rep = {"novos": [], "iguais": [], "conflitos": []}
    man = json.loads((snapshot / "manifest.json").read_text("utf-8"))
    stamp = datetime.now().strftime("%Y%m%d")
    for rel, meta in man["files"].items():
        name, _, rest = rel.partition("/")
        orig = Path(man["sources"][name])
        dst = orig if man.get("source_is_file", {}).get(name) else orig / rest
        src = snapshot / "data" / rel
        if not dst.exists():
            rep["novos"].append(str(dst))
            if not dry_run:
                dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, dst)
        elif backup.sha256_file(dst) == meta["sha256"]:
            rep["iguais"].append(str(dst))
        else:
            side = dst.with_name(f"{dst.name}.conflito-{stamp}")
            rep["conflitos"].append(f"{dst} (versão importada em {side.name})")
            if not dry_run:
                shutil.copy2(src, side)
    return rep


# ----------------------------------------------------------------- M21 diagnóstico
@dataclass
class Finding:
    problem: str
    mode: str      # auto / ask / alert
    ok: bool
    detail: str
    action: str = ""


def _attempts(paths: Paths) -> dict:
    try:
        return json.loads((paths.state / "repair-attempts.json").read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def diagnose(paths: Paths, store: Store, repair: bool = False) -> list[Finding]:
    f: list[Finding] = []
    att = _attempts(paths)

    def auto(key: str, fn, detail: str) -> Finding:
        n = att.get(key, 0)
        if not repair:
            return Finding(key, "auto", False, detail, "autorreparo disponível")
        if n >= 3:
            return Finding(key, "auto", False, detail, "3 tentativas esgotadas — /sos")
        att[key] = n + 1
        try:
            return Finding(key, "auto", False, detail, f"reparado: {fn()} (tentativa {n + 1}/3)")
        except Exception as e:  # noqa: BLE001
            return Finding(key, "auto", False, detail, f"reparo falhou: {e} (tentativa {n + 1}/3)")

    # 1 serviço parado (só os que deveriam estar ativos e não estamos em safe-mode)
    if not ops.in_safe_mode(paths):
        for u in ops.dc_units(ops.unit_dir()):
            if u.endswith(".service") and ("bot" in u or "power" in u or "qbittorrent" in u):
                if "bot" in u and not (paths.secrets / "telegram").exists():
                    continue  # desligado de propósito: ainda sem token
                if "qbittorrent" in u and not (H / ".local/bin/qbittorrent-nox").exists():
                    continue  # ainda não instalado
                en = subprocess.run(["systemctl", "--user", "is-enabled", u], capture_output=True, text=True).stdout.strip()
                act = subprocess.run(["systemctl", "--user", "is-active", u], capture_output=True, text=True).stdout.strip()
                if en == "enabled" and act != "active":
                    f.append(auto(f"servico:{u}", lambda u=u: ops._systemctl("restart", u) and u, f"{u} parado"))
    # 2/3 backups
    try:
        snap, warns = backup.latest_valid(paths.backups, paths.quarantine, "config") if repair else (None, [])
        bad = [s.name for s in backup.list_snapshots(paths.backups, "config") if backup.verify_snapshot(s, sample=5)]
        f.append(Finding("backup", "auto", not bad and not warns, f"{len(bad)} inválido(s)" if bad else "ok",
                         "; ".join(warns)))
    except backup.AllBackupsCorrupt:
        f.append(Finding("todos-backups", "alert", False, "nenhum snapshot válido", "/sos"))
    # 4 BIOS
    from . import inventory
    inv = inventory.collect(H, paths)
    miss = [c for c, ok in inv["bios"]["required_ok"].items() if not ok]
    f.append(Finding("bios", "alert", not miss, f"faltando: {miss}" if miss else "ok"))
    # 5 config inconsistente (lançadores apontam para algo que não existe)
    try:
        from . import library
        lm = json.loads((paths.data / "launch-map.json").read_text("utf-8"))
        emu_cfg = paths.config / "emulators.json"
        emu = json.loads(emu_cfg.read_text("utf-8")) if emu_cfg.exists() else {}
        broken = [g for g in lm if not all(os.path.exists(x) for x in (library.build_command(g, lm, emu)[0], lm[g]["rom"]))]
        f.append(Finding("config", "ask", not broken, f"{len(broken)} lançador(es) quebrado(s): {broken[:5]}" if broken else "ok",
                         "oferecer restauração: dc restore <snapshot>" if broken else ""))
    except (OSError, ValueError):
        f.append(Finding("config", "ask", True, "sem mapa ainda"))
    # 6 plugin incompatível
    lock = paths.config / "plugins.lock"
    if lock.exists():
        want = json.loads(lock.read_text("utf-8"))
        have = installed_plugins()
        diff = [f"{k}: travado {v} / instalado {have.get(k)}" for k, v in want.items() if have.get(k) != v]
        f.append(Finding("plugins", "alert", not diff, "; ".join(diff) or "ok", "recomendar versão do plugins.lock" if diff else ""))
    # 7 ROM corrompida
    bad = [r[0] for r in store.conn.execute("SELECT path FROM files WHERE integrity IN ('corrupted','mismatch')")
           if os.path.exists(r[0])]
    if bad:
        f.append(auto("rom-corrompida", lambda: [quarantine.quarantine(Path(p), paths.quarantine, "ROM corrompida") for p in bad]
                      and len(bad), f"{len(bad)} ROM(s) com erro"))
    else:
        f.append(Finding("rom-corrompida", "auto", True, "ok"))
    # 8/10 DB divergente / jogo no Steam e não no DB
    from . import library, syncer
    games, _ = library.scan(syncer.rom_roots())
    rep = ops.db_verify(store, games, vdf.read_shortcuts(syncer.shortcuts_path()))
    div = {k: len(v) for k, v in rep.items() if v}
    f.append(Finding("db", "ask", not div, json.dumps(div) if div else "ok", "dc db index (usuário decide)" if div else ""))
    f.append(Finding("steam-sem-db", "ask", not rep["shortcut_untracked"],
                     f"{rep['shortcut_untracked'][:5]}" if rep["shortcut_untracked"] else "ok"))
    # 11 controles sem mapeamento / 12 jogos duplicados
    try:
        from . import controls
        bad_c = [c for c in controls.check() if not c.ok]
        f.append(Finding("controles", "alert", not bad_c, "; ".join(f"{c.emulator}: {c.detail}" for c in bad_c) or "ok"))
    except Exception as e:  # noqa: BLE001
        f.append(Finding("controles", "alert", False, f"não consegui verificar: {e}"))
    try:
        from . import dedup, remove
        lm = remove.effective_map(paths)
        dups = dedup.library_dups(lm)
        f.append(Finding("duplicatas", "ask", not dups,
                         "; ".join(" = ".join(lm[g]["title"] for g in grp) for grp in dups[:5]) or "ok",
                         "/duplicados mostra e /remover limpa (com confirmação)" if dups else ""))
    except (OSError, ValueError):
        pass
    # 9 Decky sumiu
    decky = (H / "homebrew/services/PluginLoader").exists()
    f.append(Finding("decky", "alert", decky, "ok" if decky else "Decky Loader sumiu (update do SteamOS?) — reinstalar manualmente"))
    if repair:
        paths.state.mkdir(parents=True, exist_ok=True)
        (paths.state / "repair-attempts.json").write_text(json.dumps(att), "utf-8")
    return f


def installed_plugins() -> dict[str, str]:
    out = {}
    for pj in glob.glob(str(H / "homebrew/plugins/*/package.json")):
        try:
            d = json.loads(Path(pj).read_text("utf-8"))
            out[Path(pj).parent.name] = d.get("version", "?")
        except (OSError, ValueError):
            pass
    return out


# ----------------------------------------------------------------- M10.1 status
def status_text(paths: Paths, store: Store, qbt=None) -> str:
    L = []
    L.append("🛑 SAFE-MODE ATIVO" if ops.in_safe_mode(paths) else "🟢 Deck Commander ativo")
    units = ops.dc_units(ops.unit_dir())
    names = {"qbittorrent": "downloads", "power": "monitor de energia", "bot": "bot", "dashboard": "painel",
             "backup": "backup diário", "tests": "testes semanais", "updates": "verificação de updates"}
    for u in units:
        base = u.replace("deck-commander-", "").rsplit(".", 1)[0]
        if u.endswith(".service") and f"deck-commander-{base}.timer" in units:
            continue  # tarefa agendada: o que importa é o timer
        act = subprocess.run(["systemctl", "--user", "is-active", u], capture_output=True, text=True).stdout.strip()
        if base == "dashboard" and act != "active":
            label = "desligado (opcional)"
        elif u.endswith(".timer"):
            label = "agendado ✅" if act == "active" else "NÃO agendado ⚠️"
        else:
            label = "rodando ✅" if act == "active" else f"{act} ⚠️"
        L.append(f"• {names.get(base, base)}: {label}")
    if qbt is not None:
        try:
            ts = qbt.torrents()
            L.append(f"• qBittorrent {qbt.version()}: {len(ts)} torrent(s), "
                     f"{sum(1 for t in ts if t['state'] in ('downloading', 'stalledDL', 'metaDL'))} baixando")
        except Exception as e:  # noqa: BLE001
            L.append(f"• qBittorrent: indisponível ({e})")
    try:
        st = json.loads((paths.state / "sync-state.json").read_text("utf-8"))
        L.append(f"• último /sync: {(st.get('last_sync') or 'nunca')[:16]}")
    except (OSError, ValueError):
        L.append("• último /sync: nunca")
    snaps = backup.list_snapshots(paths.backups, "config")
    L.append(f"• último backup: {snaps[0].name[:15] if snaps else 'nenhum'}")
    du = shutil.disk_usage(H)
    L.append(f"• espaço livre: {du.free // 10**9} GB interno"
             + "".join(f", {shutil.disk_usage(m).free // 10**9} GB {Path(m).name}" for m in glob.glob("/run/media/*/*")
                     if os.path.ismount(m)))
    late = [q for q in quarantine.list_entries(paths.quarantine) if q.overdue]
    L.append(f"• quarentena: {len(quarantine.list_entries(paths.quarantine))} item(s)" + (f", {len(late)} com revisão VENCIDA" if late else ""))
    pend = store.list(("awaiting_approval", "interrupted", "failed"), limit=5)
    for o in pend:
        L.append(f"• op {o.id} {o.type}: {o.state}" + (f" — /aprovar {o.id}" if o.state == "awaiting_approval" else ""))
    try:
        rep = json.loads((paths.state / "tests-last.json").read_text("utf-8"))
        L.append(f"• testes: {rep['summary']} em {rep['at'][:16]}")
    except (OSError, ValueError):
        pass
    return "\n".join(L)
