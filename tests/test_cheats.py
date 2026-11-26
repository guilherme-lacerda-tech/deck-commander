"""Cheats do RetroArch por jogo — docs/specs/cheats.md."""
import pytest

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


def test_campos_intercalados_e_extras_com_aspas_sao_preservados():
    texto = ('cheats = 2\ncheat0_desc = "Vida"\ncheat1_desc = "Tempo"\n'
             'cheat0_code = "ABCD"\ncheat0_memory_search_size = "8 bit"\n')
    lista = C.ler_cht(texto)
    assert len(lista) == 2 and lista[0]["code"] == "ABCD"
    assert lista[0]["extra"]["memory_search_size"] == '"8 bit"'
    assert C.ler_cht(C.escrever_cht(lista)) == lista


def test_nao_confunde_sequencia_com_jogo_original():
    assert C.achar_cht(["Super Mario World 2 (USA).cht"], "Super Mario World.sfc") is None


@pytest.mark.parametrize("texto", ["cheats = 999999999", "cheats = -1", "cheat10000_desc = x"])
def test_recusa_quantidades_e_indices_excessivos(texto):
    with pytest.raises(ValueError):
        C.ler_cht(texto)
