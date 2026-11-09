"""Arquivos da Next Level Games (Luigi's Mansion 3): tabela de textos e o contêiner `.patch` da atualização.

Só biblioteca padrão. Nada aqui altera o jogo: lê bytes e devolve bytes novos.

Tabela de textos (little-endian):
    u32 idioma, u32 quantidade, u32 desconhecido
    quantidade × (u32 id, u32 pos)        pos em unidades UTF-16, a partir do fim do índice
    frases UTF-16LE terminadas em 0x0000, coladas uma depois da outra

`.patch` da atualização (ex.: init.patch da 1.4):
    b"UUU\\x01", u32 0, u32 início do bloco zlib, u32 tamanho comprimido, u32 tamanho descomprimido, ...
    registros por idioma (não mexemos) e, no fim do arquivo, um único bloco zlib.
    O bloco descomprimido começa com 16 u32 = início de cada seção. A seção 5 do init.patch guarda
    as 13 tabelas de texto (uma por idioma) coladas. Os tamanhos de cada tabela também aparecem em
    índices do jogo, por isso a tradução NUNCA muda o tamanho de uma tabela: só o conteúdo (o que
    sobra vira zeros no fim).
"""
from __future__ import annotations

import hashlib
import struct
import zlib
from dataclasses import dataclass, field

MAGIC_PATCH = b"UUU\x01"
TEXT_SECTION = 5


class TableError(ValueError):
    pass


class PatchError(ValueError):
    pass


# ----------------------------------------------------------------------------- tabela de textos
def _wstr_end(buf: bytes, start: int, limit: int) -> int:
    """Fim (exclusivo, já contando o terminador) de uma frase UTF-16 que começa em `start`."""
    i = start
    while i + 1 < limit:
        if buf[i] == 0 and buf[i + 1] == 0:
            return i + 2
        i += 2
    raise TableError("frase sem terminador")


@dataclass
class TextTable:
    locale: int
    unk: int
    ids: list[int]
    strings: list[str]          # na ordem das entradas
    order: list[int]            # entradas na ordem em que as frases estão gravadas
    shared: dict[int, int] = field(default_factory=dict)  # entrada -> entrada cuja frase ela reaproveita
    tail: bytes = b""           # o que vem depois da última frase (mantido igual)

    def size(self) -> int:
        """Tamanho sem o `tail`."""
        return 12 + 8 * len(self.ids) + sum(2 * (len(self.strings[i]) + 1) for i in self.order)


def read_table(buf: bytes) -> TextTable:
    if len(buf) < 12:
        raise TableError("tabela curta demais")
    locale, count, unk = struct.unpack_from("<III", buf, 0)
    if count > 200000:
        raise TableError("quantidade de frases absurda")
    base = 12 + 8 * count
    if base > len(buf):
        raise TableError("índice passa do fim")
    ids, poss = [], []
    for i in range(count):
        _id, pos = struct.unpack_from("<II", buf, 12 + 8 * i)
        ids.append(_id)
        poss.append(pos)
    first: dict[int, int] = {}
    shared: dict[int, int] = {}
    for i, pos in enumerate(poss):
        if pos in first:
            shared[i] = first[pos]
        else:
            first[pos] = i
    order = sorted(first.values(), key=lambda i: poss[i])
    strings: list[str] = [""] * count
    cur = 0
    end = base
    for i in order:
        if poss[i] != cur:
            raise TableError("frases não estão coladas (formato desconhecido)")
        start = base + 2 * poss[i]
        end = _wstr_end(buf, start, len(buf))
        strings[i] = buf[start:end - 2].decode("utf-16-le", "surrogatepass")
        cur = (end - base) // 2
    for i, j in shared.items():
        strings[i] = strings[j]
    return TextTable(locale, unk, ids, strings, order, shared, bytes(buf[end:]))


def write_table(t: TextTable, size: int | None = None) -> bytes:
    """Regrava a tabela. `size=None`: reprodução exata (com o `tail`). Com `size`: completa com zeros até
    exatamente `size` bytes (erro se não couber)."""
    pos: dict[int, int] = {}
    parts = []
    cur = 0
    for i in t.order:
        s = t.strings[i]
        if "\x00" in s:
            raise TableError("frase com caractere nulo")
        pos[i] = cur
        enc = s.encode("utf-16-le", "surrogatepass") + b"\x00\x00"
        parts.append(enc)
        cur += len(enc) // 2
    for i, j in t.shared.items():
        if t.strings[i] != t.strings[j]:
            raise TableError("frase compartilhada traduzida diferente")
        pos[i] = pos[j]
    out = bytearray(struct.pack("<III", t.locale, len(t.ids), t.unk))
    for i, _id in enumerate(t.ids):
        out += struct.pack("<II", _id, pos[i])
    out += b"".join(parts)
    if size is None:
        return bytes(out) + t.tail
    if len(out) > size:
        raise TableError(f"tabela maior que o espaço: {len(out)} > {size}")
    return bytes(out) + b"\x00" * (size - len(out))


