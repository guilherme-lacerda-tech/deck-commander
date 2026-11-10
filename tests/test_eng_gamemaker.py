"""GameMaker: data.win sintético (FORM/GEN8/STRG/CODE/AUDO) e arquivos de idioma ao lado."""
import json
import struct

import pytest

from dc.traducao import eng_gamemaker as gm
from dc.traducao import motores
from dc.traducao.motores import MotorError

FRASES = ["obj_player", "spr_hero_idle", "rm_title", "Hello, traveler! Welcome home.", "scripts/main.gml",
          "Press # to start the game", "Arial", "global.player_name", "draw_text(x, y, msg)",
          "Ação já traduzida ✓ aqui", "void main() { gl_FragColor = v_vColour; }"]


def _data_win(strings, code_size=8):
    """Monta um data.win mínimo. Retorna os bytes."""
    gen8 = b"\x01" * 12
    # STRG: count + ponteiros + entradas (ponteiros absolutos, calculados depois)
    pre = 8 + (8 + len(gen8))                       # FORM header + chunk GEN8
    strg_ini = pre + 8
    tab_len = 4 + 4 * len(strings)
    entradas, ptrs, pos = b"", [], strg_ini + tab_len
    for s in strings:
        e = s.encode()
        blob = struct.pack("<I", len(e)) + e + b"\0"
        blob += b"\0" * ((-len(blob)) % 4)
        ptrs.append(pos)
        entradas += blob
        pos += len(blob)
    strg = struct.pack("<I", len(strings)) + struct.pack(f"<{len(strings)}I", *ptrs) + entradas
    code = b"\xAB" * code_size
    audo = struct.pack("<I", 0)
    corpo = (b"GEN8" + struct.pack("<I", len(gen8)) + gen8 + b"STRG" + struct.pack("<I", len(strg)) + strg
             + b"CODE" + struct.pack("<I", len(code)) + code + b"AUDO" + struct.pack("<I", len(audo)) + audo)
    return b"FORM" + struct.pack("<I", len(corpo)) + corpo


def _strings_de(b):
    cs = {c[0]: c for c in gm.chunks(b)}
    return gm.ler_strg(b, cs["STRG"][1], cs["STRG"][2])


def _coleta(arqs):
    return gm.collect({p: (0, len(b)) for p, b in arqs.items()}, lambda p: arqs[p])


def test_detect():
    assert gm.detect(["/data.win"]) and gm.detect(["/game.droid"]) and gm.detect(["/assets/game.unx"])
    assert not gm.detect(["/data/Map001.json"])
    assert motores.adapter_for(["/data.win", "/options.ini"]) is gm


def test_eh_frase():
    assert gm.eh_frase("Hello, traveler! Welcome home.")
    assert gm.eh_frase("Ação já traduzida ✓ aqui")
    for s in ("obj_player", "spr_hero_idle", "scripts/main.gml", "global.player_name", "Arial",
              "draw_text(x, y, msg)", "void main() { gl_FragColor = v_vColour; }", "HP: 10/10 MP: 2/2", "a b"):
        assert not gm.eh_frase(s), s


def test_strg_roundtrip_identificadores_ficam():
    b = _data_win(FRASES)
    assert _strings_de(b) == FRASES
    col = _coleta({"/data.win": b})
    ids = {t.id: t.text for t in col.textos}
    assert set(ids.values()) == {"Hello, traveler! Welcome home.", "Press # to start the game", "Ação já traduzida ✓ aqui"}
    assert col.aviso == "" and not col.extra["yyc"]
    out = col.rebuild({"/data.win|STRG|3": "Olá, viajante! Bem-vindo de volta ao lar.",
                       "/data.win|STRG|5": "Aperte # para começar"})
    novo = out["/data.win"]
    # tudo antes do fim original fica igual, exceto os 2 ponteiros, o tamanho do FORM e do último chunk
    cs = gm.chunks(novo)
    assert [c[0] for c in cs] == ["GEN8", "STRG", "CODE", "AUDO"]
    assert len(novo) % 4 == 0 and struct.unpack_from("<I", novo, 4)[0] == len(novo) - 8
    strs = _strings_de(novo)
    assert strs[3] == "Olá, viajante! Bem-vindo de volta ao lar." and strs[5] == "Aperte # para começar"
    assert [s for k, s in enumerate(strs) if k not in (3, 5)] == [s for k, s in enumerate(FRASES) if k not in (3, 5)]
    # o texto antigo continua no lugar (outros chunks podem apontar para ele direto)
    assert b"Hello, traveler! Welcome home." in novo
    # chunk CODE intacto
    code = next(c for c in cs if c[0] == "CODE")
    assert novo[code[1]:code[1] + code[2]] == b"\xAB" * 8
    # coleta de novo
    col2 = _coleta({"/data.win": novo})
    assert "Olá, viajante! Bem-vindo de volta ao lar." in {t.text for t in col2.textos}


