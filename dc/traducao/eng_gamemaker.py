"""GameMaker (Studio 1/2): frases do data.win (game.droid/game.unx/game.ios) e arquivos de idioma ao lado.

Formato do data.win (documentado pela comunidade no UndertaleModTool):
- arquivo IFF: "FORM" + u32 tamanho + chunks em sequência ("GEN8", "STRG", "CODE", ..., normalmente "AUDO" no fim),
  cada chunk = nome(4) + u32 tamanho + dados; tudo little-endian;
- STRG: u32 quantidade + quantidade × u32 ponteiros ABSOLUTOS (a partir do início do arquivo). Cada ponteiro aponta
  para uma entrada "u32 tamanho em bytes + texto UTF-8 + \\0".

Por que dá para traduzir sem recompilar nada: o bytecode (chunk CODE) empurra uma constante de texto pelo ÍNDICE
dela na tabela STRG ("push.s índice"). Então basta gravar a frase nova no FIM do arquivo e trocar só o ponteiro
daquela entrada da tabela. O tamanho do ÚLTIMO chunk e do FORM crescem juntos (o runtime anda pelos chunks pelo
tamanho; bytes extras no fim do último chunk são ignorados por ele). Outros chunks que citam o texto por ponteiro
direto (nomes de objetos, salas, fontes...) continuam apontando para o texto antigo, que fica intacto onde estava.

Só trocamos o que parece FRASE (tem espaço e letras). Identificadores (snake_case, caminhos, nomes de
sprite/sala/objeto, código de shader) ficam como estão: o jogo compara alguns desses textos e quebraria.

YYC (GameMaker compilado para C++): o chunk CODE vem vazio e as frases do código viram parte do executável nativo
(main/NSO), fora do data.win. Aí só dá para traduzir o que estiver em arquivos de idioma ao lado.

Este arquivo também tem os leitores de ARQUIVO DE TEXTO (json/csv/txt/ini/lua/xml) usados aqui e pelo eng_cri:
eles marcam a posição exata de cada frase no arquivo e trocam só aquele pedaço, sem reformatar o resto.
"""
from __future__ import annotations

import html
import json
import re
import struct
from dataclasses import dataclass, field

from .motores import CODES_PADRAO, Coleta, MotorError, Texto

NAME = "GameMaker"

DATA_NOMES = ("data.win", "game.win", "game.droid", "game.unx", "game.ios")

# '#' é a quebra de linha do draw_text no GameMaker Studio 1; a IA não pode apagar nem traduzir.
CODES_GM = re.compile(CODES_PADRAO.pattern + r"|#")

MAX_TEXTO = 16 << 20  # arquivo de idioma maior que isso não é arquivo de idioma


def _base(p: str) -> str:
    return p.replace("\\", "/").rsplit("/", 1)[-1].lower()


def detect(paths: list[str]) -> bool:
    return any(_base(p) in DATA_NOMES for p in paths)


# ================================================================== o que é "frase"
_LET = re.compile(r"[^\W\d_]{2,}")
_SHADER = ("void main", "gl_", "uniform ", "#define", "precision ", "attribute ", "varying ", "texture2D")


def eh_frase(s: str, codes: re.Pattern = CODES_PADRAO) -> bool:
    """Frase de verdade (vale traduzir) e não identificador/código.

    Regra: tem espaço, tem palavra com letras, a maior parte é letra e a maioria das palavras não tem cara de
    identificador (snake_case, camelCase, chamada de função). Erra para o lado de NÃO coletar.
    """
    t = s.strip()
    if len(t) < 3 or not re.search(r"\s", t):
        return False
    limpo = codes.sub(" ", t)
    if not _LET.search(limpo):
        return False
    if any(k in t for k in _SHADER) or re.fullmatch(r"[\w.]+\(.*\)\s*;?", t, re.DOTALL):
        return False  # código de shader ou chamada de função
    vis = re.sub(r"\s+", "", limpo)
    if not vis or sum(c.isalpha() for c in vis) / len(vis) < 0.5:
        return False
    palavras = limpo.split()
    idlike = sum(1 for w in palavras
                 if "_" in w or re.search(r"[a-z][A-Z]", w) or re.search(r"\w\(", w) or "/" in w or "\\" in w)
    return idlike * 2 < len(palavras)


