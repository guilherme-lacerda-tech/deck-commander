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
