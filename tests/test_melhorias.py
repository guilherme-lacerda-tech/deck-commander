from dc import melhorias as M

PCSX2 = "[UI]\nX = 1\n\n[EmuCore]\nEnableWideScreenPatches = false\nEnableNoInterlacingPatches = false\nOutro = 3\n\n[Pad1]\nType = DualShock2\n"
DUCK = "[GPU]\nRenderer = Vulkan\nWidescreenHack = false\n\n[Display]\nAspectRatio = Auto (Game Native)\n"


def test_ini_basico():
    assert M.ler_ini_valor(PCSX2, "emucore", "enablewidescreenpatches") == "false"
    novo = M.trocar_ini_valor(PCSX2, "EmuCore", "EnableWideScreenPatches", "true")
    assert "EnableWideScreenPatches = true" in novo and novo.replace("= true", "= false", 1) == PCSX2
    assert "Nova = 1" in M.trocar_ini_valor(PCSX2, "Pad1", "Nova", "1")
    assert M.trocar_ini_valor("[A]\nx = 1\n", "B", "y", "2").rstrip().endswith("[B]\ny = 2")


def test_definir_e_estado(tmp_path):
    f = tmp_path / ".var/app/net.pcsx2.PCSX2/config/PCSX2/inis/PCSX2.ini"; f.parent.mkdir(parents=True); f.write_text(PCSX2)
    d = tmp_path / ".local/share/duckstation/settings.ini"; d.parent.mkdir(parents=True); d.write_text(DUCK)
    est = {e["emulador"]: e["opcoes"] for e in M.estado(tmp_path)}
    assert est["pcsx2"] == {"widescreen": False, "sem_entrelacamento": False} and est["duckstation"]["widescreen"] is False
    M.definir(tmp_path, "duckstation", "widescreen", True)
    t = d.read_text()
    assert "WidescreenHack = true" in t and "AspectRatio = 16:9" in t and "Renderer = Vulkan" in t
    assert (d.parent / "settings.ini.antes-deck-commander").read_text() == DUCK
    assert {e["emulador"]: e["opcoes"] for e in M.estado(tmp_path)}["duckstation"]["widescreen"] is True
    import pytest
    with pytest.raises(ValueError):
        M.definir(tmp_path, "dolphin", "widescreen", True)  # arquivo ausente
