"""Duplicatas (identidade, checagem antes de baixar, /sync), remoção com confirmação, qualidade por
jogo com devolução, controles do Switch."""
import json
from pathlib import Path

import pytest

from dc import bot, controls, dedup, quality, remove
from dc.paths import get_paths
from dc.store import Store


# ---------------------------------------------------------------- identidade
def test_match_key_ignores_region_version_and_roman():
    k = lambda t, c="ps2": dedup.match_key(t, c)
    assert k("God of War II (USA)") == k("God of War 2 [!]") == k("god_of_war_ii (v1.01) (En,Fr)")
    assert k("Shadow of the Colossus (USA)") == k("Shadow of the Colossus")
    assert k("Okami") != k("Okami", "wii")                                  # console diferente
    assert k("Final Fantasy Tactics [BR]", "psx") != k("Final Fantasy Tactics", "psx")  # tradução é outro jogo


def test_switch_identity_by_title_id():
    a = dedup.match_key("Castlevania Dominus", "switch", "/r/Castlevania Dominus [01006BE01FE6C000][v0].nsp")
    b = dedup.match_key("Dominus Collection", "switch", "/r/x/Dominus Collection [01006BE01FE6C000].xci")
    upd = dedup.base_title_id("Castlevania [01006BE01FE6C800][v131072].nsp")
    dlc = dedup.base_title_id("Algo [01006BE01FE6D001].nsp")
    assert a == b and upd == "01006BE01FE6C000" and dlc == "01006BE01FE6C000"


def test_torrent_and_magnet_names():
    data = b"d8:announce3:url4:infod6:lengthi1e4:name21:Okami (USA) [PS2].iso12:piece lengthi1eee"
    assert dedup.torrent_name(data) == "Okami (USA) [PS2].iso"
    assert dedup.torrent_name(b"lixo") is None
    assert dedup.magnet_name("magnet:?xt=urn:btih:abc&dn=Okami+%28USA%29") == "Okami (USA)"


def test_find_existing_library_and_downloads():
    lm = {"ps2-okami": {"title": "Okami", "console": "ps2", "rom": "/r/ps2/Okami/Okami.iso"}}
    assert "biblioteca" in dedup.find_existing("Okami (USA) [PS2].torrent", "ps2", lm)
    assert dedup.find_existing("Okami (USA)", "wii", lm) is None
    assert "biblioteca" in dedup.find_existing("Okami (USA)", None, lm)  # console desconhecido: compara pelo nome
    ts = [{"name": "Shadow of the Colossus.rar", "category": "ps2", "progress": 0.6}]
    assert "downloads (60%)" in dedup.find_existing("Shadow of the Colossus (USA)", "ps2", {}, ts)
    assert dedup.find_existing("Hercules", "psx", lm, ts) is None


def test_library_dups_groups_same_game():
    lm = {"a": {"title": "Okami", "console": "ps2", "rom": "/1"},
          "b": {"title": "Okami (USA)", "console": "ps2", "rom": "/2"},
          "c": {"title": "Okami (USA)", "console": "ps2", "rom": "/3", "removed": True},
          "d": {"title": "Hercules", "console": "psx", "rom": "/4"}}
    assert dedup.library_dups(lm) == [["a", "b"]]


# ---------------------------------------------------------------- bot: antes de baixar
class Q:
    def __init__(self, ts=()):
        self.ts, self.added, self.deleted = list(ts), [], []

    def torrents(self, *a, **k):
        return self.ts

    def add(self, magnet, cat, path):
        self.added.append(magnet)

    def add_file(self, data, name, cat, path):
        self.added.append(name)

    def delete(self, h, delete_files=False):
        self.deleted.append((h, delete_files))


@pytest.fixture
def b(tmp_path, monkeypatch):
    paths = get_paths(tmp_path).ensure()
    monkeypatch.setattr(bot.ops, "game_running", lambda: False)
    x = bot.Bot(paths, "TOKEN123")
    x.qbt = Q()
    x.cfg["allowed"] = [1]
    (paths.data / "launch-map.json").write_text(json.dumps(
        {"ps2-okami": {"title": "Okami", "console": "ps2", "rom": str(tmp_path / "roms/ps2/Okami/Okami.iso")}}))
    return x


