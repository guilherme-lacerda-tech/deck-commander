"""M3 — consoles oficiais do MVP, emuladores, comandos de lançamento e perfis de qualidade.

Fonte única (equivalente ao config/consoles/*.toml da v5.1): adicionar console = 1 entrada aqui.
Regra M3.2: perfis só são aplicados em emulador que o usuário NUNCA ajustou à mão; DuckStation e
PCSX2 do usuário têm override manual (5x / 3x) e ficam intactos sem --force.
"""
from __future__ import annotations

import os
from pathlib import Path

from ..adapters.ini import CfgDoc, IniDoc

H = Path.home()
VAR = H / ".var/app"
RA_DIR = VAR / "org.libretro.RetroArch/config/retroarch"
RA_CORES = RA_DIR / "cores"
DOLPHIN_DIR = VAR / "org.DolphinEmu.dolphin-emu/config/dolphin-emu"
PPSSPP_INI = VAR / "org.ppsspp.PPSSPP/config/ppsspp/PSP/SYSTEM/ppsspp.ini"
FLATPAK = "/usr/bin/flatpak"

# console -> rótulo, extensões (ordem = preferência), comando ({rom}), BIOS obrigatória?
CONSOLES = {
    "psx":    {"label": "PlayStation", "exts": [".m3u", ".chd", ".pbp", ".cue", ".mds"],  # .mds: imagem do Alcohol (DuckStation lê)
               "cmd": [str(H / "Applications/DuckStation-x64.AppImage"), "-fullscreen", "-batch", "--", "{rom}"]},
    "ps2":    {"label": "PlayStation 2", "exts": [".chd", ".iso", ".cso"],
               "cmd": [FLATPAK, "run", "net.pcsx2.PCSX2", "-fullscreen", "-batch", "--", "{rom}"]},
    "gc":     {"label": "GameCube", "exts": [".rvz", ".iso", ".gcz", ".ciso"],
               "cmd": [FLATPAK, "run", "org.DolphinEmu.dolphin-emu", "-b", "-e", "{rom}"]},
    "wii":    {"label": "Wii", "exts": [".rvz", ".wbfs", ".iso", ".wad"],
               "cmd": [FLATPAK, "run", "org.DolphinEmu.dolphin-emu", "-b", "-e", "{rom}"]},
    "doom":   {"label": "DOOM PC", "exts": [".wad", ".iwad"],
               "cmd": [FLATPAK, "run", "org.libretro.RetroArch", "-f", "-L", str(RA_CORES / "prboom_libretro.so"), "{rom}"]},
    "snes":   {"label": "Super Nintendo", "exts": [".sfc", ".smc", ".zip"],
               "cmd": [FLATPAK, "run", "org.libretro.RetroArch", "-f", "-L", str(RA_CORES / "snes9x_libretro.so"), "{rom}"]},
    "n64":    {"label": "Nintendo 64", "exts": [".z64", ".n64", ".v64", ".zip"],
               "cmd": [FLATPAK, "run", "org.libretro.RetroArch", "-f", "-L", str(RA_CORES / "mupen64plus_next_libretro.so"), "{rom}"]},
    "gba":    {"label": "Game Boy Advance", "exts": [".gba", ".zip"],
               "cmd": [FLATPAK, "run", "org.libretro.RetroArch", "-f", "-L", str(RA_CORES / "mgba_libretro.so"), "{rom}"]},
    "nds":    {"label": "Nintendo DS", "exts": [".nds", ".dsi", ".zip"],
               "cmd": [FLATPAK, "run", "net.kuribo64.melonDS", "-f", "{rom}"]},
    "psp":    {"label": "PSP", "exts": [".chd", ".cso", ".iso", ".pbp"],
               "cmd": [FLATPAK, "run", "org.ppsspp.PPSSPP", "--fullscreen", "{rom}"]},
    "n3ds":   {"label": "Nintendo 3DS", "exts": [".3ds", ".cci", ".cxi", ".z3ds", ".zcci", ".zcxi", ".3dsx"],
               "cmd": [FLATPAK, "run", "org.azahar_emu.Azahar", "-f", "{rom}"]},
    "wiiu":   {"label": "Wii U", "exts": [".wua", ".wux", ".wud", ".rpx"],
               "cmd": [FLATPAK, "run", "info.cemu.Cemu", "-f", "-g", "{rom}"]},
    # PS3: ISO ou jogo em pasta (PS3_GAME/USRDIR/EBOOT.BIN); firmware oficial instalada uma vez no RPCS3
    "ps3":    {"label": "PlayStation 3", "exts": [".iso"], "eboot": True,
               "cmd": [FLATPAK, "run", "net.rpcs3.RPCS3", "--no-gui", "--fullscreen", "{rom}"]},
    # Xbox 360 (Xenia Canary, nativo Linux): .iso, .xex, ou "Games on Demand" (<TitleID>/00007000/<arquivo sem extensão>)
    "x360":   {"label": "Xbox 360", "exts": [".iso", ".xex", ".zar"], "god": True,
               "cmd": [str(H / ".local/share/deck-commander/emus/xenia-canary/xenia_canary"), "--fullscreen=true", "{rom}"]},
    "xbox":   {"label": "Xbox", "exts": [".xiso", ".iso"],
               "cmd": [FLATPAK, "run", "app.xemu.xemu", "-full-screen", "-dvd_path", "{rom}"]},
    "dc":     {"label": "Dreamcast", "exts": [".chd", ".gdi", ".cdi"],
               "cmd": [FLATPAK, "run", "org.flycast.Flycast", "-config", "window:fullscreen=yes", "{rom}"]},
    "nes":    {"label": "NES", "exts": [".nes", ".fds", ".zip"],
               "cmd": [FLATPAK, "run", "org.libretro.RetroArch", "-f", "-L", str(RA_CORES / "nestopia_libretro.so"), "{rom}"]},
    "gb":     {"label": "Game Boy", "exts": [".gb", ".zip"],
               "cmd": [FLATPAK, "run", "org.libretro.RetroArch", "-f", "-L", str(RA_CORES / "gambatte_libretro.so"), "{rom}"]},
    "gbc":    {"label": "Game Boy Color", "exts": [".gbc", ".zip"],
               "cmd": [FLATPAK, "run", "org.libretro.RetroArch", "-f", "-L", str(RA_CORES / "gambatte_libretro.so"), "{rom}"]},
    "genesis": {"label": "Mega Drive", "exts": [".md", ".gen", ".smd", ".bin", ".zip"],
                "cmd": [FLATPAK, "run", "org.libretro.RetroArch", "-f", "-L", str(RA_CORES / "genesis_plus_gx_libretro.so"), "{rom}"]},
    "sms":    {"label": "Master System", "exts": [".sms", ".zip"],
               "cmd": [FLATPAK, "run", "org.libretro.RetroArch", "-f", "-L", str(RA_CORES / "genesis_plus_gx_libretro.so"), "{rom}"]},
    "gg":     {"label": "Game Gear", "exts": [".gg", ".zip"],
               "cmd": [FLATPAK, "run", "org.libretro.RetroArch", "-f", "-L", str(RA_CORES / "genesis_plus_gx_libretro.so"), "{rom}"]},
    "segacd": {"label": "Sega CD", "exts": [".chd", ".cue"],
               "cmd": [FLATPAK, "run", "org.libretro.RetroArch", "-f", "-L", str(RA_CORES / "genesis_plus_gx_libretro.so"), "{rom}"]},
    "saturn": {"label": "Sega Saturn", "exts": [".chd", ".cue"],
               "cmd": [FLATPAK, "run", "org.libretro.RetroArch", "-f", "-L", str(RA_CORES / "mednafen_saturn_libretro.so"), "{rom}"]},
    "pce":    {"label": "PC Engine", "exts": [".pce", ".chd", ".cue", ".zip"],
               "cmd": [FLATPAK, "run", "org.libretro.RetroArch", "-f", "-L", str(RA_CORES / "mednafen_pce_fast_libretro.so"), "{rom}"]},
    "arcade": {"label": "Arcade", "exts": [".zip", ".7z"],
               "cmd": [FLATPAK, "run", "org.libretro.RetroArch", "-f", "-L", str(RA_CORES / "fbneo_libretro.so"), "{rom}"]},
    "switch": {"label": "Nintendo Switch", "exts": [".xci", ".nsp", ".nsz", ".xcz"],
               "cmd": [str(H / "Downloads/publish/Ryujinx"), "--fullscreen", "{rom}"]},
    # Jogos do PC de casa por streaming (Moonlight <- Sunshine). Não há ROM nem emulador: o dc-launch chama
    # dc.pc_remoto.jogar (acorda o PC, espera o Sunshine, transmite). Lista vem do PC: dc.pc_remoto.sincronizar.
    "pc":     {"label": "Computador", "exts": [], "remoto": True, "cmd": []},
    # Switch 2 (experimental): dumps extraídos <jogo>/base/exefs/main, abertos pelo Lichii como o usuário já fazia
    "switch2": {"label": "Nintendo Switch 2", "exts": [], "dump": True,
                "cmd": [str(H / "Emulation/Lichii/lichii-linux-x86_64-pgo.AppImage"), "-f", "-g", "{rom}"]},
}
# Emuladores por console, em ordem de preferência. Falha real 15/11/2026 (Deck com EmuDeck): o PS2 abria um PCSX2
# Flatpak novo e vazio ("primeira vez": pedia BIOS e jogos) em vez do PCSX2 que o EmuDeck já tinha configurado.
# Regra: 1º o emulador que JÁ EXISTE no Deck (AppImage em ~/Applications, como o EmuDeck instala), 2º Flatpak,
# 3º núcleo do RetroArch. O usuário escolhe outro no painel (Emuladores) — fica em emulators.json.
_DUCK = ["Applications/DuckStation*.AppImage", "Applications/duckstation*.AppImage",
         "Downloads/DuckStation*.AppImage", "Downloads/*/DuckStation*.AppImage"]
