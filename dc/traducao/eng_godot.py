"""Godot 3 e 4: textos de dentro do pacote .pck ("GDPC") e regravação de um .pck NOVO e completo.

Por que o pck inteiro: o LayeredFS do Ryujinx troca arquivos do RomFS, e o Godot só enxerga o que está dentro
do .pck. Então o mod é o mesmo .pck com os arquivos de texto trocados (mesma versão, flags e alinhamento).

Formato do .pck (core/io/file_access_pack.cpp e editor/export do Godot, que são abertos):
- "GDPC", versão do formato (1 = Godot 3; 2 = Godot 4.0–4.4), versão do Godot (maior, menor, patch);
- só v2: flags u32 (1 = diretório criptografado, 2 = file_base relativo) e file_base u64;
- 16 × u32 reservados, quantidade de arquivos;
- por arquivo: tamanho do caminho u32 (já com o enchimento até múltiplo de 4), caminho, offset u64, tamanho u64,
  md5 (16) e, só v2, flags u32 (1 = arquivo criptografado, 2 = "removido" no 4.4).
  No v1 o offset é a partir do início do pck; no v2 é a partir do file_base.

O que vira texto para traduzir (dentro do pck):
- .csv de tradução (cabeçalho com a coluna "en"): troca a coluna en;
- .json: valores de texto com espaço e letras (as chaves nunca);
- .tscn/.tres (texto): text, bbcode_text, dialog_text, hint_tooltip, tooltip_text, placeholder_text, window_title, title;
- .scn/.res/.translation BINÁRIOS ("RSRC"): Translation (Godot 3: messages = pares chave/valor; Godot 4:
  dicionário) e cenas PackedScene (as mesmas propriedades de texto acima);
- .dialogue (addon Dialogue Manager): falas e respostas.
NÃO suportado (vira aviso): OptimizedTranslation/PHashTranslation (texto comprimido com o "smaz" do Godot),
recursos binários compactados ("RSCC"), arquivos criptografados, pck v3 (Godot 4.5+) e pck embutido no executável.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import struct
from collections.abc import Callable
from dataclasses import dataclass, field

from .motores import CODES_PADRAO, Coleta, MotorError, Texto

NAME = "Godot"

PCK_MAGIC = b"GDPC"
RSRC_MAGIC = b"RSRC"
_DIR_CRIPTO = 1          # flag do pck v2: diretório criptografado
_ARQ_CRIPTO = 1          # flag do arquivo no pck v2: conteúdo criptografado

# BBCode [b] [/b] [color=..], {var} e {{var}} (Dialogue Manager), %s, quebras de linha
CODES = re.compile(r"\{\{.*?\}\}|" + CODES_PADRAO.pattern)

_PROPS_TEXTO = ("text", "bbcode_text", "dialog_text", "hint_tooltip", "tooltip_text", "placeholder_text",
                "window_title", "title")
_CHAVE = re.compile(r"^[A-Z0-9_.\-/:]+$")     # "MENU_START": chave de tr(), não texto (traduzir quebra a busca)
_LETRAS = re.compile(r"[^\W\d_]{2,}")

# arquivos .pck que não são do Godot costumam ser bancos de som do Wwise (magic "AKPK") em pastas de áudio
_PASTAS_SOM = ("audio", "sound", "wwise", "streamingassets", "bgm", "se/", "voice")
_OUTROS_MOTORES = ("globalgamemanagers", "data.unity3d", "/managed/", ".utoc", "/content/paks/", "re_chunk_")


# ================================================================== detecção
def detect(paths: list[str]) -> bool:
    low = [p.lower() for p in paths]
    if any(m in p for p in low for m in _OUTROS_MOTORES):
        return False
    return any(p.endswith(".pck") and not any(s in p for s in _PASTAS_SOM) for p in low)


def pck_embutido(exe: bytes) -> bool:
    """True se o executável traz um pck do Godot colado no fim (rodapé: tamanho u64 + "GDPC")."""
    return len(exe) >= 12 and exe[-4:] == PCK_MAGIC


# ================================================================== pck
@dataclass
class PckEntry:
    path: str
    raw_path: bytes      # caminho como está gravado (com o enchimento), para regravar igualzinho
    offset: int          # absoluto dentro do pck
    size: int
    md5: bytes
    flags: int = 0


@dataclass
class Pck:
    version: int
    godot: tuple
    flags: int
    file_base: int
    reserved: bytes
    entries: list
    align: int
    extra: dict = field(default_factory=dict)


def read_pck(data: bytes) -> Pck:
    if data[:4] != PCK_MAGIC:
        raise MotorError("não é um pacote .pck do Godot (falta o 'GDPC')")
    try:
        ver, ma, mi, pa = struct.unpack_from("<4I", data, 4)
        p = 20
        flags = file_base = 0
        if ver == 2:
            flags, file_base = struct.unpack_from("<IQ", data, p)
            p += 12
        elif ver != 1:
            raise MotorError(f"pck no formato {ver} (Godot {ma}.{mi}): só sei ler o 1 (Godot 3) e o 2 (Godot 4.0–4.4)")
        if flags & _DIR_CRIPTO:
            raise MotorError("o .pck deste jogo é criptografado: a chave AES fica compilada dentro do executável "
                             "do jogo (script_encryption_key), e eu não tenho como tirar de lá")
        reserved = data[p:p + 64]
        p += 64
        (count,) = struct.unpack_from("<I", data, p)
        p += 4
        entries = []
        for _ in range(count):
            (n,) = struct.unpack_from("<I", data, p)
            raw = data[p + 4:p + 4 + n]
            if len(raw) != n:
                raise MotorError("diretório do pck truncado")
            p += 4 + n
            off, size = struct.unpack_from("<QQ", data, p)
            md5 = data[p + 16:p + 32]
            p += 32
            fl = 0
            if ver == 2:
                (fl,) = struct.unpack_from("<I", data, p)
                p += 4
            off += file_base if ver == 2 else 0
            if off + size > len(data) and not fl:
                raise MotorError(f"arquivo fora do pck: {raw!r}")
            entries.append(PckEntry(raw.rstrip(b"\0").decode("utf-8", "replace"), raw, off, size, md5, fl))
    except struct.error as e:
        raise MotorError(f"pck truncado ({e})") from None
    base = file_base if ver == 2 else 0
    pck = Pck(ver, (ma, mi, pa), flags, file_base, reserved, entries, _alinhamento([e.offset - base for e in entries]))
    pck.extra["dir_end"] = p
    return pck


def _alinhamento(rel_offsets: list[int]) -> int:
    """Maior potência de 2 (até 4096) que divide todos os offsets: é o alinhamento que o exportador usou."""
    a = 4096
    while a > 1 and any(o % a for o in rel_offsets):
        a //= 2
    return a


def _pad(n: int, a: int) -> int:
    return (-n) % a if a > 1 else 0


def _span(pck: Pck, data: bytes, i: int, ordem: list[int]) -> bytes:
    """Bytes do arquivo i como estão no pck. Criptografado: o tamanho no disco é maior que `size`
    (cabeçalho + enchimento da cifra), então copia até o começo do próximo arquivo."""
    e = pck.entries[i]
    if not (e.flags & _ARQ_CRIPTO):
        return data[e.offset:e.offset + e.size]
    k = ordem.index(i)
    fim = pck.entries[ordem[k + 1]].offset if k + 1 < len(ordem) else len(data)
    return data[e.offset:fim]


def write_pck(pck: Pck, data: bytes, novos: dict[int, bytes]) -> bytes:
    """Pck novo: mesmo diretório (ordem, caminhos, flags), arquivos `novos` trocados e md5 recalculado deles."""
    ordem = sorted(range(len(pck.entries)), key=lambda i: (pck.entries[i].offset, i))
    head = bytearray(PCK_MAGIC + struct.pack("<4I", pck.version, *pck.godot))
    if pck.version == 2:
        head += struct.pack("<IQ", pck.flags, 0)  # file_base preenchido abaixo
    head += pck.reserved + struct.pack("<I", len(pck.entries))
    dir_pos = []
    for e in pck.entries:
        head += struct.pack("<I", len(e.raw_path)) + e.raw_path
        dir_pos.append(len(head))
        head += bytes(32 + (4 if pck.version == 2 else 0))
    base = len(head) + _pad(len(head), pck.align)
    corpo = bytearray()
    novo_off: dict[int, int] = {}
    visto: dict[tuple, int] = {}
    for i in ordem:
        e = pck.entries[i]
        chave = (e.offset, e.size)
        if i not in novos and chave in visto:   # dois nomes apontando para os mesmos bytes
            novo_off[i] = visto[chave]
            continue
        corpo += bytes(_pad(len(corpo), pck.align))
        novo_off[i] = len(corpo)
        corpo += novos[i] if i in novos else _span(pck, data, i, ordem)
        if i not in novos:
            visto[chave] = novo_off[i]
    for i, e in enumerate(pck.entries):
        off = novo_off[i] + (0 if pck.version == 2 else base)
        size = len(novos[i]) if i in novos else e.size
        md5 = hashlib.md5(novos[i]).digest() if i in novos else e.md5
        rec = struct.pack("<QQ", off, size) + md5
        if pck.version == 2:
            rec += struct.pack("<I", e.flags)
        head[dir_pos[i]:dir_pos[i] + len(rec)] = rec
    if pck.version == 2:
        struct.pack_into("<Q", head, 24, base)
    return bytes(head) + bytes(base - len(head)) + bytes(corpo)


# ================================================================== extratores (um por tipo de arquivo)
# Cada extrator devolve ([(id local, texto)], aplicar) — aplicar({id local: novo}) devolve os bytes novos.
Extrator = tuple[list[tuple[str, str]], Callable[[dict[str, str]], bytes]]


class _Pula(Exception):
    """Arquivo que não dá para usar (formato não suportado); o motivo vira aviso, não erro."""


# ---------------------------------------------------------------- .csv de tradução
def _ext_csv(data: bytes) -> Extrator:
    bom = data.startswith(b"\xef\xbb\xbf")
    txt = data.decode("utf-8-sig")
    primeira = txt.split("\n", 1)[0]
    delim = max((",", ";", "\t"), key=primeira.count)
    nl = "\r\n" if "\r\n" in txt else "\n"
    rows = list(csv.reader(io.StringIO(txt, newline=""), delimiter=delim))
    if not rows:
        raise _Pula("csv vazio")
    head = [h.strip().lower() for h in rows[0]]
    col = next((k for k, h in enumerate(head) if h == "en"), None)
    if col is None:
        col = next((k for k, h in enumerate(head) if h.startswith(("en_", "en-"))), None)
    if col is None or col == 0:
        raise _Pula("csv sem coluna 'en'")
    itens = [(f"r{r}", row[col]) for r, row in enumerate(rows) if r and len(row) > col and row[col]]

    def aplicar(novos: dict[str, str]) -> bytes:
        out_rows = [list(r) for r in rows]
        for lid, s in novos.items():
            out_rows[int(lid[1:])][col] = s
        buf = io.StringIO(newline="")
        csv.writer(buf, delimiter=delim, lineterminator=nl).writerows(out_rows)
        b = buf.getvalue()
        if not txt.endswith(("\n", "\r")) and b.endswith(nl):
            b = b[:-len(nl)]
        return (b"\xef\xbb\xbf" if bom else b"") + b.encode("utf-8")
    return itens, aplicar


# ---------------------------------------------------------------- .json
_JSON_STR = re.compile(r'"(?:[^"\\]|\\.)*"', re.DOTALL)


def _ext_json(data: bytes) -> Extrator:
    """Troca só o trecho de cada string no arquivo (não reformata o JSON)."""
    bom = data.startswith(b"\xef\xbb\xbf")
    txt = data.decode("utf-8-sig")
    try:
        json.loads(txt)
    except ValueError:
        raise _Pula("json inválido") from None
    spans = []
    for m in _JSON_STR.finditer(txt):
        resto = txt[m.end():m.end() + 64].lstrip()
        if resto.startswith(":"):
            continue  # chave de objeto
        s = json.loads(m.group())
        if " " in s.strip() and _LETRAS.search(s) and not s.startswith(("res://", "user://", "http")):
            spans.append((m.start(), m.end(), s))
    itens = [(f"s{k}", s) for k, (_a, _b, s) in enumerate(spans)]

    def aplicar(novos: dict[str, str]) -> bytes:
        out, pos = [], 0
        for k, (a, b, _s) in enumerate(spans):
            if f"s{k}" in novos:
                out += [txt[pos:a], json.dumps(novos[f"s{k}"], ensure_ascii=False)]
                pos = b
        out.append(txt[pos:])
        return (b"\xef\xbb\xbf" if bom else b"") + "".join(out).encode("utf-8")
    return itens, aplicar


# ---------------------------------------------------------------- .tscn / .tres (texto)
_TSCN_PROP = re.compile(r"^(?:{})\s*=\s*\"".format("|".join(_PROPS_TEXTO)), re.MULTILINE)
_ESC = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", '"': '"', "\\": "\\", "'": "'"}


def _godot_unescape(s: str) -> str:
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            n = s[i + 1]
            if n in ("u", "U"):
                k = 4 if n == "u" else 6
                try:
                    out.append(chr(int(s[i + 2:i + 2 + k], 16)))
                    i += 2 + k
                    continue
                except ValueError:
                    pass
            out.append(_ESC.get(n, n))
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _godot_escape(s: str) -> str:
    """Como o Godot grava (String::c_escape_multiline): só \\ e aspas; quebra de linha fica literal."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _ext_tscn(data: bytes) -> Extrator:
    txt = data.decode("utf-8")
    spans = []
    for m in _TSCN_PROP.finditer(txt):
        a = i = m.end()
        while i < len(txt) and txt[i] != '"':
            i += 2 if txt[i] == "\\" else 1
        if i >= len(txt):
            break
        s = _godot_unescape(txt[a:i])
        if s.strip() and not _CHAVE.match(s.strip()):
            spans.append((a, i, s))
    itens = [(f"p{k}", s) for k, (_a, _b, s) in enumerate(spans)]

    def aplicar(novos: dict[str, str]) -> bytes:
        out, pos = [], 0
        for k, (a, b, _s) in enumerate(spans):
            if f"p{k}" in novos:
                out += [txt[pos:a], _godot_escape(novos[f"p{k}"])]
                pos = b
        out.append(txt[pos:])
        return "".join(out).encode("utf-8")
    return itens, aplicar


