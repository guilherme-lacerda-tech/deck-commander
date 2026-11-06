"""Ponte com o plugin do Decky "Deck Commander": atalhos ao vivo, sem reiniciar o Steam.

O DC escreve plugin-queue.json (com as capas já baixadas em data/art/<game_id>/); o plugin cria o
atalho via SteamClient.Apps.AddShortcut, aplica as capas e grava plugin-done.json com o AppID que o
Steam gerou. `collect()` registra esses AppIDs em `provenance` (origem 'dc').
Sem o plugin instalado, o DC volta ao método antigo (gravar shortcuts.vdf + reiniciar o Steam).
"""
from __future__ import annotations

import glob
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .paths import Paths
from .store import Store

H = Path.home()


def installed(home: Path = H) -> bool:
    for pj in glob.glob(str(home / "homebrew/plugins/*/plugin.json")):
        try:
            if json.loads(Path(pj).read_text("utf-8")).get("name") == "Deck Commander":
                return True
        except (OSError, ValueError):
            pass
    return False


def _load(p: Path, default):
    try:
        return json.loads(p.read_text("utf-8"))
    except (OSError, ValueError):
        return default


def _save(p: Path, data) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    os.replace(tmp, p)


def queue_path(paths: Paths) -> Path:
    return paths.data / "plugin-queue.json"


def done_path(paths: Paths) -> Path:
    return paths.data / "plugin-done.json"


def prepare_art(paths: Paths, game_id: str, title: str) -> dict:
    """Baixa as capas para data/art/<game_id>/ (se houver chave do SteamGridDB)."""
    from . import artwork
    key = artwork.read_key(paths.secrets)
    if not key:
        return {}
    d = paths.data / "art" / game_id
    try:
        artwork.fetch_for("img", title, d, artwork.make_fetch(key))
    except Exception:  # noqa: BLE001 — sem capa não impede o jogo de entrar
        return {}
    kinds = {"imgp": "p", "img": "wide", "img_hero": "hero", "img_logo": "logo"}
    return {kinds[f.stem]: str(f) for f in d.iterdir() if f.stem in kinds}


def enqueue(paths: Paths, rows: list[dict], with_art: bool = True) -> int:
    q = _load(queue_path(paths), [])
    have = {x["game_id"] for x in q}
    n = 0
    for r in rows:
        gid = r["LaunchOptions"]
        if gid in have:
            continue
        q.append({"game_id": gid, "name": r["AppName"], "exe": r["exe"], "start_dir": r["StartDir"],
                  "launch_options": gid, "art": prepare_art(paths, gid, r["AppName"]) if with_art else {}})
        n += 1
    _save(queue_path(paths), q)
    items = _load(paths.data / "plugin-items.json", {})  # para a autocorreção do plugin
    items.update({x["game_id"]: x for x in q})
    _save(paths.data / "plugin-items.json", items)
    return n


def collect(paths: Paths, store: Store) -> list[str]:
    """Registra em provenance o que o plugin já criou. Retorna game_ids com erro."""
    done = _load(done_path(paths), {})
    errors = []
    now = datetime.now(timezone.utc).isoformat()
    with store.tx() as c:
        for gid, v in done.items():
            if v.get("appid"):
                # atalho recriado (autocorreção) ganha AppID novo: o antigo deixa de existir
                c.execute("DELETE FROM provenance WHERE operation_id=? AND appid<>?", (f"plugin:{gid}", str(v["appid"])))
                c.execute("INSERT OR IGNORE INTO provenance VALUES(?,?,?,?)", (str(v["appid"]), "dc", now, f"plugin:{gid}"))
            elif v.get("error"):
                errors.append(f"{gid}: {v['error']}")
    return errors


def pending(paths: Paths) -> list[str]:
    done = _load(done_path(paths), {})
    return [x["game_id"] for x in _load(queue_path(paths), []) if x["game_id"] not in done]
