"""Unity no Switch: textos em TextAsset (csv/tsv/json/xml/ini/txt/yarn/ink) e em MonoBehaviour com typetree
(ex.: I2 Localization), dentro de arquivos SerializedFile soltos (resources.assets, sharedassetsN.assets,
levelN...) ou de bundles UnityFS (data.unity3d, *.bundle, StreamingAssets/...).

Formatos (documentação pública de ferramentas abertas: AssetStudio, UnityPy, UABE):
- SerializedFile (versões 15 a 22): cabeçalho big-endian; metadados na ordem do arquivo (byte de endianness);
  tipos (com typetree opcional), tabela de objetos (path_id, início, tamanho, tipo). Objetos ficam a partir de
  data_offset, alinhados de 8 em 8.
- UnityFS: cabeçalho big-endian, "blocks info" (hash, blocos, nós de diretório) comprimido com LZ4/LZ4HC/LZMA
  ou sem compressão, depois os blocos de dados (cada um com sua compressão). Os nós são pedaços do fluxo
  descomprimido (um SerializedFile "CAB-...", o .resS dele etc.).

A regravação troca só os objetos traduzidos (recalcula início/tamanho dos objetos seguintes, mantendo o
alinhamento de 8) e, se veio de bundle, regrava o bundle SEM compressão (mesma assinatura/versão). Tudo é
relido antes de devolver: se não conferir, levanta MotorError e nada vai para o jogo. Arquivos .resS ficam
intocados.
"""
from __future__ import annotations

import html
import json
import lzma
import re
import struct
from dataclasses import dataclass, field
from typing import Callable
from xml.sax.saxutils import escape as _xml_escape

from . import lz4blk
from .motores import Coleta, MotorError, Texto

NAME = "Unity"

SF_MIN, SF_MAX = 15, 22
CLS_TEXTASSET, CLS_MONOBEHAVIOUR = 49, 114
ALIGN_FLAG = 0x4000
BUNDLE_CHUNK = 0x20000  # blocos de 128 KiB ao regravar (mesmo tamanho dos blocos LZ4 da Unity)


class UnityError(MotorError):
    pass


class _Pula(Exception):
    """Objeto que não sei ler com segurança: fica como está."""


# ------------------------------------------------------------------ leitura binária
class _R:
    def __init__(self, b: bytes, pos: int = 0, e: str = ">"):
        self.b, self.p, self.e = b, pos, e

    def take(self, n: int) -> bytes:
        if n < 0 or self.p + n > len(self.b):
            raise UnityError("dados terminaram antes do esperado")
        v = self.b[self.p:self.p + n]
        self.p += n
        return v

    def _u(self, fmt: str, n: int):
        return struct.unpack(self.e + fmt, self.take(n))[0]

    def u8(self): return self.take(1)[0]
    def i16(self): return self._u("h", 2)
    def u16(self): return self._u("H", 2)
    def i32(self): return self._u("i", 4)
    def u32(self): return self._u("I", 4)
    def i64(self): return self._u("q", 8)

    def cstr(self, limit: int = 4096) -> str:
        j = self.b.find(b"\0", self.p, self.p + limit)
        if j < 0:
            raise UnityError("texto sem terminador")
        s = self.b[self.p:j].decode("utf-8", "replace")
        self.p = j + 1
        return s

    def align(self, n: int = 4) -> None:
        self.p += (-self.p) % n


def _al(n: int, a: int = 16) -> int:
    return n + (-n) % a


# Tabela de nomes comuns do typetree (CommonString da Unity; offset | 0x80000000 aponta para cá)
_COMMON_LIST = (
    "AABB AnimationClip AnimationCurve AnimationState Array Base BitField bitset bool char ColorRGBA Component "
    "data deque double dynamic_array FastPropertyName first float Font GameObject |Generic Mono| GradientNEW GUID "
    "GUIStyle int list |long long| map Matrix4x4f MdFour MonoBehaviour MonoScript m_ByteSize m_Curve "
    "m_EditorClassIdentifier m_EditorHideFlags m_Enabled m_ExtensionPtr m_GameObject m_Index m_IsArray m_IsStatic "
    "m_MetaFlag m_Name m_ObjectHideFlags m_PrefabInternal m_PrefabParentObject m_Script m_StaticEditorFlags m_Type "
    "m_Version Object pair PPtr<Component> PPtr<GameObject> PPtr<Material> PPtr<MonoBehaviour> PPtr<MonoScript> "
    "PPtr<Object> PPtr<Prefab> PPtr<Sprite> PPtr<TextAsset> PPtr<Texture> PPtr<Texture2D> PPtr<Transform> Prefab "
    "Quaternionf Rectf RectInt RectOffset second set short size SInt16 SInt32 SInt64 SInt8 staticvector string "
    "TextAsset TextMesh Texture Texture2D Transform TypelessData UInt16 UInt32 UInt64 UInt8 |unsigned int| "
    "|unsigned long long| |unsigned short| vector Vector2f Vector3f Vector4f m_ScriptingClassIdentifier Gradient "
    "Type* int2_storage int3_storage BoundsInt m_CorrespondingSourceObject m_PrefabInstance m_PrefabAsset FileSize "
    "Hash128 RenderingLayerMask")


def _common_table() -> dict[int, str]:
    names = re.findall(r"\|([^|]+)\||(\S+)", _COMMON_LIST)
    out, off = {}, 0
    for a, b in names:
        s = a or b
        out[off] = s
        off += len(s) + 1
    return out


_COMMON = _common_table()


# ------------------------------------------------------------------ SerializedFile
@dataclass
class _Node:
    type: str
    name: str
    size: int
    flags: int
    meta: int
    children: list = field(default_factory=list)


@dataclass
class _Type:
    class_id: int
    tree: _Node | None


@dataclass
class _Obj:
    path_id: int
    start: int
    size: int
    class_id: int
    type: _Type | None
    f_start: int  # posição (no arquivo) do campo "início" na tabela de objetos; o tamanho vem logo depois


@dataclass
class _SF:
    data: bytes
    version: int
    e: str
    data_offset: int
    typetree: bool
    objects: list

    def obj(self, o: _Obj) -> bytes:
        a = self.data_offset + o.start
        return self.data[a:a + o.size]


