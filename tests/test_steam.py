"""Usuário Steam ativo (Deck com várias contas) e ingest com hardlink."""
import os

from dc import content, steam


def test_most_recent_account_wins(tmp_path):
    root = tmp_path / "steam"
    for uid in ("111", "222"):
        (root / "userdata" / uid / "config").mkdir(parents=True)
    (root / "config").mkdir()
    sid = str(222 + steam.STEAMID64_BASE)
    (root / "config/loginusers.vdf").write_text(
        '"users" { "%d" { "AccountName" "a" "MostRecent" "0" } "%s" { "AccountName" "b" "MostRecent" "1" } }'
        % (111 + steam.STEAMID64_BASE, sid))
    assert steam.userdata_dir(root).name == "222"
    assert steam.shortcuts_path(root).name == "shortcuts.vdf"


def test_fallback_to_most_recently_used(tmp_path):
    root = tmp_path / "steam"
    for uid, age in (("111", 100), ("222", 10)):
        d = root / "userdata" / uid / "config"; d.mkdir(parents=True)
        (d / "localconfig.vdf").write_text("x"); os.utime(d / "localconfig.vdf", (age, age))
    assert steam.userdata_dir(root).name == "111"


def test_ingest_uses_hardlink_on_same_disk(tmp_path):
    d = tmp_path / "dl" / "Jogo"; d.mkdir(parents=True)
    src = d / "Jogo.gba"; src.write_bytes(b"x" * 4096)
    it = content.ingest(d, "gba", tmp_path / "roms", tmp_path / "q", tmp_path / "work")
    out = tmp_path / "roms/gba/Jogo/Jogo.gba"
    assert it.status == "added" and out.exists() and src.exists()
    assert os.stat(out).st_ino == os.stat(src).st_ino or os.name == "nt"  # mesmo arquivo físico (Linux)
