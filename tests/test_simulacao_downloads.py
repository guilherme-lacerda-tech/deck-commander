"""Simulação 10/11: downloads de vários consoles como o /sync recebe (categoria "auto" = /add sem console)."""
import json
import zipfile

from dc import content, library


def _w(p, n=2048):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\x01" * n)
    return p


def _ing(tmp_path, path, cat="auto"):
    return content.ingest(path, cat, tmp_path / "roms", tmp_path / "q", tmp_path / "work")


def test_god_of_war_is_not_xbox_360():
    assert content.classify("God of War II (USA).iso") is None          # ambíguo: pergunta (antes ia p/ x360)
    assert content.classify("God of War Chains of Olympus.cso") is None
    assert content.classify("Halo 3 (GOD)") == "x360"
    assert content.classify("Halo 3 [GOD]") == "x360"
    assert content.classify("Mario Kart 8 (Wii U).wua") == "wiiu"         # antes: "wii"
    assert content.classify("Pokemon Legends Z-A (Switch 2)") == "switch2"
    assert content.classify("Wipeout PlayStation Portable.iso") == "psp"


def test_auto_category_uses_download_name(tmp_path):
    d = tmp_path / "dl" / "Shadow Hearts PS2"
    _w(d / "Shadow Hearts (USA).iso")
    it = _ing(tmp_path, d)
    assert it.status == "added" and it.console == "ps2"


def test_console_by_folder_structure(tmp_path):
    ps3 = tmp_path / "dl" / "Demon's Souls [BLUS30443]"
    _w(ps3 / "PS3_GAME/USRDIR/EBOOT.BIN"); _w(ps3 / "PS3_GAME/PARAM.SFO")
    god = tmp_path / "dl" / "Forza Horizon (USA)"
    _w(god / "4D530910/00007000/ABCDEF"); _w(god / "4D530910/00007000/ABCDEF.data/Data0000")
    sw2 = tmp_path / "dl" / "Jogo Novo"
    _w(sw2 / "base/exefs/main")
    assert _ing(tmp_path, ps3).console == "ps3"
    assert _ing(tmp_path, god).console == "x360"
    it = _ing(tmp_path, sw2)
    assert it.console == "switch2" and it.status == "added" and it.files[0].endswith("main")


def test_console_from_names_inside_archive(tmp_path):
    z = tmp_path / "dl" / "Super Mario World (USA).zip"
    z.parent.mkdir(parents=True)
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("Super Mario World (USA).sfc", b"\x01" * 2048)
    it = _ing(tmp_path, z)
    assert it.console == "snes" and it.status == "added"
    assert content.classify("Pokemon Emerald (USA).7z") is None   # antes: "arcade" e o jogo era pulado


def test_not_a_game_is_skipped_not_asked(tmp_path):
    it = _ing(tmp_path, _w(tmp_path / "dl" / "Leia-me.txt"))
    assert it.status == "skipped" and "não achei arquivo de jogo" in it.note


def test_switch_update_alone_goes_to_switch_folder(tmp_path):
    it = _ing(tmp_path, _w(tmp_path / "dl" / "Zelda BotW Update [01007EF00011E800][v196608].nsp"))
    assert it.status == "added" and it.files == [] and "atualização" in it.note
    assert list((tmp_path / "roms" / "switch").rglob("*.nsp"))


def test_multidisc_m3u_is_one_game_in_scan(tmp_path):
    d = tmp_path / "dl" / "Final Fantasy VII PSX"
    for n in (1, 2, 3):
        _w(d / f"FF7 (Disc {n}).chd")
    it = _ing(tmp_path, d)
    assert it.status == "added" and it.files[0].endswith("FF7.m3u")
    games, _ = library.scan([tmp_path / "roms"])
    assert [g.title for g in games] == ["FF7"]   # antes: FF7 + 3 discos soltos = 4 atalhos


def test_god_title_without_tag(tmp_path):
    _w(tmp_path / "roms/x360/Halo 3 (GOD)/4D5307E6/00007000/0123ABCD")
    games, _ = library.scan([tmp_path / "roms"])
    assert [g.title for g in games] == ["Halo 3"]


def test_sync_skipped_warns_once_and_console_retries(tmp_path, monkeypatch):
    from dc import syncer
    from dc.paths import get_paths
    from dc.store import Store
    P = get_paths(tmp_path / "root").ensure()
    roms = tmp_path / "roms"
    (P.config / "deck.json").write_text(json.dumps({"roms_root": str(roms)}), "utf-8")
    dl = _w(tmp_path / "dl" / "Jogo (USA).sfc")
    tor = [{"hash": "ab" * 20, "name": dl.name, "content_path": str(dl), "category": "psx", "state": "stoppedUP"}]

    class Q:
        def torrents(self):
            return tor
    monkeypatch.setattr(syncer, "add_to_steam", lambda *a: [])
    monkeypatch.setattr(syncer.ops, "game_running", lambda: False)
    S = Store(P.db)
    out1 = syncer.run_sync(P, S, Q())
    assert "nenhum arquivo jogável para PlayStation" in out1 and "/console abababab" in out1
    out2 = syncer.run_sync(P, S, Q())
    assert "nenhum arquivo jogável" not in out2   # não repete a cada /sync
    st = syncer._state(P)
    assert "ab" * 20 in st["pending"]


def test_bench_refuses_while_deck_ai_is_busy(tmp_path, monkeypatch):
    from dc import bench
    from dc.paths import get_paths
    P = get_paths(tmp_path).ensure()
    real = bench.deck_ai_busy
    monkeypatch.setattr(bench, "launcher_pids", lambda *a: [])
    monkeypatch.setattr(bench, "deck_ai_busy", lambda *a: True)
    said = []
    assert bench.run(P, "psx-jogo", 30, log=said.append) is None
    assert "IA do Deck" in said[0]
    assert real("http://127.0.0.1:9/api/ps") is False  # sem Ollama: livre
