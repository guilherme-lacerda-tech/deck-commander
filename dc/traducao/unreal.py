"""Unreal Engine 4/5: ler o índice de um .pak (v8–v11, sem criptografia), o .locres (textos) e gravar um
pak de mod "_P" sem compressão, que o jogo carrega por cima do original (LayeredFS no Switch).

Formatos (documentação pública da UE / ferramentas abertas como repak e UnrealLocres):
- rodapé do pak: guid(16) + índice_criptografado(1) + magic 0x5A6F12E1 + versão(4) + offset(8) + tamanho(8) + hash(20)
  [+ 5×32 nomes de compressão a partir da v8];
- índice v10+: ponto de montagem, entradas codificadas em bits e "índice de diretório completo";
- .locres v2/v3: tabela de textos únicos + namespaces → chaves → índice do texto.
"""
from __future__ import annotations

import hashlib
import io
import struct
from dataclasses import dataclass
from typing import Callable

PAK_MAGIC = 0x5A6F12E1
LOCRES_MAGIC = bytes.fromhex("0E147475674A03FC4A15909DC3377F1B")


class UnrealError(ValueError):
    pass


Read = Callable[[int, int], bytes]  # (deslocamento, tamanho) -> bytes


# ------------------------------------------------------------------ leitura de FString / helpers
class _R:
    def __init__(self, b: bytes, pos: int = 0):
        self.b, self.p = b, pos

    def take(self, n: int) -> bytes:
        if self.p + n > len(self.b):
            raise UnrealError("dados terminaram antes do esperado")
        v = self.b[self.p:self.p + n]
        self.p += n
        return v

    def u8(self): return self.take(1)[0]
    def i32(self): return struct.unpack("<i", self.take(4))[0]
    def u32(self): return struct.unpack("<I", self.take(4))[0]
    def i64(self): return struct.unpack("<q", self.take(8))[0]
    def u64(self): return struct.unpack("<Q", self.take(8))[0]

    def fstr(self) -> str:
        n = self.i32()
        if n == 0:
            return ""
        if n > 0:
            if n > 1 << 20:
                raise UnrealError("texto grande demais")
            return self.take(n)[:-1].decode("utf-8", "replace")
        n = -n
        if n > 1 << 20:
            raise UnrealError("texto grande demais")
        return self.take(n * 2)[:-2].decode("utf-16-le", "replace")