# ---------------------------------------------------------------- .dialogue (Dialogue Manager)
_DLG_CODIGO = ("#", "~", "=>", "if ", "elif ", "else", "do ", "do!", "set ", "while ", "match ", "when ",
               "import ", "using ", "[if", "%%")
_DLG_FALA = re.compile(r"^([^:\[\]{}\"]{1,40}?):\s+(.*)$")


def _ext_dialogue(data: bytes) -> Extrator:
    txt = data.decode("utf-8-sig")
    bom = data.startswith(b"\xef\xbb\xbf")
    linhas = txt.splitlines(keepends=True)
    partes = {}   # nº da linha -> (prefixo, texto, sufixo)
    for n, ln in enumerate(linhas):
        corpo = ln.rstrip("\r\n")
        fim = ln[len(corpo):]
        s = corpo.strip()
        if not s or s.startswith(_DLG_CODIGO):
            continue
        pre = corpo[:len(corpo) - len(corpo.lstrip())]
        if s.startswith("%"):  # linha aleatória com peso: "%2 texto"
            m = re.match(r"^%\d*\s*", s)
            pre, s = pre + m.group(), s[m.end():]
        if s.startswith("- "):  # resposta: "- texto [if cond] => destino"
            pre, s = pre + "- ", s[2:]
            cortes = [k for k in (s.find(" =>"), s.find(" [if ")) if k >= 0]
            cut = min(cortes) if cortes else len(s)
            texto, suf = s[:cut], s[cut:]
        else:
            m = _DLG_FALA.match(s)
            if m:
                pre, texto = pre + s[:m.start(2)], m.group(2)
            else:
                texto = s
            suf = ""
        if _LETRAS.search(CODES.sub(" ", texto)):
            partes[n] = (pre, texto, suf + fim)
    itens = [(f"l{n}", t) for n, (_p, t, _s) in partes.items()]

    def aplicar(novos: dict[str, str]) -> bytes:
        out = list(linhas)
        for lid, s in novos.items():
            n = int(lid[1:])
            pre, _t, suf = partes[n]
            out[n] = pre + s.replace("\r", " ").replace("\n", " ") + suf
        return (b"\xef\xbb\xbf" if bom else b"") + "".join(out).encode("utf-8")
    return itens, aplicar


