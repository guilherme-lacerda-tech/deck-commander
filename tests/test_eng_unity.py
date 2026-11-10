"""Unity no Switch: SerializedFile e bundles UnityFS SINTÉTICOS montados aqui (nenhum jogo real).

Roundtrip: collect -> rebuild -> collect com as frases novas; objetos não tocados idênticos byte a byte.
"""
import lzma
import struct

import pytest

from dc.traducao import eng_unity as U
from dc.traducao import lz4blk, motores

E = "<"
_COMMON_REV = {v: k for k, v in U._COMMON.items()}


# ------------------------------------------------------------------ montadores
def s_al(b: bytes) -> bytes:
    if isinstance(b, str):
        b = b.encode("utf-8")
    out = struct.pack(E + "i", len(b)) + b
    return out + b"\0" * ((-len(out)) % 4)


def str_nodes(level, name, meta=0x8000):
    return [(level, "string", name, -1, 0, meta), (level + 1, "Array", "Array", -1, 1, 0x4000),
            (level + 2, "int", "size", 4, 0, 0), (level + 2, "char", "data", 1, 0, 0)]


def tree_blob(nodes, version):
    strs = bytearray()
    offs = {}

    def so(s):
        if s in ("string", "Array", "int", "Base", "m_Name"):  # parte vem da tabela comum da Unity
            return _COMMON_REV[s] | 0x80000000
        if s not in offs:
            offs[s] = len(strs)
            strs.extend(s.encode() + b"\0")
        return offs[s]

    raw = b""
    for k, (lvl, typ, name, size, flags, meta) in enumerate(nodes):
        raw += struct.pack(E + "HBBIIiii", 1, lvl, flags, so(typ), so(name), size, k, meta)
        if version >= 19:
            raw += struct.pack(E + "Q", 0)
    return struct.pack(E + "ii", len(nodes), len(strs)) + raw + bytes(strs)


def build_sf(version, types, objects, typetree=True):
    """types: [(class_id, nodes|None)]; objects: [(path_id, índice_do_tipo, bytes)]."""
    hs = 48 if version >= 22 else 20
    m = bytearray(b"2020.3.0f1\0" + struct.pack(E + "i", 38) + bytes([1 if typetree else 0]))
    m += struct.pack(E + "i", len(types))
    for cid, nodes in types:
        m += struct.pack(E + "i", cid)
        if version >= 16:
            m += b"\0"
        if version >= 17:
            m += struct.pack(E + "h", 0 if cid == 114 else -1)
        if (version < 16 and cid < 0) or (version >= 16 and cid == 114):
            m += b"\x11" * 16
        m += b"\x22" * 16
        if typetree:
            m += tree_blob(nodes, version)
            if version >= 21:
                m += struct.pack(E + "i", 0)
    data, starts = bytearray(), []
    for _pid, _ti, payload in objects:
        data += b"\0" * ((-len(data)) % 8)
        starts.append(len(data))
        data += payload
    m += struct.pack(E + "i", len(objects))
    for (pid, ti, payload), st in zip(objects, starts):
        while (hs + len(m)) % 4:
            m += b"\0"
        m += struct.pack(E + "q", pid)
        m += struct.pack(E + "q", st) if version >= 22 else struct.pack(E + "I", st)
        m += struct.pack(E + "I", len(payload))
        if version >= 16:
            m += struct.pack(E + "i", ti)
        else:
            cid = types[ti][0]
            m += struct.pack(E + "iH", cid, cid & 0xFFFF)
        if version < 17:
            m += struct.pack(E + "h", -1)
        if version in (15, 16):
            m += b"\0"
    m += struct.pack(E + "ii", 0, 0)  # scripts, externos
    if version >= 20:
        m += struct.pack(E + "i", 0)
    m += b"\0"
    do = (hs + len(m) + 15) // 16 * 16
    total = do + len(data)
    if version >= 22:
        head = struct.pack(">IIII", 0, 0, version, 0) + b"\0\0\0\0" + struct.pack(">IQQQ", len(m), total, do, 0)
    else:
        head = struct.pack(">IIII", len(m), total, version, do) + b"\0\0\0\0"
    return head + bytes(m) + b"\0" * (do - hs - len(m)) + bytes(data)


