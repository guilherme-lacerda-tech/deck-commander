"""M2.3 — Abas do TabMaster geradas a partir dos atalhos do Deck Commander.

Uma aba por console (filtro whitelist com os AppIDs; some sozinha se vazia — autoHide), uma aba
"Emuladores" e uma aba por loja do Unifideck (Epic, GOG...), pedido do usuário em 2026-11-06. A aba padrão "Non-Steam" é escondida (v5.1 M2.3).
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
STORE_TITLES = {"epic": "Epic Games", "gog": "GOG", "amazon": "Amazon Games", "itch": "itch.io"}
ORDER = ["ps2", "psx", "switch", "switch2", "gc", "wii", "psp", "n64", "snes", "gba"]


COLLECTION_IDS: dict[str, str] = {}  # título -> id da coleção do Steam (preenchido por apply())


def _tab(tid: str, title: str, pos: int, appids: list[int]) -> dict:
    cid = COLLECTION_IDS.get(title)
    flt = ({"type": "collection", "inverted": False, "params": {"id": cid, "name": title}} if cid else
           {"type": "whitelist", "inverted": False, "params": {"games": sorted(appids)}})
    return {"id": tid, "title": title, "position": pos,
            "filters": [flt],
            "filtersMode": "and", "categoriesToInclude": GAMES_AND_SOFTWARE, "autoHide": True,
            "visibleToOthers": False, "sortByOverride": -1}


def groups(shortcuts: list[dict], launch_map: dict, plugin_done: dict | None = None) -> dict[str, list[int]]:
    """Título da aba/coleção -> AppIDs. Inclui atalhos criados ao vivo pelo plugin (plugin-done.json)."""
    rows = list(shortcuts)
    known = {r.get("LaunchOptions") for r in rows}
    for gid, v in (plugin_done or {}).items():
        if v.get("appid") and gid not in known:
            rows.append({"appid": v["appid"], "exe": "dc-launch", "LaunchOptions": gid})
    tabs = build({}, rows, launch_map, _ids_only=True)
    return {t["title"]: t["_apps"] for t in tabs.values()}


def build(tabs: dict, shortcuts: list[dict], launch_map: dict, _ids_only: bool = False) -> dict:
    by_console: dict[str, list[int]] = {c: [] for c in ORDER}
    emus: list[int] = []
    stores: dict[str, list[int]] = {}
    for r in shortcuts:
        appid = (r.get("appid") or 0) & 0xFFFFFFFF
        exe = (r.get("exe") or r.get("Exe") or "").lower()
        if "unifideck" in exe:  # lojas do Unifideck: a etiqueta diz a loja (Epic, Gog...)
            tags = [v for v in (r.get("tags") or {}).values() if v not in ("Installed", "Not Installed")]
            for tg in tags[:1]:
                stores.setdefault(tg, []).append(appid)
            continue
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
    for store in sorted(stores):  # uma aba por loja, logo depois dos Favoritos
        title = STORE_TITLES.get(store.lower(), store)
        out[f"dc-loja-{store.lower()}"] = _tab(f"dc-loja-{store.lower()}", title, pos, stores[store]); pos += 1
    for c in ORDER:
        out[f"dc-{c}"] = _tab(f"dc-{c}", CONSOLES[c]["label"], pos, by_console[c]); pos += 1
    out["dc-emuladores"] = _tab("dc-emuladores", "Emuladores", pos, emus); pos += 1
    for t in tail:
        out[t["id"]] = {**t, "position": pos}; pos += 1
    if _ids_only:
        apps = {f"dc-{c}": by_console[c] for c in ORDER}
        apps["dc-emuladores"] = emus
        apps.update({f"dc-loja-{s.lower()}": v for s, v in stores.items()})
        return {k: {"title": v["title"], "_apps": sorted(set(apps[k]))} for k, v in out.items() if k in apps}
    return out


def write_collections(data_dir: Path, shortcuts: list[dict], launch_map: dict) -> dict:
    """Gera collections.json para o plugin manter as coleções do Steam (atualização ao vivo das abas)."""
    try:
        done = json.loads((data_dir / "plugin-done.json").read_text("utf-8"))
    except (OSError, ValueError):
        done = {}
    # consoles e Emuladores sempre existem (mesmo vazios) para as abas acompanharem ao vivo; lojas só se houver jogos
    spec = {k: v for k, v in groups(shortcuts, launch_map, done).items()
            if v or k in {CONSOLES[c]["label"] for c in ORDER} | {"Emuladores"}}
    tmp = data_dir / "collections.json.tmp"
    tmp.write_text(json.dumps(spec, ensure_ascii=False, indent=1), "utf-8")
    os.replace(tmp, data_dir / "collections.json")
    return spec


def load_collection_ids(data_dir: Path) -> None:
    try:
        COLLECTION_IDS.clear()
        COLLECTION_IDS.update(json.loads((data_dir / "collection-ids.json").read_text("utf-8")))
    except (OSError, ValueError):
        pass


def apply(shortcuts: list[dict], launch_map: dict, user_id: str, settings_path: Path = SETTINGS,
          data_dir: Path | None = None) -> dict:
    if data_dir is not None:
        write_collections(data_dir, shortcuts, launch_map)
        load_collection_ids(data_dir)
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
    return {k: v["filters"][0]["type"] for k, v in new.items() if k.startswith("dc-")}
