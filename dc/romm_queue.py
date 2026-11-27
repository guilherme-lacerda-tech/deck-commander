"""Fila persistente de varreduras do RomM para a biblioteca compartilhada."""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from contextlib import closing
from pathlib import Path

from . import ops
from .lock import LockTimeout, OperationLock
from .romm_client import RommClient, RommError

LOG = logging.getLogger(__name__)


def _db(paths):
    conn = sqlite3.connect(paths.state / "romm-queue.sqlite", timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS scan (
        singleton INTEGER PRIMARY KEY CHECK(singleton=1), requested INTEGER DEFAULT 0,
        completed INTEGER DEFAULT 0, submitted INTEGER DEFAULT 0, task TEXT,
        attempts INTEGER DEFAULT 0, next_at REAL DEFAULT 0, error TEXT)""")
    conn.execute("INSERT OR IGNORE INTO scan(singleton) VALUES (1)")
    conn.commit()
    return conn


def published(paths, files):
    config = paths.config / "romm.json"
    if not config.is_file():
        return False
    cfg = json.loads(config.read_text("utf-8"))
    root = Path(cfg["roms_root"]).expanduser()
    if not root.is_absolute() or not root.is_dir():
        raise ValueError("raiz compartilhada do RomM indisponível")
    root = root.resolve(strict=True)
    if not any(Path(f).is_file() and Path(f).resolve(strict=True).is_relative_to(root) for f in files if f):
        return False
    with closing(_db(paths)) as conn, conn:
        conn.execute("UPDATE scan SET requested=requested+1")
    return True


def _step(paths, conn, row, now):
    cfg = json.loads((paths.config / "romm.json").read_text("utf-8"))
    token = (paths.secrets / "romm-token").read_text("utf-8").strip()
    client = RommClient(cfg["url"], token)
    if not row["task"]:
        task = client.iniciar_scan()["task_id"]
        if not isinstance(task, str) or not task.strip():
            raise RommError("Identificador remoto inválido")
        conn.execute("UPDATE scan SET task=?,submitted=?,next_at=?,error=NULL",
                     (task, row["requested"], now + 5))
        return
    result = client.consultar_tarefa(row["task"])
    if result.get("task_id") != row["task"]:
        raise RommError("RomM retornou outra tarefa")
    status = result.get("status")
    if status == "finished":
        conn.execute("UPDATE scan SET completed=submitted,task=NULL,attempts=0,next_at=0,error=NULL")
    elif status in ("queued", "started", "scheduled", "deferred"):
        conn.execute("UPDATE scan SET next_at=?,error=NULL", (now + 10,))
    else:
        conn.execute("UPDATE scan SET task=NULL")
        raise RommError("varredura remota interrompida")


def tick(paths, now=None):
    """Um POST pode se repetir se o processo cair antes de registrar o ID da varredura."""
    now = time.time() if now is None else now
    if not (paths.state / "romm-queue.sqlite").exists() or ops.in_safe_mode(paths):
        return
    try:
        with OperationLock(paths.state / "romm-worker.lock", uuid.uuid4().hex, "romm", timeout=0):
            with closing(_db(paths)) as conn, conn:
                row = conn.execute("SELECT * FROM scan").fetchone()
                if row["requested"] <= row["completed"] or now < row["next_at"]:
                    return
                try:
                    _step(paths, conn, row, now)
                except (OSError, ValueError, TypeError, KeyError, RommError) as exc:
                    if row["task"] and getattr(exc, "status", None) == 404:
                        conn.execute("UPDATE scan SET task=NULL")
                    delay = min(900, 5 * 2 ** min(8, row["attempts"]))
                    reason = str(exc) if isinstance(exc, RommError) else type(exc).__name__
                    conn.execute("UPDATE scan SET attempts=attempts+1,next_at=?,error=?", (now + delay, reason))
                    LOG.warning("RomM: %s. Nova tentativa em %d s", reason, delay)
    except LockTimeout:
        return


def start(paths):
    def work():
        while True:
            try:
                tick(paths)
            except (OSError, sqlite3.Error) as exc:
                LOG.warning("Falha no worker RomM: %s", type(exc).__name__)
            time.sleep(5)
    threading.Thread(target=work, name="romm-scan", daemon=True).start()