# ================================================================== arquivos de texto (compartilhado com eng_cri)
@dataclass
class Item:
    id: str        # id local, ESTÁVEL: posição entre todos os candidatos (frase ou não), ex.: "l12", "v3", "r2c1"
    ini: int       # trecho [ini, fim) no texto decodificado que será substituído
    fim: int
    texto: str     # valor já "desescapado" (o que a IA vê)
    modo: str      # linha | kv | json | lua" | lua' | xml | csv
    aspas: bool = False   # csv: célula original vinha entre aspas


@dataclass
class ArqTexto:
    nome: str
    enc: str
    bom: bytes
    texto: str
    tipo: str
    itens: list = field(default_factory=list)


_EN_HEAD = {"en", "eng", "english", "en_us", "en-us", "en_gb", "en-gb", "inglês", "ingles"}
_JSON_STR = re.compile(r'"(?:[^"\\\n]|\\.)*"')
_KV = re.compile(r"^(\s*[A-Za-z_][\w.\-]*\s*[=:]\s*)(.*?)\s*$")
_LUA_LONG = re.compile(r"\[(=*)\[")
_LUA_ESC = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"', "'": "'"}


def decodificar(data: bytes) -> tuple[str, str, bytes] | None:
    """(texto, codificação, BOM) ou None se não for texto. Só UTF-8/UTF-16 (com BOM); o resto é binário."""
    if data.startswith(b"\xef\xbb\xbf"):
        enc, bom = "utf-8", data[:3]
    elif data.startswith(b"\xff\xfe"):
        enc, bom = "utf-16-le", data[:2]
    elif data.startswith(b"\xfe\xff"):
        enc, bom = "utf-16-be", data[:2]
    else:
        enc, bom = "utf-8", b""
    try:
        t = data[len(bom):].decode(enc)
    except UnicodeDecodeError:
        return None
    if "\0" in t:
        return None
    return t, enc, bom


def parece_texto(t: str) -> bool:
    """Conteúdo de texto legível (para arquivos sem extensão conhecida): quase tudo imprimível."""
    amostra = t[:8192]
    if len(amostra.strip()) < 16:
        return False
    ok = sum(1 for c in amostra if c.isprintable() or c in "\r\n\t")
    return ok / len(amostra) >= 0.95


def _tipo(nome: str) -> str:
    ext = nome.lower().rsplit(".", 1)[-1] if "." in nome.rsplit("/", 1)[-1] else ""
    return {"json": "json", "csv": "csv", "tsv": "csv", "lua": "lua", "xml": "xml",
            "ini": "kv", "cfg": "kv", "properties": "kv"}.get(ext, "linhas")


def _linhas(t: str):
    pos = 0
    for n, ln in enumerate(t.split("\n")):
        yield n, pos, ln.rstrip("\r")
        pos += len(ln) + 1


def _itens_linhas(t: str, kv: bool) -> list[Item]:
    out = []
    for n, pos, ln in _linhas(t):
        if kv:
            s = ln.lstrip()
            if not s or s[0] in ";#[":
                continue
            m = _KV.match(ln)
            if not m:
                continue
            ini, val = pos + m.end(1), m.group(2)
            if len(val) >= 2 and val[0] == val[-1] == '"':
                ini, val = ini + 1, val[1:-1]
            out.append(Item(f"l{n}", ini, ini + len(val), val, "kv"))
        else:
            s = ln.strip()
            ini = pos + (len(ln) - len(ln.lstrip()))
            out.append(Item(f"l{n}", ini, ini + len(s), s, "linha"))
    return out


def _itens_json(t: str) -> list[Item]:
    out, k = [], 0
    for m in _JSON_STR.finditer(t):
        j = m.end()
        while j < len(t) and t[j] in " \t\r\n":
            j += 1
        if j < len(t) and t[j] == ":":
            continue  # chave, não valor
        out.append(Item(f"v{k}", m.start(), m.end(), json.loads(m.group()), "json"))
        k += 1
    return out


