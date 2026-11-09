"""Luigi's Mansion 3: tabela de textos e init.patch da Next Level Games (sem precisar do jogo)."""
import struct
import zlib

import pytest

from dc.traducao import ia, lm3, nlg


def _table(locale, strings, ids=None, tail=b""):
    ids = ids or list(range(100, 100 + len(strings)))
    out = bytearray(struct.pack("<III", locale, len(strings), 0))
    pos, body = 0, b""
    for i, s in enumerate(strings):
        out += struct.pack("<II", ids[i], pos)
        enc = s.encode("utf-16-le") + b"\0\0"
        body += enc
        pos += len(enc) // 2
    return bytes(out) + body + tail


EN = ["[tp:0.03]Welcome to [clr:FFE98B]The Last Resort[/clr]![tp:0.3] [/tp][p]Are you ready to check in?[/tp]",
      "OK", "{0} Save", "Close the team?[p]Doing so will make the team[p]invisible to new players.",
      "[tp:0.03]You won't find [clr:FE7388]Toad[/clr] in such a place.[tp:0.3] [/tp][p]Hurry up![/tp]"]
JA = ["ようこそ", "OK", "{0} セーブ", "チーム", "キノピオ"]   # U+3000 etc.: terminador precisa estar alinhado


def _patch(tables):
    sec5 = b"".join(tables)
    pre = b"\x11" * 200
    sections = [64, 64, 64, 64, 64, 64 + len(pre)] + [64 + len(pre) + len(sec5)] * 10
    blob = struct.pack("<16I", *sections) + pre + sec5 + b"\x22" * 50
    stream = zlib.compress(blob, 9)
    head = bytearray(b"UUU\x01" + struct.pack("<IIII", 0, 0, len(stream), len(blob)) + b"\xab" * 40)
    struct.pack_into("<I", head, 8, len(head))
    return bytes(head) + stream


def _ten_tables():
    t = []
    for loc in range(10):
        t.append(_table(loc, JA if loc == 1 else EN))
    return t


def test_tabela_le_e_regrava_identica():
    raw = _table(0, EN, tail=b"\0\0\0\0")
    t = nlg.read_table(raw)
    assert t.strings == EN and t.tail == b"\0\0\0\0"
    assert nlg.write_table(t) == raw


def test_tabela_japonesa_terminador_alinhado():
    raw = _table(1, ["A　B", "x"])  # 'A' = 41 00, U+3000 = 00 30 -> "00 00" desalinhado
    assert nlg.read_table(raw).strings == ["A　B", "x"]


def test_tabela_frase_compartilhada():
    raw = bytearray(_table(0, ["um", "dois"]))
    struct.pack_into("<II", raw, 12 + 8, 7, 0)  # segunda entrada aponta para a primeira frase
    raw = bytes(raw[:12 + 16]) + "um".encode("utf-16-le") + b"\0\0"
    t = nlg.read_table(raw)
    assert t.shared == {1: 0} and t.strings == ["um", "um"]
    assert nlg.write_table(t) == raw


def test_tabela_com_tamanho_fixo():
    raw = _table(0, EN)
    t = nlg.read_table(raw)
    t.strings[1] = "Ok"
    assert len(nlg.write_table(t, len(raw))) == len(raw)
    t.strings[1] = "x" * 400
    with pytest.raises(nlg.TableError):
        nlg.write_table(t, len(raw))


def test_patch_selfcheck_e_regravacao_identica():
    raw = _patch(_ten_tables())
    ok, why = nlg.selfcheck_patch(raw)
    assert ok, why
    p = nlg.read_patch(raw)
    assert len(nlg.section_tables(p)) == 10
    assert nlg.write_patch(p) == raw


def test_patch_troca_tabela_sem_mudar_tamanho():
    raw = _patch(_ten_tables())
    p = nlg.read_patch(raw)
    spans = nlg.section_tables(p)
    t = nlg.get_table(p, 0)
    t.strings[1] = "Ok"
    nlg.put_table(p, 0, t)
    out = nlg.write_patch(p)
    q = nlg.read_patch(out)
    assert nlg.section_tables(q) == spans and len(q.blob) == len(p.blob)
    assert nlg.get_table(q, 0).strings[1] == "Ok" and nlg.get_table(q, 9).strings == EN
    assert out[:8] == raw[:8] and out[16:nlg.struct.unpack_from("<I", raw, 8)[0]] == \
        raw[16:nlg.struct.unpack_from("<I", raw, 8)[0]]


