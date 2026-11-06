#!/usr/bin/env python3
"""S1 (parte física) — operação 'running' + reboot real do Deck.

  python3 tools/s1_reboot.py prepare   # cria op running segurando o lock, num DC_ROOT isolado
  (reiniciar o Deck)
  python3 tools/s1_reboot.py check     # depois do boot: DB íntegro + op vira 'interrupted'

Usa ~/deck-commander-spikes/s1 como raiz — não toca em nada do sistema.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path.home() / "deck-commander-spikes" / "s1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["DC_ROOT"] = str(ROOT)

from dc import worker  # noqa: E402
from dc.lock import OperationLock  # noqa: E402
from dc.paths import get_paths  # noqa: E402
from dc.store import DatabaseCorrupt, Store  # noqa: E402

paths = get_paths(ROOT).ensure()


def prepare():
    s = Store(paths.db)
    op = s.enqueue("spike-s1-reboot")
    s.claim_next()
    (ROOT / "op_id").write_text(op)
    # processo em segundo plano segura o lock e fica escrevendo até o reboot
    code = f"""
import sys, time; sys.path.insert(0, {str(Path(__file__).resolve().parents[1])!r})
from dc.lock import OperationLock
from dc.store import Store
s = Store({str(paths.db)!r})
with OperationLock({str(paths.lock)!r}, {op!r}, 'spike-s1-reboot'):
    i = 0
    while True:
        with s.tx():
            s.conn.execute("INSERT OR REPLACE INTO games(id,title,console,created_at) VALUES(?,?,?,?)",
                           (str(i % 500), 'x' * 200, 'ps1', str(time.time())))
        i += 1
        time.sleep(0.01)
"""
    p = subprocess.Popen([sys.executable, "-c", code], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)
    print(f"op {op} em 'running', escritor pid {p.pid} gravando continuamente.")
    print("AGORA: reinicie o Deck (botão Power > Reiniciar) e depois rode: python3 tools/s1_reboot.py check")


def check():
    op = (ROOT / "op_id").read_text().strip()
    try:
        s = Store(paths.db)
    except DatabaseCorrupt as e:
        print(f"FALHOU: integrity_check: {e}"); return 1
    print("integrity_check: ok")
    before = s.get(op).state
    ids = worker.recover(s, paths)
    after = s.get(op).state
    print(f"estado antes do recover: {before}; depois: {after}; marcadas: {ids}")
    with OperationLock(paths.lock, "post-boot", "check", timeout=5):
        print("lock adquirível após boot: ok")
    ok = before == "running" and after == "interrupted"
    print("S1-reboot:", "PASSOU" if ok else "FALHOU")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit({"prepare": prepare, "check": check}[sys.argv[1]]() or 0)