def _itens_lua(t: str) -> list[Item]:
    out, k, i, n = [], 0, 0, len(t)
    while i < n:
        c = t[i]
        if t.startswith("--", i):
            m = _LUA_LONG.match(t, i + 2)
            if m:
                fim = t.find("]" + m.group(1) + "]", m.end())
                i = n if fim < 0 else fim + len(m.group(1)) + 2
            else:
                fim = t.find("\n", i)
                i = n if fim < 0 else fim + 1
        elif c == "[" and _LUA_LONG.match(t, i):
            m = _LUA_LONG.match(t, i)  # string longa [[...]]: não mexemos (pode ser código embutido)
            fim = t.find("]" + m.group(1) + "]", m.end())
            i = n if fim < 0 else fim + len(m.group(1)) + 2
        elif c in "\"'":
            j, buf, ok = i + 1, [], True
            while j < n and t[j] != c and t[j] != "\n":
                if t[j] == "\\":
                    e = t[j + 1] if j + 1 < n else ""
                    if e in _LUA_ESC:
                        buf.append(_LUA_ESC[e])
                    else:
                        ok = False  # \ddd, \x.., \z: não arrisco reescrever
                    j += 2
                    continue
                buf.append(t[j])
                j += 1
            if j >= n or t[j] != c:
                ok = False
            fim = min(j + 1, n)
            if ok:
                out.append(Item(f"s{k}", i, fim, "".join(buf), "lua" + c))
            k += 1
            i = fim
        else:
            i += 1
    return out


def _itens_xml(t: str) -> list[Item]:
    out = []
    for k, m in enumerate(re.finditer(r">([^<]*)<", t)):
        raw = m.group(1)
        s = raw.strip()
        if not s:
            continue
        ini = m.start(1) + (len(raw) - len(raw.lstrip()))
        out.append(Item(f"x{k}", ini, ini + len(s), html.unescape(s), "xml"))
    return out


def _csv_celulas(t: str, delim: str) -> list[list[tuple[int, int, str, bool]]]:
    """CSV com a posição de cada célula (para trocar só a célula, sem reescrever aspas das outras)."""
    rows, row, i, n = [], [], 0, len(t)
    while True:
        if i < n and t[i] == '"':
            j, buf = i + 1, []
            while True:
                if j >= n:
                    raise ValueError("aspas sem fim no CSV")
                if t[j] == '"':
                    if j + 1 < n and t[j + 1] == '"':
                        buf.append('"')
                        j += 2
                        continue
                    j += 1
                    break
                buf.append(t[j])
                j += 1
            row.append((i, j, "".join(buf), True))
        else:
            j = i
            while j < n and t[j] not in (delim, "\n", "\r"):
                j += 1
            row.append((i, j, t[i:j], False))
        i = j
        if i >= n:
            rows.append(row)
            break
        c = t[i]
        if c == delim:
            i += 1
            continue
        if c == "\r" and i + 1 < n and t[i + 1] == "\n":
            i += 2
        elif c in "\r\n":
            i += 1
        else:
            raise ValueError("texto depois das aspas no CSV")
        rows.append(row)
        row = []
        if i >= n:
            break
    return rows


def _delim(t: str) -> str:
    primeira = t.split("\n", 1)[0]
    return max((",", ";", "\t"), key=primeira.count) if primeira else ","


def _itens_csv(t: str, so_coluna_en: bool) -> list[Item]:
    rows = _csv_celulas(t, _delim(t))
    if not rows:
        return []
    head = [c[2].strip().lower() for c in rows[0]]
    col_en = next((k for k, h in enumerate(head) if h in _EN_HEAD), None)
    if col_en is None and so_coluna_en:
        return []
    out = []
    for r, row in enumerate(rows):
        if col_en is not None and r == 0:
            continue
        for c, (ini, fim, val, q) in enumerate(row):
            if col_en is not None and c != col_en:
                continue
            out.append(Item(f"r{r}c{c}", ini, fim, val, "csv", q))
    return out


