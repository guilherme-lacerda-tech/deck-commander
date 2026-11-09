"""Auto-ajuste de qualidade por jogo: começa num nível que roda bem, sobe um passo a cada medição lisa e,
na primeira travada (mesmo leve), volta um passo e fixa ali. Sem perguntar nada ao usuário.

Medições vêm do benchmark (abre o jogo sozinho com o Deck parado, dc.bench) ou de partidas de verdade
(dc-launch). Se um jogo já fixado travar numa partida real, desce mais um passo (rede de segurança).
Ajuste manual pelo painel desliga o automático daquele jogo até voltar para "Automático".

Estado em state/autotune.json: game_id -> {level, fase: subindo|fixo|manual, trava_em, medidas}
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from . import quality, tuning
from .paths import Paths

SMOOTH = "liso"


def _file(paths: Paths) -> Path:
    return paths.state / "autotune.json"


def load(paths: Paths) -> dict:
    try:
        return json.loads(_file(paths).read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def _save(paths: Paths, data: dict) -> None:
    f = _file(paths)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_name(f.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    os.replace(tmp, f)


def start_level(console: str) -> int:
    """Um nível abaixo do equilibrado (mínimo nativo): o "OK" de onde a subida começa."""
    return max(1, tuning.level_for(console, "equilibrado") - 1)


def max_level(console: str) -> int:
    return min(quality.MAX.get(console, 4), tuning.level_for(console, "qualidade") + 1)


def ensure(paths: Paths, game_id: str, console: str) -> Optional[dict]:
    """Estado do jogo; cria no nível inicial (e grava a exceção de qualidade) se ainda não existe."""
    if not tuning.supported(console):
        return None
    data = load(paths)
    st = data.get(game_id)
    if st is None:
        st = {"level": start_level(console), "fase": "subindo", "trava_em": None, "medidas": 0}
        data[game_id] = st
        _save(paths, data)
        quality.set_override(paths, game_id, console, quality.LABEL[st["level"]])
    return st


def record(paths: Paths, game_id: str, console: str, verdict: Optional[str]) -> Optional[str]:
    """Aplica uma medição. Devolve o que mudou (texto) ou None."""
    st = ensure(paths, game_id, console)
    if st is None or verdict is None or st["fase"] == "manual":
        return None
    data = load(paths)
    st = data[game_id]
    st["medidas"] += 1
    lvl, msg = st["level"], None
    if verdict == SMOOTH:
        if st["fase"] == "subindo":
            if lvl < max_level(console) and (st["trava_em"] is None or lvl + 1 < st["trava_em"]):
                st["level"] = lvl + 1
                msg = f"liso em {quality.LABEL[lvl]}: testando {quality.LABEL[lvl + 1]}"
            else:
                st["fase"] = "fixo"
                msg = f"fixado em {quality.LABEL[lvl]} (máximo)"
    else:  # travou (mesmo leve): volta um passo e fixa
        st["trava_em"] = lvl if st["trava_em"] is None else min(st["trava_em"], lvl)
        if lvl > 1:
            st["level"] = lvl - 1
        st["fase"] = "fixo"
        msg = f"travou em {quality.LABEL[lvl]}: fixado em {quality.LABEL[st['level']]}"
    data[game_id] = st
    _save(paths, data)
    quality.set_override(paths, game_id, console, quality.LABEL[st["level"]])
    return msg


def set_manual(paths: Paths, game_id: str, manual: bool, console: str = "") -> None:
    """Escolha manual no painel congela o automático; 'Automático' volta a calibrar de onde parou."""
    data = load(paths)
    st = data.get(game_id)
    if st is None and manual:
        st = {"level": None, "fase": "manual", "trava_em": None, "medidas": 0}
    elif st is not None:
        st["fase"] = "manual" if manual else ("fixo" if st.get("trava_em") else "subindo")
        if not manual and st.get("level"):
            quality.set_override(paths, game_id, console, quality.LABEL[st["level"]])
    if st is not None:
        data[game_id] = st
        _save(paths, data)


def needs_calibration(paths: Paths, game_id: str, console: str) -> bool:
    st = load(paths).get(game_id)
    return tuning.supported(console) and (st is None or st.get("fase") == "subindo")
