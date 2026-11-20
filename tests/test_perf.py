"""Medição de desempenho e bateria por jogo (dc/perf.py)."""
import json

from pathlib import Path

from dc import perf

MANGO = """os,cpu,gpu,ram,kernel,driver,cpuscheduler
SteamOS,AMD Custom APU 0405,AMD Custom GPU 0405,16,6.5,Mesa,
fps,frametime,cpu_load,gpu_load,cpu_temp,gpu_temp,gpu_core_clock,gpu_mem_clock,gpu_vram_used,gpu_power,ram_used,swap_used,process_rss,elapsed
60.0,16.6,40,70,60,55,1600,5500,1.1,9.5,5.0,0,1.2,1000000
60.0,16.6,40,70,61,55,1600,5500,1.1,9.5,5.0,0,1.2,2000000
30.0,33.3,45,99,70,60,1600,5500,1.1,12.0,5.0,0,1.2,3000000
60.0,16.6,40,70,62,55,1600,5500,1.1,9.5,5.0,0,1.2,4000000
"""


def test_parse_mangohud(tmp_path):
    p = tmp_path / "log.csv"
    p.write_text(MANGO)
    s = perf.parse_mangohud(p)
    assert s["samples"] == 4
    assert s["fps_avg"] == 52.5
    assert s["fps_low"] == 30.0          # pior amostra (1% low com poucas amostras = mínimo)
    assert s["cpu_temp_max"] == 70
    assert s["gpu_load_avg"] == 77.25
    assert s["slow_share"] == 0.25       # fração de amostras abaixo de 90% do alvo (alvo 60)


def test_parse_mangohud_missing_or_empty(tmp_path):
    assert perf.parse_mangohud(tmp_path / "nao-existe.csv") is None
    (tmp_path / "v.csv").write_text("fps,frametime\n")
    assert perf.parse_mangohud(tmp_path / "v.csv") is None


def _mango_many(fps_values):
    head = "fps,frametime,cpu_load,gpu_load,cpu_temp,gpu_temp,elapsed\n"
    rows = [f"{fps},16.6,40,70,60,55,{(i + 1) * 250_000_000}" for i, fps in enumerate(fps_values)]
    return head + "\n".join(rows) + "\n"


def test_live_stats_requires_time_and_detects_sustained_slowdown(tmp_path):
    p = tmp_path / "growing.csv"
    p.write_text(_mango_many([60.0] * 20 + [36.0] * 80))
    s = perf.live_stats(p)
    assert s["samples"] == 48 and s["target"] == 50
    assert s["fps_avg"] == 36.0 and s["slow_share"] == 1.0
    # Queda que ainda mantém meta de 60 é travamento, e não um jogo legítimo de 30 FPS.
    p.write_text(_mango_many([60.0] * 40 + [36.0] * 40))
    s = perf.live_stats(p)
    assert s["target"] == 60.0 and s["slow_share"] == 40 / 48


def test_live_stats_ignores_csv_created_before_its_header(tmp_path):
    """MangoHud cria o arquivo antes de terminar de escrever o cabeçalho de dados."""
    p = tmp_path / "starting.csv"
    p.write_text("os,cpu,gpu\nSteamOS,AMD,AMD\n")
    assert perf.live_stats(p) is None


def test_live_monitor_alerts_once_and_exposes_one_notification(tmp_path):
    from types import SimpleNamespace
    paths = SimpleNamespace(data=tmp_path / "data")
    paths.data.mkdir()
    logs = tmp_path / "logs"; logs.mkdir()
    (logs / "game.csv").write_text(_mango_many([60.0] * 25 + [36.0] * 75))
    calls = []
    monitor = perf.LiveMonitor(paths, "ps2-dmc3", "ps2", "Devil May Cry 3", logs, 0,
                               on_stutter=lambda stats: calls.append(stats) or "TDP elevado agora para 15 W")
    data = monitor.check()
    assert data["verdict"] == "travando" and data["next_level"] is None and len(calls) == 1
    assert monitor.adjusted is True
    assert "Ação durante a partida" in data["message"] and "TDP elevado" in data["message"]
    assert monitor.check() is None
    assert "Devil May Cry 3" in perf.live_message(paths)
    assert perf.live_message(paths) is None


