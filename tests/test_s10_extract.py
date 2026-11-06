"""S10 — ZIP Slip / ZIP bomb / symlink / colisão / cancelamento."""
import stat
import threading
import zipfile

import pytest

from dc.safe_extract import ExtractionCancelled, Limits, UnsafeArchive, extract, inspect


def make_zip(path, entries):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data, *mode in entries:
            if mode:
                zi = zipfile.ZipInfo(name)
                zi.external_attr = mode[0] << 16
                z.writestr(zi, data)
            else:
                z.writestr(name, data)
    return path


def test_ok_extract(tmp_path):
    z = make_zip(tmp_path / "a.zip", [("Game (Disc 1).cue", "x"), ("Game (Disc 1).bin", b"\x01" * 1000)])
    out = extract(z, tmp_path / "lib" / "Game")
    assert len(out) == 2 and all(p.exists() for p in out)


@pytest.mark.parametrize("name", ["../evil.txt", "a/../../evil.txt", "/etc/passwd", "C:/x.txt", "..\\evil.txt"])
def test_zip_slip_rejected(tmp_path, name):
    z = make_zip(tmp_path / "s.zip", [(name, "x")])
    with pytest.raises(UnsafeArchive):
        extract(z, tmp_path / "out")
    assert not (tmp_path / "evil.txt").exists() and not (tmp_path / "out").exists()


def test_symlink_rejected(tmp_path):
    z = make_zip(tmp_path / "l.zip", [("link", "/home/deck/.ssh", stat.S_IFLNK | 0o777)])
    with pytest.raises(UnsafeArchive, match="simbólico"):
        inspect(z)


def test_bomb_ratio_rejected(tmp_path):
    z = make_zip(tmp_path / "b.zip", [("zeros.bin", b"\x00" * (50 * 1024 * 1024))])
    with pytest.raises(UnsafeArchive, match="proporção"):
        inspect(z)


def test_total_size_and_count_limits(tmp_path):
    z = make_zip(tmp_path / "t.zip", [(f"f{i}", "x" * 10) for i in range(20)])
    with pytest.raises(UnsafeArchive):
        inspect(z, Limits(max_files=10))
    with pytest.raises(UnsafeArchive):
        inspect(z, Limits(max_total_bytes=100))


def test_collisions_rejected(tmp_path):
    z = make_zip(tmp_path / "c.zip", [("Game.bin", "a"), ("game.BIN", "b")])
    with pytest.raises(UnsafeArchive, match="colisão"):
        inspect(z)
    z2 = make_zip(tmp_path / "c2.zip", [("a", "x"), ("a/b", "y")])
    with pytest.raises(UnsafeArchive, match="colisão"):
        inspect(z2)


def test_depth_limit(tmp_path):
    z = make_zip(tmp_path / "d.zip", [("/".join(["d"] * 20) + "/f", "x")])
    with pytest.raises(UnsafeArchive, match="profundidade"):
        inspect(z)


def test_cancel_leaves_no_partial_library(tmp_path):
    import os
    z = make_zip(tmp_path / "big.zip", [("a.bin", os.urandom(3 * 1024 * 1024))])
    ev = threading.Event(); ev.set()
    with pytest.raises(ExtractionCancelled):
        extract(z, tmp_path / "lib" / "G", cancel=ev, chunk=64 * 1024)
    assert not (tmp_path / "lib" / "G").exists()
    assert not any(p.name.startswith(".dc-extract-") for p in (tmp_path / "lib").iterdir())


def test_not_a_zip(tmp_path):
    p = tmp_path / "x.zip"; p.write_bytes(b"nope")
    with pytest.raises(UnsafeArchive):
        inspect(p)
