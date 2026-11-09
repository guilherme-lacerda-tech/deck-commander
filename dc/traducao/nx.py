"""Formatos de texto do Switch, sem dependências: MSBT (mensagens), SARC (pacote), Yaz0 e zstd
(compressão) e BFFNT (fonte bitmap — só para saber quais caracteres ela tem).

MSBT: só a seção TXT2 (as frases) é reescrita; LBL1/ATR1/TSY1/NLI1 e qualquer outra seção são
copiadas byte a byte. Dentro de cada frase, as tags (0x0E grupo tipo tamanho parâmetros / 0x0F
fechamento) viram ⟦n⟧ para a IA e voltam idênticas.
"""
from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field
from typing import Optional


class FormatError(ValueError):
    pass


# ============================================================================ MSBT
@dataclass
class Msbt:
    endian: str                 # "<" ou ">"
    encoding: int               # 0 utf-8, 1 utf-16, 2 utf-32
    header: bytes               # 0x20 bytes originais
    sections: list[tuple[bytes, bytes]]   # (magic, dados) na ordem original
    labels: dict[int, str] = field(default_factory=dict)   # índice -> rótulo
    # cada frase = lista de pedaços: str (texto) ou bytes (tag crua, sem o terminador)
    strings: list[list] = field(default_factory=list)

    def texts(self) -> list[tuple[str, list[bytes]]]:
        """(texto com ⟦n⟧, [tags na ordem]) por frase."""
        out = []
        for parts in self.strings:
            tags, buf = [], []
            for p in parts:
                if isinstance(p, bytes):
                    buf.append(f"⟦{len(tags)}⟧")
                    tags.append(p)
                else:
                    buf.append(p)
            out.append(("".join(buf), tags))
        return out

    def set_text(self, i: int, text: str, tags: list[bytes]) -> None:
        parts, pos = [], 0
        for m in re.finditer(r"⟦(\d+)⟧", text):
            if m.start() > pos:
                parts.append(text[pos:m.start()])
            parts.append(tags[int(m.group(1))])
            pos = m.end()
        if pos < len(text):
            parts.append(text[pos:])
        self.strings[i] = parts


def _codec(enc: int, e: str) -> tuple[str, int]:
    if enc == 0:
        return "utf-8", 1
    if enc == 1:
        return ("utf-16-le" if e == "<" else "utf-16-be"), 2
    if enc == 2:
        return ("utf-32-le" if e == "<" else "utf-32-be"), 4
    raise FormatError(f"codificação MSBT desconhecida: {enc}")


def _pad16(n: int) -> int:
    return (16 - n % 16) % 16


def read_msbt(data: bytes) -> Msbt:
    if data[:8] != b"MsgStdBn":
        raise FormatError("não é MSBT")
    bom = data[8:10]
    e = ">" if bom == b"\xfe\xff" else "<" if bom == b"\xff\xfe" else None
    if e is None:
        raise FormatError("BOM inválido")
    enc = data[0x0C]
    nsec = struct.unpack_from(e + "H", data, 0x0E)[0]
    m = Msbt(e, enc, data[:0x20], [])
    pos = 0x20
    for _ in range(nsec):
        if pos + 16 > len(data):
            raise FormatError("seção truncada")
        magic = data[pos:pos + 4]
        size = struct.unpack_from(e + "I", data, pos + 4)[0]
        body = data[pos + 16:pos + 16 + size]
        if len(body) != size:
            raise FormatError("seção truncada")
        m.sections.append((magic, body))
        pos += 16 + size + _pad16(size)
    for magic, body in m.sections:
        if magic == b"LBL1":
            m.labels = _read_lbl1(body, e)
        elif magic == b"TXT2":
            m.strings = _read_txt2(body, e, enc)
    if not any(s[0] == b"TXT2" for s in m.sections):
        raise FormatError("MSBT sem TXT2")
    return m


