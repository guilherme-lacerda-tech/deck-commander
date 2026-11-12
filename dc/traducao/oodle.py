"""Descompressor Oodle (Mermaid/Selkie) em Python puro, só leitura.

Os jogos da engine Trinity (Pokémon Scarlet/Violet, Legends Z-A) guardam os arquivos dentro de pacotes
comprimidos com Oodle. A biblioteca oficial é fechada; este módulo é um porte fiel do decodificador
aberto `ooz` (powzix, GPL-3; https://github.com/powzix/ooz), restrito ao que a tradução precisa:
- contêiner de blocos de 256 KiB (cabeçalho 0x?C + tipo do decodificador);
- decodificador 10 (Mermaid/Selkie, os dois têm o mesmo formato em disco);
- camada de entropia ("DecodeBytes"): cópia direta, Huffman (tipos 2/4), RLE (3), recursivo (5) e tANS (1).
Kraken (6) e Leviathan (12) NÃO estão implementados: o arquivo é recusado com OodleError.

Lento (Python), mas os textos de um jogo têm poucos MB. Nunca é usado para gravar: o mod usa arquivos soltos
sem compressão. A validação é o tamanho exato de saída declarado no pacote mais o leitor do formato da mensagem.
"""
from __future__ import annotations

import struct


class OodleError(ValueError):
    pass


def _fail(msg: str = "fluxo Oodle inválido"):
    raise OodleError(msg)




def _bsr(x: int) -> int:
    return x.bit_length() - 1


# ============================================================================ camada de entropia
def decode_bytes(src: bytes, p: int, p_end: int, out_cap: int) -> tuple[bytes, int]:
    """Kraken_DecodeBytes: devolve (dados, bytes de entrada consumidos)."""
    if p_end - p < 2:
        _fail("poucos bytes")
    b0 = src[p]
    chunk_type = (b0 >> 4) & 7
    if chunk_type == 0:
        if b0 >= 0x80:
            size = ((b0 << 8) | src[p + 1]) & 0xFFF
            q = p + 2
        else:
            if p_end - p < 3:
                _fail("poucos bytes")
            size = (b0 << 16) | (src[p + 1] << 8) | src[p + 2]
            if size & ~0x3FFFF:
                _fail("bits reservados")
            q = p + 3
        if size > out_cap or p_end - q < size:
            _fail("cópia maior que o espaço")
        return bytes(src[q:q + size]), q + size - p
    if b0 >= 0x80:
        if p_end - p < 3:
            _fail("poucos bytes")
        bits = (b0 << 16) | (src[p + 1] << 8) | src[p + 2]
        src_size = bits & 0x3FF
        dst_size = src_size + ((bits >> 10) & 0x3FF) + 1
        q = p + 3
    else:
        if p_end - p < 5:
            _fail("poucos bytes")
        bits = (src[p + 1] << 24) | (src[p + 2] << 16) | (src[p + 3] << 8) | src[p + 4]
        src_size = bits & 0x3FFFF
        dst_size = (((bits >> 18) | (b0 << 14)) & 0x3FFFF) + 1
        if src_size >= dst_size:
            _fail("tamanhos incoerentes")
        q = p + 5
    if p_end - q < src_size or dst_size > out_cap:
        _fail("bloco maior que o espaço")
    if chunk_type in (2, 4):
        out = _decode_huff(src, q, src_size, dst_size, chunk_type >> 1)
        used = src_size
    elif chunk_type == 5:
        out, used = _decode_recursive(src, q, src_size, dst_size)
    elif chunk_type == 3:
        out, used = _decode_rle(src, q, src_size, dst_size)
    elif chunk_type == 1:
        out = _decode_tans(src, q, src_size, dst_size)
        used = src_size
    else:
        _fail(f"tipo de entropia {chunk_type} desconhecido")
    if used != src_size or len(out) != dst_size:
        _fail("tamanho decodificado não confere")
    return bytes(out), q + src_size - p


def _block_size(src, p, p_end, cap) -> int:
    """Kraken_GetBlockSize: só o tamanho de saída do próximo bloco."""
    if p_end - p < 2:
        _fail()
    b0 = src[p]
    t = (b0 >> 4) & 7
    if t == 0:
        size = (((b0 << 8) | src[p + 1]) & 0xFFF) if b0 >= 0x80 else (b0 << 16) | (src[p + 1] << 8) | src[p + 2]
        if size > cap:
            _fail()
        return size
    if t >= 6:
        _fail()
    if b0 >= 0x80:
        bits = (b0 << 16) | (src[p + 1] << 8) | src[p + 2]
        dst = (bits & 0x3FF) + ((bits >> 10) & 0x3FF) + 1
    else:
        bits = (src[p + 1] << 24) | (src[p + 2] << 16) | (src[p + 3] << 8) | src[p + 4]
        dst = (((bits >> 18) | (b0 << 14)) & 0x3FFFF) + 1
    if dst > cap:
        _fail()
    return dst