_RYU = ["Applications/publish/Ryujinx", "Applications/Ryujinx*/Ryujinx", "Applications/Ryujinx*.AppImage",
        "Applications/ryujinx*.AppImage", "Downloads/publish/Ryujinx", "Downloads/*/publish/Ryujinx"]
_YUZU_ARGS = ["-f", "-g"]
OPCOES: dict[str, list[dict]] = {
    "doom": [{"nome": "PrBoom (RetroArch)", "ra_core": "prboom_libretro.so"}],
    "psx": [{"nome": "DuckStation", "globs": _DUCK, "args": ["-fullscreen", "-batch", "--"]},
            {"nome": "DuckStation (Flatpak)", "flatpak": "org.duckstation.DuckStation",
             "args": ["-fullscreen", "-batch", "--"]},
            # o DuckStation saiu do Flathub: sem ele, o PS1 abre no RetroArch com o núcleo SwanStation (mesmo código)
            {"nome": "SwanStation (RetroArch)", "ra_core": "swanstation_libretro.so"}],
    "ps2": [{"nome": "PCSX2 (do EmuDeck / ~/Applications)", "globs": ["Applications/pcsx2-Qt.AppImage",
             "Applications/pcsx2*.AppImage", "Applications/PCSX2*.AppImage"], "args": ["-fullscreen", "-batch", "--"]},
            {"nome": "PCSX2 (Flatpak)", "flatpak": "net.pcsx2.PCSX2", "args": ["-fullscreen", "-batch", "--"]}],
    "ps3": [{"nome": "RPCS3 (do EmuDeck / ~/Applications)", "globs": ["Applications/rpcs3.AppImage",
             "Applications/rpcs3*.AppImage", "Applications/RPCS3*.AppImage"], "args": ["--no-gui", "--fullscreen"]},
            {"nome": "RPCS3 (Flatpak)", "flatpak": "net.rpcs3.RPCS3", "args": ["--no-gui", "--fullscreen"]}],
    "psp": [{"nome": "PPSSPP (Flatpak)", "flatpak": "org.ppsspp.PPSSPP", "args": ["--fullscreen"]},
            {"nome": "PPSSPP (AppImage)", "globs": ["Applications/PPSSPP*.AppImage", "Applications/ppsspp*.AppImage"],
             "args": ["--fullscreen"]}],
    "gc": [{"nome": "Dolphin (Flatpak)", "flatpak": "org.DolphinEmu.dolphin-emu", "args": ["-b", "-e"]},
           {"nome": "Dolphin (AppImage)", "globs": ["Applications/Dolphin*.AppImage", "Applications/dolphin*.AppImage"],
            "args": ["-b", "-e"]}],
    "wii": [{"nome": "Dolphin (Flatpak)", "flatpak": "org.DolphinEmu.dolphin-emu", "args": ["-b", "-e"]},
            {"nome": "Dolphin (AppImage)", "globs": ["Applications/Dolphin*.AppImage", "Applications/dolphin*.AppImage"],
             "args": ["-b", "-e"]}],
    "wiiu": [{"nome": "Cemu (do EmuDeck / ~/Applications)", "globs": ["Applications/Cemu.AppImage",
              "Applications/Cemu*.AppImage", "Applications/cemu*.AppImage"], "args": ["-f", "-g"]},
             {"nome": "Cemu (Flatpak)", "flatpak": "info.cemu.Cemu", "args": ["-f", "-g"]}],
    "n3ds": [{"nome": "Azahar (AppImage)", "globs": ["Applications/azahar*.AppImage", "Applications/Azahar*.AppImage"],
              "args": ["-f"]},
             {"nome": "Lime3DS / Citra (AppImage)", "globs": ["Applications/lime3ds*.AppImage",
              "Applications/Lime3DS*.AppImage", "Applications/citra*.AppImage"], "args": ["-f"]},
             {"nome": "Azahar (Flatpak)", "flatpak": "org.azahar_emu.Azahar", "args": ["-f"]}],
    "nds": [{"nome": "melonDS (Flatpak)", "flatpak": "net.kuribo64.melonDS", "args": ["-f"]},
            {"nome": "melonDS (AppImage)", "globs": ["Applications/melonDS*.AppImage"], "args": ["-f"]}],
    "switch": [{"nome": "Ryujinx", "globs": _RYU, "args": ["--fullscreen"]},
               {"nome": "Ryujinx (Flatpak)", "flatpak": "io.github.ryubing.Ryujinx", "args": ["--fullscreen"]},
               {"nome": "Citron", "globs": ["Applications/citron*.AppImage", "Applications/Citron*.AppImage"],
                "args": _YUZU_ARGS},
               {"nome": "Eden", "globs": ["Applications/eden*.AppImage", "Applications/Eden*.AppImage"],
                "args": _YUZU_ARGS},
               {"nome": "Sudachi", "globs": ["Applications/sudachi*.AppImage", "Applications/Sudachi*.AppImage"],
                "args": _YUZU_ARGS},
               {"nome": "Yuzu", "globs": ["Applications/yuzu*.AppImage"], "args": _YUZU_ARGS}],
    "switch2": [{"nome": "Lichii", "globs": ["Emulation/Lichii/lichii-linux-x86_64-pgo.AppImage",
                 "Emulation/Lichii/*.AppImage", "Applications/*[Ll]ichii*.AppImage"], "args": ["-f", "-g"]}],
    "xbox": [{"nome": "xemu (AppImage)", "globs": ["Applications/xemu*.AppImage"], "args": ["-full-screen", "-dvd_path"]},
             {"nome": "xemu (Flatpak)", "flatpak": "app.xemu.xemu", "args": ["-full-screen", "-dvd_path"]}],
    "dc": [{"nome": "Flycast (Flatpak)", "flatpak": "org.flycast.Flycast", "args": ["-config", "window:fullscreen=yes"]},
           {"nome": "Flycast (AppImage)", "globs": ["Applications/flycast*.AppImage", "Applications/Flycast*.AppImage"],
            "args": ["-config", "window:fullscreen=yes"]}],
}
SEARCH = OPCOES  # nome antigo


