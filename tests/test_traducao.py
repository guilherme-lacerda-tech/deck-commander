"""Adições A1/A2/A3: motor de IA, formatos do Switch, mod LayeredFS, retrô (Meowth simulado), /converter."""
import json
import os
import struct
from pathlib import Path

import pytest

from dc import patches
from dc.paths import get_paths
from dc.traducao import converter, ia, nx, retro, switch


# ============================================================ helpers: MSBT/SARC sintéticos
def make_msbt(strings: list[list], labels: list[str], endian="<") -> bytes:
    """Monta um MSBT UTF-16 real: header + LBL1 + ATR1 + TXT2 (strings = pedaços str/bytes de tag)."""
    e = endian
    enc = "utf-16-le" if e == "<" else "utf-16-be"

    def sec(magic, body):
        return magic + struct.pack(e + "I", len(body)) + b"\x00" * 8 + body + b"\xab" * ((16 - len(body) % 16) % 16)
    lbl = struct.pack(e + "I", 1) + struct.pack(e + "II", len(labels), 12)
    for i, l in enumerate(labels):
        lbl += bytes([len(l)]) + l.encode() + struct.pack(e + "I", i)
    blobs = []
    for parts in strings:
        b = b"".join(p if isinstance(p, bytes) else p.encode(enc) for p in parts) + b"\x00\x00"
        blobs.append(b)
    offs, o = [], 4 + 4 * len(blobs)
    for b in blobs:
        offs.append(o); o += len(b)
    txt = struct.pack(e + "I", len(blobs)) + struct.pack(e + f"{len(blobs)}I", *offs) + b"".join(blobs)
    atr = struct.pack(e + "II", len(blobs), 0)
    body = sec(b"LBL1", lbl) + sec(b"ATR1", atr) + sec(b"TXT2", txt)
    head = bytearray(b"MsgStdBn" + (b"\xff\xfe" if e == "<" else b"\xfe\xff") + b"\x00\x00" + bytes([1, 3])
                     + struct.pack(e + "H", 3) + b"\x00\x00" + struct.pack(e + "I", 0) + b"\x00" * 10)
    out = bytearray(head + body)
    struct.pack_into(e + "I", out, 0x12, len(out))
    return bytes(out)


def tag(group=0, typ=3, params=b"\x01\x00", e="<") -> bytes:
    return struct.pack(e + "HHHH", 0x0E, group, typ, len(params)) + params


class FakeAI:
    """Provedor falso: 'traduz' acrescentando [pt] e respeita/perde marcadores conforme pedido."""
    def __init__(self, lose=(), fail=False):
        self.calls, self.lose, self.fail = 0, set(lose), fail

    def __call__(self, url, body, headers, timeout):
        self.calls += 1
        if self.fail:
            raise ia.ProviderError("HTTP 429")
        user = body["messages"][-1]["content"]
        try:
            d = json.loads(user)
            out = {k: ("" if k in self.lose else "PT " + v) for k, v in d.items()}
            out = {k: (v.replace("⟦0⟧", "") if k in self.lose else v) for k, v in out.items()}
            content = json.dumps(out, ensure_ascii=False)
        except ValueError:
            content = "PT " + user
        if "/api/chat" in url:
            return {"message": {"content": content}, "prompt_eval_count": 10, "eval_count": 5}
        return {"choices": [{"message": {"content": content}}], "usage": {"total_tokens": 15}}


def cfg_with(paths, **kw):
    cfg = ia.load_cfg(paths)
    cfg.update(kw)
    return cfg


# ============================================================ motor de IA
def test_protect_restore_and_only_codes():
    import re
    pat = re.compile(r"\[[^\]]+\]|\\n")
    p, codes = ia.protect(r"Oi [PLAYER]!\nTudo bem?", pat)
    assert p == "Oi ⟦0⟧!⟦1⟧Tudo bem?" and ia.restore(p, codes) == r"Oi [PLAYER]!\nTudo bem?"
    assert ia.only_codes("⟦0⟧ 12!") and not ia.only_codes("⟦0⟧ Oi")
    assert ia.only_codes("pppppppppppppppp") and ia.only_codes("Item_Banana_01") and not ia.only_codes("DK!")
    assert not ia.only_codes("Help me!") and not ia.only_codes("Zips, Hops, and Swaps")
    assert ia.placeholders_ok("a ⟦0⟧ b ⟦1⟧", "⟦1⟧ x ⟦0⟧") and not ia.placeholders_ok("a ⟦0⟧", "a")


