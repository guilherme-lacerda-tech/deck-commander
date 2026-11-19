"""Detonado por capítulo (pedido 13/11/2026): índice da StrategyWiki em ordem, texto limpo e traduzido, guardado."""
from dc import detonado as D
from dc.paths import get_paths
from types import SimpleNamespace

TOC = """<noinclude>{{Header Nav|game=Pokémon FireRed and LeafGreen}}</noinclude>
{{h2|[[Pokémon FireRed and LeafGreen/Gameplay|Gameplay]]}}
* [[Pokémon FireRed and LeafGreen/Controls|Controls]]
{{h2|[[Pokémon FireRed and LeafGreen/Walkthrough|Walkthrough]]|center}}
{{h3|Boulder Badge}}
* [[Pokémon FireRed and LeafGreen/Pallet Town|Pallet Town]]
* [[Pokémon FireRed and LeafGreen/Route 1|Route 1]]
{{h3|Cascade Badge}}
* [[Pokémon FireRed and LeafGreen/Mt. Moon|Mt. Moon]]
{{h2|Appendices}}
* [[Pokémon FireRed and LeafGreen/Secrets|Secrets]]
"""
PAGINA = """{{Header Nav|game=X}}
[[File:Mapa.png|thumb|O [[mapa]] da cidade]]
== Pallet Town ==
Talk to '''Professor Oak''' and pick a [[Pokémon FireRed and LeafGreen/Pokémon|Pokémon]].<ref>nota</ref>
Then press {{gba|A}} near {{psx|T}}.
* Get the [[Town Map]]
{| class="wikitable"
| tabela || some
|}
"""


def _api(params):
    if params.get("list") == "search":
        return {"query": {"search": [{"title": "Pokemon FireRed"}, {"title": "Pokémon Stadium/Rules"}]}}
    if params.get("redirects") and params.get("action") == "query":
        return {"query": {"redirects": [{"from": "Pokemon FireRed", "to": "Pokémon FireRed and LeafGreen"}]}}
    if params.get("action") == "query":
        return {"query": {"pages": [{"title": "Pokémon FireRed and LeafGreen/Table of Contents"},
                                    {"title": "Pokémon Stadium/Table of Contents", "missing": True}]}}
    if params["page"].endswith("Table of Contents"):
        return {"parse": {"wikitext": TOC}}
    return {"parse": {"wikitext": PAGINA}}


def test_acha_o_jogo_e_o_indice_por_ginasio():
    assert D._sem_marcas("Pokemon FireRed (BR) [GBA]") == "Pokemon FireRed"
    assert D._sem_marcas("God of War 1 (Dublado)") == "God of War"
    jogo = D.achar_jogo("Pokemon FireRed (BR)", api=_api)
    assert jogo == "Pokémon FireRed and LeafGreen"  # redirecionamento seguido
    caps = D.indice(jogo, api=_api)
    assert [(c["grupo"], c["titulo"]) for c in caps] == [
        ("Boulder Badge", "Pallet Town"), ("Boulder Badge", "Route 1"), ("Cascade Badge", "Mt. Moon")]


def test_texto_limpo_com_botoes():
    p = D.limpar_wikitext(PAGINA)
    assert p[0] == "Pallet Town"
    assert p[1].startswith("Talk to Professor Oak and pick a Pokémon.")
    assert "[A]" in p[1] and "[△]" in p[1]  # os ícones de botão viram texto
    assert "• Get the Town Map" in p and not any("tabela" in x or "mapa" in x.lower() for x in p)


def test_capitulo_traduz_uma_vez_e_lembra_onde_parou(tmp_path):
    paths = get_paths(tmp_path).ensure()
    D.preparar(paths, "gba-pokemon", "Pokemon FireRed (BR)", api=_api)
    chamadas = []

    def tradutor(paths, gid, textos):
        chamadas.append(len(textos))
        return ["PT: " + t for t in textos]

    c = D.capitulo(paths, "gba-pokemon", 1, api=_api, tradutor=tradutor)
    assert c["traduzido"] and c["titulo"] == "PT: Route 1" and c["paragrafos"][0] == "PT: Pallet Town"
    D.capitulo(paths, "gba-pokemon", 1, api=lambda p: 1 / 0, tradutor=tradutor)  # 2ª vez: do disco, sem internet
    assert len(chamadas) == 1  # traduziu uma vez só
    assert D.titulos(paths, "gba-pokemon") == ["Pallet Town", "PT: Route 1", "Mt. Moon"]  # lista do painel
    D.marcar(paths, "gba-pokemon", 2)
    assert D.info(paths, "gba-pokemon")["atual"] == 2
    D.preparar(paths, "gba-pokemon", "Pokemon FireRed (BR)", api=_api)
    assert D.info(paths, "gba-pokemon")["atual"] == 2  # buscar de novo não perde onde você estava


