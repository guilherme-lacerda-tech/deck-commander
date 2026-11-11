"""Voz .bwav (Opus da Nintendo) — docs/specs/bwav.md. Estrutura conferida num arquivo real do Zelda TotK."""
import struct

from dc.traducao import bwav as B


def test_ida_e_volta():
    b = B.Bwav(48000, 2880, 120, [b"\x01\x02", b"\x03", b"\x04\x05\x06"])
    d = B.gravar(b)
    assert d.startswith(b"BWAV\xff\xfe\x01\x00") and d[0x10:0x12] == b"\x02\x00"
    assert d[0x80:0x84] == struct.pack("<I", 0x80000001) and d[0xA0:0xA4] == struct.pack("<I", 0x80000004)
    assert B.ler(d) == b


def _pagina(segmentos: list[bytes], seq: int, continua: bool = False) -> bytes:
    lacing, corpo = b"", b""
    for s in segmentos:
        corpo += s
        n = len(s)
        lacing += b"\xff" * (n // 255) + bytes([n % 255])
    cab = b"OggS" + bytes([0, 1 if continua else 0]) + bytes(8) + b"\x01\x00\x00\x00" + struct.pack("<I", seq) \
        + bytes(4) + bytes([len(lacing)])
    return cab + lacing + corpo


def test_ogg():
    head = b"OpusHead" + bytes([1, 1]) + struct.pack("<H", 312) + bytes(7)
    ogg = _pagina([head], 0) + _pagina([b"OpusTags" + bytes(8)], 1) + _pagina([b"A" * 300, b"BB"], 2)
    pacotes, preskip = B.pacotes_do_ogg(ogg)
    assert preskip == 312 and pacotes == [b"A" * 300, b"BB"]
    assert B.de_ogg(ogg, 960).pacotes == pacotes


def test_ogg_ida_e_volta():
    b = B.Bwav(48000, 2 * 960 - 120, 120, [b"\xfc" + bytes(40), b"\xfc" + bytes(300)])
    ogg = B.para_ogg(b)
    assert ogg.startswith(b"OggS") and B.pacotes_do_ogg(ogg) == (b.pacotes, 120)
