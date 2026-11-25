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
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://strategywiki.org/w/api.php"
SITE = "https://strategywiki.org/wiki/"
UA = "DeckCommander/0.9 (detonado offline; https://github.com/guilherme-lacerda-tech/deck-commander)"

# A StrategyWiki tem uma tabela de conteúdo do DMC3, mas praticamente todas as
# subpáginas daquela tabela foram apagadas.  O Devil May Cry Wiki mantém as 20
# missões, também sob CC BY-SA.  Isto é uma troca de fonte explícita e
# atribuída, não uma tentativa de adivinhar/inventar instruções ausentes.
FANDOM_API = "https://devilmaycry.fandom.com/api.php"
FANDOM_SITE = "https://devilmaycry.fandom.com/wiki/"
DMC3_WIKI = "Devil May Cry 3: Dante's Awakening walkthrough"


# ------------------------------------------------------------------------------------------------ wiki
def _api(params: dict, timeout: float = 20) -> dict:
    return _api_url(API, params, timeout)


def _api_url(base: str, params: dict, timeout: float = 20) -> dict:
    url = base + "?" + urllib.parse.urlencode(params | {"format": "json", "formatversion": "2"})
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _api_da_fonte(dados: dict):
    """Cliente da fonte guardada no índice (o cache continua legível offline)."""
    base = dados.get("api")
    if not base:
        return _api
    return lambda params: _api_url(base, params)


def fonte_especial(titulo: str) -> dict | None:
    """Fonte alternativa só quando há cobertura comprovadamente melhor para o jogo."""
    nome = _sem_marcas(titulo).casefold()
    if "devil may cry 3" not in nome:
        return None
    return {
        "jogo": DMC3_WIKI,
        "fonte": FANDOM_SITE + urllib.parse.quote(DMC3_WIKI.replace(" ", "_")),
        "fonte_nome": "Devil May Cry Wiki",
        "licenca": "CC BY-SA",
        "api": FANDOM_API,
        "site": FANDOM_SITE,
        "capitulos": [
            {"grupo": "Missões", "titulo": f"Missão {i:02d}",
             "pagina": f"{DMC3_WIKI}/M{i:02d}"} for i in range(1, 21)
        ],
    }


def precisa_migrar(dados: dict, titulo: str) -> bool:
    """Evita manter o índice quebrado quando uma fonte alternativa conhecida existe."""
    especial = fonte_especial(titulo)
    return bool(especial and dados and dados.get("api") != especial["api"])


def wikitext(pagina: str, api=_api) -> str | None:
    d = api({"action": "parse", "page": pagina, "prop": "wikitext", "redirects": "1"})
    return (d.get("parse") or {}).get("wikitext")


def pagina_ausente(pagina: str, api=_api) -> bool:
    """Diz se a própria StrategyWiki não publicou a subpágina (não confunde com queda de rede)."""
    d = api({"action": "parse", "page": pagina, "prop": "wikitext", "redirects": "1"})
    return (d.get("error") or {}).get("code") in {"missingtitle", "invalidtitle"}


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


def pronto(paths, game_id: str) -> bool:
    """O guia fica offline quando cada parte é PT-BR ou foi confirmada ausente na fonte."""
    d = info(paths, game_id)
    caps = d.get("capitulos") or []
    if not caps:
        return False
    for i in range(len(caps)):
        try:
            parte = json.loads((_pasta(paths, game_id) / f"{i:03d}.json").read_text("utf-8"))
        except (OSError, ValueError):
            return False
        if parte.get("indisponivel"):
            continue
        if not parte.get("pt") or not parte.get("titulo_pt"):
            return False
    return True


def erro(paths, game_id: str) -> str | None:
    """Último impedimento concreto da preparação, para o painel não prometer uma fila infinita."""
    try:
        d = json.loads((_pasta(paths, game_id) / "status.json").read_text("utf-8"))
        return d.get("erro") if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def _status(paths, game_id: str, mensagem: str | None = None) -> None:
    p = _pasta(paths, game_id) / "status.json"
    if mensagem:
        _gravar(p, {"erro": mensagem, "em": time.time()})
    else:
        p.unlink(missing_ok=True)


