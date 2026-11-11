"""Falha real 11/11/2026: a tela de arquivos do Castlevania (File select/copy/delete, Name entry/change) é desenho,
o tradutor de texto não via e o jogo "abria todo em inglês". Os botões são remontados com o alfabeto gótico do jogo."""
from dc.traducao import sotn_imagens as I


def _folha_falsa() -> bytearray:
    d = bytearray(I.LARG * 3072)
    for folha in I.FOLHAS:
        for k, c in enumerate(I.ALFABETO):  # cada letra: um bloco 10x12 da cor 5 na célula dela
            for y in range(2, 14):
                for x in range(3, 13):
                    I.put(d, (k % 8) * 16 + x, folha + I.LINHA_ALFABETO + (k // 8) * 16 + y, 5)
        for y in range(32):  # "File copy" antigo: cor 9 em todo o botão
            for x in range(128):
                I.put(d, x, folha + y, 9)
    return d


def test_px_e_put():
    d = bytearray(I.LARG * 2)
    I.put(d, 0, 0, 0xA)
    I.put(d, 1, 0, 0x3)
    assert d[0] == 0x3A and I.px(d, 0, 0) == 0xA and I.px(d, 1, 0) == 3
    I.put(d, 0, 0, 0)
    assert d[0] == 0x30


def test_botoes_em_portugues():
    d = _folha_falsa()
    n = I.botoes_em_portugues(bytes(d))
    assert len(n) == len(d)
    for folha in I.FOLHAS:  # as duas páginas de vídeo
        cores = {I.px(n, x, folha + y) for y in range(32) for x in range(128)}
        assert 9 not in cores and 5 in cores  # o desenho antigo saiu; as letras do jogo entraram
        colunas = [x for x in range(128) if any(I.px(n, x, folha + y) for y in range(32))]
        assert 128 - colunas[-1] - 1 - colunas[0] in (0, 1)  # centrado
        assert I.glifo(n, 0, folha + I.LINHA_ALFABETO) == I.glifo(d, 0, folha + I.LINHA_ALFABETO)  # alfabeto intacto


def test_palavra_larga_demais_recusa():
    import pytest
    d = _folha_falsa()
    with pytest.raises(ValueError):
        I.escrever(d, 0, 0, 40, 32, [I.letra(d, 256, c) for c in "ESCOLHER"])
