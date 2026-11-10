"""RPG Maker MV/MZ: textos dos JSON da pasta data/ (ou www/data/).

O que é traduzido (formato público dos projetos MV/MZ, igual ao que o editor salva):
- eventos (Map###.json → events[].pages[].list, CommonEvents.json → [].list, Troops.json → [].pages[].list):
  401 texto da mensagem, 405 texto rolante, 102 escolhas (parameters[0] é a lista), 402 "quando escolher X",
  320/324/325 mudar nome/apelido/perfil, e o nome de quem fala no 101 do MZ (parameters[4]);
- displayName dos mapas (o nome que aparece ao entrar no mapa);
- System.json: terms.messages / commands / basic / params e as listas de tipos (armas, armaduras, habilidades,
  elementos, equipamentos). O gameTitle NÃO (ele vira o título da janela e às vezes nome de save);
- banco de dados: Actors/Classes/Items/Weapons/Armors/Skills/States/Enemies (name, description, nickname,
  profile, message1..4).

Mensagens (401/405): várias linhas seguidas com o mesmo recuo são UMA fala na tela. A IA recebe a fala inteira
(linhas unidas com \\n, que ela não pode mexer) e a gente devolve no MESMO número de comandos: se vier com mais
linhas, o excesso entra na última; se vier com menos, quebramos por palavra até caber no número original.
Nunca criamos comandos novos (mudaria os índices dos eventos e os saltos/ramos do RPG Maker).

O JSON é regravado no mesmo estilo do editor: sem espaços e sem escapar acentos; os arquivos do banco de dados
(que o MV salva com um item por linha) mantêm um item por linha.

VX Ace / VX / XP (.rvdata2/.rvdata/.rxdata, Ruby Marshal): só detecta; ainda não traduz.
"""
from __future__ import annotations

import copy
import json
import re
from typing import Any

from .motores import Coleta, MotorError, Texto

NAME = "RPG Maker"

# \C[2] \N[1] \V[3] \I[64] \FS[24] (plugins) \G \{ \} \$ \. \| \! \> \< \^ \\, %1 dos termos, <tags> de plugin
CODES_RPGM = re.compile(r"\\[A-Za-z]+(?:\[[^\]]*\]|<[^>]*>)?|\\[{}$.|!><^\\]|%\d+|<[^>]*>|\r?\n")

_DATA = re.compile(r"(?:^|/)data/([^/]+\.json)$", re.IGNORECASE)
_RUBY = (".rvdata2", ".rvdata", ".rxdata")

_DB = {
    "actors.json": ("name", "nickname", "profile"),
    "classes.json": ("name",),
    "items.json": ("name", "description"),
    "weapons.json": ("name", "description"),
    "armors.json": ("name", "description"),
    "skills.json": ("name", "description", "message1", "message2"),
    "states.json": ("name", "message1", "message2", "message3", "message4"),
    "enemies.json": ("name",),
}
_SYS_TERMOS = ("commands", "basic", "params")
_SYS_LISTAS = ("armorTypes", "weaponTypes", "skillTypes", "elements", "equipTypes")


def _norm(p: str) -> str:
    return p.replace("\\", "/")


def detect(paths: list[str]) -> bool:
    for p in paths:
        m = _DATA.search(_norm(p))
        if m and re.fullmatch(r"(map\d{3}|system|commonevents|actors)\.json", m.group(1).lower()):
            return True
        if p.lower().endswith(_RUBY) and "/data/" in _norm(p).lower():
            return True
    return False


# ================================================================== onde ficam os textos
def _p(c: list) -> str:
    return "/".join(str(x) for x in c)


def _lista(base: list, lst: Any, out: list, blocos: set) -> None:
    if not isinstance(lst, list):
        return
    i = 0
    while i < len(lst):
        cmd = lst[i]
        if not isinstance(cmd, dict):
            i += 1
            continue
        code, par = cmd.get("code"), cmd.get("parameters") or []
        if code in (401, 405):
            j, linhas, caminhos = i, [], []
            while j < len(lst) and isinstance(lst[j], dict) and lst[j].get("code") == code \
                    and lst[j].get("indent") == cmd.get("indent"):
                pj = lst[j].get("parameters") or [""]
                linhas.append(pj[0] if isinstance(pj[0], str) else str(pj[0]))
                caminhos.append(base + [j, "parameters", 0])
                j += 1
            out.append((caminhos, "\n".join(linhas)))
            blocos.add(_p(caminhos[0]))
            i = j
            continue
        if code == 102 and par and isinstance(par[0], list):
            for k, ch in enumerate(par[0]):
                if isinstance(ch, str):
                    out.append(([base + [i, "parameters", 0, k]], ch))
        elif code in (402, 320, 324, 325) and len(par) > 1 and isinstance(par[1], str):
            out.append(([base + [i, "parameters", 1]], par[1]))
        elif code == 101 and len(par) > 4 and isinstance(par[4], str):
            out.append(([base + [i, "parameters", 4]], par[4]))
        i += 1