# ---------------------------------------------------------------------------- leitor MSB por posição absoluta
class _Msb:
    """Leitor de bits MSB-first por posição absoluta. `peek32()` devolve o mesmo registrador de 32 bits que o
    BitReader do ooz teria depois de recarregar (bits além do fim = 0)."""
    __slots__ = ("buf", "end", "pos")

    def __init__(self, buf: bytes, start: int, end: int):
        self.buf, self.end, self.pos = buf, end, start * 8

    def peek32(self) -> int:
        i = self.pos >> 3
        chunk = self.buf[i:min(i + 5, self.end)] if i < self.end else b""
        v = int.from_bytes(bytes(chunk).ljust(5, b"\0"), "big")
        return (v >> (8 - (self.pos & 7))) & 0xFFFFFFFF

    def read(self, n: int) -> int:
        if n == 0:
            return 0
        v = self.peek32() >> (32 - n)
        self.pos += n
        return v

    def clz(self) -> int:
        return 32 - self.peek32().bit_length()


# ---------------------------------------------------------------------------- Huffman (tipos 2 e 4)
_PREFIX_ORG = (0x0, 0x0, 0x2, 0x6, 0xE, 0x1E, 0x3E, 0x7E, 0xFE, 0x1FE, 0x2FE, 0x3FE)
_REV11 = [int(f"{i:011b}"[::-1], 2) for i in range(2048)]


def _huff_lengths_old(r: _Msb, syms: list, prefix: list) -> int:
    if r.read(1):
        sym = num = 0
        avg = 32
        forced = r.read(2)
        thres = 1 << (31 - (20 >> forced))
        skip = r.read(1)
        while True:
            if not skip:
                if not r.peek32() & 0xFF000000:
                    _fail("Huffman: sequência de zeros inválida")
                sym += r.read(2 * (r.clz() + 1)) - 2 + 1
                if sym >= 256:
                    break
            skip = 0
            if not r.peek32() & 0xFF000000:
                _fail("Huffman: contagem inválida")
            n = r.read(2 * (r.clz() + 1)) - 2 + 1
            if sym + n > 256:
                _fail("Huffman: símbolos demais")
            num += n
            for _ in range(n):
                b = r.peek32()
                if b < thres:
                    _fail("Huffman: gamma grande demais")
                lz = 32 - b.bit_length()
                v = r.read(lz + forced + 1) + ((lz - 1) << forced)
                codelen = ((-(v & 1)) ^ (v >> 1)) + ((avg + 2) >> 2)
                if not 1 <= codelen <= 11:
                    _fail("Huffman: comprimento de código inválido")
                avg = codelen + ((3 * avg + 2) >> 2)
                syms[prefix[codelen]] = sym
                prefix[codelen] += 1
                sym += 1
            if sym == 256:
                break
        if sym != 256 or num < 2:
            _fail("Huffman: tabela incompleta")
        return num
    num = r.read(8)
    if num == 0:
        _fail("Huffman: tabela vazia")
    if num == 1:
        syms[0] = r.read(8)
        return 1
    cb = r.read(3)
    if cb > 4:
        _fail("Huffman: tabela esparsa inválida")
    for _ in range(num):
        s = r.read(8)
        cl = r.read(cb) + 1
        if cl > 11:
            _fail("Huffman: comprimento de código inválido")
        syms[prefix[cl]] = s
        prefix[cl] += 1
    return num


def _huff_fluff(r: _Msb, num: int) -> int:
    if num == 256:
        return 0
    x = min(257 - num, num) * 2
    y = _bsr(x - 1) + 1
    v = r.peek32() >> (32 - y)
    z = (1 << y) - x
    if (v >> 1) >= z:
        r.pos += y
        return v - z
    r.pos += y - 1
    return v >> 1


def _rice_lengths(r: _Msb, count: int) -> list[int]:
    """DecodeGolombRiceLengths: cada valor = quantidade de zeros antes do próximo 1 (MSB-first)."""
    buf, pos, bitlen = r.buf, r.pos, r.end * 8
    vals = []
    for _ in range(count):
        c = 0
        while True:
            if pos >= bitlen:
                _fail("comprimentos Golomb-Rice truncados")
            bit = (buf[pos >> 3] >> (7 - (pos & 7))) & 1
            pos += 1
            if bit:
                break
            c += 1
        vals.append(c & 0xFF)
    r.pos = pos
    return vals


