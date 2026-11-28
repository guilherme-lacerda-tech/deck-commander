"""Pesquisa de jogos pelo nome, em todas as plataformas, em várias fontes ao mesmo tempo.

    "god"           -> todas as plataformas
    "god psp"       -> só PSP           ("god ps2" -> só PS2)
    "re4 pt-br"     -> abreviação expandida (Resident Evil 4) + filtro de idioma

Fontes (provedores), cada uma com estado próprio — nunca "lista vazia" quando na verdade a fonte falhou:
    biblioteca  jogos que já estão no Deck (launch-map)
    catalogo    catálogo verificado (SHA-256) do Deck Commander e do dono
    familia     catálogo do Deck pareado (Modo Família)
    internet_archive  busca direta na API do Internet Archive (só se o dono ligar em busca.json)
    prowlarr    indexadores configurados pelo dono no Prowlarr

Por que o Internet Archive tem adaptador direto: medido no Deck em 28/11/2026, a MESMA consulta leva 1–3 s com um
cliente comum e ~85 s quando o User-Agent é o do Prowlarr (o Archive atrasa esse cliente); o Prowlarr não deixa trocar
o User-Agent por indexador. O adaptador se identifica honestamente como Deck Commander.

Licença: no Internet Archive o campo de licença é DECLARADO por quem enviou e não é conferido (há ISOs comerciais
marcados como domínio público). Por isso a busca mostra "licença declarada, não verificada" e nunca rotula um item
como autorizado; a responsabilidade pelo que é baixado é do dono, que escolhe as fontes.
"""
from __future__ import annotations

import concurrent.futures as cf
import difflib
import hashlib
import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

USER_AGENT = "DeckCommander/0.11 (+https://github.com/guilherme-lacerda-tech/deck-commander)"
PROVEDORES_PADRAO = ("biblioteca", "catalogo", "familia", "prowlarr")
TIMEOUT = {"biblioteca": 5, "catalogo": 5, "familia": 10, "internet_archive": 20, "prowlarr": 30}
POR_PAGINA = 6
TTL_SESSAO = 30 * 60
MAX_SESSOES = 8

# estados por fonte (texto para o usuário)
OK, VAZIO, FORA, TEMPO, AUTH, NAO_CONFIG, ERRO = ("ok", "sem resultados", "indisponível", "tempo esgotado",
                                                  "erro de autenticação", "não configurado", "erro")

ABREVIACOES = {
    "gow": "god of war", "re": "resident evil", "re2": "resident evil 2", "re3": "resident evil 3",
    "re4": "resident evil 4", "dmc": "devil may cry", "dmc3": "devil may cry 3", "ff": "final fantasy",
    "ffx": "final fantasy x", "ffvii": "final fantasy vii", "ff7": "final fantasy vii", "mgs": "metal gear solid",
    "mgs2": "metal gear solid 2", "mgs3": "metal gear solid 3", "kh": "kingdom hearts", "gta": "grand theft auto",
    "sotn": "symphony of the night", "totk": "tears of the kingdom", "botw": "breath of the wild",
    "mk": "mortal kombat", "nfs": "need for speed", "pes": "pro evolution soccer", "smb": "super mario bros",
    "sf": "street fighter", "sf2": "street fighter ii", "dq8": "dragon quest viii", "sc3": "soulcalibur iii",
    "cod": "call of duty", "dbz": "dragon ball z", "tlou": "the last of us", "loz": "the legend of zelda",
}
REGIOES = [  # (regex no título/consulta, rótulo)
    (r"usa|us|eua|ntsc-?u|ntsc(?!-?j)", "EUA"), (r"europe|eur|eu|pal", "Europa"),
    (r"japan|jpn|jap|jp|ntsc-?j", "Japão"), (r"brazil|brasil|br", "Brasil"), (r"world|mundo", "Mundial"),
]
PTBR_RX = re.compile(r"(?i)pt[-_ ]?br|portugu[eê]s|traduzid|tradu[cç][aã]o|\(br\)|\bbr\b|romsportugues")
FORMATOS = ("iso", "chd", "rvz", "wbfs", "cso", "pbp", "nsp", "nsz", "xci", "cue", "bin", "gdi", "cdi", "zip",
            "7z", "rar", "nes", "sfc", "smc", "gba", "gb", "gbc", "nds", "3ds", "z64", "n64", "wad", "md")
