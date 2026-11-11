"""Acentos nas FALAS e descrições do Castlevania SOTN (PS1, versão europeia SLES-00524) — engenharia reversa 11/11/2026.

Como o jogo desenha as falas (projeto sotn-decomp, src/st/blit_char.h + src/dra/66590.c): cada letra vira um código
Shift-JIS e func_80106A28 (DRA.BIN, 0x80106C6C) pede o desenho à fonte do BIOS (Krom2RawAdd). Se o BIOS não tem o
código, ela procura numa tabela de letras PRÓPRIAS do jogo (códigos em 0x800AC910, desenhos 16x15 de 30 bytes em
0x800AC914) — que na versão ocidental tem 1 letra só (©) e um laço que roda 1 vez.

O patch:
 1. tabela nova com © + 24 letras acentuadas (montadas a partir das letras do próprio BIOS + o acento) na área de
    SsUtKeyOn (0x80025F08, 932 bytes) do executável SLES_005.24 — função da biblioteca de som da Sony que nenhum
    arquivo do disco chama (conferido: nenhum jal nem ponteiro para dentro da área);
 2. em func_80106A28 os 2 endereços da tabela passam a apontar para a nova e o laço passa de 1 para 25 voltas
    (sltiu v0, t9, 25 + bnez) — 6 instruções, conferidas antes contra os bytes originais;
 3. o texto das falas usa os códigos 0x8540.. (Shift-JIS sem desenho no BIOS) para as letras acentuadas.
"""
from __future__ import annotations

import struct

DRA_BASE = 0x800A0000
EXE_BASE = 0x80010000 - 0x800          # endereço na memória - EXE_BASE = posição no arquivo SLES_005.24
AREA = 0x80025F08                      # SsUtKeyOn: livre (nunca chamada)
AREA_TAM = 932
CODIGO0 = 0x8540                       # 1º código Shift-JIS das letras acentuadas
LETRAS = "áàâãéêíóôõúçÁÀÂÃÉÊÍÓÔÕÚÇ"
CODIGO = {ch: CODIGO0 + k for k, ch in enumerate(LETRAS)}
BASE = {"á": "a", "à": "a", "â": "a", "ã": "a", "é": "e", "ê": "e", "í": "i", "ó": "o", "ô": "o", "õ": "o",
        "ú": "u", "ç": "c"}
ACENTO = {"á": "agudo", "à": "grave", "â": "circ", "ã": "til", "é": "agudo", "ê": "circ", "í": "agudo",
          "ó": "agudo", "ô": "circ", "õ": "til", "ú": "agudo", "ç": None}
MOLDE = {"agudo": ["...#", "..#."], "grave": ["#...", ".#.."], "circ": [".##.", "#..#"], "til": [".#.#", "#.#."]}
KROM = 0x66000                         # fonte do BIOS (16x15, 30 bytes por letra), só os caracteres que existem
IDX_MAIUSC, IDX_MINUSC = 157, 183      # 'Ａ' e 'ａ' na tabela do BIOS (conferido desenhando a tabela)

# patch em func_80106A28 (endereço -> (instrução original esperada, nova))
def _lui(rt, v): return 0x3C000000 | (rt << 16) | ((v + 0x8000) >> 16 & 0xFFFF)
def _addiu(rt, rs, v): return 0x24000000 | (rs << 21) | (rt << 16) | (v & 0xFFFF)
def _sltiu(rt, rs, imm): return 0x2C000000 | (rs << 21) | (rt << 16) | imm
def _bnez(rs, pc, alvo): return 0x14000000 | (rs << 21) | (((alvo - pc - 4) >> 2) & 0xFFFF)


def _base(bios: bytes, ch: str) -> list[int]:
    i = IDX_MINUSC + ord(ch) - ord("a") if ch.islower() else IDX_MAIUSC + ord(ch) - ord("A")
    o = KROM + i * 30
    return [(bios[o + 2 * r] << 8) | bios[o + 2 * r + 1] for r in range(15)]


def _centro(rows: list[int]) -> int:
    cols = [k for r in rows for k in range(16) if r & (0x8000 >> k)]
    return (min(cols) + max(cols)) // 2 if cols else 7


def _desenha(rows: list[int], y: int, x: int, molde: str) -> None:
    for k, c in enumerate(molde):
        if c == "#" and 0 <= x + k < 16:
            rows[y] |= 0x8000 >> (x + k)