def _read_lbl1(b: bytes, e: str) -> dict[int, str]:
    out = {}
    n = struct.unpack_from(e + "I", b, 0)[0]
    for g in range(n):
        cnt, off = struct.unpack_from(e + "II", b, 4 + g * 8)
        p = off
        for _ in range(cnt):
            ln = b[p]
            name = b[p + 1:p + 1 + ln].decode("utf-8", "replace")
            idx = struct.unpack_from(e + "I", b, p + 1 + ln)[0]
            out[idx] = name
            p += 1 + ln + 4
    return out


def _read_txt2(b: bytes, e: str, enc: int) -> list[list]:
    codec, w = _codec(enc, e)
    n = struct.unpack_from(e + "I", b, 0)[0]
    offs = list(struct.unpack_from(e + f"{n}I", b, 4)) + [len(b)]
    unit = {1: "B", 2: "H", 4: "I"}[w]
    out = []
    for i in range(n):
        raw = b[offs[i]:offs[i + 1]]
        parts, text, p = [], bytearray(), 0
        while p + w <= len(raw):
            c = struct.unpack_from(e + unit, raw, p)[0]
            if c == 0:
                break
            if c in (0x0E, 0x0F):
                if text:
                    parts.append(text.decode(codec)); text = bytearray()
                if enc == 0:
                    raise FormatError("tags em MSBT UTF-8 não suportadas")  # raro no Switch; não arrisca
                if c == 0x0E:
                    size = struct.unpack_from(e + "H", raw, p + 3 * w)[0]
                    end = p + 4 * w + size
                else:
                    end = p + 3 * w
                if end > len(raw):
                    raise FormatError("tag truncada")
                parts.append(bytes(raw[p:end]))
                p = end
                continue
            text += raw[p:p + w]
            p += w
        if text:
            parts.append(text.decode(codec))
        out.append(parts)
    return out


def _write_txt2(strings: list[list], e: str, enc: int) -> bytes:
    codec, w = _codec(enc, e)
    blobs = []
    for parts in strings:
        b = bytearray()
        for p in parts:
            b += p if isinstance(p, bytes) else p.encode(codec)
        b += b"\x00" * w
        blobs.append(bytes(b))
    n = len(blobs)
    head = struct.pack(e + "I", n)
    off = 4 + 4 * n
    offs = []
    for bl in blobs:
        offs.append(off)
        off += len(bl)
    return head + struct.pack(e + f"{n}I", *offs) + b"".join(blobs)


def write_msbt(m: Msbt) -> bytes:
    out = bytearray(m.header)
    for magic, body in m.sections:
        if magic == b"TXT2":
            body = _write_txt2(m.strings, m.endian, m.encoding)
        out += magic + struct.pack(m.endian + "I", len(body)) + b"\x00" * 8 + body + b"\xab" * _pad16(len(body))
    struct.pack_into(m.endian + "I", out, 0x12, len(out))
    return bytes(out)


# ============================================================================ SARC
def sarc_hash(name: str, key: int) -> int:
    h = 0
    for ch in name.encode("utf-8"):
        c = ch - 256 if ch >= 128 else ch  # o Nintendo SDK usa char com sinal
        h = (h * key + c) & 0xFFFFFFFF
    return h


@dataclass
class Sarc:
    endian: str
    files: dict[str, bytes]
    order: list[str]
    align: dict[str, int]
    key: int = 0x65
    version: int = 0x0100


def read_sarc(data: bytes) -> Sarc:
    if data[:4] != b"SARC":
        raise FormatError("não é SARC")
    e = ">" if data[6:8] == b"\xfe\xff" else "<"
    hsize, _bom, _fsize, data_off, ver = struct.unpack_from(e + "HHIIH", data, 4)
    p = hsize
    if data[p:p + 4] != b"SFAT":
        raise FormatError("SFAT ausente")
    _sh, count, key = struct.unpack_from(e + "HHI", data, p + 4)
    nodes = []
    for i in range(count):
        nodes.append(struct.unpack_from(e + "IIII", data, p + 12 + i * 16))
    q = p + 12 + count * 16
    if data[q:q + 4] != b"SFNT":
        raise FormatError("SFNT ausente")
    names_off = q + 8
    files, order, align = {}, [], {}
    for i, (h, attr, s, t) in enumerate(nodes):
        if attr >> 24:
            no = names_off + (attr & 0xFFFFFF) * 4
            name = data[no:data.index(b"\x00", no)].decode("utf-8")
        else:
            name = f"0x{h:08x}.bin"
        files[name] = data[data_off + s:data_off + t]
        order.append(name)
        a = 4
        while a < 0x2000 and (data_off + s) % (a * 2) == 0:
            a *= 2
        align[name] = a
    return Sarc(e, files, order, align, key, ver)