def _w_fstr(s: str) -> bytes:
    if not s:
        return struct.pack("<i", 0)
    try:
        b = s.encode("ascii") + b"\0"
        return struct.pack("<i", len(b)) + b
    except UnicodeEncodeError:
        b = s.encode("utf-16-le") + b"\0\0"
        return struct.pack("<i", -(len(b) // 2)) + b


# ------------------------------------------------------------------ pak
@dataclass
class PakEntry:
    path: str
    offset: int          # início do cabeçalho da entrada no pak
    size: int            # tamanho gravado (comprimido)
    usize: int           # tamanho real
    method: str          # "" = sem compressão
    blocks: list         # [(início, fim)] absolutos no pak
    block_size: int
    encrypted: bool


@dataclass
class Pak:
    version: int
    mount: str
    methods: list
    entries: dict        # caminho completo (com ponto de montagem) -> PakEntry


def _entry_header_size(version: int, compressed: bool, nblocks: int) -> int:
    n = 8 + 8 + 8 + 4 + 20  # offset, size, usize, método, hash
    if compressed:
        n += 4 + nblocks * 16
    return n + 1 + 4  # criptografado, tamanho do bloco


def read_pak(read: Read, size: int) -> Pak:
    tail = read(size - 221, 221)
    i = tail.find(struct.pack("<I", PAK_MAGIC))
    if i < 17:
        raise UnrealError("rodapé de pak não encontrado")
    encrypted_index = tail[i - 1]
    version, idx_off, idx_size = struct.unpack_from("<IQQ", tail, i + 4)
    if encrypted_index:
        raise UnrealError("índice do pak criptografado (precisa da chave AES do jogo)")
    if version < 10:
        raise UnrealError(f"pak versão {version}: só leio v10 ou mais nova")
    names = tail[i + 4 + 4 + 8 + 8 + 20:]
    methods = [""] + [names[k:k + 32].split(b"\0")[0].decode() for k in range(0, len(names) - 31, 32)]
    r = _R(read(idx_off, idx_size))
    mount = r.fstr()
    _count = r.i32()
    r.u64()  # semente do hash
    if r.u32():
        r.take(8 + 8 + 20)
    if not r.u32():
        raise UnrealError("pak sem índice de diretório completo")
    fdi_off, fdi_size = r.i64(), r.i64()
    r.take(20)
    enc = r.take(r.i32())
    _n_plain = r.i32()  # entradas não codificadas (raras; não usadas aqui)

    def decode(pos: int) -> PakEntry:
        e = _R(enc, pos)
        bits = e.u32()
        bsz = (bits & 0x3F) << 11
        if (bits & 0x3F) == 0x3F:
            bsz = e.u32()
        nblocks = (bits >> 6) & 0xFFFF
        encrypted = bool(bits & (1 << 22))
        mi = (bits >> 23) & 0x3F
        off = e.u32() if bits & (1 << 31) else e.u64()
        usize = e.u32() if bits & (1 << 30) else e.u64()
        csize = (e.u32() if bits & (1 << 29) else e.u64()) if mi else usize
        hdr = _entry_header_size(version, mi != 0, nblocks)
        blocks = []
        if mi and nblocks:
            if nblocks == 1 and not encrypted:
                blocks = [(off + hdr, off + hdr + csize)]
            else:
                start = off + hdr
                for _ in range(nblocks):
                    n = e.u32()
                    blocks.append((start, start + n))
                    start += (n + 15) & ~15 if encrypted else n
        return PakEntry("", off, csize, usize, methods[mi] if mi < len(methods) else f"#{mi}",
                        blocks, bsz, encrypted)

    entries = {}
    d = _R(read(fdi_off, fdi_size))
    for _ in range(d.i32()):
        dname = d.fstr()
        for _ in range(d.i32()):
            fname = d.fstr()
            pos = d.i32()
            if pos < 0:
                continue  # entrada não codificada: ignorada
            ent = decode(pos)
            ent.path = (mount + dname.lstrip("/") + fname).replace("../../../", "")
            entries[ent.path] = ent
    return Pak(version, mount, methods, entries)


def read_entry(read: Read, ent: PakEntry, decompress: Callable[[str, bytes, int], bytes] | None = None) -> bytes:
    if ent.encrypted:
        raise UnrealError(f"{ent.path}: arquivo criptografado")
    if not ent.method:
        hdr = _entry_header_size(0, False, 0)
        return read(ent.offset + hdr, ent.usize)
    if decompress is None:
        raise UnrealError(f"{ent.path}: comprimido com {ent.method} e não tenho o descompressor")
    out = bytearray()
    for k, (a, b) in enumerate(ent.blocks):
        want = min(ent.block_size, ent.usize - k * ent.block_size)
        out += decompress(ent.method, read(a, b - a), want)
    if len(out) != ent.usize:
        raise UnrealError(f"{ent.path}: tamanho descompactado não confere")
    return bytes(out)


def write_pak(files: dict[str, bytes], mount: str = "../../../", version: int = 11) -> bytes:
    """Pak de mod sem compressão e sem criptografia, com índice v10+ (só índice de diretório completo)."""
    body = io.BytesIO()
    enc = io.BytesIO()
    dirs: dict[str, dict[str, int]] = {}
    for path in sorted(files):
        data = files[path]
        off = body.tell()
        sha = hashlib.sha1(data).digest()
        body.write(struct.pack("<qqqI", 0, len(data), len(data), 0) + sha + b"\0" + struct.pack("<I", 0))
        body.write(data)
        pos = enc.tell()
        small = off < 1 << 32 and len(data) < 1 << 32
        bits = (1 << 31 | 1 << 30 | 1 << 29) if small else 0
        enc.write(struct.pack("<I", bits))
        enc.write(struct.pack("<II", off, len(data)) if small else struct.pack("<QQ", off, len(data)))
        d, _, f = path.rpartition("/")
        dirs.setdefault(d + "/" if d else "/", {})[f] = pos
    fdi = io.BytesIO()
    fdi.write(struct.pack("<i", len(dirs)))
    for d, fs in dirs.items():
        fdi.write(_w_fstr(d))
        fdi.write(struct.pack("<i", len(fs)))
        for f, pos in fs.items():
            fdi.write(_w_fstr(f) + struct.pack("<i", pos))
    fdi_b = fdi.getvalue()
    idx_off = body.tell()
    fdi_off_placeholder = None
    idx = io.BytesIO()
    idx.write(_w_fstr(mount))
    idx.write(struct.pack("<iQ", len(files), 0))
    idx.write(struct.pack("<I", 0))  # sem índice por hash
    idx.write(struct.pack("<I", 1))
    fdi_off_placeholder = idx.tell()
    idx.write(struct.pack("<qq", 0, len(fdi_b)) + hashlib.sha1(fdi_b).digest())
    e = enc.getvalue()
    idx.write(struct.pack("<i", len(e)) + e + struct.pack("<i", 0))
    ib = bytearray(idx.getvalue())
    struct.pack_into("<q", ib, fdi_off_placeholder, idx_off + len(ib))
    out = bytearray(body.getvalue()) + ib + fdi_b
    footer = (b"\0" * 16 + b"\0" + struct.pack("<IIQQ", PAK_MAGIC, version, idx_off, len(ib))
              + hashlib.sha1(bytes(ib)).digest() + b"\0" * 32 * 5)
    return bytes(out) + footer


# ------------------------------------------------------------------ locres
@dataclass
class Locres:
    version: int
    entries: list  # [(namespace, chave, hash_fonte, texto)]


def read_locres(b: bytes) -> Locres:
    r = _R(b)
    if b[:16] == LOCRES_MAGIC:
        r.take(16)
        version = r.u8()
    else:
        version = 0
    if version == 0:
        raise UnrealError("locres antigo (v0) ainda não suportado")
    table_off = r.i64()
    t = _R(b, table_off)
    texts = []
    for _ in range(t.i32()):
        s = t.fstr()
        if version >= 2:
            t.i32()  # contagem de referências
        texts.append(s)
    if version >= 2:
        r.u32()  # total de entradas
    out = []
    for _ in range(r.u32()):
        if version >= 2:
            r.u32()
        ns = r.fstr()
        for _ in range(r.u32()):
            if version >= 2:
                r.u32()
            key = r.fstr()
            src_hash = r.u32()
            out.append((ns, key, src_hash, texts[r.i32()]))
    return Locres(version, out)


def write_locres(loc: Locres) -> bytes:
    """Grava v2 (CompactLocRes, aceito pela UE 4.20+ e UE5)."""
    texts: list[str] = []
    refs: dict[str, int] = {}
    count: dict[int, int] = {}
    nss: dict[str, list] = {}
    for ns, key, h, s in loc.entries:
        if s not in refs:
            refs[s] = len(texts)
            texts.append(s)
        count[refs[s]] = count.get(refs[s], 0) + 1
        nss.setdefault(ns, []).append((key, h, refs[s]))
    body = io.BytesIO()
    body.write(struct.pack("<I", len(loc.entries)))
    body.write(struct.pack("<I", len(nss)))
    for ns, keys in nss.items():
        body.write(struct.pack("<I", _str_hash(ns)) + _w_fstr(ns) + struct.pack("<I", len(keys)))
        for key, h, i in keys:
            body.write(struct.pack("<I", _str_hash(key)) + _w_fstr(key) + struct.pack("<Ii", h, i))
    head = LOCRES_MAGIC + bytes([2])
    table_off = len(head) + 8 + len(body.getvalue())
    table = io.BytesIO()
    table.write(struct.pack("<i", len(texts)))
    for i, s in enumerate(texts):
        table.write(_w_fstr(s) + struct.pack("<i", count[i]))
    return head + struct.pack("<q", table_off) + body.getvalue() + table.getvalue()


# CRC32 das chaves de texto (FCrc::StrCrc32, usado pelo locres v2+)
_CRC_TABLE = []
for _n in range(256):
    _c = _n
    for _ in range(8):
        _c = (_c >> 1) ^ 0xEDB88320 if _c & 1 else _c >> 1
    _CRC_TABLE.append(_c)


def _str_hash(s: str) -> int:
    """FCrc::StrCrc32: CRC32 sobre cada caractere como 4 bytes (UTF-32 little-endian), ~0 no início e no fim."""
    crc = 0xFFFFFFFF
    for ch in s:
        c = ord(ch)
        for _ in range(4):
            crc = (crc >> 8) ^ _CRC_TABLE[(crc ^ c) & 0xFF]
            c >>= 8
    return crc ^ 0xFFFFFFFF


# ------------------------------------------------------------------ jogo inteiro (Switch, Unreal)
import json  # noqa: E402
import re  # noqa: E402
from pathlib import Path  # noqa: E402

MOD_PAK = "zz_DeckCommander_PTBR_P.pak"  # "_P" = prioridade sobre o pak original; "zz" = carrega por último
CODES = re.compile(r"<[^>]*>|\{[^}]*\}|\r?\n|\[TEMP\]")
_LETTERS = re.compile(r"[^\W\d_]{2}")


def game_locres(pak: Pak, lang: str = "en") -> list[str]:
    """Textos do jogo (não os da Unreal nem menus de depuração) no idioma de origem."""
    out = []
    for p in pak.entries:
        if p.endswith(".locres") and f"/Localization/" in p and f"/{lang}/" in p and not p.startswith("Engine/") \
                and "/DebugMenu/" not in p:
            out.append(p)
    return sorted(out)


def cache_dir(data: Path, title_id: str) -> Path:
    return data / "traducao" / "unreal" / title_id.upper()


def cached_plain(data: Path, title_id: str, path: str) -> bytes | None:
    """Arquivo já descompactado (pelo PC, que tem o Oodle de um jogo seu) guardado para este jogo."""
    p = cache_dir(data, title_id) / "descompactado" / path
    try:
        return p.read_bytes()
    except OSError:
        return None


def translate_locres(paths, cfg: dict, data: bytes, job: str, title: str, chain=None,
                     progress=lambda d, t: None, should_pause=lambda: False):
    """Traduz um .locres inteiro. Devolve (bytes novos, Result do tradutor, quantas frases trocou)."""
    from . import ia
    loc = read_locres(data)
    uniq: dict[str, tuple[str, list[str]]] = {}
    for _ns, _k, _h, s in loc.entries:
        if s not in uniq and _LETTERS.search(CODES.sub(" ", s)):
            uniq[s] = ia.protect(s, CODES)
    items = [ia.Item(hashlib.sha1(s.encode()).hexdigest()[:16], p) for s, (p, _c) in uniq.items()]
    res = ia.translate(paths, cfg, items, job, ia.load_glossary(paths, title), chain=chain,
                       progress=progress, should_pause=should_pause)
    new_text = {}
    for s, (_p, codes) in uniq.items():
        t = res.translated.get(hashlib.sha1(s.encode()).hexdigest()[:16])
        if t:
            new_text[s] = ia.restore(t, codes)
    entries = [(ns, k, h, new_text.get(s, s)) for ns, k, h, s in loc.entries]
    changed = sum(1 for e, o in zip(entries, loc.entries) if e[3] != o[3])
    return write_locres(Locres(loc.version, entries)), res, changed


def build_mod(files: dict[str, bytes], mod_romfs: Path, project: str) -> Path:
    """Grava o pak de mod em <romfs do mod>/<Projeto>/Content/Paks/~mods/ (o jogo original não é tocado)."""
    dst = mod_romfs / project / "Content" / "Paks" / "~mods"
    dst.mkdir(parents=True, exist_ok=True)
    out = dst / MOD_PAK
    blob = write_pak(files)
    check = read_pak(lambda a, n: blob[a:a + n], len(blob))
    for p, b in files.items():
        if read_entry(lambda a, n: blob[a:a + n], check.entries[p]) != b:
            raise UnrealError("o pak gravado não confere na releitura")
    out.write_bytes(blob)
    return out


def main_paks(romfs_files: dict[str, tuple[int, int]]) -> list[str]:
    return sorted(p for p in romfs_files if p.endswith(".pak") and "/Content/Paks/" in p and "~mods" not in p)


def save_version(mod_root: Path, info: dict) -> None:
    (mod_root / "deck-commander-unreal.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), "utf-8")
