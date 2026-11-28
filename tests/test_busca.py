"""dc/busca.py — interpretação da consulta, relevância, deduplicação e provedores."""
import io
import json

import pytest

from dc import busca, prowlarr
from dc.paths import get_paths


@pytest.mark.parametrize("texto,termos,console", [
    ("god", "god", None), ("god PSP", "god", "psp"), ("god ps2", "god", "ps2"), ("PS2 god of war", "god of war", "ps2"),
    ("Resident Evil", "Resident Evil", None), ("mario kart wii", "mario kart", "wii"),
    ("zelda nintendo 3ds", "zelda", "n3ds"), ("halo xbox 360", "halo", "x360"), ("Hades pc", "Hades", "pc"),
])
def test_interpretar_plataforma_no_comeco_ou_no_fim(texto, termos, console):
    q = busca.interpretar(texto)
    assert (q["termos"], q["console"]) == (termos, console)


def test_interpretar_regiao_idioma_e_abreviacao():
    q = busca.interpretar("re4 pt-br usa")
    assert q["busca"] == "resident evil 4" and q["ptbr"] and q["regiao"] == "EUA"
    assert busca.interpretar("usa")["termos"] == "usa"  # uma palavra só nunca vira filtro


def test_relevancia_aceita_parcial_e_erro_de_digitacao():
    assert busca.relevancia("God of War (USA)", "god") >= 0.9
    assert busca.relevancia("Resident Evil 4 [PS2]", "resident evil") >= 0.9
    assert busca.relevancia("Resident Evil 4", "resident evl") >= 0.6  # erro comum
    assert busca.relevancia("Kingdom Hearts", "king") >= 0.6  # começo da palavra
    assert busca.relevancia("Goddess Story", "god of war") < 0.6


def test_metadados_do_titulo():
    assert busca.regiao_de("Jogo (USA)") == "EUA" and busca.regiao_de("Jogo [PAL]") == "Europa"
    assert busca.formato_de("Jogo [PS2][ISO]") == "ISO" and busca.formato_de("jogo.chd") == "CHD"
    assert busca.console_de("God of War [PS2][PAL]") == "ps2"
    r = busca.resultado("prowlarr", "x", "Final Fantasy Tactics (BR) (T1.6.4)", "psx")
    assert r["ptbr"] is True


def test_deduplica_mesma_versao_mas_mantem_plataformas_e_regioes():
    a = busca.resultado("prowlarr", "1", "Jogo (USA)", "ps2", tamanho=2**30, seeders=5)
    b = busca.resultado("internet_archive", "2", "Jogo (USA)", "ps2", tamanho=2**30)
    c = busca.resultado("prowlarr", "3", "Jogo (Europe)", "ps2", tamanho=2**30)
    d = busca.resultado("prowlarr", "4", "Jogo (USA)", "psp", tamanho=2**29)
    out = busca.deduplicar([a, b, c, d])
    assert len(out) == 3 and b in out and a not in out  # Internet Archive vem antes do Prowlarr


def test_estado_por_fonte_e_resultado_parcial(tmp_path):
    def ok(p, q, **kw):
        return [busca.resultado("catalogo", "j", "Jogo", "nes", acao={})]

    def cai(p, q, **kw):
        raise OSError("refused")
    paths = get_paths(tmp_path).ensure()
    r = busca.pesquisar(paths, "jogo", provedores=["catalogo", "prowlarr"], funcs={"catalogo": ok, "prowlarr": cai})
    assert r["fontes"] == {"catalogo": busca.OK, "prowlarr": busca.FORA} and len(r["resultados"]) == 1


def test_ia_direto_tira_o_indexador_do_prowlarr(tmp_path):
    vistos = {}

    def prow(p, q, **kw):
        vistos.update(kw)
        return []
    paths = get_paths(tmp_path).ensure()
    busca.pesquisar(paths, "x", provedores=["internet_archive", "prowlarr"],
                    funcs={"internet_archive": lambda p, q, **k: [], "prowlarr": prow})
    assert "internetarchive" in vistos["ignorar_indexadores"]


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_internet_archive_honesto_e_licenca_nao_verificada(tmp_path):
    pedidos = []
    docs = [{"identifier": "super-tilt-bro", "title": "Super Tilt Bro [NES]", "item_size": 41000,
             "licenseurl": "http://www.wtfpl.net/"},
            {"identifier": "../etc/passwd", "title": "malicioso"},
            {"identifier": "dos-game", "title": "Algum Jogo", "collection": ["softwarelibrary_msdos_games"]}]

    def abrir(req, timeout):
        pedidos.append(req)
        return Resp(json.dumps({"response": {"docs": docs}}).encode())
    out = busca._p_internet_archive(get_paths(tmp_path).ensure(), busca.interpretar("tilt"), abrir=abrir)
    assert pedidos[0].get_header("User-agent").startswith("DeckCommander/")
    assert [r["acao"]["id"] for r in out] == ["super-tilt-bro", "dos-game"]  # identificador perigoso descartado
    assert out[0]["console"] == "nes" and out[0]["licenca_verificada"] is False and out[1]["console"] == "pc"


