"""Mensagens da engine Trinity (`message/dat/<Idioma>/**/*.dat`), formato "TextFile" do pkNX (kwsch, GPL-3).

Arquivo: u16 seções (=1), u16 linhas, u32 tamanho da seção, u32 chave inicial (0), u32 início da seção (0x10).
Seção: u32 tamanho, tabela de linhas {u32 deslocamento, u16 tamanho em UTF-16 (com o 0 final), u16 flags},
depois o texto de cada linha em UTF-16LE cifrado (XOR com chave 0x7C89 + 0x2983*linha, rotacionada 3 bits a
cada caractere) e completado com zeros até múltiplo de 4.
Códigos do jogo: 0x0010, n, n palavras (variável, quebra de caixa, pausa...). Caracteres de área privada
(U+E000..U+F8FF) são ícones da fonte. Os dois viram ⟦n⟧ para a IA; o resto é texto.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

KEY_BASE = 0x7C89
KEY_ADVANCE = 0x2983
VAR = 0x0010


class MsgError(ValueError):
    pass


def _crypt(words: list[int], line: int) -> list[int]:
    key = (KEY_BASE + KEY_ADVANCE * line) & 0xFFFF
    out = []
    for w in words:
        out.append(w ^ key)
        key = ((key << 3) | (key >> 13)) & 0xFFFF
    return out


@dataclass
class Line:
    words: list[int]          # decifrado, SEM o 0 final
    flags: int


@dataclass
class MsgDat:
    lines: list[Line] = field(default_factory=list)

    # ------------------------------------------------------------------ texto para a IA
    def texts(self) -> list[tuple[str, list[tuple[int, ...]]]]:
        return [split_codes(l.words) for l in self.lines]

    def set_text(self, i: int, text: str, codes: list[tuple[int, ...]]) -> None:
        self.lines[i].words = join_codes(text, codes)


def split_codes(words: list[int]) -> tuple[str, list[tuple[int, ...]]]:
    """(texto com \\x00 no lugar de cada código, códigos) — \\x00 nunca aparece em texto do jogo."""
    out, codes, i = [], [], 0
    while i < len(words):
        w = words[i]
        if w == VAR:
            if i + 1 >= len(words):
                raise MsgError("variável truncada")
            n = words[i + 1]
            if i + 2 + n > len(words):
                raise MsgError("variável truncada")
            codes.append(tuple(words[i:i + 2 + n]))
            out.append("\x00")
            i += 2 + n
        elif 0xE000 <= w <= 0xF8FF or w < 0x20 and w != 0x0A or 0xD800 <= w <= 0xDFFF:
            codes.append((w,))
            out.append("\x00")
            i += 1
        else:
            out.append(chr(w))
            i += 1
    return "".join(out), codes


def join_codes(text: str, codes: list[tuple[int, ...]]) -> list[int]:
    words, k = [], 0
    for ch in text:
        if ch == "\x00":
            if k >= len(codes):
                raise MsgError("código a mais")
            words += codes[k]
            k += 1
        else:
            b = ch.encode("utf-16-le")
            words += list(struct.unpack(f"<{len(b) // 2}H", b))
    if k != len(codes):
        raise MsgError("código faltando")
    return words


def read_dat(raw: bytes) -> MsgDat:
    if len(raw) < 0x14:
        raise MsgError("arquivo curto")
    secs, n, total, key, soff = struct.unpack_from("<HHIII", raw, 0)
    if secs != 1 or key != 0 or soff != 0x10:
        raise MsgError(f"cabeçalho inesperado ({secs}, {key}, {soff:#x})")
    slen = struct.unpack_from("<I", raw, soff)[0]
    if slen != total or soff + slen != len(raw):
        raise MsgError("tamanho da seção não confere")
    m = MsgDat()
    for i in range(n):
        off, ln, fl = struct.unpack_from("<IHH", raw, soff + 4 + 8 * i)
        if ln == 0 or soff + off + 2 * ln > len(raw):
            raise MsgError(f"linha {i} fora do arquivo")
        words = _crypt(list(struct.unpack_from(f"<{ln}H", raw, soff + off)), i)
        if words[-1] != 0:
            raise MsgError(f"linha {i} sem terminador")
        m.lines.append(Line(words[:-1], fl))
    return m


def write_dat(m: MsgDat) -> bytes:
    n = len(m.lines)
    table = bytearray()
    data = bytearray()
    base = 4 + 8 * n
    for i, l in enumerate(m.lines):
        words = l.words + [0]
        if len(words) > 0xFFFF:
            raise MsgError(f"linha {i} longa demais")
        table += struct.pack("<IHH", base + len(data), len(words), l.flags)
        data += struct.pack(f"<{len(words)}H", *_crypt(words, i))
        data += b"\0" * (-len(data) % 4)
    slen = 4 + len(table) + len(data)
    return struct.pack("<HHIII", 1, n, slen, 0, 0x10) + struct.pack("<I", slen) + bytes(table) + bytes(data)
