#!/usr/bin/env python3
"""Diagnóstico SÓ DE LEITURA: roda a varredura de textos do Switch num RomFS real e mostra o que daria
para traduzir (quantos MSBT, frases, pacotes, compressão, fonte) e se cada arquivo sobrevive a
ler+regravar sem mudar nada. Não grava nada no RomFS nem instala mod.
Uso: python3 tools/switch_text_check.py <pasta romfs> [idioma_origem]"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dc.traducao import nx, switch  # noqa: E402

romfs = Path(sys.argv[1])
rep = switch.Report("check")
files, containers = switch.scan(romfs, rep, sys.argv[2] if len(sys.argv) > 2 else "en")
strings = sum(len(f.msbt.strings) for f in files)
tags = sum(1 for f in files for parts in f.msbt.strings for p in parts if isinstance(p, bytes))
print(f"MSBT: {len(files)} · frases: {strings} · tags: {tags} · pacotes: {len(containers)}")
print("compressão:", sorted(rep.compression), "· fonte:", rep.font)
print("pulados:", len(rep.skipped_files), rep.skipped_files[:5])
# recompressão e pacote: conferidos de ponta a ponta sem alterar texto
bad = 0
for rel, (sarc, kind, raw) in list(containers.items())[:50]:
    if sarc is None:
        continue
    data = nx.write_sarc(sarc)
    packed = nx.pack_layer(data, kind)
    again = nx.read_sarc(nx.unpack_layer(rel, packed)[0])
    if again.files != sarc.files:
        bad += 1
        print("FALHA pacote", rel)
print("pacotes regravados e conferidos:", min(50, len(containers)) - bad, "falhas:", bad)
for f in files[:3]:
    for i, (t, tg) in enumerate(f.msbt.texts()[:3]):
        print(f"  {f.rel}:{f.inner}#{f.msbt.labels.get(i, i)} | {t[:90]!r}")
print("RESULTADO:", "OK" if files and not bad else "VER ACIMA")
