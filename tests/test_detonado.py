"""Detonado por capítulo (pedido 13/11/2026): índice da StrategyWiki em ordem, texto limpo e traduzido, guardado."""
from dc import detonado as D
from dc.paths import get_paths

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
    D.marcar(paths, "gba-pokemon", 2)
    assert D.info(paths, "gba-pokemon")["atual"] == 2
    D.preparar(paths, "gba-pokemon", "Pokemon FireRed (BR)", api=_api)
    assert D.info(paths, "gba-pokemon")["atual"] == 2  # buscar de novo não perde onde você estava


def test_sem_ia_fica_o_original(tmp_path):
    paths = get_paths(tmp_path).ensure()
    D.preparar(paths, "gba-pokemon", "Pokemon FireRed", api=_api)
    c = D.capitulo(paths, "gba-pokemon", 0, api=_api, tradutor=lambda *a: None)
    assert not c["traduzido"] and c["paragrafos"][0] == "Pallet Town"
