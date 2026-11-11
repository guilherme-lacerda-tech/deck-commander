import json

from dc.paths import get_paths
from dc.traducao import corrigir_servico as CS


def test_corrigir_troca_so_a_frase(tmp_path):
    paths = get_paths(tmp_path / "dc").ensure()
    cdir = paths.data / "traducao" / "cache"; cdir.mkdir(parents=True)
    c = cdir / "switch-0100ABCD12340000.json"
    c.write_text(json.dumps({"k1": "Você pegou ⟦0⟧ cogumelo da reino!", "k2": "Salvar o jogo?"}, ensure_ascii=False), "utf-8")
    lm = {"switch-jogo": {"title": "Jogo", "console": "switch", "rom": "/r/Jogo [0100ABCD12340000][v0].nsp"}}
    res = CS.corrigir(paths, {}, b"img", "/corrigir Jogo | reino é masculino", lm,
                      ocr_fn=lambda img: "Você pegou cogumelo da reino!",
                      perguntar_fn=lambda s, u: '"Você pegou ⟦0⟧ cogumelo do reino!"')
    assert res["feito"] and res["gid"] == "switch-jogo"
    d = json.loads(c.read_text("utf-8"))
    assert d["k1"] == "Você pegou ⟦0⟧ cogumelo do reino!" and d["k2"] == "Salvar o jogo?"
    ruim = CS.corrigir(paths, {}, b"img", "/corrigir Jogo", lm, ocr_fn=lambda i: "Salvar o jogo?",
                       perguntar_fn=lambda s, u: "Salvar sem código ⟦9⟧")
    assert not ruim["feito"]
