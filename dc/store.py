"""M18+M19 — Operation Store (SQLite fonte única de fila/estado/histórico).

Durabilidade (v5.1 M19.1): WAL; synchronous=FULL nas escritas críticas e NORMAL no resto;
wal_autocheckpoint=1000 + checkpoint após operação crítica; integrity_check na abertura;
BEGIN IMMEDIATE para escrita; snapshot consistente via VACUUM INTO.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

STATES = ("pending", "awaiting_approval", "running", "done", "failed", "interrupted", "cancelled")
APPROVAL_TTL = timedelta(hours=1)

MIGRATIONS: dict[int, list[str]] = {
    1: [
        """CREATE TABLE operations(
            id TEXT PRIMARY KEY,
            seq INTEGER NOT NULL,
            type TEXT NOT NULL,
            params TEXT NOT NULL DEFAULT '{}',
            state TEXT NOT NULL CHECK(state IN ('pending','awaiting_approval','running','done',
                                                'failed','interrupted','cancelled')),
            requires_approval INTEGER NOT NULL DEFAULT 0,
            approval_expires_at TEXT,
            approved_at TEXT,
            attempts INTEGER NOT NULL DEFAULT 0,
            error TEXT,
            result TEXT,
            created_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT)""",
        "CREATE INDEX ix_operations_state_seq ON operations(state, seq)",
        """CREATE TABLE games(
            id TEXT PRIMARY KEY, title TEXT NOT NULL, console TEXT NOT NULL,
            region TEXT, serial TEXT, created_at TEXT NOT NULL)""",
        """CREATE TABLE content_hashes(
            sha256 TEXT PRIMARY KEY, size INTEGER NOT NULL, first_seen_at TEXT NOT NULL)""",
        """CREATE TABLE files(
            id INTEGER PRIMARY KEY,
            game_id TEXT REFERENCES games(id),
            path TEXT NOT NULL UNIQUE,
            size INTEGER NOT NULL, mtime REAL NOT NULL,
            sha256 TEXT REFERENCES content_hashes(sha256),
            origin TEXT NOT NULL DEFAULT 'unknown'
                CHECK(origin IN ('torrent','import','manual','unknown')),
            origin_ref TEXT, origin_note TEXT,
            integrity TEXT NOT NULL DEFAULT 'unverified'
                CHECK(integrity IN ('verified','mismatch','unverified','corrupted')))""",
        """CREATE TABLE provenance(
            appid TEXT PRIMARY KEY,
            source TEXT NOT NULL CHECK(source IN ('srm','unifideck','dc','manual')),
            created_at TEXT NOT NULL, operation_id TEXT)""",
    ],
}
SCHEMA_VERSION = max(MIGRATIONS)


class DatabaseCorrupt(RuntimeError):
    pass


class ApprovalError(RuntimeError):
    pass


class ApprovalExpired(ApprovalError):
    pass


class ApprovalReplay(ApprovalError):
    pass


@dataclass
class Operation:
    id: str
    seq: int
    type: str
    params: dict
    state: str
    attempts: int
    error: Optional[str]
    result: Optional[str]
    approval_expires_at: Optional[str]
    approved_at: Optional[str]
    created_at: str
    started_at: Optional[str]
    finished_at: Optional[str]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).isoformat()


class Store:
    def __init__(self, db_path: Path, now: Callable[[], datetime] = _utcnow, check: bool = True):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.now = now
        self.conn = sqlite3.connect(self.db_path, isolation_level=None, timeout=30)
        self.conn.row_factory = sqlite3.Row
        c = self.conn
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        c.execute("PRAGMA wal_autocheckpoint=1000")
        c.execute("PRAGMA foreign_keys=ON")
        c.execute("PRAGMA busy_timeout=30000")
        if check:
            res = [r[0] for r in c.execute("PRAGMA integrity_check")]
            if res != ["ok"]:
                c.close()
                raise DatabaseCorrupt("; ".join(res[:5]))
        self._migrate()

    def close(self) -> None:
        self.conn.close()

    # -- transações ------------------------------------------------------------
    @contextmanager
    def tx(self, critical: bool = False):
        c = self.conn
        if critical:
            c.execute("PRAGMA synchronous=FULL")
        c.execute("BEGIN IMMEDIATE")
        try:
            yield c
            c.execute("COMMIT")
        except BaseException:
            c.execute("ROLLBACK")
            raise
        finally:
            if critical:
                c.execute("PRAGMA synchronous=NORMAL")
        if critical:
            c.execute("PRAGMA wal_checkpoint(PASSIVE)")

    # -- schema ------------------------------------------------------------------
    def schema_version(self) -> int:
        has = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_version'").fetchone()
        if not has:
            return 0
        row = self.conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        return row[0] or 0

    def _migrate(self) -> None:
        current = self.schema_version()
        if current > SCHEMA_VERSION:
            raise RuntimeError(f"banco v{current} é mais novo que o código (v{SCHEMA_VERSION})")
        for v in range(current + 1, SCHEMA_VERSION + 1):
            with self.tx(critical=True) as c:
                if v == 1:
                    c.execute("CREATE TABLE schema_version(version INTEGER NOT NULL, applied_at TEXT NOT NULL)")
                for sql in MIGRATIONS[v]:
                    c.execute(sql)
                c.execute("INSERT INTO schema_version VALUES(?,?)", (v, _iso(self.now())))

    def snapshot_to(self, dest: Path) -> Path:
        """Cópia consistente e atômica do banco (VACUUM INTO)."""
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            raise FileExistsError(dest)
        self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.conn.execute("VACUUM INTO ?", (str(dest),))
        return dest

    # -- operações -----------------------------------------------------------------
    def _row(self, r: sqlite3.Row) -> Operation:
        d = dict(r)
        d["params"] = json.loads(d["params"])
        d.pop("requires_approval", None)
        return Operation(**d)

    def get(self, op_id: str) -> Optional[Operation]:
        r = self.conn.execute("SELECT * FROM operations WHERE id=?", (op_id,)).fetchone()
        return self._row(r) if r else None

    def list(self, states: tuple[str, ...] = STATES, limit: int = 50) -> list[Operation]:
        q = f"SELECT * FROM operations WHERE state IN ({','.join('?' * len(states))}) ORDER BY seq DESC LIMIT ?"
        return [self._row(r) for r in self.conn.execute(q, (*states, limit))]

    def is_running(self, op_id: str) -> bool:
        op = self.get(op_id)
        return bool(op and op.state == "running")

    def enqueue(self, op_type: str, params: Optional[dict] = None, requires_approval: bool = False) -> str:
        op_id = uuid.uuid4().hex[:12]
        now = self.now()
        state = "awaiting_approval" if requires_approval else "pending"
        expires = _iso(now + APPROVAL_TTL) if requires_approval else None
        with self.tx(critical=requires_approval) as c:
            seq = (c.execute("SELECT COALESCE(MAX(seq),0)+1 FROM operations").fetchone()[0])
            c.execute(
                "INSERT INTO operations(id,seq,type,params,state,requires_approval,approval_expires_at,created_at)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (op_id, seq, op_type, json.dumps(params or {}), state, int(requires_approval), expires, _iso(now)))
        return op_id

    def approve(self, op_id: str) -> None:
        """Aprovação vinculada ao ID, válida por 1h, não aprova 2x (M12.2)."""
        with self.tx(critical=True) as c:
            r = c.execute("SELECT state, approved_at, approval_expires_at FROM operations WHERE id=?",
                          (op_id,)).fetchone()
            if r is None:
                raise ApprovalError(f"operação {op_id} não existe")
            if r["approved_at"] is not None:
                raise ApprovalReplay(f"operação {op_id} já foi aprovada em {r['approved_at']}")
            if r["state"] != "awaiting_approval":
                raise ApprovalError(f"operação {op_id} está '{r['state']}', não aguarda aprovação")
            if self.now() >= datetime.fromisoformat(r["approval_expires_at"]):
                c.execute("UPDATE operations SET state='cancelled', error='approval_expired', finished_at=?"
                          " WHERE id=?", (_iso(self.now()), op_id))
                expired = True
            else:
                c.execute("UPDATE operations SET state='pending', approved_at=? WHERE id=?",
                          (_iso(self.now()), op_id))
                expired = False
        if expired:
            raise ApprovalExpired(f"aprovação de {op_id} expirou")

    def expire_approvals(self) -> int:
        with self.tx() as c:
            cur = c.execute(
                "UPDATE operations SET state='cancelled', error='approval_expired', finished_at=?"
                " WHERE state='awaiting_approval' AND approval_expires_at <= ?",
                (_iso(self.now()), _iso(self.now())))
            return cur.rowcount

    def claim_next(self) -> Optional[Operation]:
        """FIFO entre 'pending'. 'awaiting_approval' não segura a fila (correção F9)."""
        self.expire_approvals()
        with self.tx(critical=True) as c:
            r = c.execute("SELECT id FROM operations WHERE state='pending' ORDER BY seq LIMIT 1").fetchone()
            if r is None:
                return None
            c.execute("UPDATE operations SET state='running', started_at=?, attempts=attempts+1 WHERE id=?",
                      (_iso(self.now()), r["id"]))
        return self.get(r["id"])

    def claim(self, op_id: str) -> Optional[Operation]:
        """Pega UMA operação específica (a que o chamador acabou de criar), nunca a de outro."""
        with self.tx(critical=True) as c:
            cur = c.execute("UPDATE operations SET state='running', started_at=?, attempts=attempts+1"
                            " WHERE id=? AND state='pending'", (_iso(self.now()), op_id))
            if cur.rowcount != 1:
                return None
        return self.get(op_id)

    def finish(self, op_id: str, ok: bool, result: Optional[dict] = None, error: Optional[str] = None) -> None:
        with self.tx(critical=True) as c:
            c.execute("UPDATE operations SET state=?, result=?, error=?, finished_at=? WHERE id=? AND state='running'",
                      ("done" if ok else "failed", json.dumps(result) if result is not None else None,
                       error, _iso(self.now()), op_id))

    def mark_interrupted(self) -> list[str]:
        """Chamar só quando ninguém segura o lock (ver worker.recover)."""
        with self.tx(critical=True) as c:
            ids = [r[0] for r in c.execute("SELECT id FROM operations WHERE state='running'")]
            c.execute("UPDATE operations SET state='interrupted', error='interrompida (reinício/crash)',"
                      " finished_at=? WHERE state='running'", (_iso(self.now()),))
        return ids

    def retry(self, op_id: str) -> None:
        with self.tx(critical=True) as c:
            seq = c.execute("SELECT COALESCE(MAX(seq),0)+1 FROM operations").fetchone()[0]
            cur = c.execute("UPDATE operations SET state='pending', seq=?, error=NULL, finished_at=NULL"
                            " WHERE id=? AND state IN ('interrupted','failed')", (seq, op_id))
            if cur.rowcount != 1:
                raise ValueError(f"operação {op_id} não está interrupted/failed")

    def cancel(self, op_id: str) -> None:
        with self.tx(critical=True) as c:
            cur = c.execute("UPDATE operations SET state='cancelled', finished_at=?"
                            " WHERE id=? AND state IN ('pending','awaiting_approval','interrupted','failed')",
                            (_iso(self.now()), op_id))
            if cur.rowcount != 1:
                raise ValueError(f"operação {op_id} não pode ser cancelada no estado atual")