def test_bot_holds_duplicate_magnet_until_baixar(b):
    r = b.handle(1, 1, "/add ps2 magnet:?xt=urn:btih:abc&dn=Okami+(USA)")
    assert "Parece repetido" in r and b.qbt.added == []
    assert "mesmo assim" in b.handle(1, 1, "/baixar") and b.qbt.added
    assert "Nada guardado" in b.handle(1, 1, "/baixar")
    assert "Adicionado" in b.handle(1, 1, "/add ps2 magnet:?xt=urn:btih:def&dn=Rez")


# ---------------------------------------------------------------- remoção
def _setup_game(tmp_path, paths, name="Okami", gid="ps2-okami"):
    roms = tmp_path / "roms"
    d = roms / "ps2" / name
    d.mkdir(parents=True)
    (d / f"{name}.iso").write_bytes(b"x" * 2048)
    lm_p = paths.data / "launch-map.json"
    lm = json.loads(lm_p.read_text()) if lm_p.exists() else {}
    lm[gid] = {"title": name, "console": "ps2", "rom": str(d / f"{name}.iso")}
    lm_p.write_text(json.dumps(lm))
    (paths.data / "plugin-done.json").write_text(json.dumps({gid: {"appid": 3000000001, "error": ""}}))
    (paths.data / "plugin-items.json").write_text(json.dumps({gid: {"game_id": gid}}))
    (paths.state / "sync-state.json").write_text(json.dumps({"ingested": {"HASH": {"name": "t", "files": [str(d / f"{name}.iso")]}}}))
    return roms, d


def test_remove_plan_then_apply_moves_to_quarantine(tmp_path, monkeypatch):
    paths = get_paths(tmp_path / "dc").ensure()
    roms, d = _setup_game(tmp_path, paths)
    monkeypatch.setattr(remove.plugin_bridge, "installed", lambda *a: True)
    rp = remove.plan(paths, "ps2-okami", [roms])
    assert rp.move == d and rp.torrents == ["HASH"] and rp.appids == [3000000001] and "30 dias" in rp.describe()
    assert d.exists()  # plano não faz nada
    q = Q()
    store = Store(paths.db)
    with store.tx() as c:
        for p in (d / "Okami.iso", tmp_path / "roms/ps2/Okami2/x.iso"):  # o segundo é de outro jogo e fica
            c.execute("INSERT INTO files(path,size,mtime,origin) VALUES(?,?,?,?)", (str(p), 1, 0, "torrent"))
    out = remove.apply(paths, store, rp, q)
    assert [r[0] for r in store.conn.execute("SELECT path FROM files")] == [str(tmp_path / "roms/ps2/Okami2/x.iso")]
    assert not d.exists() and q.deleted == [("HASH", True)]
    assert "ps2-okami" not in json.loads((paths.data / "launch-map.json").read_text())
    assert json.loads((paths.data / "plugin-done.json").read_text())["ps2-okami"]["removed"] is True
    assert json.loads((paths.data / "plugin-remove.json").read_text()) == [{"game_id": "ps2-okami", "appid": 3000000001}]
    assert json.loads((paths.data / "plugin-items.json").read_text()) == {}
    assert any("quarentena" in x for x in out)
    from dc import quarantine
    assert len(quarantine.list_entries(paths.quarantine)) == 1  # recuperável


def test_remove_only_file_when_folder_is_shared(tmp_path):
    paths = get_paths(tmp_path / "dc").ensure()
    roms, d = _setup_game(tmp_path, paths)
    lm = json.loads((paths.data / "launch-map.json").read_text())
    (d / "Outro.iso").write_bytes(b"y")
    lm["ps2-outro"] = {"title": "Outro", "console": "ps2", "rom": str(d / "Outro.iso")}
    (paths.data / "launch-map.json").write_text(json.dumps(lm))
    assert remove.plan(paths, "ps2-okami", [roms]).move == d / "Okami.iso"


def test_bot_remove_requires_confirmation(b, tmp_path, monkeypatch):
    roms, d = _setup_game(tmp_path, b.paths, "Okami (USA)", "ps2-okami-usa")
    monkeypatch.setattr(bot.syncer, "rom_roots", lambda: [roms])
    lst = b.handle(1, 1, "/duplicados")
    assert "Mesmo jogo" in lst and "1." in lst and "2." in lst
    r = b.handle(1, 1, "/remover 2")
    assert "Confirme" in r and d.exists()
    r = b.handle(1, 1, "/remover 2 confirmar")
    assert "Removido" in r and not d.exists()
    assert "Nenhum jogo repetido" in b.handle(1, 1, "/duplicados")


