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
import unicodedata
from dataclasses import dataclass

APOSTROFO = b"\x81\x66"
_PROIBIDOS = set("_\\/{}|<>=#$@~^")
_EXT = (".BIN", ".VH", ".VB", ".TIM", ".STR", ".DAT", ".XA")


@dataclass
class Trecho:
    arquivo: str
    pos: int      # 1º byte do texto no arquivo
    tam: int      # bytes que o texto ocupa (sem o terminador)
    texto: str
    tipo: str     # "ascii" | "menos20"


def parece_texto(s: str) -> bool:
    """Frase/nome em inglês, não lixo binário nem nome de arquivo."""
    if sum(c.isalpha() for c in s) < 3 or len(set(s)) == 1:
        return False
    if not any(re.search(r"[aeiouAEIOU]", w) for w in re.findall(r"[A-Za-z]{3,}", s)):
        return False
    if sum(c.isalpha() or c == " " for c in s) / len(s) < 0.7 or set(s) & _PROIBIDOS:
        return False
    if s.upper().endswith(_EXT):
        return False
    return any(c.islower() for c in s) or " " in s.strip()  # "4ABCD"/"0OTION" (lixo, nome em -0x20) não passam


def _apara(t: Trecho, espaco: int, d: bytes) -> Trecho | None:
    """Tira espaços das pontas ajustando pos/tam (os espaços ficam no arquivo como estão)."""
    ini, fim = t.pos, t.pos + t.tam
    while ini < fim and d[ini] == espaco:
        ini += 1
    while fim > ini and d[fim - 1] == espaco:
        fim -= 1
    if fim <= ini:
        return None
    t.pos, t.tam, t.texto = ini, fim - ini, t.texto.strip()
    return t


def achar_ascii(arquivo: str, d: bytes, minimo: int = 4) -> list[Trecho]:
    out, i, n = [], 0, len(d)
    while i < n:
        if not (0x20 <= d[i] <= 0x7E or d[i:i + 2] == APOSTROFO):
            i += 1
            continue
        ini, chars = i, []
        while i < n and (0x20 <= d[i] <= 0x7E or d[i:i + 2] == APOSTROFO):
            if d[i:i + 2] == APOSTROFO:
                chars.append("'")
                i += 2
            else:
                chars.append(chr(d[i]))
                i += 1
        if i < n and d[i] == 0xFF:  # termina em 0xFF: é nome no formato -0x20 (achar_menos20 cuida)
            continue
        t = _apara(Trecho(arquivo, ini, i - ini, "".join(chars), "ascii"), 0x20, d)
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


def _bytes(texto: str, tipo: str) -> list[bytes]:
    """Cada caractere vira os bytes dele no formato (o "'" em ASCII ocupa 2)."""
    if tipo == "ascii":
        return [APOSTROFO if c == "'" else c.encode("ascii") for c in texto]
    if tipo == "menos20":
        return [bytes([ord(c) - 0x20]) for c in texto]
    raise ValueError(f"tipo inválido: {tipo}")


def codificar(texto: str, tam: int, tipo: str) -> bytes:
    """Exatamente `tam` bytes: corta em palavra inteira se precisar e completa com espaço."""
    pedacos = _bytes(sem_acento(texto), tipo)
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
        novo[t.pos:t.pos + t.tam] = codificar(texto, t.tam, t.tipo)
        ocupado.append((t.pos, t.pos + t.tam))
    return bytes(novo)
