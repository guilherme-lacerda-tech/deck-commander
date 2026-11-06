"""M2.3 — Abas do TabMaster geradas a partir dos atalhos do Deck Commander.

Uma aba por console (filtro whitelist com os AppIDs; some sozinha se vazia — autoHide) e uma aba
"Emuladores" com os atalhos de emulador. A aba padrão "Non-Steam" é escondida (v5.1 M2.3).
Abas que o usuário criou no TabMaster são preservadas; só as abas "dc-*" são reescritas.
O TabMaster lê o arquivo ao iniciar: as mudanças aparecem depois de reiniciar o Deck.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from .emulators import CONSOLES

SETTINGS = Path.home() / "homebrew/settings/TabMaster/settings.json"
GAMES_AND_SOFTWARE = 1 | 2
EMULATOR_HINTS = ("pcsx2", "duckstation", "ryujinx", "lichii", "dolphin", "retroarch", "ppsspp", "eden")
ORDER = ["ps2", "psx", "switch", "switch2", "gc", "wii", "psp", "n64", "snes", "gba"]


def _tab(tid: str, title: str, pos: int, appids: list[int]) -> dict:
    return {"id": tid, "title": title, "position": pos,
            "filters": [{"type": "whitelist", "inverted": False, "params": {"games": sorted(appids)}}],
            "filtersMode": "and", "categoriesToInclude": GAMES_AND_SOFTWARE, "autoHide": True,
            "visibleToOthers": False, "sortByOverride": -1}


def build(tabs: dict, shortcuts: list[dict], launch_map: dict) -> dict:
    by_console: dict[str, list[int]] = {c: [] for c in ORDER}
    emus: list[int] = []
    for r in shortcuts:
        appid = (r.get("appid") or 0) & 0xFFFFFFFF
        exe = (r.get("exe") or r.get("Exe") or "").lower()
        if "dc-launch" in exe:
            entry = launch_map.get(r.get("LaunchOptions", ""))
            if entry and entry["console"] in by_console:
                by_console[entry["console"]].append(appid)
        elif any(h in exe or h in (r.get("LaunchOptions") or "").lower() for h in EMULATOR_HINTS) \
                and "unifideck" not in exe:
            emus.append(appid)
    out = {k: v for k, v in tabs.items() if not k.startswith("dc-")}
    if "DesktopApps" in out:
        out["DesktopApps"] = {**out["DesktopApps"], "position": -1}
    # empurra as abas existentes visíveis para abrir espaço depois de "Favorites"
    visible = sorted((t for t in out.values() if t.get("position", -1) > -1), key=lambda t: t["position"])
    head = [t for t in visible if t["id"] in ("GreatOnDeck", "AllGames", "Installed", "Favorites")]
    tail = [t for t in visible if t not in head]
    pos = 0
    for t in head:
        out[t["id"]] = {**t, "position": pos}; pos += 1
    for c in ORDER:
        out[f"dc-{c}"] = _tab(f"dc-{c}", CONSOLES[c]["label"], pos, by_console[c]); pos += 1
    out["dc-emuladores"] = _tab("dc-emuladores", "Emuladores", pos, emus); pos += 1
    for t in tail:
        out[t["id"]] = {**t, "position": pos}; pos += 1
    return out


def apply(shortcuts: list[dict], launch_map: dict, user_id: str, settings_path: Path = SETTINGS) -> dict:
    data = json.loads(settings_path.read_text("utf-8"))
    user = data.setdefault("usersDict", {}).setdefault(str(user_id), {})
    new = build(user.get("tabs", {}), shortcuts, launch_map)
    if new == user.get("tabs"):
        return {}
    bak = settings_path.with_name("settings.json.antes-deck-commander")
    if not bak.exists():
        shutil.copy2(settings_path, bak)
    user["tabs"] = new
    tmp = settings_path.with_name("settings.json.dc-tmp")
    tmp.write_text(json.dumps(data, indent=4, ensure_ascii=False), "utf-8")
    os.replace(tmp, settings_path)
    return {k: len(v["filters"][0]["params"]["games"]) for k, v in new.items() if k.startswith("dc-")}