def _flatpak_installed(app_id: str) -> bool:
    import subprocess
    try:
        return subprocess.run([FLATPAK, "info", app_id], capture_output=True, timeout=10, check=False).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def candidatos(console: str, home: Path = H, check_flatpak: bool = True) -> list[dict]:
    """Emuladores deste console que existem neste Deck: [{"nome", "cmd", "origem"}], na ordem de preferência."""
    import glob
    out = []
    # `home` também precisa valer para os núcleos RetroArch. Sem isso, uma inspeção/instalação
    # isolada acabava enxergando o RetroArch do usuário real e dizia que havia emulador no teste.
    ra_cores = home / ".var/app/org.libretro.RetroArch/config/retroarch/cores"
    for o in OPCOES.get(console, []):
        if o.get("globs"):
            hits = [h for g in o["globs"] for h in sorted(glob.glob(str(home / g)), reverse=True) if os.access(h, os.X_OK)]
            if hits:
                out.append({"nome": o["nome"], "cmd": [hits[0], *o["args"], "{rom}"], "origem": "appimage"})
        elif o.get("flatpak"):
            if check_flatpak and _flatpak_installed(o["flatpak"]):
                out.append({"nome": o["nome"], "cmd": [FLATPAK, "run", o["flatpak"], *o["args"], "{rom}"],
                            "origem": "flatpak"})
        elif o.get("ra_core"):
            if (ra_cores / o["ra_core"]).exists() and (not check_flatpak or _flatpak_installed("org.libretro.RetroArch")):
                out.append({"nome": o["nome"], "cmd": [FLATPAK, "run", "org.libretro.RetroArch", "-f", "-L",
                                                        str(ra_cores / o["ra_core"]), "{rom}"], "origem": "retroarch"})
    return out


