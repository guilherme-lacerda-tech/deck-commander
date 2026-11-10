"""Godot 3/4: .pck sintético com csv, json, tscn, dialogue e recursos binários (Translation e cena)."""
import hashlib
import struct

import pytest

from dc.traducao import eng_godot as g
from dc.traducao import ia
from dc.traducao.motores import MotorError, adapter_for


# ------------------------------------------------------------------ montadores independentes do adaptador
def _pck(files, ver=1, align=16, flags=0, godot=(3, 5, 0)):
    """files: [(caminho, bytes, flags)] -> .pck como o exportador do Godot grava."""
    head = b"GDPC" + struct.pack("<4I", ver, *godot)
    if ver == 2:
        head += struct.pack("<IQ", flags, 0)
    head += bytes(64) + struct.pack("<I", len(files))
    dir_len = len(head)
    for p, _d, _f in files:
        n = len(p.encode()) + (-len(p.encode())) % 4
        dir_len += 4 + n + 32 + (4 if ver == 2 else 0)
    base = dir_len + (-dir_len) % align
    body, offs = b"", []
    for _p, d, _f in files:
        body += bytes((-len(body)) % align)
        offs.append(len(body))
        body += d
    out = bytearray(b"GDPC" + struct.pack("<4I", ver, *godot))
    if ver == 2:
        out += struct.pack("<IQ", flags, base)
    out += bytes(64) + struct.pack("<I", len(files))
    for (p, d, f), o in zip(files, offs):
        pb = p.encode()
        pb += bytes((-len(pb)) % 4)
        out += struct.pack("<I", len(pb)) + pb + struct.pack("<QQ", o + (0 if ver == 2 else base), len(d))
        out += hashlib.md5(d).digest()
        if ver == 2:
            out += struct.pack("<I", f)
    assert len(out) == dir_len
    return bytes(out) + bytes(base - dir_len) + body


def _u(s):
    b = s.encode() + b"\0"
    return struct.pack("<I", len(b)) + b


def vstr(s): return struct.pack("<I", 5) + _u(s)
def vsname(s): return struct.pack("<I", 44) + _u(s)
def vint(i): return struct.pack("<Ii", 3, i)
def vbool(b): return struct.pack("<Ii", 2, int(b))
def vvec2(x, y): return struct.pack("<Iff", 10, x, y)
def vbytes(b): return struct.pack("<II", 31, len(b)) + b + bytes((-len(b)) % 4)
def vstrs(xs): return struct.pack("<II", 34, len(xs)) + b"".join(_u(x) for x in xs)
def vints(xs): return struct.pack("<II", 32, len(xs)) + struct.pack(f"<{len(xs)}i", *xs)
def varr(xs): return struct.pack("<II", 30, len(xs)) + b"".join(xs)
def vdict(pairs): return struct.pack("<II", 26, len(pairs)) + b"".join(k + v for k, v in pairs)
def vobj_int(i): return struct.pack("<III", 24, 2, i)


def _rsrc(recursos, g4=True):
    """recursos: [(tipo, [(nome, valor)])]; o último é o principal."""
    nomes = []
    for _t, props in recursos:
        for n, _v in props:
            if n not in nomes:
                nomes.append(n)
    h = b"RSRC" + struct.pack("<5I", 0, 0, 4 if g4 else 3, 0, 5 if g4 else 3) + _u(recursos[-1][0])
    h += struct.pack("<Q", 0)
    h += struct.pack("<IQ", 3, 123) + bytes(44) if g4 else bytes(56)
    h += struct.pack("<I", len(nomes)) + b"".join(_u(n) for n in nomes)
    h += struct.pack("<I", 0)  # externos
    h += struct.pack("<I", len(recursos))
    campos = []
    for k in range(len(recursos)):
        h += _u(f"local://{k}")
        campos.append(len(h))
        h += bytes(8)
    out = bytearray(h)
    for k, (t, props) in enumerate(recursos):
        struct.pack_into("<Q", out, campos[k], len(out))
        out += _u(t) + struct.pack("<I", len(props))
        for n, v in props:
            out += struct.pack("<I", nomes.index(n)) + v
    return bytes(out) + b"RSRC"


CSV = (b"keys,en,fr\r\nMENU_START,\"Start, now\",Commencer\r\nMENU_HP,\"HP: {hp} [b]max[/b]\",PV\r\n"
       b"EMPTY,,\r\n")
JSON = b'{\n  "title": "The [color=red]Big[/color] Quest",\n  "id": "hero_01",\n  "lines": ["Hello there %s", 3],' \
       b'\n  "Key with space": 1\n}\n'
