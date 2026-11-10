"""Instalação fácil: QR code em Python puro, assistente do Telegram e pareamento protegido."""
import os
import time

from dc import bot, qr, telegram_setup
from dc.paths import get_paths


def test_qr_structure():
    m = qr.encode("https://t.me/BotFather")
    n = len(m)
    assert n == 25  # versão 2
    for x0, y0 in ((0, 0), (n - 7, 0), (0, n - 7)):  # três quadrados de canto
        assert all(m[y0][x0 + i] and m[y0 + 6][x0 + i] for i in range(7))
        assert not m[y0 + 1][x0 + 1] and m[y0 + 3][x0 + 3]
    assert [m[6][i] for i in range(8, n - 8)] == [i % 2 == 0 for i in range(8, n - 8)]  # linha de tempo
    assert m[n - 8][8]  # módulo escuro fixo
    assert len(qr.encode("y" * 200)) == 57  # versão 10 (com bloco de versão)
    t = qr.terminal("abc")
    assert "█" in t and len(t.splitlines()) == (21 + 4 + 1) // 2


def test_qr_png(tmp_path):
    p = qr.png("https://t.me/x_bot?start=123456", tmp_path / "q.png")
    assert p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_pairing_code_expires_and_locks_after_failures(tmp_path, monkeypatch):
    paths = get_paths(tmp_path).ensure()
    monkeypatch.setattr(bot.ops, "game_running", lambda: False)
    b = bot.Bot(paths, "T")
    code = bot.pair_code(paths)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(bot.PAIR_MAX_FAILS):
        assert "negado" in b.handle(7, 7, f"/start {wrong}")
    assert "negado" in b.handle(1, 1, f"/start {code}")  # errou demais: o código caiu
    code = bot.pair_code(paths)
    assert "negado" in b.handle(1, 1, "/start ção")  # acento não derruba o bot
    old = time.time() - bot.PAIR_TTL - 5
    os.utime(paths.state / "telegram-pairing", (old, old))
    assert "negado" in b.handle(1, 1, f"/start {code}")  # venceu
    code = bot.pair_code(paths)
    assert "Pareado" in b.handle(1, 1, f"/start {code}")


def test_telegram_setup_wizard(tmp_path):
    paths = get_paths(tmp_path).ensure()
    said, tokens = [], iter(["lixo", "123456789:" + "A" * 35, "123456789:" + "B" * 35])
    started = []

    def whoami(tok):
        return "deckdojoao_bot" if tok.endswith("B" * 35) else None
    rc = telegram_setup.run(paths, ask_token=lambda prompt: next(tokens), out=said.append, whoami=whoami,
                            start_service=lambda: started.append(1), wait_s=0)
    text = "\n".join(said)
    assert rc == 0 and started == [1]
    assert "t.me/BotFather" in text and "não parece um token" in text and "não reconheceu" in text
    assert (paths.secrets / "telegram").read_text().strip().endswith("B" * 35)
    code = (paths.state / "telegram-pairing").read_text().strip()
    assert f"https://t.me/deckdojoao_bot?start={code}" in text
    assert "B" * 35 not in text  # o token nunca aparece na tela
