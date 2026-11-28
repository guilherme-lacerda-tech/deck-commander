"""Busca multiplataforma pelo Telegram (pedido do dono, 28/11/2026): "god" procura em todas as plataformas,
"god psp" só no PSP; a lista tem botões com identidade estável; detalhe -> escolher dispositivo -> baixar.
Substitui o fluxo antigo "nome -> qual plataforma?" mantendo as garantias dele (versão ambígua nunca baixa
sozinha, pedido sem fonte fica guardado e é retomado, busca lenta não trava o bot)."""
import threading

import pytest

from dc import bot, busca, syncer
from dc.paths import get_paths

MAG = "magnet:?xt=urn:btih:" + "a" * 40 + "&dn=Jogo"
MAG2 = "magnet:?xt=urn:btih:" + "b" * 40 + "&dn=Jogo2"
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
    b.call = lambda method, **kw: b.sent.append(kw) or []
    b.qbt = FakeQbt()
    b.limited = lambda uid: False
    monkeypatch.setattr(syncer, "_cfg", lambda p: {"downloads_root": str(tmp_path / "dl")})
    monkeypatch.setattr(b, "_already", lambda *a: None)
    return b


def fontes(monkeypatch, **provs):
    """Troca os provedores reais por funções de teste (paths, q, **kw) -> [resultado]."""
    monkeypatch.setattr(busca, "PROVEDORES", {**{k: (lambda p, q, **kw: []) for k in busca.PROVEDORES}, **provs})
    monkeypatch.setattr(busca, "config", lambda paths: {"provedores": list(provs)})


def prowl(*itens):
    def f(paths, q, **kw):
        return [busca.resultado("prowlarr", i["titulo"], i["titulo"], busca.console_de(i["titulo"]),
                                seeders=i.get("seeders", 1), tamanho=i.get("tamanho"),
                                acao={"tipo": "magnet", "magnet": i["magnet"]} if i.get("magnet")
                                else {"tipo": "prowlarr", "download_url": i["url"]}) for i in itens]
    return f


def msg(b, text, uid=1):
    return b.handle_message({"from": {"id": uid}, "chat": {"id": 9}, "text": text})


def terminar(b):
    for v in list(b.buscas.values()):
        v["future"].result(timeout=5)
    b.notify_buscas()
    return b.sent[-1]


def botoes(envio):
    import json
    kb = json.loads(envio.get("reply_markup", '{"inline_keyboard": []}'))["inline_keyboard"]
    return [btn for linha in kb for btn in linha]


def tocar(b, envio, rotulo_comeca):
    btn = next(bt for bt in botoes(envio) if bt["text"].startswith(rotulo_comeca))
    b.handle_callback({"id": "q", "from": {"id": 1}, "data": btn["callback_data"], "message": {"chat": {"id": 9}}})
    return b.sent[-1]


def test_nome_sozinho_procura_em_todas_as_plataformas_sem_baixar(x, monkeypatch):
    fontes(monkeypatch, prowlarr=prowl({"titulo": "God of War [PS2] (USA)", "magnet": MAG},
                                       {"titulo": "God of War Ghost of Sparta [PSP]", "magnet": MAG2},
                                       {"titulo": "Goddess Story [NES]", "magnet": MAG}))
    assert "em todas as plataformas" in msg(x, "god of war")
    lista = terminar(x)["text"]
    assert "God of War [PS2] (USA)" in lista and "Ghost of Sparta" in lista and "Goddess" not in lista
    assert "PlayStation 2" in lista or "PS2" in lista
    assert x.qbt.added == []  # lista nunca baixa sozinha (antes: versão ambígua)


def test_plataforma_na_mensagem_restringe(x, monkeypatch):
    fontes(monkeypatch, prowlarr=prowl({"titulo": "God of War [PS2]", "magnet": MAG},
                                       {"titulo": "God of War Ghost of Sparta [PSP]", "magnet": MAG2}))
    assert "(PSP)" in msg(x, "god psp")
    lista = terminar(x)["text"]
    assert "Sparta" in lista and "[PS2]" not in lista


