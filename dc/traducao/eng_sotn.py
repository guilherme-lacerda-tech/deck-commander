"""Texto do Castlevania: Symphony of the Night (PS1) — achar, recodificar e regravar SEM mudar tamanho nenhum.

Engenharia reversa (11/11/2026, disco SLES-00524):
  A) "ascii": diálogos e descrições em ASCII comum, entre códigos de controle (< 0x20: 0x01 quebra de linha + 1 byte
     de recuo, 0x02 nova página, 0x03 pausa…) e 0x00. Apóstrofo pode vir como 0x81 0x66 (código japonês).
  B) "menos20": nomes de itens/menus com cada caractere gravado como (ASCII - 0x20), 0x00 = espaço, fim em 0xFF.
Cada trecho traduzido ocupa exatamente os bytes do original (fonte só ASCII: sem acento). docs/specs/eng_sotn.md
(1ª versão gerada pela IA local; reescrita depois dos testes: posição/tamanho errados e o 0xFF sobrescrito).
"""
from __future__ import annotations

import re
import struct
import unicodedata
from dataclasses import dataclass

APOSTROFO = b"\x81\x66"
# Pontuação japonesa (2 bytes) no meio do ASCII. Falha real 11/11/2026: os menus do cartão de memória terminam com
# "." = 0x81 0x44, "?" = 0x81 0x48 ("Select the slot．") e o leitor descartava ou cortava esses textos
# ("No data found" virou "Sem dados n"; "Memory card" virou "nMemória") — o jogo abria todo em inglês.
SJIS = {0x8166: "'", 0x8144: ".", 0x8148: "?", 0x8149: "!", 0x8143: ",", 0x8146: ":", 0x8168: '"', 0x8169: "(",
        0x816A: ")", 0x816D: "[", 0x816E: "]", 0x815B: "-", **{0x824F + k: str(k - 1) for k in range(1, 11)}}
SJIS_DE = {v: struct.pack(">H", k) for k, v in SJIS.items()}


def _sjis(d: bytes, i: int) -> str | None:
    """Caractere da pontuação japonesa em d[i:i+2], ou None."""
    return SJIS.get(d[i] << 8 | d[i + 1]) if i + 1 < len(d) and d[i] in (0x81, 0x82) else None


_PROIBIDOS = set("_\\/{}|<>=#$@~^%")  # "%" = texto de depuração ("col step %x")
_EXT = (".BIN", ".VH", ".VB", ".TIM", ".STR", ".DAT", ".XA")


@dataclass
class Trecho:
    arquivo: str
    pos: int      # 1º byte do texto no arquivo
    tam: int      # bytes que o texto ocupa (sem o terminador)
    texto: str
    tipo: str     # "ascii" | "menos20"
    sjis: bool = False  # o original usa pontuação japonesa de 2 bytes (. ? ! , números): a tradução também usa


_COMUNS = set("""the of and to in is you that it he was for on are with as his they be at one have this from or had by not
but what all were we when your can said there an each which she do how their if will up other about out many then
them these so some her would make like him into time has look two more go see no way could my than first been who
its now find long down day did get come made may part me here where why must am thy thee shall know never may
sword shield attack defense magic potion heart hearts cape armor armour ring cloak helm hat boots damage strength
vampire castle count lord dracula alucard richter maria death belmont blade spell card relic item items power life
gold hit enemy enemies stone staff rod fire ice holy dark poison curse water air earth light thunder bolt
mail plate shirt tunic robe crown mask glasses gauntlet bracelet necklace medal brooch knife axe cross bible stopwatch
rebound book library master save room map exit equip use yes cancel start continue option sound stereo mono
name status level exp hp mp str con int lck def atk soul bat wolf mist form jump double gravity leap
increases restores resistance immune raises adds attacks against while when slightly greatly user nearby
son father mother man men woman god evil night moon world time back again help kill destroy king queen""".split())


def parece_texto(s: str) -> bool:
    """Frase/nome em inglês, não lixo binário nem nome de arquivo (filtro endurecido com o disco de verdade)."""
    if sum(c.isalpha() for c in s) < 3 or len(set(s)) == 1 or set(s) & _PROIBIDOS or s.upper().endswith(_EXT):
        return False
    if sum(c.isalpha() or c in " '.,!?-" for c in s) / len(s) < 0.8:
        return False
    palavras = re.findall(r"[A-Za-z]+", s)
    if len(palavras) == 1 and s.strip().islower():  # palavra-chave interna ("alucard", "axearmor"): nunca traduzir
        return False
    for w in palavras:  # caixa de palavra de verdade: "word", "Word" ou "WORD" — nunca "CEqX4XZ"/"IHdaExW"
        if len(w) > 1 and not (w.islower() or w.isupper() or (w[0].isupper() and w[1:].islower())):
            return False
        if re.search(r"[^aeiouyAEIOUY]{5,}", w):
            return False
    letras = "".join(palavras)
    vogais = sum(c in "aeiouAEIOU" for c in letras) / len(letras)
    if not 0.2 <= vogais <= 0.7:
        return False
    grandes = [w for w in palavras if len(w) >= 3]
    if any(w.lower() in _COMUNS for w in palavras):
        return True
    return len(grandes) >= 2  # nome de item com 2 palavras ("Iron cuirass")


_ANTES_DEPOIS_OK = set(range(0x20)) | {0xFF}


def _apara(t: Trecho, espaco: int, d: bytes) -> Trecho | None:
    """Tira espaços das pontas ajustando pos/tam (os espaços ficam no arquivo como estão)."""
    ini, fim = t.pos, t.pos + t.tam
    while ini < fim and d[ini] == espaco:
        ini += 1
    while fim > ini and d[fim - 1] == espaco:
        fim -= 1
    if fim <= ini:
        return None
    texto = t.texto.strip()
    m = re.match(r"^[A-Za-z0-9] {2,}", texto)  # letra solta de outro dado colada na frente ("i  Ring of Varda")
    if m:
        ini += m.end()
        texto = texto[m.end():]
    t.pos, t.tam, t.texto = ini, fim - ini, texto
    return t


