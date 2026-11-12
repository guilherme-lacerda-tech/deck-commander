"""Jogos Unreal Engine (ex.: Final Fantasy Resonance no Switch): .locres dentro do .pak, mod "_P" por cima."""
import struct

import pytest
from test_traducao import FakeAI

from dc.paths import get_paths
from dc.traducao import ia, unreal


def _loc():
    return unreal.Locres(3, [
        ("ST_Menu", "Start", 111, "New Game"),
        ("ST_Menu", "Load", 222, "Load <text style=\"bold\">{Num}</> saves\r\nnow"),
        ("ST_BtlAI", "N1", 333, "10"),
        ("ST_BtlAI", "Dup", 444, "New Game"),
        ("", "Uni", 555, "Ação ✓ 魔法"),
    ])


def test_locres_roundtrip_keeps_every_entry():
    loc = _loc()
    back = unreal.read_locres(unreal.write_locres(loc))
    assert back.entries == loc.entries


def test_str_hash_is_ue_strcrc32():
    # FCrc::StrCrc32("") = 0 ; valor de "A" conferido com a fórmula (CRC32 de b"A\0\0\0")
    import zlib
    assert unreal._str_hash("") == 0
    assert unreal._str_hash("A") == zlib.crc32(b"A\0\0\0")


def test_pak_roundtrip_uncompressed():
    files = {"FFRS/Content/Localization/Game/en/Game.locres": unreal.write_locres(_loc()),
             "FFRS/Content/Other/x.txt": b"abc" * 1000}
    blob = unreal.write_pak(files)
    pak = unreal.read_pak(lambda a, n: blob[a:a + n], len(blob))
    assert pak.version == 11 and pak.mount == "../../../"
    assert set(pak.entries) == set(files)
    for p, b in files.items():
        assert unreal.read_entry(lambda a, n: blob[a:a + n], pak.entries[p]) == b
    assert unreal.game_locres(pak) == ["FFRS/Content/Localization/Game/en/Game.locres"]


def test_encrypted_index_is_refused():
    blob = bytearray(unreal.write_pak({"a/b.txt": b"x"}))
    i = blob.rfind(struct.pack("<I", unreal.PAK_MAGIC))
    blob[i - 1] = 1
    with pytest.raises(unreal.UnrealError, match="AES"):
        unreal.read_pak(lambda a, n: bytes(blob[a:a + n]), len(blob))


def test_compressed_entry_without_decompressor_says_so():
    ent = unreal.PakEntry("x.locres", 0, 10, 20, "Oodle", [(0, 10)], 65536, False)
    with pytest.raises(unreal.UnrealError, match="Oodle"):
        unreal.read_entry(lambda a, n: b"\0" * n, ent)


def test_translate_locres_keeps_codes_and_skips_numbers(tmp_path):
    paths = get_paths(tmp_path / "dc").ensure()
    cfg = ia.load_cfg(paths)
    chain = [ia.Provider("ollama", {**cfg["providers"]["ollama"], "modelo": "qwen"}, "", FakeAI())]
    new, res, changed = unreal.translate_locres(paths, cfg, unreal.write_locres(_loc()), "t", "Jogo", chain=chain)
    out = {(ns, k): s for ns, k, _h, s in unreal.read_locres(new).entries}
    assert out[("ST_Menu", "Start")] == out[("ST_BtlAI", "Dup")] == "PT New Game"
    load = out[("ST_Menu", "Load")]
    assert '<text style="bold">' in load and "{Num}" in load and "</>" in load and "\r\n" in load
    assert out[("ST_BtlAI", "N1")] == "10"  # só número: não vai para a IA
    assert changed == 4


def test_build_mod_writes_pak_under_mods_folder(tmp_path):
    files = {"FFRS/Content/Localization/Game/en/Game.locres": unreal.write_locres(_loc())}
    out = unreal.build_mod(files, tmp_path / "romfs", "FFRS")
    assert out == tmp_path / "romfs/FFRS/Content/Paks/~mods" / unreal.MOD_PAK
    blob = out.read_bytes()
    pak = unreal.read_pak(lambda a, n: blob[a:a + n], len(blob))
    assert list(pak.entries) == list(files)


def test_cached_plain(tmp_path):
    p = unreal.cache_dir(tmp_path, "0100abc") / "descompactado/FFRS/x.locres"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"ok")
    assert unreal.cached_plain(tmp_path, "0100ABC", "FFRS/x.locres") == b"ok"
    assert unreal.cached_plain(tmp_path, "0100ABC", "nada") is None