def test_empty_old_cache_is_downloaded_again_instead_of_being_called_ready(tmp_path):
    paths = get_paths(tmp_path).ensure()
    D.preparar(paths, "gba-pokemon", "Pokemon FireRed", api=_api)
    vazio = paths.data / "detonado/gba-pokemon/000.json"
    vazio.parent.mkdir(parents=True, exist_ok=True)
    vazio.write_text('{"original": [], "pt": null}')
    c = D.capitulo(paths, "gba-pokemon", 0, api=_api,
                    tradutor=lambda _p, _g, textos: ["PT: " + x for x in textos])
    assert c["traduzido"] and c["paragrafos"] and D.pronto(paths, "gba-pokemon") is False


def test_full_download_never_reports_success_with_missing_text(tmp_path):
    paths = get_paths(tmp_path).ensure()
    D.preparar(paths, "gba-pokemon", "Pokemon FireRed", api=_api)
    out = D.baixar_tudo(paths, "gba-pokemon", "Pokemon FireRed",
                         api=lambda _p: {"parse": {"wikitext": ""}}, tradutor=lambda *_a: None)
    assert out.startswith("detonado não terminou:") and not D.pronto(paths, "gba-pokemon")
    assert D.erro(paths, "gba-pokemon") == out


def test_sem_ia_fica_o_original(tmp_path):
    paths = get_paths(tmp_path).ensure()
    D.preparar(paths, "gba-pokemon", "Pokemon FireRed", api=_api)
    c = D.capitulo(paths, "gba-pokemon", 0, api=_api, tradutor=lambda *a: None)
    assert not c["traduzido"] and c["paragrafos"][0] == "Pallet Town"


def test_detonado_so_fica_pronto_quando_tudo_esta_em_portugues_e_pode_ser_agendado(tmp_path):
    paths = get_paths(tmp_path).ensure()
    D.preparar(paths, "gba-pokemon", "Pokemon FireRed", api=_api)
    assert not D.pronto(paths, "gba-pokemon")
    calls = []
    assert D.agendar(paths, "gba-pokemon", "Pokemon FireRed",
                     run=lambda cmd, **kw: calls.append(cmd) or SimpleNamespace(returncode=0))
    assert calls[0][-3:] == ["dc.detonado", "baixar", "gba-pokemon"]
    D.baixar_tudo(paths, "gba-pokemon", "Pokemon FireRed", api=_api,
                   tradutor=lambda _p, _g, textos: ["PT: " + x for x in textos], log=lambda _m: None)
    assert D.pronto(paths, "gba-pokemon")
    assert not D.agendar(paths, "gba-pokemon", "Pokemon FireRed", run=lambda *_a, **_k: 1)


def test_existing_library_gets_one_offline_guide_at_a_time_and_retries_later(tmp_path, monkeypatch):
    """Jogo que já existia antes do recurso entra na fila; uma falha não vira martelada na rede."""
    paths = get_paths(tmp_path).ensure()
    (paths.data / "launch-map.json").write_text(__import__("json").dumps({
        "ps2-dmc": {"title": "Devil May Cry 3", "console": "ps2"},
        "psp-pronto": {"title": "God of War", "console": "psp"},
        "pc-x": {"title": "PC", "console": "pc"},
    }))
    monkeypatch.setattr(D, "pronto", lambda _p, gid: gid == "psp-pronto")
    chamadas = []
    monkeypatch.setattr(D, "agendar", lambda _p, gid, titulo, run=None: chamadas.append((gid, titulo)) or True)
    assert D.agendar_proximo(paths, now=1000) == "detonado: preparando em português Devil May Cry 3"
    assert chamadas == [("ps2-dmc", "Devil May Cry 3")]
    assert D.agendar_proximo(paths, now=1001) is None  # não repete enquanto está em preparação
    assert D.agendar_proximo(paths, now=1000 + D.FILA_ESPERA + 1)


def test_detonado_vai_junto_para_o_jogo_traduzido(tmp_path):
    """God of War do PSP (14/11/2026): a versão (PT-BR) substitui a russa; os 9 capítulos traduzidos vão junto."""
    paths = get_paths(tmp_path).ensure()
    D.preparar(paths, "psp-gow-rus", "God of War", jogo="Pokémon FireRed and LeafGreen", api=_api)
    D.marcar(paths, "psp-gow-rus", 2)
    assert D.herdar(paths, "psp-gow-rus", "psp-gow-pt-br")
    assert D.info(paths, "psp-gow-pt-br")["atual"] == 2
    assert not D.herdar(paths, "psp-gow-rus", "psp-gow-pt-br")  # já tem: não sobrescreve
    assert not D.herdar(paths, "nao-existe", "x")


def test_traducao_que_substitui_o_jogo_leva_o_detonado(tmp_path):
    from dc.traducao import run
    paths = get_paths(tmp_path / "dc").ensure()
    D.preparar(paths, "psp-god-of-war-rus", "God of War", jogo="Pokémon FireRed and LeafGreen", api=_api)
    (tmp_path / "roms/psp").mkdir(parents=True)
    rom = tmp_path / "roms/psp/God of War (PT-BR).iso"
    rom.write_bytes(b"\0" * 4096)
    run._herdar_detonado(paths, "psp-god-of-war-rus", rom)
    assert len(list((paths.data / "detonado").iterdir())) == 2