PRIORIDADE_FONTE = {"biblioteca": 0, "catalogo": 1, "familia": 2, "internet_archive": 3, "prowlarr": 4}


# ----------------------------------------------------------------------------------------------- texto
def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().casefold()
    texto = re.sub(r"[\[\(][^\]\)]*[\]\)]", " ", texto)  # tira [PS2] (USA) etc. do título
    return " ".join(re.findall(r"[a-z0-9]+", texto))


def _console_exato(palavras: str) -> str | None:
    from .bot import ALIASES
    for rx, c in ALIASES:
        if re.fullmatch(rf"\s*(?:{rx})\s*", palavras, re.I):
            return c
    if re.fullmatch(r"\s*(?:pc|computador|windows)\s*", palavras, re.I):
        return "pc"
    return None


def interpretar(texto: str) -> dict:
    """"god psp" -> {"termos": "god", "console": "psp"}. Plataforma, região e PT-BR podem vir no começo ou no fim."""
    palavras = (texto or "").split()
    console = regiao = None
    ptbr = False
    mudou = True
    while mudou and palavras:
        mudou = False
        for lado in (-1, 0):
            for n in (3, 2, 1):  # "nintendo 3ds", "xbox 360", "ps2"
                if len(palavras) <= n:
                    continue
                trecho = " ".join(palavras[-n:] if lado == -1 else palavras[:n])
                c = None if console else _console_exato(trecho)
                if c:
                    console, palavras = c, (palavras[:-n] if lado == -1 else palavras[n:])
                    mudou = True
                    break
            if mudou:
                break
            pedaco = palavras[lado]
            if re.fullmatch(r"(?i)pt-?br|portugu[eê]s|traduzido", pedaco):
                ptbr, mudou = True, True
                palavras.pop(lado)
                break
            r = next((rot for rx, rot in REGIOES if re.fullmatch(rf"(?i)\(?(?:{rx})\)?", pedaco)), None)
            if r and len(palavras) > 1 and not regiao:
                regiao, mudou = r, True
                palavras.pop(lado)
                break
    termos = " ".join(palavras).strip()
    expandido = " ".join(ABREVIACOES.get(p.casefold(), p) for p in termos.split())
    return {"termos": termos, "busca": expandido, "console": console, "regiao": regiao, "ptbr": ptbr}


def relevancia(titulo: str, busca: str) -> float:
    """0..1. Todas as palavras da busca no título (aceita começo de palavra) vale mais; erro de digitação conta
    pela semelhança (difflib)."""
    t, b = normalizar(titulo), normalizar(busca)
    if not b or not t:
        return 0.0
    tp, bp = t.split(), b.split()
    acertos = 0.0
    for w in bp:
        if w in tp:
            acertos += 1
        elif any(x.startswith(w) for x in tp if len(w) >= 3):
            acertos += 0.85
        else:
            melhor = max((difflib.SequenceMatcher(None, w, x).ratio() for x in tp), default=0)
            acertos += melhor if melhor >= 0.75 else 0
    base = acertos / len(bp)
    if t.startswith(b):
        base += 0.15
    elif b in t:
        base += 0.08
    return min(1.0, base)


def regiao_de(titulo: str) -> str | None:
    for bloco in re.findall(r"[\[\(]([^\]\)]*)[\]\)]", titulo or ""):
        for parte in re.split(r"[,/ ]+", bloco):
            r = next((rot for rx, rot in REGIOES if re.fullmatch(rf"(?i){rx}", parte.strip())), None)
            if r:
                return r
    return None


def formato_de(titulo: str) -> str | None:
    m = re.findall(r"(?i)(?:\.|\[|\(|\b)(" + "|".join(FORMATOS) + r")(?:\]|\)|\b)", titulo or "")
    return m[-1].upper() if m else None


def console_de(titulo: str, extra: str = "") -> str | None:
    from .bot import parse_console
    for bloco in re.findall(r"[\[\(]([^\]\)]*)[\]\)]", titulo or ""):
        c = parse_console(bloco)
        if c:
            return c
    return parse_console(titulo) or (parse_console(extra) if extra else None)


