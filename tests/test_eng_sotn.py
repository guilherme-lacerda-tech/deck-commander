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
    from dc.traducao.sotn_fonte import INDICE
    POCAO = bytes([0x30, 0x4F, INDICE["ç"], INDICE["ã"], 0x4F, 0x00])  # nomes: acentos na fonte 8x8 redesenhada
    assert S.codificar("Poção", 6, "menos20") == POCAO
    assert S.codificar("D'água", 8, "ascii") == bytes.fromhex("44816685406775 61")  # á = código 0x8540
    assert S.codificar("Uma frase grande demais", 10, "ascii") == b"Uma frase "  # corta em palavra inteira
    a = S.achar_ascii("X", FALA)
    m = S.achar_menos20("X", FALA)
    novo = S.aplicar(FALA, [(a[0], "A humanidade precisa"), (m[0], "Poção"), (a[2], "Herança da mãe")])
    assert len(novo) == len(FALA)
    assert novo[2:21] == b"A humanidade       " or novo[2:21].startswith(b"A humanidade")
    assert novo[:2] == FALA[:2] and novo[21:24] == FALA[21:24]  # códigos de controle intactos
    p = m[0].pos
    from dc.traducao.sotn_fonte import INDICE
    assert novo[p:p + 6] == bytes([0x30, 0x4F, INDICE["ç"], INDICE["ã"], 0x4F, 0x00]) and novo[p + 6] == 0xFF


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
    assert linhas == ["Precisamos de", "alguém como você!"]  # o acento fica até a gravação


def test_sem_sobreposicao():
    """Falha real: o mesmo nome achado pelos dois leitores em DRA.BIN @260864 parou a gravação."""
    from dc.traducao import sotn
    a = S.Trecho("X", 10, 6, "Potion", "menos20")
    b = S.Trecho("X", 8, 10, "xxPotion", "ascii")
    c = S.Trecho("X", 30, 5, "Sword", "ascii")
    assert sotn.sem_sobreposicao([a, b, c]) == [a, c]


def test_fonte_8x8_com_acentos():
    """Células de katakana (0x70..0x87) viram as 24 letras acentuadas, no traço das letras do jogo."""
    from dc.traducao import sotn_fonte as F
    d = bytearray(F.BASE + (F.LINHA0 + 16 * 8) * F.LARG)
    F._grava(d, ord("a") - 0x20, [[0] * 8, [0] * 8] + [[0, 0, 6, 6, 6, 0, 0, 0]] * 5 + [[0] * 8])
    n = F.com_acentos(bytes(d))
    assert len(n) == len(d)
    assert F.desenho(n, F.INDICE["á"]).splitlines()[0] == "....#..." and "###" in F.desenho(n, F.INDICE["á"])
    assert len(set(F.INDICE.values())) == 24 and min(F.INDICE.values()) == 0x70


def test_cabe():
    from dc.traducao import sotn
    g = [S.Trecho("X", 0, 10, "a", "ascii"), S.Trecho("X", 20, 10, "b", "ascii")]
    assert sotn.cabe("Uma frase curta", g)
    assert not sotn.cabe("Uma frase comprida demais para duas linhas", g)


def test_patch_da_rotina_de_letras_das_falas():
    """Laço de 1 para 25 letras e tabela nova na área livre (SsUtKeyOn) — só se o disco for o esperado."""
    import struct
    import pytest
    from dc.traducao import sotn_falas_fonte as F
    dra = bytearray(0x70000)
    for end, ins in F.PATCH_DRA.items():
        struct.pack_into("<I", dra, end - F.DRA_BASE, ins)
    struct.pack_into("<H", dra, 0x800AC910 - F.DRA_BASE, 0x9F54)
    exe = bytearray(0x20000)
    exe[F.AREA - F.EXE_BASE:F.AREA - F.EXE_BASE + 4] = bytes.fromhex("c8ffbd27")
    bios = bytes(0x70000)
    d2, e2 = F.aplicar(bytes(dra), bytes(exe), bios)
    assert struct.unpack_from("<I", d2, 0x80106CDC - F.DRA_BASE)[0] == 0x2F220019  # sltiu v0, t9, 25
    o = F.AREA - F.EXE_BASE
    assert struct.unpack_from("<2H", e2, o) == (0x9F54, 0x8540)  # © original + á
    dra[0x66CA0] ^= 1  # outra versão do jogo: recusa sem mexer em nada
    with pytest.raises(ValueError):
        F.aplicar(bytes(dra), bytes(exe), bios)