def test_translate_batch_cache_flags_and_fallback(tmp_path):
    paths = get_paths(tmp_path).ensure()
    cfg = cfg_with(paths, provider="index_translate", fallback=["ollama"])
    bad = FakeAI(fail=True)
    good = FakeAI(lose={"2"})
    chain = [ia.Provider("index_translate", cfg["providers"]["index_translate"], "", bad),
             ia.Provider("ollama", {**cfg["providers"]["ollama"], "modelo": "qwen"}, "", good)]
    items = [ia.Item("1", "Hello ⟦0⟧"), ia.Item("2", "Bye ⟦0⟧"), ia.Item("3", "⟦0⟧ 10")]
    res = ia.translate(paths, cfg, items, "job", chain=chain)
    assert res.translated["1"] == "PT Hello ⟦0⟧" and res.translated["3"] == "⟦0⟧ 10"  # só códigos: não vai p/ IA
    assert "2" in res.flagged and res.provider_used == "ollama" and any("index_translate" in e for e in res.errors)
    # retomar: o que já foi traduzido vem do cache, sem chamar a IA de novo
    good2 = FakeAI()
    chain2 = [ia.Provider("ollama", {**cfg["providers"]["ollama"], "modelo": "qwen"}, "", good2)]
    res2 = ia.translate(paths, cfg, items, "job", chain=chain2)
    assert res2.translated["1"] == "PT Hello ⟦0⟧" and good2.calls == 1  # só a frase que faltava


def test_translategemma_goes_one_by_one_and_glossary_review(tmp_path):
    paths = get_paths(tmp_path).ensure()
    cfg = ia.load_cfg(paths)
    ai = FakeAI()
    chain = [ia.Provider("ollama", cfg["providers"]["ollama"], "", ai)]
    res = ia.translate(paths, cfg, [ia.Item("a", "Pikachu attacks"), ia.Item("b", "Go")], "j2",
                       glossary={"Pikachu": "="}, chain=chain)
    assert ai.calls == 2 and res.translated["a"] == "PT Pikachu attacks" and not res.review
    res = ia.translate(paths, cfg, [ia.Item("c", "Potion here")], "j3", glossary={"Potion": "Poção"}, chain=chain)
    assert "c" in res.review  # traduziu, mas sem usar o termo do glossário


def test_paid_provider_respects_daily_limit(tmp_path):
    paths = get_paths(tmp_path).ensure()
    cfg = cfg_with(paths, limite_diario_tokens=10)
    ai = FakeAI()
    paid = ia.Provider("openai", {**cfg["providers"]["openai"], "lote": 1}, "sk-test", ai)
    ia.add_tokens(paths, 10)
    res = ia.translate(paths, cfg, [ia.Item("1", "Hello")], "j4", chain=[paid])
    assert ai.calls == 0 and "1" in res.flagged and any("limite" in e for e in res.errors)


def test_chain_skips_providers_without_key(tmp_path):
    paths = get_paths(tmp_path).ensure()
    cfg = cfg_with(paths, provider="openai", fallback=["github_models", "ollama"])
    assert [p.name for p in ia.build_chain(paths, cfg)] == ["ollama"]
    (paths.secrets / "github_pat").write_text("ghp_123456789")
    assert [p.name for p in ia.build_chain(paths, cfg)] == ["github_models", "ollama"]
    assert ia.mask("ghp_123456789") == "ghp_…89"


def test_ollama_down_is_skipped_quickly(tmp_path, monkeypatch):
    paths = get_paths(tmp_path).ensure()
    monkeypatch.setattr(ia, "_ollama_up", lambda spec: "11435" not in spec.get("url", ""))  # PC desligado
    cfg = cfg_with(paths, provider="index_translate", fallback=["ollama_pc", "ollama"])
    assert [p.name for p in ia.build_chain(paths, cfg)] == ["index_translate", "ollama"]


# ============================================================ formatos do Switch
def test_msbt_roundtrip_byte_identical_and_edit():
    raw = make_msbt([["Hello ", tag(), "!"], ["Second line"], [""]], ["L0", "L1", "L2"])
    m = nx.read_msbt(raw)
    assert nx.write_msbt(m) == raw  # ler+regravar sem mudar nada = idêntico
    texts = m.texts()
    assert texts[0][0] == "Hello ⟦0⟧!" and m.labels == {0: "L0", 1: "L1", 2: "L2"}
    m.set_text(0, "Olá ⟦0⟧!", texts[0][1])
    back = nx.read_msbt(nx.write_msbt(m))
    assert back.texts()[0] == ("Olá ⟦0⟧!", texts[0][1]) and back.texts()[1][0] == "Second line"


