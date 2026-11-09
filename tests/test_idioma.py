"""Tradução de qualquer língua: detecção de idioma, frase de verdade em russo/japonês/espanhol, tabelas cirílicas."""
from dc.traducao import idioma


def test_language_detection():
    assert idioma.language("Нажмите СТАРТ чтобы начать игру") == "ru"
    assert idioma.language("ゲームをはじめる") == "ja"
    assert idioma.language("Pulsa START para continuar el juego") == "es"
    assert idioma.language("Press START to continue") == "en"


def test_real_sentences_in_other_languages():
    for t, lang in [("Нажмите СТАРТ чтобы начать игру", "ru"), ("Вставьте карту памяти", "ru"),
                    ("НОВАЯ ИГРА", "ru"), ("セーブしますか？", "ja"), ("Pulsa START para continuar", "es"),
                    ("Appuyez sur START pour continuer", "fr")]:
        assert idioma.is_sentence(t), t


def test_junk_in_cyrillic_and_latin_never_passes():
    for t in ["ЖЪЫ", "аа бб", "ЫЪЬЭ ЖЪ", "VDD33Ce", "AAC:cp", "nq NO", "ゃ", "%s: ошибка", "Aux2Count "]:
        assert not idioma.is_sentence(t), t


def test_dominant_language_and_tbl(tmp_path):
    assert idioma.dominant_language(["Нажмите СТАРТ чтобы начать игру", "Вставьте карту памяти", "OK"]) == "ru"
    tbl = idioma.write_tbl(tmp_path / "cp1251.tbl", "cp1251").read_text("utf-8").splitlines()
    assert "C0=А" in tbl and "41=A" in tbl and len(tbl) > 180


def test_gate_blocks_real_junk_from_russian_dumps():
    gos = ["God of War", "o binary in 0.006000 seconds", "ion during this session."] * 10 + ["ヶ淳wミヘワバ", "膜ホュ荘槽喧妹"] * 13
    ok, why = idioma.extraction_is_clean(gos, idioma.language_from_name("GOW GoS rus.iso"))
    assert not ok
    nfs = ["Persistent Memory Pool", "Audio Memory Pool", "Database not initialized"]
    ok, why = idioma.extraction_is_clean(nfs, idioma.language_from_name(
        "Need for Speed Most Wanted Black Edition [RUS NTSC] [ViT Company].iso"))
    assert not ok and "RU" in why


def test_gate_accepts_clean_text():
    ok, _ = idioma.extraction_is_clean(["Press START to continue", "Save your game?", "You found a key"])
    assert ok
    ok, _ = idioma.extraction_is_clean(["Нажмите СТАРТ чтобы начать игру", "Вставьте карту памяти"], "ru")
    assert ok
