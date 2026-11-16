"""Falha real 15/11/2026 (Deck com EmuDeck): o PS2 abria um PCSX2 Flatpak novo e vazio ("primeira vez", pedindo BIOS
e jogos) em vez do PCSX2 do EmuDeck. Agora: o emulador que já existe vem primeiro, o usuário escolhe no painel, o
Flatpak dispensável não é instalado e o que o Deck Commander instala já sai pronto."""
import json
import os

from dc import emulators as E
from dc import setup
from dc.paths import get_paths


def _exe(home, rel):
    p = home / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x")
    os.chmod(p, 0o755)
    return p


def test_pcsx2_do_emudeck_vem_antes_do_flatpak(tmp_path, monkeypatch):
    _exe(tmp_path, "Applications/pcsx2-Qt.AppImage")
    monkeypatch.setattr(E, "_flatpak_installed", lambda app: True)
    ops = E.candidatos("ps2", tmp_path)
    assert [o["nome"] for o in ops] == ["PCSX2 (do EmuDeck / ~/Applications)", "PCSX2 (Flatpak)"]
    assert ops[0]["cmd"][0].endswith("pcsx2-Qt.AppImage") and ops[0]["cmd"][-1] == "{rom}"
    assert E.detect(tmp_path)["ps2"] == ops[0]["cmd"]


def test_switch_lista_varios_emuladores(tmp_path, monkeypatch):
    _exe(tmp_path, "Applications/publish/Ryujinx")
    _exe(tmp_path, "Applications/citron.AppImage")
    _exe(tmp_path, "Applications/Eden-Linux.AppImage")
    monkeypatch.setattr(E, "_flatpak_installed", lambda app: False)
    nomes = [o["nome"] for o in E.candidatos("switch", tmp_path)]
    assert nomes == ["Ryujinx", "Citron", "Eden"]
    assert E.candidatos("switch", tmp_path)[1]["cmd"][1:3] == ["-f", "-g"]


def test_flatpak_dispensavel_quando_o_console_ja_tem_emulador(tmp_path):
    _exe(tmp_path, "Applications/pcsx2-Qt.AppImage")
    dis = E.flatpaks_dispensaveis(tmp_path)
    assert "net.pcsx2.PCSX2" in dis
    assert "org.DolphinEmu.dolphin-emu" not in dis  # GameCube/Wii sem emulador fora do Flatpak


def test_escolher_grava_e_o_painel_mostra(tmp_path, monkeypatch):
    P = get_paths(tmp_path / "dc").ensure()
    _exe(tmp_path, "Applications/publish/Ryujinx")
    _exe(tmp_path, "Applications/citron.AppImage")
    monkeypatch.setattr(E, "_flatpak_installed", lambda app: False)
    sw = next(e for e in E.escolhas(P, tmp_path) if e["console"] == "switch")
    assert sw["atual"] == "Ryujinx" and sw["opcoes"] == ["Ryujinx", "Citron"]
    assert "Citron" in E.escolher(P, "switch", "Citron", tmp_path)
    cfg = json.loads((P.config / "emulators.json").read_text())
    assert cfg["switch"][0].endswith("citron.AppImage")
    assert next(e for e in E.escolhas(P, tmp_path) if e["console"] == "switch")["atual"] == "Citron"
    try:
        E.escolher(P, "switch", "Yuzu", tmp_path)
        raise AssertionError("aceitou emulador que não está instalado")
    except ValueError:
        pass


def test_configuracao_inicial_sem_assistente_e_sem_tocar_no_que_existe(tmp_path):
    (tmp_path / "Emulation/bios").mkdir(parents=True)
    duck = tmp_path / ".local/share/duckstation/settings.ini"
    duck.parent.mkdir(parents=True)
    duck.write_text("[Main]\nmeu = sim\n")  # já existia (do usuário/EmuDeck): intocado
    feitos = setup.preparar_primeira_vez(tmp_path, presente=lambda nome, home: True)
    assert feitos == ["PCSX2"] and duck.read_text() == "[Main]\nmeu = sim\n"
    ini = (tmp_path / ".var/app/net.pcsx2.PCSX2/config/PCSX2/inis/PCSX2.ini").read_text()
    assert "SetupWizardIncomplete = false" in ini and f"Bios = {tmp_path / 'Emulation/bios'}" in ini
    assert "Cross = SDL-0/FaceSouth" in ini and "Start = SDL-0/Start" in ini
    assert setup.preparar_primeira_vez(tmp_path, presente=lambda nome, home: True) == []  # idempotente


def test_nao_prepara_emulador_que_nao_esta_instalado(tmp_path):
    """Num Deck com o PCSX2 do EmuDeck, o PCSX2 Flatpak nem é instalado: não cria a pasta dele."""
    assert setup.preparar_primeira_vez(tmp_path, presente=lambda nome, home: False) == []
    assert not (tmp_path / ".var/app/net.pcsx2.PCSX2").exists()


def test_instalacao_nao_mexe_na_configuracao_dos_emuladores_do_emudeck(tmp_path, monkeypatch):
    """Falha real 15/11/2026: a instalação ajustava Dolphin/PPSSPP/RetroArch/melonDS — os mesmos do EmuDeck."""
    from dc import biblioteca, controls
    P = get_paths(tmp_path / "dc").ensure()
    monkeypatch.setattr(biblioteca, "outro_gerenciador", lambda home=None: "EmuDeck")

    def proibido(*a, **k):
        raise AssertionError("mexeu na configuração do EmuDeck")
    for alvo in (E, ):
        monkeypatch.setattr(alvo, "configure", proibido)
    for f in ("switch_layout", "dolphin_defaults", "melonds_defaults", "vibracao"):
        monkeypatch.setattr(controls, f, proibido)
    monkeypatch.setattr(setup.subprocess, "run", lambda *a, **k: type("R", (), {"returncode": 0, "stdout": "",
                                                                             "stderr": ""})())
    monkeypatch.setattr(setup, "preparar_primeira_vez", lambda **k: [])
    monkeypatch.setattr(setup, "write_emulators_json", lambda paths, log: None)
    monkeypatch.setattr(setup, "write_units", lambda log: None)
    log = setup.setup(P, ["M3"], downloads=False)
    assert any("EmuDeck neste Deck" in ln for ln in log)