def _convert_ranges(r: _Msb, num: int, fluff: int, symlen: list[int]) -> list[tuple[int, int]]:
    """Huff_ConvertToRanges: faixas (primeiro símbolo, quantidade) dos símbolos usados."""
    sl = 0
    sym_idx = 0
    if fluff & 1:
        v = symlen[sl]; sl += 1
        if v >= 8:
            _fail("faixa de símbolos inválida")
        sym_idx = r.read(v + 1) + (1 << (v + 1)) - 1
    used = 0
    ranges = []
    for _ in range(fluff >> 1):
        v = symlen[sl]
        if v >= 9:
            _fail("faixa de símbolos inválida")
        n = r.read(v) + (1 << v)
        v = symlen[sl + 1]
        if v >= 8:
            _fail("faixa de símbolos inválida")
        space = r.read(v + 1) + (1 << (v + 1)) - 1
        ranges.append((sym_idx, n))
        used += n
        sym_idx += n + space
        sl += 2
    if sym_idx >= 256 or used >= num or sym_idx + num - used > 256:
        _fail("faixas de símbolos incoerentes")
    ranges.append((sym_idx, num - used))
    return ranges


def _huff_lengths_new(r: _Msb, syms: list, prefix: list) -> int:
    forced = r.read(2)
    num = r.read(8) + 1
    fluff = _huff_fluff(r, num)
    vals = _rice_lengths(r, num + fluff)
    pos = r.pos
    if forced:  # DecodeGolombRiceBits
        if (pos + forced * num + 7) >> 3 > r.end:
            _fail("Huffman: bits extras truncados")
        r.pos = pos
        for i in range(num):
            vals[i] = ((vals[i] << forced) + r.read(forced)) & 0xFF
        pos = r.pos
    r.pos = pos
    running = 0x1E
    for i in range(num):
        v = vals[i]
        v = (-(v & 1)) ^ (v >> 1)
        cl = v + (running >> 2) + 1
        if not 1 <= cl <= 11:
            _fail("Huffman: comprimento de código inválido")
        vals[i] = cl
        running += v
    ranges = _convert_ranges(r, num, fluff, vals[num:])
    cp = 0
    for s, n in ranges:
        for k in range(n):
            cl = vals[cp]; cp += 1
            syms[prefix[cl]] = s + k
            prefix[cl] += 1
    return num


def _huff_core(src, a0, mid, end, n_out, rlen, rsym) -> bytearray:
    """Kraken_DecodeBytesCore: 3 fluxos LSB-first intercalados (A para frente de a0, B para trás a partir
    de `end`, C para frente a partir de `mid`). B e C dividem [mid, end) e precisam se encontrar."""
    if a0 > mid or mid > end:
        _fail("Huffman: divisão inválida")
    sa = bytes(src[a0:mid]) + b"\0\0\0"
    sc = bytes(src[mid:end]) + b"\0\0\0"
    sb = bytes(src[mid:end])[::-1] + b"\0\0\0"
    out = bytearray(n_out)
    pa = pb = pc = 0
    for i in range(n_out):
        r = i % 3
        if r == 0:
            j = pa >> 3
            k = ((sa[j] | sa[j + 1] << 8 | sa[j + 2] << 16) >> (pa & 7)) & 0x7FF
            pa += rlen[k]
        elif r == 1:
            j = pb >> 3
            k = ((sb[j] | sb[j + 1] << 8 | sb[j + 2] << 16) >> (pb & 7)) & 0x7FF
            pb += rlen[k]
        else:
            j = pc >> 3
            k = ((sc[j] | sc[j + 1] << 8 | sc[j + 2] << 16) >> (pc & 7)) & 0x7FF
            pc += rlen[k]
        out[i] = rsym[k]
    if (pa + 7) >> 3 != mid - a0 or ((pb + 7) >> 3) + ((pc + 7) >> 3) != end - mid:
        _fail("Huffman: fluxos não terminam onde deviam")
    return out


