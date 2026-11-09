"""Lista (e opcionalmente copia) arquivos do RomFS de um jogo de Switch (base + atualização).

python3 tools/lm3_listar.py <TitleID> [regex] [--dump DEST]
Só lê o jogo; nunca altera nada. Lento (AES em Python puro): copie só o necessário.
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dc import syncer  # noqa: E402
from dc.traducao import converter, extract, nca, switch  # noqa: E402


def main() -> None:
    tid = sys.argv[1].upper()
    pat = re.compile(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else None
    dest = Path(sys.argv[sys.argv.index("--dump") + 1]) if "--dump" in sys.argv else None
    tf = converter.collect(syncer.rom_roots(), tid)
    base = next(p for p in tf.base if p.suffix.lower() == ".nsp") if tf.base else None
    upd = extract.latest_update(tf)
    print("base:", base, "\nupdate:", upd, flush=True)
    rfs, hs = nca.open_romfs(base, nca.load_keys(switch.keys_path()), upd)
    try:
        files = rfs.files()
        sel = {p: v for p, v in sorted(files.items()) if not pat or pat.search(p)}
        for p, (off, size) in sel.items():
            print(f"{size:12d} {p}", flush=True)
        print(f"{len(sel)} de {len(files)} arquivos, {sum(s for _, s in sel.values()) / 1e6:.1f} MB", flush=True)
        if dest:
            for p, (off, size) in sel.items():
                out = dest / p
                if out.exists() and out.stat().st_size == size:
                    continue
                out.parent.mkdir(parents=True, exist_ok=True)
                t = time.time()
                tmp = out.with_name(out.name + ".part")
                with open(tmp, "wb") as f:
                    pos = 0
                    while pos < size:
                        n = min(8 << 20, size - pos)
                        f.write(rfs.read_at(off + pos, n))
                        pos += n
                tmp.rename(out)
                print(f"copiado {p} ({size / 1e6:.1f} MB em {time.time() - t:.0f}s)", flush=True)
    finally:
        for h in hs:
            h.close()


if __name__ == "__main__":
    main()
