"""Pedido 13/11/2026: "nunca senti o Deck vibrar". No Deck: Ryujinx com enable_rumble false e Dolphin sem motor."""
import json

from dc import controls as C


def test_liga_vibracao_no_ryujinx_e_no_dolphin(tmp_path):
    ryu = tmp_path / ".config/Ryujinx/Config.json"
    ryu.parent.mkdir(parents=True)
    ryu.write_text(json.dumps({"input_config": [
        {"backend": "GamepadSDL2", "rumble": {"strong_rumble": 1, "weak_rumble": 1, "enable_rumble": False}},
        {"backend": "WindowKeyboard"}]}))
    dol = tmp_path / ".var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu"
    dol.mkdir(parents=True)
    (dol / "GCPadNew.ini").write_text("[GCPad1]\nDevice = SDL/0/Steam Virtual Gamepad\nButtons/A = `Button S`\n"
                                      "[GCPad2]\nDevice = XInput2/0/Virtual core pointer\n")
    (dol / "WiimoteNew.ini").write_text("[Wiimote1]\nDevice = SDL/0/Steam Virtual Gamepad\nRumble/Motor = `Motor L`\n")
    log = C.vibracao(tmp_path)
    assert "Ryujinx (Switch): vibração ligada" in log and "Dolphin (GameCube): vibração ligada" in log
    pads = json.loads(ryu.read_text())["input_config"]
    assert pads[0]["rumble"]["enable_rumble"] is True and "rumble" not in pads[1]  # teclado não muda
    gc = (dol / "GCPadNew.ini").read_text()
    assert gc.index("Rumble/Motor = Motor") < gc.index("[GCPad2]") and "Buttons/A = `Button S`" in gc
    assert "Rumble/Motor = `Motor L`" in (dol / "WiimoteNew.ini").read_text()  # escolha do usuário: não mexe
    assert (dol / "GCPadNew.ini.dc-orig").exists()
    assert C.vibracao(tmp_path) == []  # segunda vez: nada a fazer


def test_lichii_switch2(tmp_path):
    p = tmp_path / ".config/eden/qt-config.ini"
    p.parent.mkdir(parents=True)
    p.write_text("[Controls]\nvibration_enabled\\default=false\nvibration_enabled=false\nplayer_0_vibration_enabled=false\n")
    assert C.vibracao(tmp_path) == ["Lichii (Switch 2): vibração ligada"]
    t = p.read_text()
    assert "vibration_enabled=true" in t and "player_0_vibration_enabled=true" in t