def write_sarc(s: Sarc) -> bytes:
    e = s.endian
    names = sorted(s.order, key=lambda n: sarc_hash(n, s.key))  # nós ordenados pelo hash (exigência do formato)
    name_tbl, name_off = bytearray(), {}
    for n in names:
        name_off[n] = len(name_tbl) // 4
        name_tbl += n.encode("utf-8") + b"\x00"
        name_tbl += b"\x00" * ((4 - len(name_tbl) % 4) % 4)
    hdr = 0x14
    sfat = 12 + 16 * len(names)
    sfnt = 8 + len(name_tbl)
    maxa = max([s.align.get(n, 4) for n in names] + [4])
    data_off = hdr + sfat + sfnt
    data_off += (-data_off) % maxa
    blob, nodes = bytearray(), []
    for n in names:
        a = s.align.get(n, 4)
        blob += b"\x00" * ((-(data_off + len(blob))) % a)
        start = len(blob)
        blob += s.files[n]
        nodes.append((sarc_hash(n, s.key), 0x01000000 | name_off[n], start, len(blob)))
    out = bytearray(b"SARC" + struct.pack(e + "HHIIHH", hdr, 0xFEFF, 0, data_off, s.version, 0))
    out += b"SFAT" + struct.pack(e + "HHI", 12, len(names), s.key)
    for nd in nodes:
        out += struct.pack(e + "IIII", *nd)
    out += b"SFNT" + struct.pack(e + "HH", 8, 0) + name_tbl
    out += b"\x00" * (data_off - len(out))
    out += blob
    struct.pack_into(e + "I", out, 8, len(out))
    return bytes(out)


# ============================================================================ Yaz0 / zstd
def yaz0_decompress(data: bytes) -> bytes:
    if data[:4] != b"Yaz0":
        raise FormatError("não é Yaz0")
    size = struct.unpack_from(">I", data, 4)[0]
    out, p = bytearray(), 16
    while len(out) < size:
        code = data[p]; p += 1
        for bit in range(8):
            if len(out) >= size:
                break
            if code & (0x80 >> bit):
                out.append(data[p]); p += 1
            else:
                b1, b2 = data[p], data[p + 1]; p += 2
                dist = ((b1 & 0xF) << 8 | b2) + 1
                n = b1 >> 4
                if n == 0:
                    n = data[p] + 0x12; p += 1
                else:
                    n += 2
                for _ in range(n):
                    out.append(out[-dist])
    return bytes(out)


def yaz0_compress(data: bytes) -> bytes:
    """Compressor simples (procura repetições nos últimos 4 KB). Sempre gera Yaz0 válido."""
    out = bytearray(b"Yaz0" + struct.pack(">I", len(data)) + b"\x00" * 8)
    p, n = 0, len(data)
    index: dict[bytes, list[int]] = {}
    while p < n:
        code_pos = len(out); out.append(0); code = 0
        for bit in range(8):
            if p >= n:
                break
            best_len, best_dist = 0, 0
            if p + 3 <= n:
                for c in reversed(index.get(data[p:p + 3], [])[-32:]):
                    if p - c > 0x1000:
                        continue
                    ln = 3
                    while ln < 0x111 and p + ln < n and data[c + ln] == data[p + ln]:
                        ln += 1
                    if ln > best_len:
                        best_len, best_dist = ln, p - c
            if best_len >= 3:
                d = best_dist - 1
                if best_len < 0x12:
                    out += bytes([((best_len - 2) << 4) | (d >> 8), d & 0xFF])
                else:
                    out += bytes([d >> 8, d & 0xFF, best_len - 0x12])
                for k in range(best_len):
                    if p + k + 3 <= n:
                        index.setdefault(data[p + k:p + k + 3], []).append(p + k)
                p += best_len
            else:
                code |= 0x80 >> bit
                out.append(data[p])
                if p + 3 <= n:
                    index.setdefault(data[p:p + 3], []).append(p)
                p += 1
        out[code_pos] = code
    return bytes(out)