def ler_texto(nome: str, data: bytes, so_coluna_en: bool = False, exigir_texto: bool = False) -> ArqTexto | None:
    """Abre um arquivo de texto e marca TODOS os candidatos (frase ou não; o filtro é eh_frase, depois).

    Os ids ficam estáveis entre leitura e releitura, que é o que a conferência da rebuild usa.
    """
    dec = decodificar(data)
    if dec is None:
        return None
    t, enc, bom = dec
    if exigir_texto and not parece_texto(t):
        return None
    tipo = _tipo(nome)
    try:
        if tipo == "json":
            json.loads(t)
            itens = _itens_json(t)
        elif tipo == "csv":
            itens = _itens_csv(t, so_coluna_en)
        elif tipo == "lua":
            itens = _itens_lua(t)
        elif tipo == "xml":
            itens = _itens_xml(t)
        elif tipo == "kv":
            itens = _itens_linhas(t, True)
        else:
            linhas = [ln for _, _, ln in _linhas(t) if ln.strip() and ln.strip()[0] not in ";#["]
            kv = bool(linhas) and sum(1 for ln in linhas if re.match(r"^\s*[A-Za-z_][\w.\-]*\s*=", ln)) >= 0.6 * len(linhas)
            tipo = "kv" if kv else "linhas"
            itens = _itens_linhas(t, kv)
    except ValueError:
        return None
    return ArqTexto(nome, enc, bom, t, tipo, itens)


def _normal(modo: str, s: str) -> str:
    """Como a frase nova fica depois de gravada e relida (linha única não pode ganhar quebra de linha)."""
    if modo in ("linha", "kv"):
        return re.sub(r"\s*[\r\n]+\s*", " ", s).strip()
    if modo == "xml":
        return s.strip()
    return s


def _escrever(it: Item, s: str) -> str:
    if it.modo in ("linha", "kv"):
        return s
    if it.modo == "json":
        return json.dumps(s, ensure_ascii=False)
    if it.modo.startswith("lua"):
        q = it.modo[3]
        return q + s.replace("\\", "\\\\").replace(q, "\\" + q).replace("\n", "\\n").replace("\r", "\\r") + q
    if it.modo == "xml":
        return html.escape(s, quote=False)
    if it.modo == "csv":
        if it.aspas or any(c in s for c in ',;\t"\r\n'):
            return '"' + s.replace('"', '""') + '"'
        return s
    raise MotorError(f"modo de texto desconhecido: {it.modo}")


def gravar_texto(arq: ArqTexto, novos: dict[str, str], so_coluna_en: bool = False) -> bytes:
    """Troca só os trechos das frases (de trás para frente) e confere relendo o arquivo gerado."""
    por_id = {it.id: it for it in arq.itens}
    trocas = []
    for lid, s in novos.items():
        it = por_id.get(lid)
        if it is None:
            raise MotorError(f"{arq.nome}: frase {lid} não existe")
        trocas.append((it, _normal(it.modo, s)))
    t = arq.texto
    for it, s in sorted(trocas, key=lambda x: x[0].ini, reverse=True):
        t = t[:it.ini] + _escrever(it, s) + t[it.fim:]
    data = arq.bom + t.encode(arq.enc)
    back = ler_texto(arq.nome, data, so_coluna_en)
    if back is None:
        raise MotorError(f"{arq.nome}: arquivo gerado não abre de novo")
    novo = {it.id: it.texto for it in back.itens}
    esperado = {it.id: it.texto for it in arq.itens}
    esperado.update({it.id: s for it, s in trocas})
    if novo != esperado:
        ruins = sorted(k for k in esperado.keys() | novo.keys() if esperado.get(k) != novo.get(k))
        raise MotorError(f"{arq.nome}: releitura não confere ({', '.join(ruins[:5])})")
    return data


# ================================================================== data.win
def _u32(b, p):
    return struct.unpack_from("<I", b, p)[0]


def chunks(b: bytes) -> list[tuple[str, int, int, int]]:
    """[(nome, início dos dados, tamanho, posição do cabeçalho)] dos chunks do FORM."""
    if len(b) < 8 or b[:4] != b"FORM":
        raise MotorError("data.win sem cabeçalho FORM")
    total = _u32(b, 4)
    if 8 + total != len(b):
        raise MotorError(f"tamanho do FORM ({8 + total}) não bate com o arquivo ({len(b)})")
    out, p = [], 8
    while p < len(b):
        if p + 8 > len(b):
            raise MotorError("chunk do data.win cortado")
        nome = b[p:p + 4].decode("latin-1")
        n = _u32(b, p + 4)
        if p + 8 + n > len(b):
            raise MotorError(f"chunk {nome} passa do fim do arquivo")
        out.append((nome, p + 8, n, p))
        p += 8 + n
    return out


