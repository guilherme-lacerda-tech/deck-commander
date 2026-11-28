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
# Palavras de franquias comuns: corrigem erro de digitação ANTES de consultar fontes remotas (que só acham a palavra
# exata). Somadas às palavras dos títulos da biblioteca do dono e do catálogo.
VOCABULARIO = set("""
resident evil final fantasy kingdom hearts metal gear solid legend zelda mario kart pokemon sonic hedgehog street
fighter castlevania metroid devil may cry tekken crash bandicoot spyro dragon silent hill quest ball soulcalibur
persona shin megami tensei gran turismo need speed grand theft auto ratchet clank jak daxter sly cooper shadow
colossus okami halo gears forza fable smash bros donkey kong kirby yoshi pikmin xenoblade fire emblem monster
hunter bloodborne souls sekiro naruto bleach digimon yugioh warriors dynasty samurai ninja gaiden onimusha
chronicles symphony night tactics vagrant story chrono trigger cross breath wild tears ocarina majora twilight
princess skyward wind waker galaxy sunshine odyssey party paper luigi mansion wario animal crossing splatoon
burnout midnight club tony hawk skate guitar hero rock band dance just sims spider batman arkham lego star wars
harry potter assassin creed prince persia splinter cell rainbow call duty battlefield medal honor doom quake
wolfenstein half life portal counter strike bioshock fallout elder scrolls skyrim oblivion witcher mass effect
dragon age god war ghost sparta chains olympus ascension hand drakengard nier ace combat ridge racer tekken
""".split())
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


def corrigir(texto: str, vocab: set[str]) -> str:
    """Troca palavra quase igual a uma conhecida ("evl" -> "evil", "kingdon" -> "kingdom")."""
    out = []
    for w in texto.split():
        n = normalizar(w)
        if len(n) >= 3 and n not in vocab and not n.isdigit():
            perto = difflib.get_close_matches(n, vocab, n=1, cutoff=0.8)
            out.append(perto[0] if perto else w)
        else:
            out.append(w)
    return " ".join(out)


def _vocabulario(paths) -> set[str]:
    v = set(VOCABULARIO)
    try:
        from . import transferir
        for e in transferir.carregar_mapa().values():
            v.update(normalizar(e.get("title", "")).split())
    except Exception:  # noqa: BLE001, S110 — vocabulário extra é conforto
        pass
    return {w for w in v if len(w) >= 3}


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


PACOTE_RX = re.compile(r"(?i)\b(roms|collection|cole[cç][aã]o|pack|complete set|full set|bundle|todos os jogos)\b")
PACOTE_GRANDE = 40 * 2**30  # nenhum jogo avulso das plataformas suportadas chega perto disso


def limpar_titulo(titulo: str) -> str:
    """Tira número de catálogo do começo ('1635 Pokemon Fire Red' -> 'Pokemon Fire Red'): no Internet Archive
    muitos itens vêm assim e iam para o topo da lista na ordem alfabética."""
    limpo = re.sub(r"^\s*\(?\d{3,5}\)?\s*[-–.]?\s+(?=\D)", "", titulo or "")
    return limpo or titulo


def eh_pacote(r: dict) -> bool:
    return bool(PACOTE_RX.search(r.get("titulo") or "")) or (r.get("tamanho") or 0) > PACOTE_GRANDE


def resultado(fonte: str, ref: str, titulo: str, console: str | None, **extra) -> dict:
    titulo = limpar_titulo(titulo)
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


PALAVRAS_PLATAFORMA = {  # como cada plataforma aparece em título/assunto/descrição nas fontes
    "psp": ["psp", "playstation portable"], "ps2": ["ps2", "playstation 2"], "psx": ["psx", "ps1", "playstation"],
    "ps3": ["ps3", "playstation 3"], "gc": ["gamecube", "ngc"], "wii": ["wii"], "wiiu": ["wii u", "wiiu"],
    "switch": ["switch", "nsp", "xci"], "n64": ["n64", "nintendo 64"], "snes": ["snes", "super nintendo"],
    "nes": ["nes", "famicom"], "gba": ["gba", "game boy advance"], "gb": ["game boy", "gameboy"],
    "gbc": ["game boy color", "gbc"], "nds": ["nds", "nintendo ds"], "n3ds": ["3ds", "nintendo 3ds"],
    "genesis": ["genesis", "mega drive", "megadrive"], "sms": ["master system"], "gg": ["game gear"],
    "dc": ["dreamcast"], "saturn": ["saturn"], "segacd": ["sega cd", "mega cd"], "xbox": ["xbox"],
    "x360": ["xbox 360", "x360"], "pce": ["pc engine", "turbografx"], "arcade": ["arcade", "mame"],
    "pc": ["pc", "windows", "dos"],
}


