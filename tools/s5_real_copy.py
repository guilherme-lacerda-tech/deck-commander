#!/usr/bin/env python3
"""S5 no Deck: aplica os 3 perfis numa CÓPIA dos arquivos reais e confere read-back.
Nunca toca nos arquivos originais (confere hash antes/depois)."""
import hashlib
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dc.adapters import PROFILES, get_adapter  # noqa: E402

H = Path.home()
REAL = {"duckstation": (H / ".local/share/duckstation/settings.ini", "ps1"),
        "pcsx2": (H / ".var/app/net.pcsx2.PCSX2/config/PCSX2/inis/PCSX2.ini", "ps2")}
WORK = H / "deck-commander-spikes/s5"
ok = True
for emu, (src, console) in REAL.items():
    if not src.exists():
        print(f"{emu}: não instalado ({src})"); continue
    h0 = hashlib.sha256(src.read_bytes()).hexdigest()
    ad = get_adapter(emu)
    for prof in PROFILES:
        d = WORK / emu / prof; d.mkdir(parents=True, exist_ok=True)
        cp = d / src.name; shutil.copy2(src, cp)
        before = cp.read_bytes().splitlines(keepends=True)
        ch = ad.apply(cp, console, prof, d / "state.json", force=True, dry_run=False)
        ad.read_back(cp, console, prof)
        after = cp.read_bytes().splitlines(keepends=True)
        diff = sum(1 for a, b in zip(before, after) if a != b)
        good = len(before) == len(after) and diff == len(ch)
        ok &= good
        print(f"{emu:12} {prof:12} mudanças={[f'{c.key}:{c.old}->{c.new}' for c in ch]} "
              f"linhas_alteradas={diff} {'OK' if good else 'FALHOU'}")
    intact = hashlib.sha256(src.read_bytes()).hexdigest() == h0
    ok &= intact
    print(f"{emu}: arquivo original intacto = {intact}")
print("S5 (cópias):", "PASSOU" if ok else "FALHOU")
sys.exit(0 if ok else 1)
