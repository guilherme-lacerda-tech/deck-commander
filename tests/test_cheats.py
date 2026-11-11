"""Cheats do RetroArch por jogo — docs/specs/cheats.md."""
from dc import cheats as C

T = ('cheats = 2\n\ncheat0_desc = "Infinite Lives"\ncheat0_code = "7E0DBE:09"\ncheat0_enable = false\n'
     'cheat0_handler = 1\n\ncheat1_desc = "Max Money"\ncheat1_code = "AAAA-BBBB"\ncheat1_enable = false\n')


def test_ler_e_escrever():
    c = C.ler_cht(T)
    assert [x["i"] for x in c] == [0, 1]
    assert c[0]["desc"] == "Infinite Lives" and c[0]["code"] == "7E0DBE:09" and c[0]["extra"] == {"handler": "1"}
    assert c[1]["enable"] is False
    volta = C.ler_cht(C.escrever_cht(C.com_ativos(c, {1})))
    assert volta[1]["enable"] is True and volta[0]["enable"] is False and volta[0]["extra"] == {"handler": "1"}
    assert C.escrever_cht(c).startswith("cheats = 2\n")


def test_achar_e_traduzir():
    nomes = ["Super Mario World (Europe).cht", "Super Mario World (USA).cht", "Super Mario World 2 (USA).cht"]
    assert C.achar_cht(nomes, "Super Mario World (USA).sfc") == "Super Mario World (USA).cht"
    assert C.achar_cht(nomes, "Zelda") is None
    assert C.normalizar("Super Mario World (USA) [!].sfc") == "super mario world"
    assert C.normalizar("Pokémon Fire Red & Blue") == "pokemon fire red and blue"
    assert C.traduzir_desc("Infinite Lives P1") == "Vidas infinitas P1"
    assert C.traduzir_desc("infinite ammo") == "Munição infinita"
