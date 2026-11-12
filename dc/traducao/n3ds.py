"""Leitor de jogos de 3DS DESCRIPTOGRAFADOS (.3ds/.cci = NCSD, .cxi = NCCH) e do RomFS deles.

Para traduzir não é preciso remontar o jogo: o Azahar carrega arquivos de
`load/mods/<TitleID>/romfs/` por cima do original (LayeredFS), igual ao Ryujinx no Switch.
Dump criptografado é recusado com a explicação (o Azahar também não roda esses).
Referência dos formatos: 3dbrew (NCSD, NCCH, RomFS/IVFC). Tudo little-endian; media unit = 0x200.
"""
from __future__ import annotations

import struct
from collections.abc import Callable
from pathlib import Path

MU = 0x200
NONE = 0xFFFFFFFF


class FormatError(ValueError):
    pass


class Encrypted(FormatError):
    pass


class Game3DS:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.files: dict[str, tuple[int, int]] = {}  # caminho -> (posição absoluta no arquivo, tamanho)
        with open(self.path, "rb") as f:
            head = f.read(0x200)
            if head[0x100:0x104] == b"NCSD":
                off = struct.unpack_from("<I", head, 0x120)[0] * MU  # partição 0 = o jogo
                f.seek(off)
                head = f.read(0x200)
            elif head[0x100:0x104] == b"NCCH":
                off = 0
            else:
                raise FormatError("não é um jogo de 3DS (.3ds/.cci/.cxi)")
            if head[0x100:0x104] != b"NCCH":
                raise FormatError("partição do jogo sem cabeçalho NCCH")
            self.title_id = f"{struct.unpack_from('<Q', head, 0x118)[0]:016X}"
            if not head[0x188 + 7] & 0x04:
                raise Encrypted("o dump está criptografado: refaça com o GodMode9 em modo decrypted")
            rom_off, rom_size = struct.unpack_from("<II", head, 0x1B0)
            if not rom_size:
                raise FormatError("jogo sem RomFS (arquivos)")
            self._index(f, off + rom_off * MU)

    def _index(self, f, romfs: int) -> None:
        f.seek(romfs)
        ivfc = f.read(0x60)
        if ivfc[:4] != b"IVFC":
            raise FormatError("RomFS sem cabeçalho IVFC")
        master = struct.unpack_from("<I", ivfc, 0x08)[0]
        log2 = struct.unpack_from("<I", ivfc, 0x0C + 2 * 0x18 + 0x10)[0]
        blk = 1 << log2
        lv3 = romfs + (0x60 + master + blk - 1) // blk * blk
        f.seek(lv3)
        _, _, _, dm_off, dm_len, _, _, fm_off, fm_len, fd_off = struct.unpack("<10I", f.read(0x28))
        f.seek(lv3 + dm_off)
        dmeta = f.read(dm_len)
        f.seek(lv3 + fm_off)
        fmeta = f.read(fm_len)
        data0 = lv3 + fd_off

        def name(buf: bytes, at: int, n: int) -> str:
            return buf[at:at + n].decode("utf-16-le")

        def walk_dir(off: int, prefix: str, depth: int = 0) -> None:
            if depth > 64:
                raise FormatError("RomFS com pastas em laço")
            _, _, child, first_file, _, _ = struct.unpack_from("<6I", dmeta, off)
            fo = first_file
            while fo != NONE:
                _, sib, doff, dsize, _, fnl = struct.unpack_from("<IIQQII", fmeta, fo)
                self.files[prefix + name(fmeta, fo + 0x20, fnl)] = (data0 + doff, dsize)
                fo = sib
            co = child
            while co != NONE:
                _, csib, _, _, _, cnl = struct.unpack_from("<6I", dmeta, co)
                walk_dir(co, prefix + name(dmeta, co + 0x18, cnl) + "/", depth + 1)
                co = csib

        walk_dir(0, "")

    def list_files(self) -> list[str]:
        return sorted(self.files)

    def read(self, rel: str) -> bytes:
        off, size = self.files[rel]
        with open(self.path, "rb") as f:
            f.seek(off)
            return f.read(size)

    def extract(self, dest: Path, keep: Callable[[str], bool] = lambda rel: True) -> int:
        n = 0
        for rel in self.list_files():
            if keep(rel):
                out = Path(dest) / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(self.read(rel))
                n += 1
        return n


def open_game(path: Path) -> Game3DS:
    return Game3DS(path)


def mod_dir(title_id: str, home: Path = Path.home()) -> Path:
    """Pasta de mods do Azahar (flatpak) para o jogo: o romfs/ do mod vai dentro dela."""
    return home / ".var/app/org.azahar_emu.Azahar/data/azahar-emu/load/mods" / title_id.upper()