def _zstd():
    try:
        from compression import zstd  # Python 3.14+
        return zstd.decompress, lambda b: zstd.compress(b, level=15)
    except ImportError:
        pass
    try:
        import zstandard  # opcional
        return (lambda b: zstandard.ZstdDecompressor().decompress(b, max_output_size=1 << 31),
                lambda b: zstandard.ZstdCompressor(level=15).compress(b))
    except ImportError:
        return None


def unpack_layer(name: str, data: bytes) -> tuple[bytes, Optional[str]]:
    """Tira a compressão externa. Devolve (dados, 'yaz0'|'zstd'|None)."""
    if data[:4] == b"Yaz0":
        return yaz0_decompress(data), "yaz0"
    if data[:4] == b"\x28\xb5\x2f\xfd":
        z = _zstd()
        if not z:
            raise FormatError("arquivo .zs precisa de Python 3.14+ (zstd embutido)")
        try:
            return z[0](data), "zstd"
        except Exception as ex:  # noqa: BLE001 — ex.: jogo que usa dicionário zstd próprio
            raise FormatError(f"zstd não abriu ({ex}); o jogo pode usar dicionário próprio") from ex
    return data, None


def pack_layer(data: bytes, kind: Optional[str]) -> bytes:
    if kind == "yaz0":
        return yaz0_compress(data)
    if kind == "zstd":
        return _zstd()[1](data)
    return data


# ============================================================================ BFFNT
LATIN_PTBR = "áàâãéêíóôõúçÁÀÂÃÉÊÍÓÔÕÚÇ"


def bffnt_chars(data: bytes) -> Optional[set[int]]:
    """Códigos de caractere que a fonte tem, ou None se não conseguir ler com segurança."""
    if data[:4] not in (b"FFNT", b"CFNT", b"RFNT"):
        return None
    e = ">" if data[4:6] == b"\xfe\xff" else "<"
    try:
        hsize = struct.unpack_from(e + "H", data, 6)[0]
        version = struct.unpack_from(e + "I", data, 8)[0]
        v4 = (version >> 24) >= 4
        chars: set[int] = set()
        p = hsize
        while p + 8 <= len(data):
            magic = data[p:p + 4]
            size = struct.unpack_from(e + "I", data, p + 4)[0]
            if size < 8:
                return None
            if magic == b"CMAP":
                b = p + 8
                if v4:
                    lo, hi, method = struct.unpack_from(e + "IIH", data, b)
                    d = b + 4 + 4 + 2 + 2 + 4
                else:
                    lo, hi, method = struct.unpack_from(e + "HHH", data, b)
                    d = b + 2 + 2 + 2 + 2 + 4
                if method == 0:  # direto: toda a faixa
                    chars.update(range(lo, hi + 1))
                elif method == 1:  # tabela: 0xFFFF = sem glifo
                    for i, code in enumerate(range(lo, hi + 1)):
                        if struct.unpack_from(e + "H", data, d + 2 * i)[0] != 0xFFFF:
                            chars.add(code)
                elif method == 2:  # varredura: pares (código, índice)
                    if v4:
                        cnt = struct.unpack_from(e + "H", data, d)[0]
                        q = d + 4
                        for i in range(cnt):
                            chars.add(struct.unpack_from(e + "I", data, q + 8 * i)[0])
                    else:
                        cnt = struct.unpack_from(e + "H", data, d)[0]
                        for i in range(cnt):
                            chars.add(struct.unpack_from(e + "H", data, d + 2 + 4 * i)[0])
                else:
                    return None
            p += size
        return chars or None
    except struct.error:
        return None


def missing_ptbr(chars: set[int]) -> str:
    return "".join(c for c in LATIN_PTBR if ord(c) not in chars)
