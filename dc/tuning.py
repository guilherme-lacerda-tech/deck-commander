"""Presets de qualidade: Bateria / Equilibrado / Qualidade, por console (padrão) ou por jogo (exceção).

Os números vêm de recomendações públicas para o Steam Deck (tela 1280x800, APU de ~15 W) e devem ser
conferidos com a medição real (dc.perf): onde um jogo travar no "equilibrado", o ajuste por jogo resolve.
- PS1 (DuckStation): 3x = 720p, já preenche a tela; 4x+ só antisserrilha e gasta bateria.
- PS2 (PCSX2): 2x é o ponto de equilíbrio; 3x trava jogos pesados (Shadow of the Colossus, God of War II).
- PSP (PPSSPP): 3x = 816p; quase todos os jogos aguentam.
- GameCube/Wii (Dolphin): 2x preenche; Wii pesado (Mario Galaxy, Xenoblade) pode pedir 1x.
- Switch (Ryujinx): 1x (720p portátil); 2x só para jogos 2D/leves.
- 3DS (Azahar): 2x é leve para quase tudo; 3x em jogos 2D.
"""
from __future__ import annotations


from . import quality
from .paths import Paths

NAMES = ("bateria", "equilibrado", "qualidade")
PRESETS = {
    "psx": (2, 3, 4),
    "ps2": (1, 2, 3),
    "psp": (2, 3, 4),
    "gc": (1, 2, 3),
    "wii": (1, 2, 3),
    "switch": (1, 1, 2),
    "n3ds": (1, 2, 3),
}
LABEL = {"bateria": "🔋 Bateria", "equilibrado": "⚖️ Equilibrado", "qualidade": "✨ Qualidade"}


def supported(console: str) -> bool:
    return console in PRESETS and quality.supported(console)


def level_for(console: str, preset: str) -> int:
    if preset not in NAMES:
        raise ValueError("use: bateria, equilibrado ou qualidade")
    return PRESETS[console][NAMES.index(preset)]


def preset_of(console: str, level: int | None) -> str | None:
    """Nome do preset que corresponde a um nível (o mais econômico, se dois coincidirem)."""
    if console not in PRESETS or level is None:
        return None
    return next((n for n, v in zip(NAMES, PRESETS[console]) if v == level), None)


def console_level(console: str) -> int | None:
    """Resolução global atual do emulador (o padrão do console)."""
    t = quality._target(console) if quality.supported(console) else None
    if not t:
        return None
    v = quality._read(*t)
    try:
        return int(float(v)) if v is not None else None
    except ValueError:
        return None


def apply_console(console: str, preset: str) -> str:
    """Muda o padrão do console (vale para todos os jogos dele sem exceção própria)."""
    if not supported(console):
        return "Esse console ainda não tem presets (roda na resolução do emulador)."
    t = quality._target(console)
    if not t:
        return "Abra o emulador uma vez para ele criar a configuração; depois aplico o preset."
    n = level_for(console, preset)
    fmt, f, sec, key = t
    quality._write(fmt, f, sec, key, str(n))
    if console == "n3ds":  # Qt guarda "usar o padrão" ao lado; sem isto o Azahar ignora o valor
        quality._write(fmt, f, sec, key + "\\default", "false")
    return f"{LABEL[preset]} para todo o console: {quality.LABEL.get(n, str(n) + 'x')}"


def apply_game(paths: Paths, game_id: str, console: str, preset: str | None) -> str:
    """Preset só para um jogo (None = volta ao padrão do console)."""
    if preset is None:
        return quality.set_override(paths, game_id, console, None)
    if not supported(console):
        return "Esse console ainda não tem presets (roda na resolução do emulador)."
    n = level_for(console, preset)
    return quality.set_override(paths, game_id, console, quality.LABEL[n])
