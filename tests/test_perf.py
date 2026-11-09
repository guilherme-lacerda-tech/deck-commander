"""Medição de desempenho e bateria por jogo (dc/perf.py)."""
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
    assert "alpha=0.0" in cfg and "autostart_log" in cfg and f"output_folder={log_dir}" in cfg
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


def test_record_session_keeps_history(tmp_path):
    for i in range(25):
        perf.record_session(tmp_path, "ps2-sotc", {"fps_avg": 30.0 + i, "verdict": "liso"})
    h = perf.history(tmp_path, "ps2-sotc")
    assert len(h) == 20 and h[-1]["fps_avg"] == 54.0 and "at" in h[-1]
    assert perf.history(tmp_path, "outro") == []


def test_newest_log(tmp_path):
    import os, time
    a = tmp_path / "a.csv"; a.write_text("x"); b = tmp_path / "b.csv"; b.write_text("y")
    os.utime(a, (time.time() - 100, time.time() - 100))
    assert perf.newest_log(tmp_path, since=time.time() - 50) == b
    assert perf.newest_log(tmp_path, since=time.time() + 50) is None


def test_finish_session_records_and_flags_for_bot(tmp_path):
    import json, time
    from types import SimpleNamespace
    paths = SimpleNamespace(state=tmp_path / "state", data=tmp_path / "data", config=tmp_path / "cfg")
    paths.data.mkdir()
    logs = tmp_path / "logs"; logs.mkdir()
    t0 = time.time() - 600
    (logs / "jogo.csv").write_text(MANGO)
    s = perf.Sampler(hwmon_root=tmp_path / "x", sysfs_root=tmp_path / "y")
    s.bat, s.wh_left = [12.0, 14.0], 39.0
    out = perf.finish_session(paths, "ps2-sotc", "ps2", "Shadow of the Colossus", logs, t0, s)
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