def _rid(fonte: str, ref: str) -> str:
    return hashlib.sha1(f"{fonte}\0{ref}".encode()).hexdigest()[:10]


def resultado(fonte: str, ref: str, titulo: str, console: str | None, **extra) -> dict:
    r = {"rid": _rid(fonte, ref), "fonte": fonte, "titulo": titulo[:200], "console": console,
         "regiao": extra.pop("regiao", None) or regiao_de(titulo), "formato": extra.pop("formato", None) or formato_de(titulo),
         "ptbr": extra.pop("ptbr", None), "tamanho": extra.pop("tamanho", None)}
    if r["ptbr"] is None and PTBR_RX.search(titulo or ""):
        r["ptbr"] = True
    r.update(extra)
    return r


# -------------------------------------------------------------------------------------------- provedores
def _p_biblioteca(paths, q):
    from . import transferir
    lm = transferir.carregar_mapa()
    out = []
    for gid, e in lm.items():
        titulo = e.get("title") or gid
        out.append(resultado("biblioteca", gid, titulo, e.get("console"), gid=gid, acao={"tipo": "biblioteca"}))
    return out


def _p_catalogo(paths, q):
    from . import catalogo_downloads
    entradas = {}
    for arq in (catalogo_downloads.DEFAULT_CATALOG, paths.config / "download-catalog.json"):
        if not arq.exists():
            continue
        dados = json.loads(arq.read_text("utf-8"))
        for e in dados.get("games", []):
            e = catalogo_downloads._validate(e)
            entradas[e["id"]] = e
    out = []
    for e in entradas.values():
        nomes = [e["titulo"], *e.get("aliases", [])]
        out.append(resultado("catalogo", e["id"], e["titulo"], e["console"], tamanho=e.get("file_size") or e["size"],
                             formato=Path(e["filename"]).suffix.lstrip(".").upper(), nomes=nomes,
                             licenca=e["license"], licenca_verificada=True, origem=e["source_url"],
                             acao={"tipo": "catalogo", "item": e}))
    return out


def _p_familia(paths, q):
    from . import familia_servico
    out = []
    for j in familia_servico.catalogo_guardado(paths).get("jogos", []):
        if not j.get("gid") or not j.get("titulo"):
            continue
        out.append(resultado("familia", j["gid"], j["titulo"], j.get("console"), tamanho=j.get("tamanho"),
                             ptbr=bool(j.get("ptbr")) or None, acao={"tipo": "familia", "gid": j["gid"]}))
    return out


IA_COLECAO_CONSOLE = {  # coleções do Internet Archive -> console (softwarelibrary_* e afins)
    "nes": "nes", "famicom": "nes", "snes": "snes", "megadrive": "genesis", "genesis": "genesis", "gba": "gba",
    "gameboy": "gb", "gbc": "gbc", "n64": "n64", "psx": "psx", "playstation": "psx", "ps2": "ps2", "psp": "psp",
    "dreamcast": "dc", "saturn": "saturn", "sms": "sms", "mastersystem": "sms", "gamegear": "gg",
    "msdos": "pc", "win3x": "pc", "windows": "pc",
}


def _ia_console(doc: dict) -> str | None:
    c = console_de(doc.get("title", ""))
    if c:
        return c
    cols = doc.get("collection") or []
    for col in ([cols] if isinstance(cols, str) else cols):
        for chave, cons in IA_COLECAO_CONSOLE.items():
            if re.search(rf"(?:^|_){chave}(?:$|_)", str(col).lower()):
                return cons
    return {"dosbox": "pc"}.get(str(doc.get("emulator") or "").lower())


