"""M2 — launcher fixo + mapa. Nomes de arquivo reais do Deck do usuário."""
from pathlib import Path

import pytest

from dc import library, vdf

SW = "switch/Super Mario Galaxy 1-2 [NSZ]/Super Mario Galaxy"


def touch(root, rel, data=b"x"):
    p = root / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data); return p


@pytest.fixture
def roms(tmp_path):
    r = tmp_path / "roms"
    touch(r, f"{SW}/Super Mario Galaxy [010099C022B96000][v0] (3.30 GB).nsp")
    touch(r, f"{SW}/Super Mario Galaxy [010099C022B96800][v327680] (0.32 GB).nsp")       # update
    touch(r, "switch/Z-A/Pokemon Legends Z-A [DLC Mega Dimension Full] [0100F43008C45002][v0].nsp")  # DLC
    touch(r, "switch/Z-A/Pokemon Legends Z-A [0100F43008C44000][v0] (4.02 GB).nsp")
    touch(r, "ps2/Ghost Rider (BR) (DUB-IA) (T1.0) (www.romsportugues.com).iso")
    touch(r, "psx/Final Fantasy Tactics (BR)/Final Fantasy Tactics (BR) (T1.6.4) (www.romsportugues.com).cue")
    touch(r, "psx/Final Fantasy Tactics (BR)/Final Fantasy Tactics (BR) (T1.6.4) (www.romsportugues.com).bin")
    touch(r, "switch-outros-idiomas/x [01004B3023412000][v0].nsp")
    return r


def test_scan_picks_base_games_and_cleans_titles(roms):
    games, _ = library.scan([roms])
    got = {(g.console, g.title) for g in games}
    assert got == {("switch", "Super Mario Galaxy"), ("switch", "Pokemon Legends Z-A"),
                   ("ps2", "Ghost Rider (BR) (DUB-IA)"), ("psx", "Final Fantasy Tactics (BR)")}
    assert {g.game_id for g in games} >= {"switch-super-mario-galaxy", "ps2-ghost-rider-br-dub-ia"}


def test_appid_stable_and_matches_formula(tmp_path, roms):
    launcher = Path("/home/deck/.local/share/deck-commander/bin/dc-launch")
    g = library.scan([roms])[0][0]
    a = library.shortcut_for(g, launcher)
    assert a["appid"] & 0xFFFFFFFF == vdf.shortcut_appid(a["exe"], a["AppName"])
    g.path = "/outro/lugar/jogo.m3u"  # mudar ROM/formato não muda o AppID
    assert library.shortcut_for(g, launcher)["appid"] == a["appid"]


def test_plan_and_write_preserves_existing(tmp_path, roms):
    launcher = Path("/home/deck/.local/share/deck-commander/bin/dc-launch")
    existing = {"shortcuts": {
        "0": {"appid": -123456, "AppName": "Metro 2033 Redux", "exe": '"/x/unifideck-launcher"',
              "LastPlayTime": 1791217677, "tags": {"0": "Epic"}},
        "1": {"appid": -5, "AppName": "Ghost Rider (BR) (DUB-IA)", "exe": '"/manual"', "tags": {}}}}
    p = tmp_path / "shortcuts.vdf"; p.write_bytes(vdf.dump_binary(existing))
    before = vdf.read_shortcuts(p)
    games, _ = library.scan([roms])
    pl = library.plan(before, games, launcher)
    assert pl.name_conflicts == ["Ghost Rider (BR) (DUB-IA)"]  # manual com mesmo nome: não duplica
    assert len(pl.add) == 3
    library.write_shortcuts(p, pl.add)
    after = vdf.read_shortcuts(p)
    assert after[:2] == before  # existentes intactos, na mesma posição
    assert len(after) == 5
    pl2 = library.plan(after, games, launcher)  # idempotente
    assert pl2.add == [] and len(pl2.already) == 3


def test_write_refuses_unknown_format(tmp_path):
    p = tmp_path / "shortcuts.vdf"
    p.write_bytes(b"\x00shortcuts\x00\x07big\x00" + (5).to_bytes(8, "little") + b"\x08\x08")
    with pytest.raises(RuntimeError, match="round-trip"):
        library.write_shortcuts(p, [])


def test_launch_command(tmp_path, roms):
    games, _ = library.scan([roms])
    m = tmp_path / "launch-map.json"; library.write_map(m, games)
    import json
    lm = json.loads(m.read_text("utf-8"))
    cmd = library.build_command("ps2-ghost-rider-br-dub-ia", lm, {})
    assert cmd[:3] == ["/usr/bin/flatpak", "run", "net.pcsx2.PCSX2"] and cmd[-1].endswith(".iso")
    assert library.build_command("switch-super-mario-galaxy", lm, {"switch": ["/x/ryu", "{rom}"]})[0] == "/x/ryu"
    with pytest.raises(KeyError):
        library.build_command("nao-existe", lm, {})
