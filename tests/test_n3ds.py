"""Leitor de jogo de 3DS descriptografado (.3ds/.cci = NCSD, .cxi = NCCH) e do RomFS (dc/traducao/n3ds.py)."""
import struct

import pytest

from dc.traducao import n3ds

NONE = 0xFFFFFFFF


def _name(s: str) -> bytes:
    b = s.encode("utf-16-le")
    return b + b"\0" * (-len(b) % 4)


def _level3(files: dict[str, bytes]) -> bytes:
    """RomFS nível 3 com a raiz + uma pasta 'msg' (arquivos com '/' vão para ela)."""
    root_files = {k: v for k, v in files.items() if "/" not in k}
    sub_files = {k.split("/", 1)[1]: v for k, v in files.items() if "/" in k}
    # metadados de pastas: raiz (offset 0) e 'msg'
    root_len = 0x18
    msg_off = root_len
    data = b""
    fmeta = b""
    entries = []  # (parent, name, data)
    for n, d in root_files.items():
        entries.append((0, n, d))
    for n, d in sub_files.items():
        entries.append((msg_off, n, d))
    offs = []
    for parent, n, d in entries:
        offs.append(len(fmeta))
        fmeta += struct.pack("<IIQQII", parent, 0, 0, 0, NONE, 0) + _name(n)
    # agora preenche irmãos e dados
    fmeta = bytearray(fmeta)
    first_root = first_msg = NONE
    prev = {0: None, msg_off: None}
    for (parent, n, d), off in zip(entries, offs):
        pad = -len(data) % 16
        data += b"\0" * pad
        struct.pack_into("<IIQQII", fmeta, off, parent, NONE, len(data), len(d), NONE, len(n) * 2)
        data += d
        if prev[parent] is None:
            if parent == 0:
                first_root = off
            else:
                first_msg = off
        else:
            struct.pack_into("<I", fmeta, prev[parent] + 4, off)
        prev[parent] = off
    dmeta = struct.pack("<IIIIII", 0, NONE, msg_off, first_root, NONE, 0)
    dmeta += struct.pack("<IIIIII", 0, NONE, NONE, first_msg, NONE, 6) + _name("msg")
    hdr_len = 0x28
    dh_off = hdr_len
    dm_off = dh_off + 4
    fh_off = dm_off + len(dmeta)
    fm_off = fh_off + 4
    fd_off = fm_off + len(fmeta)
    fd_off += -fd_off % 16
    hdr = struct.pack("<10I", hdr_len, dh_off, 4, dm_off, len(dmeta), fh_off, 4, fm_off, len(fmeta), fd_off)
    body = hdr + struct.pack("<I", NONE) + dmeta + struct.pack("<I", NONE) + bytes(fmeta)
    body += b"\0" * (fd_off - len(body))
    return body + data


def _romfs(files) -> bytes:
    lvl3 = _level3(files)
    master = 0x20
    ivfc = b"IVFC" + struct.pack("<II", 0x10000, master)
    for size in (0x20, 0x20, len(lvl3)):
        ivfc += struct.pack("<QQII", 0, size, 12, 0)
    ivfc += struct.pack("<I", 0x5C)
    ivfc += b"\0" * (0x60 - len(ivfc)) + b"\0" * master
    ivfc += b"\0" * (0x1000 - len(ivfc))  # nível 3 alinhado a 1 << 12
    return ivfc + lvl3