def _sf_header(b: bytes):
    """(versão, endian, tamanho_cabeçalho, data_offset) se parecer um SerializedFile; senão None."""
    if len(b) < 48:
        return None
    _ms, fs, ver, do = struct.unpack_from(">IIII", b, 0)
    if ver < 9 or ver > 64:
        return None
    hs = 20
    if ver >= 22:
        _ms, fs, do = struct.unpack_from(">IQQ", b, 20)
        hs = 48
    if b[16] not in (0, 1) or fs != len(b) or not hs < do <= fs:
        return None
    return ver, "<" if b[16] == 0 else ">", hs, do


def _read_tree(r: _R, ver: int) -> _Node:
    n, sb = r.i32(), r.i32()
    if not 0 < n < 200000 or not 0 <= sb < 1 << 24:
        raise UnityError("typetree inválido")
    nsz = 32 if ver >= 19 else 24
    raw = r.take(n * nsz)
    strs = r.take(sb)

    def name(off: int) -> str:
        if off & 0x80000000:
            return _COMMON.get(off & 0x7FFFFFFF, f"?{off & 0x7FFFFFFF}")
        j = strs.find(b"\0", off)
        return strs[off:j if j >= 0 else len(strs)].decode("utf-8", "replace")

    root, stack = None, []
    for k in range(n):
        _v, level, flags, to, no, size, _idx, meta = struct.unpack_from(r.e + "HBBIIiii", raw, k * nsz)
        node = _Node(name(to), name(no), size, flags, meta)
        if level > len(stack) or (level == 0 and root is not None):
            raise UnityError("typetree com níveis inválidos")
        del stack[level:]
        if level == 0:
            root = node
        else:
            stack[-1].children.append(node)
        stack.append(node)
    return root


def _read_type(r: _R, ver: int, tt: bool) -> _Type:
    cid = r.i32()
    if ver >= 16:
        r.u8()  # tipo "stripped"
    if ver >= 17:
        r.i16()  # índice do script
    if (ver < 16 and cid < 0) or (ver >= 16 and cid == CLS_MONOBEHAVIOUR):
        r.take(16)  # hash do script
    r.take(16)  # hash do tipo
    tree = None
    if tt:
        tree = _read_tree(r, ver)
        if ver >= 21:
            r.take(4 * r.i32())  # dependências do tipo
    return _Type(cid, tree)


def parse_sf(b: bytes) -> _SF:
    h = _sf_header(b)
    if not h:
        raise UnityError("não é um SerializedFile da Unity")
    ver, e, hs, do = h
    if not SF_MIN <= ver <= SF_MAX:
        raise UnityError(f"SerializedFile versão {ver} (só leio {SF_MIN} a {SF_MAX})")
    r = _R(b, hs, e)
    r.cstr()  # versão da Unity
    r.i32()  # plataforma
    tt = bool(r.u8())
    types = [_read_type(r, ver, tt) for _ in range(r.i32())]
    n = r.i32()
    if not 0 <= n < 10_000_000:
        raise UnityError("número de objetos inválido")
    objs = []
    for _ in range(n):
        r.align(4)
        pid = r.i64()
        fpos = r.p
        start = r.i64() if ver >= 22 else r.u32()
        size = r.u32()
        tid = r.i32()
        if ver < 16:
            cid = r.u16()
            typ = next((t for t in types if t.class_id == tid), None)
        else:
            if not 0 <= tid < len(types):
                raise UnityError("objeto com tipo inexistente")
            typ = types[tid]
            cid = typ.class_id
        if ver < 17:
            r.i16()
        if ver in (15, 16):
            r.u8()
        if do + start + size > len(b):
            raise UnityError("objeto fora do arquivo")
        objs.append(_Obj(pid, start, size, cid, typ, fpos))
    return _SF(b, ver, e, do, tt, objs)


def _sf_rebuild(sf: _SF, new_objs: dict[int, bytes]) -> bytes:
    """Mesmo arquivo com alguns objetos trocados; os seguintes andam junto (alinhados de 8 em 8)."""
    b, do, e = sf.data, sf.data_offset, sf.e
    head = bytearray(b[:do])
    order = sorted(sf.objects, key=lambda o: (o.start, o.path_id))
    body = bytearray()
    delta = 0
    prev_end = 0
    for o in order:
        new_start = o.start + delta
        if new_start < len(body):
            raise UnityError("objetos sobrepostos no SerializedFile")
        gap = b[do + prev_end:do + o.start] if o.start >= prev_end else b""
        fill = new_start - len(body)
        body += gap[:fill] + b"\0" * max(0, fill - len(gap))
        payload = new_objs.get(o.path_id, sf.obj(o))
        body += payload
        old_end = o.start + o.size
        delta = ((len(body) - old_end) + 7) // 8 * 8
        prev_end = max(prev_end, old_end)
        if sf.version >= 22:
            struct.pack_into(e + "qI", head, o.f_start, new_start, len(payload))
        else:
            if new_start >= 1 << 32:
                raise UnityError("SerializedFile ficaria grande demais")
            struct.pack_into(e + "II", head, o.f_start, new_start, len(payload))
    body += b[do + prev_end:]
    total = do + len(body)
    if sf.version >= 22:
        struct.pack_into(">Q", head, 24, total)
        if struct.unpack_from(">I", head, 4)[0] and total < 1 << 32:
            struct.pack_into(">I", head, 4, total)
    else:
        if total >= 1 << 32:
            raise UnityError("SerializedFile ficaria grande demais")
        struct.pack_into(">I", head, 4, total)
    return bytes(head + body)


