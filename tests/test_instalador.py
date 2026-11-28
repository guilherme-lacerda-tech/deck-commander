"""Instalador de arquivo único (tools/instalador/cabecalho.sh)."""
import re
from pathlib import Path

CAB = (Path(__file__).resolve().parents[1] / "tools/instalador/cabecalho.sh").read_text("utf-8")


def test_decky_instalado_como_root():
    """Falha real 16/11/2026 (VM SteamOS + EmuDeck): o install_release.sh do Decky faz 'exec sudo "$0"';
    rodado com 'bash arquivo' sem bit de execução dava 'command not found' e o Decky não era instalado."""
    linha = next(l for l in CAB.splitlines() if "install_release.sh\"" in l and "aviso" in l)
    assert re.search(r"\bsudo bash \"\$tmp_decky/install_release\.sh\"", linha)
    assert 'chmod +x "$tmp_decky/install_release.sh"' in CAB


def test_permissao_flatpak_so_para_os_instalados(monkeypatch):
    """Simulação EmuDeck 16/11/2026: PCSX2/RPCS3/Cemu/Azahar eram AppImage e ganhavam override de Flatpak à toa."""
    import subprocess
    from dc import emulators, setup

    chamadas = []

    def falso(cmd, **kw):
        chamadas.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="org.ppsspp.PPSSPP\n" if cmd[1] == "list" else "")

    monkeypatch.setattr(setup.subprocess, "run", falso)
    log = []
    setup.flatpak_overrides(log)
    apps = {c[-1] for c in chamadas if c[1] == "override"}
    assert apps == {"org.ppsspp.PPSSPP"} and "org.ppsspp.PPSSPP" in emulators.FLATPAK_IDS


def test_instalador_nao_manda_instalar_zip_que_ele_mesmo_instala(monkeypatch, tmp_path):
    """Simulação EmuDeck 16/11/2026: no meio da instalação aparecia 'instale pelo ZIP' e o passo seguinte já instalava."""
    from dc import setup
    monkeypatch.setattr(setup, "PLUGIN_ZIP", tmp_path / "p.zip")
    monkeypatch.setattr(setup, "find_installed_plugin", lambda: None)
    log = []
    monkeypatch.setenv("DC_INSTALADOR", "1")
    setup.setup_plugin(log)
    assert log == [] and (tmp_path / "p.zip").exists()
    monkeypatch.delenv("DC_INSTALADOR")
    setup.setup_plugin(log)
    assert "ZIP" in log[0]
    assert "DC_INSTALADOR=1 ./setup-deck.sh" in CAB


def test_plugin_de_outro_dono_e_detectado_pela_pasta_inteira():
    """28/11/2026: pasta do plugin e plugin.json do root, index.js do usuário: a checagem antiga (só index.js)
    dizia 'em dia' e a atualização automática nunca conseguia trocar o plugin.json."""
    assert 'find "$HOME/homebrew/plugins/deck-commander" ! -user "$(id -u)"' in CAB
    assert '[ ! -w "$HOME/homebrew/plugins/deck-commander/dist/index.js" ]' not in CAB
