"""DuckStation a 60% da velocidade no Deck: a camada WSI do gamescope segurava em 30 FPS (medido 11/11/2026)."""
from dc.launch import sem_wsi_do_gamescope


def test_duckstation_sem_wsi():
    c = sem_wsi_do_gamescope(["/home/deck/Applications/DuckStation-x64.AppImage", "-fullscreen", "--", "/x.cue"])
    assert c[:2] == ["/usr/bin/env", "ENABLE_GAMESCOPE_WSI=0"] and c[-1] == "/x.cue"
    assert sem_wsi_do_gamescope(c) == c  # não duplica
    env = ["/usr/bin/env", "ENABLE_GAMESCOPE_WSI=0", "/a/DuckStation-x64.AppImage"]
    assert sem_wsi_do_gamescope(env) == env


def test_outros_emuladores_ficam_iguais():
    pcsx2 = ["/usr/bin/flatpak", "run", "net.pcsx2.PCSX2", "/x.iso"]
    assert sem_wsi_do_gamescope(pcsx2) == pcsx2
