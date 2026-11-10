"""RPG Maker MV/MZ: JSON sintéticos no formato do editor (sem jogo de verdade)."""
import json

import pytest

from dc.traducao import eng_rpgmaker as rm
from dc.traducao import motores
from dc.traducao.motores import MotorError


def _c(x):
    return json.dumps(x, ensure_ascii=False, separators=(",", ":"))


def _cmd(code, params, indent=0):
    return {"code": code, "indent": indent, "parameters": params}


MAPA = {
    "displayName": "Old Forest",
    "events": [None, {"id": 1, "name": "EV001", "pages": [{"list": [
        _cmd(101, ["Actor1", 0, 0, 2, "Harold"]),
        _cmd(401, ["\\C[2]Harold\\C[0]: Hello there,"]),
        _cmd(401, ["how are you, \\N[1]?"]),
        _cmd(102, [["Fine, thanks", "Go away"], 1, 0, 2, 0]),
        _cmd(402, [0, "Fine, thanks"]),
        _cmd(401, ["Good to hear!\\!"], 1),
        _cmd(0, [], 1),
        _cmd(404, []),
        _cmd(320, [1, "Hero"]),
        _cmd(405, ["Long ago there was"]),
        _cmd(405, ["a kingdom."]),
        _cmd(0, []),
    ]}]}],
}
SISTEMA = {"gameTitle": "My Game", "currencyUnit": "G",
           "armorTypes": ["", "General Armor"], "weaponTypes": ["", "Dagger"], "skillTypes": ["", "Magic"],
           "elements": ["", "Physical"], "equipTypes": ["", "Weapon"],
           "terms": {"basic": ["Level", "Lv"], "commands": ["Fight", "Escape", None],
                     "params": ["Max HP"], "messages": {"actorDamage": "%1 took %2 damage!", "victory": "%1 was victorious!"}}}
ITENS = [None, {"id": 1, "name": "Potion", "description": "Restores 500 HP.\nTastes bad.", "iconIndex": 176},
         {"id": 2, "name": "", "description": ""}]


def _arquivos():
    itens_txt = "[\n" + ",\n".join(_c(x) for x in ITENS) + "\n]"
    return {
        "/www/data/Map001.json": _c(MAPA).encode(),
        "/www/data/System.json": _c(SISTEMA).encode(),
        "/www/data/Items.json": itens_txt.encode(),
        "/www/data/MapInfos.json": b"[null]",
        "/www/js/plugins.js": b"var $plugins = [];",
    }


def _coleta(arqs=None):
    arqs = arqs or _arquivos()
    return rm.collect({p: (0, len(b)) for p, b in arqs.items()}, lambda p: arqs[p])


def test_detect():
    assert rm.detect(["/www/data/Map001.json", "/www/index.html"])
    assert rm.detect(["/data/System.json"])
    assert rm.detect(["/Data/Map001.rvdata2"])
    assert not rm.detect(["/www/data/Foo.txt", "/Data/Something.json"])
    assert motores.adapter_for(["/www/data/Map001.json"]) is rm


def test_collect_ids_e_textos():
    col = _coleta()
    by = {t.id: t.text for t in col.textos}
    assert by["Map001.json|events/1/pages/0/list/1/parameters/0"] == "\\C[2]Harold\\C[0]: Hello there,\nhow are you, \\N[1]?"
    assert by["Map001.json|events/1/pages/0/list/3/parameters/0/0"] == "Fine, thanks"
    assert by["Map001.json|events/1/pages/0/list/4/parameters/1"] == "Fine, thanks"
    assert by["Map001.json|events/1/pages/0/list/0/parameters/4"] == "Harold"
    assert by["Map001.json|events/1/pages/0/list/8/parameters/1"] == "Hero"
    assert by["Map001.json|events/1/pages/0/list/9/parameters/0"] == "Long ago there was\na kingdom."
    assert by["Map001.json|displayName"] == "Old Forest"
    assert by["System.json|terms/messages/actorDamage"] == "%1 took %2 damage!"
    assert by["System.json|weaponTypes/1"] == "Dagger"
    assert by["Items.json|1/description"] == "Restores 500 HP.\nTastes bad."
    assert "My Game" not in by.values() and "G" not in by.values()
    assert not any(t.id.startswith("MapInfos") for t in col.textos)
    assert all(t.codes is rm.CODES_RPGM for t in col.textos)


def test_codigos_protegidos():
    from dc.traducao import ia
    s = "\\C[2]Harold\\C[0]: Hi \\N[1]\\! \\{big\\} 100\\G %1\nx"
    p, codes = ia.protect(s, rm.CODES_RPGM)
    for c in ("\\C[2]", "\\C[0]", "\\N[1]", "\\!", "\\{", "\\}", "\\G", "%1", "\n"):
        assert c in codes
    assert ia.restore(p, codes) == s


