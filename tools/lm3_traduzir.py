"""Traduz o Luigi's Mansion 3 fora da fila do bot (mesmo código e mesmo cache do /traduzir).

python3 tools/lm3_traduzir.py [--sem-instalar]
Útil quando a fila está cheia: depois, o /traduzir do bot reaproveita o cache e termina na hora.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dc import syncer  # noqa: E402
from dc.paths import get_paths  # noqa: E402
from dc.traducao import lm3  # noqa: E402

TID = "0100DCA0064A6000"


def main() -> None:
    paths = get_paths().ensure()
    lm = json.loads((paths.data / "launch-map.json").read_text("utf-8"))
    g = next(v for v in lm.values() if TID in v.get("rom", ""))
    t0 = time.time()
    patch = lm3.fetch_patch(Path(g["rom"]), TID, syncer.rom_roots())
    print(f"init.patch: {patch} ({time.time() - t0:.0f}s)", flush=True)
    last = [0.0]

    def progress(d, t):
        if time.time() - last[0] > 30 or d == t:
            last[0] = time.time()
            print(f"progresso {d}/{t} ({time.time() - t0:.0f}s)", flush=True)
    rep = lm3.translate_game(paths, TID, patch, g.get("title", ""), progress=progress,
                             install="--sem-instalar" not in sys.argv)
    print(rep.text(), flush=True)
    for s in rep.flagged_samples[:10]:
        print("  •", s, flush=True)


if __name__ == "__main__":
    main()
