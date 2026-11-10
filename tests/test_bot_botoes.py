"""Botões nas mensagens do bot: tocar = mandar o comando completo."""
import json

from dc import bot
from dc.paths import get_paths


def _bot(tmp_path):
    x = bot.Bot(get_paths(tmp_path).ensure(), "T")
    x.cfg["allowed"] = [1]
    x.calls = []
    x.call = lambda method, **kw: x.calls.append((method, kw)) or []
    return x


def test_command_in_text_becomes_button_and_tap_runs_it(tmp_path):
    x = _bot(tmp_path)
    x.send(9, "Para seguir: /traduzir aprovar 1a2b3c\nOu use /traduzir <jogo> --forcar")
    kb = json.loads(x.calls[-1][1]["reply_markup"])["inline_keyboard"]
    flat = [b for row in kb for b in row]
    assert [b["text"] for b in flat] == ["/traduzir aprovar 1a2b3c"]  # o com <jogo> não vira botão
    ran = []
    x.handle = lambda uid, chat, cmd: ran.append(cmd) or "ok"
    x.handle_callback({"id": "q", "from": {"id": 1}, "data": flat[0]["callback_data"], "message": {"chat": {"id": 9}}})
    assert ran == ["/traduzir aprovar 1a2b3c"]


def test_yes_no_buttons_send_their_text(tmp_path):
    x = _bot(tmp_path)
    x.send(9, "deseja traduzir?", buttons=["Sim", "Não"])
    kb = json.loads(x.calls[-1][1]["reply_markup"])["inline_keyboard"]
    assert [b["text"] for b in kb[0]] == ["Sim", "Não"]
    ran = []
    x.handle = lambda uid, chat, cmd: ran.append(cmd) or ""
    x.handle_callback({"id": "q", "from": {"id": 1}, "data": kb[0][1]["callback_data"], "message": {"chat": {"id": 9}}})
    assert ran == ["Não"]


def test_help_text_buttons_are_only_complete_commands(tmp_path):
    x = _bot(tmp_path)
    x.send(9, bot.HELP)
    kb = json.loads(x.calls[-1][1].get("reply_markup", '{"inline_keyboard": []}'))["inline_keyboard"]
    labels = [b["text"] for row in kb for b in row]
    assert len(labels) <= 6 and all(len(lbl.split()) <= 3 for lbl in labels)
