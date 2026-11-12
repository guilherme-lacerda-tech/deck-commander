"""M2.5 — Artes do SteamGridDB para os atalhos do Deck Commander.

Grava em userdata/<id>/config/grid/ com os nomes que o Steam usa:
  <appid>p.<ext> (capa vertical) · <appid>.<ext> (capa horizontal) · <appid>_hero.<ext> · <appid>_logo.<ext>
Nunca sobrescreve arte existente (pode ter sido escolhida pelo usuário). A chave fica em
~/.config/deck-commander/secrets/steamgriddb (600) e nunca é exportada nem logada.
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

API = "https://www.steamgriddb.com/api/v2"
KINDS = [  # (endpoint, parâmetros, sufixo do arquivo)
    ("grids", {"dimensions": "600x900"}, "p"),
    ("grids", {"dimensions": "920x430,460x215"}, ""),
    ("heroes", {}, "_hero"),
    ("logos", {}, "_logo"),
]
_STRIP = [re.compile(p, re.IGNORECASE) for p in (r"\([^)]*\)", r"\[[^\]]*\]", r"\bvers[aã]o\s+i\.?a\.?", r"\bdublado\b")]

Fetch = Callable[[str, dict], bytes]


def search_term(title: str) -> str:
    t = title
    for rx in _STRIP:
        t = rx.sub("", t)
    t = re.sub(r"\s{2,}", " ", t).strip(" -")
    return re.sub(r"\s+1$", "", t)  # "God of War 1" -> "God of War" (senão o site devolve o II)


def best_match(results: list[dict], term: str) -> dict:
    norm = lambda s: re.sub(r"[^a-z0-9]+", "", s.casefold())  # noqa: E731
    exact = [r for r in results if norm(r.get("name", "")) == norm(term)]
    return (exact or results)[0]


def read_key(secrets_dir: Path) -> str | None:
    p = Path(secrets_dir) / "steamgriddb"
    try:
        k = p.read_text("utf-8").strip()
        return k or None
    except OSError:
        return None


def make_fetch(key: str) -> Fetch:
    def fetch(url: str, headers: dict) -> bytes:
        h = {"User-Agent": "deck-commander/0.1", **headers}
        if url.startswith(API):
            h["Authorization"] = f"Bearer {key}"
        with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30) as r:
            return r.read()
    return fetch


def _api(fetch: Fetch, path: str, params: dict | None = None):
    url = f"{API}/{path}" + (("?" + urllib.parse.urlencode(params)) if params else "")
    data = json.loads(fetch(url, {}))
    if not data.get("success", False):
        raise RuntimeError(f"SteamGridDB: {data.get('errors') or data}")
    return data["data"]


def fetch_for(appid32: int, title: str, grid_dir: Path, fetch: Fetch) -> dict:
    """Baixa o que faltar para um atalho. Retorna {'game': nome encontrado, 'saved': [...], 'skipped': [...]}."""
    grid_dir.mkdir(parents=True, exist_ok=True)
    term = search_term(title)
    found = _api(fetch, "search/autocomplete/" + urllib.parse.quote(term))
    if not found:
        return {"game": None, "saved": [], "skipped": [], "error": "não encontrado"}
    game = best_match(found, term)
    out = {"game": game.get("name"), "saved": [], "skipped": []}
    for endpoint, params, suffix in KINDS:
        base = f"{appid32}{suffix}"
        if any(grid_dir.glob(base + ".*")):
            out["skipped"].append(base)
            continue
        items = _api(fetch, f"{endpoint}/game/{game['id']}", params)
        if not items:
            continue
        url = items[0]["url"]
        ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower() or ".png"
        target = grid_dir / f"{base}{ext}"
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_bytes(fetch(url, {}))
        os.replace(tmp, target)
        out["saved"].append(target.name)
    return out
