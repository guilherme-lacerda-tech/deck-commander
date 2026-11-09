"""Download em RAR dividido (.rar + .r00…) e imagem .mdf/.mds de PS1 (Castlevania SotN PAL veio assim)."""
import shutil
from pathlib import Path

from dc import content

FIX = Path(__file__).parent / "fixtures" / "sotn_pal.mds"  # .mds real: dados + 1 faixa de áudio, com subcanal


def _f(p: Path, data: bytes = b"x") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


def test_extra_volumes_skipped_only_with_first_volume(tmp_path):
    files = [_f(tmp_path / n) for n in ("jogo.rar", "jogo.r00", "jogo.r25", "outro.r00",
                                       "x.part1.rar", "x.part2.rar", "x.part10.rar", "y.part2.rar")]
    skip = {f.name for f in files if content._extra_volume(f, files)}
    assert skip == {"jogo.r00", "jogo.r25", "x.part2.rar", "x.part10.rar"}


def test_real_mds_tracks():
    tr = content.mds_tracks(FIX)
    assert [(t["track"], t["kind"], t["sector"], t["start"]) for t in tr] == [
        (1, "MODE2/2352", 2448, 0), (2, "AUDIO", 2448, 229174)]


def test_mdf_without_mds_single_track(tmp_path):
    mdf = _f(tmp_path / "jogo.mdf", bytes(2352 * 4))
    cue = content.mdf_to_cue(mdf)
    assert cue.name == "jogo.cue" and (tmp_path / "jogo.bin").stat().st_size == 2352 * 4
    assert cue.read_text().splitlines() == ['FILE "jogo.bin" BINARY', "  TRACK 01 MODE2/2352", "    INDEX 01 00:00:00"]


def test_dvd_sized_mdf_untouched(tmp_path):
    odd = _f(tmp_path / "b.mdf", bytes(2048 * 3))
    assert content.mdf_to_cue(odd) is None and odd.exists()


def test_subchannel_stripped_and_audio_track_kept(tmp_path, monkeypatch):
    shutil.copyfile(FIX, tmp_path / "SLES_00524.mds")
    sectors = [bytes([i]) * 2352 + b"\xff" * 96 for i in range(5)]
    mdf = _f(tmp_path / "SLES_00524.mdf", b"".join(sectors))
    real = content.mds_tracks(FIX)
    small = [dict(real[0]), dict(real[1], start=4, offset=2 * 2448)]  # mesma estrutura, disco minúsculo
    monkeypatch.setattr(content, "mds_tracks", lambda p: small)
    cue = content.mdf_to_cue(mdf, "Castlevania - Symphony of the Night PSX (PAL)")
    assert cue.name == "Castlevania - Symphony of the Night PSX (PAL).cue"
    data = (tmp_path / "Castlevania - Symphony of the Night PSX (PAL).bin").read_bytes()
    assert len(data) == 5 * 2352 and data[2352] == 1 and b"\xff" not in data
    assert not mdf.exists() and not (tmp_path / "SLES_00524.mds").exists()
    assert cue.read_text().splitlines() == [
        'FILE "Castlevania - Symphony of the Night PSX (PAL).bin" BINARY',
        "  TRACK 01 MODE2/2352", "    INDEX 01 00:00:00",
        "  TRACK 02 AUDIO", "    INDEX 00 00:00:02", "    INDEX 01 00:00:04"]


def test_msf():
    assert content._msf(229174) == "50:55:49"
