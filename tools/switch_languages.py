#!/usr/bin/env python3
"""Diagnóstico SÓ DE LEITURA: idiomas que cada jogo de Switch da biblioteca traz (control.nacp, com a
atualização) e quantos arquivos de texto Nintendo (MSBT) ele tem.
Uso: python3 tools/switch_languages.py"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dc import syncer  # noqa: E402
from dc.dedup import base_title_id  # noqa: E402
from dc.paths import get_paths  # noqa: E402
from dc.traducao import converter, extract, nca, switch  # noqa: E402

keys = nca.load_keys(switch.keys_path())
lm = json.loads((get_paths().data / "launch-map.json").read_text("utf-8"))
for gid, g in lm.items():
    if g["console"] != "switch":
        continue
    t0 = time.time()
    tid = base_title_id(Path(g["rom"]).name)
    upd = extract.latest_update(converter.collect(syncer.rom_roots(), tid))
    try:
        langs = nca.game_languages(Path(g["rom"]), keys, upd)
        rfs, hs = nca.open_romfs(Path(g["rom"]), keys, upd)
        files = rfs.files()
        msbt = [p for p in files if ".msbt" in p.lower() or "/mals/" in f"/{p.lower()}" or p.lower().startswith("mals/")]
        for h in hs:
            h.close()
        pt = "✅ PT-BR OFICIAL" if "BrazilianPortuguese" in langs else ("PT (Portugal)" if "Portuguese" in langs else "sem português")
        print(f"{g['title'][:36]:36} {pt:16} msbt/mals={len(msbt):4} arquivos={len(files):5} {time.time() - t0:.0f}s "
              f"| {','.join(l[:6] for l in langs)}")
    except nca.NcaError as e:
        print(f"{g['title'][:36]:36} ERRO {e}")
