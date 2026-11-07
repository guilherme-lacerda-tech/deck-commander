"""Ponte com o plugin do Decky: fila, reconhecimento por game_id, coleta de AppIDs, backend do plugin."""
import asyncio
import importlib.util
import json
from pathlib import Path

from dc import library, plugin_bridge
from dc.paths import get_paths
from dc.store import Store

ROW = {"LaunchOptions": "switch-castlevania", "AppName": "Castlevania", "exe": '"/x/dc-launch"', "StartDir": '"/x/"'}


def test_enqueue_is_idempotent_and_collect_records_appid(tmp_path):
    paths = get_paths(tmp_path).ensure()
    assert plugin_bridge.enqueue(paths, [ROW], with_art=False) == 1
    assert plugin_bridge.enqueue(paths, [ROW], with_art=False) == 0
    assert plugin_bridge.pending(paths) == ["switch-castlevania"]
    assert json.loads((paths.data / "plugin-items.json").read_text())["switch-castlevania"]["name"] == "Castlevania"
    (paths.data / "plugin-done.json").write_text(json.dumps({"switch-castlevania": {"appid": 3123456789, "error": ""}}))
    s = Store(paths.db)
    assert plugin_bridge.collect(paths, s) == []
    assert s.conn.execute("SELECT appid FROM provenance").fetchone()[0] == "3123456789"
    assert plugin_bridge.pending(paths) == []


def test_plan_recognizes_plugin_created_shortcut():
    g = library.Game("switch-castlevania", "Castlevania", "switch", "/r/c.nsp")
    existing = [{"appid": 999, "AppName": "Castlevania", "exe": '"/x/dc-launch"', "LaunchOptions": "switch-castlevania"}]
    pl = library.plan(existing, [g], Path("/x/dc-launch"))
    assert pl.add == [] and pl.already == ["Castlevania"]


def test_installed_detection(tmp_path):
    assert not plugin_bridge.installed(tmp_path)
    d = tmp_path / "homebrew/plugins/deck-commander"; d.mkdir(parents=True)
    (d / "plugin.json").write_text('{"name": "Deck Commander"}')
    assert plugin_bridge.installed(tmp_path)


def test_plugin_backend(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("dcplugin", Path(__file__).resolve().parents[1] / "decky-plugin/main.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    base = tmp_path / "base"; base.mkdir()
    monkeypatch.setattr(m, "BASE", str(base)); monkeypatch.setattr(m, "QUEUE", str(base / "q.json")); monkeypatch.setattr(m, "DONE", str(base / "d.json"))
    monkeypatch.setattr(m, "ITEMS", str(base / "i.json"))
    (base / "q.json").write_text(json.dumps([{"game_id": "a"}, {"game_id": "b"}]))
    (base / "art.png").write_bytes(b"PNG")
    p = m.Plugin(); run = asyncio.run
    assert [x["game_id"] for x in run(p.get_pending())] == ["a", "b"]
    run(p.report("a", 123, "")); run(p.report("b", 0, "falhou"))
    assert run(p.get_pending()) == [] and run(p.get_status())["added"] == 1
    run(p.remember_item("a", {"game_id": "a", "name": "A"}))
    assert run(p.get_done())["a"] == {"appid": 123, "error": "", "item": {"game_id": "a", "name": "A"}}
    assert run(p.read_art(str(base / "art.png")))["ext"] == "png"
    outside = tmp_path / "segredo.png"; outside.write_bytes(b"x")
    assert run(p.read_art(str(outside))) is None  # nunca lê fora da pasta do DC


def test_plugin_backend_removal_and_launch_error(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("dcplugin2", Path(__file__).resolve().parents[1] / "decky-plugin/main.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    base = tmp_path / "base"; base.mkdir()
    for k, f in (("BASE", ""), ("QUEUE", "q.json"), ("DONE", "d.json"), ("ITEMS", "i.json"), ("REMOVE", "r.json")):
        monkeypatch.setattr(m, k, str(base / f) if f else str(base))
    p = m.Plugin(); run = asyncio.run
    run(p.report("a", 123, "")); run(p.remember_item("a", {"game_id": "a"}))
    (base / "r.json").write_text(json.dumps([{"game_id": "a", "appid": 123}]))
    assert run(p.get_removals()) == [{"game_id": "a", "appid": 123}]
    run(p.removal_done("a", 123))
    assert run(p.get_removals()) == [] and run(p.get_done()) == {}  # removido some da autocorreção
    assert run(p.get_status())["removed"] == 1
    assert run(p.get_launch_error()) is None
    (base / "launch-error.json").write_text(json.dumps({"message": "cartão SD?"}))
    assert run(p.get_launch_error()) == "cartão SD?" and run(p.get_launch_error()) is None  # mostra 1 vez


def test_launch_failure_leaves_message_for_plugin(tmp_path, monkeypatch):
    import pytest
    from dc import launch
    monkeypatch.setenv("DC_ROOT", str(tmp_path))
    from dc.paths import get_paths
    paths = get_paths().ensure()
    (paths.data / "launch-map.json").write_text(json.dumps(
        {"ps2-x": {"title": "Jogo X", "console": "ps2", "rom": "/run/media/deck/SD/Emulation/roms/ps2/x.iso"}}))
    with pytest.raises(SystemExit):
        launch.main(["ps2-x"])
    msg = json.loads((paths.data / "launch-error.json").read_text())["message"]
    assert "Jogo X" in msg and "cartão SD" in msg
    with pytest.raises(SystemExit):
        launch.main(["sumiu"])
    assert "removido" in json.loads((paths.data / "launch-error.json").read_text())["message"]
