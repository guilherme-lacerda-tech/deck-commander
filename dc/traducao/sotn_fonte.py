"""Acentos do Castlevania SOTN (PS1) na fonte 8x8 dos menus e nomes de itens — engenharia reversa de 11/11/2026.

A fonte 8x8 fica em BIN/F_GAME.BIN (bloco de memória de vídeo de 128 pixels de largura, 4 bits por pixel): a tabela
de 16x16 células começa na linha 960 da 2ª metade do arquivo (deslocamento 135168). A ordem é a do projeto de
decompilação (tools/sotn-assets/sotn/string.go): índice = código ASCII - 0x20; da linha 6 em diante ficam katakana e
hiragana que a versão ocidental nunca mostra. Igual à versão de PSP do jogo, essas células viram letras acentuadas
desenhadas aqui a partir das letras do próprio jogo (mesma cor e traço) + o acento.
"""
from __future__ import annotations

BASE = 135168     # 2ª metade do F_GAME.BIN
LINHA0 = 960      # 1ª linha da tabela de letras 8x8
LARG = 64         # bytes por linha (128 pixels a 4 bits)
COR = 6           # cor do traço das letras

# acento -> (linhas de cima para minúscula [2 linhas], linha de cima para maiúscula [1 linha])
ACENTOS = {
    "agudo": (["....#...", "...#...."], "....#..."),
    "grave": (["...#....", "....#..."], "...#...."),
    "circ": (["...##...", "..#..#.."], "..#..#.."),
    "til": (["..##..#.", ".#..##.."], "..##.#.."),
}
LETRAS = {  # letra acentuada -> (base, acento); "ç"/"Ç" são tratadas à parte (cedilha embaixo)
    "á": ("a", "agudo"), "à": ("a", "grave"), "â": ("a", "circ"), "ã": ("a", "til"),
    "é": ("e", "agudo"), "ê": ("e", "circ"), "í": ("i", "agudo"), "ó": ("o", "agudo"),
    "ô": ("o", "circ"), "õ": ("o", "til"), "ú": ("u", "agudo"), "ç": ("c", None),
    "Á": ("A", "agudo"), "À": ("A", "grave"), "Â": ("A", "circ"), "Ã": ("A", "til"),
    "É": ("E", "agudo"), "Ê": ("E", "circ"), "Í": ("I", "agudo"), "Ó": ("O", "agudo"),
    "Ô": ("O", "circ"), "Õ": ("O", "til"), "Ú": ("U", "agudo"), "Ç": ("C", None),
}
PRIMEIRA = 0x70   # células 0x70..0x87 (katakana) recebem as 24 letras
INDICE = {ch: PRIMEIRA + k for k, ch in enumerate(LETRAS)}


def _cel(d: bytes | bytearray, i: int) -> list[list[int]]:
    r, c = i >> 4, i & 15
    out = []
    for y in range(8):
        off = BASE + (LINHA0 + r * 8 + y) * LARG + c * 4
        px = []
        for b in d[off:off + 4]:
            px += [b & 0xF, b >> 4]
        out.append(px)
    return out


def _grava(d: bytearray, i: int, cel: list[list[int]]) -> None:
    r, c = i >> 4, i & 15
    for y in range(8):
        off = BASE + (LINHA0 + r * 8 + y) * LARG + c * 4
        for k in range(4):
            d[off + k] = (cel[y][2 * k] & 0xF) | ((cel[y][2 * k + 1] & 0xF) << 4)


def glifo(d: bytes, ch: str) -> list[list[int]]:
    """Célula 8x8 da letra acentuada, feita a partir da letra-base do próprio jogo."""
    base, acento = LETRAS[ch]
    b = _cel(d, ord(base) - 0x20)
    novo = [[0] * 8 for _ in range(8)]
    if base == "i":  # "i" sem o pingo antes de pôr o acento
        b = [[0] * 8 if y < 2 else row[:] for y, row in enumerate(b)]
    if acento is None:  # ç / Ç: a letra igual + cedilha na linha de baixo (vazia nas duas)
        novo = [row[:] for row in b]
        novo[7] = [0, 0, 0, COR, 0, 0, 0, 0]
        if base == "C":  # o C maiúsculo vai até a linha 6: sobe a cedilha encostada
            novo[7] = [0, 0, 0, 0, COR, 0, 0, 0]
        return novo
    if base.islower():  # minúscula ocupa as linhas 2..6: acento nas linhas 0 e 1
        novo = [row[:] for row in b]
        for y, molde in enumerate(ACENTOS[acento][0]):
            novo[y] = [COR if c == "#" else 0 for c in molde]
        return novo
    # maiúscula ocupa 0..6: desce uma linha (a 7 é vazia) e o acento entra na linha 0
    novo[1:8] = [row[:] for row in b[0:7]]
    novo[0] = [COR if c == "#" else 0 for c in ACENTOS[acento][1]]
    return novo


def com_acentos(fgame: bytes) -> bytes:
    """F_GAME.BIN com as 24 letras acentuadas nas células 0x70..0x87."""
    d = bytearray(fgame)
    for ch, i in INDICE.items():
        _grava(d, i, glifo(fgame, ch))
    return bytes(d)


def desenho(d: bytes, i: int) -> str:
    return "\n".join("".join(".#"[v != 0] for v in row) for row in _cel(d, i))
