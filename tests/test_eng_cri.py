"""CRI .cpk sintético: tabelas @UTF montadas aqui, CRILAYLA com um compressor de teste (literais + cópias)."""
import json
import os
import struct

import pytest

from dc.traducao import eng_cri as cri
from dc.traducao import motores

U8, U16, U32, U64, STR = 0, 2, 4, 6, 0xA
_FMT = {U8: ">B", U16: ">H", U32: ">I", U64: ">Q"}


# ------------------------------------------------------------------ montador de @UTF (só para teste)
def utf_table(nome, cols, rows, const=None):
    """cols: [(nome, tipo)] por linha; const: {nome: (tipo, valor)} colunas de valor fixo; rows: [dict]."""
    const = const or {}
    strings = bytearray(b"<NULL>\0")
    pos_str = {}

    def s_off(s):
        if s not in pos_str:
            pos_str[s] = len(strings)
            strings.extend(s.encode() + b"\0")
        return pos_str[s]

    nome_o = s_off(nome)
    esquema = bytearray()
    for cn, (tp, v) in const.items():
        esquema += bytes([0x30 | tp]) + struct.pack(">I", s_off(cn))
        esquema += struct.pack(">I", s_off(v)) if tp == STR else struct.pack(_FMT[tp], v)
    for cn, tp in cols:
        esquema += bytes([0x50 | tp]) + struct.pack(">I", s_off(cn))
    linhas = bytearray()
    for r in rows:
        for cn, tp in cols:
            linhas += struct.pack(">I", s_off(r[cn])) if tp == STR else struct.pack(_FMT[tp], r[cn])
    tam_linha = sum(4 if tp == STR else struct.calcsize(_FMT[tp]) for _, tp in cols)
    ini_linhas = 32 + len(esquema)
    ini_str = ini_linhas + len(linhas)
    ini_dados = ini_str + len(strings)
    corpo = struct.pack(">HHIIIHHI", 0, ini_linhas - 8, ini_str - 8, ini_dados - 8, nome_o,
                        len(cols) + len(const), tam_linha, len(rows)) + esquema + linhas + strings
    corpo += b"\0" * ((-len(corpo)) % 8)
    return b"@UTF" + struct.pack(">I", len(corpo)) + corpo


def bloco(sig, utf, cifrar=False):
    if cifrar:
        utf = cri._embaralha(utf)
    return sig.encode() + struct.pack("<IQ", 0xFF, len(utf)) + utf


# ------------------------------------------------------------------ compressor CRILAYLA de teste
def crilayla(d: bytes) -> bytes:
    assert len(d) >= 0x100
    body = d[0x100:]
    L = len(body)
    bits = []

    def emit(v, n):
        bits.extend((v >> (n - 1 - k)) & 1 for k in range(n))

    j = L - 1
    while j >= 0:
        best_m, best_d = 0, 0
        for dist in range(3, min(8194, L - 1 - j) + 1):
            m = 0
            while j - m >= 0 and body[j - m] == body[j - m + dist] and m < 600:
                m += 1
            if m > best_m:
                best_m, best_d = m, dist
        if best_m >= 3:
            emit(1, 1)
            emit(best_d - 3, 13)
            n = best_m - 3
            cheio = True
            for lv in (2, 3, 5, 8):
                mx = (1 << lv) - 1
                v = min(n, mx)
                emit(v, lv)
                n -= v
                if v != mx:
                    cheio = False
                    break
            if cheio:
                while True:
                    v = min(n, 255)
                    emit(v, 8)
                    n -= v
                    if v != 255:
                        break
            j -= best_m
        else:
            emit(0, 1)
            emit(body[j], 8)
            j -= 1
    bits += [0] * ((-len(bits)) % 8)
    packed = bytes(int("".join(map(str, bits[k:k + 8])), 2) for k in range(0, len(bits), 8))
    return b"CRILAYLA" + struct.pack("<II", L, len(packed)) + packed[::-1] + d[:0x100]


# ------------------------------------------------------------------ CPK de teste
TXT = "Hello, brave hero.\r\nThe castle is far away.\r\nOK\r\n"
JSN = json.dumps({"title": "A long journey begins", "id": "evt_001", "lines": ["Wake up, sleepy head"]}, indent=1)
LUA = '-- npc talk\nlocal t = { greet = "Good morning, sir", key = "npc_01", \'Single quoted line here\' }\n'
COMP = ("Repeated words compress well. " * 20) + "\nLast line of the file.\n"
BIN = bytes(range(256)) * 3


