"""Backend do plugin Deck Commander (roda como o usuário, sem root).

Só lê/escreve dentro de ~/.local/share/deck-commander:
  plugin-queue.json  — jogos esperando virar atalho (gerado pelo /sync)
  plugin-done.json   — resultado (game_id -> appid ou erro), lido pelo Deck Commander
"""
import base64
import json
import os

try:
    import decky
    HOME = decky.DECKY_USER_HOME
except Exception:  # noqa: BLE001
    HOME = os.path.expanduser("~")

BASE = os.path.join(HOME, ".local/share/deck-commander")
QUEUE = os.path.join(BASE, "plugin-queue.json")
DONE = os.path.join(BASE, "plugin-done.json")
ITEMS = os.path.join(BASE, "plugin-items.json")  # escrito pelo Deck Commander e pelo plugin


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


class Plugin:
    async def get_pending(self):
        done = _load(DONE, {})
        return [q for q in _load(QUEUE, []) if q.get("game_id") not in done]

    async def get_done(self):
        items = _load(ITEMS, {})
        return {k: {**v, "item": items.get(k)} for k, v in _load(DONE, {}).items()}

    async def remember_item(self, game_id, item):
        """Guarda o item para a autocorreção poder recriar o atalho se ele sumir."""
        items = _load(ITEMS, {})
        items[game_id] = item
        _save(ITEMS, items)
        return True

    async def report(self, game_id, appid, error):
        done = _load(DONE, {})
        done[game_id] = {"appid": int(appid or 0), "error": error or ""}
        _save(DONE, done)
        if not error:
            _save(QUEUE, [q for q in _load(QUEUE, []) if q.get("game_id") != game_id])
        return True

    async def read_art(self, path):
        real = os.path.realpath(path)
        if not real.startswith(os.path.realpath(BASE) + os.sep) or not os.path.isfile(real):
            return None  # só imagens preparadas pelo Deck Commander
        with open(real, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        return {"data": data, "ext": os.path.splitext(real)[1].lstrip(".").lower() or "png"}

    async def get_collections(self):
        """{nome da coleção: [appids]} gerado pelo Deck Commander (consoles, Emuladores, lojas)."""
        return _load(os.path.join(BASE, "collections.json"), {})

    async def set_collection_ids(self, ids):
        path = os.path.join(BASE, "collection-ids.json")
        cur = _load(path, {})
        if cur != ids:
            _save(path, ids)
        return True

    async def get_status(self):
        done = _load(DONE, {})
        return {"pending": len(await self.get_pending()),
                "added": sum(1 for v in done.values() if v.get("appid")),
                "errors": [k for k, v in done.items() if v.get("error")][-5:]}

    async def _main(self):
        os.makedirs(BASE, exist_ok=True)

    async def _unload(self):
        pass
