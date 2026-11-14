"""Modo repouso (pedido 13/11/2026): na tomada com download/tradução o Deck não dorme até terminar."""
import json

from dc import repouso as R
from dc.paths import get_paths


class _Proc:
    def __init__(self, cmd, **k):
        self.cmd, self.vivo = cmd, True

    def poll(self):
        return None if self.vivo else 0

    def terminate(self):
        self.vivo = False


def test_segura_so_na_tomada_com_trabalho(tmp_path):
    p = get_paths(tmp_path).ensure()
    baixando = [{"state": "downloading"}, {"state": "uploading"}]
    assert R.motivo(p, baixando, ac=False) is None  # na bateria: dorme normal
    assert R.motivo(p, [{"state": "uploading"}], ac=True) is None  # só semeando: dorme
    assert R.motivo(p, baixando, ac=True) == "1 download(s)"
    (p.state / "traducao").mkdir()
    (p.state / "traducao" / "x.json").write_text(json.dumps({"status": "rodando"}))
    assert R.motivo(p, [], ac=True) == "tradução"
    (p.config / "repouso-desligado").write_text("1")
    assert R.motivo(p, baixando, ac=True) is None


def test_trava_liga_e_solta():
    abertos = []
    t = R.Trava(abrir=lambda cmd, **k: abertos.append(_Proc(cmd)) or abertos[-1])
    assert "não dorme" in t.ajustar("1 download(s)")
    assert t.ajustar("1 download(s)") is None and len(abertos) == 1  # já segurando: não abre outra
    assert "--mode=block" in abertos[0].cmd and "sleep:idle" in abertos[0].cmd[1]
    assert "pode dormir" in t.ajustar(None) and not abertos[0].vivo
    assert t.ajustar(None) is None


def test_sem_a_regra_nao_faz_nada(tmp_path):
    assert R.permitido(tmp_path / "nao-existe.rules") is False


def test_permissao_testada_pela_propria_trava(monkeypatch):
    """No Deck a pasta da regra só o administrador lê: olhar o arquivo dava "sem permissão" com ela instalada."""
    R._PERMITIDO.clear()
    assert R.permitido(testar=lambda: True) is True
    assert R.permitido(testar=lambda: False) is True  # guardado por 10 min (não abre um processo a cada 30 s)
    R._PERMITIDO.clear()
    assert R.permitido(testar=lambda: False) is False
    R._PERMITIDO.clear()


def test_botao_apaga_e_acende_so_com_trava(tmp_path):
    p = get_paths(tmp_path).ensure()
    brilho = tmp_path / "brightness"; brilho.write_text("40000")
    assert "nada segurando" in R.botao(p, brilho) and brilho.read_text() == "40000"
    (p.state / "repouso-ativo").write_text("1 download(s)")
    assert "apagada" in R.botao(p, brilho) and brilho.read_text() == "0"
    assert "acesa" in R.botao(p, brilho) and brilho.read_text() == "40000"
    R.botao(p, brilho)  # apaga de novo; o trabalho acaba com a tela apagada:
    dormiu = []
    assert "dormir" in R.ao_terminar(p, dormir=lambda: dormiu.append(1), brilho=brilho)
    assert dormiu == [1] and brilho.read_text() == "40000"  # acorda depois com o brilho de antes
    assert R.ao_terminar(p, dormir=lambda: dormiu.append(1), brilho=brilho) is None


def test_trava_marca_e_desmarca(tmp_path):
    marca = tmp_path / "repouso-ativo"
    t = R.Trava(abrir=lambda cmd, **k: _Proc(cmd), marca=marca)
    t.ajustar("tradução")
    assert marca.read_text() == "tradução"
    t.ajustar(None)
    assert not marca.exists()