def ler_strg(b: bytes, ini: int, tam: int) -> list[str | None]:
    """Textos da tabela STRG por índice (None = entrada que não é UTF-8 válido; nunca mexemos nela)."""
    if tam < 4:
        raise MotorError("chunk STRG vazio")
    n = _u32(b, ini)
    if 4 + 4 * n > tam:
        raise MotorError("tabela STRG maior que o chunk")
    out: list[str | None] = []
    for k in range(n):
        ptr = _u32(b, ini + 4 + 4 * k)
        if ptr + 4 > len(b):
            raise MotorError(f"STRG[{k}] aponta para fora do arquivo")
        ln = _u32(b, ptr)
        if ptr + 4 + ln >= len(b) or b[ptr + 4 + ln] != 0:
            raise MotorError(f"STRG[{k}] sem \\0 no fim")
        try:
            out.append(b[ptr + 4:ptr + 4 + ln].decode("utf-8"))
        except UnicodeDecodeError:
            out.append(None)
    return out


def _pad4(n: int) -> int:
    return (-n) % 4


def regravar_strg(b: bytes, novos: dict[int, str]) -> bytes:
    """Grava as frases novas no fim do arquivo e troca só os ponteiros da tabela STRG. Confere relendo."""
    cs = chunks(b)
    strg = next((c for c in cs if c[0] == "STRG"), None)
    if strg is None:
        raise MotorError("data.win sem chunk STRG")
    antigos = ler_strg(b, strg[1], strg[2])
    buf = bytearray(b)
    buf += b"\0" * _pad4(len(buf))
    ja: dict[str, int] = {}
    for idx, s in sorted(novos.items()):
        if not 0 <= idx < len(antigos):
            raise MotorError(f"STRG[{idx}] não existe")
        s = s.replace("\0", "")
        if s not in ja:
            ja[s] = len(buf)
            enc = s.encode("utf-8")
            buf += struct.pack("<I", len(enc)) + enc + b"\0"
            buf += b"\0" * _pad4(len(buf))
        struct.pack_into("<I", buf, strg[1] + 4 + 4 * idx, ja[s])
    cresceu = len(buf) - len(b)
    _nome, _ini, tam, cab = cs[-1]
    struct.pack_into("<I", buf, 4, _u32(b, 4) + cresceu)
    struct.pack_into("<I", buf, cab + 4, tam + cresceu)
    out = bytes(buf)
    # conferência: o arquivo novo anda pelos mesmos chunks e a tabela dá os textos esperados
    cs2 = chunks(out)
    if [c[0] for c in cs2] != [c[0] for c in cs] or [c[1] for c in cs2] != [c[1] for c in cs]:
        raise MotorError("chunks do data.win mudaram de lugar")
    s2 = next(c for c in cs2 if c[0] == "STRG")
    novos_lidos = ler_strg(out, s2[1], s2[2])
    esperado = list(antigos)
    for idx, s in novos.items():
        esperado[idx] = s.replace("\0", "")
    if novos_lidos != esperado:
        raise MotorError("tabela STRG relida não confere")
    return out


# ================================================================== arquivos de idioma ao lado
_PASTAS = {"lang", "langs", "language", "languages", "text", "texts", "localization", "localisation",
           "locale", "locales", "loc", "i18n", "l10n", "strings", "dialogue", "dialogues", "dialog"}
_EXTS = (".json", ".csv", ".txt", ".ini")
_EN = re.compile(r"(?:^|[^a-z])(?:en|eng|english|en_us|en-us|en_gb|en-gb)(?:[^a-z]|$)", re.IGNORECASE)
_OUTRO = re.compile(r"(?:^|[^a-z])(?:fr|de|es|it|ja|jp|ko|kr|zh|cn|tw|ru|pt|br|pl|nl|french|german|spanish|"
                    r"italian|japanese|korean|chinese|russian|portuguese|polish)(?:[^a-z]|$)", re.IGNORECASE)