def achar(nome: str, obj: Any) -> tuple[list, set]:
    """[(caminhos, texto)] de um arquivo data/*.json e o conjunto de ids que são mensagens (blocos 401/405)."""
    n = nome.lower()
    out: list = []
    blocos: set = set()
    if re.fullmatch(r"map\d+\.json", n) and isinstance(obj, dict):
        if isinstance(obj.get("displayName"), str):
            out.append(([["displayName"]], obj["displayName"]))
        for e, ev in enumerate(obj.get("events") or []):
            if isinstance(ev, dict):
                for g, pg in enumerate(ev.get("pages") or []):
                    if isinstance(pg, dict):
                        _lista(["events", e, "pages", g, "list"], pg.get("list"), out, blocos)
    elif n == "commonevents.json" and isinstance(obj, list):
        for e, ev in enumerate(obj):
            if isinstance(ev, dict):
                _lista([e, "list"], ev.get("list"), out, blocos)
    elif n == "troops.json" and isinstance(obj, list):
        for e, tr in enumerate(obj):
            if isinstance(tr, dict):
                for g, pg in enumerate(tr.get("pages") or []):
                    if isinstance(pg, dict):
                        _lista([e, "pages", g, "list"], pg.get("list"), out, blocos)
    elif n == "system.json" and isinstance(obj, dict):
        termos = obj.get("terms") or {}
        msgs = termos.get("messages")
        if isinstance(msgs, dict):
            for k, v in msgs.items():
                if isinstance(v, str):
                    out.append(([["terms", "messages", k]], v))
        for t in _SYS_TERMOS:
            for k, v in enumerate(termos.get(t) or []):
                if isinstance(v, str):
                    out.append(([["terms", t, k]], v))
        for t in _SYS_LISTAS:
            for k, v in enumerate(obj.get(t) or []):
                if isinstance(v, str):
                    out.append(([[t, k]], v))
    elif n in _DB and isinstance(obj, list):
        for k, it in enumerate(obj):
            if isinstance(it, dict):
                for c in _DB[n]:
                    if isinstance(it.get(c), str):
                        out.append(([[k, c]], it[c]))
    return out, blocos


def _get(obj, cam):
    for k in cam:
        obj = obj[k]
    return obj


def _set(obj, cam, v):
    for k in cam[:-1]:
        obj = obj[k]
    obj[cam[-1]] = v


# ================================================================== quebra das mensagens
def _visivel(s: str) -> int:
    return len(CODES_RPGM.sub("", s))


def distribuir(novo: str, originais: list[str]) -> list[str]:
    """Põe a fala traduzida em exatamente len(originais) linhas (sem criar comandos novos)."""
    n = len(originais)
    linhas = novo.split("\n")
    if len(linhas) > n:
        resto = " ".join(x.strip() for x in linhas[n - 1:] if x.strip())
        linhas = linhas[:n - 1] + [resto]
    elif len(linhas) < n and n > 1:
        largura = max([_visivel(x) for x in originais] + [20])
        palavras = " ".join(linhas).split(" ")
        linhas, atual = [], ""
        for w in palavras:
            teste = f"{atual} {w}" if atual else w
            if atual and _visivel(teste) > largura and len(linhas) < n - 1:
                linhas.append(atual)
                atual = w
            else:
                atual = teste
        linhas.append(atual)
    return linhas + [""] * (n - len(linhas))


# ================================================================== JSON no estilo do editor
def _compacto(x) -> str:
    return json.dumps(x, ensure_ascii=False, separators=(",", ":"))


def _estilo(t: str, obj) -> str:
    return "linhas" if isinstance(obj, list) and t.startswith("[\n") else "compacto"


def _dump(obj, estilo: str, final_nl: bool) -> str:
    if estilo == "linhas":
        s = "[\n" + ",\n".join(_compacto(x) for x in obj) + "\n]"
    else:
        s = _compacto(obj)
    return s + ("\n" if final_nl else "")