def test_prowlarr_ignora_indexador_coberto_por_outra_fonte(tmp_path):
    paths = get_paths(tmp_path).ensure()
    (paths.config / "prowlarr.json").write_text(json.dumps({"url": "http://127.0.0.1:9696", "api_key": "k",
                                                              "indexer_ids": []}))
    urls = []

    def abrir(req, timeout):
        urls.append(req.full_url)
        if req.full_url.endswith("/api/v1/indexer"):
            return Resp(json.dumps([{"id": 1, "name": "Internet Archive", "definitionName": "internetarchive",
                                     "enable": True}, {"id": 7, "name": "Outro", "enable": True}]).encode())
        return Resp(json.dumps([{"title": "Jogo", "magnetUrl": "magnet:?xt=urn:btih:" + "a" * 40, "size": 123,
                                 "indexer": "Outro"}]).encode())
    out = prowlarr.pesquisar(paths, "jogo", abrir=abrir, ignorar=("internetarchive",))
    assert any("indexerIds=7" in u for u in urls) and not any("indexerIds=1" in u for u in urls)
    assert out[0]["tamanho"] == 123 and out[0]["indexador"] == "Outro"


def test_prowlarr_so_com_o_indexador_coberto_diz_nao_configurado(tmp_path):
    paths = get_paths(tmp_path).ensure()
    (paths.config / "prowlarr.json").write_text(json.dumps({"url": "http://127.0.0.1:9696", "api_key": "k"}))

    def abrir(req, timeout):
        return Resp(json.dumps([{"id": 1, "name": "Internet Archive", "definitionName": "internetarchive",
                                 "enable": True}]).encode())
    with pytest.raises(prowlarr.SemIndexadores):
        prowlarr.pesquisar(paths, "jogo", abrir=abrir, ignorar=("internetarchive",))
    assert busca._estado_de_erro(prowlarr.SemIndexadores("x")) == busca.NAO_CONFIG


def test_sessao_expira_pertence_ao_dono_e_limita_quantidade():
    cfg = {}
    resp = {"consulta": busca.interpretar("x"), "fontes": {}, "resultados": [busca.resultado("catalogo", "1", "X", "nes")]}
    sid = busca.nova_sessao(cfg, 1, resp, agora=1000)
    assert busca.sessao(cfg, sid, 1, agora=1000) and busca.sessao(cfg, sid, 2, agora=1000) is None
    assert busca.sessao(cfg, sid, 1, agora=1000 + busca.TTL_SESSAO + 1) is None
    for i in range(20):
        busca.nova_sessao(cfg, 1, resp, agora=2000 + i)
    assert len(cfg["buscas"]) <= busca.MAX_SESSOES


def test_paginacao_e_filtros():
    rs = [busca.resultado("prowlarr", str(i), f"Jogo {i}", "ps2" if i % 2 else "psp", acao={}) for i in range(15)]
    s = {"consulta": busca.interpretar("jogo"), "fontes": {"prowlarr": "ok"}, "resultados": rs, "filtro": None}
    def plano(bt):
        return [x for b in bt for x in (b if isinstance(b, list) else [b])]
    txt, bt = busca.pagina(s, "abc", 0, lambda c: c)
    assert "página 1/3" in txt and ("Próxima ▶", "/bp abc 1") in plano(bt) and ("Só ps2", "/bf abc ps2") in plano(bt)
    assert [("Próxima ▶", "/bp abc 1")] in bt and [("Só ps2", "/bf abc ps2"), ("Só psp", "/bf abc psp")] in bt
    linha1 = bt[0]  # cada jogo: detalhes e baixar lado a lado (teste real 28/11/2026)
    assert linha1[0][1].startswith("/bi abc ") and linha1[1] == ("⬇️ 1", f"/bd abc {rs[0]['rid']} deck")
    txt, bt = busca.pagina(s, "abc", 2, lambda c: c)
    assert ("◀ Anterior", "/bp abc 1") in plano(bt) and not any(b[0].startswith("Próxima") for b in plano(bt))
    s["filtro"] = "psp"
    txt, _ = busca.pagina(s, "abc", 0, lambda c: c)
    assert "8 para baixar" in txt