def lzma_unity(data: bytes) -> bytes:
    props = {"id": lzma.FILTER_LZMA1, "dict_size": 1 << 16, "lc": 3, "lp": 0, "pb": 2}
    return bytes([(2 * 5 + 0) * 9 + 3]) + (1 << 16).to_bytes(4, "little") + lzma.compress(
        data, format=lzma.FORMAT_RAW, filters=[props])


def comp(method, data):
    return {0: lambda d: d, 1: lzma_unity, 2: lz4blk.compress_literal, 3: lz4blk.compress_literal}[method](data)


def build_bundle(nodes, fmt=7, method=2, bi_method=2, chunk=100, at_end=False, pad=False):
    """nodes: [(caminho, bytes, flags)]."""
    stream, dirs = b"", []
    for path, data, fl in nodes:
        dirs.append((len(stream), len(data), fl, path))
        stream += data
    blocks = [stream[k:k + chunk] for k in range(0, len(stream), chunk)]
    cblocks = [comp(method, b) for b in blocks]
    bi = b"\x33" * 16 + struct.pack(">i", len(blocks))
    for b, c in zip(blocks, cblocks):
        bi += struct.pack(">IIH", len(b), len(c), 0x40 | method)
    bi += struct.pack(">i", len(dirs))
    for off, sz, fl, path in dirs:
        bi += struct.pack(">qqI", off, sz, fl) + path.encode() + b"\0"
    cbi = comp(bi_method, bi)
    flags = bi_method | 0x40 | (0x80 if at_end else 0) | (0x200 if pad else 0)
    out = bytearray(b"UnityFS\0" + struct.pack(">I", fmt) + b"5.x.x\0" + b"2020.3.0f1\0")
    size_pos = len(out)
    out += struct.pack(">qIII", 0, len(cbi), len(bi), flags)
    if fmt >= 7:
        out += b"\0" * ((-len(out)) % 16)
    if not at_end:
        out += cbi
    if pad:
        out += b"\0" * ((-len(out)) % 16)
    out += b"".join(cblocks)
    if at_end:
        out += cbi
    struct.pack_into(">q", out, size_pos, len(out))
    return bytes(out)


CSV = ('key,English,Japanese\r\n'
       'menu_start,"Start Game",ゲーム開始\r\n'
       'menu_quit,Quit to title,終了\r\n'
       'npc_1,"He said ""hi"", then left",言った\r\n'
       'num,42,42\r\n')


def ta(name, text, enc="utf-8"):
    return s_al(name) + s_al(text.encode(enc) if isinstance(text, str) else text)


def mono_header(name):
    return (struct.pack(E + "iq", 0, 1) + b"\x01\0\0\0" + struct.pack(E + "iq", 0, 99) + s_al(name))


TA_NODES = [(0, "TextAsset", "Base", -1, 0, 0)] + str_nodes(1, "m_Name") + str_nodes(1, "m_Script")


def i2_nodes():
    n = [(0, "MonoBehaviour", "Base", -1, 0, 0),
         (1, "PPtr<GameObject>", "m_GameObject", 12, 0, 0), (2, "int", "m_FileID", 4, 0, 0),
         (2, "SInt64", "m_PathID", 8, 0, 0),
         (1, "UInt8", "m_Enabled", 1, 0, 0x4000),
         (1, "PPtr<MonoScript>", "m_Script", 12, 0, 0), (2, "int", "m_FileID", 4, 0, 0),
         (2, "SInt64", "m_PathID", 8, 0, 0)]
    n += str_nodes(1, "m_Name")
    n += [(1, "LanguageSourceData", "mSource", -1, 0, 0),
          (2, "vector", "mTerms", -1, 0, 0), (3, "Array", "Array", -1, 1, 0), (4, "int", "size", 4, 0, 0),
          (4, "TermData", "data", -1, 0, 0)]
    n += str_nodes(5, "Term")
    n += [(5, "UInt8", "TermType", 1, 0, 0x4000),
          (5, "vector", "Languages", -1, 0, 0), (6, "Array", "Array", -1, 1, 0), (7, "int", "size", 4, 0, 0)]
    n += str_nodes(7, "data")
    n += [(2, "vector", "mLanguages", -1, 0, 0), (3, "Array", "Array", -1, 1, 0), (4, "int", "size", 4, 0, 0),
          (4, "LanguageData", "data", -1, 0, 0)]
    n += str_nodes(5, "Name") + str_nodes(5, "Code")
    n += [(1, "int", "mVersion", 4, 0, 0)]
    return n


