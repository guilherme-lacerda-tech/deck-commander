"""Ler/gravar JSON do Deck Commander (antes copiado igual em 6 módulos — revisão de lançamento 12/11/2026)."""
from __future__ import annotations

import json
import os
from pathlib import Path


def ler(p: Path, padrao):
    """Conteúdo do arquivo, ou `padrao` se ele não existe ou está ilegível."""
    try:
        return json.loads(Path(p).read_text("utf-8"))
    except (OSError, ValueError):
        return padrao


def gravar(p: Path, dados) -> None:
    """Grava de uma vez (arquivo temporário + troca): quem lê nunca vê o arquivo pela metade."""
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=1), "utf-8")
    os.replace(tmp, p)