# ---------------------------------------------------------------- recurso binário "RSRC"
@dataclass
class _S:
    """Texto dentro do recurso binário, com a posição exata (u32 tamanho + utf-8 + \\0) para trocar no lugar."""
    text: str
    start: int
    end: int


# códigos de tipo do formato binário (core/io/resource_format_binary.cpp; iguais no Godot 3 e 4)
_V_NIL, _V_BOOL, _V_INT, _V_FLOAT, _V_STRING = 1, 2, 3, 4, 5
_V_NODE_PATH, _V_RID, _V_OBJECT, _V_INPUT_EVENT, _V_DICT, _V_ARRAY = 22, 23, 24, 25, 26, 30
_V_BYTES, _V_INT32S, _V_FLOAT32S, _V_STRINGS = 31, 32, 33, 34
_V_VEC3S, _V_COLORS, _V_VEC2S, _V_INT64, _V_DOUBLE = 35, 36, 37, 40, 41
_V_CALLABLE, _V_SIGNAL, _V_STRING_NAME = 42, 43, 44
_V_INT64S, _V_FLOAT64S, _V_VEC4S = 48, 49, 53
_REAIS = {10: 2, 11: 4, 12: 3, 13: 4, 14: 4, 15: 6, 16: 9, 17: 12, 18: 6, 50: 4, 52: 16}   # tipo -> qtd de real_t
_INTEIROS = {45: 2, 46: 4, 47: 3, 51: 4}                                                     # Vector2i etc.


