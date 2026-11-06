"""adapter-pcsx2 — chaves confirmadas no Deck do usuário em 2026-11-06
(Flatpak net.pcsx2.PCSX2 v2.6.3: ~/.var/app/net.pcsx2.PCSX2/config/PCSX2/inis/PCSX2.ini)."""
from . import IniAdapter


def _bool(v: bool) -> str:
    return "true" if v else "false"


class PCSX2(IniAdapter):
    name = "pcsx2"
    FIELDS = {
        "resolution_scale": ("EmuCore/GS", "upscale_multiplier", str),
        "backend": ("EmuCore/GS", "Renderer", str),   # -1 = Automático (14 = Vulkan forçado gera aviso na tela)
        "widescreen_hack": ("EmuCore", "EnableWideScreenPatches", _bool),
    }
    UNSUPPORTED = ("aspect_ratio", "shader", "frame_limit", "precision")
    PROFILES = {"ps2": {
        "economico":   {"resolution_scale": 1, "backend": -1, "widescreen_hack": False},
        "equilibrado": {"resolution_scale": 2, "backend": -1, "widescreen_hack": False},
        "desempenho":  {"resolution_scale": 3, "backend": -1, "widescreen_hack": False},
    }}