def test_msbt_big_endian_and_bad_input():
    raw = make_msbt([["A", tag(e=">"), "B"]], ["x"], endian=">")
    assert nx.write_msbt(nx.read_msbt(raw)) == raw
    with pytest.raises(nx.FormatError):
        nx.read_msbt(b"not msbt")


def test_sarc_and_yaz0_roundtrip():
    files = {"Msg/A.msbt": make_msbt([["Hi"]], ["a"]), "Font/x.bin": b"\x01" * 100}
    s = nx.Sarc("<", files, list(files), {n: 4 for n in files})
    data = nx.write_sarc(s)
    back = nx.read_sarc(data)
    assert back.files == files
    blob = (b"abcabcabc" * 500) + os.urandom(300)
    z = nx.yaz0_compress(blob)
    assert nx.yaz0_decompress(z) == blob and len(z) < len(blob)
    assert nx.unpack_layer("x.szs", z) == (blob, "yaz0")


def test_bffnt_direct_cmap():
    def font(lo, hi):
        cmap = b"CMAP" + struct.pack("<I", 8 + 16) + struct.pack("<IIHHI", lo, hi, 0, 0, 0)
        hdr = b"FFNT" + b"\xff\xfe" + struct.pack("<HIIH", 0x14, 0x04010000, 0, 1) + b"\x00\x00"
        return hdr + cmap
    full = nx.bffnt_chars(font(0x20, 0xFF))
    assert nx.missing_ptbr(full) == ""
    poor = nx.bffnt_chars(font(0x20, 0x7E))
    assert "ã" in nx.missing_ptbr(poor)


# ============================================================ A2: tradução Switch como mod
def _romfs(tmp_path, with_font=None):
    r = tmp_path / "romfs"
    (r / "Message/USen").mkdir(parents=True)
    (r / "Message/EUfr").mkdir(parents=True)
    (r / "Message/USen/Talk.msbt").write_bytes(make_msbt([["Hello ", tag(), "!"], ["Bye"]], ["t0", "t1"]))
    (r / "Message/EUfr/Talk.msbt").write_bytes(make_msbt([["Bonjour"]], ["t0"]))
    s = nx.Sarc("<", {"Menu.msbt": make_msbt([["Start"]], ["m0"])}, ["Menu.msbt"], {"Menu.msbt": 4})
    (r / "Message/USen/Menu.szs").write_bytes(nx.yaz0_compress(nx.write_sarc(s)))
    if with_font is not None:
        (r / "Font").mkdir()
        (r / "Font/main.bffnt").write_bytes(with_font)
    return r


def test_switch_translate_game_writes_mod_and_keeps_originals(tmp_path, monkeypatch):
    paths = get_paths(tmp_path / "dc").ensure()
    romfs = _romfs(tmp_path)
    before = {p: p.read_bytes() for p in romfs.rglob("*") if p.is_file()}
    monkeypatch.setattr(switch, "RYU_DIRS", [tmp_path / "Ryujinx"])
    (tmp_path / "Ryujinx").mkdir()
    cfg = ia.load_cfg(paths)
    chain = [ia.Provider("ollama", {**cfg["providers"]["ollama"], "modelo": "qwen"}, "", FakeAI())]
    rep = switch.translate_game(paths, "0100ABCD12340000", romfs, "Jogo", chain=chain)
    assert rep.applied and rep.msbt_count == 2 and rep.translated == 3 and rep.flagged == 0
    assert "yaz0" in rep.compression
    mod = tmp_path / "Ryujinx/mods/contents/0100abcd12340000" / switch.MOD_NAME / "romfs"
    m = nx.read_msbt((mod / "Message/USen/Talk.msbt").read_bytes())
    t0 = m.texts()[0]
    assert t0[0] == "PT Hello ⟦0⟧!" and t0[1] == [tag()]  # tag preservada byte a byte
    inner = nx.read_sarc(nx.yaz0_decompress((mod / "Message/USen/Menu.szs").read_bytes()))
    assert nx.read_msbt(inner.files["Menu.msbt"]).texts()[0][0] == "PT Start"
    assert not (mod / "Message/EUfr").exists()  # só o idioma de origem
    assert {p: p.read_bytes() for p in romfs.rglob("*") if p.is_file()} == before  # jogo intacto
    assert switch.uninstall_mod("0100ABCD12340000") and not mod.exists()