def detect(home: Path = H, check_flatpak: bool = True) -> dict[str, list[str]]:
    """Comando do emulador preferido de cada console encontrado neste Deck."""
    out = {}
    for console in OPCOES:
        c = candidatos(console, home, check_flatpak)
        if c:
            out[console] = c[0]["cmd"]
    return out


def flatpaks_dispensaveis(home: Path = H, fora: set[str] | None = None) -> set[str]:
    """Flatpaks que NÃO precisam ser instalados: o console já tem emulador fora do Flatpak (ex.: AppImage do EmuDeck).
    `fora`: consoles que já têm emulador fora do Flatpak (o resultado de detect(check_flatpak=False))."""
    if fora is None:
        fora = set(detect(home, check_flatpak=False))
    usos: dict[str, set[str]] = {}
    for c, ops in OPCOES.items():
        for o in ops:
            if o.get("flatpak"):
                usos.setdefault(o["flatpak"], set()).add(c)
    return {fp for fp, cs in usos.items() if cs <= fora}


RA_CORE_FILES = ["snes9x_libretro.so", "mupen64plus_next_libretro.so", "mgba_libretro.so", "nestopia_libretro.so",
                 "gambatte_libretro.so", "genesis_plus_gx_libretro.so", "mednafen_saturn_libretro.so",
                 "mednafen_pce_fast_libretro.so", "fbneo_libretro.so", "swanstation_libretro.so", "prboom_libretro.so"]
