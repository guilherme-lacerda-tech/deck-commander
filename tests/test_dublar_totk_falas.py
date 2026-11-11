"""Falha real 11/11/2026: a IA devolveu {'f': 'Você vê...'} no lugar da fala e a voz leu as chaves."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "pc"))
import dublar_totk as D  # noqa: E402


def test_fala_que_vem_como_objeto_vira_texto():
    D.ULTIMAS_VOZES[:] = ["m", "m"]
    assert D._fala({"f": "Você vê..."}, 0) == "Você vê..." and D.ULTIMAS_VOZES[0] == "f"
    assert D._fala({"texto": "Oi", "voz": "m"}, 1) == "Oi"
    assert D._fala("Olá", 0) == "Olá"
    with pytest.raises(RuntimeError):
        D._fala("{'f': 'texto'}", 0)  # texto com cara de objeto: a tradução é refeita
