"""Castlevania SOTN (PS1): menus DESENHADOS em português (engenharia reversa de 11/11/2026, disco SLES-00524).

Falha real: logo depois do título o jogo mostra a tela "SELECT YOUR DESTINY" com os botões File select / File copy /
File delete / Name entry / Name change — são DESENHOS (não texto), então o tradutor de texto não enxergava e o jogo
"abria todo em inglês".

ST/SEL/F_SEL.BIN é uma cópia crua da memória de vídeo: 4 bits por pixel, 64 bytes por linha (128 pixels), nibble
baixo = pixel da esquerda. Cada botão ocupa 128x32 pixels; o mesmo arquivo traz o alfabeto gótico do jogo
(A–Z & ! - . ' ?, células de 16x16). Os botões em português são montados com essas MESMAS letras (traço e cores do
jogo) — o arquivo continua do mesmo tamanho. A folha aparece 2 vezes no arquivo (as 2 páginas de vídeo); as duas
são trocadas.

Rascunho de px/put/glifo pela IA local (qwen2.5-coder:7b); largura_util e escrever reescritas (mediam linhas em vez
de colunas e limpavam a área errada).
"""
from __future__ import annotations

LARG = 64  # bytes por linha
ALFABETO = "ABCDEFGHIJKLMNOPQRSTUVWXYZ&!-.'?"
# Folhas (linha inicial de cada cópia) e, dentro de cada folha, a linha de cada botão e do alfabeto.
FOLHAS = (256, 2304)  # conferidas no disco: as duas cópias são iguais byte a byte
BOTOES = {0: "COPIAR", 32: "APAGAR", 64: "NOME", 96: "RENOMEAR", 144: "ESCOLHER"}  # File copy/delete, Name entry/change, File select
LINHA_ALFABETO = 176


def px(d, x: int, y: int) -> int:
    return (d[y * LARG + x // 2] >> (4 * (x % 2))) & 0xF


def put(d: bytearray, x: int, y: int, v: int) -> None:
    i = y * LARG + x // 2
    s = 4 * (x % 2)
    d[i] = (d[i] & (0xF0 >> s)) | ((v & 0xF) << s)


def glifo(d, gx: int, gy: int, w: int = 16, h: int = 16) -> list[list[int]]:
    return [[px(d, gx + x, gy + y) for x in range(w)] for y in range(h)]


def largura_util(g: list[list[int]]) -> tuple[int, int]:
    """(primeira, última) coluna com algum pixel aceso; (0, -1) se vazio."""
    cols = [x for x in range(len(g[0])) if any(linha[x] for linha in g)]
    return (cols[0], cols[-1]) if cols else (0, -1)


def escrever(d: bytearray, x0: int, y0: int, w: int, h: int, glifos: list[list[list[int]]], espaco: int = 1) -> None:
    """Limpa o retângulo e escreve as letras (aparadas na largura útil), centradas. Espaço = glifo vazio (6 px)."""
    for y in range(y0, y0 + h):
        for x in range(x0, x0 + w):
            put(d, x, y, 0)
    partes = []
    for g in glifos:
        a, b = largura_util(g)
        partes.append((g, a, b) if b >= a else (None, 0, 5))
    total = sum(b - a + 1 for _g, a, b in partes) + espaco * (len(partes) - 1)
    if total > w:
        raise ValueError(f"palavra larga demais ({total} px em {w})")
    gh = len(glifos[0]) if glifos else 0
    x = x0 + (w - total) // 2
    y = y0 + (h - gh) // 2
    for g, a, b in partes:
        if g is not None:
            for yy in range(gh):
                for xx in range(a, b + 1):
                    if g[yy][xx]:
                        put(d, x + xx - a, y + yy, g[yy][xx])
        x += b - a + 1 + espaco


def letra(d, folha: int, c: str) -> list[list[int]]:
    if c == " ":
        return [[0] * 16 for _ in range(16)]
    k = ALFABETO.index(c)
    return glifo(d, (k % 8) * 16, folha + LINHA_ALFABETO + (k // 8) * 16)


def botoes_em_portugues(f_sel: bytes) -> bytes:
    d = bytearray(f_sel)
    for folha in FOLHAS:
        for y, palavra in BOTOES.items():
            escrever(d, 0, folha + y, 128, 32, [letra(d, folha, c) for c in palavra])
    return bytes(d)


# ST/SEL/SEL.BIN (engenharia reversa 14/11/2026): a placa "SELECT YOUR DESTINY" e os rótulos dos arquivos ("new
# game", "no data"…) são TEXTO em minúsculas desenhado letra a letra com o alfabeto gótico acima — só a–z, sem
# acento. Cada um ocupa um espaço fixo terminado em 0x00. Falha real: o tradutor de texto tratou esses como frases
# comuns e gravou lixo ("new game" -> "jg novo", "no data" -> "n"). Aqui eles são gravados DEPOIS da tradução de
# texto, conferindo os bytes originais (só no disco SLES-00524). Os cabeçalhos "| Erase File |" usam a fonte comum.
BARRA = b"\x81|"
GOTICO = {  # posição: (original, tamanho do espaço, português)
    161488: (b"select", 8, b"escolha"), 161496: (b"your", 8, b"seu"), 161504: (b"destiny", 8, b"destino"),
    161512: (BARRA + b" Erase File " + BARRA, 20, BARRA + b" Apagar " + BARRA),
    161532: (BARRA + b" Copy File " + BARRA, 16, BARRA + b" Copiar " + BARRA),
    161548: (BARRA + b" Change Name " + BARRA, 20, BARRA + b" Renomear " + BARRA),
    161568: (BARRA + b" New Game " + BARRA, 16, BARRA + b" Novo Jogo " + BARRA),
    161688: (b"new game", 12, b"novo jogo"), 161700: (b"used", 8, b"usado"), 161708: (b"no data", 12, b"vazio"),
    161720: (b"card", 8, b"cartao"),
}


def textos_goticos(sel_original: bytes, sel_traduzido: bytes) -> bytes:
    """Regrava os textos góticos/cabeçalhos da tela de arquivos. Recusa (ValueError) se o disco não for o esperado."""
    for pos, (orig, tam, pt) in GOTICO.items():
        if sel_original[pos:pos + len(orig) + 1] != orig + b"\x00":
            raise ValueError(f"SEL.BIN de outra versão do jogo (posição {pos})")
        if len(pt) >= tam or (pt.islower() and not all(chr(c) in " abcdefghijklmnopqrstuvwxyz&!-.'" for c in pt)):
            raise ValueError(f"{pt!r} não cabe no espaço de {tam} bytes ou tem letra fora do alfabeto gótico")
    d = bytearray(sel_traduzido)
    for pos, (_orig, tam, pt) in GOTICO.items():
        d[pos:pos + tam] = pt + bytes(tam - len(pt))
    return bytes(d)