# ------------------------------------------------------------------ typetree: percorre lendo e regravando
class _Walker:
    def __init__(self, src: bytes, e: str, subs: dict[str, bytes] | None = None):
        self.s, self.i, self.e = src, 0, e
        self.out = bytearray()
        self.subs = subs or {}
        self.strings: list[tuple[str, bytes]] = []

    def _take(self, n: int) -> bytes:
        if n < 0 or self.i + n > len(self.s):
            raise _Pula("typetree não bate com os dados")
        v = self.s[self.i:self.i + n]
        self.i += n
        return v

    def _i32(self) -> int:
        v = struct.unpack(self.e + "i", self._take(4))[0]
        if v < 0 or v > len(self.s):
            raise _Pula("tamanho inválido")
        return v

    def _align(self) -> None:
        self.i += (-self.i) % 4
        self.out += b"\0" * ((-len(self.out)) % 4)

    def walk(self, node: _Node, path: str, depth: int = 0) -> None:
        if depth > 80:
            raise _Pula("typetree fundo demais")
        if node.type in ("ManagedReferencesRegistry", "ReferencedObject", "ReferencedObjectData"):
            raise _Pula("SerializeReference (ainda não leio)")
        align = node.meta & ALIGN_FLAG
        if node.type == "string" and node.children:
            raw = self._take(self._i32())
            self.strings.append((path, raw))
            new = self.subs.get(path, raw)
            self.out += struct.pack(self.e + "i", len(new)) + new
            align |= node.children[0].meta & ALIGN_FLAG
        elif node.type == "TypelessData":
            n = self._i32()
            self.out += struct.pack(self.e + "i", n) + self._take(n)
        elif node.flags & 1 or node.type == "Array":
            if len(node.children) != 2:
                raise _Pula("array estranho no typetree")
            n = self._i32()
            self.out += struct.pack(self.e + "i", n)
            el = node.children[1]
            if not el.children and el.size > 0 and not el.meta & ALIGN_FLAG:
                self.out += self._take(n * el.size)
            else:
                for k in range(n):
                    self.walk(el, f"{path}[{k}]", depth + 1)
        elif not node.children:
            if node.size <= 0:
                raise _Pula(f"campo '{node.type}' sem tamanho")
            self.out += self._take(node.size)
        else:
            for c in node.children:
                cp = path if (c.flags & 1 or c.type == "Array") else (f"{path}.{c.name}" if path else c.name)
                self.walk(c, cp, depth + 1)
        if align:
            self._align()


def _walk(tree: _Node, data: bytes, e: str, subs: dict[str, bytes] | None = None) -> _Walker:
    w = _Walker(data, e, subs)
    w.walk(tree, "")
    if w.i != len(data):
        raise _Pula("typetree não cobre o objeto inteiro")
    if not subs and bytes(w.out) != data:
        raise _Pula("typetree não reproduz o objeto")
    return w


# ------------------------------------------------------------------ TextAsset
def _ta_get(sf: _SF, o: _Obj) -> tuple[str, bytes, str]:
    """(nome, conteúdo de m_Script, como_regravar)."""
    data = sf.obj(o)
    tree = o.type.tree if o.type else None
    if tree is not None:
        try:
            w = _walk(tree, data, sf.e)
            d = dict(w.strings)
            if "m_Script" in d:
                return d.get("m_Name", b"").decode("utf-8", "replace"), d["m_Script"], "tt"
        except _Pula:
            pass
    r = _R(data, 0, sf.e)
    try:
        n = r.i32()
        if not 0 <= n <= 4096:
            raise _Pula("TextAsset com nome estranho")
        name = r.take(n).decode("utf-8", "replace")
        r.align(4)
        m = r.i32()
        if m < 0:
            raise _Pula("TextAsset com tamanho estranho")
        script = r.take(m)
    except UnityError as ex:
        raise _Pula(str(ex)) from None
    return name, script, "fix"


def _ta_set(sf: _SF, o: _Obj, new_script: bytes, how: str) -> bytes:
    data = sf.obj(o)
    if how == "tt":
        return bytes(_walk(o.type.tree, data, sf.e, {"m_Script": new_script}).out)
    r = _R(data, 0, sf.e)
    n = r.i32()
    r.take(n)
    r.align(4)
    lpos = r.p
    m = r.i32()
    r.take(m)
    r.p = min(len(data), _al(r.p, 4))
    tail = data[r.p:]
    body = data[:lpos] + struct.pack(sf.e + "i", len(new_script)) + new_script
    return body + b"\0" * ((-len(body)) % 4) + tail


def _decode(raw: bytes):
    """(texto, codificação, BOM) se for texto; senão None."""
    if not raw:
        return None
    if raw.startswith(b"\xef\xbb\xbf"):
        enc, bom = "utf-8", raw[:3]
    elif raw[:2] == b"\xff\xfe":
        enc, bom = "utf-16-le", raw[:2]
    elif raw[:2] == b"\xfe\xff":
        enc, bom = "utf-16-be", raw[:2]
    else:
        bom = b""
        enc = "utf-8"
        if len(raw) >= 4 and len(raw) % 2 == 0 and raw.count(0) >= len(raw) // 4:
            enc = "utf-16-le" if raw[1::2].count(0) > raw[0::2].count(0) else "utf-16-be"
    try:
        t = raw[len(bom):].decode(enc)
    except UnicodeDecodeError:
        return None
    if not t.strip():
        return None
    bad = sum(1 for c in t if (ord(c) < 32 and c not in "\t\r\n") or c == "�")
    if bad > len(t) // 100:
        return None
    return t, enc, bom


# ------------------------------------------------------------------ frases dentro do texto
_LETTERS = re.compile(r"[^\W\d_]{2,}")
_EN_COLS = {"en", "eng", "english", "en-us", "en_us", "en-gb", "en_gb", "text_en", "en_text"}
_YARN_CODES = re.compile(r"<<[^>]*>>|<[^>]*>|\{[^}]*\}|\[[^\]]*\]|%[-+0-9.]*[sdif]|\r?\n")
_LINE = re.compile(r"(?m)^[^\r\n]*")
_INI_KV = re.compile(r"^\s*[\w.\-\[\]]+\s*=\s*(.*?)\s*$")
_INI_SEC = re.compile(r"^\s*\[[^\]]+\]\s*$")


@dataclass
class _Seg:
    n: int       # posição (estável): ordem do texto, ou linha da tabela no CSV
    a: int       # início/fim no texto decodificado (o que é trocado)
    b: int
    text: str    # frase "limpa" (sem aspas/escapes)
    kind: str    # como escapar ao regravar: line, csv, csvq, json, xml, cdata
    want: bool   # vai para a tradução?


def _letters(s: str) -> bool:
    return bool(_LETTERS.search(s))


