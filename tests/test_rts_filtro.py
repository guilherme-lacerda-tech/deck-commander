"""Filtro de "frase de verdade" do RomTranslate: casos reais do Hercules (PS1). Lixo aceito = jogo corrompido."""
from dc.traducao.rts import is_sentence, strip_accents

REAIS = ["VISIT TO THEBES", "PLEASE INSERT CD", "Press START to continue", "BATTLE OF TITANS",
         "I came here with some friends to catch us some BUG POKEMON!", "You have no memory card.",
         "TRAINING GROUND", "PLEASE INSERT A", "FOREST OF CENTAURS"]
LIXO = ["VDD33Ce", "AAC:cp", "Aux2Count ", "Command Error: ", "A A EAI E EAE", "A tiw", "nq NO", "yb; SO",
        "a pg'", ": IN V", "zt( A", "A ; QB", "9 E A", "%s: no param", "ACA a(", "8 A I A", " B b a B",
        "pg !a", "adu( A", "A IJ)", "Bh4CCO", "EDC!\"VETE4DUT", "Sp1Y2Zn*EI", "Iib,dw", "CJBH9UE", "GT.OVL",
        "I!I!M!IAIAIAM!IAM!I!MAMAM!I E", "EJ:CC FJ", "Ki(Tyj", "li0bei", "on Tu",
        "Sony Computer Entertainment Inc. for North America area"]


def test_real_sentences_pass():
    assert [t for t in REAIS if not is_sentence(t)] == []


def test_junk_never_passes():
    assert [t for t in LIXO if is_sentence(t)] == []


def test_strip_accents():
    assert strip_accents("Ação à vista, coração!") == "Acao a vista, coracao!"
