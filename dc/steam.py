"""Localiza o usuário Steam ativo (Decks com mais de uma conta) e os arquivos dele.

Ordem: conta marcada "MostRecent" em config/loginusers.vdf -> pasta userdata modificada por último.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from .vdf import load_text

STEAM_ROOT = Path.home() / ".steam/steam"
STEAMID64_BASE = 76561197960265728


def userdata_dir(root: Path = STEAM_ROOT) -> Path:
    base = root / "userdata"
    users = [d for d in base.iterdir() if d.is_dir() and d.name.isdigit() and d.name != "0"] if base.is_dir() else []
    if not users:
        raise FileNotFoundError(f"nenhum usuário Steam em {base} — abra o Steam e faça login uma vez")
    recent = most_recent_account(root)
    if recent and (base / recent).is_dir():
        return base / recent
    return max(users, key=lambda d: (d / "config/localconfig.vdf").stat().st_mtime
               if (d / "config/localconfig.vdf").exists() else d.stat().st_mtime)


def most_recent_account(root: Path = STEAM_ROOT) -> Optional[str]:
    try:
        users = load_text((root / "config/loginusers.vdf").read_text("utf-8", "replace")).get("users", {})
    except OSError:
        return None
    for sid64, info in users.items():
        if str(info.get("MostRecent", "0")) == "1" and sid64.isdigit():
            return str(int(sid64) - STEAMID64_BASE)
    return None


def shortcuts_path(root: Path = STEAM_ROOT) -> Path:
    return userdata_dir(root) / "config/shortcuts.vdf"