def test_titulo_com_nome_de_console_acha_o_jogo(x, monkeypatch):
    fontes(monkeypatch, prowlarr=prowl({"titulo": "Mario Kart Wii (Europe)", "magnet": MAG}))
    msg(x, "Mario Kart Wii")
    assert "Mario Kart Wii (Europe)" in terminar(x)["text"]


def test_detalhe_mostra_dispositivos_e_baixa_uma_vez_so(x, monkeypatch):
    fontes(monkeypatch, prowlarr=prowl({"titulo": "Jogo Teste [PS2]", "magnet": MAG, "tamanho": 2 * 2**30}))
    msg(x, "jogo teste")
    lista = terminar(x)
    detalhe = tocar(x, lista, "1.")
    assert "Steam Deck" in detalhe["text"] and "RG505" in detalhe["text"] and "2 GB" in detalhe["text"]
    assert "desempenho inconsistente no RG505" in detalhe["text"]  # PS2 no RG505: política, não chute
    feito = tocar(x, detalhe, "⬇️ Baixar no Steam Deck")
    assert feito["text"].startswith("Adicionado (ps2)")
    de_novo = tocar(x, detalhe, "⬇️ Baixar no Steam Deck")  # toque duplo / botão repetido
    assert "já foi pedido" in de_novo["text"]
    assert x.qbt.added == [(MAG, "ps2")]


def test_resultado_torrent_do_prowlarr_vai_para_o_qbittorrent(x, monkeypatch):
    from dc import prowlarr
    fontes(monkeypatch, prowlarr=prowl({"titulo": "Jogo [PS2]", "url": "http://localhost:9696/dl"}))
    monkeypatch.setattr(prowlarr, "baixar_torrent", lambda p, url: TORRENT)
    msg(x, "jogo")
    tocar(x, tocar(x, terminar(x), "1."), "⬇️")
    assert "Adicionado" in x.sent[-1]["text"] and x.qbt.added == [("resultado.torrent", "ps2")]


def test_catalogo_verificado_agenda_pela_fila_propria(x, monkeypatch):
    from dc import catalogo_downloads
    item = {"id": "jogo", "titulo": "Jogo Teste", "console": "nes", "license": "MIT", "source_url": "https://x",
            "filename": "j.nes", "size": 10}
    fontes(monkeypatch, catalogo=lambda p, q, **kw: [busca.resultado(
        "catalogo", "jogo", "Jogo Teste", "nes", tamanho=10, licenca="MIT", licenca_verificada=True,
        acao={"tipo": "catalogo", "item": item})])
    chamadas = []
    monkeypatch.setattr(catalogo_downloads, "agendar", lambda paths, store, it, chat: chamadas.append(it) or "op1")
    msg(x, "jogo teste")
    detalhe = tocar(x, terminar(x), "1.")
    assert "Licença: MIT" in detalhe["text"] and "não verificada" not in detalhe["text"]
    assert "entrou na fila op1" in tocar(x, detalhe, "⬇️")["text"]
    assert chamadas == [item]


def test_familia_puxa_do_outro_deck(x, monkeypatch):
    from dc import familia_servico as fs
    fontes(monkeypatch, familia=lambda p, q, **kw: [busca.resultado(
        "familia", "ps2-teste", "Jogo Teste", "ps2", acao={"tipo": "familia", "gid": "ps2-teste"})])
    puxados = []
    monkeypatch.setattr(fs, "puxar", lambda p, q, gid: puxados.append(gid) or "⬇️ download na fila")
    msg(x, "jogo teste")
    tocar(x, tocar(x, terminar(x), "1."), "⬇️")
    assert puxados == ["ps2-teste"]


def test_fonte_que_falhou_nao_vira_lista_vazia(x, monkeypatch):
    def cai(p, q, **kw):
        raise OSError("connection refused")
    fontes(monkeypatch, prowlarr=cai)
    msg(x, "jogo")
    r = terminar(x)["text"]
    assert "falharam" in r and "Nenhum resultado" not in r


