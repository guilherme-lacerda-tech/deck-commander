"""Dispositivos de destino e o que cada um roda — sem benchmark inventado.

Cada classificação diz de onde veio. "varia por jogo" = não há medição deste jogo; o Deck Commander não promete.
"""
from __future__ import annotations

# Steam Deck: emuladores instalados/gerenciados pelo Deck Commander (dc/emulators). Consoles pesados dependem do jogo.
DECK_BOM = {"nes", "snes", "gb", "gbc", "gba", "genesis", "sms", "gg", "segacd", "saturn", "pce", "n64", "nds",
            "psx", "psp", "ps2", "gc", "wii", "dc", "doom", "arcade", "xbox", "n3ds", "pc"}
DECK_VARIA = {"switch", "wiiu", "ps3", "x360"}
# RG505 (Android): política do RG505 Commander (Codex, 20/11/2026): automático só onde o desempenho é consistente.
RG505_BOM = {"nes", "snes", "gb", "gbc", "gba", "genesis", "sms", "psx", "psp", "n64", "nds"}
RG505_NAO = {"ps2", "gc", "wii", "n3ds", "switch", "switch2", "xbox", "x360", "ps3", "wiiu", "pc"}

DISPOSITIVOS = {
    "deck": {"nome": "Steam Deck", "envio": True},
    "rg505": {"nome": "RG505", "envio": False},  # ainda não ligado a este bot (o RG505 Commander é outro bot no PC)
}


def compatibilidade(dispositivo: str, console: str | None) -> tuple[str, str]:
    """(nível, explicação). nível: "bom" | "varia" | "nao" | "?"."""
    if not console:
        return "?", "plataforma não identificada"
    if console == "switch2":
        return "nao", "Switch 2 ainda não tem emulador utilizável"
    if dispositivo == "deck":
        if console in DECK_BOM:
            return "bom", "emulador suportado pelo Deck Commander"
        if console in DECK_VARIA:
            return "varia", "roda, mas o desempenho varia por jogo (sem medição deste jogo)"
        return "?", "sem perfil para essa plataforma"
    if dispositivo == "rg505":
        if console in RG505_BOM:
            return "bom", "plataforma com desempenho consistente no RG505"
        if console in RG505_NAO:
            return "nao", "desempenho inconsistente no RG505 (política do RG505 Commander)"
        return "?", "sem perfil para essa plataforma no RG505"
    return "?", "dispositivo desconhecido"


SIMBOLO = {"bom": "✅", "varia": "⚠️", "nao": "❌", "?": "❔"}
