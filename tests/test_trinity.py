"""Engine Trinity (Pokémon Legends Z-A): Oodle/Mermaid, FlatBuffers do trpfd/trpfs/trpak, mensagens .dat e o mod.
Dados sintéticos (nada do jogo no repositório); a conferência com os arquivos reais é tools/trinity_check.py."""
import json
import struct

import pytest

from dc.traducao import ia, oodle, trinity, trinity_game as tg, trinity_msg as tm


# ----------------------------------------------------------------------------- FlatBuffers mínimos (só p/ teste)
class FB:
    def __init__(self):
        self.b = bytearray(4)

    def pad(self, a):
        self.b += b"\0" * (-len(self.b) % a)

    def table(self, fields):
        """fields: None | ("s", fmt, valor) | ("v", função que grava o filho e devolve a posição)"""
        layout, off = [], 4
        for f in fields:
            if f is None:
                layout.append(0)
                continue
            size = struct.calcsize("<" + f[1]) if f[0] == "s" else 4
            off = (off + size - 1) // size * size
            layout.append(off)
            off += size
        self.pad(2)
        vt = len(self.b)
        self.b += struct.pack("<HH", 4 + 2 * len(fields), off) + b"".join(struct.pack("<H", o) for o in layout)
        self.pad(8)
        t = len(self.b)
        self.b += b"\0" * off
        struct.pack_into("<i", self.b, t, t - vt)
        for f, o in zip(fields, layout):
            if f and f[0] == "s":
                struct.pack_into("<" + f[1], self.b, t + o, f[2])
        for f, o in zip(fields, layout):
            if f and f[0] == "v":
                pos = f[1](self)
                struct.pack_into("<I", self.b, t + o, pos - (t + o))
        return t

    def vec_u64(self, vals):
        self.pad(8)
        self.b += b"\0" * 4
        pos = len(self.b)
        self.b += struct.pack(f"<I{len(vals)}Q", len(vals), *vals)
        return pos

    def vec_bytes(self, data):
        self.pad(4)
        pos = len(self.b)
        self.b += struct.pack("<I", len(data)) + data
        return pos

    def vec_refs(self, writers):
        self.pad(4)
        pos = len(self.b)
        self.b += struct.pack("<I", len(writers)) + b"\0" * 4 * len(writers)
        for k, w in enumerate(writers):
            target = w(self)
            e = pos + 4 + 4 * k
            struct.pack_into("<I", self.b, e, target - e)
        return pos

    @staticmethod
    def string(s):
        def w(fb):
            fb.pad(4)
            pos = len(fb.b)
            d = s.encode()
            fb.b += struct.pack("<I", len(d)) + d + b"\0"
            return pos
        return w

    def finish(self, root):
        struct.pack_into("<I", self.b, 0, root)
        return bytes(self.b)


def make_trpfd(paths_by_pack: dict[str, list[str]]) -> bytes:
    names = list(paths_by_pack)
    entries = sorted((trinity.fnv1a64(p), i) for i, n in enumerate(names) for p in paths_by_pack[n])
    fb = FB()
    root = fb.table([
        ("v", lambda f: f.vec_u64([h for h, _ in entries])),
        ("v", lambda f: f.vec_refs([FB.string(n) for n in names])),
        ("v", lambda f: f.vec_refs([(lambda i: lambda g: g.table([("s", "Q", i), ("s", "I", 0)]))(i)
                                    for _, i in entries])),
        ("v", lambda f: f.vec_refs([(lambda n: lambda g: g.table([("s", "Q", 100), ("s", "Q", n)]))(len(paths_by_pack[x]))
                                    for x in names])),
    ])
    return fb.finish(root)


def make_pack(files: list[tuple[str, int, int, bytes]]) -> bytes:
    """files: (caminho, enc, tamanho original, dados no pacote)"""
    fb = FB()
    root = fb.table([
        ("v", lambda f: f.vec_u64([trinity.fnv1a64(p) for p, *_ in files])),
        ("v", lambda f: f.vec_refs([(lambda e, s, d: lambda g: g.table(
            [("s", "I", 0), ("s", "b", e), ("s", "B", 0), ("s", "Q", s), ("v", lambda h: h.vec_bytes(d))]))(e, s, d)
            for _, e, s, d in files])),
    ])
    return fb.finish(root)