def _cpk(cifrar_toc=False, align=0x20):
    arqs = [("text", "dialog_en.txt", TXT.encode()), ("data", "msg.json", JSN.encode("utf-8")),
            ("img", "a.bin", BIN), ("text", "comp.txt", COMP.encode()), ("script", "talk.lua", LUA.encode())]
    gravados = [crilayla(d) if n == "comp.txt" else d for _, n, d in arqs]
    toc_off = 0x800
    # TOC com offsets provisórios para saber o tamanho
    def toc_utf(offs):
        rows = [{"DirName": dn, "FileName": fn, "FileSize": len(g), "ExtractSize": len(d), "FileOffset": o, "ID": k}
                for k, ((dn, fn, d), g, o) in enumerate(zip(arqs, gravados, offs))]
        return utf_table("CpkTocInfo", [("DirName", STR), ("FileName", STR), ("FileSize", U32),
                                        ("ExtractSize", U32), ("FileOffset", U64), ("ID", U32)], rows)
    toc = bloco("TOC ", toc_utf([0] * len(arqs)), cifrar_toc)
    content_off = (toc_off + len(toc) + 0x7FF) & ~0x7FF
    offs, pos = [], content_off
    for g in gravados:
        pos += (-pos) % align
        offs.append(pos - toc_off)
        pos += len(g)
    fim_cont = pos
    etoc_off = fim_cont + ((-fim_cont) % align)
    etoc = bloco("ETOC", utf_table("CpkEtocInfo", [("LocalDir", STR), ("UpdateDateTime", U64)],
                                   [{"LocalDir": "x", "UpdateDateTime": 123456789}] * len(arqs)))
    toc = bloco("TOC ", toc_utf(offs), cifrar_toc)
    cab_cols = [("ContentOffset", U64), ("ContentSize", U64), ("TocOffset", U64), ("TocSize", U64),
                ("EtocOffset", U64), ("EtocSize", U64), ("EnabledPackedSize", U64), ("EnabledDataSize", U64),
                ("Files", U32), ("Align", U16)]
    cab = bloco("CPK ", utf_table("CpkHeader", cab_cols, [{
        "ContentOffset": content_off, "ContentSize": fim_cont - content_off, "TocOffset": toc_off,
        "TocSize": len(toc), "EtocOffset": etoc_off, "EtocSize": len(etoc),
        "EnabledPackedSize": sum(map(len, gravados)), "EnabledDataSize": sum(len(d) for _, _, d in arqs),
        "Files": len(arqs), "Align": align}], const={"Tvers": (STR, "CPKMC2.18.04")}))
    out = bytearray(cab)
    out += b"\0" * (toc_off - len(out))
    out += toc
    out += b"\0" * (content_off - len(out))
    for o, g in zip(offs, gravados):
        out += b"\0" * (o + toc_off - len(out))
        out += g
    out += b"\0" * (etoc_off - len(out))
    out += etoc
    return bytes(out)


def _coleta(arqs):
    return cri.collect({p: (0, len(b)) for p, b in arqs.items()}, lambda p: arqs[p])


def test_crilayla_vetor_proprio():
    d = os.urandom(0x100) + COMP.encode() + bytes(50) + b"abcabcabc" * 40
    c = crilayla(d)
    assert len(c) < len(d)  # comprimiu de verdade (usa cópias)
    assert cri.crilayla_descomprimir(c) == d


def test_crilayla_comprimento_longo():
    d = bytes(0x100) + b"Z" * 5000 + b"tail"
    assert cri.crilayla_descomprimir(crilayla(d)) == d


def test_detect():
    assert cri.detect(["/data/text.cpk"]) and not cri.detect(["/data/text.pak"])
    assert motores.adapter_for(["/a.cpk"]) is cri


@pytest.mark.parametrize("cifrar", [False, True])
def test_abre_cpk_e_le_arquivos(cifrar):
    cpk = cri.abrir_cpk(_cpk(cifrar))
    assert cpk.base == 0x800 and cpk.alinha == 0x20 and cpk.toc.cifrado == cifrar
    by = {i.caminho: cpk.conteudo(i) for i in cpk.internos}
    assert by["text/comp.txt"] == COMP.encode() and by["img/a.bin"] == BIN and by["data/msg.json"] == JSN.encode()
    assert cpk.cab.tab.linhas[0]["Tvers"] == "CPKMC2.18.04"


