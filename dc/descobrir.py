"""Descobrir jogos: os mais bem avaliados de uma plataforma e/ou de um gênero (pedido do dono, 28/11/2026:
"coloco PS2 e traz os jogos mais bem avaliados… ou temas, por exemplo FPS").

    PS2 · melhores ps2 · top psp   -> mais bem avaliados da plataforma
    fps · rpg · corrida · terror    -> mais bem avaliados do gênero (todas as plataformas)
    fps ps2 · melhores rpg psp      -> os dois juntos

Fonte: Wikidata (sem chave), nota do Metacritic (P444 avaliada por Q150248). Prefere a nota DA PLATAFORMA pedida;
quando o Wikidata só tem a nota de outra versão do jogo, isso é dito (nunca se inventa nota). Códigos de plataforma
e gênero conferidos no Wikidata em 28/11/2026 (nome oficial + uso real em jogos).
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request

USER_AGENT = "DeckCommander/0.11 (+https://github.com/guilherme-lacerda-tech/deck-commander)"
METACRITIC = "Q150248"
CACHE_DIAS = 7

PLATAFORMA_WD = {  # console do Deck Commander -> item do Wikidata (conferido pelo título da Wikipédia)
    "ps2": "Q10680", "psx": "Q10677", "psp": "Q170325", "ps3": "Q10683", "nds": "Q170323", "n3ds": "Q203597",
    "gc": "Q182172", "wii": "Q8079", "wiiu": "Q56942", "switch": "Q19610114", "switch2": "Q122761124",
    "nes": "Q172742", "snes": "Q183259", "n64": "Q184839", "gb": "Q186437", "gbc": "Q203992", "gba": "Q188642",
    "genesis": "Q10676", "sms": "Q209868", "gg": "Q751719", "segacd": "Q1047516", "saturn": "Q200912",
    "dc": "Q184198", "xbox": "Q132020", "x360": "Q48263", "pce": "Q1057377", "pc": "Q1406",
}
GENEROS = {  # palavra em português -> (rótulo, item do Wikidata)
    "fps": ("tiro em primeira pessoa", "Q185029"), "primeira pessoa": ("tiro em primeira pessoa", "Q185029"),
    "tiro": ("tiro", "Q4282636"), "shooter": ("tiro", "Q4282636"),
    "terceira pessoa": ("tiro em terceira pessoa", "Q380266"), "tps": ("tiro em terceira pessoa", "Q380266"),
    "rpg": ("RPG", "Q744038"), "rpg de acao": ("RPG de ação", "Q1422746"), "rpg tatico": ("RPG tático", "Q1529437"),
    "corrida": ("corrida", "Q860750"), "kart": ("kart", "Q18759108"), "luta": ("luta", "Q846224"),
    "plataforma": ("plataforma", "Q828322"), "terror": ("survival horror", "Q333967"),
    "survival horror": ("survival horror", "Q333967"), "esporte": ("esporte", "Q868217"),
    "esportes": ("esporte", "Q868217"), "futebol": ("futebol", "Q1478420"), "estrategia": ("estratégia", "Q472055"),
    "rts": ("estratégia em tempo real", "Q208189"), "aventura": ("ação e aventura", "Q343568"),
    "acao e aventura": ("ação e aventura", "Q343568"), "furtivo": ("furtividade", "Q858523"),
    "stealth": ("furtividade", "Q858523"), "puzzle": ("quebra-cabeça", "Q54767"),
    "quebra cabeca": ("quebra-cabeça", "Q54767"), "musical": ("musical", "Q584105"), "ritmo": ("ritmo", "Q2632782"),
    "beat em up": ("beat 'em up", "Q401831"), "briga de rua": ("beat 'em up", "Q401831"),
    "metroidvania": ("metroidvania", "Q19643088"), "mundo aberto": ("mundo aberto", "Q867123"),
    "simulacao": ("simulação", "Q1610017"), "nave": ("shoot 'em up", "Q1044478"), "shmup": ("shoot 'em up", "Q1044478"),
    "acao": ("ação", "Q270948"), "roguelike": ("roguelike", "Q1143132"), "hack and slash": ("hack and slash", "Q1163960"),
    "sobrevivencia": ("sobrevivência", "Q21030988"), "festa": ("festa", "Q7888616"),
    "visual novel": ("visual novel", "Q689445"),
}


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().casefold()
    return " ".join(re.findall(r"[a-z0-9]+", t))


def interpretar(texto: str) -> dict | None:
    """{"console": ..., "genero": (rótulo, qid)} se a mensagem é SÓ plataforma e/ou gênero (com 'melhores', 'top',
    'jogos de' opcionais). Qualquer outra coisa é nome de jogo -> None (vai para a busca normal)."""
    from .busca import _console_exato
    t = _norm(texto)
    t = re.sub(r"^(?:os |as )?(?:melhores|top|mais bem avaliados|jogos|jogo)(?: jogos)?(?: de| do| da)?\s*", "", t)
    t = re.sub(r"\s*(?:mais bem avaliados|bem avaliados)$", "", t).strip()
    if not t:
        return None
    palavras = t.split()
    console = genero = None
    i = 0
    while i < len(palavras):
        achou = False
        for n in (3, 2, 1):
            trecho = " ".join(palavras[i:i + n])
            if len(palavras) - i < n:
                continue
            if not genero and trecho in GENEROS:
                genero, i, achou = GENEROS[trecho], i + n, True
                break
            c = None if console else _console_exato(trecho)
            if c and c in PLATAFORMA_WD:
                console, i, achou = c, i + n, True
                break
        if not achou:
            if palavras[i] in ("de", "do", "da", "no", "na", "para", "pra"):
                i += 1
                continue
            return None
    return {"console": console, "genero": genero} if (console or genero) else None


def _filtros(console: str | None, genero: tuple | None) -> str:
    plat = PLATAFORMA_WD.get(console) if console else None
    return (f"?jogo wdt:P400 wd:{plat} ." if plat else "") + \
        (f" ?jogo wdt:P136/wdt:P279* wd:{genero[1]} ." if genero else "")


def _consulta(console: str | None, genero: tuple | None, limite: int) -> str:
    """Uma linha por NOTA do Metacritic, com a plataforma a que ela se refere (quando o Wikidata diz). O Python
    decide qual vale: a da plataforma pedida > a geral (sem plataforma) > nunca a que é SÓ de outra plataforma
    (antes: Half-Life aparecia com 96 no PS2, que é a nota do PC)."""
    return f"""SELECT ?jogo ?nome ?n ?pq ?ano WHERE {{
  ?jogo wdt:P31 wd:Q7889 . {_filtros(console, genero)}
  ?jogo p:P444 ?st . ?st ps:P444 ?txt ; pq:P447 wd:{METACRITIC} .
  BIND(xsd:integer(STRBEFORE(STR(?txt), "/")) AS ?n)
  OPTIONAL {{ ?st pq:P400 ?pq . }}
  OPTIONAL {{ ?jogo wdt:P577 ?data . BIND(YEAR(?data) AS ?ano) }}
  ?jogo rdfs:label ?nome . FILTER(LANG(?nome) = "en")
}} LIMIT {limite * 40}"""


def _consulta_conhecidos(console: str | None, genero: tuple | None, limite: int) -> str:
    """Sem nota no Wikidata (comum em gêneros de nicho): os mais conhecidos = com mais artigos na Wikipédia."""
    return f"""SELECT ?jogo ?nome ?links (MIN(?a) AS ?ano) WHERE {{
  ?jogo wdt:P31 wd:Q7889 . {_filtros(console, genero)}
  ?jogo wikibase:sitelinks ?links .
  OPTIONAL {{ ?jogo wdt:P577 ?data . BIND(YEAR(?data) AS ?a) }}
  ?jogo rdfs:label ?nome . FILTER(LANG(?nome) = "en")
}} GROUP BY ?jogo ?nome ?links ORDER BY DESC(?links) LIMIT {limite}"""


def _baixar(consulta: str, abrir=None, timeout: int = 60) -> list[dict]:
    url = "https://query.wikidata.org/sparql?" + urllib.parse.urlencode({"query": consulta, "format": "json"})
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/sparql-results+json"})
    with (abrir or urllib.request.urlopen)(req, timeout=timeout) as r:
        return json.loads(r.read(8 * 1024 * 1024))["results"]["bindings"]


def _escolher_notas(linhas: list[dict], console: str | None) -> list[dict]:
    plat = PLATAFORMA_WD.get(console) if console else None
    por_jogo: dict[str, dict] = {}
    for b in linhas:
        try:
            n = int(b["n"]["value"])
        except (KeyError, ValueError):
            continue
        j = por_jogo.setdefault(b["jogo"]["value"], {"nome": b["nome"]["value"], "plat": [], "geral": [],
                                                      "outra": [], "ano": None})
        pq = b.get("pq", {}).get("value", "").rsplit("/", 1)[-1] or None
        (j["plat"] if plat and pq == plat else j["geral"] if not pq or not plat else j["outra"]).append(n)
        if b.get("ano"):
            ano = int(b["ano"]["value"])
            j["ano"] = min(j["ano"] or ano, ano)
    out = []
    for j in por_jogo.values():
        if j["plat"]:
            out.append({"nome": j["nome"], "nota": max(j["plat"]), "tipo_nota": "plataforma", "ano": j["ano"]})
        elif j["geral"]:
            out.append({"nome": j["nome"], "nota": max(j["geral"]), "tipo_nota": "geral" if plat else "plataforma",
                        "ano": j["ano"]})
        # só nota de OUTRA plataforma: fica de fora (não é a nota desta versão)
    return out


def melhores(paths, console: str | None, genero: tuple | None, limite: int = 40, abrir=None,
             agora: float | None = None) -> list[dict]:
    """[{"nome", "nota", "tipo_nota", "ano"}]: tipo_nota = "plataforma" | "geral" | None (sem nota, entre os mais
    conhecidos). Cache de 7 dias em paths.state/descobrir-cache."""
    agora = time.time() if agora is None else agora
    consulta = _consulta(console, genero, limite)
    pasta = paths.state / "descobrir-cache"
    arq = pasta / (hashlib.sha1(consulta.encode()).hexdigest()[:16] + ".json")
    try:
        dados = json.loads(arq.read_text("utf-8"))
        if agora - dados["at"] < CACHE_DIAS * 86400:
            return dados["jogos"]
    except (OSError, ValueError, KeyError):
        pass
    jogos = _escolher_notas(_baixar(consulta, abrir), console)
    jogos.sort(key=lambda j: (-j["nota"], j["tipo_nota"] != "plataforma"))
    jogos = jogos[:limite]
    if len(jogos) < 10:  # completa com os mais conhecidos (sem nota no Wikidata)
        tem = {j["nome"].casefold() for j in jogos}
        for b in _baixar(_consulta_conhecidos(console, genero, limite), abrir):
            nome = b["nome"]["value"]
            if nome.casefold() not in tem:
                tem.add(nome.casefold())
                jogos.append({"nome": nome, "nota": None, "tipo_nota": None,
                              "ano": int(b["ano"]["value"]) if b.get("ano") else None})
        jogos = jogos[:limite]
    pasta.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps({"at": agora, "jogos": jogos}, ensure_ascii=False), "utf-8")
    return jogos


def titulo(console: str | None, genero: tuple | None, rotulo) -> str:
    partes = []
    if genero:
        partes.append(genero[0])
    if console:
        partes.append(rotulo(console))
    return " · ".join(partes)
