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


def test_netplay_com_erro_nao_impede_o_jogo(tmp_path, monkeypatch):
    """Revisão 11/11/2026: um erro no netplay caía no mesmo bloco do "jogo removido" e o jogo não abria."""
    import json
    import pytest
    from dc import launch, netplay
    from dc.paths import get_paths
    p = get_paths(tmp_path)
    p.ensure()
    rom = tmp_path / "x.cue"
    rom.write_text("FILE")
    (p.data / "launch-map.json").write_text(json.dumps({"psx-x": {"console": "psx", "title": "X", "rom": str(rom)}}))
    monkeypatch.setattr(launch, "get_paths", lambda: p)
    import sys
    monkeypatch.setattr(launch, "build_command", lambda *a: [sys.executable, str(rom)])

    def quebra(*a, **k):
        raise OSError("estado do netplay ilegível")
    monkeypatch.setattr(netplay, "argumentos", quebra)
    abriu = []

    def execvp(prog, cmd):
        abriu.append(cmd)
        raise SystemExit(0)
    monkeypatch.setattr(launch.os, "execvp", execvp)
    import subprocess

    def popen(cmd, *a, **k):
        if cmd[-1] != str(rom):  # energia/TDP etc. (sem SteamOS aqui): falham e são ignorados pelo lançador
            raise OSError("fora do Deck")
        abriu.append(cmd)
        raise SystemExit(0)
    monkeypatch.setattr(subprocess, "Popen", popen)
    with pytest.raises(SystemExit):
        launch.main(["psx-x"])
    assert abriu and abriu[0][-1] == str(rom)
    assert not (p.data / "launch-error.json").exists()