def test_roundtrip_e_linhas_redistribuidas():
    col = _coleta()
    msg = "Map001.json|events/1/pages/0/list/1/parameters/0"
    trads = {
        msg: "\\C[2]Harold\\C[0]: Olá, como vai você, \\N[1]? Faz tempo que não te vejo por aqui na floresta",
        "Map001.json|events/1/pages/0/list/3/parameters/0/0": "Bem, obrigado",
        "Map001.json|events/1/pages/0/list/4/parameters/1": "Bem, obrigado",
        "Map001.json|events/1/pages/0/list/9/parameters/0": "Há muito tempo\nhavia\num reino.",
        "Map001.json|displayName": "Floresta Velha",
        "System.json|terms/messages/actorDamage": "%1 sofreu %2 de dano!",
        "Items.json|1/description": "Recupera 500 HP.\nGosto ruim.",
    }
    out = col.rebuild(trads)
    assert set(out) == {"/www/data/Map001.json", "/www/data/System.json", "/www/data/Items.json"}
    mapa = json.loads(out["/www/data/Map001.json"])
    lst = mapa["events"][1]["pages"][0]["list"]
    assert len(lst) == len(MAPA["events"][1]["pages"][0]["list"])  # nenhum comando novo
    assert lst[1]["parameters"][0].startswith("\\C[2]Harold\\C[0]: Olá")
    assert lst[2]["parameters"][0] and "\\N[1]" in lst[1]["parameters"][0] + lst[2]["parameters"][0]
    assert [lst[9]["parameters"][0], lst[10]["parameters"][0]] == ["Há muito tempo", "havia um reino."]
    assert lst[5]["parameters"][0] == "Good to hear!\\!"  # não traduzido fica igual
    # estilo do editor: compacto, sem escapar acento; banco de dados com um item por linha
    assert b"Ol\xc3\xa1" in out["/www/data/Map001.json"] and b'": ' not in out["/www/data/Map001.json"]
    assert out["/www/data/Items.json"].startswith(b"[\nnull,\n{")
    # coleta de novo enxerga o texto novo
    arqs = _arquivos()
    arqs.update(out)
    by = {t.id: t.text for t in _coleta(arqs).textos}
    assert by["Map001.json|displayName"] == "Floresta Velha"
    assert by["System.json|terms/messages/actorDamage"] == "%1 sofreu %2 de dano!"
    assert by["Map001.json|events/1/pages/0/list/9/parameters/0"] == "Há muito tempo\nhavia um reino."
    assert by["Items.json|1/description"] == "Recupera 500 HP.\nGosto ruim."


def test_arquivo_sem_traducao_nao_muda_bytes():
    arqs = _arquivos()
    col = _coleta(arqs)
    out = col.rebuild({"System.json|weaponTypes/1": "Dagger"})
    assert out["/www/data/System.json"] == arqs["/www/data/System.json"]


def test_escolha_nao_ganha_quebra_de_linha():
    col = _coleta()
    out = col.rebuild({"Map001.json|events/1/pages/0/list/3/parameters/0/1": "Vai\nembora"})
    lst = json.loads(out["/www/data/Map001.json"])["events"][1]["pages"][0]["list"]
    assert lst[3]["parameters"][0] == ["Fine, thanks", "Vai embora"]


def test_distribuir():
    assert rm.distribuir("a\nb\nc\nd", ["x", "y"]) == ["a", "b c d"]
    assert rm.distribuir("um dois tres quatro cinco seis", ["123456789012", "123456789012"]) == \
        ["um dois tres quatro", "cinco seis"]
    linhas = rm.distribuir("palavra " * 12, ["x" * 20, "x" * 20, "x" * 20])
    assert len(linhas) == 3 and all(linhas)
    assert rm.distribuir("só", ["a", "b"]) == ["só", ""]


def test_rvdata2_sozinho_erro_claro():
    arqs = {"/Data/Map001.rvdata2": b"\x04\x08", "/Data/System.rvdata2": b"\x04\x08"}
    assert rm.detect(list(arqs))
    with pytest.raises(MotorError, match="rvdata2"):
        rm.collect({p: (0, 2) for p in arqs}, lambda p: arqs[p])


def test_rvdata2_junto_vira_aviso():
    arqs = _arquivos()
    arqs["/www/data/Old.rvdata2"] = b"\x04\x08"
    assert "rvdata2" in _coleta(arqs).aviso


def test_json_ilegivel():
    arqs = {"/www/data/Map001.json": b"\x89\x00garbage"}
    with pytest.raises(MotorError, match="JSON"):
        rm.collect({p: (0, 1) for p in arqs}, lambda p: arqs[p])