# ----------------------------------------------------------------------------- Oodle
def mermaid_lz_stream() -> tuple[bytes, bytes]:
    """Fluxo Mermaid feito à mão: 8 bytes crus + 2 comandos de cópia (offset 8) = 32 bytes."""
    plain = b"ABCDEFGH" * 4
    body = (b"ABCDEFGH"                       # primeiros 8 bytes do bloco vão crus
            + b"\x00\x00\x00"                 # fluxo de literais vazio (cópia, tamanho 0)
            + b"\x00\x00\x02" + bytes([15 << 3, 0x80 | 9 << 3])  # comandos: 15 com offset novo, 9 com o recente
            + struct.pack("<HH", 1, 8)        # 1 offset curto = 8
            + b"\x00\x00\x00")                # sem offsets distantes
    chunk = struct.pack(">I", 0x800000 | (1 << 19) | len(body))[1:] + body   # trecho LZ, modo 1
    quantum = struct.pack(">I", len(chunk) - 1)[1:] + chunk
    return b"\x0c\x0a" + quantum, plain


def test_oodle_mermaid_lz_e_cru():
    comp, plain = mermaid_lz_stream()
    assert oodle.decompress(comp, len(plain)) == plain
    raw = b"texto qualquer"
    assert oodle.decompress(b"\x4c\x0a" + raw, len(raw)) == raw     # bloco sem compressão


def test_oodle_rle_memset_e_erros():
    # trecho sem LZ com entropia RLE de 1 byte (memset)
    n = 40  # cabeçalho longo (o curto liga o bit 0x800000, que no Mermaid quer dizer "trecho LZ")
    chunk = bytes([0x30]) + struct.pack(">I", ((n - 1) << 18) | 1) + b"Z"
    comp = b"\x0c\x0a" + struct.pack(">I", len(chunk) - 1)[1:] + chunk
    assert oodle.decompress(comp, n) == b"Z" * n
    with pytest.raises(oodle.OodleError):
        oodle.decompress(b"\x0c\x06" + comp[2:], n)   # Kraken: não suportado, recusa
    with pytest.raises(oodle.OodleError):
        oodle.decompress(comp[:-1], n)                # truncado
    comp2, plain = mermaid_lz_stream()
    with pytest.raises(oodle.OodleError):
        oodle.decompress(comp2, len(plain) + 1)       # tamanho declarado errado


def test_tans_e_huffman_recusam_lixo():
    for t in (1, 2, 4):
        b0 = 0x80 | t << 4
        data = bytes([b0, 0x08, 0x05]) + b"\xff" * 5   # src 5, dst 8
        with pytest.raises(oodle.OodleError):
            oodle.decode_bytes(data, 0, len(data), 64)


# ----------------------------------------------------------------------------- FlatBuffers
PATHS = {"arc/a.trpak": ["ik_message/dat/English/common/bag.dat", "ik_message/dat/English/common/bag.tbl"],
         "arc/b.trpak": ["x/y.bin", "x/z.bin", "x/w.bin"]}


def test_fnv_e_trpfd():
    assert trinity.fnv1a64("") == 0xCBF29CE484222645
    assert trinity.fnv1a64("ik_message/dat/English/common/bag.tbl") == 0xDCB5541BF5FB08B5  # do jogo real
    raw = make_trpfd(PATHS)
    fd = trinity.read_trpfd(raw)
    assert fd.pack_names == list(PATHS)
    assert fd.pack_names[fd.pack_of(trinity.fnv1a64("x/z.bin"))] == "arc/b.trpak"
    assert fd.pack_of(trinity.fnv1a64("nada")) is None
    rm = {trinity.fnv1a64("ik_message/dat/English/common/bag.dat"), trinity.fnv1a64("x/w.bin")}
    new = trinity.trpfd_without(raw, rm)
    assert len(new) == len(raw)
    fd2 = trinity.read_trpfd(new)
    assert len(fd2.hashes) == 3 and not rm & set(fd2.hashes)
    for p in ("ik_message/dat/English/common/bag.tbl", "x/y.bin", "x/z.bin"):
        assert fd2.pack_of(trinity.fnv1a64(p)) == fd.pack_of(trinity.fnv1a64(p))
    with pytest.raises(trinity.TrinityError):
        trinity.trpfd_without(raw, {123})


def test_pack_e_archive():
    comp, plain = mermaid_lz_stream()
    pk = make_pack([("x/y.bin", 3, len(plain), comp), ("x/z.bin", -1, 3, b"abc")])
    files = trinity.read_pack(pk)
    assert [f.content() for f in files] == [plain, b"abc"]
    # data.trpfs: ONEPACK + pacote + tabela no fim
    fb = FB()
    body = b"ONEPACK\0" + b"\0" * 8 + pk
    table_off = len(body)
    t = FB()
    t.b = bytearray(4)
    troot = t.table([("v", lambda f: f.vec_u64([trinity.fnv1a64("arc/b.trpak")])), ("v", lambda f: f.vec_u64([16]))])
    trpfs = bytearray(body + t.finish(troot))
    struct.pack_into("<Q", trpfs, 8, table_off)
    arc = trinity.Archive(make_trpfd(PATHS), lambda o, n: bytes(trpfs[o:o + n]), len(trpfs))
    assert arc.get("x/y.bin") == plain and arc.get("x/z.bin") == b"abc"
    with pytest.raises(trinity.TrinityError):
        arc.get("ik_message/dat/English/common/bag.dat")   # pacote não está no trpfs
    del fb