def test_parcial_avisa_qual_fonte_falhou(x, monkeypatch):
    def lenta(p, q, **kw):
        raise TimeoutError("timed out")
    fontes(monkeypatch, familia=lambda p, q, **kw: [busca.resultado("familia", "g", "Jogo Teste", "ps2",
                                                                    acao={"tipo": "familia", "gid": "g"})],
           prowlarr=lenta)
    msg(x, "jogo teste")
    r = terminar(x)["text"]
    assert "Jogo Teste" in r and "Prowlarr: tempo esgotado" in r and "parcial" in r


def test_sem_resultado_oferece_aviso_e_retoma_depois(x, monkeypatch):
    achou = []
    fontes(monkeypatch, prowlarr=lambda p, q, **kw: achou)
    msg(x, "Hades pc")
    vazio = terminar(x)
    assert "Nenhum resultado" in vazio["text"]
    guardado = tocar(x, vazio, "🔔")
    assert "Guardei «Hades pc»" in guardado["text"]
    # bot reaberto: o pedido continua guardado e volta a ser pesquisado
    novo = bot.Bot(x.paths, "TOK")
    novo.sent, novo.call, novo.qbt = x.sent, x.call, x.qbt
    for v in novo.cfg["vigias"].values():
        v["proxima"] = 0
    novo.retry_catalog_requests()
    for v in list(novo.buscas.values()):
        v["future"].result(timeout=5)
    n = len(x.sent)
    novo.notify_buscas()
    assert len(x.sent) == n  # ainda nada: silêncio
    achou.append(busca.resultado("prowlarr", "h", "Hades [PC]", "pc", acao={"tipo": "magnet", "magnet": MAG}))
    for v in novo.cfg["vigias"].values():
        v["proxima"] = 0
    novo.retry_catalog_requests()
    for v in list(novo.buscas.values()):
        v["future"].result(timeout=5)
    novo.notify_buscas()
    assert "🔔 Apareceu" in x.sent[-1]["text"] and "Hades [PC]" in x.sent[-1]["text"]
    assert novo.cfg["vigias"] == {}


def test_botao_de_busca_antiga_ou_de_outra_pessoa_nao_vale(x, monkeypatch):
    fontes(monkeypatch, prowlarr=prowl({"titulo": "Jogo [PS2]", "magnet": MAG}))
    msg(x, "jogo")
    lista = terminar(x)
    sid = x.cfg["ultima_busca"]["1"]
    x.cfg["buscas"][sid]["at"] -= busca.TTL_SESSAO + 1
    assert "antiga ou vencida" in tocar(x, lista, "1.")["text"]
    x.cfg["allowed"].append(2)
    x.cfg["buscas"][sid]["at"] += busca.TTL_SESSAO + 1
    assert "antiga ou vencida" in msg(x, f"/bi {sid} {x.cfg['buscas'][sid]['resultados'][0]['rid']}", uid=2)
    assert "não existe nesta busca" in msg(x, f"/bd {sid} ffffffffff deck")
    assert x.qbt.added == []


def test_digitar_a_plataforma_depois_filtra_a_lista(x, monkeypatch):
    fontes(monkeypatch, prowlarr=prowl({"titulo": "God of War [PS2]", "magnet": MAG},
                                       {"titulo": "God of War Ghost of Sparta [PSP]", "magnet": MAG2}))
    msg(x, "god of war")
    terminar(x)
    r = msg(x, "PSP")
    assert "Sparta" in r and "[PS2]" not in r and "filtro" in r
    assert x.qbt.added == []


def test_busca_lenta_nao_bloqueia_comandos(x, monkeypatch):
    libera, iniciou = threading.Event(), threading.Event()

    def lenta(p, q, **kw):
        iniciou.set()
        libera.wait(3)
        return []
    fontes(monkeypatch, prowlarr=lenta)
    try:
        msg(x, "Jogo Teste")
        assert iniciou.wait(2)
        assert "comandos" in msg(x, "/help")
        assert "Ainda estou pesquisando" in msg(x, "Outro Jogo")
    finally:
        libera.set()
        terminar(x)


def test_switch2_nunca_baixa(x, monkeypatch):
    fontes(monkeypatch, prowlarr=prowl({"titulo": "Jogo [Switch 2]", "magnet": MAG}))
    msg(x, "jogo")
    detalhe = tocar(x, terminar(x), "1.")
    assert not any(b["text"].startswith("⬇️") for b in botoes(detalhe))