class _Rsrc:
    def __init__(self, b: bytes):
        self.b = b
        if b[:4] == b"RSCC":
            raise _Pula("recurso binário compactado (RSCC)")
        if b[:4] != RSRC_MAGIC:
            raise _Pula("não é recurso binário")
        self.p = 4
        big, real64 = self.u32(), self.u32()
        if big:
            raise _Pula("recurso big-endian")
        self.major, self.minor, self.fmt = self.u32(), self.u32(), self.u32()
        self.g4 = self.major >= 4 or self.fmt >= 4
        self.tipo = self.ustr()
        self.importmd_pos = self.p
        self.importmd = self.u64()
        flags = 0
        if self.g4:
            flags = self.u32()
            self.p += 8            # uid
            if flags & 8:          # FORMAT_FLAG_HAS_SCRIPT_CLASS
                self.ustr()
            self.p += 11 * 4
        else:
            self.p += 14 * 4
        self.real = 8 if (real64 or flags & 4) else 4
        self.nomes = [self.ustr() for _ in range(self.u32())]
        for _ in range(self.u32()):  # recursos externos
            self.ustr()
            self.ustr()
            if self.g4 and flags & 2:
                self.p += 8
        self.internos = []          # (posição do campo offset no cabeçalho, offset)
        for _ in range(self.u32()):
            self.ustr()
            self.internos.append((self.p, self.u64()))

    # --- leitura básica
    def take(self, n: int) -> bytes:
        if n < 0 or self.p + n > len(self.b):
            raise _Pula("recurso binário truncado")
        v = self.b[self.p:self.p + n]
        self.p += n
        return v

    def u32(self) -> int:
        return struct.unpack("<I", self.take(4))[0]

    def u64(self) -> int:
        return struct.unpack("<Q", self.take(8))[0]

    def ustr(self) -> str:
        n = self.u32() & 0x7FFFFFFF
        return self.take(n).split(b"\0", 1)[0].decode("utf-8", "replace")

    def ustr_s(self) -> _S:
        a = self.p
        s = self.ustr()
        return _S(s, a, self.p)

    def nome(self) -> str:
        i = self.u32()
        if i & 0x80000000:
            return self.take(i & 0x7FFFFFFF).split(b"\0", 1)[0].decode("utf-8", "replace")
        if i >= len(self.nomes):
            raise _Pula("índice de nome inválido")
        return self.nomes[i]

    # --- valores
    def valor(self, prof: int = 0):
        if prof > 64:
            raise _Pula("recurso aninhado demais")
        t = self.u32()
        if t in (_V_NIL, _V_INPUT_EVENT, _V_CALLABLE, _V_SIGNAL):
            return None
        if t in (_V_BOOL, _V_INT, _V_RID):
            return struct.unpack("<i", self.take(4))[0]
        if t == _V_FLOAT:
            n = 4 if self.g4 else self.real
            return struct.unpack("<f" if n == 4 else "<d", self.take(n))[0]
        if t in (_V_INT64, _V_DOUBLE):
            self.take(8)
            return None
        if t in (_V_STRING, _V_STRING_NAME):
            return self.ustr_s()
        if t in _REAIS:
            self.take(_REAIS[t] * self.real)
            return None
        if t in _INTEIROS:
            self.take(_INTEIROS[t] * 4)
            return None
        if t == 20:  # Color: float no Godot 4, real_t no Godot 3
            self.take(4 * (4 if self.g4 else self.real))
            return None
        if t == _V_NODE_PATH:
            nn = struct.unpack("<H", self.take(2))[0]
            sn = struct.unpack("<H", self.take(2))[0] & 0x7FFF
            if not self.g4 and self.fmt < 3:
                sn += 1
            for _ in range(nn + sn):
                self.nome()
            return None
        if t == _V_OBJECT:
            k = self.u32()
            if k == 1:
                self.ustr()
                self.ustr()
            elif k in (2, 3):
                self.u32()
            elif k:
                raise _Pula(f"objeto de tipo {k} desconhecido")
            return None
        if t == _V_DICT:
            n = self.u32() & 0x7FFFFFFF
            return {"__dict__": [(self.valor(prof + 1), self.valor(prof + 1)) for _ in range(n)]}
        if t == _V_ARRAY:
            n = self.u32() & 0x7FFFFFFF
            return [self.valor(prof + 1) for _ in range(n)]
        if t == _V_BYTES:
            n = self.u32()
            self.take(n + _pad(n, 4))
            return None
        if t == _V_INT32S:
            n = self.u32()
            return list(struct.unpack(f"<{n}i", self.take(4 * n)))
        if t == _V_FLOAT32S:
            n = self.u32()
            self.take(n * (4 if self.g4 else self.real))
            return None
        if t == _V_STRINGS:
            n = self.u32()
            return ("strings", [self.ustr_s() for _ in range(n)])
        if t in (_V_VEC2S, _V_VEC3S, _V_VEC4S):
            n = self.u32()
            self.take(n * {_V_VEC2S: 2, _V_VEC3S: 3, _V_VEC4S: 4}[t] * self.real)
            return None
        if t == _V_COLORS:
            n = self.u32()
            self.take(n * 4 * (4 if self.g4 else self.real))
            return None
        if t in (_V_INT64S, _V_FLOAT64S):
            n = self.u32()
            self.take(n * 8)
            return None
        raise _Pula(f"tipo de valor {t} que eu não conheço")

    def recursos(self):
        """[(tipo, {propriedade: valor})] dos recursos internos (o último é o principal)."""
        out = []
        for _pos, off in self.internos:
            self.p = off
            tipo = self.ustr()
            props = {}
            for _ in range(self.u32()):
                nm = self.nome()
                props[nm] = self.valor()
            out.append((tipo, props))
        return out

    def regravar(self, trocas: dict[int, str], spans: list[_S]) -> bytes:
        """Troca as strings `spans[k]` (k em trocas) e corrige os offsets dos recursos internos no cabeçalho."""
        alvo = sorted(((spans[k], s) for k, s in trocas.items()), key=lambda x: x[0].start)
        out, pos, deltas = bytearray(), 0, []
        for sp, s in alvo:
            u = s.encode("utf-8") + b"\0"
            novo = struct.pack("<I", len(u)) + u
            out += self.b[pos:sp.start] + novo
            deltas.append((sp.start, len(novo) - (sp.end - sp.start)))
            pos = sp.end
        out += self.b[pos:]

        def mover(x: int) -> int:
            return x + sum(d for a, d in deltas if a < x)
        for campo, off in self.internos:   # o cabeçalho vem antes de qualquer string trocada
            struct.pack_into("<Q", out, campo, mover(off))
        if self.importmd:
            struct.pack_into("<Q", out, self.importmd_pos, mover(self.importmd))
        return bytes(out)


