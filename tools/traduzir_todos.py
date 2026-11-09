#!/usr/bin/env python3
"""Teste de /traduzir em TODOS os jogos da biblioteca, sem Telegram: cada pedido roda o executor na hora
(em vez de em segundo plano) e a resposta/relatório é impressa. As tarefas ficam marcadas como já
avisadas (o bot de verdade não manda mensagem). Só jogos que podem ser traduzidos de fato geram mod/ROM.
Uso: python3 tools/traduzir_todos.py [parte do nome]"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dc import bot  # noqa: E402
from dc.paths import get_paths  # noqa: E402
from dc.traducao import run  # noqa: E402

paths = get_paths()
tmp = Path(tempfile.mkdtemp()) / "telegram.json"
shutil.copy(paths.config / "telegram.json", tmp)
b = bot.Bot(paths, "dry-run")
b.cfg_path = tmp
b.cfg = json.loads(tmp.read_text("utf-8"))
b.cfg.pop("notify_chat", None)
b.send = lambda chat, text: None
uid = b.cfg["allowed"][0]
started = []
run.spawn = lambda p, op: started.append(op)
q = (sys.argv[1] if len(sys.argv) > 1 else "").lower()
print(b.handle(uid, uid, "/traduzir lista"))
print("=" * 70)
for gid, g in sorted(b._map().items(), key=lambda kv: (kv[1]["console"], kv[1]["title"])):
    if g.get("removed") or q not in g["title"].lower():
        continue
    started.clear()
    reply = b.handle(uid, uid, f"/traduzir {gid}")
    line = f"[{g['console']}] {g['title'][:45]}\n   → {reply.splitlines()[0][:150]}"
    for op in started:
        job = run.run(paths, op)
        job["notified"] = True
        run.save_job(paths, job)
        line += f"\n   ⇒ {job['status']}: " + " | ".join(job.get("report", "").splitlines()[:3])[:300]
    print(line)