def test_resolve_paths():
    hs = {trinity.fnv1a64(p) for p in PATHS["arc/a.trpak"]}
    got = tg.resolve_paths("arc/ik_messagedatEnglishcommonbag.tbl.trpak", "English", hs)
    assert sorted(got.values()) == sorted(PATHS["arc/a.trpak"])
    p3 = "ik_message/dat/English/script/sub/talk.dat"
    got = tg.resolve_paths("arc/ik_messagedatEnglishscriptsubtalk.dat.trpak", "English", {trinity.fnv1a64(p3)})
    assert list(got.values()) == [p3]


# ----------------------------------------------------------------------------- mensagens
def sample_dat() -> tm.MsgDat:
    W = lambda s: list(struct.unpack(f"<{len(s.encode('utf-16-le')) // 2}H", s.encode("utf-16-le")))  # noqa: E731
    lines = [
        tm.Line(W("Hello, ") + [0x10, 1, 0x0100] + W("!"), 0),
        tm.Line([0xE300] + W("Lv. ") + [0x10, 3, 0x0206, 0, 0x2C], 4),
        tm.Line(W("I think I’m finally getting used to the smell of all\nthe Pokémon around here.")
                + [0x10, 1, 0xBE01] + W("\nIt’s weird, but now I sort of feel reassured."), 0),
        tm.Line([], 0),
    ]
    return tm.MsgDat(lines)


def test_dat_roundtrip_byte_a_byte():
    m = sample_dat()
    raw = tm.write_dat(m)
    assert raw[:4] == struct.pack("<HH", 1, 4)
    back = tm.read_dat(raw)
    assert [l.words for l in back.lines] == [l.words for l in m.lines]
    assert [l.flags for l in back.lines] == [0, 4, 0, 0]
    assert tm.write_dat(back) == raw
    # o texto está cifrado (não aparece em claro no arquivo)
    assert "Hello".encode("utf-16-le") not in raw
    with pytest.raises(tm.MsgError):
        tm.read_dat(raw[:-4])


def test_codigos_viram_marcadores():
    m = sample_dat()
    text, codes = m.texts()[0]
    assert to(text) == "Hello, ⟦0⟧!"
    words = tg.from_marked("Olá, ⟦0⟧!", codes)
    assert tm.split_codes(words)[1] == codes
    t2, c2 = m.texts()[1]
    assert to(t2) == "⟦0⟧Lv. ⟦1⟧"
    # a IA pode trocar a ordem dos marcadores
    w = tg.from_marked("Nv. ⟦1⟧ ⟦0⟧", c2)
    assert w[:4] == [ord(c) for c in "Nv. "] and w[4:9] == list(c2[1])
    with pytest.raises(tm.MsgError):
        tg.from_marked("Nv. ⟦1⟧", c2)
    assert ia.placeholders_ok(to(t2), "Nv. ⟦1⟧ ⟦0⟧")


def to(text):
    return tg.to_marked(text)


def test_layout_quebra_linhas_e_caixas():
    m = sample_dat()
    text, codes = m.texts()[2]
    long_pt = ("Acho que finalmente estou me acostumando com o cheiro de todos os Pokémon por aqui, "
               "de verdade mesmo. ⟦0⟧ É estranho, mas agora eu me sinto tranquilo quando sinto um cheiro forte "
               "deles e isso continua por várias linhas a mais do que cabe numa caixa.")
    marked, codes2, fits = tg.layout(text, codes, long_pt)
    assert fits
    words = tg.from_marked(marked, codes2)
    t3, c3 = tm.split_codes(words)
    width = max(len(x) for x in text.replace("\x00", "").split("\n"))
    boxes = t3.split("\x00")
    for b in boxes:
        lines = b.strip("\n").split("\n")
        assert len(lines) <= 2 and all(len(x) <= width for x in lines)
    assert codes[0] in c3 and len(c3) > 1 and all(c[2] in (0xBE00, 0xBE01) for c in c3)
    # frase de uma linha só (menu) não é mexida
    t0, k0 = m.texts()[0]
    assert tg.layout(t0, k0, "Olá, ⟦0⟧!") == ("Olá, ⟦0⟧!", k0, True)