def _str_de(v) -> str | None:
    return v.text if isinstance(v, _S) else None


def _dict_get(d, chave: str):
    if isinstance(d, dict):
        for k, v in d.get("__dict__", []):
            if _str_de(k) == chave:
                return v
    return None


def _folhas(v) -> list[_S]:
    """Todas as strings de um valor (para os VALORES de um dicionário de mensagens)."""
    if isinstance(v, _S):
        return [v]
    if isinstance(v, tuple):
        return list(v[1])
    if isinstance(v, list):
        return [s for x in v for s in _folhas(x)]
    if isinstance(v, dict):
        return [s for _k, x in v.get("__dict__", []) for s in _folhas(x)]
    return []


_TRAD_OK = ("Translation", "TranslationPO")
_TRAD_NAO = ("PHashTranslation", "OptimizedTranslation")


def _spans_rsrc(r: _Rsrc) -> list[_S]:
    """Strings traduzíveis de um recurso binário (Translation em inglês ou cena)."""
    recs = r.recursos()
    if not recs:
        return []
    tipo, props = recs[-1]
    if tipo in _TRAD_NAO:
        raise _Pula(f"{tipo} (texto comprimido do Godot) não é suportado")
    if tipo in _TRAD_OK:
        loc = _str_de(props.get("locale")) or ""
        if not loc.lower().startswith("en"):
            return []
        msgs = props.get("messages")
        if isinstance(msgs, tuple):              # Godot 3: [chave0, valor0, chave1, valor1, ...]
            return list(msgs[1][1::2])
        if isinstance(msgs, dict):               # Godot 4: {chave: valor} (TranslationPO: {contexto: {id: [..]}})
            return [s for _k, v in msgs["__dict__"] for s in _folhas(v)]
        return []
    if tipo == "PackedScene":
        return _spans_cena(props.get("_bundled"))
    return []