def _csv_rows(t: str, d: str):
    """Linhas do CSV: [[(início, fim, texto, entre_aspas)]]."""
    rows, row, i, n = [], [], 0, len(t)
    if t.startswith("﻿"):
        i = 1
    while True:
        if i >= n and not row:
            break
        if i < n and t[i] == '"':
            j, buf = i + 1, []
            while j < n:
                if t[j] == '"':
                    if j + 1 < n and t[j + 1] == '"':
                        buf.append('"')
                        j += 2
                        continue
                    break
                buf.append(t[j])
                j += 1
            end = min(j + 1, n)
            k = end
            while k < n and t[k] not in (d, "\r", "\n"):
                k += 1
            row.append((i, end, "".join(buf), True))
        else:
            k = i
            while k < n and t[k] not in (d, "\r", "\n"):
                k += 1
            row.append((i, k, t[i:k], False))
        if k < n and t[k] == d:
            i = k + 1
            continue
        rows.append(row)
        row = []
        if k >= n:
            break
        i = k + 2 if t.startswith("\r\n", k) else k + 1
    return rows


def _detect_fmt(t: str):
    """(formato, parâmetros) ou (None, motivo)."""
    s = t.lstrip("﻿ \t\r\n")
    if s[:1] in ("{", "["):
        try:
            json.loads(s)
            return "json", {}
        except ValueError:
            if s[:1] == "{":
                return None, "parece JSON mas não abre"
    if s[:1] == "<":
        return "xml", {}
    first = s.split("\n", 1)[0]
    d = next((c for c in ("\t", ",", ";") if c in first), None)
    if d:
        rows = _csv_rows(t, d)
        if rows:
            hdr = [f[2].strip().lower() for f in rows[0]]
            col = next((k for k, h in enumerate(hdr) if h in _EN_COLS or h.startswith("english")), None)
            if col is not None and len(rows) > 1:
                return "csv", {"d": d, "col": col}
            sample = [r for r in rows[1:6] if len(r) > 1]
            if len(hdr) >= 2 and sample and all(len(r) == len(hdr) for r in sample):
                return None, f"tabela sem coluna de inglês (colunas: {', '.join(hdr[:6])})"
    if re.search(r"(?m)^title:", t) and re.search(r"(?m)^---\s*$", t) and re.search(r"(?m)^===\s*$", t):
        return "yarn", {}
    if re.search(r"(?m)^\s*={2,}\s*\w", t) and "->" in t:
        return "ink", {}
    lines = [ln for ln in t.splitlines() if ln.strip() and not ln.lstrip().startswith((";", "#", "//"))]
    kv = sum(1 for ln in lines if _INI_KV.match(ln) or _INI_SEC.match(ln))
    if lines and kv >= max(2, 0.8 * len(lines)):
        return "ini", {}
    return "txt", {}


def _strip_span(t: str, a: int, b: int):
    raw = t[a:b]
    lead = len(raw) - len(raw.lstrip())
    s = raw.strip()
    return a + lead, a + lead + len(s), s


def _segments(fmt: str, t: str, p: dict) -> list[_Seg]:
    out: list[_Seg] = []
    if fmt == "csv":
        for n, row in enumerate(_csv_rows(t, p["d"])):
            if n == 0 or p["col"] >= len(row):
                continue
            a, b, txt, q = row[p["col"]]
            out.append(_Seg(n, a, b, txt, "csvq" if q else "csv", _letters(txt)))
    elif fmt == "json":
        i, n = 0, len(t)
        while i < n:
            if t[i] != '"':
                i += 1
                continue
            j = i + 1
            while j < n and t[j] != '"':
                j += 2 if t[j] == "\\" else 1
            k = j + 1
            while k < n and t[k] in " \t\r\n":
                k += 1
            if not (k < n and t[k] == ":"):
                a, raw = i + 1, t[i + 1:j]
                ink = raw.startswith("^")
                if ink:
                    a, raw = a + 1, raw[1:]
                try:
                    txt = json.loads('"' + raw + '"')
                except ValueError:
                    txt = None
                if txt is not None:
                    want = _letters(txt) and (ink or " " in txt.strip())
                    out.append(_Seg(len(out), a, j, txt, "json", want))
            i = j + 1
    elif fmt == "xml":
        pos = 0

        def text_node(a, b):
            a, b, s = _strip_span(t, a, b)
            if s:
                txt = html.unescape(s)
                out.append(_Seg(len(out), a, b, txt, "xml", _letters(txt)))

        for m in re.finditer(r"<!--.*?-->|<!\[CDATA\[(.*?)\]\]>|<[^>]*>", t, re.DOTALL):
            text_node(pos, m.start())
            if m.group(1) is not None:
                a, b, s = _strip_span(t, m.start(1), m.end(1))
                if s:
                    out.append(_Seg(len(out), a, b, s, "cdata", _letters(s)))
            pos = m.end()
        text_node(pos, len(t))
    else:
        body = fmt != "yarn"
        for m in _LINE.finditer(t):
            line = m.group(0)
            a0 = m.start()
            st = line.strip()
            if fmt == "yarn":
                if st == "---":
                    body = True
                    continue
                if st == "===":
                    body = False
                    continue
                if not body or not st or st.startswith(("//", "<<")) and st.endswith(">>"):
                    continue
                if st.startswith("//"):
                    continue
                m2 = re.match(r"\s*(?:->\s*)?(?:[\w]+(?: [\w]+)?:\s+)?", line)
                a = a0 + m2.end()
                tag = re.search(r"(\s+#[^\s#]+)+\s*$", line)
                b = a0 + (tag.start() if tag and tag.start() >= m2.end() else len(line))
                a, b, s = _strip_span(t, a, b)
                if s:
                    out.append(_Seg(len(out), a, b, s, "line", _letters(s)))
            elif fmt == "ink":
                if not st or st.startswith(("==", "~", "VAR ", "CONST ", "INCLUDE ", "//", "LIST ", "EXTERNAL ",
                                            "->", "#")):
                    continue
                m2 = re.match(r"\s*(?:[*+\-]\s*)*", line)
                end = len(line)
                for sep in ("->", " #", "//"):
                    k = line.find(sep, m2.end())
                    if k >= 0:
                        end = min(end, k)
                a, b, s = _strip_span(t, a0 + m2.end(), a0 + end)
                if s:
                    out.append(_Seg(len(out), a, b, s, "line", _letters(s)))
            elif fmt == "ini":
                if _INI_SEC.match(line) or st.startswith((";", "#", "//")):
                    continue
                m2 = _INI_KV.match(line)
                if m2 and m2.group(1):
                    a, b, s = _strip_span(t, a0 + m2.start(1), a0 + m2.end(1))
                    out.append(_Seg(len(out), a, b, s, "line", _letters(s)))
            else:  # txt
                if not st:
                    continue
                a, b, s = _strip_span(t, a0, a0 + len(line))
                codey = sum(1 for c in s if c in "{}();=<>[]$") > len(s) * 0.08
                out.append(_Seg(len(out), a, b, s, "line", _letters(s) and " " in s and not codey))
    return out


