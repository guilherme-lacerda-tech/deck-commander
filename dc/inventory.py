"""M-1 — Inventário do ambiente (somente leitura; só grava os relatórios em ~/.local/state).

DoD v5.1: roda sem efeito colateral; origem de cada ROM = torrent/import/manual (com registro
no banco) ou `unknown` com nota — nunca chuta; avisa (sem falhar) se Decky/EmuDeck faltam.
"""
from __future__ import annotations

import glob
import json
import os
import platform
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from .paths import Paths
from .vdf import VdfError, read_shortcuts

ROM_EXTS = {".iso", ".chd", ".cue", ".bin", ".m3u", ".pbp", ".cso", ".gcz", ".rvz", ".wbfs", ".wad",
            ".sfc", ".smc", ".z64", ".n64", ".v64", ".gba", ".gb", ".gbc", ".nds", ".zip", ".7z"}
EMULATORS = {
    "duckstation": ["~/.local/share/duckstation/settings.ini",
                    "~/.var/app/org.duckstation.DuckStation/config/duckstation/settings.ini"],
    "pcsx2": ["~/.var/app/net.pcsx2.PCSX2/config/PCSX2/inis/PCSX2.ini", "~/.config/PCSX2/inis/PCSX2.ini"],
    "dolphin": ["~/.var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu/GFX.ini"],
    "retroarch": ["~/.var/app/org.libretro.RetroArch/config/retroarch/retroarch.cfg"],
    "ppsspp": ["~/.var/app/org.ppsspp.PPSSPP/config/ppsspp/PSP/SYSTEM/ppsspp.ini"],
}
FLATPAKS = {"pcsx2": "net.pcsx2.PCSX2", "dolphin": "org.DolphinEmu.dolphin-emu",
            "retroarch": "org.libretro.RetroArch", "ppsspp": "org.ppsspp.PPSSPP",
            "duckstation": "org.duckstation.DuckStation"}
# PS1/PS2 obrigatórias no MVP (M3.3). Nomes usuais: PS1 scph5501.bin / scph1001.bin;
# PS2 SCPH-70012.bin / ps2-0230a-20080220.bin. Só checa presença pelo nome — nunca baixa.
import re as _re
BIOS_REQUIRED = {"ps1": _re.compile(r"^scph\d{4}[a-z]?\.bin$"),
                 "ps2": _re.compile(r"^(scph-\d{5}.*|ps2-.*)\.bin$")}


def _rd(p) -> str | None:
    try:
        return Path(p).read_text("utf-8", "replace").strip()
    except OSError:
        return None


def _flatpak_apps() -> dict[str, str]:
    if not shutil.which("flatpak"):
        return {}
    import subprocess
    try:
        out = subprocess.run(["flatpak", "list", "--app", "--columns=application,version"],
                             capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    return dict(line.split("\t", 1) if "\t" in line else (line, "") for line in out.splitlines() if line)


def _provenance(db: Path) -> dict[str, tuple[str, str | None]]:
    if not db.exists():
        return {}
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)  # leitura pura
    try:
        return {r[0]: (r[1], r[2]) for r in con.execute("SELECT path, origin, origin_ref FROM files")}
    except sqlite3.Error:
        return {}
    finally:
        con.close()


