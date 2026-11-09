"""Dolphin: mapeia o controle do Deck só quando ainda está no teclado (padrão de fábrica)."""
from dc import controls

FACTORY_GC = "[GCPad1]\nDevice = XInput2/0/Virtual core pointer\nButtons/A = `X`\n[GCPad2]\nDevice = XInput2/0/Virtual core pointer\n"


def _dir(tmp_path):
    d = tmp_path / ".var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu"
    d.mkdir(parents=True)
    return d


def test_dolphin_factory_config_gets_deck_mapping(tmp_path):
    d = _dir(tmp_path)
    (d / "GCPadNew.ini").write_text(FACTORY_GC)
    log = controls.dolphin_defaults(tmp_path)
    assert len(log) == 2  # GC e Wii (Wii nem existia: é criado)
    gc = (d / "GCPadNew.ini").read_text()
    assert "[GCPad1]\nDevice = SDL/0/Steam Virtual Gamepad\nButtons/A = `Button S`" in gc
    assert gc.count("[GCPad1]") == 1 and "Buttons/A = `X`" not in gc
    assert "[GCPad2]\nDevice = XInput2/0/Virtual core pointer" in gc  # porta 2 intocada
    assert (d / "GCPadNew.ini.dc-orig").read_text() == FACTORY_GC
    wii = (d / "WiimoteNew.ini").read_text()
    assert "Extension = Nunchuk" in wii and "Source = 1" in wii
    assert all(c.ok for c in controls.check(tmp_path) if "Dolphin" in c.emulator)
    assert controls.dolphin_defaults(tmp_path) == []  # idempotente


def test_dolphin_user_mapping_is_respected(tmp_path):
    d = _dir(tmp_path)
    mine = "[GCPad1]\nDevice = evdev/0/Meu Controle\nButtons/A = `BTN_SOUTH`\n"
    (d / "GCPadNew.ini").write_text(mine)
    (d / "WiimoteNew.ini").write_text("[Wiimote1]\nDevice = SDL/0/Outro\n")
    assert controls.dolphin_defaults(tmp_path) == []
    assert (d / "GCPadNew.ini").read_text() == mine


def test_dolphin_not_installed_does_nothing(tmp_path):
    assert controls.dolphin_defaults(tmp_path) == []


def test_melonds_mapping_written_once_and_respects_user(tmp_path):
    import tomllib
    (tmp_path / ".var/app/net.kuribo64.melonDS").mkdir(parents=True)
    assert controls.melonds_defaults(tmp_path)
    cfg = tomllib.loads(controls.melonds_path(tmp_path).read_text())
    j = cfg["Instance0"]["Joystick"]
    assert j["A"] == 0 and j["Start"] == 7 and j["Up"] & 0x100 and j["Up"] & 0x10000 and cfg["Instance0"]["JoystickID"] == 0
    assert controls.melonds_defaults(tmp_path) == []  # já mapeado: não mexe
    assert [c for c in controls.check(tmp_path) if "melonDS" in c.emulator][0].ok
    # configuração existente do usuário (sem controle) é preservada
    p = controls.melonds_path(tmp_path)
    p.write_text('[Instance0]\nJoystickID = 1\nAudioVolume = 200\n')
    controls.melonds_defaults(tmp_path)
    cfg = tomllib.loads(p.read_text())
    assert cfg["Instance0"]["JoystickID"] == 1 and cfg["Instance0"]["AudioVolume"] == 200 and "Joystick" in cfg["Instance0"]
