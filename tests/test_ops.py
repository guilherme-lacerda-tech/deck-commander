"""M0.3/M15/M19 — safe-mode, uninstall com confirmação, índice e verify do banco."""
import pytest

from dc import ops
from dc.library import Game
from dc.paths import get_paths
from dc.store import Store


@pytest.fixture
def env(tmp_path, monkeypatch):
    units = tmp_path / "units"; units.mkdir()
    (units / "deck-commander-bot.service").write_text("x")
    (units / "outro.service").write_text("x")
    monkeypatch.setattr(ops, "unit_dir", lambda: units)
    calls = []
    monkeypatch.setattr(ops, "_systemctl", lambda *a: calls.append(a))
    paths = get_paths(tmp_path / "root").ensure()
    return paths, units, calls


def test_safe_mode_only_disables_and_queues_restore(env):
    paths, units, calls = env
    s = Store(paths.db)
    out = ops.safe_mode_on(paths, "teste", s)
    assert ("disable", "--now", "deck-commander-bot.service") in calls
    assert all("outro" not in c[-1] for c in calls)  # só serviços do DC
    assert ops.in_safe_mode(paths)
    assert s.list(("awaiting_approval",))[0].type == "safe-mode-restore"  # F4
    ops.safe_mode_off(paths)
    assert not ops.in_safe_mode(paths)


def test_uninstall_requires_confirmation_and_keeps_backups(env, tmp_path):
    paths, units, calls = env
    code = tmp_path / "code"; code.mkdir()
    (paths.backups / "snap").mkdir(parents=True)
    with pytest.raises(PermissionError):
        ops.uninstall(paths, code, purge=True, purge_backups=False)
    with pytest.raises(PermissionError):
        ops.uninstall(paths, code, purge=False, purge_backups=True, confirm="APAGAR")
    log = ops.uninstall(paths, code, purge=True, purge_backups=False, confirm="APAGAR")
    assert (paths.backups / "snap").exists() and not paths.config.exists() and not code.exists()
    assert not (units / "deck-commander-bot.service").exists() and (units / "outro.service").exists()
    assert any("preservados" in l for l in log)


def test_index_and_verify(env, tmp_path):
    paths, *_ = env
    s = Store(paths.db)
    a = tmp_path / "a.iso"; a.write_bytes(b"a")
    b = tmp_path / "b.iso"; b.write_bytes(b"b")
    games = [Game("ps2-a", "A", "ps2", str(a)), Game("ps2-b", "B", "ps2", str(b))]
    assert ops.index_files(s, games) == 2
    assert ops.index_files(s, games) == 0  # idempotente
    assert [tuple(r) for r in s.conn.execute("SELECT DISTINCT origin FROM files")] == [("unknown",)]
    b.unlink()
    a.write_bytes(b"aa")
    c = tmp_path / "c.iso"; c.write_bytes(b"c")
    with s.tx() as cx:
        cx.execute("INSERT INTO provenance VALUES('111','dc','x','op')")
    rep = ops.db_verify(s, [Game("ps2-a", "A", "ps2", str(a)), Game("ps2-c", "C", "ps2", str(c))],
                        [{"appid": 222, "AppName": "Novo", "exe": '"/x/dc-launch"'}])
    assert rep["missing"] == [str(b)] and rep["modified"] == [str(a)] and rep["untracked"] == [str(c)]
    assert rep["shortcut_untracked"] == ["Novo"] and rep["shortcut_missing"] == ["111"]
