"""PC: descompacta os textos (.locres) de um jogo Unreal de Switch que usam Oodle e guarda no Deck.

O Deck não tem Oodle (compressor comercial). Muitos jogos de PC trazem a biblioteca dele
(oo2core_*_win64.dll); este script usa a que achar nos SEUS jogos instalados, só para descompactar.

Uso:  python tools/pc/oodle_locres.py <TitleID> [deck@IP]
Depois: /traduzir <jogo> no bot.
"""
import ctypes
import os
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dc.traducao import unreal  # noqa: E402

KEY = Path.home() / ".ssh/deck_commander_ed25519"
CFG = Path.home() / ".deck-commander-pc.txt"
SEARCH = ["Program Files (x86)/Steam/steamapps/common", "SteamLibrary/steamapps/common", "Program Files/Epic Games",
          "Games", "XboxGames"]

DECK_SIDE = r'''
import sys, os, json, struct
sys.path.insert(0, os.path.expanduser("~/deck-commander"))
from pathlib import Path
from dc import syncer
from dc.traducao import nca, switch, unreal, converter, extract
tid = sys.argv[1].upper()
m = json.load(open(os.path.expanduser("~/.local/share/deck-commander/launch-map.json")))
rom = next(Path(v["rom"]) for v in m.values() if v.get("console") == "switch" and tid in v.get("rom", "").upper())
upd = extract.latest_update(converter.collect(syncer.rom_roots(), tid))
rfs, h = nca.open_romfs(rom, nca.load_keys(switch.keys_path()), upd)
files = rfs.files()
out = sys.stdout.buffer
for pk in unreal.main_paks(files):
    o, s = files[pk]
    rd = lambda a, n, o=o: rfs.read_at(o + a, n)
    pak = unreal.read_pak(rd, s)
    for lp in unreal.game_locres(pak):
        e = pak.entries[lp]
        name = lp.encode()
        out.write(struct.pack("<I", len(name)) + name + struct.pack("<II", e.usize, len(e.blocks)))
        for k, (a, b) in enumerate(e.blocks):
            want = min(e.block_size, e.usize - k * e.block_size)
            d = rd(a, b - a)
            out.write(struct.pack("<II", len(d), want) + d)
'''


def find_dll() -> Path:
    for drive in "CDEFGH":
        for s in SEARCH:
            base = Path(f"{drive}:/") / s
            if base.is_dir():
                for p in base.rglob("oo2core_*_win64.dll"):
                    return p
    raise SystemExit("Não achei oo2core_*_win64.dll em nenhum jogo instalado neste PC.")


def decompressor(dll: Path):
    f = ctypes.WinDLL(str(dll)).OodleLZ_Decompress
    f.restype = ctypes.c_int64
    f.argtypes = [ctypes.c_void_p, ctypes.c_int64, ctypes.c_void_p, ctypes.c_int64] + [ctypes.c_int] * 3 + [
        ctypes.c_void_p, ctypes.c_int64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int64,
        ctypes.c_int]

    def run(src: bytes, want: int) -> bytes:
        dst = ctypes.create_string_buffer(want)
        got = f(src, len(src), dst, want, 1, 0, 0, None, 0, None, None, None, 0, 3)
        if got != want:
            raise SystemExit(f"Oodle falhou num bloco ({got} != {want})")
        return dst.raw
    return run


def main() -> None:
    tid = sys.argv[1].upper()
    deck = sys.argv[2] if len(sys.argv) > 2 else (CFG.read_text().strip() if CFG.exists() else "")
    if not deck:  # nada fixo deste PC: o endereço vem do argumento ou do arquivo que o instalar-tunel-ia.ps1 grava
        raise SystemExit(f"Diga o Deck: oodle_locres.py <TitleID> deck@<ip-do-deck>  (ou grave-o em {CFG})")
    ssh = ["ssh", "-i", str(KEY), "-o", "BatchMode=yes", deck]
    raw = subprocess.run(ssh + ["python3", "-", tid], input=DECK_SIDE.encode(), capture_output=True, check=True).stdout
    dec = decompressor(find_dll())
    p, n = 0, 0
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "descompactado"
        while p < len(raw):
            ln, = struct.unpack_from("<I", raw, p); p += 4
            name = raw[p:p + ln].decode(); p += ln
            usize, nb = struct.unpack_from("<II", raw, p); p += 8
            data = bytearray()
            for _ in range(nb):
                cl, want = struct.unpack_from("<II", raw, p); p += 8
                data += dec(raw[p:p + cl], want); p += cl
            if len(data) != usize:
                raise SystemExit(f"{name}: tamanho não confere")
            loc = unreal.read_locres(bytes(data))  # confere se abriu certo antes de mandar
            print(f"{name}: {len(loc.entries)} frases")
            out = root / name
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
            n += 1
        if not n:
            raise SystemExit("O jogo não tem .locres de texto.")
        dest = f"~/.local/share/deck-commander/traducao/unreal/{tid}"
        tar = subprocess.run(["tar", "-C", tmp, "-cf", "-", "descompactado"], capture_output=True, check=True).stdout
        subprocess.run(ssh + [f"mkdir -p {dest} && tar -C {dest} -xf -"], input=tar, check=True)
    print(f"Pronto: {n} arquivo(s) no Deck. Agora mande /traduzir no bot.")


if __name__ == "__main__":
    if os.name != "nt":
        raise SystemExit("Rode no PC (Windows).")
    main()
