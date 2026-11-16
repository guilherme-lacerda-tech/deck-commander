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
