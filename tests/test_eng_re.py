"""RE Engine: .msg sintético (cifrado e não), solto e dentro de .pak (sem compressão e deflate)."""
import struct
import zlib

import pytest

from dc.traducao import eng_re as r
from dc.traducao import ia
from dc.traducao.motores import MotorError, adapter_for

LANGS = [0, 1, 2, 3]   # japonês, inglês, francês, italiano


def _msg(version=22, extra=""):
    ents = [
        (bytes(range(16)), "MSG_Title", ["タイトル", "Welcome to <COLOR FF0000>Raccoon City</COLOR>", "Bienvenue", "Ciao"]),
        (bytes(16), "MSG_Item", ["アイテム", "Got {0} x <REF Item_01>\r\nPress <ICON PAD_A>" + extra, "Objet", "Oggetto"]),
        (b"\x01" * 16, "MSG_Empty", ["", "", "", ""]),
        (b"\x02" * 16, "MSG_Same", ["同じ", "Welcome to <COLOR FF0000>Raccoon City</COLOR>", "Bienvenue", "Ciao"]),
    ]
    return r.montar_msg(version, LANGS, ents, attrs=[("note", 2), ("num", 0)],
                        valores=[["a", 1], ["b", 2], ["c", 3], ["d", 4]])


def _decifrar_lento(enc):
    out, prev = bytearray(), 0
    for i, c in enumerate(enc):
        out.append(c ^ prev ^ r.KEY[i & 15])
        prev = c
    return bytes(out)


def _cifrar_lento(dec):
    out, prev = bytearray(), 0
    for i, c in enumerate(dec):
        prev = c ^ prev ^ r.KEY[i & 15]
        out.append(prev)
    return bytes(out)


def _traduz(s):
    p, codes = ia.protect(s, r.CODES)
    return ia.restore("PT " + p + " — ação", codes)


def test_cifra_ida_e_volta_e_direcao():
    dados = bytes(range(256)) * 5 + b"\x00\xff" * 33
    enc = r.cifrar(dados)
    assert enc == _cifrar_lento(dados)          # fórmula: enc[i] = dec[i] ^ enc[i-1] ^ KEY[i&15]
    assert r.decifrar(enc) == dados == _decifrar_lento(enc)
    assert r.decifrar(b"") == b"" and r.cifrar(b"") == b""
    # primeiro byte: enc[-1] = 0 -> dec[0] = enc[0] ^ KEY[0]
    assert r.decifrar(b"\x00")[0] == r.KEY[0]


@pytest.mark.parametrize("ver", [12, 14, 15, 17, 20, 22, 23])
def test_msg_leitura_e_regravacao(ver):
    blob = _msg(ver)
    m = r.read_msg(blob)
    assert m.cifrado == (ver > 12)
    assert m.langs == LANGS and m.idx_ingles == 1
    assert m.nomes == ["MSG_Title", "MSG_Item", "MSG_Empty", "MSG_Same"]
    assert m.textos[1][1].startswith("Got {0}")
    if ver > 12:  # o bloco realmente está cifrado (o texto não aparece em claro)
        assert "Raccoon".encode("utf-16-le") not in blob
    novo = r.write_msg(m, {0: "Bem-vindo a <COLOR FF0000>Raccoon City</COLOR>", 1: "Pegou {0}\r\nação"})
    m2 = r.read_msg(novo)
    assert m2.textos[0] == ["タイトル", "Bem-vindo a <COLOR FF0000>Raccoon City</COLOR>", "Bienvenue", "Ciao"]
    assert m2.textos[1][1] == "Pegou {0}\r\nação"
    assert m2.textos[3] == m.textos[3]          # entrada que compartilhava o texto não mudou
    assert novo[:m.data_offset - 0][:40] == blob[:40]
    # o bloco antigo continua byte a byte igual (só cresceu no fim); atributos/nome intactos
    assert r.decifrar(novo[m.data_offset:])[:len(m.pool)] == m.pool if ver > 12 else \
        novo[m.data_offset:][:len(m.pool)] == m.pool


def test_versao_desconhecida_e_lixo():
    blob = bytearray(_msg())
    struct.pack_into("<I", blob, 0, 99)
    with pytest.raises(MotorError, match="versão 99"):
        r.read_msg(bytes(blob))
    with pytest.raises(MotorError, match="GMSG"):
        r.read_msg(b"\0" * 64)


def test_bloco_com_chave_errada_e_recusado():
    blob = bytearray(_msg(22))
    m = r.read_msg(bytes(blob))
    # XOR constante se cancela na cifra encadeada; um padrão que varia estraga o bloco de verdade
    blob[m.data_offset:] = bytes(x ^ ((i * 7 + 1) & 0xFF) for i, x in enumerate(blob[m.data_offset:]))
    with pytest.raises(MotorError):
        r.read_msg(bytes(blob))


def test_murmur3_valores_conhecidos():
    # vetores públicos do MurmurHash3_x86_32
    assert r.murmur3_32(b"", 0) == 0
    assert r.murmur3_32(b"", 1) == 0x514E28B7
    assert r.murmur3_32(b"", 0xFFFFFFFF) == 0x81F16F39
    assert r.murmur3_32(b"\0\0\0\0", 0) == 0x2362F9DE
    assert r.murmur3_32(b"Hello, world!", 1234) == 0xFAF6CDB3
    assert r.murmur3_32(b"aaa", 0x9747B28C) == 0x283E0130


