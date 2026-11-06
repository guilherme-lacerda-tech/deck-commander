"""S1 — concorrência, reentrância e crash (simulado com kill do processo)."""
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from dc.lock import ENV_OP_ID, LockTimeout, OperationLock, lock_is_held
from dc.paths import get_paths
from dc.store import Store
from dc import worker

ROOT = Path(__file__).resolve().parents[1]


def run_py(code: str, env=None, wait=True):
    e = dict(os.environ if env is None else env)
    e["PYTHONPATH"] = str(ROOT)
    p = subprocess.Popen([sys.executable, "-c", textwrap.dedent(code)], env=e,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if wait:
        out, err = p.communicate(timeout=60)
        return p.returncode, out, err
    return p


@pytest.fixture
def paths(tmp_path):
    return get_paths(tmp_path).ensure()


def test_two_processes_exclusive(paths):
    """Processo A segura o lock; B (independente) espera e estoura o timeout."""
    holder = run_py(f"""
        import time
        from dc.lock import OperationLock
        with OperationLock(r'{paths.lock}', 'opA', 'dedup'):
            print('held', flush=True); time.sleep(3)
    """, wait=False)
    assert holder.stdout.readline().strip() == "held"
    rc, out, err = run_py(f"""
        from dc.lock import OperationLock, LockTimeout
        try:
            OperationLock(r'{paths.lock}', 'opB', 'restore', timeout=0.5).acquire()
            print('ACQUIRED')
        except LockTimeout as e:
            print('TIMEOUT', e)
    """)
    holder.wait(timeout=30)
    assert out.startswith("TIMEOUT"), out + err
    assert "dedup" in out and "opA" in out  # mensagem mostra quem segura


def test_lock_released_after_holder_killed(paths):
    """Kill -9 do dono: o SO libera o flock; ninguém fica preso para sempre."""
    holder = run_py(f"""
        import time
        from dc.lock import OperationLock
        OperationLock(r'{paths.lock}', 'opA', 'dedup').acquire()
        print('held', flush=True); time.sleep(60)
    """, wait=False)
    assert holder.stdout.readline().strip() == "held"
    assert lock_is_held(paths.lock)
    holder.kill(); holder.wait(timeout=30)
    with OperationLock(paths.lock, "opB", "restore", timeout=5):
        pass


def test_reentrancy_internal_script_does_not_deadlock(paths):
    store = Store(paths.db)
    op = store.enqueue("dedup")
    store.claim_next()
    with OperationLock(paths.lock, op, "dedup", is_running=store.is_running) as lk:
        rc, out, err = run_py(f"""
            from dc.lock import OperationLock
            from dc.store import Store
            s = Store(r'{paths.db}')
            l = OperationLock(r'{paths.lock}', '{op}', 'dedup-internal', timeout=2, is_running=s.is_running).acquire()
            print('REENTRANT' if l.reentrant else 'ACQUIRED'); l.release()
        """, env=lk.child_env())
    assert out.strip() == "REENTRANT", out + err


def test_leaked_operation_id_is_not_trusted(paths):
    """Correção F5: DC_OPERATION_ID herdado de operação já concluída não fura o lock."""
    store = Store(paths.db)
    op = store.enqueue("dedup")
    store.claim_next(); store.finish(op, True)
    other = OperationLock(paths.lock, "opX", "restore").acquire()  # lock preso por outra op
    try:
        env = dict(os.environ); env[ENV_OP_ID] = op
        rc, out, err = run_py(f"""
            from dc.lock import OperationLock, LockTimeout
            from dc.store import Store
            s = Store(r'{paths.db}')
            try:
                OperationLock(r'{paths.lock}', '{op}', 'x', timeout=0.5, is_running=s.is_running).acquire()
                print('BYPASS')
            except LockTimeout:
                print('BLOCKED')
        """, env=env)
        assert out.strip() == "BLOCKED", out + err
    finally:
        other.release()


def test_crash_mid_transaction_keeps_db_intact(paths):
    Store(paths.db).close()
    proc = run_py(f"""
        import time
        from dc.store import Store
        s = Store(r'{paths.db}')
        op = s.enqueue('dedup'); s.claim_next()
        s.conn.execute('BEGIN IMMEDIATE')
        for i in range(2000):
            s.conn.execute("INSERT INTO games(id,title,console,created_at) VALUES(?,?,?,?)", (str(i),'t','ps1','x'))
        print('mid-tx', flush=True); time.sleep(60)
    """, wait=False)
    assert proc.stdout.readline().strip() == "mid-tx"
    proc.kill(); proc.wait(timeout=30)
    s = Store(paths.db)  # integrity_check roda na abertura
    assert s.conn.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 0  # tx não confirmada sumiu
    running = s.list(("running",))
    assert len(running) == 1  # commit anterior ao crash sobreviveu
    ids = worker.recover(s, paths)
    assert ids == [running[0].id]
    assert s.get(ids[0]).state == "interrupted"
    s.retry(ids[0])
    assert s.get(ids[0]).state == "pending"


def test_recover_does_not_touch_live_operation(paths):
    s = Store(paths.db)
    op = s.enqueue("dedup"); s.claim_next()
    with OperationLock(paths.lock, op, "dedup"):
        assert worker.recover(s, paths) == []
        assert s.get(op).state == "running"


def test_worker_runs_fifo_and_logs(paths):
    s = Store(paths.db)
    seen = []
    a = s.enqueue("t", {"n": 1})
    gated = s.enqueue("t", {"n": 2}, requires_approval=True)
    c = s.enqueue("t", {"n": 3})
    handlers = {"t": lambda op, env: seen.append((op.params["n"], env[ENV_OP_ID] == op.id)) or {"ok": 1}}
    while worker.run_once(s, paths, handlers):
        pass
    assert seen == [(1, True), (3, True)]  # aguardando aprovação não segura a fila
    assert s.get(gated).state == "awaiting_approval"
    log = (paths.logs / "operations.log").read_text("utf-8")
    assert log.count('"event": "done"') == 2


def test_handler_failure_marks_failed(paths):
    s = Store(paths.db)
    op = s.enqueue("boom")
    worker.run_once(s, paths, {"boom": lambda o, e: 1 / 0})
    assert s.get(op).state == "failed" and "ZeroDivisionError" in s.get(op).error
    assert not lock_is_held(paths.lock)
