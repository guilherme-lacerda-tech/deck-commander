"""Simulação 10/11: usuário confuso no bot (as mensagens chegam por handle_message, como no Telegram)."""

import pytest

from dc import bot
from dc.paths import get_paths

H = "c" * 40
MAG = f"magnet:?xt=urn:btih:{H}&dn=Okami"


class Q:
    def __init__(self):
        self.added, self.going = [], []

    def add(self, magnet, cat, path):
        self.added.append((magnet, cat))

    def torrents(self, *a, **k):
        return self.going


@pytest.fixture
def b(tmp_path, monkeypatch):
    paths = get_paths(tmp_path).ensure()
    monkeypatch.setattr(bot.ops, "game_running", lambda: False)
    monkeypatch.setattr(bot.ops, "_systemctl", lambda *a: None)
    x = bot.Bot(paths, "TOKEN123")
    x.qbt = Q()
    x.cfg["allowed"] = [1]
    x.sent = []
    x.call = lambda method, **p: x.sent.append(p) or {}
    return x


def msg(text):
    return {"from": {"id": 1}, "chat": {"id": 1}, "text": text}


def test_typed_yes_answers_last_yes_no_question(b):
    b.send(1, "Começar a traduzir os 3?", buttons=[("Sim", "/help"), ("Não", "/status")])
    assert "comandos" in b.handle_message(msg("sim"))           # antes: silêncio
    assert "nenhuma pergunta aberta" in b.handle_message(msg("sim"))  # pergunta já respondida


def test_typed_yes_reaches_out_of_standard_question(b, monkeypatch):
    from dc.traducao import run
    b.cfg["pergunta_op"] = "op123"
    monkeypatch.setattr(run, "answer_generic", lambda paths, op, yes: f"resposta {op} {yes}")
    assert b.handle_message(msg("Sim")) == "resposta op123 True"   # antes: o "Sim" digitado era ignorado


def test_same_magnet_twice_and_no_auto_jargon(b):
    r = b.handle_message(msg(MAG))
    assert "auto" not in r and "descubro o console" in r
    b.qbt.going = [{"hash": H, "name": "Okami (USA)"}]
    assert "já está na fila (Okami (USA))" in b.handle_message(msg(MAG))
    assert len(b.qbt.added) == 1


def test_free_text_download_request_gets_hint(b):
    assert "magnet" in b.handle_message(msg("baixa god of war pra mim"))
    assert b.handle_message(msg("valeu")) is None


def test_wrong_pairing_code_is_explained(b):
    bot.pair_code(b.paths)
    r = b.handle(7, 7, "/start 000001")
    assert "negado" in r and "errado ou vencido" in r


def test_console_aliases_without_invisible_chars():
    assert bot.parse_console("360") == "x360"
    assert bot.parse_console("xbox series s") != "xbox"
    assert bot.parse_console("xbox") == "xbox"
