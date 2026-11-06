"""adapter-duckstation — chaves confirmadas no Deck do usuário em 2026-11-06
(~/.local/share/duckstation/settings.ini, AppImage)."""
from . import IniAdapter


def _bool(v: bool) -> str:
    return "true" if v else "false"


class DuckStation(IniAdapter):
    name = "duckstation"
    FIELDS = {
        "resolution_scale": ("GPU", "ResolutionScale", str),
        "backend": ("GPU", "Renderer", str),          # Vulkan / OpenGL / Software
        "widescreen_hack": ("GPU", "WidescreenHack", _bool),
    }
    # aspect_ratio/shader/frame_limit: valores ainda não mapeados com segurança -> não mexe
    UNSUPPORTED = ("aspect_ratio", "shader", "frame_limit", "precision")
    PROFILES = {"ps1": {
        "economico":   {"resolution_scale": 2, "backend": "Vulkan", "widescreen_hack": False},
        "equilibrado": {"resolution_scale": 4, "backend": "Vulkan", "widescreen_hack": False},
        "desempenho":  {"resolution_scale": 6, "backend": "Vulkan", "widescreen_hack": False},
    }}
