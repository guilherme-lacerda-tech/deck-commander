"""Atualização e timer jamais podem executar a suíte dentro da sessão real."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from dc import test_runner


def _venv(tmp_path):
    root = tmp_path / "venv"
    (root / "bin").mkdir(parents=True)
    (root / "pyvenv.cfg").write_text("home = /usr/bin\n")
    py = root / "bin/python"
    py.touch()
    return py


def test_missing_sandbox_never_executes_pytest(tmp_path, monkeypatch):
    monkeypatch.setattr(test_runner.shutil, "which", lambda name: None)
    called = []
    result = test_runner.run(tmp_path, _venv(tmp_path), rodar=lambda *a, **k: called.append(a))
    assert result.returncode == 2 and "bubblewrap" in result.stdout
    assert called == []


def test_sandbox_command_has_private_home_no_host_environment(tmp_path, monkeypatch):
    monkeypatch.setattr(test_runner.shutil, "which", lambda name: "/usr/bin/bwrap")
    captured = []
    def execute(cmd, **kwargs):
        captured.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, "1 passed\n", "DECK_COMMANDER_ISOLATED_PYTEST_STARTED\n")
    result = test_runner.run(tmp_path, _venv(tmp_path), stop_first=True, rodar=execute)
    assert result.returncode == 0 and result.stderr == ""
    cmd, kwargs = captured[0]
    for option in ("--unshare-all", "--new-session", "--clearenv", "--die-with-parent"):
        assert option in cmd
    assert cmd[cmd.index("--ro-bind") + 1:cmd.index("--ro-bind") + 3] == ["/", "/"]
    variables = {cmd[i + 1]: cmd[i + 2] for i, value in enumerate(cmd) if value == "--setenv"}
    assert variables["HOME"] == variables["DC_ROOT"] == "/tmp/home"
    assert variables["XDG_RUNTIME_DIR"] == "/tmp/runtime"
    assert "DBUS_SESSION_BUS_ADDRESS" not in variables and "DISPLAY" not in variables
    assert "-x" in cmd and kwargs["timeout"] == 1800


def test_sandbox_start_failure_is_infrastructure_not_failed_test(tmp_path, monkeypatch):
    monkeypatch.setattr(test_runner.shutil, "which", lambda name: "/usr/bin/bwrap")
    result = test_runner.run(tmp_path, _venv(tmp_path), rodar=lambda cmd, **k:
                            subprocess.CompletedProcess(cmd, 1, "", "bwrap: unshare failed"))
    assert result.returncode == 2 and "unshare failed" in result.stderr


def test_pytest_failure_keeps_its_exit_code(tmp_path, monkeypatch):
    monkeypatch.setattr(test_runner.shutil, "which", lambda name: "/usr/bin/bwrap")
    result = test_runner.run(tmp_path, _venv(tmp_path), rodar=lambda cmd, **k:
                            subprocess.CompletedProcess(cmd, 1, "1 failed\n", "DECK_COMMANDER_ISOLATED_PYTEST_STARTED\n"))
    assert result.returncode == 1 and result.stdout == "1 failed\n"


@pytest.mark.skipif(sys.platform != "linux" or not shutil.which("bwrap") or os.environ.get("DC_TEST_SANDBOX"),
                    reason="requires outer Linux bubblewrap environment")
def test_real_sandbox_preserves_host_launcher_and_saves(tmp_path):
    """Filesystem/process isolation exercised by a real child pytest process."""
    python = Path(sys.executable)
    if not (python.parent.parent / "pyvenv.cfg").exists():
        pytest.skip("requires dedicated pytest venv")
    host = tmp_path / "host"
    host.mkdir()
    launcher, save = host / "dc-launch", host / "latest.p2s"
    launcher.write_bytes(b"working-launcher")
    save.write_bytes(b"save-that-must-not-change")
    source = tmp_path / "downloaded-source"
    tests = source / "tests"
    tests.mkdir(parents=True)
    shutil.copytree(Path(__file__).resolve().parents[1] / "dc", source / "dc", ignore=shutil.ignore_patterns("__pycache__"))
    (tests / "test_isolation.py").write_text(
        "from pathlib import Path\nimport os\nimport pytest\nfrom dc.library import write_launcher\n"
        "def test_attempt_live_writes():\n"
        "    assert str(Path.home()) == '/tmp/home'\n"
        "    lp = write_launcher(Path.home(), Path.cwd())\n"
        "    assert lp.is_file()\n"
        "    with pytest.raises(OSError):\n"
        "        Path('/tmp/source/corruption').write_text('bad')\n"
        "    assert not Path('/run/user').exists()\n"
        f"    assert not Path({str(save)!r}).exists()\n", "utf-8")
    result = test_runner.run(source, python)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout
    assert launcher.read_bytes() == b"working-launcher"
    assert save.read_bytes() == b"save-that-must-not-change"
    assert not (source / "corruption").exists()
