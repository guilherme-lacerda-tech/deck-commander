import json

from dc.traducao import corrigir as C


def test_parecidas_marcadores_aplicar(tmp_path):
    frases = {"k1": "Você encontrou ⟦0⟧ cogumelo do reino!", "k2": "Salvar o jogo agora?", "k3": "Ok"}
    r = C.parecidas("Voce encontrou\n cogumelo do reino", frases)
    assert r and r[0][0] == "k1" and r[0][1] >= 0.55
    assert C.marcadores_ok("a ⟦0⟧ b ⟦1⟧", "x ⟦1⟧ y ⟦0⟧") and not C.marcadores_ok("a ⟦0⟧", "a")
    assert C.limpar_resposta('Tradução: "Olá ⟦0⟧"') == "Olá ⟦0⟧"
    f = tmp_path / "c.json"; f.write_text(json.dumps(frases, ensure_ascii=False), "utf-8")
    assert C.aplicar([f, tmp_path / "outro.json"], "k1", "Novo ⟦0⟧") == [f]
    assert json.loads(f.read_text("utf-8"))["k1"] == "Novo ⟦0⟧" and (tmp_path / "c.json.antes-correcao").exists()
    corpo = C.pedido_ocr(b"\x89PNG", "qwen2.5vl:7b")
    assert corpo["model"] == "qwen2.5vl:7b" and corpo["images"] and corpo["stream"] is False
