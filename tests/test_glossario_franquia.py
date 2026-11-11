from dc.traducao import glossario_franquia as G


def test_franquia_e_candidatos(tmp_path):
    assert G.franquia("Pokémon Legends Z-A") == "pokemon"
    assert G.franquia("Super Mario Galaxy 2") == "mario"
    assert G.franquia("Jogo Qualquer") is None
    txt = ["Welcome to the Mushroom Kingdom, friend.", "The Mushroom Kingdom is big.", "Go to Mushroom Kingdom now!",
           "You see Bowser there.", "Ask Bowser again.", "Call Bowser later.", "The end.", "Hey you.", "Hey there.",
           "Say Hey loud", "Use <b>Peach</b> {x}"]
    c = G.candidatos(txt, min_vezes=3)
    assert "Mushroom Kingdom" in c and "Bowser" in c and "Hey" not in c


def test_salvar_juntar_e_resposta(tmp_path):
    p = tmp_path / "glossary.json"
    d = G.juntar({}, "mario", {"Mushroom Kingdom": "Reino Cogumelo"})
    d = G.juntar(d, "mario", {"Mushroom Kingdom": "Outro", "Bowser": "Bowser"})
    assert d["mario"]["Mushroom Kingdom"] == "Reino Cogumelo"
    G.salvar(p, d)
    assert G.carregar(p) == d and G.do_jogo(d, None) == {}
    assert G.faltando(d, "mario", ["Bowser", "Peach"]) == ["Peach"]
    r = G.ler_resposta('ok ```json\n{"Peach": "=", "Toad": "Toad", "X": ""}\n```', ["Peach", "Toad"])
    assert r == {"Peach": "Peach", "Toad": "Toad"}