def i2_payload(terms, langs=(("Japanese", "ja"), ("English", "en"))):
    b = mono_header("I2Languages")
    b += struct.pack(E + "i", len(terms))
    for key, vals in terms:
        b += s_al(key) + b"\x00\0\0\0" + struct.pack(E + "i", len(vals)) + b"".join(s_al(v) for v in vals)
    b += struct.pack(E + "i", len(langs)) + b"".join(s_al(nm) + s_al(cd) for nm, cd in langs)
    return b + struct.pack(E + "i", 7)


def collect_from(files: dict):
    return U.collect({p: (0, len(b)) for p, b in files.items()}, lambda p: files[p])


def objs(blob):
    sf = U.parse_sf(blob)
    return {o.path_id: sf.obj(o) for o in sf.objects}


# ------------------------------------------------------------------ testes
def test_detect():
    assert U.detect(["Data/globalgamemanagers", "Data/level0"])
    assert U.detect(["/Data/data.unity3d"])
    assert U.detect(["Data/StreamingAssets/aa/Switch/x"])
    assert U.detect(["Data/sharedassets3.assets"]) and U.detect(["Data/resources.assets"])
    assert U.detect(["foo/ui.bundle"])
    assert not U.detect(["romfs/Message/a.msbt", "Content/Paks/x.pak"])
    assert "eng_unity" in motores.ADAPTADORES


def test_common_strings_offsets():
    # offsets públicos conhecidos da tabela CommonString da Unity
    assert U._COMMON[0] == "AABB" and U._COMMON[49] == "Array" and U._COMMON[55] == "Base"
    assert U._COMMON[840] == "string"


def test_loose_serializedfile_textasset_csv_roundtrip():
    tex = bytes(range(256)) * 3  # "Texture2D" qualquer: tem que ficar idêntico
    sdf = mono_header("LiberationSans SDF") + b"\x05" * 40
    blob = build_sf(17, [(49, None), (28, None), (114, None)],
                    [(1, 0, ta("Strings", CSV)), (2, 1, tex), (3, 2, sdf),
                     (4, 0, ta("binario", b"\x00\x01\x02\xff" * 10))], typetree=False)
    files = {"Data/resources.assets": blob, "Data/resources.assets.resS": b"\x99" * 64}
    col = collect_from(files)
    got = {t.id: t.text for t in col.textos}
    assert got == {"Data/resources.assets|1|1": "Start Game", "Data/resources.assets|1|2": "Quit to title",
                   "Data/resources.assets|1|3": 'He said "hi", then left'}
    assert "SDF" in col.aviso and "typetree" in col.aviso

    new = {"Data/resources.assets|1|1": "Começar o jogo, agora",
           "Data/resources.assets|1|2": "Sair",
           "Data/resources.assets|1|3": 'Ele disse "oi" e foi\nembora'}
    out = col.rebuild(new)
    assert set(out) == {"Data/resources.assets"}
    col2 = collect_from({**files, **out})
    assert {t.id: t.text for t in col2.textos} == new
    a, b = objs(blob), objs(out["Data/resources.assets"])
    assert b[2] == a[2] and b[3] == a[3] and b[4] == a[4]
    sf2 = U.parse_sf(out["Data/resources.assets"])
    assert all(o.start % 8 == 0 for o in sf2.objects)
    _n, script, _h = U._ta_get(sf2, sf2.objects[0])
    assert "ゲーム開始" in script.decode() and script.decode().startswith("key,English,Japanese\r\n")