def test_write_map_keeps_user_removal(tmp_path):
    from dc.library import Game, write_map
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"g": {"title": "T", "console": "ps2", "rom": "/x", "removed": True}}))
    write_map(p, [Game("g", "T", "ps2", "/x")])
    assert json.loads(p.read_text())["g"]["removed"] is True


# ---------------------------------------------------------------- qualidade por jogo
def test_quality_override_applies_and_restores(tmp_path, monkeypatch):
    paths = get_paths(tmp_path / "dc").ensure()
    ini = tmp_path / "PCSX2.ini"
    ini.write_text("[EmuCore/GS]\nupscale_multiplier = 3\nRenderer = -1\n")
    monkeypatch.setitem(quality.TARGETS, "ps2", ("ini", [ini], "EmuCore/GS", "upscale_multiplier"))
    assert "Esse console" in quality.set_override(paths, "snes-x", "snes", "2x")
    with pytest.raises(ValueError):
        quality.set_override(paths, "ps2-sotc", "ps2", "9x")
    assert "2x" in quality.set_override(paths, "ps2-sotc", "ps2", "2x")
    rec = quality.apply_for_launch(paths, "ps2-sotc", "ps2")
    assert rec["old"] == "3" and "upscale_multiplier = 2" in ini.read_text()
    assert quality.apply_for_launch(paths, "ps2-outro", "ps2") is None  # jogo sem ajuste: nada muda
    assert "devolvido" in quality.restore(paths) and "upscale_multiplier = 3" in ini.read_text()
    assert quality.restore(paths) is None  # nada pendente


def test_quality_respects_manual_change_during_game(tmp_path, monkeypatch):
    paths = get_paths(tmp_path / "dc").ensure()
    cfg = tmp_path / "Config.json"
    cfg.write_text(json.dumps({"res_scale": 1, "other": True}))
    monkeypatch.setitem(quality.TARGETS, "switch", ("json", [cfg], None, "res_scale"))
    quality.set_override(paths, "switch-x", "switch", "2x")
    quality.apply_for_launch(paths, "switch-x", "switch")
    assert json.loads(cfg.read_text())["res_scale"] == 2
    d = json.loads(cfg.read_text()); d["res_scale"] = 3; cfg.write_text(json.dumps(d))  # usuário mudou no menu
    assert "mantido" in quality.restore(paths) and json.loads(cfg.read_text())["res_scale"] == 3
    assert "padrão" in quality.set_override(paths, "switch-x", "switch", "padrão")
    assert quality.get_override(paths, "switch-x") is None


# ---------------------------------------------------------------- controles
def test_switch_layout_labels_and_check(tmp_path):
    p = tmp_path / ".config/Ryujinx/Config.json"
    p.parent.mkdir(parents=True)
    pad = {"backend": "GamepadSDL2", "id": "0-x", "right_joycon": {"button_a": "B", "button_b": "A", "button_x": "Y",
                                                                    "button_y": "X", "button_r": "RightShoulder"}}
    kb = {"backend": "WindowKeyboard", "right_joycon": {"button_a": "Z"}}
    p.write_text(json.dumps({"input_config": [kb, pad]}))
    assert controls.switch_layout("labels", tmp_path)
    d = json.loads(p.read_text())["input_config"]
    assert d[1]["right_joycon"]["button_a"] == "A" and d[1]["right_joycon"]["button_r"] == "RightShoulder"
    assert d[0]["right_joycon"]["button_a"] == "Z"  # teclado intocado
    assert controls.switch_layout("labels", tmp_path) == []  # idempotente
    ryu = [c for c in controls.check(tmp_path) if "Ryujinx" in c.emulator][0]
    assert ryu.ok and "A=A" in ryu.detail


def test_controls_check_flags_unmapped_dolphin(tmp_path):
    p = tmp_path / ".var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu/GCPadNew.ini"
    p.parent.mkdir(parents=True)
    p.write_text("[GCPad1]\nDevice = XInput2/0/Virtual core pointer\n")
    gc = [c for c in controls.check(tmp_path) if c.emulator == "Dolphin GameCube"][0]
    assert not gc.ok
    p.write_text("[GCPad1]\nDevice = SDL/0/Steam Deck\n")
    assert [c for c in controls.check(tmp_path) if c.emulator == "Dolphin GameCube"][0].ok


