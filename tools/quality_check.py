#!/usr/bin/env python3
"""Diagnóstico no Deck: para cada console com ajuste por jogo, aplica um valor de teste no arquivo REAL
do emulador, devolve e confere que o arquivo voltou byte a byte igual. Não abre jogo nenhum.
Uso: python3 tools/quality_check.py"""
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dc import quality  # noqa: E402
from dc.paths import get_paths  # noqa: E402

paths = get_paths()
ok = True
for console in quality.TARGETS:
    t = quality._target(console)
    if not t:
        print(f"--   {console}: emulador ainda sem arquivo de config (nada a testar)")
        continue
    fmt, f, sec, key = t
    before = hashlib.sha256(f.read_bytes()).hexdigest()
    cur = quality._read(fmt, f, sec, key)
    test = "1" if (cur or "").strip() not in ("1", "1.0") else "2"
    gid = f"__teste-{console}"
    quality.set_override(paths, gid, console, {"1": "nativo", "2": "2x"}[test])
    rec = quality.apply_for_launch(paths, gid, console)
    applied = quality._read(fmt, f, sec, key)
    msg = quality.restore(paths)
    quality.set_override(paths, gid, console, None)
    after = hashlib.sha256(f.read_bytes()).hexdigest()
    good = rec is not None and applied.strip() == test and before == after
    ok &= good
    print(f"{'OK  ' if good else 'FALHA'} {console}: {f.name} [{sec}] {key}: {cur} -> {applied} -> devolvido ({msg})"
          f"{'' if before == after else ' ARQUIVO MUDOU!'}")
print("RESULTADO:", "TUDO OK" if ok else "FALHOU")
sys.exit(0 if ok else 1)