def test_patch_invalido():
    with pytest.raises(nlg.PatchError):
        nlg.read_patch(b"XXXX" + b"\0" * 40)
    raw = bytearray(_patch(_ten_tables()))
    raw[-3] ^= 0xFF
    assert not nlg.selfcheck_patch(bytes(raw))[0]


def test_prepare_e_quebras():
    s = EN[0]
    pr = lm3.prepare(s)
    assert pr.prefix == "[tp:0.03]" and pr.suffix == "[/tp]"
    assert "⟦" in pr.core and "[" not in pr.core
    # tradução "identidade": conteúdo igual (só as quebras [p] podem mudar de lugar)
    out, fits = lm3.finish(pr, pr.core)
    assert out.replace("[p]", " ").split() == s.replace("[p]", " ").split() and fits
    # a pausa "[tp:0.3] [/tp]" nunca é cortada por quebra de linha
    for s in EN:
        pr = lm3.prepare(s)
        out, _ = lm3.finish(pr, pr.core)
        assert "[tp:0.3][p]" not in out
        assert "[tp:0.3] [/tp]" in out or "[tp:0.3]" not in s


def test_quebra_intencional_fica():
    pr = lm3.prepare(EN[3])
    assert "[p]" not in pr.core and "⟦" in pr.core  # quebra depois de '?' virou código protegido
    out, _ = lm3.finish(pr, pr.core)
    assert out.startswith("Close the team?[p]")


def test_wrap_respeita_largura():
    out, fits = lm3.wrap("uma frase bem comprida que precisa quebrar em linhas", 20, 3)
    assert all(len(x) <= 20 for x in out.split("[p]")) and fits
    _, fits = lm3.wrap("palavra " * 30, 10, 2)
    assert not fits


def _fake_http(url, body, headers, timeout):
    import json
    user = body["messages"][-1]["content"]

    def tr(v):
        return v.replace("Welcome", "Bem-vindo").replace("Hurry up", "Corra").replace("Save", "Salvar").replace("Are you ready to check in?", "Pronto?")
    try:
        content = json.dumps({k: tr(v) for k, v in json.loads(user).items()}, ensure_ascii=False)
    except ValueError:
        content = tr(user)
    return {"choices": [{"message": {"content": content}}], "usage": {"total_tokens": 10},
            "message": {"content": content}, "eval_count": 5, "prompt_eval_count": 5}


def test_traducao_ponta_a_ponta(tmp_path):
    from dc.paths import get_paths
    paths = get_paths(tmp_path).ensure()
    cfg = ia.load_cfg(paths)
    chain = [ia.Provider("ollama", {**cfg["providers"]["ollama"], "modelo": "qwen"}, "", _fake_http)]
    raw = _patch(_ten_tables())
    pf = tmp_path / "init.patch"
    pf.write_bytes(raw)
    rep = lm3.translate_game(paths, "0100DCA0064A6000", pf, chain=chain, install=False)
    assert rep.translated >= 2 and rep.selfcheck, rep.text()
    out = paths.data / "traducao" / "mods" / "0100DCA0064A6000" / "romfs" / "init.patch"
    q = nlg.read_patch(out.read_bytes())
    t0, t1 = nlg.get_table(q, 0), nlg.get_table(q, 1)
    assert any("Bem-vindo" in s for s in t0.strings) and any("Bem-vindo" in s for s in nlg.get_table(q, 9).strings)
    assert t1.strings == JA  # outros idiomas intocados
    assert len(q.blob) == len(nlg.read_patch(raw).blob)
    for s in t0.strings:  # códigos do jogo preservados
        assert s.count("[clr:") == s.count("[/clr]")


def test_espaco_insuficiente_volta_ao_ingles():
    t = nlg.read_table(_table(0, ["abc", "defg"]))
    originals = list(t.strings)
    budget = t.size()
    rev = lm3._fit(t, originals, {0: "abcdefghij", 1: "de"}, budget)
    assert rev == 1 and t.strings == ["abc", "de"] and t.size() <= budget


def test_lm3_suportado():
    assert lm3.supported("0100dca0064a6000") and not lm3.supported("0100000000010000")
    assert ia.only_codes("⟦0⟧") is True
