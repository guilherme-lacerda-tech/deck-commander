#!/usr/bin/env python3
"""Coletor SOMENTE LEITURA do ambiente do Steam Deck (base de M-1 e dos spikes S3–S6).

Não escreve nada fora de ~/deck-commander-probe/. Não lê senhas: linhas com
pass/token/user/key/secret são descartadas. Uso:  python3 tools/deck_probe.py
"""
import glob
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

H = Path.home()
OUT = H / "deck-commander-probe"
SECRET = re.compile(r"pass|token|user|key|secret|cheevos_username", re.I)
QUALITY = re.compile(r"upscal|resolution|internal|scale|efb|renderer|backend|video_driver|"
                     r"aspect|widescreen|shader|vsync|fps|framelimit|graphics", re.I)

EMU_CONFIGS = {
    "duckstation": ["~/.config/duckstation/settings.ini",
                    "~/.var/app/org.duckstation.DuckStation/config/duckstation/settings.ini",
                    "~/.local/share/duckstation/settings.ini"],
    "pcsx2": ["~/.config/PCSX2/inis/PCSX2.ini", "~/.var/app/net.pcsx2.PCSX2/config/PCSX2/inis/PCSX2.ini"],
    "dolphin": ["~/.var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu/GFX.ini",
                "~/.var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu/Dolphin.ini",
                "~/.config/dolphin-emu/GFX.ini"],
    "retroarch": ["~/.var/app/org.libretro.RetroArch/config/retroarch/retroarch.cfg",
                  "~/.config/retroarch/retroarch.cfg"],
    "ppsspp": ["~/.var/app/org.ppsspp.PPSSPP/config/ppsspp/PSP/SYSTEM/ppsspp.ini",
               "~/.config/ppsspp/PSP/SYSTEM/ppsspp.ini"],
}


def rd(p):
    try:
        return Path(p).read_text("utf-8", "replace").strip()
    except OSError:
        return None


def run(cmd):
    if not shutil.which(cmd[0]):
        return None
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception as e:  # noqa: BLE001
        return f"erro: {e}"


def procs():
    out = []
    for d in glob.glob("/proc/[0-9]*/comm"):
        c = rd(d)
        if c:
            out.append(c)
    return sorted(set(out))


def listening_ports():
    ports = set()
    for f in ("/proc/net/tcp", "/proc/net/tcp6"):
        for line in (rd(f) or "").splitlines()[1:]:
            parts = line.split()
            if len(parts) > 3 and parts[3] == "0A":
                ports.add(int(parts[1].rsplit(":", 1)[1], 16))
    return sorted(ports)


def emu(name, cands):
    for c in cands:
        p = Path(c).expanduser()
        if p.is_file():
            lines, section = [], ""
            for ln in p.read_text("utf-8", "replace").splitlines():
                s = ln.strip()
                if s.startswith("["):
                    section = s
                if QUALITY.search(s) and not SECRET.search(s):
                    lines.append(f"{section} {s}".strip())
            return {"path": str(p), "size": p.stat().st_size, "quality_lines": lines[:120]}
    return {"path": None, "searched": cands}


def steam():
    res = []
    for d in sorted(glob.glob(str(H / ".steam/steam/userdata/*"))):
        uid = Path(d).name
        sc, lc = Path(d) / "config/shortcuts.vdf", Path(d) / "config/localconfig.vdf"
        item = {"userdata_id": uid}
        for label, p in (("shortcuts", sc), ("localconfig", lc)):
            item[label] = {"exists": p.exists(), "size": p.stat().st_size if p.exists() else None,
                           "mtime": p.stat().st_mtime if p.exists() else None}
        if sc.exists():
            try:
                sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
                from dc import vdf
                rows = vdf.read_shortcuts(sc)
                item["shortcuts"]["count"] = len(rows)
                item["shortcuts"]["sample"] = [
                    {"AppName": r.get("AppName") or r.get("appname"), "appid": r.get("appid"),
                     "appid_formula": vdf.shortcut_appid(r.get("Exe") or r.get("exe") or "",
                                                         r.get("AppName") or r.get("appname") or ""),
                     "LastPlayTime": r.get("LastPlayTime"), "keys": sorted(r)} for r in rows[:15]]
            except Exception as e:  # noqa: BLE001
                item["shortcuts"]["parse_error"] = str(e)
        res.append(item)
    return res


def main():
    OUT.mkdir(exist_ok=True)
    pl = procs()
    info = {
        "os_release": rd("/etc/os-release"),
        "kernel": platform.release(),
        "python": sys.version,
        "has_tomllib": sys.version_info >= (3, 11),
        "dmi_product": rd("/sys/devices/virtual/dmi/id/product_name"),
        "dmi_board": rd("/sys/devices/virtual/dmi/id/board_name"),
        "power_supply": {Path(d).name: {f: rd(Path(d) / f) for f in ("type", "online", "capacity", "status", "usb_type")}
                         for d in sorted(glob.glob("/sys/class/power_supply/*"))},
        "session": {"XDG_CURRENT_DESKTOP": os.environ.get("XDG_CURRENT_DESKTOP"),
                    "gamescope_running": any("gamescope" in p for p in pl),
                    "steam_running": "steam" in pl, "plasma_running": any("plasmashell" in p for p in pl)},
        "listening_ports": listening_ports(),
        "tools": {t: shutil.which(t) for t in ("flock", "sqlite3", "jq", "unzip", "unrar", "7z", "xdelta3",
                                                "flips", "qbittorrent-nox", "flatpak", "steamos-readonly", "git")},
        "flatpaks": run(["flatpak", "list", "--app", "--columns=application,version"]),
        "decky": {"homebrew": (H / "homebrew").exists(),
                  "plugins": sorted(Path(p).name for p in glob.glob(str(H / "homebrew/plugins/*")))},
        "emudeck": {"config": (H / ".config/EmuDeck").exists(), "emulation_dir": (H / "Emulation").exists(),
                    "appimages": sorted(Path(p).name for p in glob.glob(str(H / "Applications/*.AppImage"))),
                    "srm_candidates": sorted(glob.glob(str(H / "Applications/*team*OM*anager*"))
                                             + glob.glob(str(H / ".config/EmuDeck/backend/tools/*srm*"))
                                             + glob.glob(str(H / "Applications/srm/*")))},
        "bios_files": sorted(Path(p).name for p in glob.glob(str(H / "Emulation/bios/*")))[:200],
        "rom_dirs": {Path(p).name: len(os.listdir(p)) for p in sorted(glob.glob(str(H / "Emulation/roms/*")))
                     if os.path.isdir(p)},
        "emulator_configs": {k: emu(k, v) for k, v in EMU_CONFIGS.items()},
        "steam": steam(),
        "disk": {m: shutil.disk_usage(m)._asdict() for m in ("/home", "/run/media") if os.path.exists(m)},
    }
    (OUT / "probe.json").write_text(json.dumps(info, indent=1, ensure_ascii=False, default=str), "utf-8")
    print(f"ok: {OUT / 'probe.json'}")
    print(f"modelo: {info['dmi_product']}  python: {sys.version.split()[0]}  tomllib: {info['has_tomllib']}")
    print("sessão:", info["session"])
    print("portas:", info["listening_ports"])
    print("energia:", {k: v.get('type') for k, v in info['power_supply'].items()})


if __name__ == "__main__":
    main()
