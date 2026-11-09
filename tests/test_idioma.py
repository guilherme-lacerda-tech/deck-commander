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
