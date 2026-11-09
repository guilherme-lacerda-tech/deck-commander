"""Arquivos da engine Trinity (Game Freak): Pokémon Legends Z-A (e Scarlet/Violet, mesmo formato).

- `arc/data.trpfd` (FlatBuffers): FileHashes[u64] (ordenado), PackNames[str], FileInfo[{PackIndex}],
  PackInfo[{FileSize, FileCount}]. Cada arquivo do jogo é o FNV-1a-64 do caminho, ex.
  "ik_message/dat/English/common/bag.dat".
- `arc/data.trpfs`: "ONEPACK\\0" + u64 posição de uma tabela FlatBuffers no fim: FileHashes[u64] (hash do nome
  do pacote) e FileOffsets[u64]. Cada pacote (.trpak) é FlatBuffers: FileHashes[u64] + FileEntry[{Field_00 u32,
  EncryptionType i8 (-1 cru, 3 Oodle), Level u8, FileSize u64, FileBuffer [u8]}].
- Mod (LayeredFS): um arquivo cujo hash SAI de FileHashes/FileInfo do data.trpfd é lido do RomFS pelo caminho
  (mesma técnica do Trinity Mod Loader, gftool/pkZukan). O mod leva o data.trpfd alterado + os arquivos soltos.
Referências: github.com/pkZukan/gftool (esquemas), Q4st/SCVI_Extract.
"""
from __future__ import annotations

import bisect
import struct
from dataclasses import dataclass
from typing import Callable

from . import oodle


class TrinityError(ValueError):
    pass


