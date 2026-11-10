"""QR code em Python puro (só biblioteca padrão), para o instalador mostrar no terminal do Deck.

Modo byte, correção de erro nível M, versões 1 a 10 (até ~210 caracteres — sobra para links do Telegram).
Saída: terminal (meios-blocos Unicode), PNG ou SVG (painel do Deck).
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

# versão: (códigos de correção por bloco, [(blocos, códigos de dados por bloco), ...]) — nível M
_M = {1: (10, [(1, 16)]), 2: (16, [(1, 28)]), 3: (26, [(1, 44)]), 4: (18, [(2, 32)]), 5: (24, [(2, 43)]),
      6: (16, [(4, 27)]), 7: (18, [(4, 31)]), 8: (22, [(2, 38), (2, 39)]), 9: (22, [(3, 36), (2, 37)]),
      10: (26, [(4, 43), (1, 44)])}
_ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42],
          9: [6, 26, 46], 10: [6, 28, 50]}
_ECL_M = 0  # bits do nível M no campo de formato


def _gf_mul(x: int, y: int) -> int:
    z = 0
    for i in reversed(range(8)):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _rs_divisor(degree: int) -> list[int]:
    res = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            res[j] = _gf_mul(res[j], root)
            if j + 1 < degree:
                res[j] ^= res[j + 1]
        root = _gf_mul(root, 2)
    return res


def _rs_remainder(data: list[int], div: list[int]) -> list[int]:
    res = [0] * len(div)
    for b in data:
        f = b ^ res.pop(0)
        res.append(0)
        for i, c in enumerate(div):
            res[i] ^= _gf_mul(c, f)
    return res


def _codewords(text: bytes) -> tuple[int, list[int]]:
    for ver in range(1, 11):
        ec, groups = _M[ver]
        cap = sum(n * k for n, k in groups)
        cbits = 8 if ver < 10 else 16
        if 4 + cbits + 8 * len(text) <= cap * 8:
            break
    else:
        raise ValueError("texto grande demais para o QR (máx. ~210 caracteres)")
    bits = [0, 1, 0, 0] + [(len(text) >> i) & 1 for i in reversed(range(cbits))]
    for b in text:
        bits += [(b >> i) & 1 for i in reversed(range(8))]
    bits += [0] * min(4, cap * 8 - len(bits))
    bits += [0] * (-len(bits) % 8)
    data = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pad = 0xEC
    while len(data) < cap:
        data.append(pad)
        pad ^= 0xEC ^ 0x11
    blocks, k = [], 0
    div = _rs_divisor(ec)
    for n, size in groups:
        for _ in range(n):
            d = data[k:k + size]
            k += size
            blocks.append((d, _rs_remainder(d, div)))
    out = []
    for i in range(max(len(d) for d, _ in blocks)):
        out += [d[i] for d, _ in blocks if i < len(d)]
    for i in range(ec):
        out += [e[i] for _, e in blocks]
    return ver, out


def encode(text: str) -> list[list[bool]]:
    """Matriz do QR (True = módulo escuro), sem a margem."""
    ver, cw = _codewords(text.encode("utf-8"))
    n = ver * 4 + 17
    mod = [[False] * n for _ in range(n)]
    fn = [[False] * n for _ in range(n)]

    def put(x, y, dark):
        mod[y][x] = dark
        fn[y][x] = True

    for i in range(n):
        put(6, i, i % 2 == 0)
        put(i, 6, i % 2 == 0)
    for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                x, y = cx + dx, cy + dy
                if 0 <= x < n and 0 <= y < n:
                    put(x, y, max(abs(dx), abs(dy)) not in (2, 4))
    al = _ALIGN[ver]
    for i, ax in enumerate(al):
        for j, ay in enumerate(al):
            if (i, j) in ((0, 0), (0, len(al) - 1), (len(al) - 1, 0)):
                continue
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    put(ax + dx, ay + dy, max(abs(dx), abs(dy)) != 1)
    _format(put, n, 0)  # reserva (o certo vem depois da máscara)
    if ver >= 7:
        rem = ver
        for _ in range(12):
            rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
        bits = ver << 12 | rem
        for i in range(18):
            b = (bits >> i) & 1 == 1
            a, c = n - 11 + i % 3, i // 3
            put(a, c, b)
            put(c, a, b)
    i, right = 0, n - 1
    while right >= 1:
        if right == 6:
            right = 5
        for vert in range(n):
            for j in range(2):
                x = right - j
                y = n - 1 - vert if ((right + 1) & 2) == 0 else vert
                if not fn[y][x] and i < len(cw) * 8:
                    mod[y][x] = (cw[i >> 3] >> (7 - (i & 7))) & 1 == 1
                    i += 1
        right -= 2
    best = None
    for mask in range(8):
        m = [row[:] for row in mod]
        for y in range(n):
            for x in range(n):
                if not fn[y][x] and _MASKS[mask](x, y):
                    m[y][x] = not m[y][x]

        def put_m(x, y, dark, m=m):
            m[y][x] = dark
        _format(put_m, n, mask)
        score = _penalty(m)
        if best is None or score < best[0]:
            best = (score, m)
    return best[1]


_MASKS = [lambda x, y: (x + y) % 2 == 0, lambda x, y: y % 2 == 0, lambda x, y: x % 3 == 0,
          lambda x, y: (x + y) % 3 == 0, lambda x, y: (x // 3 + y // 2) % 2 == 0,
          lambda x, y: x * y % 2 + x * y % 3 == 0, lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
          lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0]


def _format(put, n: int, mask: int) -> None:
    data = _ECL_M << 3 | mask
    rem = data
    for _ in range(10):
        rem = (rem << 1) ^ ((rem >> 9) * 0x537)
    bits = (data << 10 | rem) ^ 0x5412

    def b(i):
        return (bits >> i) & 1 == 1
    for i in range(6):
        put(8, i, b(i))
    put(8, 7, b(6)); put(8, 8, b(7)); put(7, 8, b(8))
    for i in range(9, 15):
        put(14 - i, 8, b(i))
    for i in range(8):
        put(n - 1 - i, 8, b(i))
    for i in range(8, 15):
        put(8, n - 15 + i, b(i))
    put(8, n - 8, True)


def _penalty(m: list[list[bool]]) -> int:
    """Penalidade simplificada (sequências de 5+ iguais e blocos 2x2) para escolher a máscara mais legível."""
    n, p = len(m), 0
    for lines in (m, list(zip(*m))):
        for row in lines:
            run, prev = 0, None
            for v in row:
                run = run + 1 if v == prev else 1
                prev = v
                if run == 5:
                    p += 3
                elif run > 5:
                    p += 1
    for y in range(n - 1):
        for x in range(n - 1):
            if m[y][x] == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                p += 3
    dark = sum(map(sum, m))
    return p + abs(dark * 20 - n * n * 10) // (n * n) * 10


def terminal(text: str, margin: int = 2) -> str:
    """QR para o terminal: claro = bloco cheio (terminal de fundo escuro, como o Konsole do Deck)."""
    m = encode(text)
    n = len(m) + 2 * margin
    def light(x, y):
        x, y = x - margin, y - margin
        return not (0 <= x < len(m) and 0 <= y < len(m) and m[y][x])
    lines = []
    for y in range(0, n, 2):
        row = ""
        for x in range(n):
            top, bot = light(x, y), (light(x, y + 1) if y + 1 < n else False)
            row += "█" if top and bot else "▀" if top else "▄" if bot else " "
        lines.append(row)
    return "\n".join(lines)


def png(text: str, path: Path, scale: int = 8, margin: int = 4) -> Path:
    m = encode(text)
    n = (len(m) + 2 * margin) * scale
    rows = []
    for y in range(n):
        my = y // scale - margin
        row = bytearray(b"\x00")
        for x in range(n):
            mx = x // scale - margin
            dark = 0 <= mx < len(m) and 0 <= my < len(m) and m[my][mx]
            row.append(0 if dark else 255)
        rows.append(bytes(row))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    data = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))
    path.write_bytes(data)
    return path


def svg(text: str, margin: int = 4) -> str:
    """QR em SVG (para o painel do Deck mostrar como imagem): um caminho só, fundo branco, módulos pretos."""
    m = encode(text)
    n = len(m) + 2 * margin
    d = "".join(f"M{x + margin} {y + margin}h1v1h-1z" for y, row in enumerate(m) for x, dark in enumerate(row) if dark)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" shape-rendering="crispEdges">'
            f'<rect width="{n}" height="{n}" fill="#fff"/><path fill="#000" d="{d}"/></svg>')