def test_fonte_travada_nao_segura_a_busca_alem_do_tempo(tmp_path, monkeypatch):
    import threading
    import time
    libera = threading.Event()

    def travada(p, q, **kw):
        libera.wait(10)
        return []
    monkeypatch.setitem(busca.TIMEOUT, "prowlarr", 0.3)
    paths = get_paths(tmp_path).ensure()
    t0 = time.monotonic()
    try:
        r = busca.pesquisar(paths, "jogo", provedores=["catalogo", "prowlarr"],
                            funcs={"catalogo": lambda p, q, **k: [], "prowlarr": travada})
    finally:
        libera.set()
    assert time.monotonic() - t0 < 3 and r["fontes"]["prowlarr"] == busca.TEMPO


def test_erro_de_digitacao_corrigido_antes_das_fontes_remotas(tmp_path):
    pedidos = []

    def remota(p, q, **kw):  # como a fonte real: só acha a palavra exata
        pedidos.append(q["busca"])
        return [busca.resultado("internet_archive", "re", "Resident Evil 2 (USA)", "psx", acao={})]             if "evil" in q["busca"] else []
    paths = get_paths(tmp_path).ensure()
    r = busca.pesquisar(paths, "resident evl", provedores=["internet_archive"], funcs={"internet_archive": remota})
    assert pedidos == ["resident evl", "resident evil"] and r["consulta"]["corrigido"] == "resident evil"
    assert r["resultados"]
    pedidos.clear()
    busca.pesquisar(paths, "hollow knight", provedores=["internet_archive"],
                    funcs={"internet_archive": lambda p, q, **k: pedidos.append(q["busca"]) or [
                        busca.resultado("internet_archive", "h", "Hollow Knight", "pc", acao={})]})
    assert pedidos == ["hollow knight"]  # nome certo com resultado nunca é "corrigido"
    assert busca.corrigir("god of war 2", busca.VOCABULARIO) == "god of war 2"  # certo continua certo
    txt, _ = busca.pagina({**r, "filtro": None}, "s", 0, lambda c: c)
    assert "mostrando resultados para «resident evil»" in txt


def test_prowlarr_tempo_esgotado_e_diferente_de_fora_do_ar(tmp_path):
    paths = get_paths(tmp_path).ensure()
    (paths.config / "prowlarr.json").write_text(json.dumps({"url": "http://127.0.0.1:9696", "api_key": "k"}))

    def lento(req, timeout):
        raise TimeoutError("timed out")

    def caido(req, timeout):
        raise ConnectionRefusedError("refused")
    with pytest.raises(prowlarr.BuscaTempo):
        prowlarr.pesquisar(paths, "x", abrir=lento)
    with pytest.raises(prowlarr.BuscaErro) as e:
        prowlarr.pesquisar(paths, "x", abrir=caido)
    assert not isinstance(e.value, prowlarr.BuscaTempo)
    assert busca._estado_de_erro(prowlarr.BuscaTempo("x")) == busca.TEMPO
    assert busca._estado_de_erro(prowlarr.BuscaErro("x")) == busca.FORA


def test_plataforma_pelo_assunto_e_consulta_filtrada_na_fonte(tmp_path):
    """Teste real 28/11/2026: 'God of War: Ghost of Sparta' não diz PSP no título, só no assunto; sumia do filtro PSP."""
    pedidos = []
    docs = [{"identifier": "gow-gos", "title": "God of War: Ghost of Sparta",
             "subject": ["God of War: Ghost of Sparta", "God of War", "PSP", "ROM", "Game", "2010"]},
            {"identifier": "gow2", "title": "God Of War II (USA)", "subject": "Sony PlayStation 2"}]

    def abrir(req, timeout):
        pedidos.append(req.full_url)
        return Resp(json.dumps({"response": {"docs": docs}}).encode())
    paths = get_paths(tmp_path).ensure()
    out = busca._p_internet_archive(paths, busca.interpretar("god of war psp"), abrir=abrir)
    assert [r["console"] for r in out] == ["psp", "ps2"]
    import urllib.parse
    consulta = urllib.parse.unquote_plus(pedidos[0])
    assert "subject:(psp OR \"playstation portable\")" in consulta