def _decode_huff(src, p, size, dst_size, typ) -> bytearray:
    end = p + size
    r = _Msb(src, p, end)
    syms = [0] * 1280
    prefix = list(_PREFIX_ORG)
    if not r.read(1):
        num = _huff_lengths_old(r, syms, prefix)
    elif not r.read(1):
        num = _huff_lengths_new(r, syms, prefix)
    else:
        _fail("Huffman: cabeçalho inválido")
    q = (r.pos + 7) >> 3
    if num == 1:
        return bytearray([syms[0]]) * dst_size
    lens = bytearray(2048)
    symt = bytearray(2048)
    cur = 0
    for i in range(1, 11):
        start = _PREFIX_ORG[i]
        count = prefix[i] - start
        if count:
            step = 1 << (11 - i)
            if cur + (count << (11 - i)) > 2048:
                _fail("Huffman: tabela grande demais")
            for j in range(count):
                lens[cur:cur + step] = bytes([i]) * step
                symt[cur:cur + step] = bytes([syms[start + j]]) * step
                cur += step
    n11 = prefix[11] - _PREFIX_ORG[11]
    if n11:
        if cur + n11 > 2048:
            _fail("Huffman: tabela grande demais")
        lens[cur:cur + n11] = bytes([11]) * n11
        symt[cur:cur + n11] = bytes(syms[_PREFIX_ORG[11]:_PREFIX_ORG[11] + n11])
        cur += n11
    if cur != 2048:
        _fail("Huffman: tabela incompleta")
    rlen = bytearray(2048)
    rsym = bytearray(2048)
    for i in range(2048):
        rlen[_REV11[i]] = lens[i]
        rsym[_REV11[i]] = symt[i]
    if typ == 1:
        if q + 3 > end:
            _fail()
        split = src[q] | src[q + 1] << 8
        q += 2
        return _huff_core(src, q, q + split, end, dst_size, rlen, rsym)
    if q + 6 > end:
        _fail()
    half = (dst_size + 1) >> 1
    split_mid = src[q] | src[q + 1] << 8 | src[q + 2] << 16
    q += 3
    if split_mid > end - q:
        _fail()
    mid = q + split_mid
    split_left = src[q] | src[q + 1] << 8
    q += 2
    if mid - q < split_left + 2 or end - mid < 3:
        _fail()
    split_right = src[mid] | src[mid + 1] << 8
    if end - (mid + 2) < split_right + 2:
        _fail()
    out = _huff_core(src, q, q + split_left, mid, half, rlen, rsym)
    out += _huff_core(src, mid + 2, mid + 2 + split_right, end, dst_size - half, rlen, rsym)
    return out


# ---------------------------------------------------------------------------- RLE (3)
def _decode_rle(src, p, size, dst_size):
    if size <= 1:
        if size != 1:
            _fail()
        return bytes([src[p]]) * dst_size, 1
    if src[p]:
        dec, n = decode_bytes(src, p, p + size, 1 << 20)
        if n <= 0:
            _fail()
        cmd = dec + bytes(src[p + n:p + size])
    else:
        cmd = bytes(src[p + 1:p + size])
    out = bytearray()
    ci, ce = 0, len(cmd)
    rle = 0
    while ci < ce:
        c = cmd[ce - 1]
        if c == 0 or c >= 0x30:
            ce -= 1
            ncopy, nrle = (-1 - c) & 0xF, c >> 4
        elif c >= 0x10:
            data = (cmd[ce - 2] | cmd[ce - 1] << 8) - 4096
            ce -= 2
            ncopy, nrle = data & 0x3F, data >> 6
        elif c == 1:
            rle = cmd[ci]
            ci += 1
            ce -= 1
            continue
        elif c >= 9:
            nrle = ((cmd[ce - 2] | cmd[ce - 1] << 8) - 0x8FF) * 128
            ce -= 2
            ncopy = 0
        else:
            ncopy = ((cmd[ce - 2] | cmd[ce - 1] << 8) - 511) * 64
            ce -= 2
            nrle = 0
        if ce - ci < ncopy or dst_size - len(out) < ncopy + nrle:
            _fail("RLE além do fim")
        out += cmd[ci:ci + ncopy]
        ci += ncopy
        out += bytes([rle]) * nrle
    if ci != ce or len(out) != dst_size:
        _fail("RLE incompleto")
    return out, size


# ---------------------------------------------------------------------------- recursivo (5) / multiarray
def _decode_recursive(src, p, size, dst_size):
    end = p + size
    if size < 6:
        _fail()
    n = src[p] & 0x7F
    if n < 2:
        _fail()
    if not src[p] & 0x80:
        q = p + 1
        out = bytearray()
        for _ in range(n):
            data, used = decode_bytes(src, q, end, dst_size - len(out))
            out += data
            q += used
        if len(out) != dst_size:
            _fail("recursivo incompleto")
        return out, q - p
    return _multiarray(src, p, end, dst_size)