def collect(home: Path, paths: Paths, sysroot: Path = Path("/")) -> dict:
    h = Path(home)
    warnings: list[str] = []
    flat = _flatpak_apps()

    hw = {"product": _rd(sysroot / "sys/devices/virtual/dmi/id/product_name"),
          "kernel": platform.release(), "python": sys.version.split()[0]}
    hw["model"] = {"Jupiter": "LCD", "Galileo": "OLED"}.get(hw["product"] or "", "desconhecido")
    os_rel = _rd(sysroot / "etc/os-release") or ""
    hw["steamos"] = next((ln.split("=", 1)[1].strip('"') for ln in os_rel.splitlines()
                          if ln.startswith("VERSION_ID=")), None)
    hw["disk_free_home"] = shutil.disk_usage(h).free if h.exists() else None

    decky_plugins = sorted(Path(p).name for p in glob.glob(str(h / "homebrew/plugins/*")))
    software = {
        "decky": (h / "homebrew").exists(),
        "decky_plugins": decky_plugins,
        "emudeck": (h / ".config/EmuDeck").exists(),
        "srm": bool(glob.glob(str(h / "Applications/*team*OM*anager*"))),
        "tabmaster": any("tabmaster" in p.lower() for p in decky_plugins),
        "unifideck": any("unifideck" in p.lower() for p in decky_plugins),
        "proton_pulse": any("pulse" in p.lower() for p in decky_plugins),
        "flatpaks": flat,
    }
    if not software["decky"]:
        warnings.append("Decky Loader não encontrado (~/homebrew) — M1 fica bloqueado")
    if not software["emudeck"]:
        warnings.append("EmuDeck não instalado — ROMs entram pelo launcher do Deck Commander, não pelo SRM")
    if not software["tabmaster"]:
        warnings.append("TabMaster ausente — instalar pela loja do Decky para as abas Jogos/Emuladores")

    emus = {}
    for name, cands in EMULATORS.items():
        cfg = next((str(Path(c.replace("~", str(h), 1))) for c in cands
                    if Path(c.replace("~", str(h), 1)).is_file()), None)
        installed = FLATPAKS.get(name) in flat or (name == "duckstation" and bool(
            glob.glob(str(h / "Applications/DuckStation*")) or (h / ".local/share/duckstation").exists()))
        emus[name] = {"installed": installed, "config": cfg}
        if installed and not cfg:
            warnings.append(f"{name}: instalado mas sem config — abra o emulador uma vez")

    bios = sorted(Path(p).name.lower() for p in glob.glob(str(h / "Emulation/bios/*")))
    bios_status = {c: any(rx.match(b) for b in bios) for c, rx in BIOS_REQUIRED.items()}
    for c, ok in bios_status.items():
        if not ok:
            warnings.append(f"BIOS de {c.upper()} ausente em ~/Emulation/bios (obrigatória no MVP; nunca baixada automaticamente)")

    steam = []
    for sc in sorted(glob.glob(str(h / ".steam/steam/userdata/*/config/shortcuts.vdf"))):
        try:
            rows = read_shortcuts(Path(sc))
            launchers: dict[str, int] = {}
            for r in rows:
                exe = (r.get("exe") or r.get("Exe") or "").strip('"').rsplit("/", 1)[-1]
                launchers[exe] = launchers.get(exe, 0) + 1
            steam.append({"userdata": Path(sc).parents[1].name, "shortcuts": len(rows),
                          "by_launcher": dict(sorted(launchers.items(), key=lambda kv: -kv[1])[:8])})
        except (OSError, VdfError) as e:
            steam.append({"userdata": Path(sc).parents[1].name, "error": str(e)})

    prov = _provenance(paths.db)
    roms = []
    for f in sorted((h / "Emulation/roms").rglob("*")) if (h / "Emulation/roms").exists() else []:
        if f.is_file() and f.suffix.lower() in ROM_EXTS:
            origin, ref = prov.get(str(f), ("unknown", None))
            item = {"path": str(f), "console": f.relative_to(h / "Emulation/roms").parts[0],
                    "size": f.stat().st_size, "origin": origin}
            if origin == "unknown":
                item["note"] = "sem registro no banco do Deck Commander — origem não rastreável"
            elif ref:
                item["origin_ref"] = ref
            roms.append(item)

    return {"generated_at": datetime.now(timezone.utc).isoformat(), "hardware": hw, "software": software,
            "emulators": emus, "bios": {"files": len(bios), "required_ok": bios_status},
            "steam": steam, "roms": roms, "warnings": warnings}


def to_markdown(inv: dict) -> str:
    hw, sw = inv["hardware"], inv["software"]
    out = [f"# Inventário do Deck — {inv['generated_at'][:19]}", "",
           f"- Modelo: **{hw['model']}** ({hw['product']}), SteamOS {hw['steamos']}, kernel {hw['kernel']}, Python {hw['python']}",
           f"- Espaço livre em /home: {round((hw['disk_free_home'] or 0) / 1e9)} GB",
           f"- Decky: {'sim' if sw['decky'] else 'NÃO'} — plugins: {', '.join(sw['decky_plugins']) or 'nenhum'}",
           f"- EmuDeck: {'sim' if sw['emudeck'] else 'não'} · SRM: {'sim' if sw['srm'] else 'não'} · "
           f"TabMaster: {'sim' if sw['tabmaster'] else 'não'} · Unifideck: {'sim' if sw['unifideck'] else 'não'}",
           "", "## Emuladores", "", "| Emulador | Instalado | Config |", "|---|---|---|"]
    for k, v in inv["emulators"].items():
        out.append(f"| {k} | {'sim' if v['installed'] else 'não'} | {v['config'] or '—'} |")
    out += ["", f"## BIOS ({inv['bios']['files']} arquivos)", ""]
    out += [f"- {c.upper()}: {'ok' if ok else 'AUSENTE (obrigatória no MVP)'}" for c, ok in inv["bios"]["required_ok"].items()]
    out += ["", "## Steam", ""]
    for s in inv["steam"]:
        out.append(f"- userdata {s['userdata']}: {s.get('shortcuts', '?')} atalhos — {s.get('by_launcher', s.get('error'))}")
    counts: dict[str, int] = {}
    for r in inv["roms"]:
        counts[r["origin"]] = counts.get(r["origin"], 0) + 1
    out += ["", f"## ROMs ({len(inv['roms'])})", "", f"Por origem: {counts or 'nenhuma ROM'}"]
    if inv["warnings"]:
        out += ["", "## Avisos", ""] + [f"- {w}" for w in inv["warnings"]]
    return "\n".join(out) + "\n"


def run(home: Path, paths: Paths) -> tuple[Path, Path, dict]:
    inv = collect(home, paths)
    paths.state.mkdir(parents=True, exist_ok=True)
    j, m = paths.state / "inventory.json", paths.state / "inventory.md"
    j.write_text(json.dumps(inv, indent=1, ensure_ascii=False), "utf-8")
    m.write_text(to_markdown(inv), "utf-8")
    return j, m, inv
