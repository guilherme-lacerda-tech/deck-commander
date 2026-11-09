"""Presets Bateria / Equilibrado / Qualidade."""
from types import SimpleNamespace

import pytest

from dc import quality, tuning


def test_levels_and_names():
    assert tuning.level_for("ps2", "equilibrado") == 2
    assert tuning.level_for("psx", "qualidade") == 4
    assert tuning.preset_of("ps2", 3) == "qualidade"
    assert tuning.preset_of("switch", 1) == "bateria"
    assert tuning.preset_of("ps2", 5) is None
    with pytest.raises(ValueError):
        tuning.level_for("ps2", "turbo")


def test_apply_console_writes_emulator_ini(tmp_path, monkeypatch):
    ini = tmp_path / "PCSX2.ini"
    ini.write_text("[EmuCore/GS]\nupscale_multiplier = 3\n")
    monkeypatch.setitem(quality.TARGETS, "ps2", ("ini", [ini], "EmuCore/GS", "upscale_multiplier"))
    assert "Equilibrado" in tuning.apply_console("ps2", "equilibrado")
    assert tuning.console_level("ps2") == 2


def test_apply_console_azahar_default_flag(tmp_path, monkeypatch):
    ini = tmp_path / "qt-config.ini"
    ini.write_text("[Renderer]\nresolution_factor=1\nresolution_factor\\default=true\n")
    monkeypatch.setitem(quality.TARGETS, "n3ds", ("ini", [ini], "Renderer", "resolution_factor"))
    tuning.apply_console("n3ds", "qualidade")
    txt = ini.read_text()
    assert "resolution_factor=3" in txt.replace(" ", "") and "resolution_factor\\default=false" in txt.replace(" ", "")


def test_apply_game_sets_override(tmp_path):
    paths = SimpleNamespace(config=tmp_path, state=tmp_path)
    tuning.apply_game(paths, "ps2-sotc", "ps2", "bateria")
    assert quality.get_override(paths, "ps2-sotc") == 1
    tuning.apply_game(paths, "ps2-sotc", "ps2", None)
    assert quality.get_override(paths, "ps2-sotc") is None


def test_unsupported_console():
    assert "ainda não tem presets" in tuning.apply_console("nes", "qualidade")
