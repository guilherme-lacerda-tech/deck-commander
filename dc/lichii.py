"""Pastas do Lichii (emulador de Switch/Switch 2, derivado do Eden).

A build 410 (instalada em 28/11/2026) trocou as pastas ~/.config/eden e ~/.local/share/eden por ~/.config/lichii e
~/.local/share/lichii. No Deck do dono a migração escolheu "Link Old Directory" (lichii -> eden), mas numa instalação
nova só existe "lichii". Todo código que procura config/saves do Lichii passa por aqui.
"""
from __future__ import annotations

from pathlib import Path


def pastas(home: Path) -> tuple[Path, Path]:
    """(config, dados) que o Lichii usa de fato: 'lichii' se existir (pasta ou link), senão 'eden'."""
    def escolher(base: Path) -> Path:
        nova, velha = base / "lichii", base / "eden"
        return nova if nova.exists() else velha
    return escolher(home / ".config"), escolher(home / ".local/share")


def saves(home: Path) -> Path:
    return pastas(home)[1] / "nand/user/save"