def achar_ascii(arquivo: str, d: bytes, minimo: int = 4) -> list[Trecho]:
    out, i, n = [], 0, len(d)
    while i < n:
        if not (0x20 <= d[i] <= 0x7E or _sjis(d, i)):
            i += 1
            continue
        ini, chars, japones = i, [], False
        while i < n and (0x20 <= d[i] <= 0x7E or _sjis(d, i)):
            c = _sjis(d, i)
            if c:
                chars.append(c)
                japones |= c != "'"
                i += 2
            else:
                chars.append(chr(d[i]))
                i += 1
        if i < n and d[i] == 0xFF:  # termina em 0xFF: é nome no formato -0x20 (achar_menos20 cuida)
            continue
        # texto de verdade começa e termina junto de código de controle/0x00 (lixo binário começa em qualquer byte)
        if (ini > 0 and d[ini - 1] not in _ANTES_DEPOIS_OK) or (i < n and d[i] not in _ANTES_DEPOIS_OK):
            continue
        t = _apara(Trecho(arquivo, ini, i - ini, "".join(chars), "ascii", japones), 0x20, d)
        if t and len(t.texto) >= minimo and parece_texto(t.texto):
            out.append(t)
    return out


# bytes que podem estar num nome em -0x20: espaço, letras, dígitos e a pontuação de nomes (! & ' , - . : ?)
_NOME = set([0x00]) | set(range(0x21, 0x3B)) | set(range(0x41, 0x5B)) | set(range(0x10, 0x1A)) | {
    0x01, 0x06, 0x07, 0x0C, 0x0D, 0x0E, 0x1A, 0x1F}


def achar_menos20(arquivo: str, d: bytes, minimo: int = 3) -> list[Trecho]:
    """Cada 0xFF: volta byte a byte enquanto forem caracteres de nome; o trecho é dali até antes do 0xFF."""
    out, ant = [], -1
    for fim in (m.start() for m in re.finditer(b"\xff", d)):
        ini = fim
        while ini - 1 > ant and d[ini - 1] in _NOME:
            ini -= 1
        ant = fim
        if fim - ini < minimo:
            continue
        texto = "".join(chr(b + 0x20) for b in d[ini:fim])
        t = _apara(Trecho(arquivo, ini, fim - ini, texto, "menos20"), 0x00, d)
        if t and len(t.texto) >= minimo and parece_texto(t.texto):
            out.append(t)
    return out


def sem_acento(s: str) -> str:
    for a, b in (("“", '"'), ("”", '"'), ("‘", "'"), ("’", "'"), ("…", "..."), ("—", "-"), ("–", "-"),
                 ("ç", "c"), ("Ç", "C")):
        s = s.replace(a, b)
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    return "".join(c for c in s if 0x20 <= ord(c) <= 0x7E)


def _bytes(texto: str, tipo: str, sjis: bool = False) -> list[bytes]:
    """Cada caractere vira os bytes dele no formato (o "'" em ASCII ocupa 2; com `sjis`, . ? ! , números também)."""
    if tipo == "ascii":  # falas/descrições: acentos pelos códigos 0x8540.. (dc.traducao.sotn_falas_fonte)
        from .sotn_falas_fonte import CODIGO
        return [APOSTROFO if c == "'" else SJIS_DE[c] if sjis and c in SJIS_DE
                else struct.pack(">H", CODIGO[c]) if c in CODIGO else c.encode("ascii") for c in texto]
    if tipo == "menos20":  # acentos: células da fonte 8x8 redesenhadas (dc.traducao.sotn_fonte)
        from .sotn_fonte import INDICE
        return [bytes([INDICE[c]]) if c in INDICE else bytes([ord(c) - 0x20]) for c in texto]
    raise ValueError(f"tipo inválido: {tipo}")


def codificar(texto: str, tam: int, tipo: str, sjis: bool = False) -> bytes:
    """Exatamente `tam` bytes: corta em palavra inteira se precisar e completa com espaço."""
    if tipo == "menos20":  # a fonte 8x8 tem as letras acentuadas do português: só tira o que ela não tem
        from .sotn_fonte import INDICE as tem
    else:  # falas: letras novas na tabela do jogo (patch da rotina de letras)
        from .sotn_falas_fonte import CODIGO as tem
    texto = "".join(c if c in tem else sem_acento(c) for c in texto)
    pedacos = _bytes(texto, tipo, sjis)
    espaco = b" " if tipo == "ascii" else b"\x00"
    total, corte, ultimo_espaco = 0, len(pedacos), None
    for k, p in enumerate(pedacos):
        if total + len(p) > tam:
            corte = ultimo_espaco if ultimo_espaco else k
            break
        if p == espaco:
            ultimo_espaco = k
        total += len(p)
    out = b"".join(pedacos[:corte]).rstrip(espaco)
    return out + espaco * (tam - len(out))


def aplicar(d: bytes, trocas: list[tuple[Trecho, str]]) -> bytes:
    novo = bytearray(d)
    ocupado: list[tuple[int, int]] = []
    for t, texto in sorted(trocas, key=lambda x: x[0].pos):
        if ocupado and t.pos < ocupado[-1][1]:
            raise ValueError(f"trechos sobrepostos em {t.arquivo} @{t.pos}")
        novo[t.pos:t.pos + t.tam] = codificar(texto, t.tam, t.tipo, t.sjis)
        ocupado.append((t.pos, t.pos + t.tam))
    return bytes(novo)