def _norm(kind: str, new: str) -> str:
    """Como a frase nova fica depois de gravada e relida."""
    if kind == "line":
        return re.sub(r"\r\n|\r|\n", " ", new).strip()
    if kind == "xml":
        return new.strip()
    if kind == "cdata":
        return new.replace("]]>", "]] >").strip()
    return new


def _esc(kind: str, new: str, p: dict) -> str:
    if kind == "json":
        return json.dumps(new, ensure_ascii=False)[1:-1]
    if kind == "xml":
        return _xml_escape(new)
    if kind == "csvq" or (kind == "csv" and any(c in new for c in (p.get("d", ","), '"', "\n", "\r"))):
        return '"' + new.replace('"', '""') + '"'
    return new


# ------------------------------------------------------------------ MonoBehaviour com typetree
_I2_TERM = re.compile(r"^(?:mSource\.)?mTerms\[(\d+)\]\.Languages\[(\d+)\]$")
_I2_LANG = re.compile(r"^(?:mSource\.)?mLanguages\[(\d+)\]\.(Name|Code)$")
_SKIP_FIELDS = {"m_Name", "m_EditorClassIdentifier"}


def _mono_strings(w: _Walker) -> tuple[dict[str, str], list[str], str]:
    """({caminho: texto}, caminhos para traduzir, observação)."""
    dec: dict[str, str] = {}
    for p, raw in w.strings:
        try:
            dec[p] = raw.decode("utf-8")
        except UnicodeDecodeError:
            pass
    terms = {p: m for p in dec if (m := _I2_TERM.match(p))}
    if terms:
        langs: dict[int, dict[str, str]] = {}
        for p, s in dec.items():
            m = _I2_LANG.match(p)
            if m:
                langs.setdefault(int(m.group(1)), {})[m.group(2)] = s
        en, nota = None, ""
        for k in sorted(langs):
            nm, cd = langs[k].get("Name", "").lower(), langs[k].get("Code", "").lower()
            if nm.startswith("english") or cd in ("en", "en-us", "en-gb"):
                en = k
                break
        if en is None:
            en, nota = 0, "I2 Localization sem idioma inglês declarado: usei o primeiro idioma"
        want = [p for p, m in terms.items() if int(m.group(2)) == en and _letters(dec[p])]
        return dec, want, nota
    want = [p for p, s in dec.items()
            if re.sub(r"\[\d+\]", "", p).rsplit(".", 1)[-1] not in _SKIP_FIELDS and " " in s.strip() and _letters(s)]
    return dec, want, ""


def _mono_name_fixed(sf: _SF, o: _Obj) -> str:
    """m_Name de um MonoBehaviour sem typetree (PPtr 12 + m_Enabled 4 + PPtr 12 = 28 bytes antes)."""
    d = sf.obj(o)
    if len(d) < 32:
        return ""
    n = struct.unpack_from(sf.e + "i", d, 28)[0]
    if not 0 < n < 512 or 32 + n > len(d):
        return ""
    return d[32:32 + n].decode("utf-8", "replace")


# ------------------------------------------------------------------ UnityFS
def _lzma_unity(src: bytes, size: int) -> bytes:
    if len(src) < 5:
        raise UnityError("bloco LZMA curto demais")
    d = src[0]
    lc, d = d % 9, d // 9
    lp, pb = d % 5, d // 5
    dict_size = max(4096, int.from_bytes(src[1:5], "little"))
    dec = lzma.LZMADecompressor(lzma.FORMAT_RAW, filters=[
        {"id": lzma.FILTER_LZMA1, "dict_size": dict_size, "lc": lc, "lp": lp, "pb": pb}])
    out = dec.decompress(src[5:], max_length=size)
    if len(out) != size:
        raise UnityError(f"LZMA deu {len(out)} bytes, esperado {size}")
    return out


def _decompress(method: int, src: bytes, size: int) -> bytes:
    if method == 0:
        if len(src) != size:
            raise UnityError("bloco sem compressão com tamanho errado")
        return src
    if method == 1:
        return _lzma_unity(src, size)
    if method in (2, 3):
        try:
            return lz4blk.decompress(src, size)
        except lz4blk.Lz4Error as ex:
            raise UnityError(str(ex)) from None
    raise UnityError(f"compressão {method} desconhecida no bundle")


@dataclass
class _Bundle:
    raw: bytes
    fmt: int
    uver: str
    urev: str
    flags: int
    hash: bytes
    blocks: list      # [(tamanho_real, tamanho_gravado, flags, posição_no_arquivo, posição_no_fluxo)]
    nodes: list       # [(offset, tamanho, flags, caminho)]
    pad_header: bool
    _cache: dict = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(b[0] for b in self.blocks)

    def read(self, a: int, n: int) -> bytes:
        out = bytearray()
        for k, (us, cs, fl, fo, so) in enumerate(self.blocks):
            if so + us <= a or so >= a + n:
                continue
            if k not in self._cache:
                self._cache[k] = _decompress(fl & 0x3F, self.raw[fo:fo + cs], us)
            blk = self._cache[k]
            out += blk[max(0, a - so):min(us, a + n - so)]
        if len(out) != n:
            raise UnityError("nó do bundle fora dos dados")
        return bytes(out)

    def node_bytes(self, node) -> bytes:
        return self.read(node[0], node[1])