def _partes(p: str) -> list[str]:
    ps = [x for x in p.replace("\\", "/").lower().split("/") if x]
    if ps:
        ps[-1] = ps[-1].rsplit(".", 1)[0]
    return ps


def arquivos_idioma(paths: list[str], tamanhos: dict | None = None) -> list[str]:
    """Arquivos de texto de idioma (inglês) ao lado do data.win.

    Entra: arquivo com 'en'/'english' no nome ou na pasta; ou arquivo numa pasta de idioma (lang/, text/...)
    que não seja de outro idioma, se na mesma pasta não houver um explicitamente em inglês.
    """
    cand = [p for p in paths if p.lower().endswith(_EXTS) and _base(p) not in DATA_NOMES]
    if tamanhos:
        cand = [p for p in cand if (tamanhos.get(p) or (0, 0))[1] <= MAX_TEXTO]
    en = {p for p in cand if any(_EN.search(x) for x in _partes(p))}
    dirs_en = {p.replace("\\", "/").rsplit("/", 1)[0] for p in en}
    out = []
    for p in cand:
        ps = _partes(p)
        if p in en or any(x in _PASTAS for x in ps[:-1]) and not any(_OUTRO.search(x) for x in ps) \
                and p.replace("\\", "/").rsplit("/", 1)[0] not in dirs_en:
            out.append(p)
    return out


# ================================================================== contrato
_AVISO_YYC = ("jogo GameMaker compilado (YYC): o texto que fica no código está no executável nativo, não no "
              "data.win; só dá para traduzir o que estiver fora dele")


def collect(files: dict, read) -> Coleta:
    paths = list(files)
    textos: list[Texto] = []
    destino: dict[str, tuple[str, str]] = {}   # id -> (caminho, chave local)
    datas: dict[str, tuple[bytes, list]] = {}
    arqs: dict[str, ArqTexto] = {}
    yyc = False
    achou_data = False
    for p in paths:
        if _base(p) not in DATA_NOMES:
            continue
        b = read(p)
        if b[:4] != b"FORM":
            continue  # game.win de outro formato, ou criptografado
        achou_data = True
        cs = chunks(b)
        nomes = {c[0]: c for c in cs}
        if "STRG" not in nomes:
            raise MotorError(f"{p}: sem chunk STRG")
        if "CODE" not in nomes or nomes["CODE"][2] == 0:
            yyc = True
        strs = ler_strg(b, nomes["STRG"][1], nomes["STRG"][2])
        datas[p] = (b, strs)
        for k, s in enumerate(strs):
            if s is not None and eh_frase(s, CODES_GM):
                tid = f"{p}|STRG|{k}"
                textos.append(Texto(tid, s, CODES_GM))
                destino[tid] = (p, str(k))
    if not achou_data:
        raise MotorError("nenhum data.win no formato FORM (pode estar criptografado ou ser outro motor)")
    for p in arquivos_idioma(paths, files):
        arq = ler_texto(p, read(p), so_coluna_en=True)
        if arq is None:
            continue
        arqs[p] = arq
        for it in arq.itens:
            if eh_frase(it.texto, CODES_GM):
                tid = f"{p}|{it.id}"
                textos.append(Texto(tid, it.texto, CODES_GM))
                destino[tid] = (p, it.id)
    if yyc and not textos:
        raise MotorError("jogo GameMaker compilado (YYC): o texto fica no executável nativo (main), não no "
                         "data.win, e não há arquivo de idioma ao lado para traduzir")

    def rebuild(trads: dict[str, str]) -> dict[str, bytes]:
        por_arq: dict[str, dict[str, str]] = {}
        for tid, s in trads.items():
            if tid in destino:
                p, k = destino[tid]
                por_arq.setdefault(p, {})[k] = s
        out: dict[str, bytes] = {}
        for p, novos in por_arq.items():
            if p in datas:
                b, strs = datas[p]
                mud = {int(k): s for k, s in novos.items() if s != strs[int(k)]}
                if mud:
                    out[p] = regravar_strg(b, mud)
            else:
                out[p] = gravar_texto(arqs[p], novos, so_coluna_en=True)
        return out

    aviso = _AVISO_YYC if yyc else ""
    return Coleta(textos, rebuild, aviso, {"yyc": yyc, "arquivos_idioma": sorted(arqs)})
