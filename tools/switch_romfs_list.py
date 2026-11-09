#!/usr/bin/env python3
"""Diagnóstico SÓ DE LEITURA: abre cada jogo de Switch da biblioteca (base + atualização), monta o
RomFS e lista quantos arquivos de texto/fonte existem. Não grava nada.
Uso: python3 tools/switch_romfs_list.py [parte do nome]"""
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
q = (sys.argv[1] if len(sys.argv) > 1 else "").lower()
for gid, g in lm.items():
    if g["console"] != "switch" or q not in g["title"].lower():
        continue
    t0 = time.time()
    tid = base_title_id(Path(g["rom"]).name)
    upd = extract.latest_update(converter.collect(syncer.rom_roots(), tid))
    try:
        rfs, hs = nca.open_romfs(Path(g["rom"]), keys, upd)
        files = rfs.files()
        texts = extract.text_files(files)
        size = sum(files[p][1] for p in texts)
        print(f"OK  {g['title'][:38]:38} {tid} upd={'sim' if upd else 'não'} arquivos={len(files)} "
              f"texto={len(texts)} ({size / 1e6:.1f} MB) {time.time() - t0:.0f}s  ex: {texts[:2]}")
        for h in hs:
            h.close()
    except nca.NcaError as e:
        print(f"ERRO {g['title'][:38]:38} {tid} {e}")
