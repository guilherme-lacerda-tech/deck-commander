"""Auto-ajuste: sobe até travar, volta um passo e fixa."""
from types import SimpleNamespace

from dc import autotune, quality


def _p(tmp_path):
    return SimpleNamespace(config=tmp_path / "c", state=tmp_path / "s")


def test_climbs_until_stutter_then_steps_back(tmp_path):
    p = _p(tmp_path)
    st = autotune.ensure(p, "ps2-sotc", "ps2")
    assert st["level"] == 1 and quality.get_override(p, "ps2-sotc") == 1  # começa num OK (abaixo do equilibrado)
    assert "testando 2x" in autotune.record(p, "ps2-sotc", "ps2", "liso")
    assert quality.get_override(p, "ps2-sotc") == 2
    autotune.record(p, "ps2-sotc", "ps2", "liso")
    assert quality.get_override(p, "ps2-sotc") == 3
    msg = autotune.record(p, "ps2-sotc", "ps2", "oscilando")  # travada leve em 3x
    assert "fixado em 2x" in msg and quality.get_override(p, "ps2-sotc") == 2
    assert autotune.load(p)["ps2-sotc"]["fase"] == "fixo"
    assert autotune.record(p, "ps2-sotc", "ps2", "liso") is None  # fixo: liso não sobe de novo
    assert quality.get_override(p, "ps2-sotc") == 2
    autotune.record(p, "ps2-sotc", "ps2", "travando")  # rede de segurança numa partida real
    assert quality.get_override(p, "ps2-sotc") == 1


def test_stops_at_max(tmp_path):
    p = _p(tmp_path)
    for _ in range(10):
        autotune.record(p, "psx-x", "psx", "liso")
    st = autotune.load(p)["psx-x"]
    assert st["fase"] == "fixo" and st["level"] == autotune.max_level("psx")


def test_manual_freezes(tmp_path):
    p = _p(tmp_path)
    autotune.ensure(p, "gc-x", "gc")
    autotune.set_manual(p, "gc-x", True, "gc")
    assert autotune.record(p, "gc-x", "gc", "liso") is None
    autotune.set_manual(p, "gc-x", False, "gc")
    assert autotune.record(p, "gc-x", "gc", "liso") is not None


def test_unsupported_console_ignored(tmp_path):
    assert autotune.ensure(_p(tmp_path), "nes-x", "nes") is None
    assert autotune.record(_p(tmp_path), "nes-x", "nes", "liso") is None