def test_switch_font_without_accents_blocks(tmp_path, monkeypatch):
    paths = get_paths(tmp_path / "dc").ensure()
    font = (b"FFNT\xff\xfe" + struct.pack("<HIIH", 0x14, 0x04010000, 0, 1) + b"\x00\x00"
            + b"CMAP" + struct.pack("<I", 24) + struct.pack("<IIHHI", 0x20, 0x7E, 0, 0, 0))
    romfs = _romfs(tmp_path, with_font=font)
    monkeypatch.setattr(switch, "RYU_DIRS", [tmp_path / "Ryujinx"])
    rep = switch.translate_game(paths, "0100ABCD12340000", romfs, chain=[])
    assert not rep.applied and any("fonte" in e for e in rep.errors) and "ã" in rep.font


def test_switch_reference_memory_is_used(tmp_path, monkeypatch):
    paths = get_paths(tmp_path / "dc").ensure()
    romfs = _romfs(tmp_path)
    ref = tmp_path / "ref/romfs/Message/USen"
    ref.mkdir(parents=True)
    (ref / "Talk.msbt").write_bytes(make_msbt([["Olá ", tag(), "!"], ["Tchau"]], ["t0", "t1"]))
    (paths.config / "referencias.toml").write_text(
        f'[[ref]]\ntitulo = "Jogo BR"\nconsole = "switch"\ntitle_id = "0100ABCD12340000"\n'
        f'original = "{romfs.as_posix()}"\ntraduzido = "{(tmp_path / "ref/romfs").as_posix()}"\n')
    monkeypatch.setattr(switch, "RYU_DIRS", [tmp_path / "Ryujinx"])
    cfg = ia.load_cfg(paths)
    ai = FakeAI()
    chain = [ia.Provider("ollama", {**cfg["providers"]["ollama"], "modelo": "qwen"}, "", ai)]
    rep = switch.translate_game(paths, "0100ABCD12340000", romfs, chain=chain)
    mod = Path(rep.mod_dir) / "romfs"
    assert nx.read_msbt((mod / "Message/USen/Talk.msbt").read_bytes()).texts()[1][0] == "Tchau"  # da referência
    assert rep.reference == "Jogo BR" and ai.calls == 1  # só o "Start" do menu foi para a IA


def test_pick_language():
    rels = ["Mals/USen.sarc", "Mals/EUfr.sarc", "Mals/JPja.sarc", "Font/a.bffnt"]
    assert switch.pick_language(rels) == ["Mals/USen.sarc", "Font/a.bffnt"]
    assert switch.pick_language(["Msg/a.msbt", "Msg/b.msbt"]) == ["Msg/a.msbt", "Msg/b.msbt"]


# ============================================================ A1: retrô (Meowth simulado)
def test_bps_create_roundtrip():
    src = bytes(range(256)) * 40
    tgt = bytearray(src); tgt[100:110] = b"X" * 10; tgt += b"extra"
    p = patches.create_bps(src, bytes(tgt))
    assert patches.apply_bps(src, p) == bytes(tgt)


def test_retro_translate_rom_with_fake_meowth(tmp_path, monkeypatch):
    paths = get_paths(tmp_path / "dc").ensure()
    rom = tmp_path / "roms/gba/Fire Red/Pokemon Fire Red.gba"
    rom.parent.mkdir(parents=True)
    rom.write_bytes(b"\x00" * 4096)
    data = {"tables": [{"category": "items", "entries": [{"id": "i1", "original": "Potion"}]}],
            "free_texts": [{"id": "f1", "original": "Hi [PLAYER]!\\nWant a Pokémon?"}]}

    def fake_extract(r, work, source="en"):
        work.mkdir(parents=True, exist_ok=True)
        return json.loads(json.dumps(data))

    def fake_run(cmd, cwd, timeout=3600):  # "meowth build": grava as traduções na ROM
        tj = json.loads(Path(cmd[cmd.index("--translations") + 1]).read_text("utf-8"))
        texts = [e["translated"] for e in retro._entries(tj) if "translated" in e]
        out = bytearray(Path(cmd[2]).read_bytes())
        blob = "|".join(texts).encode("utf-8")
        out[0:len(blob)] = blob
        Path(cmd[cmd.index("-o") + 1]).write_bytes(bytes(out))
    monkeypatch.setattr(retro, "extract", fake_extract)
    monkeypatch.setattr(retro, "_run", fake_run)
    monkeypatch.setattr(retro, "meowth_bin", lambda: "meowth")

    class AI(FakeAI):
        def __call__(self, url, body, headers, timeout):
            r = super().__call__(url, body, headers, timeout)
            r["message"]["content"] = r["message"]["content"].replace("PT Potion", "Poção ã")
            return r
    cfg = ia.load_cfg(paths)
    chain = [ia.Provider("ollama", {**cfg["providers"]["ollama"], "modelo": "qwen"}, "", AI())]
    rep = retro.translate_rom(paths, rom, chain=chain)
    out_rom, out_patch = retro.output_paths(rom)
    assert rep.translated == 2 and out_rom.exists() and out_patch.exists() and rep.replaced_chars == 2  # "Poção" e "ã"
    assert patches.apply_bps(rom.read_bytes(), out_patch.read_bytes()) == out_rom.read_bytes()
    blob = out_rom.read_bytes().split(b"\x00")[0].decode()
    assert "Poçao a" in blob and "[PLAYER]" in blob and "\\n" in blob  # códigos do jogo intactos
    assert rom.read_bytes() == b"\x00" * 4096  # original intacta


