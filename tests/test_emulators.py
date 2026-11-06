"""M3 — perfil equilibrado em Dolphin/PPSSPP/RetroArch com read-back; CfgDoc preserva o arquivo."""
from dc import emulators
from dc.adapters.ini import CfgDoc, IniDoc


def test_cfgdoc_preserves_and_appends(tmp_path):
    p = tmp_path / "retroarch.cfg"
    p.write_text('aspect_ratio_index = "22"\nvideo_driver = "gl"\n')
    d = CfgDoc.load(p); d.set("video_driver", "vulkan"); d.set("novo", "1")
    assert d.dump() == b'aspect_ratio_index = "22"\nvideo_driver = "vulkan"\nnovo = "1"\n'


def test_configure_applies_profile_with_read_back(tmp_path, monkeypatch):
    monkeypatch.setattr(emulators, "DOLPHIN_DIR", tmp_path / "dolphin")
    monkeypatch.setattr(emulators, "PPSSPP_INI", tmp_path / "ppsspp/ppsspp.ini")
    monkeypatch.setattr(emulators, "RA_DIR", tmp_path / "ra")
    prof = dict(emulators.PROFILE_EQUILIBRADO)
    prof["retroarch"] = {**prof["retroarch"], "savefile_directory": str(tmp_path / "s"),
                         "savestate_directory": str(tmp_path / "st")}
    monkeypatch.setattr(emulators, "PROFILE_EQUILIBRADO", prof)
    (tmp_path / "dolphin").mkdir()
    (tmp_path / "dolphin/Dolphin.ini").write_text("[Analytics]\nID = x\n")
    (tmp_path / "ra").mkdir()
    (tmp_path / "ra/retroarch.cfg").write_text('video_driver = "gl"\nmenu_driver = "ozone"\n')
    dry = emulators.configure(apply=False)
    assert dry and not (tmp_path / "ppsspp/ppsspp.ini").exists()  # dry-run não grava
    emulators.configure(apply=True)
    assert IniDoc.load(tmp_path / "dolphin/GFX.ini").get("Settings", "InternalResolution") == "2"
    assert IniDoc.load(tmp_path / "dolphin/Dolphin.ini").get("Analytics", "ID") == "x"  # resto intacto
    assert IniDoc.load(tmp_path / "ppsspp/ppsspp.ini").get("General", "CheckForNewVersion") == "False"
    ra = CfgDoc.load(tmp_path / "ra/retroarch.cfg")
    assert ra.get("video_driver") == "vulkan" and ra.get("menu_driver") == "ozone"
    assert emulators.configure(apply=False) == []  # idempotente


def test_detect_finds_emudeck_and_download_layouts(tmp_path):
    import os
    for rel in ("Applications/DuckStation-x64.AppImage", "Downloads/publish/Ryujinx", "Emulation/Lichii/lichii-linux-x86_64-pgo.AppImage"):
        p = tmp_path / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text("x"); os.chmod(p, 0o755)
    found = emulators.detect(tmp_path, check_flatpak=False)
    assert found["psx"][0].endswith("DuckStation-x64.AppImage") and found["psx"][-1] == "{rom}"
    assert found["switch"][0].endswith("publish/Ryujinx".replace("/", os.sep)) or found["switch"][0].endswith("publish/Ryujinx")
    assert found["switch2"][1:3] == ["-f", "-g"]
    assert emulators.detect(tmp_path / "vazio", check_flatpak=False) == {}
