#!/usr/bin/env python3
"""Diagnóstico: quais trechos de um projeto do RomTranslate o filtro do Deck Commander considera "frase de
verdade" (e portanto iriam para a tradução). Uso: python3 tools/rts_candidatos.py <projeto.rtsproj> [amostra]"""
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dc.traducao import rts  # noqa: E402

proj = Path(sys.argv[1])
exp = proj / "exports" / "deck-commander.json"
entries = json.loads(exp.read_text("utf-8"))
picked = [e for e in entries if e.get("sourceText") and rts.is_sentence(e["sourceText"])]
print(len(entries), "trechos ->", len(picked), "frases")
random.seed(int(sys.argv[2]) if len(sys.argv) > 2 else 1)
by_res = {}
for e in picked:
    by_res[e.get("resourcePath", "?")] = by_res.get(e.get("resourcePath", "?"), 0) + 1
print("por arquivo do disco:", sorted(by_res.items(), key=lambda kv: -kv[1])[:12])
for e in random.sample(picked, min(40, len(picked))):
    print(f"{e.get('resourcePath', '?')[:18]:18} {e['maxBytes']:4} {e['sourceText'][:90]!r}")