# ----------------------------------------------------------------------------- contêiner .patch
@dataclass
class NlgPatch:
    head: bytes             # tudo antes do bloco zlib (mantido igual, só o tamanho comprimido muda)
    blob: bytearray         # bloco descomprimido
    raw_stream: bytes       # bloco comprimido original
    sections: list[int]
    blob_hash: bytes        # sha256 do bloco original (para regravar idêntico se nada mudou)

    def section_span(self, sec: int) -> tuple[int, int]:
        end = self.sections[sec + 1] if sec < 15 else len(self.blob)
        return self.sections[sec], end


def read_patch(raw: bytes) -> NlgPatch:
    if raw[:4] != MAGIC_PATCH or len(raw) < 24:
        raise PatchError("não é um .patch da Next Level Games")
    off, csize, dsize = struct.unpack_from("<III", raw, 8)
    if off < 24 or off + csize != len(raw):
        raise PatchError("posição do bloco comprimido não confere")
    d = zlib.decompressobj()
    try:
        blob = d.decompress(raw[off:off + csize])
    except zlib.error as e:
        raise PatchError(f"bloco comprimido inválido: {e}") from e
    if not d.eof or d.unused_data or len(blob) != dsize:
        raise PatchError("bloco comprimido com tamanho diferente do cabeçalho")
    if len(blob) < 64:
        raise PatchError("bloco curto demais")
    sections = list(struct.unpack_from("<16I", blob, 0))
    if any(a > b for a, b in zip(sections, sections[1:])) or sections[-1] > len(blob) or sections[0] < 64:
        raise PatchError("tabela de seções inválida")
    return NlgPatch(bytes(raw[:off]), bytearray(blob), bytes(raw[off:off + csize]), sections,
                    hashlib.sha256(blob).digest())


def write_patch(p: NlgPatch) -> bytes:
    if hashlib.sha256(p.blob).digest() == p.blob_hash:
        return p.head + p.raw_stream
    if len(p.blob) != struct.unpack_from("<I", p.head, 16)[0]:
        raise PatchError("o bloco mudou de tamanho (proibido)")
    if list(struct.unpack_from("<16I", p.blob, 0)) != p.sections:
        raise PatchError("a tabela de seções mudou (proibido)")
    stream = zlib.compress(bytes(p.blob), 6)
    head = bytearray(p.head)
    struct.pack_into("<I", head, 12, len(stream))
    return bytes(head) + stream


def section_tables(p: NlgPatch, sec: int = TEXT_SECTION) -> list[tuple[int, int]]:
    """(início, tamanho) de cada tabela de texto da seção, na ordem dos idiomas 0, 1, 2…"""
    start, end = p.section_span(sec)
    out = []
    o = start
    while o < end:
        if o + 12 > end:
            raise PatchError("tabela incompleta no fim da seção")
        locale, count, _unk = struct.unpack_from("<III", p.blob, o)
        if locale != len(out) or count > 200000 or o + 12 + 8 * count > end:
            raise PatchError(f"tabela de texto inesperada em {o}")
        base = o + 12 + 8 * count
        last = base
        for i in range(count):
            pos = struct.unpack_from("<I", p.blob, o + 16 + 8 * i)[0]
            s = base + 2 * pos
            if s >= end:
                raise PatchError("frase fora da seção")
            try:
                last = max(last, _wstr_end(p.blob, s, end))
            except TableError as e:
                raise PatchError(str(e)) from e
        # zeros depois da última frase (tabela traduzida menor que o espaço) pertencem a esta tabela;
        # a próxima começa no idioma seguinte (primeiro byte != 0)
        while last + 1 < end and p.blob[last] == 0 and p.blob[last + 1] == 0:
            last += 2
        out.append((o, last - o))
        o = last
    if o != end or not out:
        raise PatchError("as tabelas não fecham exatamente com a seção")
    return out


def get_table(p: NlgPatch, locale: int, sec: int = TEXT_SECTION) -> TextTable:
    o, n = section_tables(p, sec)[locale]
    return read_table(bytes(p.blob[o:o + n]))


def put_table(p: NlgPatch, locale: int, t: TextTable, sec: int = TEXT_SECTION) -> None:
    """Grava a tabela traduzida no MESMO espaço (mesmo tamanho; sobra = zeros)."""
    o, n = section_tables(p, sec)[locale]
    new = write_table(t, n)
    check = read_table(new)
    if [check.strings[i] for i in range(len(t.ids))] != t.strings or check.ids != t.ids:
        raise TableError("conferência da tabela regravada falhou")
    p.blob[o:o + n] = new


def selfcheck_patch(raw: bytes) -> tuple[bool, str]:
    """Lê e regrava SEM mudar nada: cada tabela e o .patch inteiro precisam sair byte a byte iguais."""
    try:
        p = read_patch(raw)
        tabs = section_tables(p)
        for o, n in tabs:
            buf = bytes(p.blob[o:o + n])
            if write_table(read_table(buf)) != buf:
                return False, f"tabela em {o} não foi reproduzida com exatidão"
        if write_patch(p) != raw:
            return False, ".patch não foi reproduzido com exatidão"
        return True, f"{len(tabs)} tabelas de texto"
    except (PatchError, TableError) as e:
        return False, str(e)
