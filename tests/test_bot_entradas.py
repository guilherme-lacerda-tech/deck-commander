"""Tudo que a pessoa pode mandar errado no bot: a resposta é sempre uma mensagem clara, nunca exceção,
e nada inválido chega ao qBittorrent."""
import pytest

from dc import bot, syncer
from dc.paths import get_paths

HASH = "a" * 40
MAG = f"magnet:?xt=urn:btih:{HASH}&dn=Super+Mario"
TORRENT = b"d8:announce3:url4:infod4:name5:Mario12:piece lengthi16384eee"


class FakeQbt:
    def __init__(self):
        self.added = []

    def torrents(self, *a, **k):
        return []

    def add(self, magnet, cat, dest, extra_tags=""):
        self.added.append((magnet, cat))

    def add_file(self, data, name, cat, dest, extra_tags=""):
        self.added.append((name, cat))


@pytest.fixture
def x(tmp_path, monkeypatch):
    b = bot.Bot(get_paths(tmp_path).ensure(), "TOK")
    b.cfg["allowed"] = [1]
    b.sent = []
    b.call = lambda method, **kw: ({"file_path": "f"} if method == "getFile" else b.sent.append(kw) or [])
    b.qbt = FakeQbt()
    b.limited = lambda uid: False
    monkeypatch.setattr(syncer, "_cfg", lambda p: {"downloads_root": str(tmp_path / "dl")})
    return b


def msg(b, text=None, **extra):
    m = {"from": {"id": 1}, "chat": {"id": 9}, **extra}
    if text is not None:
        m["text"] = text
    return b.handle_message(m)


@pytest.mark.parametrize("text", ["", " ", "\n", "ççç 🎮", "a" * 5000, "/", "/@bot"])
def test_empty_or_weird_messages_never_raise(x, text):
    r = msg(x, text)
    assert r is None or isinstance(r, str)
    assert x.qbt.added == []


@pytest.mark.parametrize("text", ["/add abc", "/add switch notamagnet", "magnet:?xt", "magnet:?dn=Mario",
                                  "/add switch magnet:?xt=urn:btih:abc", "switch magnet:?xt=urn:btih:123"])
def test_invalid_magnet_is_refused_and_not_sent_to_qbittorrent(x, text):
    r = msg(x, text)
    assert "magnet" in r.lower()
    assert x.qbt.added == []


def test_misspelled_console_in_add_is_refused_not_used_as_category(x):
    r = msg(x, f"/add Swich {MAG}")
    assert "Não conheço o console" in r and x.qbt.added == []


def test_console_and_magnet_in_same_message(x):
    r = msg(x, f"Switch {MAG}")
    assert r.startswith("Adicionado (switch)")
    assert x.qbt.added == [(MAG, "switch")]


def test_magnet_alone_uses_console_said_before(x):
    assert "= ps2" in msg(x, "PS2")
    assert msg(x, MAG).startswith("Adicionado (ps2)")
    assert msg(x, MAG.replace("a" * 40, "b" * 40)).startswith("Adicionado (descubro o console")  # vale só para o próximo


def test_base32_magnet_is_valid(x):
    assert bot.valid_magnet("magnet:?xt=urn:btih:" + "A" * 32)
    assert not bot.valid_magnet("magnet:?xt=urn:btih:" + "A" * 31)


@pytest.mark.parametrize("text,expected", [("playstation 5", None), ("ps5", None), ("xbox one", None),
                                           ("xbox series x", None), ("Xbox 360", "x360"), ("xbox", "xbox"),
                                           ("playstation", "psx"), ("Switch 1", "switch"), ("switch 2", "switch2")])
def test_console_names(text, expected):
    assert bot.parse_console(text) == expected


def test_unknown_console_answers_clearly(x):
    assert "Não conheço o console" in msg(x, "playstation 5")
    assert "Não conheço o console" in msg(x, "Swich")


def test_file_that_is_not_a_torrent(x, monkeypatch):
    assert "só sei usar arquivos .torrent" in msg(x, document={"file_name": "jogo.iso", "file_id": "1"})

    class R:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self): return b"<html>login</html>"
    monkeypatch.setattr(bot.urllib.request, "urlopen", lambda *a, **k: R())
    r = msg(x, document={"file_name": "x.torrent", "file_id": "1", "file_size": 10}, caption="Switch")
    assert "não é um .torrent válido" in r and x.qbt.added == []


def test_torrent_download_fails_network(x, monkeypatch):
    def boom(*a, **k):
        raise OSError("timed out")
    monkeypatch.setattr(bot.urllib.request, "urlopen", boom)
    r = msg(x, document={"file_name": "Mario.torrent", "file_id": "1", "file_size": 10}, caption="Switch")
    assert r.startswith("❌ Não consegui pegar o arquivo") and x.qbt.added == []


def test_valid_torrent_with_accents_and_emoji_in_name(x, monkeypatch):
    class R:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self): return TORRENT
    monkeypatch.setattr(bot.urllib.request, "urlopen", lambda *a, **k: R())
    r = msg(x, document={"file_name": 'Pokémon "Édição" 🎮.torrent', "file_id": "1", "file_size": 10}, caption="switch")
    assert r.startswith("⬇️ Baixando Pokémon") and x.qbt.added[0][1] == "switch"


def test_commands_without_arguments_show_usage(x):
    assert msg(x, "/console").startswith("Uso:")
    assert msg(x, "/aprovar").startswith("Uso:")


def test_translate_library_on_fresh_deck_without_games(x):
    r = msg(x, "/traduzir biblioteca")
    assert "Nada novo para traduzir" in r


def test_old_button_gets_an_answer(x):
    x.handle_callback({"id": "q", "from": {"id": 1}, "data": "c:deadbeef0000", "message": {"chat": {"id": 9}}})
    assert "botão é de uma mensagem antiga" in x.sent[-1]["text"]


def test_button_whose_command_crashes_still_answers(x):
    x.cfg["botoes"] = {"k1": "/status"}
    x.handle = lambda *a: (_ for _ in ()).throw(RuntimeError("disco sumiu"))
    x.handle_callback({"id": "q", "from": {"id": 1}, "data": "c:k1", "message": {"chat": {"id": 9}}})
    assert x.sent[-1]["text"].startswith("❌ Deu erro ao rodar /status")


def test_stranger_is_refused_even_with_magnet(x):
    r = x.handle_message({"from": {"id": 666}, "chat": {"id": 9}, "text": MAG})
    assert "Acesso negado" in r and x.qbt.added == []
