"""Tradução fora do padrão: achar frases em qualquer arquivo e trocar no mesmo lugar, sem mudar tamanho."""
from dc.traducao import generico


def _u16(s):
    return s.encode("utf-16-le") + b"\0\0"


def _u8(s):
    return s.encode("utf-8") + b"\0"


BLOB = (b"\x01\x02\x03\x04" + _u16("Press START to begin") + b"\x00\x00" + _u16("Save your progress?")
        + b"\xff\xfe\x10\x20" + _u8("You found the golden key.") + _u8("Bye") + b"\x07" * 9 + _u8("gfx_tex_01"))


def test_find_strings_both_encodings():
    slots = generico.find_strings(BLOB)
    texts = {(s.encoding, s.text) for s in slots}
    assert ("utf-16-le", "Press START to begin") in texts
    assert ("utf-16-le", "Save your progress?") in texts
    assert ("utf-8", "You found the golden key.") in texts
    s = next(s for s in slots if s.text == "Press START to begin")
    assert s.offset == 4 and s.length == len("Press START to begin") * 2
    assert all(BLOB[s.offset:s.offset + s.length].decode(s.encoding) == s.text for s in slots)


def test_find_strings_keeps_only_sentences():
    texts = [s.text for s in generico.find_strings(BLOB, sentences_only=True)]
    assert "gfx_tex_01" not in texts and "Bye" not in texts
    assert "You found the golden key." in texts


def test_apply_same_size_and_untouched_outside():
    slots = generico.find_strings(BLOB, sentences_only=True)
    by = {s.text: s for s in slots}
    new, applied, skipped = generico.apply(BLOB, slots, {
        by["Press START to begin"].offset: "Aperte START",               # cabe
        by["You found the golden key."].offset: "Você achou a chave de ouro dourada brilhante.",  # não cabe
    })
    assert len(new) == len(BLOB)
    assert applied == 1 and skipped == 1
    s = by["Press START to begin"]
    assert new[s.offset:s.offset + s.length + 2].decode("utf-16-le").rstrip("\0") == "Aperte START"
    # nada fora do espaço da frase mudou
    diff = [i for i in range(len(BLOB)) if BLOB[i] != new[i]]
    assert all(s.offset <= i < s.offset + s.length for i in diff)


def test_apply_utf8_accents_count_bytes():
    blob = b"\0" + _u8("Open the door now") + b"\0"
    slots = generico.find_strings(blob, sentences_only=True)
    new, applied, _ = generico.apply(blob, slots, {slots[0].offset: "Abra a porta já"})
    assert applied == 1 and len(new) == len(blob)
    assert "Abra a porta já" in new.decode("utf-8", "replace")


def test_layers_roundtrip():
    import zlib
    raw = BLOB
    for packed in (zlib.compress(raw), raw):
        body, kind = generico.unpack(packed)
        assert body == raw
        assert generico.unpack(generico.pack(body, kind))[0] == raw