def glifo(bios: bytes, ch: str) -> bytes:
    """Desenho 16x15 (30 bytes) da letra acentuada, no traço da fonte do BIOS."""
    minus = ch.islower()
    base = BASE[ch.lower()]
    rows = _base(bios, base if minus else base.upper())
    acento = ACENTO[ch.lower()]
    cx = _centro(rows)
    if acento is None:  # ç/Ç: cedilha na linha 14 (vazia em todas as letras do BIOS)
        _desenha(rows, 14, cx - 1, "##")
    elif minus:  # minúsculas: linhas 5..13 → acento nas linhas 2 e 3
        if base == "i":
            rows = [0, 0, 0, 0] + rows[4:]  # (o "i" do BIOS não tem pingo acima da linha 4, mas garante)
        for k, linha in enumerate(MOLDE[acento]):
            _desenha(rows, 2 + k, cx - 1, linha)
    else:  # maiúsculas: linhas 1..13 → desce 1 linha e o acento entra nas linhas 0 e 1
        rows = [0] + rows[:14]
        for k, linha in enumerate(MOLDE[acento]):
            _desenha(rows, k, cx - 1, linha)
    return b"".join(struct.pack(">H", r) for r in rows)


def tabela(bios: bytes, copyright_codigo: int, copyright_glifo: bytes) -> tuple[bytes, int, int]:
    """(bytes da área, endereço dos códigos, endereço dos desenhos). Entrada 0 = o © original do jogo."""
    codigos = [copyright_codigo] + [CODIGO[ch] for ch in LETRAS]
    blob = b"".join(struct.pack("<H", c) for c in codigos)
    blob += bytes(-len(blob) % 4)
    end_glifos = AREA + len(blob)
    blob += copyright_glifo + b"".join(glifo(bios, ch) for ch in LETRAS)
    if len(blob) > AREA_TAM:
        raise ValueError("tabela maior que a área livre")
    return blob + bytes(AREA_TAM - len(blob)), AREA, end_glifos


PATCH_DRA = {  # endereço -> instrução original (conferida no DRA.BIN europeu antes de trocar)
    0x80106CA0: 0x3C0E800B,  # lui   t6, 0x800b
    0x80106CA4: 0x25CEC910,  # addiu t6, t6, -0x36f0   (g_SjisPages 0x800AC910)
    0x80106CAC: 0x3C05800B,  # lui   a1, 0x800b
    0x80106CB0: 0x24A5C914,  # addiu a1, a1, -0x36ec   (g_CustomGlyphs 0x800AC914)
    0x80106CDC: 0x3322FFFF,  # andi  v0, t9, 0xffff
    0x80106CE0: 0x1040FFF4,  # beqz  v0, 0x80106cb4
}


def aplicar(dra: bytes, exe: bytes, bios: bytes) -> tuple[bytes, bytes]:
    """(DRA.BIN, SLES_005.24) com a tabela nova e o laço de 25 letras. ValueError se o disco não for o esperado."""
    d, e = bytearray(dra), bytearray(exe)

    def palavra(buf, end, base):
        return struct.unpack_from("<I", buf, end - base)[0]
    # confere as instruções originais (versão europeia, lidas do disco) antes de mexer em qualquer coisa
    for end, orig in PATCH_DRA.items():
        if palavra(d, end, DRA_BASE) != orig:
            raise ValueError(f"DRA.BIN não é a versão esperada em {end:#x}")
    o = AREA - EXE_BASE
    if e[o:o + 4] != bytes.fromhex("c8ffbd27"):  # 1ª instrução de SsUtKeyOn: addiu sp, sp, -0x38
        raise ValueError("SLES_005.24 não é a versão esperada")
    cop_cod = struct.unpack_from("<H", d, 0x800AC910 - DRA_BASE)[0]
    cop_gli = bytes(d[0x800AC914 - DRA_BASE:0x800AC914 - DRA_BASE + 30])
    blob, end_cod, end_gli = tabela(bios, cop_cod, cop_gli)
    e[o:o + len(blob)] = blob
    n = 1 + len(LETRAS)
    novas = {
        0x80106CA0: _lui(14, end_cod), 0x80106CA4: _addiu(14, 14, end_cod),
        0x80106CAC: _lui(5, end_gli), 0x80106CB0: _addiu(5, 5, end_gli),
        0x80106CDC: _sltiu(2, 25, n),                       # v0 = t9 < 25
        0x80106CE0: _bnez(2, 0x80106CE0, 0x80106CB4),       # volta para o laço enquanto v0 != 0
    }
    for end, ins in novas.items():
        struct.pack_into("<I", d, end - DRA_BASE, ins)
    return bytes(d), bytes(e)


def codificar_acentos(texto: str) -> list[bytes]:
    """Pedaços de bytes de cada caractere da fala: acentuado -> código Shift-JIS de 2 bytes (0x85 0x40+k)."""
    return [struct.pack(">H", CODIGO[c]) if c in CODIGO else c.encode("latin-1", "replace") for c in texto]