def test_build_mod(tmp_path):
    rel = "ik_message/dat/English/common/bag.dat"
    raw_fd = make_trpfd(PATHS)
    m = sample_dat()
    m.lines[0].words = tg.from_marked("Olá, ⟦0⟧!", m.texts()[0][1])
    problems = tg.build_mod(tmp_path / "romfs", raw_fd, {rel: m})
    assert problems == []
    assert tm.read_dat((tmp_path / "romfs" / rel).read_bytes()).texts()[0][0] == "Olá, \x00!"
    fd = trinity.read_trpfd((tmp_path / "romfs/arc/data.trpfd").read_bytes())
    assert fd.pack_of(trinity.fnv1a64(rel)) is None                       # o jogo lê o arquivo solto
    assert fd.pack_of(trinity.fnv1a64("x/y.bin")) is not None             # o resto segue nos pacotes


def test_fonte_otf_cmap():
    # OTF mínima: só a tabela cmap formato 4 com 'a'..'z' e 'ã'
    segs = [(0x61, 0x7A), (0xE3, 0xE3), (0xFFFF, 0xFFFF)]
    n = len(segs)
    sub = struct.pack(">HHHHHHH", 4, 0, 0, 2 * n, 0, 0, 0)
    sub += b"".join(struct.pack(">H", e) for _, e in segs) + b"\0\0"
    sub += b"".join(struct.pack(">H", s) for s, _ in segs)
    sub += b"".join(struct.pack(">h", 1) for _ in segs)
    sub += b"".join(struct.pack(">H", 0) for _ in segs)
    cmap = struct.pack(">HHHHI", 0, 1, 3, 1, 12) + sub
    otf = b"OTTO" + struct.pack(">HHHH", 1, 16, 0, 0) + struct.pack(">4sIII", b"cmap", 0, 28, len(cmap)) + cmap
    key = bytes.fromhex("49621806") * (len(otf) // 4 + 1)
    bf = b"\0" * 8 + bytes(a ^ b for a, b in zip(otf, key))
    chars = trinity.otf_chars(trinity.decrypt_bfotf(bf))
    assert ord("ã") in chars and ord("q") in chars and ord("õ") not in chars
    assert "õ" in trinity.missing_ptbr(chars) and "ã" not in trinity.missing_ptbr(chars)


def test_versao_igual_a_do_ryujinx(tmp_path, monkeypatch):
    """O trpfd do mod tem de ser da versão que o Ryujinx carrega (o de outra versão trava o jogo)."""
    from dc.traducao import switch
    ryu = tmp_path / "Ryujinx"
    monkeypatch.setattr(switch, "RYU_DIRS", [ryu])
    assert tg.ryujinx_update("0100F43008C44000") is None          # nada configurado: versão base
    upd = tmp_path / "upd.nsp"
    upd.write_bytes(b"x")
    g = ryu / "games" / "0100f43008c44000"
    g.mkdir(parents=True)
    (g / "updates.json").write_text(json.dumps({"selected": str(upd), "paths": [str(upd)]}), "utf-8")
    assert tg.ryujinx_update("0100F43008C44000") == upd
    (g / "updates.json").write_text(json.dumps({"selected": "", "paths": [str(upd)]}), "utf-8")
    assert tg.ryujinx_update("0100F43008C44000") is None          # atualização desmarcada


def test_guard_desliga_mod_de_outra_versao(tmp_path, monkeypatch):
    from dc.traducao import switch
    ryu = tmp_path / "Ryujinx"
    monkeypatch.setattr(switch, "RYU_DIRS", [ryu])
    tid = "0100F43008C44000"
    mod = switch.mod_target(tid)
    (mod / "romfs/arc").mkdir(parents=True)
    (mod / tg.MARKER).write_text(json.dumps({"update": None}), "utf-8")
    assert tg.guard_version(tid, tmp_path / "park") is None              # base com base: fica
    upd = tmp_path / "Z-A [v393216].nsp"
    upd.write_bytes(b"x")
    g = ryu / "games" / tid.lower()
    g.mkdir(parents=True)
    (g / "updates.json").write_text(json.dumps({"selected": str(upd)}), "utf-8")
    msg = tg.guard_version(tid, tmp_path / "park")                       # atualização ligada depois
    assert msg and "inglês" in msg and not mod.exists()
    assert (tmp_path / "park" / f"{tid}-base" / "romfs/arc").is_dir()
    assert tg.guard_version(tid, tmp_path / "park") is None              # sem mod: nada a fazer


def test_unmark_formato(tmp_path):
    from dc.traducao import portugues
    portugues.mark(tmp_path, "g1", formato="fechado", langs=["AmericanEnglish"])
    portugues.unmark(tmp_path, "g1", "formato")
    d = json.loads(portugues.idiomas_path(tmp_path).read_text("utf-8"))
    assert d == {"g1": {"langs": ["AmericanEnglish"]}}
