"""Download em RAR dividido (.rar + .r00…) e imagem .mdf/.mds de PS1 (Castlevania SotN veio assim)."""
from pathlib import Path

from dc import content


def _f(p: Path, data: bytes = b"x") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


def test_extra_volumes_skipped_only_with_first_volume(tmp_path):
    files = [_f(tmp_path / n) for n in ("jogo.rar", "jogo.r00", "jogo.r25", "outro.r00",
                                       "x.part1.rar", "x.part2.rar", "x.part10.rar", "y.part2.rar")]
    skip = {f.name for f in files if content._extra_volume(f, files)}
    assert skip == {"jogo.r00", "jogo.r25", "x.part2.rar", "x.part10.rar"}


def _mds(tracks: int) -> bytes:
    b = bytearray(b"MEDIA DESCRIPTOR" + bytes(0x60))
    b[0x50:0x54] = (0x58).to_bytes(4, "little")
    b[0x58 + 10], b[0x58 + 11] = tracks + 3, 3
    return bytes(b) + bytes(32)


def test_mdf_single_track_becomes_bin_cue(tmp_path):
    mdf = _f(tmp_path / "SLES_00524.mdf", bytes(2352 * 4))
    _f(tmp_path / "SLES_00524.mds", _mds(1))
    cue = content.mdf_to_cue(mdf)
    assert cue and cue.name == "SLES_00524.cue"
    assert (tmp_path / "SLES_00524.bin").exists() and not (tmp_path / "SLES_00524.mds").exists()
    assert 'FILE "SLES_00524.bin" BINARY' in cue.read_text() and "MODE2/2352" in cue.read_text()


def test_mdf_multi_track_or_dvd_untouched(tmp_path):
    mdf = _f(tmp_path / "a.mdf", bytes(2352 * 4))
    _f(tmp_path / "a.mds", _mds(5))
    assert content.mdf_to_cue(mdf) is None and mdf.exists()
    odd = _f(tmp_path / "b.mdf", bytes(2048 * 3))
    assert content.mdf_to_cue(odd) is None and odd.exists()