TSCN = (b'[gd_scene format=2]\n\n[node name="L" type="Label"]\ntext = "Say \\"hi\\" to\nthe [b]world[/b]"\n'
        b'hint_tooltip = "Tip {name}"\nname_x = "nope"\n[node name="B" type="Button"]\ntext = "MENU_OK"\n')
DLG = (b"~ start\n# comment\nNathan: Hello {{player}}, how are you?\n- Fine thanks => next\n- Bad [if hp < 2] => end\n"
       b"Just narration here.\nset x = 1\n=> END\n")


def _g3_translation():
    return _rsrc([("Translation", [("locale", vstr("en")),
                                   ("messages", vstrs(["K1", "Welcome to the [b]game[/b]", "K2", "Bye %s"]))])],
                 g4=False)


def _g4_translation(locale="en"):
    return _rsrc([("Translation", [("locale", vstr(locale)),
                                   ("messages", vdict([(vsname("K1"), vsname("Open the door")),
                                                       (vsname("K2"), vsname("Score: {n}"))]))])])


def _g4_scene():
    names = ["Root", "Control", "Label", "text", "visible", "Label2", "tooltip_text", "position"]
    variants = [vstr("Hello world [b]x[/b]"), vbool(True), vstr("MENU_KEY"), vstr("Click here please"),
                vvec2(1, 2)]
    nodes = [-1, -1, 1, 0, -1, -1, 0, 0,                          # Root sem propriedades
             0, 0, 2, 2, -1, -1, 2, 3, 0, 4, 1, 0,                # Label: text, visible
             0, 0, 2, 5, -1, -1, 3, 3, 2, 6, 3, 7, 4, 1, 99]      # Label2: text (chave), tooltip, posição; 1 grupo
    bundled = vdict([(vstr("names"), vstrs(names)), (vstr("variants"), varr(variants)),
                     (vstr("node_count"), vint(3)), (vstr("nodes"), vints(nodes)),
                     (vstr("conn_count"), vint(0)), (vstr("version"), vint(3))])
    sub = ("StyleBoxFlat", [("bg", vvec2(0, 0)), ("raw", vbytes(b"abcde"))])
    return _rsrc([sub, ("PackedScene", [("_bundled", bundled)])])


PNG = bytes(range(256)) * 3


def _arquivos(g4):
    return [("res://data/text.csv", CSV, 0), ("res://data/story.json", JSON, 0), ("res://ui/menu.tscn", TSCN, 0),
            ("res://img/logo.png", PNG, 0), ("res://dlg/intro.dialogue", DLG, 0),
            ("res://lang/text.en.translation", _g4_translation() if g4 else _g3_translation(), 0),
            ("res://lang/text.ja.translation", _g4_translation("ja"), 0),
            (".godot/exported/x/export-menu.scn", _g4_scene(), 0)]


def _traduz(s):
    p, codes = ia.protect(s, g.CODES)
    return ia.restore("PT " + p + " ✓", codes)


def _coleta(blob):
    files = {"/Game.pck": (0, len(blob))}
    return g.collect(files, lambda p: {"/Game.pck": blob}[p])


# ------------------------------------------------------------------ testes
def test_detect():
    assert g.detect(["/Game.PCK", "/x.txt"])
    assert not g.detect(["/Audio/SoundBank.pck"])                    # Wwise
    assert not g.detect(["/Data/globalgamemanagers", "/x.pck"])      # Unity
    assert adapter_for(["/Game.pck"]) is g


@pytest.mark.parametrize("ver,g4,align", [(1, False, 16), (2, True, 16), (2, True, 64)])
def test_roundtrip_completo(ver, g4, align):
    arqs = _arquivos(g4)
    blob = _pck(arqs, ver=ver, align=align, godot=(4, 2, 0) if g4 else (3, 5, 0))
    col = _coleta(blob)
    textos = {t.id: t.text for t in col.textos}
    vals = set(textos.values())
    esperado = {"Start, now", "HP: {hp} [b]max[/b]", "The [color=red]Big[/color] Quest", "Hello there %s",
                'Say "hi" to\nthe [b]world[/b]', "Tip {name}", "Hello {{player}}, how are you?", "Fine thanks",
                "Bad", "Just narration here.", "Hello world [b]x[/b]", "Click here please"}
    assert esperado <= vals
    assert {"Open the door", "Score: {n}"} <= vals if g4 else {"Welcome to the [b]game[/b]", "Bye %s"} <= vals
    # chaves, ids e idioma não-inglês ficam de fora
    assert not vals & {"MENU_START", "MENU_OK", "MENU_KEY", "hero_01", "nope", "Commencer", "K1", "Key with space"}
    assert sum(1 for v in textos.values() if v == "Open the door") == (1 if g4 else 0)  # o .ja não entra

    novos = {i: _traduz(s) for i, s in textos.items()}
    out = col.rebuild(novos)
    assert list(out) == ["/Game.pck"]
    novo = out["/Game.pck"]
    back = _coleta(novo)
    assert {t.id: t.text for t in back.textos} == novos
    # códigos preservados
    for i, s in textos.items():
        assert g.CODES.findall(back_text := novos[i]) == g.CODES.findall(s), back_text

    pck = g.read_pck(novo)
    assert pck.version == ver and pck.align >= align
    orig = g.read_pck(blob)
    assert [e.path for e in pck.entries] == [e.path for e in orig.entries]
    base = pck.file_base if ver == 2 else 0
    for e in pck.entries:
        assert (e.offset - base) % align == 0
        assert hashlib.md5(novo[e.offset:e.offset + e.size]).digest() == e.md5
    logo = next(e for e in pck.entries if e.path.endswith("logo.png"))
    assert novo[logo.offset:logo.offset + logo.size] == PNG
    ja = next(e for e in pck.entries if e.path.endswith("ja.translation"))
    assert novo[ja.offset:ja.offset + ja.size] == _g4_translation("ja")