def test_live_monitor_keeps_the_known_target_after_a_sustained_drop(tmp_path):
    """42 FPS é 70% de uma partida que vinha a 60; não pode virar meta fictícia de 50."""
    from types import SimpleNamespace
    paths = SimpleNamespace(data=tmp_path / "data")
    paths.data.mkdir()
    logs = tmp_path / "logs"; logs.mkdir()
    csv = logs / "game.csv"
    monitor = perf.LiveMonitor(paths, "ps2-dmc3", "ps2", "Devil May Cry 3", logs, 0)
    csv.write_text(_mango_many([60.0] * 80))
    assert monitor.check() is None
    csv.write_text(_mango_many([60.0] * 80 + [42.0] * 80))
    data = monitor.check()
    assert data["target"] == 60 and data["fps_avg"] == 42 and data["verdict"] == "travando"


def test_live_monitor_reacts_before_the_game_reaches_70_percent(tmp_path):
    """Uma queda sustentada para 83% de 60 já aciona a correção ao vivo; não espera 70%."""
    from types import SimpleNamespace
    paths = SimpleNamespace(data=tmp_path / "data")
    paths.data.mkdir()
    logs = tmp_path / "logs"; logs.mkdir()
    csv = logs / "game.csv"
    calls = []
    monitor = perf.LiveMonitor(paths, "ps2-dmc3", "ps2", "Devil May Cry 3", logs, 0,
                               on_stutter=lambda s: calls.append(s) or "TDP já estava no máximo")
    csv.write_text(_mango_many([60.0] * 80))
    assert monitor.check() is None
    csv.write_text(_mango_many([60.0] * 80 + [50.0] * 48))
    data = monitor.check()
    assert data and data["target"] == 60 and data["fps_avg"] == 50
    assert len(calls) == 1


def test_live_monitor_steps_up_then_only_steps_down_after_long_stability(tmp_path):
    """Controlador adaptativo: sem salto ao máximo, sem devolver energia na primeira janela lisa."""
    from types import SimpleNamespace
    now = [0.0]
    paths = SimpleNamespace(data=tmp_path / "data")
    paths.data.mkdir()
    logs = tmp_path / "logs"; logs.mkdir()
    csv = logs / "game.csv"
    events = []
    monitor = perf.LiveMonitor(paths, "ps2-dmc3", "ps2", "Devil May Cry 3", logs, 0,
                               on_stutter=lambda s: events.append("up") or "TDP elevado de 12 para 13 W",
                               on_stable=lambda s: events.append("down") or "TDP reduzido de 13 para 12 W",
                               adjustment_cooldown=20, recovery_seconds=300, clock=lambda: now[0])
    csv.write_text(_mango_many([60.0] * 80))
    assert monitor.check() is None  # aprende a meta
    csv.write_text(_mango_many([60.0] * 80 + [42.0] * 48))
    assert monitor.check()["action"] == "TDP elevado de 12 para 13 W"
    now[0] = 10
    assert monitor.check() is None  # cooldown: não sobe de novo no mesmo instante
    csv.write_text(_mango_many([60.0] * 200))
    now[0] = 30
    assert monitor.check() is None  # primeira janela boa só inicia o relógio de estabilidade
    now[0] = 329
    assert monitor.check() is None
    now[0] = 330
    assert monitor.check()["action"] == "TDP reduzido de 13 para 12 W"
    assert events == ["up", "down"]


def test_live_monitor_reports_missing_mangohud_instead_of_staying_silent(tmp_path):
    """Sem CSV não existe detecção; o painel e o bot precisam poder dizer isso."""
    from types import SimpleNamespace
    import time
    paths = SimpleNamespace(data=tmp_path / "data")
    paths.data.mkdir()
    logs = tmp_path / "logs"; logs.mkdir()
    monitor = perf.LiveMonitor(paths, "ps2-dmc3", "ps2", "Devil May Cry 3", logs, time.time() - 46)
    data = monitor.check()
    assert data["verdict"] == "indisponivel" and "MangoHud" in data["message"]
    assert monitor.check() is None
    (logs / "game.csv").write_text(_mango_many([60.0] * 80))
    assert monitor.check() is None and perf.live_status(paths) is None