def agendar(paths, game_id: str, titulo: str, run=subprocess.run) -> bool:
    """Prepara o guia inteiro fora da abertura do jogo; nunca bloqueia Steam, sync ou o painel.

    A unidade user do systemd impede que a tradução morra quando o painel fecha. Um nome de unidade estável faz
    chamadas repetidas (sync, abrir jogo e painel) reaproveitarem a mesma preparação.
    """
    # Um cache DMC3 antigo podia estar "pronto" apenas porque as páginas
    # ausentes foram marcadas uma a uma. Ainda assim ele precisa rodar uma vez
    # para migrar à fonte completa.
    if not game_id or (pronto(paths, game_id) and not precisa_migrar(info(paths, game_id), titulo)):
        return False
    unidade = "dc-detonado-" + "".join(ch for ch in game_id if ch.isalnum())[:40]
    repo = Path(__file__).resolve().parents[1]
    venv = Path.home() / ".local/share/deck-commander/venv/bin/python"
    python = str(venv) if venv.exists() else sys.executable
    try:
        # Tradução offline é útil, mas nunca deve disputar CPU/I/O com uma
        # partida.  O serviço continua até terminar quando o Deck está livre,
        # porém cede recursos imediatamente ao Steam/emulador.
        r = run(["systemd-run", "--user", "--collect", "--property=Nice=15",
                 "--property=IOSchedulingClass=idle", f"--unit={unidade}", f"--working-directory={repo}",
                 python, "-m", "dc.detonado", "baixar", game_id],
                capture_output=True, text=True, timeout=10)
        return getattr(r, "returncode", 0) == 0
    except (OSError, subprocess.SubprocessError):
        return False


FILA_ESPERA = 6 * 3600


def _fila(paths) -> Path:
    return paths.state / "detonado-fila.json"


def agendar_proximo(paths, now: float | None = None, run=subprocess.run) -> str | None:
    """Põe um guia já existente na biblioteca em preparação, sem disputar recursos com uma partida.

    Jogos instalados antes do recurso de detonados não passam pelo ``syncer``; esta fila preenche
    essa lacuna. Ela inicia apenas um guia por vez e espera seis horas antes de tentar o mesmo de
    novo, inclusive se a StrategyWiki ou a IA estiver temporariamente indisponível.
    """
    now = time.time() if now is None else now
    try:
        mapa = json.loads((paths.data / "launch-map.json").read_text("utf-8"))
    except (OSError, ValueError):
        return None
    try:
        estado = json.loads(_fila(paths).read_text("utf-8"))
    except (OSError, ValueError):
        estado = {}
    tentados = estado.get("tentados", {})
    candidatos = [
        (gid, e) for gid, e in mapa.items()
        if not e.get("removed") and e.get("console") not in ("pc", "steam")
        and e.get("title") and not pronto(paths, gid)
        and (gid not in tentados or now - float(tentados[gid]) >= FILA_ESPERA)
    ]
    # Um guia já parcialmente baixado vem antes de um novo: é a forma mais rápida de consertar
    # uma abertura anterior que ficou sem Internet, como o DMC3.
    candidatos.sort(key=lambda item: (not bool(info(paths, item[0])), item[1]["title"].casefold()))
    if not candidatos:
        return None
    gid, jogo = candidatos[0]
    if not agendar(paths, gid, jogo["title"], run=run):
        return None
    tentados[gid] = now
    _gravar(_fila(paths), {"tentados": tentados, "ultimo": gid, "em": now})
    return f"detonado: preparando em português {jogo['title']}"


