"""M3 — consoles oficiais do MVP, emuladores, comandos de lançamento e perfis de qualidade.

Fonte única (equivalente ao config/consoles/*.toml da v5.1): adicionar console = 1 entrada aqui.
Regra M3.2: perfis só são aplicados em emulador que o usuário NUNCA ajustou à mão; DuckStation e
PCSX2 do usuário têm override manual (5x / 3x) e ficam intactos sem --force.
"""
from __future__ import annotations

import os
from pathlib import Path

from .adapters.ini import CfgDoc, IniDoc

H = Path.home()
VAR = H / ".var/app"
RA_DIR = VAR / "org.libretro.RetroArch/config/retroarch"
RA_CORES = RA_DIR / "cores"
DOLPHIN_DIR = VAR / "org.DolphinEmu.dolphin-emu/config/dolphin-emu"
PPSSPP_INI = VAR / "org.ppsspp.PPSSPP/config/ppsspp/PSP/SYSTEM/ppsspp.ini"
FLATPAK = "/usr/bin/flatpak"

# console -> rótulo, extensões (ordem = preferência), comando ({rom}), BIOS obrigatória?
CONSOLES = {
    "psx":    {"label": "PlayStation", "exts": [".m3u", ".chd", ".pbp", ".cue"],
               "cmd": [str(H / "Applications/DuckStation-x64.AppImage"), "-fullscreen", "-batch", "--", "{rom}"]},
    "ps2":    {"label": "PlayStation 2", "exts": [".chd", ".iso", ".cso"],
               "cmd": [FLATPAK, "run", "net.pcsx2.PCSX2", "-fullscreen", "-batch", "--", "{rom}"]},
    "gc":     {"label": "GameCube", "exts": [".rvz", ".iso", ".gcz", ".ciso"],
               "cmd": [FLATPAK, "run", "org.DolphinEmu.dolphin-emu", "-b", "-e", "{rom}"]},
    "wii":    {"label": "Wii", "exts": [".rvz", ".wbfs", ".iso", ".wad"],
               "cmd": [FLATPAK, "run", "org.DolphinEmu.dolphin-emu", "-b", "-e", "{rom}"]},
    "snes":   {"label": "Super Nintendo", "exts": [".sfc", ".smc", ".zip"],
               "cmd": [FLATPAK, "run", "org.libretro.RetroArch", "-f", "-L", str(RA_CORES / "snes9x_libretro.so"), "{rom}"]},
    "n64":    {"label": "Nintendo 64", "exts": [".z64", ".n64", ".v64", ".zip"],
               "cmd": [FLATPAK, "run", "org.libretro.RetroArch", "-f", "-L", str(RA_CORES / "mupen64plus_next_libretro.so"), "{rom}"]},
    "gba":    {"label": "Game Boy Advance", "exts": [".gba", ".zip"],
               "cmd": [FLATPAK, "run", "org.libretro.RetroArch", "-f", "-L", str(RA_CORES / "mgba_libretro.so"), "{rom}"]},
    "psp":    {"label": "PSP", "exts": [".chd", ".cso", ".iso", ".pbp"],
               "cmd": [FLATPAK, "run", "org.ppsspp.PPSSPP", "--fullscreen", "{rom}"]},
    "switch": {"label": "Nintendo Switch", "exts": [".xci", ".nsp", ".nsz", ".xcz"],
               "cmd": [str(H / "Downloads/publish/Ryujinx"), "--fullscreen", "{rom}"]},
    # Switch 2 (experimental): dumps extraídos <jogo>/base/exefs/main, abertos pelo Lichii como o usuário já fazia
    "switch2": {"label": "Nintendo Switch 2", "exts": [], "dump": True,
                "cmd": [str(H / "Emulation/Lichii/lichii-linux-x86_64-pgo.AppImage"), "-f", "-g", "{rom}"]},
}
RA_CORE_FILES = ["snes9x_libretro.so", "mupen64plus_next_libretro.so", "mgba_libretro.so"]
RA_CORE_URL = "https://buildbot.libretro.com/nightly/linux/x86_64/latest/{core}.zip"
FLATPAK_IDS = ["net.pcsx2.PCSX2", "org.DolphinEmu.dolphin-emu", "org.libretro.RetroArch", "org.ppsspp.PPSSPP"]