def test_frase_repetida_grava_uma_vez():
    b = _data_win(["Good morning to you", "Good morning to you"])
    col = _coleta({"/data.win": b})
    out = col.rebuild({"/data.win|STRG|0": "Bom dia para você", "/data.win|STRG|1": "Bom dia para você"})["/data.win"]
    assert out.count("Bom dia para você".encode()) == 1
    assert _strings_de(out) == ["Bom dia para você"] * 2


def test_codigo_hash_protegido():
    col = _coleta({"/data.win": _data_win(FRASES)})
    t = next(t for t in col.textos if "Press" in t.text)
    from dc.traducao import ia
    _p, codes = ia.protect(t.text, t.codes)
    assert "#" in codes


def test_yyc_sem_frase_erro_e_com_frase_aviso():
    b = _data_win(["obj_player", "rm_title"], code_size=0)
    with pytest.raises(MotorError, match="YYC"):
        _coleta({"/data.win": b})
    b2 = _data_win(["obj_player", "A nice sentence here"], code_size=0)
    col = _coleta({"/data.win": b2})
    assert "YYC" in col.aviso and col.extra["yyc"] and len(col.textos) == 1


def test_form_tamanho_errado():
    b = _data_win(FRASES) + b"\0\0\0\0"
    with pytest.raises(MotorError, match="FORM"):
        _coleta({"/data.win": b})


def test_arquivos_idioma_ao_lado():
    d = _data_win(["obj_x"], code_size=0)
    en_json = json.dumps({"menu": {"start": "Start the game now", "id": "btn_start"}, "list": ["Go back home", 3]},
                         indent=2).encode()
    csv = ('key;en;fr\n'
           'greet;"Hello there, friend";"Bonjour, ami"\n'
           'bye;Goodbye my friend;Au revoir\n'
           'id;btn_ok;btn_ok\n').encode("utf-8-sig")
    ini = b"[Text]\nTitle=The Lost Kingdom\nKey=menu_key\n"
    arqs = {"/data.win": d, "/lang/en.json": en_json, "/lang/fr.json": b'{"a": "Bonjour le monde"}',
            "/text/dialog.csv": csv, "/lang/english.ini": ini, "/options.ini": b"[Windows]\nVsync = true and more\n"}
    assert sorted(gm.arquivos_idioma(list(arqs))) == ["/lang/en.json", "/lang/english.ini", "/text/dialog.csv"]
    col = _coleta(arqs)
    by = {t.id: t.text for t in col.textos}
    assert set(by.values()) == {"Start the game now", "Go back home", "Hello there, friend", "Goodbye my friend",
                                "The Lost Kingdom"}
    assert "YYC" in col.aviso
    tr = {k: {"Start the game now": "Começar o jogo agora", "Go back home": "Voltar \"para\" casa",
              "Hello there, friend": "Olá, amigo; tudo bem", "Goodbye my friend": "Tchau, meu amigo",
              "The Lost Kingdom": "O Reino\nPerdido"}[v] for k, v in by.items()}
    out = col.rebuild(tr)
    assert set(out) == {"/lang/en.json", "/text/dialog.csv", "/lang/english.ini"}
    j = json.loads(out["/lang/en.json"])
    assert j == {"menu": {"start": "Começar o jogo agora", "id": "btn_start"}, "list": ["Voltar \"para\" casa", 3]}
    assert out["/lang/en.json"].decode().startswith('{\n  "menu": {\n')  # formatação preservada
    c = out["/text/dialog.csv"]
    assert c.startswith(b"\xef\xbb\xbf")
    assert c.decode("utf-8-sig") == ('key;en;fr\n'
                                     'greet;"Olá, amigo; tudo bem";"Bonjour, ami"\n'
                                     'bye;"Tchau, meu amigo";Au revoir\n'
                                     'id;btn_ok;btn_ok\n')
    assert out["/lang/english.ini"] == b"[Text]\nTitle=O Reino Perdido\nKey=menu_key\n"
    arqs.update(out)
    by2 = {t.text for t in _coleta(arqs).textos}
    assert {"Começar o jogo agora", "Olá, amigo; tudo bem", "O Reino Perdido"} <= by2


def test_csv_sem_coluna_en_ignorado():
    arqs = {"/data.win": _data_win(["Some phrase here"]), "/lang/strings_en.csv": b"a,b\nHello world,Other thing\n"}
    col = _coleta(arqs)
    assert all(t.id.startswith("/data.win") for t in col.textos)


def test_sem_form():
    with pytest.raises(MotorError, match="FORM"):
        _coleta({"/data.win": b"XXXX" + b"\0" * 12})