def _ncch(files, title_id=0x0004000000055D00) -> bytes:
    rom = _romfs(files)
    rom += b"\0" * (-len(rom) % 0x200)
    h = bytearray(0x200)
    h[0x100:0x104] = b"NCCH"
    struct.pack_into("<Q", h, 0x118, title_id)
    h[0x188 + 7] = 0x04  # NoCrypto: dump descriptografado
    struct.pack_into("<II", h, 0x1B0, 1, len(rom) // 0x200)
    return bytes(h) + rom


def _ncsd(ncch: bytes) -> bytes:
    h = bytearray(0x4000)
    h[0x100:0x104] = b"NCSD"
    struct.pack_into("<II", h, 0x120, len(h) // 0x200, len(ncch) // 0x200)
    return bytes(h) + ncch


FILES = {"credits.txt": b"oi", "msg/Common.msbt": b"MsgStdBn" + b"\x00" * 24, "msg/Talk.msbt": b"MsgStdBnXYZ"}


def test_read_cxi(tmp_path):
    p = tmp_path / "jogo.cxi"
    p.write_bytes(_ncch(FILES))
    g = n3ds.open_game(p)
    assert g.title_id == "0004000000055D00"
    assert sorted(g.list_files()) == ["credits.txt", "msg/Common.msbt", "msg/Talk.msbt"]
    assert g.read("msg/Talk.msbt") == b"MsgStdBnXYZ"


def test_read_cci_and_extract_filtered(tmp_path):
    p = tmp_path / "jogo.3ds"
    p.write_bytes(_ncsd(_ncch(FILES)))
    g = n3ds.open_game(p)
    out = tmp_path / "romfs"
    n = g.extract(out, lambda rel: rel.endswith(".msbt"))
    assert n == 2
    assert (out / "msg/Common.msbt").read_bytes().startswith(b"MsgStdBn")
    assert not (out / "credits.txt").exists()


def test_encrypted_dump_refused(tmp_path):
    raw = bytearray(_ncch(FILES))
    raw[0x188 + 7] = 0  # sem NoCrypto
    p = tmp_path / "cripto.cxi"
    p.write_bytes(bytes(raw))
    with pytest.raises(n3ds.Encrypted):
        n3ds.open_game(p)


def test_not_a_3ds_file(tmp_path):
    p = tmp_path / "x.3ds"
    p.write_bytes(b"\0" * 0x400)
    with pytest.raises(n3ds.FormatError):
        n3ds.open_game(p)


def test_mod_dir_azahar(tmp_path):
    d = n3ds.mod_dir("0004000000055d00", home=tmp_path)
    assert d == tmp_path / ".var/app/org.azahar_emu.Azahar/data/azahar-emu/load/mods/0004000000055D00"


def test_translate_3ds_end_to_end(tmp_path, monkeypatch):
    """Jogo de 3DS com MSBT (little-endian) -> mod no Azahar; o jogo original não muda."""
    from test_traducao import FakeAI, make_msbt

    from dc.paths import get_paths
    from dc.traducao import ia, run
    paths = get_paths(tmp_path / "dc").ensure()
    rom = tmp_path / "jogo.3ds"
    rom.write_bytes(_ncsd(_ncch({"msg/Talk.msbt": make_msbt([["Hello"], ["Bye"]], ["a", "b"]), "x.bin": b"z"})))
    before = rom.read_bytes()
    monkeypatch.setattr(n3ds, "mod_dir", lambda tid, home=None: tmp_path / "azahar/mods" / tid)
    cfg = ia.load_cfg(paths)
    chain = [ia.Provider("ollama", {**cfg["providers"]["ollama"], "modelo": "qwen"}, "", FakeAI())]
    from dc.traducao import switch
    real = switch.translate_game
    monkeypatch.setattr(switch, "translate_game", lambda *a, **k: real(*a, **{**k, "chain": chain}))
    monkeypatch.setattr(run, "_refresh_tabs", lambda p: None)
    job = {"args": {}}
    result, text, ok = run._translate_n3ds(paths, job, {"title": "Jogo"}, rom, cfg, lambda d, t: None, lambda: False)
    assert ok and result["translated"] == 2, text
    m = nx_read(tmp_path / "azahar/mods/0004000000055D00/romfs/msg/Talk.msbt")
    assert m.texts()[0][0] == "PT Hello"
    assert rom.read_bytes() == before


def nx_read(p):
    from dc.traducao import nx
    return nx.read_msbt(p.read_bytes())
