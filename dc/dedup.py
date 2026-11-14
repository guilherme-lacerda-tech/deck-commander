"""Duplicatas de jogos: identidade do jogo, checagem antes de baixar e relatório da biblioteca.

Identidade (`match_key`):
- Switch: Title ID do jogo-base (o mesmo jogo em .nsp/.xci/versões diferentes tem o mesmo ID);
- demais: nome sem região/versão/tags `(USA)`, `[!]`, `(v1.1)`…, algarismos romanos viram números
  ("God of War II" = "God of War 2"). Tradução/ROM hack (M4.10) é OUTRO jogo de propósito.
Nada aqui apaga arquivos — só identifica. Remoção é `dc.remove` (com confirmação).
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from pathlib import Path

_TID = re.compile(r"\[?([0-9A-Fa-f]{16})\]?")
_BRACKETS = re.compile(r"\([^)]*\)|\[[^\]]*\]|\{[^}]*\}")
_ROMAN = {"ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7", "viii": "8", "ix": "9", "x": "10"}
_JUNK = re.compile(r"\b(nsp|xci|nsz|xcz|iso|chd|rvz|wbfs|cso|pbp|multi\d*|repack|update|dlc|eshop|"
                   r"switch|ps2|psx|ps1|psp|gamecube|wii|gba|snes|n64|ntsc|pal|usa|eur|europe|japan|"
                   r"dublado|legendado|ptbr|pt-br)\b", re.IGNORECASE)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[_.]+", " ", s)
    return s


def base_title_id(name: str) -> str | None:
    """Title ID do jogo-base (update ...800 e DLC apontam para o mesmo jogo)."""
    m = _TID.search(name or "")
    if not m:
        return None
    # IDs de jogo-base são múltiplos de 0x2000; update = base+0x800, DLC = base+0x1000+n
    return f"{int(m.group(1), 16) & ~0x1FFF:016X}"


def match_key(title: str, console: str | None = None, path: str = "") -> str:
    from .content import is_translation
    if console == "switch":
        tid = base_title_id(Path(path).name) or base_title_id(title)
        if tid:
            return f"switch:{tid}"
    raw = f"{title} {Path(path).name}" if path else title
    tr = "+tr" if is_translation(raw) else ""
    t = _BRACKETS.sub(" ", _norm(title))
    t = re.sub(r"\.(zip|7z|rar|torrent)$", "", t)
    t = _JUNK.sub(" ", t)
    words = [_ROMAN.get(w, w) for w in re.findall(r"[a-z0-9]+", t)]
    words = [w for w in words if w not in ("the", "a", "o", "and", "e")]
    return f"{console or '?'}:{' '.join(words)}{tr}"


def same_game(a: str, b: str) -> bool:
    """Compara chaves ignorando o console quando um dos lados é desconhecido ('?')."""
    ca, ta = a.split(":", 1)
    cb, tb = b.split(":", 1)
    return ta == tb and bool(ta) and (ca == cb or "?" in (ca, cb))


def library_dups(launch_map: dict) -> list[list[str]]:
    """Grupos de game_ids que são o mesmo jogo (mesmo console). Ordem: o mais antigo no mapa primeiro."""
    groups: dict[str, list[str]] = defaultdict(list)
    for gid, e in launch_map.items():
        if e.get("removed"):
            continue
        groups[match_key(e.get("title", gid), e.get("console"), e.get("rom", ""))].append(gid)
    return [v for v in groups.values() if len(v) > 1]


def find_existing(name: str, console: str | None, launch_map: dict, torrents: list[dict] = ()) -> str | None:
    """Antes de baixar: devolve uma descrição do que já existe com o mesmo jogo, ou None."""
    from .library import clean_title
    stem = re.sub(r"\.(torrent|zip|7z|rar)$", "", name or "", flags=re.IGNORECASE)
    key = match_key(clean_title(stem), console, stem)
    for gid, e in launch_map.items():
        if e.get("removed"):
            continue
        if same_game(key, match_key(e.get("title", gid), e.get("console"), e.get("rom", ""))):
            return f"«{e.get('title', gid)}» já está na biblioteca"
    for t in torrents:
        tk = match_key(clean_title(re.sub(r"\.(zip|7z|rar)$", "", t.get("name", ""), flags=re.IGNORECASE)),
                       t.get("category") if t.get("category") not in (None, "", "auto") else console, t.get("name", ""))
        if same_game(key, tk):
            pct = round((t.get("progress") or 0) * 100)
            return f"«{t.get('name')}» já está nos downloads ({pct}%)"
    return None


# -- nome de dentro do .torrent (bencode mínimo: só o necessário para info.name) ----------------
def _bdecode(data: bytes, i: int = 0):
    c = data[i:i + 1]
    if c == b"i":
        j = data.index(b"e", i)
        return int(data[i + 1:j]), j + 1
    if c == b"l":
        out, i = [], i + 1
        while data[i:i + 1] != b"e":
            v, i = _bdecode(data, i)
            out.append(v)
        return out, i + 1
    if c == b"d":
        out, i = {}, i + 1
        while data[i:i + 1] != b"e":
            k, i = _bdecode(data, i)
            v, i = _bdecode(data, i)
            out[k] = v
        return out, i + 1
    j = data.index(b":", i)
    n = int(data[i:j])
    return data[j + 1:j + 1 + n], j + 1 + n


def torrent_name(data: bytes) -> str | None:
    try:
        d, _ = _bdecode(data)
        n = d[b"info"].get(b"name.utf-8") or d[b"info"][b"name"]
        return n.decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 — .torrent estranho: segue sem checagem
        return None


def info_hash(data: bytes) -> str | None:
    """Código do torrent (o mesmo que o qBittorrent usa): sha1 do dicionário "info" exatamente como está no arquivo."""
    import hashlib
    try:
        if data[:1] != b"d":
            return None
        i = 1
        while data[i:i + 1] != b"e":
            k, i = _bdecode(data, i)
            ini = i
            _v, i = _bdecode(data, i)
            if k == b"info":
                return hashlib.sha1(data[ini:i]).hexdigest()
    except Exception:  # noqa: BLE001 — .torrent estranho
        return None
    return None


def magnet_hash(magnet: str) -> str | None:
    """Código do torrent de um magnet (hex ou base32), em hex minúsculo."""
    import base64
    m = re.search(r"(?i)btih:([0-9a-f]{40}|[a-z2-7]{32})(?![0-9a-z])", magnet or "")
    if not m:
        return None
    h = m.group(1).lower()
    return base64.b32decode(h.upper()).hex() if len(h) == 32 else h


def magnet_name(magnet: str) -> str | None:
    from urllib.parse import parse_qs, urlparse
    q = parse_qs(urlparse(magnet).query)
    return (q.get("dn") or [None])[0]


def pt_redundant(launch_map: dict) -> list[tuple[str, str]]:
    """Mesmo jogo duas vezes e só uma delas em português (dublada/traduzida pelo nome): devolve
    [(game_id que sai da biblioteca, game_id em português que fica)]. Ex.: "Shadow of the Colossus" e
    "Shadow of the Colossus (Dub-e-Leg)". Só o atalho sai (remove.hide); /devolver traz de volta."""
    from .traducao.portugues import is_pt_name
    out = []
    for grp in library_dups(launch_map):
        pt = [g for g in grp if is_pt_name(launch_map[g].get("title", ""), launch_map[g].get("rom", ""))]
        if len(pt) == 1:
            out += [(g, pt[0]) for g in grp if g != pt[0]]
    return out
