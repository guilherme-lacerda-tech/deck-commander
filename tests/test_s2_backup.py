"""S2 — backup corrompido -> cai para o anterior; quarentena; avisa; restore com guarda do Steam."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dc import backup, quarantine


class Clock:
    def __init__(self):
        self.t = datetime(2026, 11, 6, tzinfo=timezone.utc)

    def __call__(self):
        self.t += timedelta(seconds=1)
        return self.t


@pytest.fixture
def env(tmp_path):
    src = tmp_path / "home"
    (src / "emu").mkdir(parents=True)
    (src / "emu" / "settings.ini").write_text("scale=2\n")
    (src / "steam").mkdir()
    (src / "steam" / "shortcuts.vdf").write_bytes(b"\x00shortcuts\x00v1")
    return {"sources": {"emu": src / "emu", "shortcuts": src / "steam" / "shortcuts.vdf"},
            "dest": tmp_path / "Backups", "q": tmp_path / "Backups" / "quarantine", "src": src,
            "clk": Clock()}


def snap(env, **kw):
    return backup.create_snapshot(env["sources"], env["dest"], env["q"], now=env["clk"], **kw)


def test_snapshot_valid_and_manifested(env):
    r = snap(env)
    assert r.ok and backup.verify_snapshot(r.path) == []
    assert any("MESMO dispositivo" in w for w in r.warnings)  # tmp é o mesmo disco


def test_corruption_during_creation_goes_to_quarantine(env):
    def corrupt(tmp: Path):
        f = next((tmp / "data").rglob("settings.ini"))
        f.write_text("scale=9\n")  # muda conteúdo depois do manifesto
    r = snap(env, _corrupt_hook=corrupt)
    assert not r.ok and "quarentena" in r.error
    assert backup.list_snapshots(env["dest"]) == []
    assert len(quarantine.list_entries(env["q"])) == 1


def test_latest_corrupt_falls_back_to_previous(env):
    good = snap(env).path
    (env["src"] / "emu" / "settings.ini").write_text("scale=3\n")
    newest = snap(env).path
    next((newest / "data").rglob("settings.ini")).write_text("lixo")
    chosen, warns = backup.latest_valid(env["dest"], env["q"])
    assert chosen == good
    assert warns and "quarentena" in warns[0]
    entries = quarantine.list_entries(env["q"])
    assert len(entries) == 1 and "divergente" in entries[0].reason
    assert not newest.exists()  # movido, não apagado
    assert (entries[0].path / newest.name / "manifest.json").exists()


def test_all_corrupt_raises_sos(env):
    s = snap(env).path
    (s / "manifest.json").unlink()
    with pytest.raises(backup.AllBackupsCorrupt):
        backup.latest_valid(env["dest"], env["q"])


def test_retention_keeps_5(env):
    for _ in range(7):
        assert snap(env).ok
    assert len(backup.list_snapshots(env["dest"], "config")) == 5


def test_restore_requires_steam_guard(env, tmp_path):
    s = snap(env).path
    plan = backup.restore_snapshot(s, dry_run=True)
    assert any(dst.endswith("shortcuts.vdf") for _, dst in plan)
    with pytest.raises(backup.BackupError, match="fechar o Steam"):
        backup.restore_snapshot(s, dry_run=False, target_root=tmp_path / "out")

    events = []

    class Guard:
        def __enter__(self): events.append("steam-closed")
        def __exit__(self, *a): events.append("steam-reopened")

    backup.restore_snapshot(s, dry_run=False, target_root=tmp_path / "out", steam_guard=Guard())
    assert events == ["steam-closed", "steam-reopened"]
    restored = list((tmp_path / "out").rglob("shortcuts.vdf"))
    assert restored and restored[0].read_bytes() == b"\x00shortcuts\x00v1"


def test_quarantine_review_by_and_never_auto_deletes(env, tmp_path):
    f = tmp_path / "rom.bin"; f.write_bytes(b"x")
    clk = env["clk"]
    e = quarantine.quarantine(f, env["q"], "teste", now=clk)
    assert not quarantine.list_entries(env["q"], now=clk)[0].overdue
    later = lambda: clk.t + timedelta(days=31)
    entries = quarantine.list_entries(env["q"], now=later)
    assert entries[0].overdue and e.exists()  # vencido só avisa