def parse_bundle(raw: bytes) -> _Bundle:
    r = _R(raw, 0, ">")
    if r.cstr(16) != "UnityFS":
        raise UnityError("não é um bundle UnityFS")
    fmt = r.u32()
    if not 6 <= fmt <= 8:
        raise UnityError(f"bundle UnityFS formato {fmt} (só leio 6 a 8)")
    uver, urev = r.cstr(), r.cstr()
    _size, cbi, ubi, flags = r.i64(), r.u32(), r.u32(), r.u32()
    hdr_end = r.p
    at_end = flags & 0x80
    cands = [_al(hdr_end)] if fmt >= 7 else [hdr_end, _al(hdr_end)]
    err = "índice ilegível"
    for start in dict.fromkeys(cands):
        try:
            bi_pos = len(raw) - cbi if at_end else start
            if bi_pos < hdr_end:
                raise UnityError("índice fora do arquivo")
            bi = _decompress(flags & 0x3F, raw[bi_pos:bi_pos + cbi], ubi)
            q = _R(bi, 0, ">")
            h = q.take(16)
            nb = q.i32()
            if not 0 <= nb < 1 << 22:
                raise UnityError("número de blocos inválido")
            data_start = start if at_end else start + cbi
            if flags & 0x200:
                data_start = _al(data_start)
            blocks, fo, so = [], data_start, 0
            for _ in range(nb):
                us, cs, fl = q.u32(), q.u32(), q.u16()
                blocks.append((us, cs, fl, fo, so))
                fo += cs
                so += us
            if fo > (bi_pos if at_end else len(raw)):
                raise UnityError("blocos passam do fim do arquivo")
            nn = q.i32()
            if not 0 <= nn < 1 << 20:
                raise UnityError("número de nós inválido")
            nodes = []
            for _ in range(nn):
                off, sz, nf = q.i64(), q.i64(), q.u32()
                path = q.cstr()
                if off < 0 or sz < 0 or off + sz > so:
                    raise UnityError("nó fora dos dados")
                nodes.append((off, sz, nf, path))
            return _Bundle(raw, fmt, uver, urev, flags, h, blocks, nodes, start != hdr_end)
        except (UnityError, lzma.LZMAError, struct.error) as ex:
            err = str(ex)
    raise UnityError(f"bundle UnityFS: {err}")


def write_bundle(b: _Bundle, stream: bytes, nodes: list) -> bytes:
    """Bundle UnityFS sem compressão (índice e blocos), mesma versão/assinatura do original."""
    bfl = (b.blocks[0][2] & ~0x3F) if b.blocks else 0
    sizes = [min(BUNDLE_CHUNK, len(stream) - k) for k in range(0, len(stream), BUNDLE_CHUNK)]
    bi = bytearray(b.hash + struct.pack(">i", len(sizes)))
    for s in sizes:
        bi += struct.pack(">IIH", s, s, bfl)
    bi += struct.pack(">i", len(nodes))
    for off, sz, nf, path in nodes:
        bi += struct.pack(">qqI", off, sz, nf) + path.encode("utf-8") + b"\0"
    flags = b.flags & ~0x3F
    out = bytearray(b"UnityFS\0" + struct.pack(">I", b.fmt) + b.uver.encode() + b"\0" + b.urev.encode() + b"\0")
    size_pos = len(out)
    out += struct.pack(">qIII", 0, len(bi), len(bi), flags)
    if b.pad_header:
        out += b"\0" * ((-len(out)) % 16)
    if flags & 0x80:
        if flags & 0x200:
            out += b"\0" * ((-len(out)) % 16)
        out += stream
        out += bi
    else:
        out += bi
        if flags & 0x200:
            out += b"\0" * ((-len(out)) % 16)
        out += stream
    struct.pack_into(">q", out, size_pos, len(out))
    return bytes(out)


def _bundle_rebuild(b: _Bundle, new_nodes: dict[str, bytes]) -> bytes:
    stream = bytearray()
    placed: dict[str, tuple[int, int]] = {}
    prev_end = 0
    for off, sz, _nf, path in sorted(b.nodes, key=lambda n: (n[0], n[3])):
        if off > prev_end:
            stream += b.read(prev_end, off - prev_end)
        content = new_nodes.get(path)
        if content is None:
            content = b.read(off, sz)
        placed[path] = (len(stream), len(content))
        stream += content
        prev_end = max(prev_end, off + sz)
    if b.total > prev_end:
        stream += b.read(prev_end, b.total - prev_end)
    nodes = [(placed[p][0], placed[p][1], nf, p) for _o, _s, nf, p in b.nodes]
    return write_bundle(b, bytes(stream), nodes)


# ------------------------------------------------------------------ detecção e coleta
def _norm_path(p: str) -> str:
    return p.replace("\\", "/").lstrip("/")


def detect(paths: list[str]) -> bool:
    for p in paths:
        q = _norm_path(p).lower()
        base = q.rsplit("/", 1)[-1]
        if (("/" + q).endswith("/data/globalgamemanagers") or base == "data.unity3d"
                or "data/streamingassets/" in q or re.fullmatch(r"sharedassets\d+\.assets", base)
                or base == "resources.assets" or base.endswith(".bundle")):
            return True
    return False


def _candidates(paths) -> list[str]:
    out = []
    for p in paths:
        q = _norm_path(p).lower()
        base = q.rsplit("/", 1)[-1]
        if base.endswith((".ress", ".resource")):
            continue
        if (base in ("globalgamemanagers", "globalgamemanagers.assets", "resources.assets", "data.unity3d")
                or base.endswith((".assets", ".bundle", ".unity3d", ".ab", ".assetbundle"))
                or re.fullmatch(r"level\d+", base)
                or ("streamingassets/" in q and "." not in base)):
            out.append(p)
    return sorted(out)


@dataclass
class _Plan:
    kind: str                          # "ta" (TextAsset) ou "mb" (MonoBehaviour)
    fmt: str = ""                      # formato do TextAsset
    params: dict = field(default_factory=dict)


@dataclass
class _Estado:
    read: Callable[[str], bytes]
    textos: list = field(default_factory=list)
    ids: dict = field(default_factory=dict)       # id -> (arquivo, path_id, posição)
    plans: dict = field(default_factory=dict)     # (arquivo, path_id) -> _Plan
    files: dict = field(default_factory=dict)     # arquivo -> (caminho no RomFS, nome do nó no bundle ou None)
    sem_tt: int = 0
    fontes: list = field(default_factory=list)
    estudo: list = field(default_factory=list)
    pulados: list = field(default_factory=list)
    notas: list = field(default_factory=list)
    bundles: int = 0
    lidos: int = 0