def _bat(root: Path, **vals):
    d = root / "BAT1"
    d.mkdir(parents=True)
    (d / "type").write_text("Battery\n")
    for k, v in vals.items():
        (d / k).write_text(f"{v}\n")
    return root


def test_battery_watts_from_current_and_voltage(tmp_path):
    root = _bat(tmp_path, current_now=1_500_000, voltage_now=8_000_000, status="Discharging",
                charge_now=4_000_000)
    b = perf.battery(root)
    assert b["watts"] == 12.0
    assert b["discharging"] is True
    assert b["wh_left"] == 32.0


def test_battery_power_now_preferred(tmp_path):
    root = _bat(tmp_path, power_now=9_000_000, status="Charging", energy_now=20_000_000)
    b = perf.battery(root)
    assert b["watts"] == 9.0 and b["discharging"] is False and b["wh_left"] == 20.0


def test_battery_absent(tmp_path):
    assert perf.battery(tmp_path) is None


def test_summary_and_verdict():
    s = perf.summary({"fps_avg": 58.0, "fps_low": 50.0, "slow_share": 0.02}, [12.0, 14.0, 13.0], wh_left=40.0, target=60)
    assert s["watts_avg"] == 13.0
    assert s["hours_left"] == round(40 / 13, 1)
    assert s["verdict"] == "liso"
    assert perf.verdict(40.0, 20.0, 0.4, 60) == "travando"
    assert perf.verdict(30.0, 29.0, 0.0, 30) == "liso"
    assert perf.verdict(55.0, 45.0, 0.12, 60) == "oscilando"


def test_wrap_command_flatpak_gets_mangohud_env(tmp_path):
    cmd = ["/usr/bin/flatpak", "run", "net.pcsx2.PCSX2", "-fullscreen", "--", "/r/jogo.iso"]
    out, log_dir = perf.wrap_command(cmd, home=tmp_path)
    assert out[:2] == ["/usr/bin/flatpak", "run"]
    assert "--env=MANGOHUD=1" in out
    cfg = next(a for a in out if a.startswith("--env=MANGOHUD_CONFIG="))
    assert "alpha=0.0" in cfg and "autostart_log" in cfg and "log_duration=14400" in cfg and f"output_folder={log_dir}" in cfg
    assert log_dir == tmp_path / ".var/app/net.pcsx2.PCSX2/dc-perf"
    assert out[-4:] == ["net.pcsx2.PCSX2", "-fullscreen", "--", "/r/jogo.iso"]


def test_wrap_command_native_uses_env(tmp_path):
    cmd = ["/home/deck/Applications/DuckStation-x64.AppImage", "-batch", "/r/j.cue"]
    out, log_dir = perf.wrap_command(cmd, home=tmp_path)
    assert out[0] == "/usr/bin/env" and "MANGOHUD=1" in out and out[-3:] == cmd
    assert log_dir == tmp_path / ".local/share/deck-commander/perf-logs"


def test_apu_watts(tmp_path):
    h = tmp_path / "hwmon6"
    h.mkdir()
    (h / "name").write_text("amdgpu\n")
    (h / "power1_average").write_text("9500000\n")
    assert perf.apu_watts(tmp_path) == 9.5
    assert perf.apu_watts(tmp_path / "nada") is None


def test_audio_xruns_reads_counters_without_audio_capture():
    from types import SimpleNamespace
    txt = "S ID QUANT RATE WAIT BUSY W/Q B/Q ERR FORMAT NAME\nR 80 256 48000 1us 1us 0 0 7 S16LE 2 48000 melonDS\n"
    got = perf.audio_xruns(lambda *a, **k: SimpleNamespace(returncode=0, stdout=txt))
    assert got == {"melonDS": 7}


