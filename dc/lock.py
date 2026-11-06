"""M18.1 — lock universal com regra de reentrada.

- Ponto de entrada adquire o lock (flock no Linux; msvcrt no Windows só para dev/teste).
- Script interno recebe DC_OPERATION_ID e NÃO re-adquire — mas só se for reentrância
  legítima (correção F5): o lock precisa estar preso AGORA pela mesma operação e a
  operação precisa estar 'running' no Operation Store. Variável herdada/vazada é ignorada.
- Holder registrado em <lock>.holder (JSON: pid, início, tipo, operation_id).
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

ENV_OP_ID = "DC_OPERATION_ID"

if os.name == "posix":
    import fcntl

    def _try_lock(fd: int) -> bool:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            return False

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)
else:  # Windows: apenas para rodar os testes no PC de desenvolvimento
    import msvcrt

    def _try_lock(fd: int) -> bool:
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    def _unlock(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)


class LockTimeout(TimeoutError):
    pass


def read_holder(lock_path: Path) -> Optional[dict]:
    try:
        return json.loads(Path(str(lock_path) + ".holder").read_text("utf-8"))
    except (OSError, ValueError):
        return None


def lock_is_held(lock_path: Path) -> bool:
    """True se alguém segura o lock agora (teste não-bloqueante, não deixa rastro)."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        if _try_lock(fd):
            _unlock(fd)
            return False
        return True
    finally:
        os.close(fd)


class OperationLock:
    def __init__(self, lock_path: Path, operation_id: str, op_type: str,
                 timeout: float = 300.0,
                 is_running: Optional[Callable[[str], bool]] = None,
                 poll: float = 0.05):
        self.lock_path = Path(lock_path)
        self.operation_id = operation_id
        self.op_type = op_type
        self.timeout = timeout
        self.is_running = is_running
        self.poll = poll
        self.reentrant = False
        self._fd: Optional[int] = None

    # -- reentrância ---------------------------------------------------------
    def _legit_reentry(self) -> bool:
        env_id = os.environ.get(ENV_OP_ID)
        if not env_id or env_id != self.operation_id:
            return False
        holder = read_holder(self.lock_path)
        if not holder or holder.get("operation_id") != env_id:
            return False
        if not lock_is_held(self.lock_path):
            return False
        if self.is_running is not None and not self.is_running(env_id):
            return False
        return True

    def acquire(self) -> "OperationLock":
        if self._legit_reentry():
            self.reentrant = True
            return self
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o644)
        deadline = time.monotonic() + self.timeout
        while not _try_lock(fd):
            if time.monotonic() >= deadline:
                os.close(fd)
                h = read_holder(self.lock_path) or {}
                raise LockTimeout(
                    f"lock ocupado há mais de {self.timeout:.0f}s por "
                    f"{h.get('type', '?')} (op {h.get('operation_id', '?')}, pid {h.get('pid', '?')})")
            time.sleep(self.poll)
        self._fd = fd
        holder = {"pid": os.getpid(), "type": self.op_type, "operation_id": self.operation_id,
                  "started_at": datetime.now(timezone.utc).isoformat()}
        tmp = Path(str(self.lock_path) + ".holder.tmp")
        tmp.write_text(json.dumps(holder), "utf-8")
        os.replace(tmp, str(self.lock_path) + ".holder")
        return self

    def release(self) -> None:
        if self.reentrant or self._fd is None:
            return
        try:
            Path(str(self.lock_path) + ".holder").unlink(missing_ok=True)
        finally:
            _unlock(self._fd)
            os.close(self._fd)
            self._fd = None

    def child_env(self, base: Optional[dict] = None) -> dict:
        """Ambiente para scripts internos desta operação."""
        env = dict(os.environ if base is None else base)
        env[ENV_OP_ID] = self.operation_id
        return env

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *exc):
        self.release()