def test_detect():
    assert r.detect(["/natives/NSW/message/ui.msg.17"])
    assert r.detect(["/re_chunk_000.pak"])
    assert not r.detect(["/data/text.msg", "/x.pak"])
    assert adapter_for(["/re_chunk_000.pak", "/re_chunk_000.pak.patch_001.pak"]) is r


def test_msg_solto_roundtrip():
    blob = _msg(17)
    files = {"/natives/NSW/message/ui.msg.17": (0, len(blob))}
    col = r.collect(files, lambda p: blob)
    textos = {t.id: t.text for t in col.textos}
    assert len(textos) == 3   # entrada vazia fica de fora
    novos = {i: _traduz(s) for i, s in textos.items()}
    out = col.rebuild(novos)
    assert list(out) == ["/natives/NSW/message/ui.msg.17"]
    back = r.collect(files, lambda p: out[p])
    assert {t.id: t.text for t in back.textos} == novos
    for i, s in textos.items():
        assert r.CODES.findall(novos[i]) == r.CODES.findall(s)


def _pak(entradas, major=4):
    """entradas: [(caminho, bytes, compressão)] -> pak KPKA com hashes dos caminhos."""
    tam = 48 if major == 4 else 24
    p = 16 + tam * len(entradas)
    idx, corpo = b"", b""
    for caminho, data, comp in entradas:
        lo, up = r.hash_caminho(caminho)
        gravado = data
        if comp == 1:
            c = zlib.compressobj(9, zlib.DEFLATED, -15)
            gravado = c.compress(data) + c.flush()
        elif comp == 2:
            gravado = b"\x28\xb5\x2f\xfd" + data[:10]
        off = p + len(corpo)
        if major == 4:
            idx += struct.pack("<IIQQQQQ", lo, up, off, len(gravado), len(data), comp, 0)
        else:
            idx += struct.pack("<QQII", off, len(data), lo, up)
        corpo += gravado
    return b"KPKA" + struct.pack("<BBHII", major, 0, 0, len(entradas), 0) + idx + corpo


def test_pak_deflate_patch_novo():
    msg_a, msg_b = _msg(22), _msg(22, extra=" more")
    base = _pak([("natives/NSW/message/a.msg.22", msg_a, 1), ("natives/NSW/tex/x.tex", b"TEX\0" * 50, 0),
                 ("natives/NSW/message/b.msg.22", b"old", 0)])
    patch1 = _pak([("natives/NSW/message/b.msg.22", msg_b, 0)])       # patch vence o base
    blobs = {"/re_chunk_000.pak": base, "/re_chunk_000.pak.patch_001.pak": patch1}
    files = {k: (0, len(v)) for k, v in blobs.items()}
    col = r.collect(files, blobs.__getitem__)
    textos = {t.id: t.text for t in col.textos}
    assert any(s.endswith(" more") for s in textos.values())
    assert sum(1 for i in textos if i.startswith("/re_chunk_000.pak.patch_001.pak#")) == 3
    novos = {i: _traduz(s) for i, s in textos.items()}
    out = col.rebuild(novos)
    assert list(out) == ["/re_chunk_000.pak.patch_002.pak"]
    novo = out["/re_chunk_000.pak.patch_002.pak"]
    pk = r.read_pak(novo)
    assert len(pk.entries) == 2 and all(e.compressao == 0 for e in pk.entries)
    hashes = {(e.hash_lower, e.hash_upper) for e in pk.entries}
    assert hashes == {r.hash_caminho("natives/NSW/message/a.msg.22"), r.hash_caminho("natives/NSW/message/b.msg.22")}
    # com o patch novo junto, a releitura enxerga as frases traduzidas
    blobs2 = dict(blobs, **out)
    back = r.collect({k: (0, len(v)) for k, v in blobs2.items()}, blobs2.__getitem__)
    assert sorted(t.text for t in back.textos) == sorted(novos.values())


def test_pak_v2_sem_compressao():
    base = _pak([("natives/x64/message/a.msg.14", _msg(14), 0)], major=2)
    col = r.collect({"/re_chunk_000.pak": (0, len(base))}, lambda p: base)
    out = col.rebuild({t.id: _traduz(t.text) for t in col.textos})
    assert r.read_pak(out["/re_chunk_000.pak.patch_001.pak"]).major == 2


def test_pak_so_zstd():
    base = _pak([("natives/NSW/message/a.msg.22", _msg(22), 2)])
    with pytest.raises(MotorError, match="zstd"):
        r.collect({"/re_chunk_000.pak": (0, len(base))}, lambda p: base)
    e = r.read_pak(base).entries[0]
    with pytest.raises(MotorError, match="zstd"):
        r.read_entry(base, e)


def test_pak_indice_cifrado():
    base = bytearray(_pak([("a", b"x", 0)]))
    struct.pack_into("<H", base, 6, 8)
    with pytest.raises(MotorError, match="criptografado"):
        r.read_pak(bytes(base))
