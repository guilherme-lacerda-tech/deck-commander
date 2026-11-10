"""Monitor de energia de ponta a ponta (laço real, energia e qBittorrent simulados)."""
import json

import pytest

from dc import services
from dc.paths import get_paths
from dc.power import PowerReading


class FakeQ:
    def __init__(self):
        self.ts = [{"hash": "a", "state": "downloading"}]
        self.paused, self.resumed, self.limits = [], [], []

    def torrents(self, *a, **k):
        return self.ts

    def pause(self, hs):
        self.paused += hs
        for t in self.ts:
            if t["hash"] in hs:
                t["state"] = "stoppedDL"

    def resume(self, hs):
        self.resumed += hs
        for t in self.ts:
            if t["hash"] in hs:
                t["state"] = "downloading"

    def set_seeding_limits(self, ratio, minutes):
        self.limits.append((ratio, minutes))


class Stop(Exception):
    pass


def run(monkeypatch, paths, q, readings, between=None):
    it = iter(readings)
    monkeypatch.setattr(services, "read_power", lambda: next(it))
    monkeypatch.setattr(services, "Qbt", lambda: q)
    monkeypatch.setattr(services.ops, "game_running", lambda: True)  # pula fila/qualidade
    n = {"i": 0}

    def sleep(_):
        n["i"] += 1
        if between:
            between(n["i"])
        if n["i"] >= len(readings):
            raise Stop
    monkeypatch.setattr(services.time, "sleep", sleep)
    with pytest.raises(Stop):
        services.power_loop(paths, interval=0)


def test_battery_pauses_new_downloads_and_bateria_sim_resumes(tmp_path, monkeypatch):
    paths = get_paths(tmp_path).ensure()
    (paths.config / "power.json").write_text(json.dumps({"debounce_s": 0}))
    q = FakeQ()
    bat = PowerReading(ac_online=False, battery_pct=80, battery_status="Discharging")

    def between(i):
        if i == 1:  # chegou download novo durante a pausa
            q.ts.append({"hash": "b", "state": "downloading"})
        if i == 2:  # /bateria sim
            (paths.config / "power.json").write_text(json.dumps({"debounce_s": 0, "allow_on_battery": True}))

    run(monkeypatch, paths, q, [bat, bat, bat, bat], between)
    assert q.paused == ["a", "b"] and sorted(q.resumed) == ["a", "b"]
    assert q.limits == [(1.0, 60)]
    st = json.loads((paths.state / "power-state.json").read_text())
    assert st["state"] == "RUN" and not (paths.state / "paused-by-dc.json").exists()


def test_leftover_pause_from_before_reboot_is_resumed_on_charger(tmp_path, monkeypatch):
    paths = get_paths(tmp_path).ensure()
    (paths.state / "paused-by-dc.json").write_text(json.dumps(["a"]))
    q = FakeQ()
    q.ts[0]["state"] = "stoppedDL"
    ac = PowerReading(ac_online=True, battery_pct=90, battery_status="Charging")
    run(monkeypatch, paths, q, [ac])
    assert q.resumed == ["a"] and not (paths.state / "paused-by-dc.json").exists()


def test_bot_bateria_and_power_note(tmp_path, monkeypatch):
    from dc import bot
    paths = get_paths(tmp_path).ensure()
    monkeypatch.setattr(bot.ops, "game_running", lambda: False)
    b = bot.Bot(paths, "T")
    b.cfg["allowed"] = [1]
    b.qbt = type("Q", (), {"torrents": lambda s, *a, **k: [], "add": lambda s, *a: None})()
    (paths.state / "power-state.json").write_text(json.dumps({"state": "PAUSE", "why": "na bateria", "battery": 55}))
    assert "fica pausado" in b.handle(1, 1, "/add ps2 magnet:?xt=urn:btih:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa&dn=Rez")
    assert "55%" in b.handle(1, 1, "/bateria")
    assert "também na bateria" in b.handle(1, 1, "/bateria sim")
    assert json.loads((paths.config / "power.json").read_text())["allow_on_battery"] is True
    assert "só baixa na tomada" in b.handle(1, 1, "/bateria nao")
    (paths.state / "power-state.json").write_text(json.dumps({"state": "RUN", "why": "no carregador"}))
    assert "pausado" not in b.handle(1, 1, "/add ps2 magnet:?xt=urn:btih:dddddddddddddddddddddddddddddddddddddddd&dn=Ico")


def test_bot_warns_once_when_safe_mode_turns_on(tmp_path, monkeypatch):
    from dc import bot, ops
    paths = get_paths(tmp_path).ensure()
    b = bot.Bot(paths, "T")
    sent = []
    b.send = lambda chat, text: sent.append(text)
    b.cfg["notify_chat"] = 9
    b.notify_safe_mode()
    assert sent == []
    ops.safe_mode_flag(paths).write_text("2026-11-07T03:00:00 testes críticos falharam 2x seguidas\n")
    b.notify_safe_mode(); b.notify_safe_mode()
    assert len(sent) == 1 and "testes críticos" in sent[0] and "/sos off" in sent[0]
    ops.safe_mode_flag(paths).unlink()
    b.notify_safe_mode()
    assert len(sent) == 1  # saiu do safe-mode: sem mensagem nova


def test_weekly_tests_safe_mode_only_on_real_failures(tmp_path, monkeypatch):
    paths = get_paths(tmp_path).ensure()
    calls = []
    monkeypatch.setattr(services.ops, "safe_mode_on", lambda *a, **k: calls.append(a[1]))
    codes = iter([4, 4, 1, 4, 1])  # 4 = pytest não conseguiu rodar; 1 = teste falhou

    class R:
        def __init__(self, c):
            self.returncode, self.stdout = c, "x failed" if c == 1 else "ERROR: usage"
    monkeypatch.setattr(services.subprocess, "run", lambda *a, **k: R(next(codes)))
    for _ in range(4):
        services.run_tests(paths, tmp_path)
    assert calls == []  # problemas de infraestrutura não contam; só 1 falha real até aqui
    services.run_tests(paths, tmp_path)
    assert len(calls) == 1  # 2 falhas reais seguidas (ignorando as de infraestrutura)


def test_quality_json_restore_is_byte_identical(tmp_path, monkeypatch):
    from dc import quality
    cfg = tmp_path / "Config.json"
    original = '{\n    "version": 70,\n    "res_scale": 1,\n    "res_scale_custom": 1.0,\n    "x": [1, 2]\n}'
    cfg.write_text(original)
    monkeypatch.setitem(quality.TARGETS, "switch", ("json", [cfg], None, "res_scale"))
    paths = get_paths(tmp_path / "dc").ensure()
    quality.set_override(paths, "g", "switch", "2x")
    quality.apply_for_launch(paths, "g", "switch")
    assert '"res_scale": 2,' in cfg.read_text() and '"res_scale_custom": 1.0' in cfg.read_text()
    quality.restore(paths)
    assert cfg.read_text() == original


def test_user_paused_torrent_is_never_resumed(tmp_path, monkeypatch):
    paths = get_paths(tmp_path).ensure()
    q = FakeQ()
    q.ts[0]["state"] = "stoppedDL"  # o usuário pausou (/pause)
    ac = PowerReading(ac_online=True, battery_pct=90, battery_status="Charging")
    run(monkeypatch, paths, q, [ac, ac])
    assert q.resumed == [] and q.paused == []