def _spans_cena(b) -> list[_S]:
    """Lê o _bundled de uma cena: nós -> (propriedade, índice do valor) e pega as propriedades de texto."""
    nomes = _dict_get(b, "names")
    valores = _dict_get(b, "variants")
    nos = _dict_get(b, "nodes")
    qtd = _dict_get(b, "node_count")
    versao = _dict_get(b, "version")
    if not (isinstance(nomes, tuple) and isinstance(valores, list) and isinstance(nos, list) and isinstance(qtd, int)):
        return []
    nomes = [s.text for s in nomes[1]]
    versao = versao if isinstance(versao, int) else 2
    out, vistos, i = [], set(), 0
    try:
        for _ in range(qtd):
            i += 5 + (1 if versao >= 3 else 0)   # pai, dono, tipo, nome, instância [, índice no Godot 4]
            n_props = nos[i]
            i += 1
            for _p in range(n_props):
                nm, vi = nos[i] & ((1 << 30) - 1), nos[i + 1]
                i += 2
                v = valores[vi]
                if nomes[nm] in _PROPS_TEXTO and isinstance(v, _S) and vi not in vistos:
                    vistos.add(vi)
                    out.append(v)
            i += 1 + nos[i]                      # grupos
    except (IndexError, TypeError):
        raise _Pula("cena binária com estrutura inesperada") from None
    return out


