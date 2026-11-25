"""Potência mínima já comprovada por jogo, sem trocar qualidade por bateria.

O TDP do console continua sendo o piso seguro. Quando o monitor ao vivo precisou subir a
potência e a partida ficou lisa por tempo suficiente, guardamos apenas aquele menor valor.
Na próxima abertura o jogo começa nesse ponto, evitando repetir a queda inicial.
"""
from __future__ import annotations

from .arquivo_json import gravar as _gravar
from .arquivo_json import ler as _ler


def _arquivo(paths):
    return paths.state / "tdp-por-jogo.json"


def recomendado(paths, game_id: str, console: str) -> int | None:
    """TDP previamente estável do jogo; dados inválidos nunca viram ajuste de energia."""
    dados = _ler(_arquivo(paths), {})
    entrada = dados.get(game_id, {}) if isinstance(dados, dict) else {}
    if not isinstance(entrada, dict) or entrada.get("console") != console:
        return None
    try:
        watts = int(entrada.get("watts"))
    except (TypeError, ValueError):
        return None
    return watts if 3 <= watts <= 30 else None


def confirmar(paths, game_id: str, console: str, watts: int | None) -> bool:
    """Marca como comprovado somente após estabilidade; devolve se o perfil mudou."""
    if watts is None or not 3 <= int(watts) <= 30:
        return False
    dados = _ler(_arquivo(paths), {})
    if not isinstance(dados, dict):
        dados = {}
    novo = {"console": console, "watts": int(watts)}
    if dados.get(game_id) == novo:
        return False
    dados[game_id] = novo
    _gravar(_arquivo(paths), dados)
    return True
