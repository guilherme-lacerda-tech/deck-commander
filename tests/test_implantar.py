"""tools/implantar.py — falha real 27/11/2026: teste rodado no Deck sem isolamento escreveu no HOME real e quebrou o
launcher do DMC3. O implantador ainda rodava pytest direto (achado na auditoria de 28/11/2026)."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("implantar", Path(__file__).resolve().parents[1] / "tools/implantar.py")
implantar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(implantar)


def test_testes_no_deck_so_pelo_executor_isolado():
    r = implantar.REMOTO
    assert "test_runner.run(" in r
    assert "-m pytest" not in r and "pytest.main" not in r


def test_troca_a_pasta_inteira_e_refaz_launcher_depois():
    r = implantar.REMOTO
    assert 'mv "$HOME/deck-commander" "$HOME/deck-commander.anterior"' in r
    assert "cp -a /tmp/dc-new/." not in r  # cópia por cima deixava arquivo removido no lugar
    assert r.index("test_runner.run(") < r.index('mv "$HOME/deck-commander"') < r.index("dc.atualizar depois")


def test_nao_interrompe_partida():
    assert "game_running()" in implantar.REMOTO and "COM_JOGO" in implantar.REMOTO
