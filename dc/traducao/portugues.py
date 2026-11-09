"""Quais jogos estão em português (para a aba "Em português" e para abrir no idioma certo).

Um jogo conta como "em português" se:
- Switch com PT-BR OFICIAL (lido do control.nacp do jogo, com a atualização) — e então ele abre com o
  Ryujinx em "BrazilianPortuguese" só para ele (os outros continuam em inglês);
- Switch com o mod de tradução do Deck Commander instalado;
- ROM com marca de tradução/dublagem no nome ((BR), PT-BR, Dublado, DUB, Dub-e-Leg, romsportugues…).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

PT_RX = re.compile(r"(?<![a-z])(pt-?br|br|dublado|dub(?:-ia)?|dub-e-leg|legendado|portugu[eê]s|traduzido|"
                   r"vers[aã]o\s*i\.?\s*a\.?)(?![a-z])|romsportugues", re.I)
OFFICIAL = "BrazilianPortuguese"


def idiomas_path(data_dir: Path) -> Path:
    return data_dir / "traducao" / "idiomas.json"


def load_idiomas(data_dir: Path) -> dict:
    try:
        return json.loads(idiomas_path(data_dir).read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def is_pt_name(title: str, rom: str = "") -> bool:
    return bool(PT_RX.search(title) or PT_RX.search(Path(rom).name))


def has_dc_mod(rom: str) -> bool:
    from ..dedup import base_title_id
    from .switch import mod_target
    tid = base_title_id(Path(rom).name)
    return bool(tid) and (mod_target(tid) / "romfs").is_dir()


def status(gid: str, entry: dict, idiomas: dict) -> Optional[str]:
    """'oficial' | 'mod' | 'traduzido' | None"""
    if entry.get("console") == "switch":
        if idiomas.get(gid, {}).get("ptbr") == "oficial":
            return "oficial"
        if has_dc_mod(entry.get("rom", "")):
            return "mod"
    if is_pt_name(entry.get("title", ""), entry.get("rom", "")):
        return "traduzido"
    return None


def pt_gids(data_dir: Path, launch_map: dict) -> dict[str, str]:
    idi = load_idiomas(data_dir)
    out = {}
    for gid, e in launch_map.items():
        if e.get("removed"):
            continue
        s = status(gid, e, idi)
        if s:
            out[gid] = s
    return out


def detect_switch(paths, launch_map: dict, roots: list[Path], log=lambda s: None) -> dict:
    """Lê os idiomas de cada jogo de Switch (só quando base/atualização mudaram) e liga o PT-BR
    oficial por jogo. Devolve {gid: {...}}."""
    from .. import quality
    from ..dedup import base_title_id
    from . import converter, extract, nca, switch
    kp = switch.keys_path()
    if not kp:
        return {}
    keys = nca.load_keys(kp)
    idi = load_idiomas(paths.data)
    changed = False
    for gid, e in launch_map.items():
        if e.get("console") != "switch" or e.get("removed"):
            continue
        rom = Path(e["rom"])
        tid = base_title_id(rom.name)
        if not tid or not rom.exists():
            continue
        upd = extract.latest_update(converter.collect(roots, tid))
        sig = [rom.name, upd.name if upd else None]
        if idi.get(gid, {}).get("sig") == sig:
            continue
        try:
            langs = nca.game_languages(rom, keys, upd)
        except (nca.NcaError, OSError) as ex:
            log(f"{e.get('title')}: {ex}")
            idi[gid] = {"sig": sig, "erro": str(ex)}
            changed = True
            continue
        ptbr = "oficial" if OFFICIAL in langs else "nao"
        idi[gid] = {"sig": sig, "langs": langs, "ptbr": ptbr, "title_id": tid}
        if ptbr == "oficial":
            quality.set_language(paths, gid, OFFICIAL, "português oficial do jogo")
        elif quality.get_language(paths, gid) == OFFICIAL:
            quality.set_language(paths, gid, None)
        changed = True
    if changed:
        p = idiomas_path(paths.data)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(idi, ensure_ascii=False, indent=1), "utf-8")
        tmp.replace(p)
    return idi