# Perfil "equilibrado" (v5.1 M3.1) para os emuladores sem ajuste manual.
# Dolphin tem UM valor global para GC e Wii: 2x (spec pede GC 3x / Wii 2x; 2x é o que cabe nos dois).
PROFILE_EQUILIBRADO = {
    "dolphin_gfx": {("Settings", "InternalResolution"): "2", ("Settings", "ShaderCompilationMode"): "2"},
    "dolphin_main": {("Core", "GFXBackend"): "Vulkan", ("Interface", "ConfirmStop"): "False",
                     ("Display", "Fullscreen"): "True", ("Analytics", "PermissionAsked"): "True"},
    "ppsspp": {("Graphics", "InternalResolution"): "2", ("Graphics", "GraphicsBackend"): "3 (VULKAN)",
               ("General", "CheckForNewVersion"): "False", ("General", "FirstRun"): "False"},
    "retroarch": {"video_driver": "vulkan", "video_fullscreen": "true", "pause_nonactive": "false",
                  "savefile_directory": str(H / "Emulation/saves/retroarch/saves"),
                  "savestate_directory": str(H / "Emulation/saves/retroarch/states"),
                  "system_directory": str(H / "Emulation/bios")},
}


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".dc-tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def configure(apply: bool = False) -> list[str]:
    """Aplica o perfil equilibrado no Dolphin, PPSSPP e RetroArch (sem override manual). Read-back incluso."""
    log: list[str] = []
    for fname, key in (("GFX.ini", "dolphin_gfx"), ("Dolphin.ini", "dolphin_main")):
        p = DOLPHIN_DIR / fname
        doc = IniDoc.load(p) if p.exists() else IniDoc([])
        for (sec, k), v in PROFILE_EQUILIBRADO[key].items():
            if doc.get(sec, k) != v:
                log.append(f"dolphin {fname} [{sec}] {k}: {doc.get(sec, k)} -> {v}")
                doc.ensure_section(sec, k, v)
        if apply:
            _write(p, doc.dump())
            back = IniDoc.load(p)
            assert all(back.get(s, k) == v for (s, k), v in PROFILE_EQUILIBRADO[key].items()), "read-back dolphin"
    doc = IniDoc.load(PPSSPP_INI) if PPSSPP_INI.exists() else IniDoc([])
    for (sec, k), v in PROFILE_EQUILIBRADO["ppsspp"].items():
        if doc.get(sec, k) != v:
            log.append(f"ppsspp [{sec}] {k}: {doc.get(sec, k)} -> {v}")
            doc.ensure_section(sec, k, v)
    if apply:
        _write(PPSSPP_INI, doc.dump())
        back = IniDoc.load(PPSSPP_INI)
        assert all(back.get(s, k) == v for (s, k), v in PROFILE_EQUILIBRADO["ppsspp"].items()), "read-back ppsspp"
    cfg = RA_DIR / "retroarch.cfg"
    ra = CfgDoc.load(cfg)
    for k, v in PROFILE_EQUILIBRADO["retroarch"].items():
        if ra.get(k) != v:
            log.append(f"retroarch {k}: {ra.get(k)} -> {v}")
            ra.set(k, v)
    if apply:
        for k in ("savefile_directory", "savestate_directory"):
            Path(PROFILE_EQUILIBRADO["retroarch"][k]).mkdir(parents=True, exist_ok=True)
        _write(cfg, ra.dump())
        back = CfgDoc.load(cfg)
        assert all(back.get(k) == v for k, v in PROFILE_EQUILIBRADO["retroarch"].items()), "read-back retroarch"
    return log
