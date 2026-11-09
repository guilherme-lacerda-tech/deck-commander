"""Idioma de origem: detectar em que língua está cada trecho e dizer se é frase de verdade, em QUALQUER
língua (o jogo pode ter vindo em russo, japonês, espanhol…). Sem dependências.

- Cirílico -> russo; kana/kanji -> japonês; alfabeto latino -> a língua cujas palavras comuns mais aparecem.
- "Frase de verdade" segue as regras rígidas do inglês (forma de palavra, vogal/consoante, nada de símbolo
  de código), adaptadas a cada alfabeto, e exige palavra comum da língua ou título em maiúsculas.
- Tabelas de caracteres (.tbl) para codificações cirílicas antigas (CP1251, CP866, KOI8-R), usadas pelo
  RomTranslate quando o texto do jogo não é ASCII.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Optional

COMMON = {
    "en": """the and you to of a in is it that for on your with this are be can not have will what here there
        press start game save load new quit exit menu continue options level stage world time score lives item
        please insert memory card data controller yes no back next ok cancel select one two you're i'm don't""",
    "ru": """и в не на я что он с это как а по но вы к у мы же из за да о от так для ты нет все его она был уже вот
        если может есть будет только здесь можно нажмите игра игру игры сохранить загрузить начать выход
        продолжить меню уровень время очки жизни карта памяти контроллер вставьте да нет назад далее отмена
        выбрать новая новый опции настройки звук музыка пауза""",
    "es": """el la los las de que y en un una es no por con para se su lo al del como pero más este esta
        pulsa presiona juego partida guardar cargar nueva salir menú continuar opciones nivel tiempo vidas""",
    "fr": """le la les de et un une est en que qui pour pas sur avec vous il elle ce cette dans au du des
        appuyez jeu partie sauvegarder charger nouvelle quitter menu continuer options niveau temps vies""",
    "de": """der die das und ist nicht ein eine zu den mit ich du sie es auf für von im dem wir ihr
        drücke spiel speichern laden neues beenden menü weiter optionen level zeit leben""",
    "it": """il la di che e un una non per con del della sono è ho hai gli le lo al
        premi gioco partita salva carica nuova esci menu continua opzioni livello tempo vite""",
}
COMMON = {k: set(v.split()) for k, v in COMMON.items()}
LANG_IA = {"en": "en", "ru": "ru", "ja": "ja", "es": "es", "fr": "fr", "de": "de", "it": "it"}

_CYR = re.compile(r"[Ѐ-ӿ]")
_KANA = re.compile(r"[぀-ヿ一-鿿]")
_BAD = re.compile(r"[_\\/|{}=<>@#$^~`%*]|\.(bin|dat|tim|str|xa|exe|ovl|bmp|vab|elf|irx)\b", re.I)
SYSTEM_TEXT = re.compile(r"Sony Computer Entertainment|Licensed by|PS-X EXE|Nintendo of America|SEGA ENTERPRISES", re.I)


def script(text: str) -> str:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return "none"
    if sum(bool(_CYR.match(c)) for c in letters) / len(letters) > 0.5:
        return "cyrillic"
    if sum(bool(_KANA.match(c)) for c in letters) / len(letters) > 0.3:
        return "cjk"
    return "latin"


def language(text: str) -> Optional[str]:
    s = script(text)
    if s == "cyrillic":
        return "ru"
    if s == "cjk":
        return "ja"
    if s != "latin":
        return None
    words = [w.strip(".,!?'\":;()-¡¿").lower() for w in text.split()]
    scores = {lang: sum(w in COMMON[lang] for w in words) for lang in ("en", "es", "fr", "de", "it")}
    best = max(scores, key=scores.get)
    return best if scores[best] else None


def _word_ok(w: str, vowels: str) -> bool:
    if not (w.islower() or w.isupper() or (w[0].isupper() and w[1:].islower())) or len(w) > 18:
        return False
    v = any(c in vowels for c in w.lower())
    if len(w) == 2 and not v and not w.isupper():
        return False
    if len(w) >= 3 and (not v or all(c in vowels for c in w.lower())):
        return False
    return True


def is_sentence(text: str, lang: Optional[str] = None) -> bool:
    """Frase que alguém lê no jogo, em qualquer língua. Rígido de propósito: dado que parece letra,
    se for traduzido e gravado, quebra o jogo."""
    t = text.strip()
    if SYSTEM_TEXT.search(t) or len(t) < 2 or _BAD.search(t):
        return False
    lang = lang or language(t)
    if lang == "ja":  # japonês não usa espaços: exige kana e quase nada de lixo
        letters = [c for c in t if not c.isspace()]
        good = sum(bool(_KANA.match(c)) or c in "、。！？「」…ー・" or c.isdigit() for c in letters)
        return len(letters) >= 3 and good / len(letters) > 0.85 and bool(re.search(r"[぀-ヿ]", t))
    if len(t) < 5:
        return False
    vowels = "аеёиоуыэюяaeiou" if lang == "ru" else "aeiouáéíóúàèìòùâêîôûäëïöüãõœ"
    words = [w.strip(".,!?'\":;()-«»¡¿…") for w in t.split()]
    words = [w for w in words if w]
    if len(words) < 2:
        return False
    alpha = [w for w in words if w.isalpha()]
    if len(alpha) < max(2, int(0.75 * len(words) + 0.5)) or not all(_word_ok(w, vowels) for w in alpha):
        return False
    if lang == "ru" and any(not _CYR.search(w) for w in alpha if len(w) >= 3) and \
            sum(bool(_CYR.search(w)) for w in alpha) < len(alpha) * 0.7:
        return False  # mistura de alfabetos em palavra: lixo
    long_ = [w for w in alpha if len(w) >= 2]
    if len(long_) < 2 or sum(map(len, long_)) < 6:
        return False
    if len(long_) <= 3 and any(w.isupper() for w in long_) and any(w.islower() for w in long_):
        return False
    common = COMMON.get(lang or "en", COMMON["en"])
    low = [w.lower() for w in long_] + [w.lower() for w in alpha if len(w) == 1 and lang == "ru"]
    if sum(w in common for w in low) >= (1 if len(long_) <= 4 else 2):
        return True
    return all(w.isupper() for w in long_) and sum(len(w) >= 3 for w in long_) >= 2


def dominant_language(texts: list[str]) -> Optional[str]:
    c = Counter(l for l in (language(t) for t in texts if is_sentence(t)) if l)
    return c.most_common(1)[0][0] if c else None


def write_tbl(path: Path, codec: str) -> Path:
    """Tabela .tbl (formato 'XX=caractere') de uma codificação de 1 byte (cp1251, cp866, koi8_r)."""
    lines = []
    for b in range(0x20, 0x100):
        if b == 0x7F:
            continue
        try:
            ch = bytes([b]).decode(codec)
        except UnicodeDecodeError:
            continue
        if ch.isprintable() and ch not in "\t\r\n":
            lines.append(f"{b:02X}={ch}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", "utf-8")
    return path


CYRILLIC_CODECS = ["cp1251", "cp866", "koi8_r"]