def _p_internet_archive(paths, q, abrir=None):
    termos = q["busca"] or q["termos"]
    palavras = " ".join(re.findall(r"[\w]+", termos))
    if not palavras:
        return []
    params = {"q": f"title:({palavras}) AND mediatype:software AND format:(\"Archive BitTorrent\")",
              "fl[]": ["identifier", "title", "item_size", "licenseurl", "collection", "emulator", "year", "language"],
              "rows": 60, "output": "json", "sort[]": "downloads desc"}
    url = "https://archive.org/advancedsearch.php?" + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with (abrir or urllib.request.urlopen)(req, timeout=TIMEOUT["internet_archive"]) as resp:
        raw = resp.read(4 * 1024 * 1024 + 1)
    if len(raw) > 4 * 1024 * 1024:
        raise ValueError("resposta grande demais")
    docs = (json.loads(raw).get("response") or {}).get("docs") or []
    out = []
    for d in docs:
        ident = d.get("identifier")
        if not isinstance(ident, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,120}", ident):
            continue
        titulo = str(d.get("title") or ident)
        tam = d.get("item_size")
        out.append(resultado("internet_archive", ident, titulo, _ia_console(d),
                             tamanho=tam if isinstance(tam, int) else None, ano=d.get("year"),
                             licenca=d.get("licenseurl"), licenca_verificada=False,
                             capa=f"https://archive.org/services/img/{ident}",
                             origem=f"https://archive.org/details/{ident}",
                             acao={"tipo": "ia_torrent", "id": ident}))
    return out


def _p_prowlarr(paths, q, ignorar_indexadores=()):
    from . import prowlarr
    if prowlarr.configuracao(paths) is None:
        raise _NaoConfigurado()
    itens = prowlarr.pesquisar(paths, q["busca"] or q["termos"], timeout=TIMEOUT["prowlarr"] - 2,
                               ignorar=ignorar_indexadores) or []
    out = []
    for it in itens:
        ref = it.get("magnet") or it.get("download_url") or it["titulo"]
        out.append(resultado("prowlarr", ref, it["titulo"], console_de(it["titulo"]), tamanho=it.get("tamanho"),
                             seeders=it.get("seeders") or 0, indexador=it.get("indexador"),
                             acao={"tipo": "magnet", "magnet": it["magnet"]} if it.get("magnet")
                             else {"tipo": "prowlarr", "download_url": it.get("download_url", "")}))
    return out


class _NaoConfigurado(Exception):
    pass


PROVEDORES = {"biblioteca": _p_biblioteca, "catalogo": _p_catalogo, "familia": _p_familia,
              "internet_archive": _p_internet_archive, "prowlarr": _p_prowlarr}


def config(paths) -> dict:
    """busca.json do dono: {"provedores": [...]} — o Internet Archive direto só entra se ele ligar."""
    try:
        cfg = json.loads((paths.config / "busca.json").read_text("utf-8"))
        provs = [p for p in cfg.get("provedores", []) if p in PROVEDORES]
        return {"provedores": provs or list(PROVEDORES_PADRAO)}
    except (OSError, ValueError, AttributeError):
        return {"provedores": list(PROVEDORES_PADRAO)}


def _estado_de_erro(exc: BaseException) -> str:
    import urllib.error
    from .prowlarr import SemIndexadores
    if isinstance(exc, (_NaoConfigurado, SemIndexadores)):
        return NAO_CONFIG
    if isinstance(exc, (TimeoutError, cf.TimeoutError)) or "timed out" in str(exc).lower():
        return TEMPO
    if isinstance(exc, urllib.error.HTTPError) and exc.code in (401, 403):
        return AUTH
    if isinstance(exc, OSError):
        return FORA
    return ERRO


# ------------------------------------------------------------------------------------------------ busca
def pesquisar(paths, texto: str, provedores=None, funcs=None) -> dict:
    """Roda as fontes em paralelo. Devolve {"consulta", "resultados", "fontes": {fonte: estado}}."""
    q = interpretar(texto)
    funcs = funcs or PROVEDORES
    provs = list(provedores or config(paths)["provedores"])
    fontes: dict[str, str] = {}
    brutos: list[dict] = []
    if not (q["termos"] or "").strip():
        return {"consulta": q, "resultados": [], "fontes": {}}
    kw = {}
    if "internet_archive" in provs and "prowlarr" in provs:
        kw["prowlarr"] = {"ignorar_indexadores": ("internetarchive", "internet archive")}
    # Sem "with": a saída do with espera TODAS as threads, e uma fonte travada seguraria a busca além do timeout.
    ex = cf.ThreadPoolExecutor(max_workers=len(provs) or 1, thread_name_prefix="busca")
    try:
        inicio = time.monotonic()
        fut = {ex.submit(funcs[p], paths, q, **kw.get(p, {})): p for p in provs if p in funcs}
        for f in fut:
            p = fut[f]
            try:
                itens = f.result(timeout=max(0.05, inicio + TIMEOUT.get(p, 20) + 1 - time.monotonic()))
            except BaseException as e:  # noqa: BLE001 — falha de UMA fonte vira estado, não derruba a busca
                fontes[p] = _estado_de_erro(e)
                continue
            achados = filtrar(itens, q)
            fontes[p] = OK if achados else VAZIO
            brutos.extend(achados)
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    return {"consulta": q, "resultados": ordenar(deduplicar(brutos)), "fontes": fontes}