RA_CORE_URL = "https://buildbot.libretro.com/nightly/linux/x86_64/latest/{core}.zip"
FLATPAK_IDS = ["net.pcsx2.PCSX2", "org.DolphinEmu.dolphin-emu", "org.libretro.RetroArch", "org.ppsspp.PPSSPP",
               "net.kuribo64.melonDS", "org.azahar_emu.Azahar", "info.cemu.Cemu", "net.rpcs3.RPCS3", "app.xemu.xemu",
               "org.flycast.Flycast"]
# Instalados só se o Deck ainda não tiver o emulador desse console (ex.: Ryujinx em ~/Applications fica como está)
FLATPAK_IF_MISSING = {"switch": "io.github.ryubing.Ryujinx"}
# O que cada console precisa que VOCÊ coloque (o Deck Commander nunca baixa BIOS/firmware/chaves)
NEEDS = {"ps3": "firmware oficial do PS3 (PS3UPDAT.PUP) instalada uma vez no RPCS3",
         "xbox": "BIOS, MCPX e imagem de HD do Xbox configurados uma vez no xemu",
         "x360": "Xenia Canary (instalado pelo Deck Commander); desempenho no Deck varia muito por jogo",
         "saturn": "BIOS do Saturn (sega_101.bin / mpr-17933.bin) em ~/Emulation/bios",
         "segacd": "BIOS do Sega CD (bios_CD_U.bin etc.) em ~/Emulation/bios",
         "n3ds": "jogos de 3DS DESCRIPTOGRAFADOS (o GodMode9 tem a opção de dump decriptado)",
         "wiiu": "chaves do Wii U (keys.txt) no Cemu para .wud/.wux"}

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