# ---------------------------------------------------------------- brechas do /sync
def test_no_space_is_not_quarantined(tmp_path, monkeypatch):
    import zipfile
    from dc import content, safe_extract
    src = tmp_path / "dl" / "Jogo.zip"
    src.parent.mkdir()
    with zipfile.ZipFile(src, "w") as z:
        z.writestr("Jogo.iso", b"x" * 4096)

    def full(*a, **k):
        raise safe_extract.NoSpace("espaço insuficiente: precisa 9.0 GB, livre 1.0 GB")
    monkeypatch.setattr(content.safe_extract, "extract_any", full)
    it = content.ingest(src, "ps2", tmp_path / "roms", tmp_path / "q", tmp_path / "w")
    assert it.status == "no_space" and src.exists() and not (tmp_path / "q").exists()


def test_store_game_with_same_name_gets_console_suffix():
    from dc.library import Game, plan
    store_row = {"appid": -5, "AppName": "Okami", "exe": '"/home/deck/unifideck/launch.sh"'}
    manual = {"appid": -6, "AppName": "Hercules", "exe": '"/usr/bin/duckstation"'}
    pl = plan([store_row, manual], [Game("ps2-okami", "Okami", "ps2", "/r/Okami.iso"),
                                    Game("psx-hercules", "Hercules", "psx", "/r/H.cue")], Path("/l/dc-launch"))
    assert [r["AppName"] for r in pl.add] == ["Okami (PlayStation 2)"] and pl.add[0]["LaunchOptions"] == "ps2-okami"
    assert pl.name_conflicts == ["Hercules"]


def _sync_env(tmp_path, monkeypatch):
    from dc import syncer
    paths = get_paths(tmp_path / "dc").ensure()
    roms = tmp_path / "roms"
    (paths.config / "deck.json").write_text(json.dumps({"roms_root": str(roms)}))
    monkeypatch.setattr(syncer.ops, "game_running", lambda: False)
    monkeypatch.setattr(syncer, "rom_roots", lambda: [roms])
    monkeypatch.setattr(syncer, "add_to_steam", lambda *a: [])
    return syncer, paths, roms


def test_sync_quarantines_duplicate_download(tmp_path, monkeypatch):
    syncer, paths, roms = _sync_env(tmp_path, monkeypatch)
    old = roms / "ps2/Okami/Okami.iso"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"a" * 2048)
    (paths.data / "launch-map.json").write_text(json.dumps({"ps2-okami": {"title": "Okami", "console": "ps2", "rom": str(old)}}))
    dl = tmp_path / "dl/Okami (USA)"
    dl.mkdir(parents=True)
    (dl / "Okami (USA).iso").write_bytes(b"b" * 2048)
    t = {"hash": "H2", "name": "Okami (USA)", "state": "uploading", "content_path": str(dl), "category": "ps2"}
    out = syncer.run_sync(paths, Store(paths.db), Q([t]))
    assert "já tem «Okami»" in out and not (roms / "ps2/Okami (USA)").exists() and old.exists()
    st = json.loads((paths.state / "sync-state.json").read_text())
    assert st["ingested"]["H2"]["duplicate_of"] == "Okami"
    assert "0 jogo" in syncer.run_sync(paths, Store(paths.db), Q([t]))  # não reprocessa


def test_sync_slow_extraction_continues_later_without_losing_state(tmp_path, monkeypatch):
    syncer, paths, roms = _sync_env(tmp_path, monkeypatch)
    ts = []
    for n in ("Rez", "Ico"):
        d = tmp_path / "dl" / n
        d.mkdir(parents=True)
        (d / f"{n}.iso").write_bytes(b"c" * 2048)
        ts.append({"hash": n, "name": n, "state": "uploading", "content_path": str(d), "category": "ps2"})
    real, done = syncer.content.ingest, []

    def slow_ingest(*a, **k):  # a 1ª extração "demora" mais de 5 minutos
        done.append(1)
        return real(*a, **k)
    monkeypatch.setattr(syncer.content, "ingest", slow_ingest)
    monkeypatch.setattr(syncer.time, "monotonic", lambda: 999 if done else 0)
    out = syncer.run_sync(paths, Store(paths.db), Q(ts))
    assert "ficam para a próxima" in out and "Safe-mode" not in out
    st = json.loads((paths.state / "sync-state.json").read_text())
    assert list(st["ingested"]) == ["Rez"] and st["timeouts"] == 0