def filtrar(itens: list[dict], q: dict) -> list[dict]:
    out = []
    for r in itens:
        if q["console"] and r.get("console") != q["console"]:
            continue
        if q["regiao"] and r.get("regiao") not in (None, q["regiao"], "Mundial"):
            continue
        if q["ptbr"] and not r.get("ptbr"):
            continue
        nomes = r.get("nomes") or [r["titulo"]]
        s = max(max(relevancia(n, q["busca"]), relevancia(n, q["termos"])) for n in nomes)
        if s >= 0.6:
            out.append({**r, "score": round(s, 3)})
    return out


def _chave(r: dict) -> tuple:
    tam = r.get("tamanho")
    return (normalizar(r["titulo"]), r.get("console"), r.get("regiao"), round(tam / 2**20) if tam else None)


def deduplicar(rs: list[dict]) -> list[dict]:
    """Mesmo jogo, mesma plataforma, região e tamanho: fica a melhor fonte. Plataformas/regiões diferentes ficam."""
    melhor: dict[tuple, dict] = {}
    for r in rs:
        k = _chave(r)
        atual = melhor.get(k)
        if atual is None or (PRIORIDADE_FONTE[r["fonte"]], -r.get("seeders", 0)) < \
                (PRIORIDADE_FONTE[atual["fonte"]], -atual.get("seeders", 0)):
            melhor[k] = r
    return list(melhor.values())


def ordenar(rs: list[dict]) -> list[dict]:
    return sorted(rs, key=lambda r: (-r.get("score", 0), PRIORIDADE_FONTE[r["fonte"]], -(r.get("seeders") or 0),
                                     r["titulo"].casefold()))


# --------------------------------------------------------------------------------------------- sessões
def nova_sessao(cfg: dict, uid: int, resposta: dict, agora: float | None = None) -> str:
    """Guarda a busca com identidade própria: botão de busca antiga ou de outra busca nunca aponta outro jogo."""
    import secrets
    agora = time.time() if agora is None else agora
    sessoes = cfg.setdefault("buscas", {})
    for sid in [s for s, v in sessoes.items() if agora - v.get("at", 0) > TTL_SESSAO]:
        sessoes.pop(sid)
    while len(sessoes) >= MAX_SESSOES:
        sessoes.pop(min(sessoes, key=lambda s: sessoes[s].get("at", 0)))
    sid = secrets.token_hex(3)
    sessoes[sid] = {"uid": uid, "at": agora, "consulta": resposta["consulta"], "fontes": resposta["fontes"],
                    "resultados": resposta["resultados"][:200], "filtro": None}
    cfg["ultima_busca"] = {str(uid): sid}
    return sid


def sessao(cfg: dict, sid: str, uid: int, agora: float | None = None) -> dict | None:
    s = (cfg.get("buscas") or {}).get(sid)
    agora = time.time() if agora is None else agora
    if not s or s.get("uid") != uid or agora - s.get("at", 0) > TTL_SESSAO:
        return None
    return s


def item(s: dict, rid: str) -> dict | None:
    return next((r for r in s["resultados"] if r["rid"] == rid), None)


def visiveis(s: dict) -> list[dict]:
    return [r for r in s["resultados"] if not s.get("filtro") or r.get("console") == s["filtro"]]


