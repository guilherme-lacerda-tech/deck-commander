"""Worker único: consome a fila do Operation Store respeitando o lock universal.

Handlers recebem (op, env) — `env` já contém DC_OPERATION_ID para scripts internos
(reentrância). Cada operação gera uma linha JSONL em logs/operations.log (M18.3).
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Callable, Optional

from .lock import OperationLock, lock_is_held
from .paths import Paths
from .store import Operation, Store

Handler = Callable[[Operation, dict], Optional[dict]]


def log_operation(paths: Paths, record: dict) -> None:
    paths.logs.mkdir(parents=True, exist_ok=True)
    record = {"ts": datetime.now(timezone.utc).isoformat(), **record}
    with open(paths.logs / "operations.log", "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def recover(store: Store, paths: Paths) -> list[str]:
    """Na inicialização: 'running' sem ninguém segurando o lock => 'interrupted'.
    O usuário decide depois (retry/cancel)."""
    if lock_is_held(paths.lock):
        return []
    ids = store.mark_interrupted()
    for i in ids:
        log_operation(paths, {"op": i, "event": "interrupted"})
    return ids


def run_once(store: Store, paths: Paths, handlers: dict[str, Handler], lock_timeout: float = 300.0) -> Optional[str]:
    op = store.claim_next()
    if op is None:
        return None
    handler = handlers.get(op.type)
    t0 = time.monotonic()
    log_operation(paths, {"op": op.id, "type": op.type, "event": "start"})
    try:
        if handler is None:
            raise LookupError(f"sem handler para '{op.type}'")
        with OperationLock(paths.lock, op.id, op.type, timeout=lock_timeout, is_running=store.is_running) as lk:
            result = handler(op, lk.child_env())
        store.finish(op.id, True, result=result)
        log_operation(paths, {"op": op.id, "type": op.type, "event": "done",
                              "duration_s": round(time.monotonic() - t0, 3)})
    except Exception as e:  # noqa: BLE001 — qualquer falha vira 'failed' com motivo
        store.finish(op.id, False, error=f"{type(e).__name__}: {e}")
        log_operation(paths, {"op": op.id, "type": op.type, "event": "failed", "error": str(e),
                              "duration_s": round(time.monotonic() - t0, 3)})
    return op.id