def test_v22_typetree_json_and_i2_roundtrip():
    js = '{\n  "title": "The Lost Key",\n  "id": "lost_key",\n  "lines": ["Hello there, friend!", "ok"]\n}'
    i2 = i2_payload([("UI/Start", ["スタート", "Press any button"]),
                     ("UI/Quit", ["終了", "Quit"]),
                     ("UI/Long", ["長い", "A long, long sentence."])])
    blob = build_sf(22, [(49, TA_NODES), (114, i2_nodes()), (1, [(0, "GameObject", "Base", 4, 0, 0)])],
                    [(10, 0, ta("dialog", js)), (11, 1, i2), (12, 2, b"\x07\0\0\0")])
    files = {"Data/sharedassets0.assets": blob}
    col = collect_from(files)
    got = {t.id.split("|", 1)[1]: t.text for t in col.textos}
    assert got == {"10|0": "The Lost Key", "10|2": "Hello there, friend!",
                   "11|mSource.mTerms[0].Languages[1]": "Press any button",
                   "11|mSource.mTerms[1].Languages[1]": "Quit",
                   "11|mSource.mTerms[2].Languages[1]": "A long, long sentence."}
    p = "Data/sharedassets0.assets|"
    new = {p + "10|0": 'A Chave "Perdida"', p + "10|2": "Olá, amigo!",
           p + "11|mSource.mTerms[0].Languages[1]": "Aperte qualquer botão",
           p + "11|mSource.mTerms[2].Languages[1]": "Uma frase longa, bem longa, com ç e ã."}
    out = col.rebuild(new)
    col2 = collect_from(out)
    got2 = {t.id: t.text for t in col2.textos}
    for k, v in new.items():
        assert got2[k] == v
    assert got2[p + "11|mSource.mTerms[1].Languages[1]"] == "Quit"
    a, b = objs(blob), objs(out["Data/sharedassets0.assets"])
    assert a[12] == b[12]
    # o japonês (outro idioma) e as chaves continuam iguais
    sf2 = U.parse_sf(out["Data/sharedassets0.assets"])
    w = U._walk(sf2.objects[1].type.tree, sf2.obj(sf2.objects[1]), "<")
    d = dict(w.strings)
    assert d["mSource.mTerms[0].Languages[0]"] == "スタート".encode() and d["mSource.mTerms[0].Term"] == b"UI/Start"
    assert struct.unpack("<i", sf2.obj(sf2.objects[1])[-4:])[0] == 7


@pytest.mark.parametrize("fmt,method,bi_method,at_end,pad", [
    (7, 2, 2, False, False),   # LZ4 nos blocos e no índice
    (6, 1, 2, True, False),    # LZMA nos blocos, índice LZ4 no fim do arquivo
    (7, 1, 1, False, True),    # tudo LZMA, com alinhamento antes dos dados
    (6, 3, 0, False, False),   # LZ4HC, índice sem compressão
])
def test_bundle_roundtrip(fmt, method, bi_method, at_end, pad):
    sf = build_sf(21, [(49, TA_NODES), (28, [(0, "Texture2D", "Base", 8, 0, 0)])],
                  [(5, 1, b"\xab" * 8), (6, 0, ta("lines", "Hello world\nSecond line here\n\nok\n"))])
    ress = bytes(range(200)) * 2
    bundle = build_bundle([("CAB-abc", sf, 4), ("CAB-abc.resS", ress, 0)], fmt=fmt, method=method,
                          bi_method=bi_method, at_end=at_end, pad=pad)
    files = {"Data/StreamingAssets/aa/Switch/ui_assets_all.bundle": bundle}
    col = collect_from(files)
    path = "Data/StreamingAssets/aa/Switch/ui_assets_all.bundle"
    assert {t.id: t.text for t in col.textos} == {f"{path}:CAB-abc|6|0": "Hello world",
                                                  f"{path}:CAB-abc|6|1": "Second line here"}
    assert "sem compressão" in col.aviso
    new = {f"{path}:CAB-abc|6|0": "Olá mundo, tudo bem com você?", f"{path}:CAB-abc|6|1": "Segunda linha aqui"}
    out = col.rebuild(new)
    b2 = U.parse_bundle(out[path])
    assert b2.fmt == fmt and b2.flags & 0x3F == 0 and all(bl[2] & 0x3F == 0 for bl in b2.blocks)
    assert b2.uver == "5.x.x" and b2.urev == "2020.3.0f1"
    nodes = {n[3]: n for n in b2.nodes}
    assert b2.node_bytes(nodes["CAB-abc.resS"]) == ress and nodes["CAB-abc"][2] == 4
    col2 = collect_from(out)
    assert {t.id: t.text for t in col2.textos} == new
    assert objs(b2.node_bytes(nodes["CAB-abc"]))[5] == b"\xab" * 8