def _multiarray(src, p0, end, cap):
    """Kraken_DecodeMultiArray com um único array de saída (é o único uso no decodificador)."""
    if end - p0 < 4:
        _fail()
    p = p0
    na = src[p]
    p += 1
    if not na & 0x80:
        _fail()
    na &= 0x3F
    if na == 0:
        data, used = decode_bytes(src, p, end, cap)
        return bytearray(data), p + used - p0
    arrays = []
    for _ in range(na):
        d, used = decode_bytes(src, p, end, 1 << 20)
        arrays.append(d)
        p += used
    total = sum(len(a) for a in arrays)
    if end - p < 3:
        _fail()
    Q = src[p] | src[p + 1] << 8
    p += 2
    num_idx = _block_size(src, p, end, total)
    num_lens = num_idx - 1
    if num_lens < 1:
        _fail()
    if Q & 0x8000:
        d, used = decode_bytes(src, p, end, num_idx)
        if len(d) != num_idx:
            _fail()
        p += used
        lenlog2 = [t >> 4 for t in d]
        idxs = [t & 0xF for t in d]
        num_lens = num_idx
    else:
        idxs, used = decode_bytes(src, p, end, num_idx)
        if len(idxs) != num_idx:
            _fail()
        p += used
        lenlog2, used = decode_bytes(src, p, end, num_idx - 1)
        if len(lenlog2) != num_idx - 1:
            _fail()
        p += used
        if any(x > 16 for x in lenlog2):
            _fail()
    varlen = Q & 0x3FFF
    if end - p < varlen:
        _fail()
    fwd = _Msb(src, p, p + varlen)
    rev = bytes(src[p:p + varlen])[::-1]
    bwd = _Msb(rev, 0, len(rev))
    intervals = []
    for i in range(num_lens):  # valor = 1 implícito seguido de `n` bits; pares vêm da frente, ímpares de trás
        nb = lenlog2[i]
        r = fwd if (i % 2 == 0 or i == num_lens - 1 and num_lens % 2) else bwd
        intervals.append((1 << nb) | r.read(nb))
    if idxs[num_idx - 1]:
        _fail()
    out = bytearray()
    pos = [0] * na
    indi = leni = 0
    while True:
        if indi >= num_idx:
            _fail()
        s = idxs[indi]
        indi += 1
        if s == 0:
            break
        if s > na or leni >= num_lens:
            _fail()
        n = intervals[leni]
        leni += 1
        a = arrays[s - 1]
        if n > len(a) - pos[s - 1] or n > cap - len(out):
            _fail()
        out += a[pos[s - 1]:pos[s - 1] + n]
        pos[s - 1] += n
    leni += 1 if Q & 0x8000 else 0
    if indi != num_idx or leni != num_lens or any(pos[i] != len(arrays[i]) for i in range(na)):
        _fail("multiarray incompleto")
    return out, p + varlen - p0


# ---------------------------------------------------------------------------- tANS (1)
def _tans_table(r: _Msb, L_bits: int) -> tuple[list[int], list[int]]:
    """Tans_DecodeTable: A = símbolos de peso 1, B = (símbolo << 16) + peso para peso >= 2."""
    L = 1 << L_bits
    A, B = [], []
    if r.read(1):
        Q = r.read(3)
        num = r.read(8) + 1
        if num < 2:
            _fail("tANS: tabela pequena demais")
        fluff = _huff_fluff(r, num)
        rice = _rice_lengths(r, num + fluff)
        ranges = _convert_ranges(r, num, fluff, rice[num:])
        avg, total, ri = 6, 0, 0
        for sym, n in ranges:
            for _ in range(n):
                nextra = Q + rice[ri]
                ri += 1
                if nextra > 15:
                    _fail("tANS: peso grande demais")
                v = r.read(nextra) + (1 << nextra) - (1 << Q)
                d4 = avg >> 2
                limit = 2 * d4
                if v <= limit:
                    v = d4 + ((-(v & 1)) ^ (v >> 1))
                if limit > v:
                    limit = v
                v += 1
                avg += limit - d4
                if v == 1:
                    A.append(sym)
                elif v >= 2:
                    B.append((sym << 16) + v)
                total += v
                sym += 1
        if total != L:
            _fail("tANS: pesos não somam L")
        return A, B
    seen = [False] * 256
    count = r.read(3) + 1
    max_delta = r.read(_bsr(L_bits) + 1)
    if max_delta == 0 or max_delta > L_bits:
        _fail("tANS: tabela inválida")
    weight = total = 0
    for _ in range(count):
        sym = r.read(8)
        if seen[sym]:
            _fail("tANS: símbolo repetido")
        weight += r.read(max_delta)
        if weight == 0:
            _fail("tANS: peso zero")
        seen[sym] = True
        if weight == 1:
            A.append(sym)
        else:
            B.append((sym << 16) + weight)
        total += weight
    sym = r.read(8)
    if seen[sym]:
        _fail("tANS: símbolo repetido")
    if L - total < weight or L - total <= 1:
        _fail("tANS: pesos incoerentes")
    B.append((sym << 16) + (L - total))
    A.sort()
    B.sort()
    return A, B