def _gravar(f: Path, dados) -> None:
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_name(f.name + ".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False), "utf-8")
    tmp.replace(f)


def preparar(paths, game_id: str, titulo: str, jogo: str | None = None, api=_api) -> dict:
    """Acha o jogo na wiki e guarda o índice. `jogo` = nome exato na StrategyWiki (quando a busca não acha)."""
    especial = fonte_especial(titulo)
    if especial:
        anterior = info(paths, game_id)
        # Só arquivos de cache do próprio detonado são removidos; ROMs, saves e
        # configurações do emulador não ficam sequer sob esta pasta. Sem isso,
        # uma tradução velha de uma página StrategyWiki poderia ser mostrada
        # como se viesse da nova fonte.
        if anterior and anterior.get("api") != especial["api"]:
            for antigo in _pasta(paths, game_id).glob("[0-9][0-9][0-9].json"):
                antigo.unlink(missing_ok=True)
        dados = especial | {"atual": anterior.get("atual", 0)}
        _gravar(_pasta(paths, game_id) / "indice.json", dados)
        return dados
    jogo = jogo or achar_jogo(titulo, api)
    if not jogo:
        return {"erro": f"Não achei o detonado de \"{_sem_marcas(titulo)}\" na StrategyWiki."}
    caps = indice(jogo, api)
    if not caps:
        return {"erro": f"A StrategyWiki tem \"{jogo}\", mas sem detonado por partes."}
    dados = {"jogo": jogo, "fonte": SITE + urllib.parse.quote(jogo.replace(" ", "_")),
             "fonte_nome": "StrategyWiki", "licenca": "CC BY-SA", "site": SITE,
             "capitulos": caps,
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
    if api is _api:
        api = _api_da_fonte(d)
    cap = d["capitulos"][n]
    f = _pasta(paths, game_id) / f"{n:03d}.json"
    try:
        salvo = json.loads(f.read_text("utf-8"))
    except (OSError, ValueError):
        salvo = None
    if salvo and salvo.get("indisponivel"):
        return {"erro": salvo["indisponivel"], "indisponivel": True}
    # Uma tentativa antiga podia deixar {original: [], pt: null} quando a wiki respondeu vazia;
    # trate isso como tentativa incompleta, não como cache válido. Assim a fila consegue reparar
    # o DMC3 e qualquer guia que tenha sido preparado sem conteúdo por uma queda de rede.
    if salvo is None or not salvo.get("original"):
        txt = wikitext(cap["pagina"], api) or ""
        original = limpar_wikitext(txt)
        if not original:
            # Alguns índices da StrategyWiki ainda listam páginas que foram apagadas. Isso não é
            # falha da conexão nem autorização para despejar uma página em inglês: o worker marca
            # explicitamente a lacuna e deixa todas as outras partes úteis offline.
            if pagina_ausente(cap["pagina"], api):
                return {"erro": f"A StrategyWiki não publicou a parte '{cap['titulo']}'.",
                        "indisponivel": True}
            return {"erro": f"não consegui baixar a parte '{cap['titulo']}' agora"}
        salvo = {"original": original, "pt": None}
        _gravar(f, salvo)
    if traduzir and salvo.get("pt") is None and salvo["original"]:
        pt = (tradutor or _traduzir)(paths, game_id, [cap["titulo"]] + salvo["original"])
        if pt:
            salvo["titulo_pt"], salvo["pt"] = pt[0], pt[1:]
            _gravar(f, salvo)
    return {"titulo": salvo.get("titulo_pt") or cap["titulo"], "grupo": cap["grupo"],
            "paragrafos": salvo.get("pt") or salvo["original"], "traduzido": salvo.get("pt") is not None,
            "fonte": d.get("site", SITE) + urllib.parse.quote(cap["pagina"].replace(" ", "_"))}


def titulos(paths, game_id: str) -> list[str]:
    """Título de cada parte para a lista do painel: o traduzido quando a parte já foi traduzida (visto no Deck
    14/11/2026: a lista mostrava "In Defense of Attica" com o texto já em português)."""
    d = info(paths, game_id)
    out = []
    for i, cap in enumerate(d.get("capitulos", [])):
        try:
            salvo = json.loads((_pasta(paths, game_id) / f"{i:03d}.json").read_text("utf-8"))
            if salvo.get("indisponivel"):
                out.append("Indisponível na fonte")
                continue
            pt = salvo.get("titulo_pt")
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
    if precisa_migrar(d, titulo):
        d = preparar(paths, game_id, titulo, api=api)
    if d.get("erro"):
        _status(paths, game_id, d["erro"])
        return d["erro"]
    n = len(d["capitulos"])
    comeco = d.get("atual", 0)  # começa pela parte em que você está, depois as seguintes
    indisponiveis = []
    for k in range(n):
        i = (comeco + k) % n
        parte = capitulo(paths, game_id, i, api=api, tradutor=tradutor)
        if parte.get("indisponivel"):
            _gravar(_pasta(paths, game_id) / f"{i:03d}.json", {"indisponivel": parte["erro"]})
            indisponiveis.append(d["capitulos"][i]["titulo"])
            log(f"detonado {game_id}: parte ausente na fonte: {d['capitulos'][i]['titulo']}")
            continue
        if parte.get("erro"):
            msg = f"detonado não terminou: {parte['erro']}"
            _status(paths, game_id, msg)
            return msg
        if not parte.get("traduzido"):
            msg = f"detonado não terminou: a tradução de '{parte['titulo']}' não ficou pronta"
            _status(paths, game_id, msg)
            return msg
        log(f"detonado {game_id}: {k + 1}/{n}")
        time.sleep(0.5)  # gentil com a wiki
    _status(paths, game_id)
    if indisponiveis:
        return (f"detonado parcial de {d['jogo']}: {n - len(indisponiveis)}/{n} parte(s) em português offline; "
                f"{len(indisponiveis)} não publicada(s) pela fonte")
    return f"detonado de {d['jogo']}: {n} parte(s) prontas para ler sem internet"


def main(argv: list[str]) -> int:
    from .paths import get_paths
    paths = get_paths()
    if argv[:1] == ["baixar"] and argv[1:]:
        from . import transferir
        e = transferir.carregar_mapa().get(argv[1], {})
        msg = baixar_tudo(paths, argv[1], e.get("title", argv[1]))
        print(msg)
        return 0 if pronto(paths, argv[1]) else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