def _ia_console(doc: dict) -> str | None:
    c = console_de(doc.get("title", ""))
    if c:
        return c
    # "assunto" do item: ["God of War: Ghost of Sparta", "PSP", "ROM"] — o título sozinho não dizia a plataforma e o
    # Ghost of Sparta sumia do filtro PSP (teste real do dono, 28/11/2026)
    assunto = doc.get("subject") or []
    for s in ([assunto] if isinstance(assunto, str) else assunto):
        c = console_de("", str(s)) if len(str(s)) <= 40 else None
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
    filtro = ""
    if q.get("console"):  # plataforma pedida: a própria fonte filtra (antes só filtrava os 60 mais baixados)
        nomes = PALAVRAS_PLATAFORMA.get(q["console"], [q["console"]])
        alt = " OR ".join(f'"{n}"' if " " in n else n for n in nomes)
        filtro = f" AND (title:({alt}) OR subject:({alt}) OR description:({alt}))"
    params = {"q": f"title:({palavras}){filtro} AND mediatype:software AND format:(\"Archive BitTorrent\")",
              "fl[]": ["identifier", "title", "item_size", "licenseurl", "collection", "emulator", "year", "language",
                       "subject", "downloads"],
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
                             popularidade=d.get("downloads") if isinstance(d.get("downloads"), int) else 0,
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
    from .prowlarr import BuscaErro, BuscaTempo, SemIndexadores
    if isinstance(exc, (_NaoConfigurado, SemIndexadores)):
        return NAO_CONFIG
    if isinstance(exc, BuscaTempo):
        return TEMPO
    if isinstance(exc, BuscaErro):
        return FORA
    if isinstance(exc, (TimeoutError, cf.TimeoutError)) or "timed out" in str(exc).lower():
        return TEMPO
    if isinstance(exc, urllib.error.HTTPError) and exc.code in (401, 403):
        return AUTH
    if isinstance(exc, OSError):
        return FORA
    return ERRO


# ------------------------------------------------------------------------------------------------ busca
def pesquisar(paths, texto: str, provedores=None, funcs=None) -> dict:
    """Roda as fontes em paralelo. Devolve {"consulta", "resultados", "fontes": {fonte: estado}}.
    Erro de digitação: pesquisa primeiro como foi escrito; só sem nenhum resultado tenta a palavra corrigida
    (corrigir antes trocava nomes certos, ex.: "hollow knight" -> "night")."""
    q = interpretar(texto)
    funcs = funcs or PROVEDORES
    provs = list(provedores or config(paths)["provedores"])
    if not (q["termos"] or "").strip():
        return {"consulta": q, "resultados": [], "fontes": {}}
    resultados, fontes = _rodada(paths, q, provs, funcs)
    if not resultados:
        corrigido = corrigir(q["busca"], _vocabulario(paths))
        if normalizar(corrigido) != normalizar(q["busca"]):
            q2 = {**q, "busca": corrigido, "corrigido": corrigido}
            r2, f2 = _rodada(paths, q2, provs, funcs)
            if r2:
                return {"consulta": q2, "resultados": r2, "fontes": f2}
    return {"consulta": q, "resultados": resultados, "fontes": fontes}


def _rodada(paths, q: dict, provs: list[str], funcs: dict) -> tuple[list[dict], dict[str, str]]:
    fontes: dict[str, str] = {}
    brutos: list[dict] = []
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
    return ordenar(deduplicar(brutos)), fontes


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
    # o que já está na biblioteca nunca "engole" a versão para baixar (pode ser outra região/versão): fica separado
    return (r["fonte"] == "biblioteca", normalizar(r["titulo"]), r.get("console"), r.get("regiao"),
            round(tam / 2**20) if tam else None)


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
    """Mais parecido com o que foi digitado; empatou: plataforma conhecida, PT-BR, jogo avulso antes de pacote, fonte,
    seeders e popularidade — só no fim o alfabeto (antes '1635 Pokemon…' e 'plataforma ?' iam para o topo)."""
    return sorted(rs, key=lambda r: (-round(r.get("score", 0), 1), r.get("console") is None, not r.get("ptbr"),
                                     eh_pacote(r), PRIORIDADE_FONTE[r["fonte"]], -(r.get("seeders") or 0),
                                     -(r.get("popularidade") or 0), r["titulo"].casefold()))


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
    """O que dá para BAIXAR. O que já está na biblioteca vai numa linha à parte (dono, 28/11/2026: "pra que eu vou
    querer baixar o que eu já tenho?")."""
    return [r for r in s["resultados"] if r["fonte"] != "biblioteca"
            and (not s.get("filtro") or r.get("console") == s["filtro"])]


def ja_tem(s: dict) -> list[dict]:
    return [r for r in s["resultados"] if r["fonte"] == "biblioteca"
            and (not s.get("filtro") or r.get("console") == s["filtro"])]


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
    if r.get("formato") and r["formato"].casefold() not in (partes[0].casefold(), str(r.get("console")).casefold()):
        partes.append(r["formato"])  # "NES · 40 KB · NES" repetia a plataforma (visto no Telegram, 28/11/2026)
    if r.get("ptbr"):
        partes.append("🇧🇷 PT-BR")
    if r["fonte"] != "biblioteca" and eh_pacote(r):
        partes.append("📦 pacote com vários jogos")
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
    tem = ja_tem(s)
    linha_tem = ("✅ Você já tem: " + "; ".join(f"{r['titulo']} ({rotulo(r['console'])})" for r in tem[:6])
                 + (f" e mais {len(tem) - 6}" if len(tem) > 6 else "")) if tem else ""
    meus = {(normalizar(r["titulo"]), r.get("console")) for r in tem}
    if not vis:
        if tem and not any(e in (FORA, TEMPO, AUTH, ERRO) for e in s["fontes"].values()):
            return (f"{linha_tem}\nNada novo para baixar em {alvo} nas fontes ligadas." + (f"\n{aviso}" if aviso else ""), [])
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
    texto = [f"🔎 {alvo}: {total} para baixar" + (f" — página {n + 1}/{paginas}" if paginas > 1 else "")]
    if linha_tem and n == 0:
        texto.append(linha_tem)
    if q.get("corrigido"):
        texto.append(f"(mostrando resultados para «{q['corrigido']}»)")
    if s.get("filtro"):
        texto[0] += f" · filtro: {rotulo(s['filtro'])}"
    for i, r in enumerate(fatia, 1 + n * POR_PAGINA):
        mesmo = (normalizar(r["titulo"]), r.get("console")) in meus
        texto.append(f"{i}. {linha(r, rotulo)}" + (" · ✅ já tem um com esse nome" if mesmo else ""))
    if aviso:
        texto.append(aviso)
    # cada jogo: "ℹ️ detalhes" e, se dá para baixar no Deck, "⬇️" na MESMA linha (teste real 28/11/2026: só o nome
    # levava aos detalhes e o dono não achou o botão de baixar)
    from . import dispositivos
    botoes: list = []
    for i, r in enumerate(fatia, 1 + n * POR_PAGINA):
        info = (f"ℹ️ {i}. {r['titulo'][:36]}", f"/bi {sid} {r['rid']}")
        pode = r["fonte"] != "biblioteca" and dispositivos.compatibilidade("deck", r.get("console"))[0] != "nao"
        botoes.append([info, (f"⬇️ {i}", f"/bd {sid} {r['rid']} deck")] if pode else [info])
    nav = []
    if n > 0:
        nav.append(("◀ Anterior", f"/bp {sid} {n - 1}"))
    if n + 1 < paginas:
        nav.append(("Próxima ▶", f"/bp {sid} {n + 1}"))
    if nav:
        botoes.append(nav)
    consoles = sorted({r["console"] for r in s["resultados"] if r.get("console")})
    if not q.get("console") and len(consoles) > 1:
        # filtros 3 por linha (teste real 28/11/2026: um por linha virava uma parede de botões)
        filtros = ([("Todas", f"/bf {sid} todas")] if s.get("filtro") else []) + [
            (f"Só {rotulo(c)}", f"/bf {sid} {c}") for c in consoles[:9] if c != s.get("filtro")]
        botoes += [filtros[i:i + 3] for i in range(0, len(filtros), 3)]
    return "\n".join(texto), botoes
