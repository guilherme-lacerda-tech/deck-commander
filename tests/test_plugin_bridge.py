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


def test_plugin_backend_appid_always_unsigned(tmp_path, monkeypatch):
    """O Steam às vezes entrega o AppID com sinal (-1732342533 == 2562624763): grava e compara sem sinal."""
    spec = importlib.util.spec_from_file_location("dcplugin3", Path(__file__).resolve().parents[1] / "decky-plugin/main.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    base = tmp_path / "base"; base.mkdir()
    for k, f in (("BASE", ""), ("QUEUE", "q.json"), ("DONE", "d.json"), ("ITEMS", "i.json"), ("REMOVE", "r.json")):
        monkeypatch.setattr(m, k, str(base / f) if f else str(base))
    p = m.Plugin(); run = asyncio.run
    run(p.report("a", -1732342533, ""))
    assert run(p.get_done())["a"]["appid"] == 2562624763
    (base / "r.json").write_text(json.dumps([{"game_id": "a", "appid": 2562624763}]))
    run(p.removal_done("a", -1732342533))  # o JS pode responder com sinal
    assert run(p.get_removals()) == []


def test_plugin_e_deck_commander_usam_a_mesma_trava(tmp_path):
    """Revisão de lançamento 12/11/2026: o plugin e o Deck Commander gravavam plugin-done.json ao mesmo tempo sem trava
    (um apagava a mudança do outro). Os dois precisam usar o MESMO arquivo de trava e nunca gravar direto."""
    import re
    raiz = Path(__file__).resolve().parents[1]
    main = (raiz / "decky-plugin/main.py").read_text("utf-8")
    assert 'path + ".lock"' in main
    assert not re.search(r"_save\((DONE|QUEUE|ITEMS|REMOVE),", main)  # só via _atualizar
    for arq in ("dc/pc_remoto.py", "dc/remove.py"):
        src = (raiz / arq).read_text("utf-8")
        assert not re.search(r"_save\(plugin_bridge\.(done_path|queue_path)", src), arq
        assert '_save(paths.data / "plugin-items.json"' not in src and '"plugin-remove.json", rq' not in src, arq


def test_sincronizar_pc_nao_apaga_a_marca_de_outro_jogo(tmp_path):
    """Mesma revisão: /pc sincronizar lia plugin-done.json no começo e, mais adiante, gravava aquela cópia velha
    por cima do que _tirar_atalho tinha acabado de marcar."""
    from dc import plugin_bridge as pb
    from dc.paths import get_paths
    p = get_paths(tmp_path)
    p.ensure()
    pb._save(pb.done_path(p), {"pc-a": {"appid": 5, "error": ""}, "pc-b": {"appid": 0, "removed": True}})
    pb.marcar_removido(p, "pc-a", [5], so_com_plugin=False)
    pb.atualizar(pb.done_path(p), {}, lambda d: d.pop("pc-b", None))  # o que o laço faz agora
    done = json.loads(pb.done_path(p).read_text("utf-8"))
    assert done == {"pc-a": {"appid": 0, "error": "", "removed": True}}
    assert json.loads((p.data / "plugin-remove.json").read_text("utf-8")) == [{"game_id": "pc-a", "appid": 5}]
