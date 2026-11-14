"""Perfis de imagem com 1 toque, como no PS5 (pedido 13/11/2026): Beleza, Desempenho, Retrô ou Automático.

- Beleza: resolução alta (BELEZA) e filtros de tela ligados;
- Desempenho: resolução nativa e filtros desligados (o jogo roda o mais liso possível);
- Retrô: resolução nativa com o filtro de TV antiga;
- Automático (padrão): o auto-ajuste de cada jogo decide (dc.autotune).
Vale na próxima vez que o jogo abrir: os emuladores só leem a resolução ao abrir. Escolha manual de um jogo (painel →
Qualidade por jogo) continua valendo no Automático. Partidas jogadas num perfil fixo não ensinam o auto-ajuste.
Rascunho da IA local (qwen2.5-coder:7b), corrigido: no Beleza um console fora da lista virava resolução 0, e um
arquivo ilegível derrubava em vez de voltar ao Automático.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

PERFIS = {"auto": "Automático (o Deck Commander ajusta cada jogo)", "beleza": "Beleza (resolução alta e filtros)",
          "desempenho": "Desempenho (resolução nativa, o mais liso)",
          "retro": "Retrô (resolução nativa com filtro de TV antiga)"}
BELEZA = {"psx": 4, "ps2": 3, "gc": 3, "wii": 3, "psp": 4, "n3ds": 3, "switch": 2}


def _arquivo(paths) -> Path:
    return paths.config / "perfil.json"


def atual(paths) -> str:
    try:
        nome = json.loads(_arquivo(paths).read_text("utf-8")).get("perfil")
    except (OSError, ValueError, AttributeError):
        return "auto"
    return nome if nome in PERFIS else "auto"


def definir(paths, nome: str) -> str:
    if nome not in PERFIS:
        raise ValueError(f"perfil desconhecido: {nome}")
    f = _arquivo(paths)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_name(f"{f.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps({"perfil": nome}), "utf-8")
    os.replace(tmp, f)
    return nome


def nivel(paths, console: str, nivel_do_jogo: int | None, maximo: int) -> int | None:
    """Resolução que o jogo abre neste perfil (None = a do console)."""
    p = atual(paths)
    if p == "auto" or console not in BELEZA:
        return nivel_do_jogo
    if p in ("desempenho", "retro"):
        return 1
    return min(max(nivel_do_jogo or 0, BELEZA[console]), maximo)


def filtros(paths) -> bool | None:
    """Filtro de tela do RetroArch neste perfil; None = deixa a escolha do usuário."""
    return {"beleza": True, "retro": True, "desempenho": False}.get(atual(paths))


def aprende(paths) -> bool:
    """O auto-ajuste só aprende com partidas no Automático."""
    return atual(paths) == "auto"
