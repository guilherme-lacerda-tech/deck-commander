"""LZ4 em Python puro (o Deck não tem o módulo lz4). Usado pelos executáveis do Switch (NSO) e pela Unity.

Só o formato de BLOCO (sem o cabeçalho de "frame"): é o que NSO e UnityFS usam.
"""
from __future__ import annotations


class Lz4Error(ValueError):
    pass


def decompress(src: bytes, size: int) -> bytes:
    """Descomprime um bloco LZ4 e confere que deu exatamente `size` bytes."""
    out = bytearray()
    i, n = 0, len(src)
    while i < n:
        tok = src[i]
        i += 1
        lit = tok >> 4
        if lit == 15:
            while True:
                if i >= n:
                    raise Lz4Error("LZ4 truncado (literal)")
                b = src[i]
                i += 1
                lit += b
                if b != 255:
                    break
        if i + lit > n:
            raise Lz4Error("LZ4 truncado (literais)")
        out += src[i:i + lit]
        i += lit
        if i >= n:
            break  # último bloco termina só com literais
        if i + 2 > n:
            raise Lz4Error("LZ4 truncado (offset)")
        off = src[i] | (src[i + 1] << 8)
        i += 2
        if off == 0 or off > len(out):
            raise Lz4Error("LZ4 com deslocamento inválido")
        ml = tok & 15
        if ml == 15:
            while True:
                if i >= n:
                    raise Lz4Error("LZ4 truncado (match)")
                b = src[i]
                i += 1
                ml += b
                if b != 255:
                    break
        ml += 4
        start = len(out) - off
        if off >= ml:
            out += out[start:start + ml]
        else:  # sobreposição: copia repetindo o padrão
            for k in range(ml):
                out.append(out[start + k])
    if len(out) != size:
        raise Lz4Error(f"LZ4 deu {len(out)} bytes, esperado {size}")
    return bytes(out)


def compress_literal(data: bytes) -> bytes:
    """Bloco LZ4 válido sem compressão (só literais). Serve para regravar sem depender de compressor."""
    n = len(data)
    if n < 15:
        return bytes([n << 4]) + data
    rest = n - 15
    ext = bytearray()
    while rest >= 255:
        ext.append(255)
        rest -= 255
    ext.append(rest)
    return bytes([0xF0]) + bytes(ext) + data