# ============================================================ A3: /converter
def _nsp(p: Path, size=1024):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"PFS0" + b"\x00" * (size - 4))


def test_converter_collect_diagnose_organize(tmp_path):
    root = tmp_path / "roms"
    base = root / "switch/A/Jogo [0100AAAA0000E000][v0].nsp"
    upd = root / "switch/B/Jogo [0100AAAA0000E800][v65536].nsp"
    dlc = root / "switch/C/Jogo DLC [0100AAAA0000F001].nsz"
    for f in (base, upd, dlc):
        _nsp(f)
    _nsp(root / "switch/D/Outro [0100BBBB00000000].nsp")
    tf = converter.collect([root], "0100AAAA0000E000")
    assert (len(tf.base), len(tf.updates), len(tf.dlc)) == (1, 1, 1)
    d = "\n".join(converter.diagnose(tf, "Jogo"))
    assert "comprimidos" in d and "espalhado em 3 pastas" in d
    out = converter.organize(tf, "Jogo")
    dest = root / "switch/Jogo [0100AAAA0000E000]"
    assert sorted(p.name for p in dest.iterdir()) == sorted([base.name, upd.name, dlc.name]) and len(out) == 3
    assert (root / "switch/D").exists() and not (root / "switch/A").exists()


def test_converter_decompress_without_tool_explains(tmp_path, monkeypatch):
    monkeypatch.setattr(converter, "nsz_bin", lambda: None)
    paths = get_paths(tmp_path / "dc").ensure()
    assert "nsz não está instalada" in converter.decompress(paths, converter.TitleFiles("X"))[0]


def test_transient_error_keeps_fast_provider_and_quotes_survive(tmp_path):
    paths = get_paths(tmp_path).ensure()
    cfg = cfg_with(paths, provider="index_translate", fallback=["ollama"])

    class Flaky(FakeAI):
        def __call__(self, url, body, headers, timeout):
            self.calls += 1
            if self.calls == 1:
                raise ia.ProviderError("HTTP 504")  # uma falha passageira
            d = json.loads(body["messages"][-1]["content"])
            return {"choices": [{"message": {"content": json.dumps({k: "PT " + v for k, v in d.items()}, ensure_ascii=False)}}]}
    fast, slow = Flaky(), FakeAI()
    chain = [ia.Provider("index_translate", cfg["providers"]["index_translate"], "", fast),
             ia.Provider("ollama", {**cfg["providers"]["ollama"], "modelo": "qwen"}, "", slow)]
    items = [ia.Item(str(i), f'"Hello {i}!"') for i in range(5)]
    res = ia.translate(paths, cfg, items, "flaky", chain=chain)
    assert slow.calls == 0 and res.provider_used == "index_translate"  # não abandonou o rápido
    assert res.translated["0"] == 'PT "Hello 0!"'  # as aspas do diálogo continuam


def test_ensure_update_selected_fixes_ryujinx(tmp_path, monkeypatch):
    import json as _j
    from dc.traducao import converter, extract
    ryu = tmp_path / "Ryujinx"
    monkeypatch.setattr(switch, "RYU_DIRS", [ryu])
    tid = "0100DCA0064A6000"
    (ryu / "mods/contents" / tid.lower() / switch.MOD_NAME).mkdir(parents=True)
    (ryu / "games" / tid.lower()).mkdir(parents=True)
    upd = tmp_path / "LM3 [0100DCA0064A6800][v327680].nsp"
    upd.write_bytes(b"x")
    monkeypatch.setattr(converter, "collect", lambda roots, t: None)
    monkeypatch.setattr(extract, "latest_update", lambda tf: upd)
    msg = switch.ensure_update_selected(tid, [tmp_path])
    assert msg and upd.name in msg
    data = _j.loads((ryu / "games" / tid.lower() / "updates.json").read_text())
    assert data["selected"] == str(upd) and str(upd) in data["paths"]
    assert switch.ensure_update_selected(tid, [tmp_path]) is None  # já certo: não mexe