# ------------------------------------------------------------------------------------------- apresentação
def tamanho_txt(n) -> str:
    if not isinstance(n, (int, float)) or n <= 0:
        return "tamanho ?"
    for unidade, base in (("GB", 2**30), ("MB", 2**20), ("KB", 2**10)):
        if n >= base:
            return f"{n / base:.1f} {unidade}".replace(".0 ", " ")
    return f"{int(n)} B"


NOME_FONTE = {"biblioteca": "sua biblioteca", "catalogo": "catálogo verificado", "familia": "Deck da família",
              "internet_archive": "Internet Archive", "prowlarr": "Prowlarr"}


def linha(r: dict, rotulo) -> str:
    partes = [rotulo(r["console"]) if r.get("console") else "plataforma ?"]
    if r.get("regiao"):
        partes.append(r["regiao"])
    if r["fonte"] != "biblioteca":
        partes.append(tamanho_txt(r.get("tamanho")))
    if r.get("formato"):
        partes.append(r["formato"])
    if r.get("ptbr"):
        partes.append("🇧🇷 PT-BR")
    marca = "✅ na biblioteca" if r["fonte"] == "biblioteca" else NOME_FONTE[r["fonte"]]
    return f"{r['titulo']}\n   {' · '.join(partes)} · {marca}"


def resumo_fontes(fontes: dict) -> str:
    ruins = [f"{NOME_FONTE.get(f, f)}: {e}" for f, e in fontes.items() if e not in (OK, VAZIO, NAO_CONFIG)]
    return ("⚠️ " + "; ".join(ruins) + " — resultado parcial.") if ruins else ""


def pagina(s: dict, sid: str, n: int, rotulo) -> tuple[str, list[tuple[str, str]]]:
    vis = visiveis(s)
    q = s["consulta"]
    alvo = f"«{q['termos']}»" + (f" ({rotulo(q['console'])})" if q.get("console") else " em todas as plataformas")
    aviso = resumo_fontes(s["fontes"])
    if not vis:
        if any(e in (FORA, TEMPO, AUTH, ERRO) for e in s["fontes"].values()) and not any(
                e == OK for e in s["fontes"].values()):
            return (f"Não consegui pesquisar {alvo}: as fontes falharam.\n{aviso}\nTente de novo em alguns minutos.",
                    [("🔁 Tentar de novo", f"/busca {q['termos']}" + (f" {q['console']}" if q.get('console') else ""))])
        sem = "Nenhum resultado para " + alvo + (f" com o filtro {rotulo(s['filtro'])}" if s.get("filtro") else "") + "."
        return sem + (f"\n{aviso}" if aviso else "") + "\nTente outro nome, parte do nome ou sem a plataforma.", []
    total = len(vis)
    paginas = (total + POR_PAGINA - 1) // POR_PAGINA
    n = max(0, min(n, paginas - 1))
    fatia = vis[n * POR_PAGINA:(n + 1) * POR_PAGINA]
    texto = [f"🔎 {alvo}: {total} resultado(s)" + (f" — página {n + 1}/{paginas}" if paginas > 1 else "")]
    if s.get("filtro"):
        texto[0] += f" · filtro: {rotulo(s['filtro'])}"
    for i, r in enumerate(fatia, 1 + n * POR_PAGINA):
        texto.append(f"{i}. {linha(r, rotulo)}")
    if aviso:
        texto.append(aviso)
    botoes = [(f"{i}. {r['titulo'][:40]}", f"/bi {sid} {r['rid']}") for i, r in enumerate(fatia, 1 + n * POR_PAGINA)]
    if n > 0:
        botoes.append(("◀ Anterior", f"/bp {sid} {n - 1}"))
    if n + 1 < paginas:
        botoes.append(("Próxima ▶", f"/bp {sid} {n + 1}"))
    consoles = sorted({r["console"] for r in s["resultados"] if r.get("console")})
    if not q.get("console") and len(consoles) > 1:
        if s.get("filtro"):
            botoes.append(("Todas as plataformas", f"/bf {sid} todas"))
        for c in consoles[:8]:
            if c != s.get("filtro"):
                botoes.append((f"Só {rotulo(c)}", f"/bf {sid} {c}"))
    return "\n".join(texto), botoes