def _cfg(paths) -> Path:
    return paths.config / "emulators.json"


def _ler_cfg(paths) -> dict:
    import json
    try:
        return json.loads(_cfg(paths).read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def _mesmo(a: list[str], b: list[str]) -> bool:
    """Mesmo emulador? (Flatpak pelo id; AppImage/binário pelo caminho)."""
    if not a or not b:
        return False
    if a[0] == FLATPAK and b[0] == FLATPAK:
        return a[2:3] == b[2:3] and ("-L" not in a or a[a.index("-L") + 1:a.index("-L") + 2] ==
                                     (b[b.index("-L") + 1:b.index("-L") + 2] if "-L" in b else []))
    return a[0] == b[0]


def escolhas(paths, home: Path = H) -> list[dict]:
    """Para o painel: cada console com emulador encontrado, as opções e qual está valendo."""
    cfg = _ler_cfg(paths)
    out = []
    for console in OPCOES:
        ops = candidatos(console, home)
        if not ops:
            continue
        atual = cfg.get(console) or ops[0]["cmd"]
        nome = next((o["nome"] for o in ops if _mesmo(o["cmd"], atual)), ops[0]["nome"])
        out.append({"console": console, "label": CONSOLES[console]["label"], "opcoes": [o["nome"] for o in ops],
                    "atual": nome})
    return out


def escolher(paths, console: str, nome: str, home: Path = H) -> str:
    """Grava o emulador escolhido para o console (vale ao abrir o próximo jogo)."""
    import json
    op = next((o for o in candidatos(console, home) if o["nome"] == nome), None)
    if op is None:
        raise ValueError(f"{nome} não está instalado neste Deck")
    cfg = _ler_cfg(paths)
    cfg[console] = op["cmd"]
    _cfg(paths).parent.mkdir(parents=True, exist_ok=True)
    _cfg(paths).write_text(json.dumps(cfg, indent=1, ensure_ascii=False), "utf-8")
    return f"{CONSOLES[console]['label']}: agora abre no {nome}. Vale a partir do próximo jogo que você abrir."
