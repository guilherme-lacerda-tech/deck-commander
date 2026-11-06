from dc import vdf


def test_binary_roundtrip(tmp_path):
    obj = {"shortcuts": {"0": {"appid": -123, "AppName": "Donkey Kong Country", "Exe": '"/x/retroarch"',
                               "LastPlayTime": 1700000000, "tags": {"0": "SNES"}}}}
    p = tmp_path / "shortcuts.vdf"; p.write_bytes(vdf.dump_binary(obj))
    sc = vdf.read_shortcuts(p)
    assert sc[0]["AppName"] == "Donkey Kong Country" and sc[0]["LastPlayTime"] == 1700000000
    assert sc[0]["tags"] == {"0": "SNES"}


def test_text_vdf():
    t = '''"UserLocalConfigStore" { "Software" { "Valve" { "Steam" { "apps" {
        "2147483649" { "Playtime" "125" "LastPlayed" "1700000000" } } } } }
        // comentário
        "x" "a \\"q\\""}'''
    d = vdf.load_text(t)
    assert d["UserLocalConfigStore"]["Software"]["Valve"]["Steam"]["apps"]["2147483649"]["Playtime"] == "125"
    assert d["UserLocalConfigStore"]["x"] == 'a "q"'


def test_appid_changes_with_name_and_target():
    """F2: renomear (sufixo BR) ou trocar .cue por .m3u muda o AppID => playtime órfão."""
    base = vdf.shortcut_appid('"/x/duckstation" "/r/FF7 (Disc 1).cue"', "Final Fantasy VII")
    assert base & 0x80000000
    assert base != vdf.shortcut_appid('"/x/duckstation" "/r/FF7 (Disc 1).cue"', "Final Fantasy VII (BR)")
    assert base != vdf.shortcut_appid('"/x/duckstation" "/r/FF7.m3u"', "Final Fantasy VII")