def _scan_sf(st: _Estado, path: str, node: str | None, data: bytes) -> None:
    try:
        sf = parse_sf(data)
    except UnityError as ex:
        st.pulados.append(f"{path}{':' + node if node else ''}: {ex}")
        return
    st.lidos += 1
    fkey = f"{path}:{node}" if node else path
    st.files[fkey] = (path, node)
    for o in sf.objects:
        if o.class_id == CLS_TEXTASSET:
            try:
                name, script, _how = _ta_get(sf, o)
            except _Pula as ex:
                st.pulados.append(f"{fkey} TextAsset {o.path_id}: {ex}")
                continue
            dec = _decode(script)
            if not dec:
                continue  # binário (imagem, bytes de jogo...)
            fmt, params = _detect_fmt(dec[0])
            if fmt is None:
                st.estudo.append(f"{name or o.path_id} ({params})")
                continue
            segs = _segments(fmt, dec[0], params)
            codes = _YARN_CODES if fmt == "yarn" else None
            got = False
            for s in segs:
                if s.want:
                    tid = f"{fkey}|{o.path_id}|{s.n}"
                    st.textos.append(Texto(tid, s.text, codes))
                    st.ids[tid] = (fkey, o.path_id, s.n)
                    got = True
            if got:
                st.plans[(fkey, o.path_id)] = _Plan("ta", fmt, params)
        elif o.class_id == CLS_MONOBEHAVIOUR:
            tree = o.type.tree if o.type else None
            if tree is None:
                st.sem_tt += 1
                name = _mono_name_fixed(sf, o)
                if "SDF" in name:
                    st.fontes.append(name)
                continue
            try:
                w = _walk(tree, sf.obj(o), sf.e)
            except _Pula as ex:
                st.pulados.append(f"{fkey} MonoBehaviour {o.path_id}: {ex}")
                continue
            dec, want, nota = _mono_strings(w)
            if "SDF" in dec.get("m_Name", ""):
                st.fontes.append(dec["m_Name"])
                continue
            if nota:
                st.notas.append(nota)
            for p in want:
                tid = f"{fkey}|{o.path_id}|{p}"
                st.textos.append(Texto(tid, dec[p]))
                st.ids[tid] = (fkey, o.path_id, p)
            if want:
                st.plans[(fkey, o.path_id)] = _Plan("mb")


def _scan_bundle(st: _Estado, path: str, raw: bytes) -> None:
    try:
        b = parse_bundle(raw)
    except UnityError as ex:
        st.pulados.append(f"{path}: {ex}")
        return
    st.bundles += 1
    for node in b.nodes:
        name = node[3]
        if name.lower().endswith((".ress", ".resource")) or node[1] < 48:
            continue
        try:
            head = b.read(node[0], 48)
            if not _sf_like(head, node[1]):
                continue
            data = b.node_bytes(node)
        except UnityError as ex:
            st.pulados.append(f"{path}:{name}: {ex}")
            continue
        _scan_sf(st, path, name, data)


def _sf_like(head: bytes, size: int) -> bool:
    """Cabeçalho de SerializedFile olhando só os primeiros 48 bytes (o tamanho vem do nó)."""
    _ms, fs, ver, do = struct.unpack_from(">IIII", head, 0)
    if ver >= 22:
        _ms, fs, do = struct.unpack_from(">IQQ", head, 20)
    return 9 <= ver <= 64 and head[16] in (0, 1) and fs == size and 0 < do <= size


# ------------------------------------------------------------------ regravação com conferência
def _patch_obj(sf: _SF, o: _Obj, plan: _Plan, subs: dict):
    """(bytes novos do objeto, o que a releitura tem que dar)."""
    if plan.kind == "ta":
        _name, script, how = _ta_get(sf, o)
        dec = _decode(script)
        if not dec:
            raise MotorError(f"TextAsset {o.path_id} mudou desde a coleta")
        text, enc, bom = dec
        segs = {s.n: s for s in _segments(plan.fmt, text, plan.params)}
        expected = {n: s.text for n, s in segs.items()}
        edits = []
        for n, new in subs.items():
            s = segs.get(n)
            if s is None:
                raise MotorError(f"TextAsset {o.path_id}: frase {n} sumiu desde a coleta")
            v = _norm(s.kind, new)
            expected[n] = v
            edits.append((s, v))
        for s, v in sorted(edits, key=lambda x: -x[0].a):
            text = text[:s.a] + _esc(s.kind, v, plan.params) + text[s.b:]
        return _ta_set(sf, o, bom + text.encode(enc), how), (enc, expected)
    w = _walk(o.type.tree, sf.obj(o), sf.e)
    orig = dict(w.strings)
    enc_subs = {}
    for p, new in subs.items():
        if p not in orig:
            raise MotorError(f"MonoBehaviour {o.path_id}: campo {p} sumiu desde a coleta")
        enc_subs[p] = new.encode("utf-8")
    new_obj = bytes(_walk(o.type.tree, sf.obj(o), sf.e, enc_subs).out)
    expected = [(p, enc_subs.get(p, raw)) for p, raw in w.strings]
    return new_obj, expected


def _check_obj(sf: _SF, o: _Obj, plan: _Plan, expected) -> None:
    try:
        if plan.kind == "ta":
            enc, exp = expected
            _n, script, _how = _ta_get(sf, o)
            dec = _decode(script)
            if not dec or dec[1] != enc:
                raise MotorError("codificação mudou")
            got = {s.n: s.text for s in _segments(plan.fmt, dec[0], plan.params)}
            if got != exp:
                bad = next((n for n in exp if got.get(n) != exp[n]), None)
                raise MotorError(f"frase {bad} não confere")
        else:
            w = _walk(o.type.tree, sf.obj(o), sf.e)
            if w.strings != expected:
                raise MotorError("textos do MonoBehaviour não conferem")
    except _Pula as ex:
        raise MotorError(f"objeto {o.path_id} ilegível depois de regravar: {ex}") from None
    except MotorError as ex:
        raise MotorError(f"Unity: objeto {o.path_id} não conferiu na releitura ({ex})") from None