# ================================================================== contrato
def collect(files: dict, read) -> Coleta:
    paths = list(files)
    jsons = [p for p in paths if _DATA.search(_norm(p))]
    ruby = [p for p in paths if p.lower().endswith(_RUBY)]
    alvo = []
    for p in jsons:
        nome = _DATA.search(_norm(p)).group(1)
        n = nome.lower()
        if re.fullmatch(r"map\d+\.json", n) or n in ("commonevents.json", "troops.json", "system.json") or n in _DB:
            alvo.append((p, nome))
    if not alvo:
        if ruby:
            raise MotorError("RPG Maker VX Ace/VX/XP (dados .rvdata2/.rvdata/.rxdata em Ruby Marshal): "
                             "esse formato ainda não é suportado")
        raise MotorError("RPG Maker sem arquivos data/*.json de texto")
    # id usa só o nome do arquivo (ex.: "Map001.json|..."); se o mesmo nome aparecer em duas pastas, usa o caminho
    contagem: dict[str, int] = {}
    for _, nome in alvo:
        contagem[nome] = contagem.get(nome, 0) + 1

    textos: list[Texto] = []
    estado: dict[str, dict] = {}       # caminho -> info do arquivo
    destino: dict[str, tuple[str, list, bool]] = {}   # id -> (caminho, caminhos no JSON, é bloco)
    for p, nome in alvo:
        raw = read(p)
        bom = raw.startswith(b"\xef\xbb\xbf")
        try:
            t = raw.decode("utf-8-sig")
            obj = json.loads(t)
        except (UnicodeDecodeError, ValueError) as e:
            raise MotorError(f"{p}: JSON ilegível ({e}); pode estar criptografado pelo porte") from e
        pref = nome if contagem[nome] == 1 else p
        estado[p] = {"obj": obj, "estilo": _estilo(t, obj), "nl": t.endswith("\n"), "bom": bom,
                     "pref": pref, "nome": nome}
        achados, blocos = achar(nome, obj)
        for caminhos, s in achados:
            if not s.strip():
                continue
            tid = f"{pref}|{_p(caminhos[0])}"
            textos.append(Texto(tid, s, CODES_RPGM))
            destino[tid] = (p, caminhos, _p(caminhos[0]) in blocos)

    aviso = ""
    if ruby:
        aviso = "há arquivos .rvdata2/.rvdata/.rxdata (Ruby Marshal) que não foram traduzidos"

    def rebuild(trads: dict[str, str]) -> dict[str, bytes]:
        por_arq: dict[str, list] = {}
        for tid, s in trads.items():
            if tid in destino:
                p, caminhos, bloco = destino[tid]
                por_arq.setdefault(p, []).append((tid, caminhos, bloco, s))
        out: dict[str, bytes] = {}
        for p, lista in por_arq.items():
            st = estado[p]
            obj = copy.deepcopy(st["obj"])
            esperado = {}
            for tid, caminhos, bloco, s in lista:
                if bloco:
                    orig = [_get(st["obj"], c) for c in caminhos]
                    linhas = distribuir(s, orig)
                    for c, ln in zip(caminhos, linhas):
                        _set(obj, c, ln)
                    esperado[tid] = "\n".join(linhas)
                else:
                    # escolha/nome em comando de evento é uma linha só na tela: quebra vira espaço
                    s1 = re.sub(r"\s*\r?\n\s*", " ", s) if "parameters" in caminhos[0] else s
                    _set(obj, caminhos[0], s1)
                    esperado[tid] = s1
            dados = (b"\xef\xbb\xbf" if st["bom"] else b"") + _dump(obj, st["estilo"], st["nl"]).encode("utf-8")
            _conferir(p, st, dados, esperado)
            out[p] = dados
        return out

    return Coleta(textos, rebuild, aviso, {"arquivos": sorted(estado)})


def _conferir(p: str, st: dict, dados: bytes, esperado: dict[str, str]) -> None:
    """Relê o JSON gerado: mesmos textos nos mesmos lugares, só os traduzidos mudaram."""
    try:
        novo = json.loads(dados.decode("utf-8-sig"))
    except ValueError as e:
        raise MotorError(f"{p}: JSON gerado não abre ({e})") from e
    antes = {f"{st['pref']}|{_p(c[0])}": s for c, s in achar(st["nome"], st["obj"])[0]}
    depois = {f"{st['pref']}|{_p(c[0])}": s for c, s in achar(st["nome"], novo)[0]}
    antes.update(esperado)
    if antes != depois:
        ruins = sorted(k for k in antes.keys() | depois.keys() if antes.get(k) != depois.get(k))
        raise MotorError(f"{p}: releitura não confere ({', '.join(ruins[:5])})")
