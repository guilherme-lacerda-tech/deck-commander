from datetime import datetime, timedelta, timezone

import pytest

from dc.store import ApprovalExpired, ApprovalReplay, DatabaseCorrupt, Store, SCHEMA_VERSION


class Clock:
    def __init__(self):
        self.t = datetime(2026, 11, 6, tzinfo=timezone.utc)

    def __call__(self):
        return self.t


def test_pragmas_and_schema(tmp_path):
    s = Store(tmp_path / "d.db")
    assert s.conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert s.schema_version() == SCHEMA_VERSION
    s.close()
    assert Store(tmp_path / "d.db").schema_version() == SCHEMA_VERSION  # idempotente


def test_approval_expires_after_1h(tmp_path):
    clk = Clock()
    s = Store(tmp_path / "d.db", now=clk)
    op = s.enqueue("dedup", requires_approval=True)
    clk.t += timedelta(hours=1, seconds=1)
    with pytest.raises(ApprovalExpired):
        s.approve(op)
    assert s.get(op).state == "cancelled" and s.get(op).error == "approval_expired"


def test_approval_replay_blocked(tmp_path):
    s = Store(tmp_path / "d.db", now=Clock())
    op = s.enqueue("dedup", requires_approval=True)
    s.approve(op)
    assert s.get(op).state == "pending"
    with pytest.raises(ApprovalReplay):
        s.approve(op)


def test_snapshot_is_consistent(tmp_path):
    s = Store(tmp_path / "d.db")
    s.enqueue("x")
    snap = s.snapshot_to(tmp_path / "bk" / "d.db")
    s2 = Store(snap)
    assert len(s2.list()) == 1


def test_corrupt_db_detected(tmp_path):
    p = tmp_path / "d.db"
    s = Store(p)
    for i in range(300):
        s.enqueue("x", {"pad": "y" * 200})
    s.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    s.close()
    raw = bytearray(p.read_bytes())
    for off in range(4096 * 2, min(len(raw), 4096 * 6)):
        raw[off] ^= 0xFF
    p.write_bytes(bytes(raw))
    with pytest.raises((DatabaseCorrupt, Exception)):
        Store(p)
