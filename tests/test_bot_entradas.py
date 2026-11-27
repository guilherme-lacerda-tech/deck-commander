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


def finish_search(b):
    for _, future in b.searches.values():
        try:
            future.result(timeout=3)
        except Exception:
            pass
    b.notify_searches()
    return b.sent[-1]["text"]


@pytest.mark.parametrize("text", ["", " ", "\n", "ççç 🎮", "a" * 5000, "/", "/@bot"])
def test_empty_or_weird_messages_never_raise(x, text):
    r = msg(x, text)
    assert r is None or isinstance(r, str)
    assert x.qbt.added == []


@pytest.mark.parametrize("text", ["/add abc", "/add switch notamagnet", "magnet:?xt", "magnet:?dn=Mario",
                                  "/add switch magnet:?xt=urn:btih:", "switch magnet:?xt=urn:sha1:123"])
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
    assert not bot.valid_magnet("magnet:?dn=Mario")


@pytest.mark.parametrize("text,expected", [("playstation 5", None), ("ps5", None), ("xbox one", None),
                                           ("xbox series x", None), ("Xbox 360", "x360"), ("xbox", "xbox"),
                                           ("playstation", "psx"), ("Switch 1", "switch"), ("switch 2", "switch2")])
def test_console_names(text, expected):
    assert bot.parse_console(text) == expected


def test_unknown_console_answers_clearly(x):
    assert "Não conheço o console" in msg(x, "playstation 5")
    assert "Não conheço o console" in msg(x, "Swich")


def test_nome_de_jogo_pede_plataforma_sem_iniciar_download(x):
    r = msg(x, "Devil May Cry 3")
    assert "qual plataforma" in r.lower()
    assert x.qbt.added == []
    assert x.cfg["catalogo"]["1"]["titulo"] == "Devil May Cry 3"


def test_titulo_com_nome_de_console_nao_vira_escolha_de_console(x):
    assert "qual plataforma" in msg(x, "Mario Kart Wii")
    assert x.cfg["catalogo"]["1"]["titulo"] == "Mario Kart Wii"
    assert x.qbt.added == []


def test_pedido_sem_fonte_fica_persistido_para_retomada(x):
    msg(x, "Hades")
    assert "Pesquisando" in msg(x, "PC")
    r = finish_search(x)
    assert "aguardando uma fonte" in r
    assert "Hades" in r
    assert x.qbt.added == []
    assert x.cfg["catalogo"]["1"]["status"] == "waiting_source"
    assert x.cfg["catalogo"]["1"]["console"] == "pc"


def test_plataforma_retro_sem_fonte_preserva_pedido(x):
    msg(x, "Devil May Cry 3")
    msg(x, "PS2")
    r = finish_search(x)
    assert "aguardando uma fonte" in r.lower()
    assert x.cfg["catalogo"]["1"]["titulo"] == "Devil May Cry 3"
    assert x.qbt.added == []


def test_magnet_com_console_nao_e_engolido_pelo_catalogo(x):
    msg(x, "Hades")
    r = msg(x, f"Switch {MAG}")
    assert r.startswith("Adicionado (switch)")
    assert x.qbt.added == [(MAG, "switch")]


def test_pc_nao_e_categoria_de_torrent():
    assert bot.parse_console("PC") is None


def test_escolha_experimental_preserva_titulo_para_nova_plataforma(x):
    msg(x, "Hades")
    assert "escolha outra plataforma" in msg(x, "Switch 2")
    assert "Hades" in msg(x, "PC")


def test_pedido_por_nome_inicia_jogo_do_catalogo_compartilhado(x, monkeypatch):
    from dc import familia_servico as fs
    item = {"titulo": "Jogo Teste", "console": "ps2", "gid": "ps2-teste", "magnet": MAG}
    monkeypatch.setattr(fs, "catalogo_guardado", lambda p: {"jogos": [item]})
    chamadas = []
    monkeypatch.setattr(fs, "puxar", lambda p, q, gid: chamadas.append(gid) or "download na fila")
    monkeypatch.setattr(x, "_already", lambda *a: None)
    msg(x, "Jogo Teste")
    assert "download na fila" in msg(x, "PS2")
    assert chamadas == ["ps2-teste"]


def test_pedido_nao_baixa_versao_ambigua(x, monkeypatch):
    from dc import familia_servico as fs
    item = {"titulo": "Jogo Teste", "console": "ps2", "gid": "um", "magnet": MAG}
    monkeypatch.setattr(fs, "catalogo_guardado", lambda p: {"jogos": [item, {**item, "gid": "dois"}]})
    msg(x, "Jogo Teste")
    assert "mais de uma versão" in msg(x, "PS2")
    assert x.qbt.added == []


def test_busca_prowlarr_escolhe_console_e_adiciona_download(x, monkeypatch):
    from dc import prowlarr
    monkeypatch.setattr(prowlarr, "pesquisar", lambda p, titulo: [
        {"titulo": "Jogo Teste PS2", "magnet": MAG, "seeders": 1},
        {"titulo": "Jogo Teste Wii", "magnet": MAG, "seeders": 1}])
    msg(x, "Jogo Teste")
    assert "Pesquisando" in msg(x, "PS2")
    resposta = finish_search(x)
    assert "Jogo Teste PS2" in resposta and "Jogo Teste Wii" not in resposta
    assert "Adicionado (ps2)" in resposta
    assert x.qbt.added == [(MAG, "ps2")]
    assert "1" not in x.cfg["catalogo"]


