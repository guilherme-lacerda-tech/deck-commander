"""Xbox 360: nome no bot, reconhecimento do download e jogo no formato Games on Demand."""
from dc import bot, content, library


def test_alias_is_360_not_original_xbox():
    assert bot.parse_console("xbox 360") == "x360"
    assert bot.parse_console("Xbox360") == "x360"
    assert bot.parse_console("xbox") == "xbox"


def test_download_name_hint():
    assert content.classify("Call of Duty - Black Ops 1-2 [Freeboot, FullRus]") == "x360"


def test_god_folder_is_found_by_library(tmp_path):
    hd = tmp_path / "x360/Call of Duty Black Ops 1/41560855/00007000/18543A0E312861A81135"
    hd.parent.mkdir(parents=True)
    hd.write_bytes(b"LIVE")
    (hd.parent / (hd.name + ".data")).mkdir()
    (hd.parent / (hd.name + ".data/Data0000")).write_bytes(b"x")
    games, _ = library.scan([tmp_path])
    g = next(g for g in games if g.console == "x360")
    assert g.title == "Call of Duty Black Ops 1" and g.path == str(hd)
    assert content.playable([hd, hd.parent / (hd.name + ".data/Data0000")], "x360") == [hd]