def fnv1a64(s: str) -> int:
    h = 0xCBF29CE484222645
    for c in s.encode("utf-8"):
        h = ((h ^ c) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h


# ============================================================================ FlatBuffers (só leitura)
def _u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def fb_fields(b: bytes, t: int) -> list[int]:
    """Deslocamentos dos campos da tabela `t` (0 = ausente)."""
    vt = t - struct.unpack_from("<i", b, t)[0]
    if not 0 <= vt < len(b) - 4:
        raise TrinityError("vtable fora do arquivo")
    vs = struct.unpack_from("<H", b, vt)[0]
    return [struct.unpack_from("<H", b, vt + 4 + 2 * i)[0] for i in range((vs - 4) // 2)]


def fb_vec(b: bytes, t: int, i: int) -> tuple[int, int]:
    """(início dos elementos, quantidade) do vetor no campo i; (0, 0) se ausente."""
    f = fb_fields(b, t)
    if i >= len(f) or not f[i]:
        return 0, 0
    p = t + f[i]
    v = p + _u32(b, p)
    n = _u32(b, v)
    if v + 4 > len(b) or n > len(b):
        raise TrinityError("vetor fora do arquivo")
    return v + 4, n


def fb_ref(b: bytes, elem: int) -> int:
    return elem + _u32(b, elem)


def fb_scalar(b: bytes, t: int, i: int, fmt: str, default=0):
    f = fb_fields(b, t)
    if i >= len(f) or not f[i]:
        return default
    return struct.unpack_from("<" + fmt, b, t + f[i])[0]


# ============================================================================ data.trpfd
@dataclass
class FileDescriptor:
    raw: bytes
    hashes: list[int]
    pack_index: list[int]
    pack_names: list[str]

    def pack_of(self, path_hash: int) -> int | None:
        i = bisect.bisect_left(self.hashes, path_hash)
        if i < len(self.hashes) and self.hashes[i] == path_hash:
            return self.pack_index[i]
        return None


def read_trpfd(raw: bytes) -> FileDescriptor:
    root = _u32(raw, 0)
    hs, hn = fb_vec(raw, root, 0)
    ns, nn = fb_vec(raw, root, 1)
    fs, fn = fb_vec(raw, root, 2)
    if hn != fn or not hn or not nn:
        raise TrinityError("data.trpfd: tabelas incoerentes")
    hashes = list(struct.unpack_from(f"<{hn}Q", raw, hs))
    if any(a >= b for a, b in zip(hashes, hashes[1:])):
        raise TrinityError("data.trpfd: hashes fora de ordem")
    names = []
    for k in range(nn):
        s = fb_ref(raw, ns + 4 * k)
        names.append(raw[s + 4:s + 4 + _u32(raw, s)].decode("utf-8"))
    pidx = [fb_scalar(raw, fb_ref(raw, fs + 4 * k), 0, "Q") for k in range(fn)]
    if any(p >= nn for p in pidx):
        raise TrinityError("data.trpfd: pacote inexistente")
    return FileDescriptor(raw, hashes, pidx, names)


def trpfd_without(raw: bytes, remove: set[int]) -> bytes:
    """data.trpfd sem os hashes `remove` (o jogo passa a ler esses arquivos soltos do RomFS).
    Alteração no próprio lugar: os vetores FileHashes e FileInfo encolhem; o resto do arquivo é idêntico."""
    buf = bytearray(raw)
    root = _u32(buf, 0)
    hs, hn = fb_vec(buf, root, 0)
    fs, fn = fb_vec(buf, root, 2)
    hashes = struct.unpack_from(f"<{hn}Q", buf, hs)
    keep = [k for k in range(hn) if hashes[k] not in remove]
    missing = remove - set(hashes)
    if missing:
        raise TrinityError(f"{len(missing)} hash(es) não estão no data.trpfd")
    targets = [fb_ref(buf, fs + 4 * k) for k in range(fn)]
    for j, k in enumerate(keep):
        struct.pack_into("<Q", buf, hs + 8 * j, hashes[k])
        e = fs + 4 * j
        struct.pack_into("<I", buf, e, targets[k] - e)
    for j in range(len(keep), hn):
        struct.pack_into("<Q", buf, hs + 8 * j, 0)
        struct.pack_into("<I", buf, fs + 4 * j, 0)
    struct.pack_into("<I", buf, hs - 4, len(keep))
    struct.pack_into("<I", buf, fs - 4, len(keep))
    return bytes(buf)


# ============================================================================ data.trpfs
def trpfs_table_offset(head: bytes) -> int:
    if head[:8] != b"ONEPACK\0":
        raise TrinityError("data.trpfs sem assinatura ONEPACK")
    return struct.unpack_from("<Q", head, 8)[0]


def read_trpfs_table(tab: bytes) -> dict[int, int]:
    """{hash do nome do pacote: deslocamento no data.trpfs}"""
    root = _u32(tab, 0)
    hs, hn = fb_vec(tab, root, 0)
    os_, on = fb_vec(tab, root, 1)
    if hn != on:
        raise TrinityError("data.trpfs: tabela incoerente")
    return dict(zip(struct.unpack_from(f"<{hn}Q", tab, hs), struct.unpack_from(f"<{on}Q", tab, os_)))


def pack_spans(table: dict[int, int], table_off: int) -> dict[int, tuple[int, int]]:
    """{hash do pacote: (início, tamanho)} — cada pacote vai até o começo do próximo."""
    starts = sorted(set(table.values())) + [table_off]
    out = {}
    for h, o in table.items():
        nxt = starts[bisect.bisect_right(starts, o)]
        out[h] = (o, nxt - o)
    return out


# ============================================================================ pacote .trpak
@dataclass
class PackedFile:
    hash: int
    enc: int
    size: int
    data: bytes   # como está no pacote

    def content(self) -> bytes:
        if self.enc == -1:
            out = self.data
        elif self.enc == 3:
            out = oodle.decompress(self.data, self.size)
        else:
            raise TrinityError(f"compressão {self.enc} desconhecida")
        if len(out) != self.size:
            raise TrinityError("tamanho descomprimido não confere")
        return out


def read_pack(raw: bytes) -> list[PackedFile]:
    root = _u32(raw, 0)
    hs, hn = fb_vec(raw, root, 0)
    es, en = fb_vec(raw, root, 1)
    if hn != en:
        raise TrinityError("pacote incoerente")
    hashes = struct.unpack_from(f"<{hn}Q", raw, hs)
    out = []
    for k in range(en):
        t = fb_ref(raw, es + 4 * k)
        enc = fb_scalar(raw, t, 1, "b", -1)
        size = fb_scalar(raw, t, 3, "Q", 0)
        bs, bn = fb_vec(raw, t, 4)
        if bs + bn > len(raw):
            raise TrinityError("dados do arquivo fora do pacote")
        out.append(PackedFile(hashes[k], enc, size, bytes(raw[bs:bs + bn])))
    return out


# ============================================================================ acesso ao jogo
class Archive:
    """Lê arquivos do jogo a partir de `read(off, size)` sobre o data.trpfs e do data.trpfd."""

    def __init__(self, trpfd: bytes, read: Callable[[int, int], bytes], trpfs_size: int):
        self.fd = read_trpfd(trpfd)
        self.read = read
        toff = trpfs_table_offset(read(0, 16))
        if not 0 < toff < trpfs_size:
            raise TrinityError("tabela do data.trpfs fora do arquivo")
        self.spans = pack_spans(read_trpfs_table(read(toff, trpfs_size - toff)), toff)
        self._cache: dict[int, list[PackedFile]] = {}

    def pack_name_of(self, path: str) -> str | None:
        i = self.fd.pack_of(fnv1a64(path))
        return None if i is None else self.fd.pack_names[i]

    def pack(self, name: str) -> list[PackedFile]:
        h = fnv1a64(name)
        if h not in self._cache:
            if h not in self.spans:
                raise TrinityError(f"pacote {name} não está no data.trpfs")
            o, n = self.spans[h]
            self._cache[h] = read_pack(self.read(o, n))
        return self._cache[h]

    def get(self, path: str) -> bytes:
        name = self.pack_name_of(path)
        if name is None:
            raise TrinityError(f"{path} não está no data.trpfd")
        h = fnv1a64(path)
        for f in self.pack(name):
            if f.hash == h:
                return f.content()
        raise TrinityError(f"{path} não está no pacote {name}")