def test_formats_segments():
    yarn = "title: Start\ntags:\n---\nSam: Hello there! #line:a1\n<<set $x to 1>>\n-> Sure thing\n===\n"
    assert [s.text for s in U._segments("yarn", yarn, {}) if s.want] == ["Hello there!", "Sure thing"]
    assert U._detect_fmt(yarn)[0] == "yarn"
    xml = '<root><e id="1">Fish &amp; Chips</e><e><![CDATA[Big <b>fish</b>]]></e><n>12</n></root>'
    segs = [s for s in U._segments("xml", xml, {}) if s.want]
    assert [s.text for s in segs] == ["Fish & Chips", "Big <b>fish</b>"]
    ini = "[ui]\nstart = Start the game\ncount=3\n"
    assert U._detect_fmt(ini)[0] == "ini"
    assert [s.text for s in U._segments("ini", ini, {}) if s.want] == ["Start the game"]
    tsv = "ID\tEnglish\nA\tOne thing\n"
    assert U._detect_fmt(tsv) == ("csv", {"d": "\t", "col": 1})
    assert U._detect_fmt("ID,ja,fr\nA,x,y\nB,z,w\n")[0] is None
    ink = '{"inkVersion":21,"root":[["^Once upon a time.","\\n",["done"]]]}'
    assert [s.text for s in U._segments("json", ink, {}) if s.want] == ["Once upon a time."]


def test_utf16_textasset_roundtrip():
    text = "﻿Key\tEnglish\r\nk1\tGood morning\r\n"
    blob = build_sf(19, [(49, None)], [(1, 0, ta("loc", text, "utf-16-le"))], typetree=False)
    col = collect_from({"Data/level0": blob})
    assert [t.text for t in col.textos] == ["Good morning"]
    out = col.rebuild({col.textos[0].id: "Bom dia"})
    sf2 = U.parse_sf(out["Data/level0"])
    raw = U._ta_get(sf2, sf2.objects[0])[1]
    assert raw.decode("utf-16-le") == "﻿Key\tEnglish\r\nk1\tBom dia\r\n"


def test_empty_collect_explains():
    blob = build_sf(17, [(114, None)], [(1, 0, mono_header("GameText") + b"\x01" * 64)], typetree=False)
    col = collect_from({"Data/resources.assets": blob})
    assert col.textos == [] and "estudo" in col.aviso and "typetree" in col.aviso
    assert col.rebuild({}) == {}


def test_rebuild_refuses_when_reread_does_not_match(monkeypatch):
    blob = build_sf(17, [(49, None)], [(1, 0, ta("s", CSV))], typetree=False)
    col = collect_from({"Data/resources.assets": blob})
    monkeypatch.setattr(U, "_esc", lambda kind, new, p: new[:-1])  # grava errado de propósito
    with pytest.raises(motores.MotorError, match="não conferiu"):
        col.rebuild({col.textos[0].id: "Começar"})


def test_unsupported_version_is_skipped_not_crashed():
    blob = bytearray(build_sf(17, [(49, None)], [(1, 0, ta("s", CSV))], typetree=False))
    struct.pack_into(">I", blob, 8, 14)
    col = collect_from({"Data/resources.assets": bytes(blob)})
    assert col.textos == [] and any("versão 14" in p for p in col.extra["pulados"])
