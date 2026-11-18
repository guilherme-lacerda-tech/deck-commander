"""O teste E2E real não pode deixar resíduos quando alguém está jogando."""
import importlib.util
from pathlib import Path

import pytest


def test_e2e_recusa_antes_de_criar_artefatos_com_jogo_aberto(monkeypatch):
    arq = Path(__file__).resolve().parents[1] / "tools/e2e_local.py"
    spec = importlib.util.spec_from_file_location("dc_e2e_local_test", arq)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod.ops, "game_running", lambda: True)
    monkeypatch.setattr(mod, "Q", lambda: pytest.fail("não pode abrir qBittorrent"))
    with pytest.raises(SystemExit, match="nenhum artefato"):
        mod.main()
