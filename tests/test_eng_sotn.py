"""Castlevania SOTN (PS1): texto achado nos dois formatos do jogo e regravado sem mudar nenhum tamanho."""
import struct

from dc.traducao import eng_sotn as S
from dc.traducao import psx_disco as P

FALA = (b"\x11\x10Mankind ill needs a\x01\x03\x04savior such as you!\x03"
        + bytes([0x30, 0x4F, 0x54, 0x49, 0x4F, 0x4E, 0xFF])          # "Potion" (menos 0x20) + FF
        + b"Mother\x81\x66s family heirloom\x00"
        + b"\x00\x00SD_ZKTE2.VH\x00\x80\x81\x00\x12\x34ABCD\x00")       # lixo/nome de arquivo: não é texto


def test_achar():
    a = S.achar_ascii("X", FALA)
    assert [t.texto for t in a] == ["Mankind ill needs a", "savior such as you!", "Mother's family heirloom"]
    assert a[0].pos == 2 and a[0].tam == 19 and a[2].tam == len("Mother's family heirloom") + 1  # ' ocupa 2 bytes
    m = S.achar_menos20("X", FALA)
    assert [(t.texto, t.tam) for t in m] == [("Potion", 6)]


def test_codificar_e_aplicar():
    assert S.codificar("Poção", 6, "menos20") == bytes(c - 0x20 for c in b"Pocao ")
    assert S.codificar("D'água", 7, "ascii") == b"D\x81\x66agua"
    assert S.codificar("Uma frase grande demais", 10, "ascii") == b"Uma frase "  # corta em palavra inteira
    a = S.achar_ascii("X", FALA)
    m = S.achar_menos20("X", FALA)
    novo = S.aplicar(FALA, [(a[0], "A humanidade precisa"), (m[0], "Poção"), (a[2], "Herança da mãe")])
    assert len(novo) == len(FALA)
    assert novo[2:21] == b"A humanidade       " or novo[2:21].startswith(b"A humanidade")
    assert novo[:2] == FALA[:2] and novo[21:24] == FALA[21:24]  # códigos de controle intactos
    p = m[0].pos
    assert novo[p:p + 6] == bytes(c - 0x20 for c in b"Pocao ") and novo[p + 6] == 0xFF  # o fim (0xFF) fica


def test_filtro_do_disco_real():
    """Amostras reais do disco: lixo binário e coisas internas não entram; texto de verdade entra."""
    for lixo in ("CEqX4XZ", "oyxyxyxyxyxyxyv", "hijklmn", "IHdaExW", "col step %x", "alucard"):
        assert not S.parece_texto(lixo), lixo
    for bom in ("Iron cuirass", "Dracula's castle beckons for you...", "Whatever we do,", "It's all right!"):
        assert S.parece_texto(bom), bom


def _bin(arquivo: bytes) -> bytes:
    """CD falso: setor 16 = descritor, 18 = raiz com A.BIN (setor 20, 2 setores)."""
    setores = [bytearray(2352) for _ in range(22)]

    def dados(n, b):
        setores[n][24:24 + len(b)] = b
    raiz = bytearray(34)
    raiz[0] = 34
    struct.pack_into("<I", raiz, 2, 18)
    struct.pack_into("<I", raiz, 10, 2048)
    pvd = bytearray(2048)
    pvd[156:190] = raiz
    dados(16, bytes(pvd))
    nome = b"A.BIN;1"
    reg = bytearray(33 + len(nome) + 1)
    reg[0] = len(reg)
    struct.pack_into("<I", reg, 2, 20)
    struct.pack_into("<I", reg, 10, len(arquivo))
    reg[32] = len(nome)
    reg[33:33 + len(nome)] = nome
    dados(18, bytes(reg))
    dados(20, arquivo[:2048])
    dados(21, arquivo[2048:])
    for s in setores:
        s[:24] = b"\x00\xff" * 12
    return b"".join(bytes(s) for s in setores)


def test_disco(tmp_path):
    arq = bytes(range(256)) * 11 + bytes(184)  # 3000 bytes
    p = tmp_path / "jogo.bin"
    p.write_bytes(_bin(arq))
    d = P.Disco(p)
    assert d.arquivos() == {"A.BIN": (20, 3000)}
    assert d.ler("A.BIN") == arq
    novo = bytes(3000)
    d.gravar_copia(tmp_path / "pt.bin", {"A.BIN": novo})
    assert P.Disco(tmp_path / "pt.bin").ler("A.BIN") == novo
    assert (tmp_path / "pt.bin").read_bytes()[20 * 2352:20 * 2352 + 24] == b"\x00\xff" * 12
    assert P.Disco(p).ler("A.BIN") == arq  # original intacto
    import pytest
    with pytest.raises(ValueError):
        d.gravar_copia(tmp_path / "x.bin", {"A.BIN": bytes(10)})
    (tmp_path / "jogo.cue").write_text('FILE "jogo.bin" BINARY\n  TRACK 01 MODE2/2352\n')
    P.gravar_cue(tmp_path / "jogo.cue", tmp_path / "pt.cue", "pt.bin")
    assert 'FILE "pt.bin" BINARY' in (tmp_path / "pt.cue").read_text() and "MODE2/2352" in (tmp_path / "pt.cue").read_text()


def test_fala_inteira_vai_junta_e_volta_nas_linhas():
    from dc.traducao import sotn
    a = S.achar_ascii("X", FALA)
    grupos = sotn.agrupar(a, {"X": FALA})
    assert [len(g) for g in grupos] == [2, 1]  # as 2 linhas da fala juntas; a descrição sozinha
    linhas = sotn.distribuir("Precisamos de alguém como você!", grupos[0])
    assert len(linhas) == 2 and all(len(S.codificar(l, 999, "ascii").rstrip()) <= t.tam for l, t in zip(linhas, grupos[0]))
    assert linhas == ["Precisamos de", "alguem como voce!"]


def test_sem_sobreposicao():
    """Falha real: o mesmo nome achado pelos dois leitores em DRA.BIN @260864 parou a gravação."""
    from dc.traducao import sotn
    a = S.Trecho("X", 10, 6, "Potion", "menos20")
    b = S.Trecho("X", 8, 10, "xxPotion", "ascii")
    c = S.Trecho("X", 30, 5, "Sword", "ascii")
    assert sotn.sem_sobreposicao([a, b, c]) == [a, c]