def test_csv_regravado_mantem_outras_colunas():
    _itens, aplicar = g._ext_csv(CSV)
    nb = aplicar({"r1": 'Começar, já "agora"'})
    rows = nb.decode().split("\r\n")
    assert rows[0] == "keys,en,fr"
    assert rows[1] == 'MENU_START,"Começar, já ""agora""",Commencer'
    assert dict(g._ext_csv(nb)[0])["r1"] == 'Começar, já "agora"'


def test_tscn_escapes():
    itens, aplicar = g._ext_tscn(TSCN)
    assert itens[0][1] == 'Say "hi" to\nthe [b]world[/b]'
    nb = aplicar({"p0": 'Diga "oi" \\ ao\nmundo'})
    assert b'text = "Diga \\"oi\\" \\\\ ao\nmundo"' in nb
    assert dict(g._ext_tscn(nb)[0])["p0"] == 'Diga "oi" \\ ao\nmundo'


def test_rsrc_offsets_corrigidos_quando_texto_cresce():
    blob = _rsrc([("Translation", [("locale", vstr("en")), ("messages", vstrs(["k", "short"]))]),
                  ("Other", [("name", vstr("after")), ("pos", vvec2(3, 4))])], g4=False)
    r = g._Rsrc(blob)
    spans = r.recursos()[0][1]["messages"][1]
    nb = r.regravar({1: "um texto bem mais comprido que o original"}, spans)
    r2 = g._Rsrc(nb)
    recs = r2.recursos()
    assert recs[0][1]["messages"][1][1].text == "um texto bem mais comprido que o original"
    assert recs[1][0] == "Other" and recs[1][1]["name"].text == "after"
    assert nb.endswith(b"RSRC")


def test_optimized_translation_vira_aviso():
    opt = _rsrc([("OptimizedTranslation", [("locale", vstr("en")), ("strings", vbytes(b"xx"))])])
    blob = _pck([("res://a.translation", opt, 0), ("res://b.json", JSON, 0)])
    col = _coleta(blob)
    assert "OptimizedTranslation" in col.aviso
    assert col.textos


def test_pck_criptografado():
    blob = _pck([("res://b.json", JSON, 0)], ver=2, flags=1, godot=(4, 1, 0))
    with pytest.raises(MotorError, match="executável"):
        _coleta(blob)


def test_arquivo_criptografado_copiado_igual():
    enc = b"GDEC" + bytes(60)  # conteúdo cifrado: só copia
    blob = _pck([("res://secret.json", enc, 1), ("res://b.json", JSON, 0)], ver=2, godot=(4, 1, 0))
    col = _coleta(blob)
    assert "criptografado" in col.aviso
    out = col.rebuild({t.id: _traduz(t.text) for t in col.textos})["/Game.pck"]
    e = g.read_pck(out).entries[0]
    assert out[e.offset:e.offset + len(enc)] == enc and e.flags == 1


def test_sem_pck_e_wwise():
    with pytest.raises(MotorError, match="embutido"):
        g.collect({"/main": (0, 0)}, lambda p: b"\x7fELF" + bytes(20) + struct.pack("<Q", 10) + b"GDPC")
    with pytest.raises(MotorError, match="Wwise"):
        g.collect({"/x.pck": (0, 0)}, lambda p: b"AKPK" + bytes(40))


def test_versao_desconhecida():
    blob = bytearray(_pck([("res://b.json", JSON, 0)]))
    struct.pack_into("<I", blob, 4, 3)
    with pytest.raises(MotorError, match="formato 3"):
        g.read_pck(bytes(blob))
