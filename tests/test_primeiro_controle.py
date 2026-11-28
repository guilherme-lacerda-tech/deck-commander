import xml.etree.ElementTree as ET

import pytest

from dc.emulators.setup_controls import LAYOUTS, prepare


@pytest.mark.parametrize("app", LAYOUTS)
def test_primeiro_uso_reabertura_e_perfil_manual(tmp_path, app):
    dmi = tmp_path / "dmi"
    dmi.mkdir()
    (dmi / "sys_vendor").write_text("Valve")
    (dmi / "board_name").write_text("Jupiter")
    args = ["/usr/bin/flatpak", "run", app, "game"]
    target = prepare(args, tmp_path, dmi)
    assert target and target.is_file()
    if app == "info.cemu.Cemu":
        assert ET.parse(target).findtext("controller/api") == "SDLController"
    elif app == "net.rpcs3.RPCS3":
        assert "Handler: Evdev" in target.read_text()
    else:
        assert "[Controls]" in target.read_text() and "nand_directory" not in target.read_text()
    assert prepare(args, tmp_path, dmi) is None
    target.write_bytes(b"perfil manual")
    assert prepare(args, tmp_path, dmi) is None and target.read_bytes() == b"perfil manual"