def _tans_lut(A: list[int], B: list[int], L_bits: int) -> list:
    """Tans_InitLut: entradas (máscara x, bits a ler, símbolo, w)."""
    L = 1 << L_bits
    lut: list = [None] * L
    slots = L - len(A)
    sa = slots >> 2
    ptr = [0, 0, 0, 0]
    sb = sa + ((slots & 3) > 0); ptr[1] = sb
    sb += sa + ((slots & 3) > 1); ptr[2] = sb
    sb += sa + ((slots & 3) > 2); ptr[3] = sb
    for i, s in enumerate(A):
        lut[slots + i] = ((1 << L_bits) - 1, L_bits, s, 0)
    wsum = 0
    for e in B:
        weight, symbol = e & 0xFFFF, e >> 16
        if weight > 4:
            sym_bits = _bsr(weight)
            Z = L_bits - sym_bits
            x, bx, w = (1 << Z) - 1, Z, (L - 1) & (weight << Z)
            add = 1 << Z
            X = (1 << (sym_bits + 1)) - weight
            for j in range(4):
                d = ptr[j]
                Y = (weight + ((wsum - j - 1) & 3)) >> 2
                if X >= Y:
                    for _ in range(Y):
                        lut[d] = (x, bx, symbol, w & 0xFFFF); d += 1; w += add
                    X -= Y
                else:
                    for _ in range(X):
                        lut[d] = (x, bx, symbol, w & 0xFFFF); d += 1; w += add
                    Z -= 1
                    add >>= 1
                    bx, w, x = Z, 0, x >> 1
                    for _ in range(Y - X):
                        lut[d] = (x, bx, symbol, w & 0xFFFF); d += 1; w += add
                    X = weight
                ptr[j] = d
        else:
            if weight <= 0:
                _fail("tANS: peso inválido")
            bits = ((1 << weight) - 1) << (wsum & 3)
            bits |= bits >> 4
            ww = weight
            for _ in range(weight):
                idx = (bits & -bits).bit_length() - 1
                bits &= bits - 1
                d = ptr[idx]
                ptr[idx] += 1
                wb = _bsr(ww)
                lut[d] = ((1 << (L_bits - wb)) - 1, L_bits - wb, symbol, (L - 1) & (ww << (L_bits - wb)))
                ww += 1
        wsum += weight
    if any(e is None for e in lut):
        _fail("tANS: tabela incompleta")
    return lut


def _decode_tans(src, p, size, dst_size) -> bytearray:
    """Krak_DecodeTans: 5 estados; fluxo LSB-first para frente (do início) e para trás (do fim), que precisam
    se encontrar. Os 5 últimos bytes da saída são os estados finais."""
    if size < 8 or dst_size < 5:
        _fail("tANS: bloco curto demais")
    end = p + size
    r = _Msb(src, p, end)
    if r.read(1):
        _fail("tANS: bit reservado")
    L_bits = r.read(2) + 8
    A, B = _tans_table(r, L_bits)
    q = (r.pos + 7) >> 3
    if q >= end:
        _fail("tANS: sem dados")
    lut = _tans_lut(A, B, L_bits)
    L = 1 << L_bits
    fs = bytes(src[q:end]) + b"\0\0\0\0"
    bs = bytes(src[q:end])[::-1] + b"\0\0\0\0"
    pos = [0, 0]
    streams = (fs, bs)

    def rd(k: int, n: int) -> int:
        s, ps = streams[k], pos[k]
        j = ps >> 3
        v = ((s[j] | s[j + 1] << 8 | s[j + 2] << 16) >> (ps & 7)) & ((1 << n) - 1)
        pos[k] = ps + n
        return v

    st = [rd(0, L_bits), rd(1, L_bits), rd(0, L_bits), rd(1, L_bits), rd(0, L_bits)]
    n_out = dst_size - 5
    out = bytearray()
    while len(out) < n_out:
        for k in (0, 1):
            for i in range(5):
                if st[i] >= L:
                    _fail("tANS: estado fora da tabela")
                x, bx, sym, w = lut[st[i]]
                out.append(sym)
                st[i] = rd(k, bx) + w
                if len(out) >= n_out:
                    break
            if len(out) >= n_out:
                break
    if q + ((pos[0] + 7) >> 3) != end - ((pos[1] + 7) >> 3):
        _fail("tANS: fluxos não se encontram")
    if any(s > 0xFF for s in st):
        _fail("tANS: estado final inválido")
    out += bytes(st)
    return out


