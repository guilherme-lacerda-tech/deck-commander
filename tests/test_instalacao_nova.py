"""Instalação para outra pessoa: PS1 e Switch abrem mesmo sem os emuladores que este Deck já tinha."""
from dc import emulators, setup


def test_psx_falls_back_to_retroarch_swanstation(tmp_path, monkeypatch):
    cores = tmp_path / "cores"; cores.mkdir()
    (cores / "swanstation_libretro.so").write_bytes(b"x")
    monkeypatch.setattr(emulators, "RA_CORES", cores)
    got = emulators.detect(tmp_path, check_flatpak=False)
    assert got["psx"][:3] == [emulators.FLATPAK, "run", "org.libretro.RetroArch"]
    assert str(cores / "swanstation_libretro.so") in got["psx"]


def test_psx_fallback_needs_the_core(tmp_path, monkeypatch):
    monkeypatch.setattr(emulators, "RA_CORES", tmp_path / "vazio")
    assert "psx" not in emulators.detect(tmp_path, check_flatpak=False)
    assert "swanstation_libretro.so" in emulators.RA_CORE_FILES


def test_ryujinx_flatpak_only_when_switch_emulator_missing(monkeypatch):
    calls = []

    class R:
        stdout, returncode, stderr = "", 0, ""

    def run(cmd, **k):
        calls.append(cmd)
        return R()
    monkeypatch.setattr(setup.subprocess, "run", run)
    monkeypatch.setattr(emulators, "detect", lambda **k: {})
    setup.install_flatpaks([])
    assert "io.github.ryubing.Ryujinx" in calls[-1]
    calls.clear()
    monkeypatch.setattr(emulators, "detect", lambda **k: {"switch": ["/home/x/Ryujinx", "{rom}"]})
    setup.install_flatpaks([])
    assert "io.github.ryubing.Ryujinx" not in calls[-1]
