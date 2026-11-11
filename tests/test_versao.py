"""/voltar: troca a versão instalada pela anterior guardada pelo implantar.py."""
from types import SimpleNamespace

from dc import versao


def test_sem_anterior(tmp_path):
    (tmp_path / "deck-commander").mkdir()
    txt, botoes = versao.comando([], home=tmp_path)
    assert "Ainda não há versão anterior" in txt and botoes == []
    assert "Não há versão anterior" in versao.voltar(tmp_path, run=lambda *a, **k: 1 / 0)


def test_mostra_e_troca_fora_do_servico(tmp_path):
    for nome, v in (("deck-commander", "bbb 11/11 10:00"), ("deck-commander.anterior", "aaa 10/11 09:00")):
        (tmp_path / nome).mkdir()
        (tmp_path / nome / "VERSAO.txt").write_text(v + "\n")
    txt, botoes = versao.comando([], home=tmp_path)
    assert "bbb" in txt and "aaa" in txt and botoes == [("Voltar versão", "/voltar sim")]
    chamadas = []
    run = lambda args, **k: chamadas.append(args) or SimpleNamespace(returncode=0, stdout="", stderr="")
    msg, _ = versao.comando(["sim"], home=tmp_path, run=run)
    assert "aaa" in msg and "/voltar de novo desfaz" in msg
    cmd = chamadas[0]
    assert cmd[:3] == ["systemd-run", "--user", "--collect"]  # fora do cgroup do bot: reiniciar o bot não mata a troca
    script = cmd[-1]
    assert script.index("mv '" + str(tmp_path / "deck-commander") + "'") < script.index("restart deck-commander-bot")