def _ext_rsrc(data: bytes) -> Extrator:
    r = _Rsrc(data)
    spans = [s for s in _spans_rsrc(r) if s.text.strip() and not _CHAVE.match(s.text.strip())]
    spans.sort(key=lambda s: s.start)
    itens = [(f"v{k}", s.text) for k, s in enumerate(spans)]

    def aplicar(novos: dict[str, str]) -> bytes:
        return r.regravar({int(k[1:]): s for k, s in novos.items()}, spans)
    return itens, aplicar


def _tipo_rsrc(data: bytes) -> str:
    """Só o tipo do recurso (barato), para não varrer malhas e texturas inteiras."""
    if data[:4] != RSRC_MAGIC or len(data) < 28:
        return ""
    n = struct.unpack_from("<I", data, 24)[0] & 0x7FFFFFFF
    return data[28:28 + min(n, 128)].split(b"\0", 1)[0].decode("utf-8", "replace")


def _extrator(caminho: str, data: bytes):
    low = caminho.lower()
    if low.endswith(".csv"):
        return _ext_csv(data)
    if low.endswith(".json"):
        return _ext_json(data)
    if low.endswith((".tscn", ".tres")):
        return _ext_tscn(data)
    if low.endswith(".dialogue"):
        return _ext_dialogue(data)
    if low.endswith((".translation", ".scn", ".res")):
        if data[:4] == b"RSCC":
            raise _Pula("recurso binário compactado (RSCC)")
        t = _tipo_rsrc(data)
        if t in _TRAD_OK or t in _TRAD_NAO or t == "PackedScene":
            return _ext_rsrc(data)
    return None


