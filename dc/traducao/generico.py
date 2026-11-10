"""Achar frases em qualquer arquivo de jogo e trocá-las no MESMO lugar, com o MESMO tamanho.

Base da "tradução fora do padrão" (dc.traducao.fora_padrao). Nenhuma posição do arquivo muda: índices e
ponteiros do jogo continuam valendo. A frase nova precisa caber no espaço da antiga; o que sobra vira 0x00.
Esqueleto de apply/unpack/pack escrito pela IA local (qwen3-coder); a busca foi refeita à mão porque a da IA
pegava bytes de dados como letras e texto em inglês lido como se fosse UTF-16 ("chinês").
"""
from __future__ import annotations

import zlib
from collections import Counter
from dataclasses import dataclass
from typing import Optional

from . import idioma


@dataclass
class Slot:
    offset: int
    length: int      # bytes do texto, sem o terminador
    encoding: str    # "utf-16-le" ou "utf-8"
    text: str


def _script(ch: str) -> str:
    o = ord(ch)
    if o < 0x250:
        return "latin"
    if 0x370 <= o < 0x530:
        return "greek-cyr"
    if 0x3040 <= o < 0xA000 or 0xAC00 <= o < 0xD7B0 or 0xFF00 <= o < 0xFFF0:
        return "cjk"
    return "other"


def _ok_char(ch: str) -> bool:
    o = ord(ch)
    return ch.isprintable() and o >= 0x20 and not 0xD800 <= o < 0xE000 and _script(ch) != "other" \
        and not 0xE000 <= o < 0xF900


def _trim(text: str) -> tuple[int, int]:
    """Quantos caracteres tirar do começo e do fim: espaços e o "lixo" de outro alfabeto colado na frase
    (bytes de dado que por acaso formam letras, ex.: 'ȁЃPress START')."""
    letters = [_script(c) for c in text if c.isalpha()]
    if not letters:
        return 0, 0
    main = Counter(letters).most_common(1)[0][0]
    a = 0
    while a < len(text) and (text[a].isspace() or (text[a].isalpha() and _script(text[a]) != main)
                             or (main == "latin" and ord(text[a]) > 0x17F)):
        a += 1
    b = len(text)
    while b > a and text[b - 1].isspace():
        b -= 1
    return a, len(text) - b


def _looks_ascii_pairs(raw: bytes) -> bool:
    """UTF-16 que na verdade é texto ASCII lido de 2 em 2 bytes (vira "chinês")."""
    pairs = len(raw) // 2
    both = sum(1 for i in range(0, pairs * 2, 2) if 0x20 <= raw[i] < 0x7F and 0x20 <= raw[i + 1] < 0x7F)
    return pairs and both / pairs > 0.6


def _utf16_runs(data: bytes, min_chars: int) -> list[Slot]:
    out, i, n = [], 0, len(data) - 1
    while i < n:
        j = i
        while j < n:
            ch = chr(data[j] | data[j + 1] << 8)
            if not _ok_char(ch):
                break
            j += 2
        if j < n and data[j] == 0 and data[j + 1] == 0 and (j - i) // 2 >= min_chars:
            raw = data[i:j]
            if not _looks_ascii_pairs(raw):
                text = raw.decode("utf-16-le")
                a, z = _trim(text)
                text = text[a:len(text) - z]
                if len(text) >= min_chars:
                    out.append(Slot(i + 2 * a, len(text) * 2, "utf-16-le", text))
            i = j + 2
        else:
            i = max(j, i) + 2
    return out


def _utf8_runs(data: bytes, min_chars: int, taken: list[tuple[int, int]]) -> list[Slot]:
    out, i, n = [], 0, len(data)
    covered = bytearray(n)
    for a, b in taken:
        covered[a:b] = b"\1" * (b - a)
    while i < n:
        if covered[i] or data[i] < 0x20 and data[i] not in (0x09,):
            i += 1
            continue
        j = i
        while j < n and data[j] != 0 and not covered[j]:
            j += 1
        if j < n and data[j] == 0:
            try:
                text = data[i:j].decode("utf-8")
            except UnicodeDecodeError as e:  # byte inválido no meio: recomeça logo depois dele
                i += max(1, e.end)
                continue
            if text and all(_ok_char(c) for c in text) and len(set(text)) > 1:
                a, z = _trim(text)
                core = text[a:len(text) - z]
                if len(core) >= min_chars:
                    start = i + len(text[:a].encode("utf-8"))
                    out.append(Slot(start, len(core.encode("utf-8")), "utf-8", core))
        i = j + 1
    return out


def find_strings(data: bytes, min_chars: int = 4, sentences_only: bool = False) -> list[Slot]:
    u16 = _utf16_runs(data, min_chars)
    taken = [(s.offset - 2, s.offset + s.length + 2) for s in u16]
    slots = u16 + _utf8_runs(data, min_chars, taken)
    if sentences_only:
        slots = [s for s in slots if idioma.is_sentence(s.text)]
    return sorted(slots, key=lambda s: s.offset)


def apply(data: bytes, slots: list[Slot], new: dict[int, str]) -> tuple[bytes, int, int]:
    """Grava as frases novas no lugar das antigas. Devolve (dados do MESMO tamanho, aplicadas, puladas)."""
    out = bytearray(data)
    applied = skipped = 0
    for s in slots:
        if s.offset not in new:
            continue
        try:
            enc = new[s.offset].encode(s.encoding)
        except UnicodeEncodeError:
            skipped += 1
            continue
        if len(enc) > s.length:
            skipped += 1
            continue
        out[s.offset:s.offset + s.length] = enc + b"\0" * (s.length - len(enc))
        applied += 1
    return bytes(out), applied, skipped


def _zstd():
    try:
        from compression import zstd  # Python 3.14+
        return zstd
    except ImportError:
        return None


def unpack(data: bytes) -> tuple[bytes, Optional[str]]:
    """Tira a compressão do arquivo inteiro (zlib/zstd), se houver."""
    if data[:1] == b"\x78":
        try:
            return zlib.decompress(data), "zlib"
        except zlib.error:
            pass
    if data[:4] == b"\x28\xb5\x2f\xfd":
        z = _zstd()
        if z:
            try:
                return z.decompress(data), "zstd"
            except Exception:  # noqa: BLE001 — dicionário próprio do jogo etc.
                pass
    return data, None


def pack(data: bytes, kind: Optional[str]) -> bytes:
    if kind == "zlib":
        return zlib.compress(data, 9)
    if kind == "zstd":
        z = _zstd()
        if not z:
            raise RuntimeError("zstd indisponível neste Python")
        return z.compress(data)
    return data
