"""M5 — IPS/BPS/UPS com encoders mínimos de teste; detecção por conteúdo; original intacta."""
import zlib

import pytest

from dc import patches

SRC = bytes(range(256)) * 4
TGT = SRC[:100] + b"TRADUZIDO PT-BR" + SRC[115:900] + b"!" * 200


def crc(b):
    return (zlib.crc32(b) & 0xFFFFFFFF).to_bytes(4, "little")


def enc(n):
    out = bytearray()
    while True:
        x = n & 0x7F; n >>= 7
        if n == 0:
            out.append(0x80 | x); return bytes(out)
        out.append(x); n -= 1


def make_bps(src, tgt):
    body = b"BPS1" + enc(len(src)) + enc(len(tgt)) + enc(0)
    body += enc(((len(tgt) - 1) << 2) | 1) + tgt  # TargetRead de tudo
    body += crc(src) + crc(tgt)
    return body + crc(body)


def make_ups(src, tgt):
    body = b"UPS1" + enc(len(src)) + enc(len(tgt))
    a, b = src.ljust(len(tgt), b"\0"), tgt
    i, last = 0, 0
    while i < len(b):
        if a[i] == b[i]:
            i += 1; continue
        body += enc(i - last)
        while i < len(b) and a[i] != b[i]:
            body += bytes([a[i] ^ b[i]]); i += 1
        body += b"\0"; i += 1; last = i
    body += crc(src) + crc(tgt)
    return body + crc(body)


def make_ips(src, tgt):
    body = b"PATCH" + (100).to_bytes(3, "big") + (15).to_bytes(2, "big") + b"TRADUZIDO PT-BR"
    body += (900).to_bytes(3, "big") + (0).to_bytes(2, "big") + (200).to_bytes(2, "big") + b"!"
    return body + b"EOF"


@pytest.mark.parametrize("maker,kind", [(make_ips, "ips"), (make_bps, "bps"), (make_ups, "ups")])
def test_formats_roundtrip(tmp_path, maker, kind):
    src = SRC if kind != "ips" else SRC[:900]
    tgt = TGT if kind != "ips" else SRC[:100] + b"TRADUZIDO PT-BR" + SRC[115:900] + b"!" * 200
    rom = tmp_path / "jogo.sfc"; rom.write_bytes(src)
    pt = tmp_path / "traducao.qualquer-extensao"; pt.write_bytes(maker(src, tgt))
    assert patches.detect(pt.read_bytes()) == kind
    out = patches.apply_file(rom, pt)
    assert out.read_bytes() == tgt and rom.read_bytes() == src  # original intacta


def test_wrong_rom_rejected_without_output(tmp_path):
    rom = tmp_path / "outra.sfc"; rom.write_bytes(b"x" * len(SRC))
    pt = tmp_path / "p.bps"; pt.write_bytes(make_bps(SRC, TGT))
    with pytest.raises(patches.PatchError, match="CRC de origem"):
        patches.apply_file(rom, pt)
    assert not (tmp_path / "outra (patch).sfc").exists()


def test_xdelta_and_exe_detected_and_refused(tmp_path):
    rom = tmp_path / "r.bin"; rom.write_bytes(b"x")
    for data, kind in ((b"\xd6\xc3\xc4\x00rest", "xdelta"), (b"MZ\x90\x00", "exe")):
        p = tmp_path / f"p.{kind}"; p.write_bytes(data)
        with pytest.raises(patches.PatchError, match=kind):
            patches.apply_file(rom, p)


def test_bps_de_disco_grande_aos_pedacos(tmp_path):
    """Revisão retrô 12/11/2026: tradução de disco (Castlevania) não gerava patch para compartilhar."""
    import random

    from dc import patches as P
    rnd = random.Random(7)
    orig = bytes(rnd.getrandbits(8) for _ in range(300_000))
    novo = bytearray(orig)
    novo[10:20] = b"PORTUGUES!"            # mudança no começo
    novo[65_530:65_545] = b"X" * 15         # atravessa a divisa de dois pedaços
    novo[-3:] = b"fim"                      # última parte
    (tmp_path / "o.bin").write_bytes(orig); (tmp_path / "n.bin").write_bytes(bytes(novo))
    bps = P.create_bps_arquivos(tmp_path / "o.bin", tmp_path / "n.bin", tmp_path / "n.bps")
    patch = bps.read_bytes()
    assert len(patch) < 200  # só o que mudou
    assert P.apply_bps(orig, patch) == bytes(novo)
    assert P.create_bps_arquivos(tmp_path / "o.bin", tmp_path / "n.bin", tmp_path / "m.bps", bloco=4096).read_bytes() \
        and P.apply_bps(orig, (tmp_path / "m.bps").read_bytes()) == bytes(novo)