# ================================================================== contrato
def collect(files: dict, read: Callable[[str], bytes]) -> Coleta:
    pcks = sorted(p for p in files if p.lower().endswith(".pck"))
    if not pcks:
        for p in files:
            if p.lower().endswith((".nso", "/main", ".exe", ".x86_64")) and pck_embutido(read(p)):
                raise MotorError(f"o pacote do Godot está embutido no executável ({p}); só sei regravar um .pck "
                                 "solto no RomFS")
        raise MotorError("não achei nenhum .pck do Godot no RomFS (pode estar embutido no executável)")
    textos: list[Texto] = []
    estado = {}   # pck -> (bytes, Pck, {i: (caminho, itens, aplicar)})
    avisos: dict[str, int] = {}
    for pk in pcks:
        data = read(pk)
        if data[:4] != PCK_MAGIC:
            continue  # ex.: banco de som do Wwise ("AKPK")
        pck = read_pck(data)
        arqs = {}
        for i, e in enumerate(pck.entries):
            low = e.path.lower()
            if not low.endswith((".csv", ".json", ".tscn", ".tres", ".dialogue", ".translation", ".scn", ".res")):
                continue
            if e.flags & _ARQ_CRIPTO:
                avisos["arquivo criptografado no pck"] = avisos.get("arquivo criptografado no pck", 0) + 1
                continue
            try:
                ext = _extrator(e.path, data[e.offset:e.offset + e.size])
            except _Pula as x:
                avisos[str(x)] = avisos.get(str(x), 0) + 1
                continue
            except (UnicodeDecodeError, ValueError, struct.error):
                avisos["arquivo ilegível"] = avisos.get("arquivo ilegível", 0) + 1
                continue
            if not ext or not ext[0]:
                continue
            itens, aplicar = ext
            arqs[i] = (e.path, itens, aplicar)
            for lid, s in itens:
                textos.append(Texto(f"{pk}|{i}|{lid}", s, CODES))
        estado[pk] = (data, pck, arqs)
    if not estado:
        raise MotorError("os .pck do RomFS não são do Godot (sem 'GDPC'; .pck do Wwise é som)")
    aviso = "; ".join(f"{n}× {m}" for m, n in sorted(avisos.items()))
    if any(path.lower().endswith(".csv") for _d, _p, a in estado.values() for path, _i, _f in a.values()):
        aviso = (aviso + "; " if aviso else "") + ("o .csv dentro do pck só vale se o jogo lê o csv em tempo de "
                                                   "execução; o normal é o Godot usar o .translation importado")

    def rebuild(traduzidos: dict[str, str]) -> dict[str, bytes]:
        por_pck: dict[str, dict[int, dict[str, str]]] = {}
        for tid, s in traduzidos.items():
            pk, i, lid = tid.split("|", 2)
            por_pck.setdefault(pk, {}).setdefault(int(i), {})[lid] = s
        out = {}
        for pk, por_arq in por_pck.items():
            if pk not in estado:
                raise MotorError(f"pck desconhecido: {pk}")
            data, pck, arqs = estado[pk]
            novos = {}
            for i, trocas in por_arq.items():
                caminho, itens, aplicar = arqs[i]
                nb = aplicar(trocas)
                esperado = {lid: trocas.get(lid, s) for lid, s in itens}
                back = _extrator(caminho, nb)
                if back is None or dict(back[0]) != esperado:
                    raise MotorError(f"{caminho}: a releitura do arquivo traduzido não confere")
                novos[i] = nb
            blob = write_pck(pck, data, novos)
            _conferir(pck, data, novos, blob)
            out[pk] = blob
        return out

    return Coleta(textos, rebuild, aviso)


def _conferir(orig: Pck, data: bytes, novos: dict[int, bytes], blob: bytes) -> None:
    """Relê o pck gravado: mesmo diretório, cada arquivo com os bytes certos e md5 dos trocados."""
    back = read_pck(blob)
    if (back.version, back.godot, back.flags, len(back.entries)) != (orig.version, orig.godot, orig.flags,
                                                                     len(orig.entries)):
        raise MotorError("o pck regravado não confere (cabeçalho)")
    ordem = sorted(range(len(orig.entries)), key=lambda i: (orig.entries[i].offset, i))
    base = back.file_base if back.version == 2 else 0
    for i, (a, b) in enumerate(zip(orig.entries, back.entries)):
        if a.raw_path != b.raw_path or a.flags != b.flags or (b.offset - base) % orig.align:
            raise MotorError(f"o pck regravado não confere ({a.path})")
        if i in novos:
            ok = blob[b.offset:b.offset + b.size] == novos[i] and b.md5 == hashlib.md5(novos[i]).digest()
        else:
            esperado = _span(orig, data, i, ordem)
            ok = blob[b.offset:b.offset + len(esperado)] == esperado and b.size == a.size and b.md5 == a.md5
        if not ok:
            raise MotorError(f"o pck regravado não confere ({a.path})")
