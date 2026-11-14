"""Detonado por capítulo, em português, no painel (pedido 13/11/2026: "to no terceiro ginásio, mostra o que fazer").

Fonte: StrategyWiki (strategywiki.org), detonados escritos pela comunidade sob licença livre (CC BY-SA — pode copiar
e traduzir citando a fonte; o painel mostra o link). O índice de cada jogo ("<Jogo>/Table of Contents") já vem em
ordem e agrupado: no Pokémon por insígnia (ginásio), no God of War por capítulo. Cada página do detonado é baixada
uma vez, limpa e traduzida pela IA do projeto (Index-Translate / PC / Deck), e fica guardada para ler sem internet.

    python3 -m dc.detonado baixar <game_id>     -> baixa e traduz o detonado inteiro (o painel chama em segundo plano)

Fica de fora o "quanto falta para zerar" do HowLongToBeat: o site não tem acesso aberto (a busca exige uma chave que
muda) e quebraria sozinho a cada mudança do site.
Rascunho do limpador pela IA local (qwen2.5-coder:7b), refeito: juntava tudo num parágrafo só, apagava todo "]",
não tirava itálico e as tabelas.
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://strategywiki.org/w/api.php"
SITE = "https://strategywiki.org/wiki/"
UA = "DeckCommander/0.9 (detonado offline; https://github.com/guilherme-lacerda-tech/deck-commander)"


# ------------------------------------------------------------------------------------------------ wiki
def _api(params: dict, timeout: float = 20) -> dict:
    url = API + "?" + urllib.parse.urlencode(params | {"format": "json", "formatversion": "2"})
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def wikitext(pagina: str, api=_api) -> str | None:
    d = api({"action": "parse", "page": pagina, "prop": "wikitext", "redirects": "1"})
    return (d.get("parse") or {}).get("wikitext")


def _sem_marcas(titulo: str) -> str:
    """Nome do jogo sem o que o arquivo tem a mais: (BR), [ISO], (DUB IA), versão, nome de tradutor…"""
    t = re.sub(r"[\(\[][^\)\]]*[\)\]]", " ", titulo)
    t = re.sub(r"\b(Barik|Rus|BR|PT-BR|USA|EUR|PAL|NTSC|ISO|DUB|IA|PSX|PS1|PS2|PSP|GBA|SNES|NES|N64|NDS|GC|Wii|"
               r"Dublado|Legendado|Black Edition|Collectors Edition|v?\d+\.\d+)\b", " ", t, flags=re.I)
    t = re.sub(r"\s+", " ", re.sub(r"[_\-:]", " ", t)).strip()
    return re.sub(r"\s1$", "", t)  # "God of War 1": na wiki o primeiro jogo não tem número


def achar_jogo(titulo: str, api=_api) -> str | None:
    """Página do jogo na StrategyWiki que tem índice ("<Jogo>/Table of Contents")."""
    busca = _sem_marcas(titulo)
    d = api({"action": "query", "list": "search", "srsearch": busca, "srnamespace": "0", "srlimit": "10"})
    raizes = []
    for r in (d.get("query") or {}).get("search", []):
        raiz = r.get("title", "").split("/")[0]
        if raiz and raiz not in raizes:
            raizes.append(raiz)
    if not raizes:
        return None
    # "Pokemon FireRed" na wiki é um redirecionamento para "Pokémon FireRed and LeafGreen": segue
    rd = api({"action": "query", "titles": "|".join(raizes[:10]), "redirects": "1"}).get("query") or {}
    para = {r["from"]: r["to"] for r in rd.get("redirects", [])}
    raizes = list(dict.fromkeys(para.get(r, r) for r in raizes))
    q = api({"action": "query", "titles": "|".join(f"{r}/Table of Contents" for r in raizes[:8])})
    existem = {p["title"][: -len("/Table of Contents")] for p in (q.get("query") or {}).get("pages", [])
               if not p.get("missing") and p.get("title", "").endswith("/Table of Contents")}
    return next((r for r in raizes if r in existem), None)


def indice(jogo: str, api=_api) -> list[dict]:
    """[{grupo, titulo, pagina}] na ordem do detonado."""
    txt = wikitext(f"{jogo}/Table of Contents", api) or ""
    m = re.search(r"\{\{h2\|\[\[[^\]|]*/Walkthrough[^\]]*\]\][^}]*\}\}", txt) or re.search(r"Walkthrough", txt)
    if not m:
        return []
    resto = txt[m.end():]
    fim = re.search(r"\{\{h2\|", resto)
    resto = resto[: fim.start()] if fim else resto
    out, grupo = [], "Detonado"
    for ln in resto.splitlines():
        h = re.match(r"\s*\{\{h[34]\|(.+?)\}\}", ln)
        if h:
            grupo = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", h.group(1)).split("|")[0].strip()
            continue
        for alvo, rotulo in re.findall(r"\[\[([^\]|]+)(?:\|([^\]]*))?\]\]", ln):
            if "/" in alvo and not alvo.lower().startswith(("file:", "image:")):
                out.append({"grupo": grupo, "titulo": (rotulo or alvo.split("/")[-1]).strip(), "pagina": alvo.strip()})
    return out


# Ícones de botão da StrategyWiki ({{psx|X}}, {{PSP|T}}…) viram texto; antes sumiam ("segure  e aperte ").
BOTOES = r"psx|ps2|ps3|ps4|psp|ps|gc|gcn|wii|gba|gb|gbc|snes|nes|n64|ds|3ds|switch|xbox|xbox360|xb|button|key|keypress"
SIMBOLOS = {"X": "✕", "C": "○", "S": "□", "T": "△", "Cross": "✕", "Circle": "○", "Square": "□", "Triangle": "△",
            "Lstick": "analógico esquerdo", "Rstick": "analógico direito", "Neutral": ""}


def _botao(m: re.Match) -> str:
    partes = [SIMBOLOS.get(x.strip(), x.strip()) for x in m.group(2).split("|")]
    return "[" + " ".join(p for p in partes if p) + "]"


def limpar_wikitext(texto: str) -> list[str]:
    """Wikitext -> parágrafos de texto simples (títulos e itens de lista viram parágrafos próprios)."""
    t = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>|<!--.*?-->", "", texto, flags=re.S)
    t = re.sub(r"\{\{(" + BOTOES + r")\|([^{}]*)\}\}", _botao, t, flags=re.I)
    while True:  # predefinições {{...}}, de dentro para fora
        n = re.sub(r"\{\{[^{}]*\}\}", "", t)
        if n == t:
            break
        t = n
    while True:  # tabelas {| ... |} (podem estar uma dentro da outra)
        n = re.sub(r"(?ms)^\{\|(?:(?!^\{\|).)*?^\|\}[^\n]*", "", t)
        if n == t:
            break
        t = n
    while True:  # imagens (a legenda pode ter [[links]])
        n = re.sub(r"\[\[(?:File|Image|Arquivo):(?:[^\[\]]|\[\[[^\]]*\]\])*\]\]", "", t, flags=re.I)
        if n == t:
            break
        t = n
    t = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", t)  # [[alvo|rótulo]] -> rótulo
    t = re.sub(r"\[https?://\S+\s+([^\]]+)\]", r"\1", t)  # [http://x rótulo] -> rótulo
    t = re.sub(r"\[https?://\S+\]", "", t)
    t = re.sub(r"'{2,}", "", t)  # '''negrito''' e ''itálico''
    t = re.sub(r"<[^>]+>", "", t)
    out, atual = [], []

    def fecha():
        if atual:
            out.append(" ".join(atual)); atual.clear()

    for ln in t.splitlines():
        s = ln.strip()
        h = re.match(r"^(=+)\s*(.*?)\s*\1$", s)
        if h:
            fecha(); out.append(h.group(2))
        elif re.match(r"^[*#:;]+", s):
            fecha(); out.append("• " + re.sub(r"^[*#:;]+\s*", "", s))
        elif not s:
            fecha()
        else:
            atual.append(s)
    fecha()
    return [p.strip() for p in out if len(p.strip()) >= 2 and p.strip() != "•"]


# ------------------------------------------------------------------------------------------------ guardado
def _pasta(paths, game_id: str) -> Path:
    return paths.data / "detonado" / game_id


def info(paths, game_id: str) -> dict:
    try:
        return json.loads((_pasta(paths, game_id) / "indice.json").read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def _gravar(f: Path, dados) -> None:
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_name(f.name + ".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False), "utf-8")
    tmp.replace(f)


def preparar(paths, game_id: str, titulo: str, jogo: str | None = None, api=_api) -> dict:
    """Acha o jogo na wiki e guarda o índice. `jogo` = nome exato na StrategyWiki (quando a busca não acha)."""
    jogo = jogo or achar_jogo(titulo, api)
    if not jogo:
        return {"erro": f"Não achei o detonado de \"{_sem_marcas(titulo)}\" na StrategyWiki."}
    caps = indice(jogo, api)
    if not caps:
        return {"erro": f"A StrategyWiki tem \"{jogo}\", mas sem detonado por partes."}
    dados = {"jogo": jogo, "fonte": SITE + urllib.parse.quote(jogo.replace(" ", "_")), "capitulos": caps,
             "atual": info(paths, game_id).get("atual", 0)}
    _gravar(_pasta(paths, game_id) / "indice.json", dados)
    return dados


def marcar(paths, game_id: str, n: int) -> None:
    d = info(paths, game_id)
    if d:
        d["atual"] = max(0, min(int(n), len(d["capitulos"]) - 1))
        _gravar(_pasta(paths, game_id) / "indice.json", d)


def capitulo(paths, game_id: str, n: int, traduzir: bool = True, api=_api, tradutor=None) -> dict:
    """{titulo, grupo, paragrafos, traduzido, fonte}. Baixa e traduz na primeira vez; depois lê do disco."""
    d = info(paths, game_id)
    if not d or not 0 <= n < len(d["capitulos"]):
        return {"erro": "capítulo não existe"}
    cap = d["capitulos"][n]
    f = _pasta(paths, game_id) / f"{n:03d}.json"
    try:
        salvo = json.loads(f.read_text("utf-8"))
    except (OSError, ValueError):
        salvo = None
    if salvo is None:
        txt = wikitext(cap["pagina"], api) or ""
        salvo = {"original": limpar_wikitext(txt), "pt": None}
        _gravar(f, salvo)
    if traduzir and salvo.get("pt") is None and salvo["original"]:
        pt = (tradutor or _traduzir)(paths, game_id, [cap["titulo"]] + salvo["original"])
        if pt:
            salvo["titulo_pt"], salvo["pt"] = pt[0], pt[1:]
            _gravar(f, salvo)
    return {"titulo": salvo.get("titulo_pt") or cap["titulo"], "grupo": cap["grupo"],
            "paragrafos": salvo.get("pt") or salvo["original"], "traduzido": salvo.get("pt") is not None,
            "fonte": SITE + urllib.parse.quote(cap["pagina"].replace(" ", "_"))}


def titulos(paths, game_id: str) -> list[str]:
    """Título de cada parte para a lista do painel: o traduzido quando a parte já foi traduzida (visto no Deck
    14/11/2026: a lista mostrava "In Defense of Attica" com o texto já em português)."""
    d = info(paths, game_id)
    out = []
    for i, cap in enumerate(d.get("capitulos", [])):
        try:
            pt = json.loads((_pasta(paths, game_id) / f"{i:03d}.json").read_text("utf-8")).get("titulo_pt")
        except (OSError, ValueError):
            pt = None
        out.append(pt or cap["titulo"])
    return out


def _traduzir(paths, game_id: str, textos: list[str]) -> list[str] | None:
    """Pela IA de tradução do projeto (com cache). None se nenhuma IA respondeu — fica o texto original."""
    from .traducao import ia
    cfg = ia.load_cfg(paths)
    itens = [ia.Item(id=str(i), text=t) for i, t in enumerate(textos)]
    res = ia.translate(paths, cfg, itens, job=f"detonado-{game_id}")
    if len(res.translated) < len(textos) * 0.8:  # tradução pela metade: melhor o original inteiro
        return None
    return [res.translated.get(str(i), t) for i, t in enumerate(textos)]


def herdar(paths, de: str, para: str) -> bool:
    """Jogo trocado pela versão traduzida (outro game_id): o detonado já traduzido e o capítulo onde você está vão
    junto (visto 14/11/2026 com o God of War do PSP: 9 capítulos traduzidos ficariam presos ao jogo antigo)."""
    import shutil
    a, b = _pasta(paths, de), _pasta(paths, para)
    if not (a / "indice.json").exists() or (b / "indice.json").exists():
        return False
    shutil.copytree(a, b, dirs_exist_ok=True)
    return True


def baixar_tudo(paths, game_id: str, titulo: str, api=_api, tradutor=None, log=print) -> str:
    d = info(paths, game_id) or preparar(paths, game_id, titulo, api=api)
    if d.get("erro"):
        return d["erro"]
    n = len(d["capitulos"])
    comeco = d.get("atual", 0)  # começa pela parte em que você está, depois as seguintes
    for k in range(n):
        i = (comeco + k) % n
        capitulo(paths, game_id, i, api=api, tradutor=tradutor)
        log(f"detonado {game_id}: {k + 1}/{n}")
        time.sleep(0.5)  # gentil com a wiki
    return f"detonado de {d['jogo']}: {n} parte(s) prontas para ler sem internet"


def main(argv: list[str]) -> int:
    from .paths import get_paths
    paths = get_paths()
    if argv[:1] == ["baixar"] and argv[1:]:
        from . import transferir
        e = transferir.carregar_mapa().get(argv[1], {})
        print(baixar_tudo(paths, argv[1], e.get("title", argv[1])))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
