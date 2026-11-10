"""Segunda chance da tradução: códigos perdidos pela IA (remonta) e frase que não cabe na caixa (encurta)."""
import json
import re

from dc.paths import get_paths
from dc.traducao import ia, switch
from dc.traducao import trinity_game as tg


def _prov(name, answer, single=False):
    """Provedor falso: answer(system, user) -> texto."""
    def http(url, body, headers, timeout):
        msgs = body["messages"]
        return {"message": {"content": answer(msgs[0]["content"], msgs[-1]["content"])}}
    spec = {"tipo": "ollama", "url": "http://x", "modelo": "translategemma" if single else "qwen", "gratis": True}
    return ia.Provider(name, spec, "", http)


def _cfg(tmp_path):
    paths = get_paths(tmp_path / "dc").ensure()
    return paths, ia.load_cfg(paths)


def test_fix_codes_smart_ai_moves_markers(tmp_path):
    paths, cfg = _cfg(tmp_path)
    smart = _prov("pc", lambda s, u: "O ⟦2⟧ do ⟦1⟧ selvagem derreteu o gelo!")
    out, how = ia.fix_codes(paths, cfg, [ia.Item("a", "The wild ⟦1⟧’s ⟦2⟧ melted the ice!")], chain=[smart])
    assert out == {"a": "O ⟦2⟧ do ⟦1⟧ selvagem derreteu o gelo!"} and how == {"a": "ia"}


def test_fix_codes_falls_back_to_pieces_keeping_order(tmp_path):
    paths, cfg = _cfg(tmp_path)
    pieces = {"The wild": "O selvagem", "melted the ice!": "derreteu o gelo!"}

    def mt(system, user):  # tradutor que sempre perde os códigos numa frase inteira
        return pieces.get(user, "texto sem códigos")
    out, how = ia.fix_codes(paths, cfg, [ia.Item("a", "⟦0⟧The wild ⟦1⟧ ⟦2⟧ melted the ice!")],
                            chain=[_prov("mt", mt, single=True)])
    assert out["a"] == "⟦0⟧O selvagem ⟦1⟧ ⟦2⟧ derreteu o gelo!" and how["a"] == "pedaços"
    assert ia.placeholders_ok("⟦0⟧The wild ⟦1⟧ ⟦2⟧ melted the ice!", out["a"])


def test_fix_codes_gives_up_without_breaking(tmp_path):
    paths, cfg = _cfg(tmp_path)
    bad = _prov("x", lambda s, u: "⟦9⟧ lixo")
    out, _ = ia.fix_codes(paths, cfg, [ia.Item("a", "Hi ⟦0⟧!")], chain=[bad])
    assert out == {}


def test_shorten_only_accepts_what_fits(tmp_path):
    paths, cfg = _cfg(tmp_path)
    smart = _prov("pc", lambda s, u: "Curto ⟦0⟧." if "⟦0⟧" in u else "ainda muito muito longo")
    got = ia.shorten(paths, cfg, [("a", "Texto bem longo ⟦0⟧ demais", 1, 20), ("b", "Outro longo demais", 1, 10)],
                     fits=lambda iid, t: len(t) <= 12, chain=[smart])
    assert got == {"a": "Curto ⟦0⟧."}


def test_second_chance_on_description_that_overflows(tmp_path):
    """Descrição de item (sem caixas) de 2 linhas: tradução de 3 linhas é encurtada e passa a caber."""
    paths, cfg = _cfg(tmp_path)
    text = "A spray-type medicine. It\nrestores 20 HP to a Pokémon."
    all_texts = {"f#0": ("f", 0, text, [])}
    long_pt = ("Um remédio em spray que restaura vinte pontos de saúde de um único Pokémon do seu time inteiro, "
               "na hora, em qualquer lugar.")
    assert not tg.layout(text, [], long_pt)[2]
    res = ia.Result(translated={"f#0": long_pt})
    rep = switch.Report("x")
    smart = _prov("pc", lambda s, u: "Remédio em spray. Restaura\n20 PS de um Pokémon.")
    tg.second_chance(paths, cfg, [ia.Item("f#0", text)], all_texts, res, rep, {}, [smart], "job")
    assert rep.shortened == 1 and tg.layout(text, [], res.translated["f#0"])[2]
    # cache: segunda vez não chama a IA
    res2 = ia.Result(translated={"f#0": long_pt})
    boom = _prov("pc", lambda s, u: (_ for _ in ()).throw(AssertionError("chamou a IA")))
    tg.second_chance(paths, cfg, [ia.Item("f#0", text)], all_texts, res2, switch.Report("x"), {}, [boom], "job")
    assert res2.translated["f#0"] == res.translated["f#0"]
    memo = json.loads((paths.data / "traducao/cache/job-segunda-chance.json").read_text("utf-8"))
    assert any(k.startswith("s") for k in memo)


def test_second_chance_rescues_lost_codes(tmp_path):
    paths, cfg = _cfg(tmp_path)
    text = "\x00The wild \x00 melted the ice!"
    codes = [(0xBE, 1, 1), (0xBE, 1, 2)]
    all_texts = {"f#0": ("f", 0, text, codes)}
    item = ia.Item("f#0", tg.to_marked(text))
    res = ia.Result(flagged={"f#0": "a IA perdeu/inventou códigos do jogo — mantido o original"})
    rep = switch.Report("x")
    smart = _prov("pc", lambda s, u: "⟦0⟧O ⟦1⟧ selvagem derreteu o gelo!")
    tg.second_chance(paths, cfg, [item], all_texts, res, rep, {}, [smart], "job2")
    assert rep.rescued == 1 and "f#0" not in res.flagged
    assert re.search("selvagem", res.translated["f#0"])
    assert "2ª chance: 1 frases com códigos refeitas" in rep.text()


def test_shorten_batches_then_single_for_the_rest(tmp_path):
    paths, cfg = _cfg(tmp_path)
    calls = []

    def ans(system, user):
        calls.append(user)
        if user.startswith("{"):
            d = json.loads(user)
            return json.dumps({k: ("curto" if k == "a" else "ainda longo demais") for k in d})
        return "curto b"
    got = ia.shorten(paths, cfg, [("a", "longo a", 1, 10), ("b", "longo b", 1, 10)],
                     fits=lambda iid, t: len(t) <= 10, chain=[_prov("pc", ans)])
    assert got == {"a": "curto", "b": "curto b"}
    assert len(calls) == 2  # 1 lote + 1 individual
