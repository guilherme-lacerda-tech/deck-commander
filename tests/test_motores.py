"""Tradução por motor (Unity, GameMaker, ...): pergunta no Telegram com nº de frases e tempo; com o Sim, traduz."""
import re
import sys
import types

import pytest

from dc.traducao import comandos, ia, motores, run
from tests.test_traducao_bot import b  # noqa: F401 - fixture


def _fake_adapter(monkeypatch):
    mod = types.ModuleType("dc.traducao.eng_fake")
    mod.NAME = "Motor Teste"
    mod.detect = lambda paths: any(p.endswith(".fake") for p in paths)

    def collect(files, read):
        txt = read("/a.fake").decode()
        lines = txt.split("\n")

        def rebuild(tr):
            return {"/a.fake": "\n".join(tr.get(str(i), l) for i, l in enumerate(lines)).encode()}
        return motores.Coleta([motores.Texto(str(i), l) for i, l in enumerate(lines)], rebuild)
    mod.collect = collect
    monkeypatch.setitem(sys.modules, "dc.traducao.eng_fake", mod)
    monkeypatch.setattr(motores, "ADAPTADORES", ("eng_fake",))
    return mod


def test_unique_texts_skips_numbers_and_dedupes():
    col = motores.Coleta([motores.Texto("1", "Hello there"), motores.Texto("2", "Hello there"),
                          motores.Texto("3", "123"), motores.Texto("4", "<b>")], lambda t: {})
    u = motores.unique_texts(col)
    assert list(u) == ["Hello there"] and len(u["Hello there"]) == 2


def test_estimate_and_format():
    assert motores.estimate_minutes(400, {"fallback": ["ollama_pc"]}) == 10
    assert motores.estimate_minutes(80, {}) == 10
    assert motores.fmt_minutes(5) == "~5 min" and motores.fmt_minutes(125) == "~2 h 05 min"


def test_translate_keeps_codes_and_rebuilds(monkeypatch):
    src = r"Hello \C[2]friend\C[0]!"
    col = motores.Coleta([motores.Texto("a", src), motores.Texto("b", src)], lambda tr: {"/x": tr})
    seen = []

    def fake(paths, cfg, items, job, glossary=None, chain=None, progress=None, should_pause=None, **k):
        seen.extend(i.text for i in items)
        return types.SimpleNamespace(translated={i.id: i.text.replace("Hello", "Olá").replace("friend", "amigo")
                                                 for i in items})
    monkeypatch.setattr(ia, "translate", fake)
    monkeypatch.setattr(ia, "load_glossary", lambda *a: {})
    files, _res, n = motores.translate(None, {}, col, "j", "T")
    assert len(seen) == 1 and "C[2]" not in seen[0]  # código escondido da IA, frase repetida vai 1 vez
    assert n == 2 and files["/x"] == {"a": r"Olá \C[2]amigo\C[0]!", "b": r"Olá \C[2]amigo\C[0]!"}


def test_install_writes_layeredfs(tmp_path):
    out = motores.install({"/Data/x.json": b"{}"}, tmp_path / "romfs")
    assert out[0].read_bytes() == b"{}" and out[0] == tmp_path / "romfs" / "Data" / "x.json"


def test_engine_game_asks_with_estimate_then_runs_on_yes(b, monkeypatch, tmp_path):  # noqa: F811
    _fake_adapter(monkeypatch)
    from dc.traducao import nca, switch

    class _Rfs:
        data = b"Hello world\nGoodbye world\n42"

        def files(self):
            return {"/a.fake": (0, len(self.data))}

        def read_at(self, o, n):
            return self.data[o:o + n]
    monkeypatch.setattr(switch, "keys_path", lambda: tmp_path / "prod.keys")
    monkeypatch.setattr(nca, "load_keys", lambda p: {})
    monkeypatch.setattr(nca, "open_romfs", lambda rom, keys, upd=None: (_Rfs(), []))
    monkeypatch.setattr(run, "_translate_unreal", lambda *a, **k: None)
    from dc.traducao import lm3, portugues
    monkeypatch.setattr(lm3, "supported", lambda tid: False)
    monkeypatch.setattr(portugues, "detect_switch", lambda *a, **k: {})
    monkeypatch.setattr(switch, "mod_target", lambda tid: tmp_path / "mods" / tid)

    def fake(paths, cfg, items, job, glossary=None, chain=None, progress=None, should_pause=None, **k):
        r = types.SimpleNamespace(translated={i.id: i.text.replace("world", "mundo") for i in items},
                                  provider_used="ollama_pc", errors=[])
        return r
    monkeypatch.setattr(ia, "translate", fake)
    monkeypatch.setattr(ia, "build_chain", lambda *a, **k: ["x"])
    asked = []
    b.send = lambda chat, text, buttons=None: asked.append((text, buttons))
    b.handle(1, 1, "/traduzir jogo")
    op = b.spawned[0]
    job = run.run(b.paths, op)
    assert job["status"] == "aguardando ok" and job["oferta"]["frases"] == 2
    comandos.notify(b)
    text, buttons = asked[-1]
    assert "Motor Teste" in text and "2 frases" in text and "tempo estimado" in text
    assert buttons == [("Sim", f"/traduzir motor {op} sim"), ("Não", f"/traduzir motor {op} nao")]
    comandos.notify(b)
    assert len(asked) == 1  # pergunta uma vez só
    r = b.handle(1, 1, "Sim")
    assert "Começou" in r and b.spawned[-1] == op
    job = run.run(b.paths, op)
    assert job["status"] == "concluido", job["report"]
    out = (tmp_path / "mods" / "0100ABCD12340000" / "romfs" / "a.fake").read_text()
    assert out == "Hello mundo\nGoodbye mundo\n42"


def test_engine_no_keeps_game(b, monkeypatch):  # noqa: F811
    job = run.create(b.paths, b.store, "translate_switch", "switch-jogo", "Jogo", {})
    job.update(status="aguardando ok", oferta={"motor": "Unity", "frases": 10, "minutos": 1})
    run.save_job(b.paths, job)
    assert "fica como está" in b.handle(1, 1, f"/traduzir motor {job['op']} nao")
    assert run.load_job(b.paths, job["op"])["status"] == "recusado" and b.spawned == []


def test_translate_keeps_leading_and_trailing_space(monkeypatch):
    col = motores.Coleta([motores.Texto("a", "  Just like I will stop Him.\n")], lambda tr: {"/x": tr})
    monkeypatch.setattr(ia, "translate", lambda paths, cfg, items, job, glossary=None, **k: types.SimpleNamespace(
        translated={i.id: "Assim como eu vou detê-Lo." for i in items}))
    monkeypatch.setattr(ia, "load_glossary", lambda *a: {})
    files, _r, n = motores.translate(None, {}, col, "j", "T")
    assert files["/x"]["a"] == "  Assim como eu vou detê-Lo.\n"