def test_resultado_busca_expirado_nao_baixa(x):
    x.cfg["resultados_busca"] = {"1": {"console": "ps2", "itens": [{"magnet": MAG}], "at": 0}}
    assert "vencido" in msg(x, "/resultado 1")
    assert x.qbt.added == []


def test_resultado_torrent_e_enviado_ao_qbittorrent(x, monkeypatch):
    from dc import prowlarr
    monkeypatch.setattr(prowlarr, "pesquisar", lambda p, titulo: [
        {"titulo": "Jogo PS2", "magnet": "", "download_url": "http://localhost:9696/download"}])
    monkeypatch.setattr(prowlarr, "baixar_torrent", lambda p, url: TORRENT)
    monkeypatch.setattr(x, "_already", lambda *a: None)
    msg(x, "Jogo")
    msg(x, "PS2")
    resposta = finish_search(x)
    assert "Jogo PS2" in resposta and "Adicionado (ps2)" in resposta
    assert x.qbt.added == [("resultado.torrent", "ps2")]


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


def test_plataforma_no_botao_executa_busca(x, monkeypatch):
    from dc import prowlarr
    monkeypatch.setattr(prowlarr, "pesquisar", lambda *args: [
        {"titulo": "Jogo Teste PS2", "magnet": MAG, "seeders": 1}])
    x.send(9, msg(x, "Jogo Teste"))
    button = x._button("PS2", "PS2")
    x.handle_callback({"id": "q", "from": {"id": 1}, "data": button["callback_data"],
                       "message": {"chat": {"id": 9}}})
    assert "Adicionado (ps2)" in finish_search(x)
    assert x.qbt.added == [(MAG, "ps2")]


def test_nome_direto_unico_agenda_sem_pedir_arquivo_ou_plataforma(x, monkeypatch):
    from dc import catalogo_downloads
    item = {"id": "jogo", "titulo": "Jogo Teste", "console": "nes"}
    monkeypatch.setattr(catalogo_downloads, "pesquisar", lambda *args: [item])
    chamadas = []
    monkeypatch.setattr(catalogo_downloads, "agendar",
                        lambda paths, store, game, chat: chamadas.append((game, chat)) or "op123")
    assert "entrou na fila op123" in msg(x, "Jogo Teste")
    assert chamadas == [(item, 9)]
    assert "1" not in x.cfg["catalogo"]


def test_nome_multiplataforma_usa_plataforma_escolhida(x, monkeypatch):
    from dc import catalogo_downloads
    itens = [{"id": "nes", "titulo": "Jogo Teste", "console": "nes"},
             {"id": "snes", "titulo": "Jogo Teste", "console": "snes"}]
    monkeypatch.setattr(catalogo_downloads, "pesquisar",
                        lambda paths, title, console=None: [i for i in itens if not console or i["console"] == console])
    chamadas = []
    monkeypatch.setattr(catalogo_downloads, "agendar",
                        lambda paths, store, item, chat: chamadas.append(item["console"]) or "op")
    assert "qual plataforma" in msg(x, "Jogo Teste")
    assert chamadas == []
    assert "entrou na fila" in msg(x, "SNES")
    assert chamadas == ["snes"]


def test_busca_lenta_nao_bloqueia_comandos(x, monkeypatch):
    import threading
    from dc import prowlarr
    aguardando = threading.Event()
    iniciou = threading.Event()
    def pesquisar(*args):
        iniciou.set()
        aguardando.wait(3)
        return []
    monkeypatch.setattr(prowlarr, "pesquisar", pesquisar)
    try:
        msg(x, "Jogo Teste")
        assert "Pesquisando" in msg(x, "NES")
        assert iniciou.wait(1)
        assert not x.searches[1][1].done()
        assert "comandos" in msg(x, "/help")
    finally:
        aguardando.set()
        finish_search(x)


def test_pedido_sem_fonte_retoma_apos_reabrir_bot(x, monkeypatch):
    from dc import prowlarr
    msg(x, "Jogo Teste")
    msg(x, "PS2")
    assert "aguardando uma fonte" in finish_search(x)
    x.cfg["catalogo"]["1"]["next_retry_at"] = 0
    x.save_cfg()
    novo = bot.Bot(x.paths, "TOK")
    novo.qbt = x.qbt
    novo.call = x.call
    novo.sent = x.sent
    monkeypatch.setattr(prowlarr, "pesquisar", lambda *args: [
        {"titulo": "Jogo Teste PS2", "magnet": MAG, "seeders": 1}])
    novo.retry_catalog_requests()
    assert "Adicionado (ps2)" in finish_search(novo)
    assert novo.qbt.added == [(MAG, "ps2")]


def test_busca_generica_preserva_escolha_de_titulo(x, monkeypatch):
    from dc import prowlarr
    monkeypatch.setattr(prowlarr, "pesquisar", lambda *args: [
        {"titulo": "Jogo Teste 2 PS2", "magnet": MAG, "seeders": 50}])
    msg(x, "Jogo Teste")
    msg(x, "PS2")
    assert "Escolha o título" in finish_search(x)
    assert x.qbt.added == []


def test_download_concluido_notifica_chat_uma_vez(x):
    op = x.store.enqueue("catalog-download", {"item": {"titulo": "Jogo Teste"}, "chat": 9})
    x.store.claim(op)
    x.store.finish(op, True, result={"phase": "installed", "message": "Instalado na biblioteca."})
    x.notify_catalog_downloads()
    x.notify_catalog_downloads()
    assert [p["text"] for p in x.sent] == ["Jogo Teste\nInstalado na biblioteca."]