def _patch_sf(st: _Estado, fkey: str, data: bytes, subs_by_obj: dict) -> bytes:
    sf = parse_sf(data)
    by_pid = {o.path_id: o for o in sf.objects}
    new_objs, expect = {}, {}
    for pid, subs in subs_by_obj.items():
        o = by_pid.get(pid)
        if o is None:
            raise MotorError(f"{fkey}: objeto {pid} sumiu desde a coleta")
        try:
            new_objs[pid], expect[pid] = _patch_obj(sf, o, st.plans[(fkey, pid)], subs)
        except _Pula as ex:
            raise MotorError(f"{fkey}: objeto {pid}: {ex}") from None
    if all(new_objs[p] == sf.obj(by_pid[p]) for p in new_objs):
        return data
    out = _sf_rebuild(sf, new_objs)
    # releitura: tabela igual, objetos não tocados idênticos byte a byte, os tocados com as frases novas
    try:
        sf2 = parse_sf(out)
    except UnityError as ex:
        raise MotorError(f"{fkey}: SerializedFile regravado não abre ({ex})") from None
    if [(o.path_id, o.class_id) for o in sf2.objects] != [(o.path_id, o.class_id) for o in sf.objects]:
        raise MotorError(f"{fkey}: tabela de objetos mudou na regravação")
    for o_old, o_new in zip(sf.objects, sf2.objects):
        if o_new.start % 8 != o_old.start % 8:
            raise MotorError(f"{fkey}: alinhamento do objeto {o_new.path_id} mudou")
        want = new_objs.get(o_old.path_id, sf.obj(o_old))
        if sf2.obj(o_new) != want:
            raise MotorError(f"{fkey}: objeto {o_new.path_id} não confere na releitura")
        if o_old.path_id in new_objs:
            _check_obj(sf2, o_new, st.plans[(fkey, o_old.path_id)], expect[o_old.path_id])
    return out


def _rebuild(st: _Estado, trans: dict[str, str]) -> dict[str, bytes]:
    work: dict[str, dict] = {}
    for tid, new in trans.items():
        if tid not in st.ids or new is None:
            continue
        fkey, pid, n = st.ids[tid]
        work.setdefault(fkey, {}).setdefault(pid, {})[n] = new
    by_path: dict[str, list[str]] = {}
    for fkey in work:
        by_path.setdefault(st.files[fkey][0], []).append(fkey)
    out: dict[str, bytes] = {}
    for path, fkeys in sorted(by_path.items()):
        raw = st.read(path)
        if raw[:8] == b"UnityFS\0":
            b = parse_bundle(raw)
            nodes = {n[3]: n for n in b.nodes}
            new_nodes = {}
            for fkey in fkeys:
                node = st.files[fkey][1]
                if node not in nodes:
                    raise MotorError(f"{path}: nó {node} sumiu desde a coleta")
                data = b.node_bytes(nodes[node])
                new = _patch_sf(st, fkey, data, work[fkey])
                if new != data:
                    new_nodes[node] = new
            if not new_nodes:
                continue
            new_raw = _bundle_rebuild(b, new_nodes)
            try:
                b2 = parse_bundle(new_raw)
            except UnityError as ex:
                raise MotorError(f"{path}: bundle regravado não abre ({ex})") from None
            if [n[3] for n in b2.nodes] != [n[3] for n in b.nodes] or b2.flags & 0x3F or b2.fmt != b.fmt:
                raise MotorError(f"{path}: bundle regravado com índice diferente")
            for n_old, n_new in zip(b.nodes, b2.nodes):
                want = new_nodes.get(n_old[3])
                if want is None:
                    want = b.node_bytes(n_old)
                if b2.node_bytes(n_new) != want or n_new[2] != n_old[2]:
                    raise MotorError(f"{path}: nó {n_old[3]} não confere na releitura do bundle")
            out[path] = new_raw
        else:
            new = _patch_sf(st, path, raw, work[path])
            if new != raw:
                out[path] = new
    return out


def collect(files: dict[str, tuple[int, int]], read: Callable[[str], bytes]) -> Coleta:
    st = _Estado(read)
    antigos = []
    for p in _candidates(files):
        try:
            raw = read(p)
        except Exception as ex:  # noqa: BLE001 - um arquivo ruim não derruba a coleta
            st.pulados.append(f"{p}: não consegui ler ({ex})")
            continue
        if raw[:8] == b"UnityFS\0":
            _scan_bundle(st, p, raw)
        elif raw[:8] in (b"UnityWeb", b"UnityRaw", b"UnityArc"):
            antigos.append(p)
        elif _sf_header(raw):
            _scan_sf(st, p, None, raw)
        del raw

    avisos = []
    if not st.textos:
        motivo = []
        if st.sem_tt:
            motivo.append(f"{st.sem_tt} MonoBehaviour sem typetree (o formato depende dos scripts do jogo)")
        if st.estudo:
            motivo.append("TextAsset em formato que não reconheço: " + "; ".join(st.estudo[:5]))
        if antigos:
            motivo.append(f"{len(antigos)} bundle(s) em formato antigo (UnityWeb/UnityRaw)")
        avisos.append("Não achei frases em formato que eu entenda: o texto deste jogo está num formato que precisa "
                      "de estudo" + (" (" + "; ".join(motivo) + ")." if motivo else
                                     " (pode estar em MonoBehaviour sem typetree, dentro do executável ou em "
                                     "arquivo próprio do jogo)."))
    else:
        if st.sem_tt:
            avisos.append(f"{st.sem_tt} MonoBehaviour sem typetree não foram lidos: se parte do texto estiver "
                          "neles, fica em inglês.")
        if st.estudo:
            avisos.append("TextAsset que não reconheço (ficam em inglês): " + "; ".join(st.estudo[:5]) + ".")
    if st.fontes:
        nomes = ", ".join(sorted(set(st.fontes))[:4])
        avisos.append(f"Fonte TextMeshPro (SDF: {nomes}) pode não ter ã, õ, ç, é...: se aparecerem quadrados no "
                      "lugar das letras, a fonte do jogo precisa ser refeita (ainda não faço isso).")
    if st.bundles and st.textos:
        avisos.append("Bundles alterados são regravados sem compressão (ficam maiores). Se o jogo confere o CRC dos "
                      "bundles (Addressables), o bundle traduzido pode ser recusado.")
    for nota in dict.fromkeys(st.notas):
        avisos.append(nota + ".")
    return Coleta(st.textos, lambda trans: _rebuild(st, trans), " ".join(avisos),
                  {"serialized_files": st.lidos, "bundles": st.bundles, "sem_typetree": st.sem_tt,
                   "pulados": st.pulados[:50], "fontes_tmp": sorted(set(st.fontes))})
