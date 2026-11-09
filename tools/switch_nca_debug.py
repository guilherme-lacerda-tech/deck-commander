#!/usr/bin/env python3
"""Diagnóstico SÓ DE LEITURA do leitor de NCA: mostra seções, tipo de criptografia e o começo do RomFS
do jogo-base e da atualização. Uso: python3 tools/switch_nca_debug.py <base.nsp> [update.nsp]"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dc.traducao import nca, switch  # noqa: E402

keys = nca.load_keys(switch.keys_path())
for p in sys.argv[1:]:
    f, n = nca.open_program(Path(p), keys)
    print(Path(p).name[:50], "tid", hex(n.title_id), "rights", n.rights_id.hex()[:8], "ctype", n.content_type)
    for s in n.sections:
        print(f"  seção {s.index}: fs={s.fs_type} enc={s.enc} hash={s.fsh[3]} start={s.start:#x} size={s.size:#x}"
              f" ivfc={s.fsh[8:12]} upper={s.upper.hex()} patchinfo={s.fsh[0x100:0x140].hex()[:64]}")
    sec = n.romfs_section()
    off, size = sec.ivfc_romfs()
    head = n.read_plain(sec, off, 0x50)
    print("  romfs@", hex(off), "header:", struct.unpack_from("<10Q", head, 0))
    vals = struct.unpack_from("<10Q", head, 0)
    if vals[0] == 0x50:
        d = n.read_plain(sec, off + vals[3], 0x40)
        print("  dir0:", struct.unpack_from("<IIIIII", d, 0), d[0x18:0x30])