@pytest.mark.parametrize("cifrar", [False, True])
def test_roundtrip(cifrar):
    b = _cpk(cifrar)
    col = _coleta({"/data/game.cpk": b})
    by = {t.id: t.text for t in col.textos}
    assert by == {
        "/data/game.cpk|text/dialog_en.txt|l0": "Hello, brave hero.",
        "/data/game.cpk|text/dialog_en.txt|l1": "The castle is far away.",
        "/data/game.cpk|data/msg.json|v0": "A long journey begins",
        "/data/game.cpk|data/msg.json|v2": "Wake up, sleepy head",
        "/data/game.cpk|text/comp.txt|l0": COMP.split("\n")[0].strip(),
        "/data/game.cpk|text/comp.txt|l1": "Last line of the file.",
        "/data/game.cpk|script/talk.lua|s0": "Good morning, sir",
        "/data/game.cpk|script/talk.lua|s2": "Single quoted line here",
    }
    tr = {
        "/data/game.cpk|text/dialog_en.txt|l1": "O castelo fica muito, muito longe.",
        "/data/game.cpk|data/msg.json|v0": "Uma longa \"jornada\" começa",
        "/data/game.cpk|text/comp.txt|l1": "Última linha\ndo arquivo.",
        "/data/game.cpk|script/talk.lua|s2": "Linha com 'aspas' aqui",
    }
    out = col.rebuild(tr)["/data/game.cpk"]
    cpk = cri.abrir_cpk(out)
    assert cpk.toc.cifrado == cifrar
    by2 = {i.caminho: (i, cpk.conteudo(i)) for i in cpk.internos}
    assert by2["text/dialog_en.txt"][1] == b"Hello, brave hero.\r\nO castelo fica muito, muito longe.\r\nOK\r\n"
    assert json.loads(by2["data/msg.json"][1])["title"] == "Uma longa \"jornada\" começa"
    assert by2["img/a.bin"][1] == BIN
    comp_i, comp = by2["text/comp.txt"]
    assert comp_i.tam == comp_i.real and comp.endswith(b"\n\xc3\x9altima linha do arquivo.\n")  # gravado sem compressão
    assert b"'Linha com \\'aspas\\' aqui'" in by2["script/talk.lua"][1]
    # alinhamento e tabelas
    assert all(i.pos % 0x20 == 0 for i in cpk.internos)
    h = cpk.cab.tab.linhas[0]
    etoc = cri.ler_bloco(out, h["EtocOffset"], "ETOC")
    assert etoc.tab.linhas[0]["UpdateDateTime"] == 123456789
    assert h["EtocOffset"] >= max(i.pos + i.tam for i in cpk.internos)
    assert h["EnabledDataSize"] == sum(i.real for i in cpk.internos)
    assert h["EnabledPackedSize"] == sum(i.tam for i in cpk.internos)
    assert h["ContentSize"] == max(i.pos + i.tam for i in cpk.internos) - h["ContentOffset"]
    # coleta de novo mostra as frases novas
    by3 = {t.id: t.text for t in _coleta({"/data/game.cpk": out}).textos}
    assert by3["/data/game.cpk|text/dialog_en.txt|l1"] == "O castelo fica muito, muito longe."
    assert by3["/data/game.cpk|text/comp.txt|l1"] == "Última linha do arquivo."
    assert by3["/data/game.cpk|script/talk.lua|s2"] == "Linha com 'aspas' aqui"


def test_cpk_sem_texto_coleta_vazia_com_aviso():
    toc_off = 0x800
    dados = bytes(range(256)) * 4
    toc = bloco("TOC ", utf_table("CpkTocInfo", [("DirName", STR), ("FileName", STR), ("FileSize", U32),
                                                ("ExtractSize", U32), ("FileOffset", U64)],
                                  [{"DirName": "", "FileName": "x.bin", "FileSize": len(dados),
                                    "ExtractSize": len(dados), "FileOffset": 0x800}]))
    cab = bloco("CPK ", utf_table("CpkHeader", [("ContentOffset", U64), ("TocOffset", U64), ("Align", U16)],
                                  [{"ContentOffset": 0x1000, "TocOffset": toc_off, "Align": 0x800}]))
    b = cab + bytes(toc_off - len(cab)) + toc
    b += bytes(0x1000 - len(b)) + dados
    col = _coleta({"/a.cpk": b})
    assert col.textos == [] and col.aviso.startswith(cri.AVISO_SEM_TEXTO)
    assert col.rebuild({}) == {}


def test_cpk_quebrado_vira_aviso():
    col = _coleta({"/a.cpk": b"NOPE" + bytes(100)})
    assert col.textos == [] and "CPK" in col.aviso


def test_regravar_sem_mudanca_preserva_bytes():
    b = _cpk()
    cpk = cri.abrir_cpk(b)
    assert cri.regravar_cpk(cpk, {}) == b
