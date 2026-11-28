"""Executa a suíte sem acesso de escrita à instalação ou à sessão do jogador.

Requer bubblewrap no Linux. Ausência ou falha do isolamento é erro de
infraestrutura: nunca executa pytest diretamente como alternativa.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def run(repo: Path, python: Path, *, stop_first: bool = False,
        rodar=subprocess.run) -> subprocess.CompletedProcess:
    """O único filesystem gravável da suíte é temporário e morre com o processo.

Nem HOME/DC_ROOT herdados nem caminhos absolutos permitem alterar saves,
serviços, atalhos ou o launcher real. /run e os namespaces de processos,
dispositivos e rede impedem falar com Steam, systemd e emuladores do host.
    """
    bwrap = shutil.which("bwrap")
    if not bwrap:
        return subprocess.CompletedProcess([], 2, "isolamento indisponível: bubblewrap (bwrap) ausente\n", "")
    repo, python = Path(repo).resolve(), Path(python).absolute()
    if not python.is_file():
        return subprocess.CompletedProcess([], 2, "ambiente de testes ausente\n", "")
    # Preserve o caminho do link bin/python: resolve() perderia o pyvenv.cfg.
    venv = python.parent.parent
    if not (venv / "pyvenv.cfg").is_file():
        return subprocess.CompletedProcess([], 2, "ambiente de testes deve ser um venv dedicado\n", "")
    cmd = [bwrap, "--die-with-parent", "--new-session", "--unshare-all", "--cap-drop", "ALL",
           "--ro-bind", "/", "/", "--tmpfs", "/home", "--tmpfs", "/root",
           "--tmpfs", "/run", "--tmpfs", "/tmp", "--dev", "/dev", "--proc", "/proc",
           "--ro-bind", str(repo), "/tmp/source", "--ro-bind", str(venv), "/tmp/venv",
           "--dir", "/tmp/home", "--perms", "0700", "--dir", "/tmp/runtime",
           "--chdir", "/tmp/source", "--clearenv"]
    env = {
        "PATH": "/tmp/venv/bin:/usr/bin:/bin", "HOME": "/tmp/home", "USER": "dc-test", "LOGNAME": "dc-test",
        "LANG": "C.UTF-8", "TMPDIR": "/tmp", "DC_ROOT": "/tmp/home", "DC_TEST_SANDBOX": "1",
        "DC_BACKUP_DIR": "/tmp/home/Backups/DeckCommander",
        "XDG_CONFIG_HOME": "/tmp/home/.config", "XDG_DATA_HOME": "/tmp/home/.local/share",
        "XDG_STATE_HOME": "/tmp/home/.local/state", "XDG_CACHE_HOME": "/tmp/home/.cache",
        "XDG_RUNTIME_DIR": "/tmp/runtime", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
    }
    for key, value in env.items():
        cmd.extend(["--setenv", key, value])
    started = "DECK_COMMANDER_ISOLATED_PYTEST_STARTED"
    bootstrap = ("import sys; import pytest; "
                 f"print({started!r}, file=sys.stderr, flush=True); sys.exit(pytest.main(sys.argv[1:]))")
    cmd.extend(["--", f"/tmp/venv/bin/{python.name}", "-c", bootstrap, "-q", "-p", "no:cacheprovider"])
    if stop_first:
        cmd.append("-x")
    cmd.append("tests")
    try:
        result = rodar(cmd, cwd=str(repo), capture_output=True, text=True, timeout=1800, check=False)
        # bwrap e importação de pytest podem sair com 1: isso é infraestrutura,
        # nunca uma falha de teste que deva ligar safe-mode após duas rodadas.
        began = started in result.stderr.splitlines()
        result.stderr = "\n".join(line for line in result.stderr.splitlines() if line != started)
        if not began:
            result.returncode = 2
        return result
    except (OSError, subprocess.SubprocessError) as exc:
        return subprocess.CompletedProcess(cmd, 2, f"executor isolado falhou: {type(exc).__name__}\n", "")