def test_diagnostics_sampler_writes_sensor_and_audio_metadata(tmp_path, monkeypatch):
    from types import SimpleNamespace
    paths = SimpleNamespace(logs=tmp_path / "logs")
    ticks = [0.0]
    monkeypatch.setattr(perf, "apu_watts", lambda: 11.5)
    monkeypatch.setattr(perf, "battery", lambda: {"watts": 14.0, "wh_left": 30.0, "discharging": True})
    monkeypatch.setattr(perf, "audio_xruns", lambda: {"PCSX2": 3})
    d = perf.DiagnosticsSampler(paths, "ps2-dmc3", "ps2", "DMC3", tdp_ctl=SimpleNamespace(ler=lambda: 13),
                                audio_every=1, clock=lambda: ticks[0])
    d.start()
    ticks[0] = 2
    sample = d.sample()
    d.stop()
    rows = [json.loads(x) for x in d.path.read_text("utf-8").splitlines()]
    assert sample["tdp_watts"] == 13 and sample["pipewire_err"] == {"PCSX2": 3}
    assert rows[0]["audio_content_recorded"] is False and rows[-1]["event"] == "fim"


def test_record_session_keeps_history(tmp_path):
    for i in range(25):
        perf.record_session(tmp_path, "ps2-sotc", {"fps_avg": 30.0 + i, "verdict": "liso"})
    h = perf.history(tmp_path, "ps2-sotc")
    assert len(h) == 20 and h[-1]["fps_avg"] == 54.0 and "at" in h[-1]
    assert perf.history(tmp_path, "outro") == []


def test_newest_log(tmp_path):
    import os
    import time
    a = tmp_path / "a.csv"; a.write_text("x"); b = tmp_path / "b.csv"; b.write_text("y")
    os.utime(a, (time.time() - 100, time.time() - 100))
    assert perf.newest_log(tmp_path, since=time.time() - 50) == b
    assert perf.newest_log(tmp_path, since=time.time() + 50) is None


def test_finish_session_records_and_flags_for_bot(tmp_path):
    import json
    import time
    from types import SimpleNamespace
    paths = SimpleNamespace(state=tmp_path / "state", data=tmp_path / "data", config=tmp_path / "cfg")
    paths.data.mkdir()
    logs = tmp_path / "logs"; logs.mkdir()
    t0 = time.time() - 600
    (logs / "jogo.csv").write_text(MANGO)
    s = perf.Sampler(hwmon_root=tmp_path / "x", sysfs_root=tmp_path / "y")
    s.bat, s.wh_left = [12.0, 14.0], 39.0
    out = perf.finish_session(paths, "ps2-sotc", "ps2", "Shadow of the Colossus", logs, t0, s)
    assert out  # o resumo da partida volta para o lançador registrar
    h = perf.history(paths.state, "ps2-sotc")[-1]
    assert h["fps_avg"] == 52.5 and h["watts_avg"] == 13.0 and h["hours_left"] == 3.0 and h["verdict"] == "travando"
    assert h["fonte_watts"] == "bateria" and h["minutos"] == 10.0
    last = json.loads((paths.data / "perf-last.json").read_text("utf-8"))
    assert last["notified"] is False and last["game_id"] == "ps2-sotc"
    s2 = perf.Sampler(hwmon_root=tmp_path / "x", sysfs_root=tmp_path / "y"); s2.apu = [8.0]
    perf.finish_session(paths, "ps2-sotc", "ps2", "SotC", logs, t0, s2)
    assert "hours_left" not in perf.history(paths.state, "ps2-sotc")[-1]
    assert "não registrada" in perf.finish_session(paths, "g", "ps2", "t", logs, time.time() - 5, s2)


def test_enabled_default_and_off(tmp_path):
    from types import SimpleNamespace
    p = SimpleNamespace(config=tmp_path)
    assert perf.enabled(p) is True
    (tmp_path / "desempenho.json").write_text('{"medir": false}')
    assert perf.enabled(p) is False


def test_pending_message_once(tmp_path):
    import json
    from types import SimpleNamespace
    p = SimpleNamespace(data=tmp_path)
    (tmp_path / "perf-last.json").write_text(json.dumps({"title": "SotC", "minutos": 10, "fps_avg": 27.0, "fps_low": 18.0,
        "target": 30, "verdict": "travando", "watts_avg": 15.2, "fonte_watts": "bateria", "hours_left": 2.6, "notified": False}))
    m = perf.pending_message(p)
    assert "SotC" in m and "27 fps" in m and "15.2 W" in m and "2.6 h" in m and "/qualidade" in m
    assert perf.pending_message(p) is None


def test_bench_gameid():
    from dc import bench
    assert bench.steam_gameid(-1732342533) == (((-1732342533) & 0xFFFFFFFF) << 32) | 0x02000000