# ============================================================================ Mermaid
def _far_offsets(src, p, p_end, count, offset):
    out = []
    for _ in range(count):
        if p_end - p < 3:
            _fail("offsets distantes truncados")
        off = src[p] | src[p + 1] << 8 | src[p + 2] << 16
        p += 3
        if offset >= 0xC00000 - 1 and off >= 0xC00000:
            if p == p_end:
                _fail("offsets distantes truncados")
            off += src[p] << 22
            p += 1
        if off > offset:
            _fail("offset distante fora do bloco")
        out.append(off)
    return out, p


def _mermaid_chunk(src, p, p_end, dst: bytearray, d0: int, dst_count: int, mode: int):
    """Mermaid_ReadLzTable + Mermaid_ProcessLzRuns de um trecho de até 128 KiB que começa em dst[d0]."""
    if mode > 1:
        _fail("modo Mermaid inválido")
    if p_end - p < 10:
        _fail("trecho Mermaid curto demais")
    first = d0 == 0
    if first:
        dst[0:8] = src[p:p + 8]
        p += 8
    lit, n = decode_bytes(src, p, p_end, dst_count)
    p += n
    cmd, n = decode_bytes(src, p, p_end, dst_count)
    p += n
    cmd2_end = len(cmd)
    if dst_count <= 0x10000:
        cmd2_off = len(cmd)
    else:
        if p_end - p < 2:
            _fail()
        cmd2_off = struct.unpack_from("<H", src, p)[0]
        p += 2
        if cmd2_off > cmd2_end:
            _fail()
    if p_end - p < 2:
        _fail()
    off16_count = struct.unpack_from("<H", src, p)[0]
    if off16_count == 0xFFFF:
        p += 2
        hi, n = decode_bytes(src, p, p_end, dst_count >> 1)
        p += n
        lo, n = decode_bytes(src, p, p_end, dst_count >> 1)
        p += n
        if len(lo) != len(hi):
            _fail()
        off16 = [lo[i] + hi[i] * 256 for i in range(len(lo))]
    else:
        off16 = list(struct.unpack_from(f"<{off16_count}H", src, p + 2))
        p += 2 + off16_count * 2
    if p_end - p < 3:
        _fail()
    tmp = src[p] | src[p + 1] << 8 | src[p + 2] << 16
    p += 3
    if tmp:
        s1, s2 = tmp >> 12, tmp & 0xFFF
        if s1 == 4095:
            s1 = struct.unpack_from("<H", src, p)[0]; p += 2
        if s2 == 4095:
            s2 = struct.unpack_from("<H", src, p)[0]; p += 2
        off32_1, p = _far_offsets(src, p, p_end, s1, d0)
        off32_2, p = _far_offsets(src, p, p_end, s2, d0 + 0x10000)
    else:
        off32_1, off32_2 = [], []
    # ---- execução (Mermaid_Mode0/1). Cópias byte a byte: o formato garante distância >= 8,
    # então copiar para frente dá o mesmo resultado dos blocos de 8 bytes do ooz.
    ls = p                      # length stream: o resto do trecho
    lit_i = 0
    o16_i = 0
    recent = -8
    remaining = dst_count
    pos = d0
    for it in range(2):
        cur = min(remaining, 0x10000)
        if it == 0:
            cmds = cmd[0:cmd2_off]
            off32 = off32_1
        else:
            cmds = cmd[cmd2_off:cmd2_end]
            off32 = off32_2
        o32_i = 0
        begin = pos
        end = pos + cur
        d = pos + (8 if (first and it == 0) else 0)
        for c in cmds:
            if c >= 24:
                litlen = c & 7
                if litlen:
                    if lit_i + litlen > len(lit) or d + litlen > end:
                        _fail("literais além do fim")
                    if mode == 0:
                        for k in range(litlen):
                            dst[d + k] = (lit[lit_i + k] + dst[d + k + recent]) & 0xFF
                    else:
                        dst[d:d + litlen] = lit[lit_i:lit_i + litlen]
                    d += litlen
                    lit_i += litlen
                if not (c >> 7):
                    if o16_i >= len(off16):
                        _fail("offsets curtos esgotados")
                    recent = -off16[o16_i]
                    o16_i += 1
                mlen = (c >> 3) & 0xF
                m = d + recent
                if m < 0 or d + mlen > end:
                    _fail("cópia fora do bloco")
                for k in range(mlen):
                    dst[d + k] = dst[m + k]
                d += mlen
                continue
            if c > 2:
                length = c + 5
                if o32_i >= len(off32):
                    _fail("offsets distantes esgotados")
                m = begin - off32[o32_i]
                o32_i += 1
            else:
                if ls >= p_end:
                    _fail("comprimentos esgotados")
                length = src[ls]
                if length > 251:
                    if p_end - ls < 3:
                        _fail()
                    length += struct.unpack_from("<H", src, ls + 1)[0] * 4
                    ls += 2
                ls += 1
                if c == 0:
                    length += 64
                    if end - d < length or len(lit) - lit_i < length:
                        _fail("literais além do fim")
                    if mode == 0:
                        for k in range(length):
                            dst[d + k] = (lit[lit_i + k] + dst[d + k + recent]) & 0xFF
                    else:
                        dst[d:d + length] = lit[lit_i:lit_i + length]
                    d += length
                    lit_i += length
                    continue
                if c == 1:
                    length += 91
                    if o16_i >= len(off16):
                        _fail("offsets curtos esgotados")
                    m = d - off16[o16_i]
                    o16_i += 1
                else:
                    length += 29
                    if o32_i >= len(off32):
                        _fail("offsets distantes esgotados")
                    m = begin - off32[o32_i]
                    o32_i += 1
            recent = m - d
            if m < 0 or end - d < length:
                _fail("cópia fora do bloco")
            for k in range(length):
                dst[d + k] = dst[m + k]
            d += length
        # literais finais do sub-bloco
        rest = end - d
        if rest < 0 or len(lit) - lit_i < rest:
            _fail("literais finais além do fim")
        if mode == 0:
            for k in range(rest):
                dst[d + k] = (lit[lit_i + k] + dst[d + k + recent]) & 0xFF
        else:
            dst[d:end] = lit[lit_i:lit_i + rest]
        lit_i += rest
        pos = end
        remaining -= cur
        if remaining == 0:
            break
    if ls != p_end:
        _fail("sobrou fluxo de comprimentos")