def test_nomes_ficam():
    from dc.traducao import sotn
    for nome in ("Alucard!?", "Trevor&Grant&Sypha", "SHIGERU FUKUTAKE", "iga load", "100sword set ok"):
        assert sotn._so_nome(nome), nome
    for frase in ("Dark shield", "says he's the lord", "Select the file"):
        assert not sotn._so_nome(frase), frase


def test_glossario_cabe_no_espaco():
    """Cada tradução escrita à mão cabe no espaço do original (nomes: acento 1 byte; falas: 2 bytes)."""
    from dc.traducao import sotn
    for en, pt in sotn.GLOSSARIO.items():
        tipo_menor = min(len(S.codificar(pt, 999, "menos20").rstrip(b"\x00")), len(S.codificar(pt, 999, "ascii").rstrip()))
        assert tipo_menor <= len(en), (en, pt)


def test_menu_com_pontuacao_japonesa():
    """Falha real 11/11/2026: menus do cartão de memória terminam com "." japonês (0x81 0x44) e o leitor descartava
    ou cortava ("No data found" -> "Sem dados n"); o jogo abria todo em inglês."""
    d = (b"\x00\x00No data found\x00\x00\x00on this Memory Card\x81D\x00\x00  Select the slot\x81D\x00 Slot \x82P\x00"
         b"your game\x81D Is that OK\x81H\x00")
    a = S.achar_ascii("SEL", d)
    textos = {t.texto: t for t in a}
    assert "No data found" in textos and "on this Memory Card." in textos and "Select the slot." in textos
    t = textos["on this Memory Card."]
    assert t.sjis and t.tam == len("on this Memory Card") + 2 and d[t.pos + t.tam] == 0
    novo = S.aplicar(d, [(t, "neste cartão.")])
    assert len(novo) == len(d) and novo[t.pos:t.pos + t.tam].rstrip(b" ").endswith(b"\x81D")  # "." volta japonês


def test_frase_nao_sai_cortada(monkeypatch):
    """Falha real 11/11/2026 ("no diálogo tava tudo cortado"): tradução que não cabe vai para o encurtar; antes de
    encurtar, tenta sem acento (cada acento ocupa 2 bytes nas falas)."""
    from dc.traducao import sotn
    g = [S.Trecho("X", 0, 12, "a", "ascii"), S.Trecho("X", 20, 12, "b", "ascii")]
    assert sotn.ajustar("Ele está aqui agora.", g) == "Ele está aqui agora."
    g9 = [S.Trecho("X", 0, 9, "a", "ascii"), S.Trecho("X", 20, 9, "b", "ascii")]
    assert not sotn.cabe("É hora da ação já", g9) and sotn.ajustar("É hora da ação já", g9) == "E hora da acao ja"
    assert sotn.ajustar("Uma frase comprida demais para duas linhas curtas", g) is None
    pedidos = []

    def encurtar(paths, cfg, itens, fits, chain=None):
        pedidos.extend(itens)
        return {iid: "Frase curta." for iid, *_ in itens if fits(iid, "Frase curta.")}
    monkeypatch.setattr(sotn.ia, "shorten", encurtar)
    monkeypatch.setattr(sotn.ia, "translate", lambda *a, **k: (_ for _ in ()).throw(AssertionError("não devia")))
    ids = {"t0": "A very long english sentence here"}
    longa = "Uma frase comprida demais para duas linhas curtas"
    ok = sotn._completar(None, {}, [], {"t0": longa}, {ids["t0"]: [g]}, ids, None, lambda *a: None)
    assert ok == {"t0": "Frase curta."} and pedidos and pedidos[0][1] == longa  # encurtou a tradução que veio