def _mermaid_quantum(src, p, p_end, dst: bytearray, d: int, d_end: int):
    p_in = p
    while d < d_end:
        count = min(d_end - d, 0x20000)
        if p_end - p < 4:
            _fail()
        hdr = src[p + 2] | src[p + 1] << 8 | src[p] << 16
        if not (hdr & 0x800000):
            data, used = decode_bytes(src, p, p_end, count)
            if len(data) != count:
                _fail("bloco sem LZ com tamanho errado")
            dst[d:d + count] = data
        else:
            p += 3
            used = hdr & 0x7FFFF
            mode = (hdr >> 19) & 0xF
            if p_end - p < used:
                _fail()
            if used < count:
                _mermaid_chunk(src, p, p + used, dst, d, count, mode)
            elif used > count or mode != 0:
                _fail()
            else:
                dst[d:d + count] = src[p:p + count]
        p += used
        d += count
    return p - p_in


# ============================================================================ contêiner
def decompress(src: bytes, dst_len: int) -> bytes:
    """Kraken_Decompress (só Mermaid/Selkie). `dst_len` = tamanho original (vem do pacote)."""
    dst = bytearray(dst_len)
    p, end = 0, len(src)
    off = 0
    dec_type = None
    uncompressed = False
    use_crc = False
    while off < dst_len:
        if off & 0x3FFFF == 0:
            if p + 2 > end:
                _fail("cabeçalho truncado")
            b = src[p]
            if b & 0xF != 0xC or (b >> 4) & 3:
                _fail("não é um fluxo Oodle")
            uncompressed = bool((b >> 6) & 1)
            dec_type = src[p + 1] & 0x7F
            use_crc = bool(src[p + 1] >> 7)
            p += 2
        if dec_type != 10:
            raise OodleError(f"decodificador Oodle {dec_type} não suportado (só Mermaid/Selkie)")
        left = min(0x40000, dst_len - off)
        if uncompressed:
            if end - p < left:
                _fail("bloco cru truncado")
            dst[off:off + left] = src[p:p + left]
            p += left
            off += left
            continue
        if end - p < 3:
            _fail()
        v = (src[p] << 16) | (src[p + 1] << 8) | src[p + 2]
        size = v & 0x3FFFF
        if size != 0x3FFFF:
            csize = size + 1
            p += 6 if use_crc else 3  # o CRC não é conferido: a validação é o formato do arquivo
        elif v >> 18 == 1:  # bloco preenchido com um byte
            dst[off:off + left] = bytes([src[p + 3]]) * left
            p += 4
            off += left
            continue
        else:
            _fail("cabeçalho de bloco inválido")
        if csize > left or end - p < csize:
            _fail("bloco maior que o espaço")
        if csize == left:
            dst[off:off + left] = src[p:p + left]
        else:
            n = _mermaid_quantum(src, p, p + csize, dst, off, off + left)
            if n != csize:
                _fail("bloco não consumido por inteiro")
        p += csize
        off += left
    if p != end:
        _fail("sobrou entrada depois do fim")
    return bytes(dst)
