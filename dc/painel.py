"""Painel do Deck (plugin do Decky, menu "…"): ações em JSON para a interface gráfica.

    python3 -m dc.painel <acao> [json]     (o json também pode vir pela entrada padrão — é assim que o
                                            plugin manda, para o token do Telegram não aparecer no `ps`)

Saída: uma linha JSON — {"ok": true, ...} ou {"ok": false, "erro": "mensagem em linguagem simples"}.

Nada de regra de negócio aqui: cada ação chama as MESMAS funções do bot do Telegram (bot.Bot, traducao.comandos,
pc_remoto, transferir, quality, controls, health, telegram_setup) e só adapta a entrada/saída.
O painel nunca grava o telegram.json (quem grava é o bot que está rodando) e o token nunca sai daqui
(nem na resposta, nem no log).
"""
from __future__ import annotations

import base64
import glob
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import tomllib

from . import ops
from .bot import Bot, pair_code, pairing_code_valid
from .paths import Paths, get_paths
from .qbt import Qbt, QbtError

TOKEN_RX = re.compile(r"\d{6,12}:[A-Za-z0-9_-]{30,50}")


class Erro(Exception):
    """Erro já explicado para a pessoa (vai direto para a tela)."""


def _limpo(s: str) -> str:
    return TOKEN_RX.sub("***", str(s))


def _sem_comandos(txt: str) -> str:
    """Tira as instruções de Telegram ("Confirme: /remover …", "(/transferir fila)") do texto do bot."""
    linhas = [ln for ln in (txt or "").splitlines() if not ln.strip().startswith("Confirme: /")]
    return re.sub(r"\s*\(/[a-z]+ [^)]*\)", "", "\n".join(linhas)).strip()


class Ponte:
    """Faz o papel do `Bot` para reaproveitar os comandos dele sem Telegram."""

    _map = Bot._map
    _battery = Bot._battery
    _power_state = Bot._power_state
    _power_note = Bot._power_note
    _duplicates = Bot._duplicates
    _remove = Bot._remove
    _quality = Bot._quality

    def __init__(self, paths: Paths, qbt=None, store=None):
        self.paths = paths
        self.qbt = qbt if qbt is not None else Qbt(timeout=8)
        self._store = store
        try:
            self.cfg = json.loads((paths.config / "telegram.json").read_text("utf-8"))
        except (OSError, ValueError):
            self.cfg = {}
        self.cfg.setdefault("allowed", [])
        self.enviadas: list[str] = []

    @property
    def store(self):
        if self._store is None:
            from .store import Store
            self._store = Store(self.paths.db)
        return self._store

    def save_cfg(self) -> None:  # telegram.json é do bot em execução: o painel não grava
        pass

    def send(self, chat, text, buttons=None) -> None:
        self.enviadas.append(text)


# ----------------------------------------------------------------------------------------------- status
ESTADOS = {"downloading": "baixando", "forcedDL": "baixando", "stalledDL": "sem fontes (esperando)",
           "metaDL": "buscando informações", "forcedMetaDL": "buscando informações", "pausedDL": "pausado",
           "stoppedDL": "pausado", "queuedDL": "na fila", "checkingDL": "conferindo", "checkingResumeData": "conferindo",
           "error": "erro (disco cheio ou cartão SD fora?)", "missingFiles": "erro (arquivos sumiram)",
           "moving": "movendo"}


def _downloads(p: Ponte) -> list[dict]:
    from .qbt import DONE_STATES
    out = []
    for t in p.qbt.torrents():
        st = t.get("state", "")
        eta = t.get("eta") or 0
        out.append({"hash": t.get("hash"), "nome": t.get("name") or "download", "pct": round((t.get("progress") or 0) * 100),
                    "estado": "concluído" if st in DONE_STATES else ESTADOS.get(st, st),
                    "pausado": st in ("pausedDL", "stoppedDL"), "concluido": st in DONE_STATES,
                    "eta_min": eta // 60 if 0 < eta < 8640000 else None,
                    "velocidade_kb": round((t.get("dlspeed") or 0) / 1024)})
    return out


def _espaco() -> list[dict]:
    out = [{"onde": "memória interna", "livre_gb": shutil.disk_usage(Path.home()).free // 10**9}]
    for m in glob.glob("/run/media/*/*"):
        if os.path.ismount(m):
            out.append({"onde": f"cartão SD ({Path(m).name})", "livre_gb": shutil.disk_usage(m).free // 10**9})
    return out


def _traducoes_ativas(p: Ponte) -> list[dict]:
    from .traducao import comandos, run
    out = []
    for j in run.all_jobs(p.paths):
        if j.get("status") not in comandos.ATIVOS:
            continue
        d, tot = (j.get("progress") or [0, 0])[:2]
        out.append({"op": j["op"], "titulo": j.get("title", j["op"]), "status": j["status"],
                    "pct": d * 100 // tot if tot else None, "feito": d, "total": tot,
                    "eta": comandos._eta(p.paths, j).strip(" ·")})
    return out


def status(p: Ponte, a: dict) -> dict:
    flag = ops.safe_mode_flag(p.paths)
    motivo = flag.read_text("utf-8").strip().split(" ", 1)[-1] if flag.exists() else ""
    try:
        dls, erro_dl = _downloads(p), ""
    except QbtError:
        dls, erro_dl = [], "o programa de downloads (qBittorrent) não está respondendo agora"
    energia = p._power_state()
    return {"safe_mode": flag.exists(), "safe_motivo": motivo, "downloads": dls, "erro_downloads": erro_dl,
            "traducoes": _traducoes_ativas(p), "perguntas": len(_perguntas(p)), "espaco": _espaco(),
            "bateria": energia.get("battery"), "downloads_pausados_energia": energia.get("state") == "PAUSE",
            "motivo_energia": energia.get("why", "")}


NOMES_DIAG = {"backup": "Backup", "todos-backups": "Backups", "bios": "BIOS", "config": "Atalhos de jogos",
              "plugins": "Plugins do Decky", "rom-corrompida": "Arquivos de jogo", "db": "Banco de dados",
              "steam-sem-db": "Atalhos do Steam", "controles": "Controles", "duplicatas": "Jogos repetidos",
              "decky": "Decky Loader"}


def diagnostico(p: Ponte, a: dict) -> dict:
    """/diagnostico sem autorreparo (só olha): o que está ok e o que falta fazer."""
    from . import health
    fs = health.diagnose(p.paths, p.store, repair=False)
    problemas = [{"problema": NOMES_DIAG.get(x.problem, x.problem.replace("servico:", "serviço ")),
                  "detalhe": x.detail, "acao": x.action} for x in fs if not x.ok]
    return {"total": len(fs), "certos": len(fs) - len(problemas), "problemas": problemas}


def safe_mode(p: Ponte, a: dict) -> dict:
    if a.get("ligar"):
        ops.safe_mode_on(p.paths, "ligado pelo painel do Deck", p.store)
        return {"texto": "Modo seguro LIGADO: downloads e automações pararam. Nada foi apagado."}
    ops.safe_mode_off(p.paths)
    return {"texto": "Modo seguro desligado: tudo voltou ao normal."}


# ----------------------------------------------------------------------------------------------- telegram
def _qr(link: str) -> str:
    from . import qr
    return "data:image/svg+xml;base64," + base64.b64encode(qr.svg(link).encode()).decode()


def telegram(p: Ponte, a: dict) -> dict:
    from . import telegram_setup
    tok = p.paths.secrets / "telegram"
    configurado = tok.exists()
    usuario = telegram_setup.bot_username(tok.read_text().strip()) if configurado and a.get("conferir", True) else None
    return {"configurado": configurado, "usuario": usuario, "pareado": bool(p.cfg.get("allowed")),
            "codigo_aberto": pairing_code_valid(p.paths) is not None}


def telegram_botfather(p: Ponte, a: dict) -> dict:
    from .telegram_setup import BOTFATHER
    return {"qr": _qr(BOTFATHER), "link": BOTFATHER,
            "passos": "No celular: aponte a câmera para o QR (abre o @BotFather) → INICIAR → mande /newbot → "
                      "escolha um nome → escolha um usuário terminado em bot. Ele responde com um TOKEN "
                      "(ex.: 123456789:AAH…). Digite esse token no campo abaixo."}


def _parear(p: Ponte, usuario: str) -> dict:
    code = pair_code(p.paths)
    link = f"https://t.me/{usuario}?start={code}"
    return {"usuario": usuario, "qr": _qr(link), "link": link, "codigo": code,
            "texto": f"Aponte a câmera para o QR: abre o seu bot (@{usuario}). Toque em INICIAR e pronto. "
                     f"Ou mande para ele: /start {code} (vale 30 minutos)."}


def telegram_token(p: Ponte, a: dict) -> dict:
    from . import telegram_setup
    tok = re.sub(r"\s+", "", a.get("token") or "")
    if len(tok) % 2 == 0 and tok and tok[:len(tok) // 2] == tok[len(tok) // 2:]:
        tok = tok[:len(tok) // 2]  # colado duas vezes
    if not TOKEN_RX.fullmatch(tok):
        raise Erro("Isso não parece um token (formato: números, dois-pontos, letras). Confira e tente de novo.")
    usuario = telegram_setup.bot_username(tok)
    if not usuario:
        raise Erro("O Telegram não reconheceu esse token (ou o Deck está sem internet). Confira e tente de novo.")
    telegram_setup.save_secret(p.paths, "telegram", tok)
    telegram_setup._start_bot_service()
    return {**_parear(p, usuario), "salvo": True}


def telegram_parear(p: Ponte, a: dict) -> dict:
    from . import telegram_setup
    tok = p.paths.secrets / "telegram"
    usuario = telegram_setup.bot_username(tok.read_text().strip()) if tok.exists() else None
    if not usuario:
        raise Erro("Ainda não há bot configurado (ou o Deck está sem internet). Use \"Configurar bot\".")
    return _parear(p, usuario)


# ----------------------------------------------------------------------------------------------- downloads
def downloads(p: Ponte, a: dict) -> dict:
    out = status(p, a)
    cfg = {}
    try:
        cfg = json.loads((p.paths.config / "power.json").read_text("utf-8"))
    except (OSError, ValueError):
        pass
    return {"downloads": out["downloads"], "erro_downloads": out["erro_downloads"],
            "bateria_permitida": bool(cfg.get("allow_on_battery")), "bateria_minima": cfg.get("min_battery_pct", 30),
            "texto_bateria": p._battery([])}


def _pausar(p: Ponte, a: dict, pausar: bool) -> dict:
    try:
        hs = [a["hash"]] if a.get("hash") else [t["hash"] for t in p.qbt.torrents()]
        (p.qbt.pause if pausar else p.qbt.resume)(hs)
    except QbtError:
        raise Erro("O programa de downloads (qBittorrent) não está respondendo agora. Tente daqui a pouco.")
    return {"texto": f"{len(hs)} download(s) {'pausado(s)' if pausar else 'retomado(s)'}."}


def downloads_limpar(p: Ponte, a: dict) -> dict:
    """Tira da lista os downloads que já terminaram E já estão na biblioteca. Os arquivos do jogo ficam."""
    from .qbt import DONE_STATES
    from .syncer import _state
    no_jogo = _state(p.paths).get("ingested", {})
    try:
        feitos = [t for t in p.qbt.torrents() if t.get("state") in DONE_STATES and t["hash"] in no_jogo]
        for t in feitos:
            p.qbt.delete(t["hash"], delete_files=False)  # só a linha da lista; o jogo continua no Deck
    except QbtError:
        raise Erro("O programa de downloads (qBittorrent) não está respondendo agora. Tente daqui a pouco.")
    if not feitos:
        return {"texto": "Nada para limpar: nenhum download concluído que já esteja na biblioteca."}
    return {"texto": f"{len(feitos)} download(s) concluído(s) saíram da lista. Os jogos continuam na biblioteca."}


def traducao_limpar(p: Ponte, a: dict) -> dict:
    """Arquiva o histórico de traduções que já acabaram (concluídas, falhas, recusadas). Traduções instaladas
    ficam; tarefas rodando ou esperando você não são tocadas. Nada é apagado: vai para traducao/arquivo/."""
    from .traducao import run
    manter = set(run.ATIVOS_FILA) | {"aguardando aprovação", "aguardando análise"}
    arq = run.jobs_dir(p.paths) / "arquivo"
    n = 0
    for f in sorted(run.jobs_dir(p.paths).glob("*.json")):
        try:
            j = json.loads(f.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        if j.get("status") in manter or (j.get("pid") and run._alive(j.get("pid"))):
            continue
        arq.mkdir(exist_ok=True)
        f.replace(arq / f.name)
        n += 1
    if not n:
        return {"texto": "Nada para limpar: só há tarefas rodando ou esperando você."}
    return {"texto": f"{n} tarefa(s) antiga(s) saíram do histórico. As traduções instaladas continuam."}


def bateria(p: Ponte, a: dict) -> dict:
    return {"texto": p._battery(["sim" if a.get("permitir") else "nao"])}


def duplicados(p: Ponte, a: dict) -> dict:
    texto = p._duplicates()
    lm = p._map()
    itens = []
    for e in p.cfg.get("listing") or []:
        if "gid" in e:
            g = lm.get(e["gid"], {})
            itens.append({"gid": e["gid"], "titulo": g.get("title", e["gid"]), "console": g.get("console", "")})
        else:
            itens.append({"hash": e["hash"], "titulo": e["name"], "console": "download repetido"})
    return {"itens": itens, "texto": _sem_comandos(texto)}


def remover(p: Ponte, a: dict) -> dict:
    """Sem "confirmar": mostra o que vai acontecer. Com "confirmar": remove (arquivos vão para a quarentena)."""
    if a.get("hash"):
        p.cfg["listing"] = [{"hash": a["hash"], "name": a.get("nome") or "download"}]
        args = ["1"]
    elif a.get("gid"):
        args = [a["gid"]]
    else:
        raise Erro("Escolha um jogo.")
    if a.get("confirmar"):
        args.append("confirmar")
    return {"texto": _sem_comandos(p._remove(args)), "feito": bool(a.get("confirmar"))}


def familia(p: Ponte, a: dict) -> dict:
    from . import familia as fm
    from . import familia_servico as fs
    cfg = fs.config(p.paths)
    par = cfg.get("par") or {}
    return {"configurado": bool(par), "par": par.get("nome", ""), "alvo": par.get("alvo", ""),
            "online": fs.online(p.paths) if par else False, "meu_nome": cfg.get("meu_nome", ""),
            "chave": fs.minha_chave_publica(p.paths),
            "jogos": fs.catalogo_guardado(p.paths).get("jogos", []),
            "pedidos": fm.pedidos(fs._dir(p.paths) / "pedidos.json")[-10:]}


def familia_salvar(p: Ponte, a: dict) -> dict:
    from . import familia_servico as fs
    nome, alvo = (a.get("nome") or "").strip(), (a.get("alvo") or "").strip()
    if not nome or "@" not in alvo:
        raise Erro("Preencha o nome e o endereço (ex.: deck@100.x.y.z, o IP da Tailscale do outro Deck).")
    cfg = fs.config(p.paths)
    cfg["par"] = {"nome": nome, "alvo": alvo, "chave": fs.CHAVE_PADRAO}
    fs.salvar_config(p.paths, cfg)
    return {"texto": "Par guardado. Mande a sua chave para ele autorizar (botão abaixo mostra a chave)."}


def familia_atualizar(p: Ponte, a: dict) -> dict:
    from . import familia_servico as fs
    try:
        fs.publicar(p.paths, p.qbt)
        n = len(fs.catalogo_do_par(p.paths).get("jogos", []))
    except (ValueError, RuntimeError) as e:
        raise Erro(str(e))
    return {"texto": f"{n} jogo(s) no Deck do par."}


def familia_puxar(p: Ponte, a: dict) -> dict:
    from . import familia_servico as fs
    if not a.get("gid"):
        raise Erro("Escolha um jogo.")
    try:
        return {"texto": fs.puxar(p.paths, p.qbt, a["gid"])}
    except (ValueError, RuntimeError) as e:
        raise Erro(str(e))


def espaco_sugestoes(p: Ponte, a: dict) -> dict:
    """Jogos grandes parados há 3+ meses (última vez aberto pelo dc-launch; nunca aberto = data do arquivo)."""
    from . import espaco, remove, syncer
    lm = remove.effective_map(p.paths)
    roots = syncer.rom_roots()

    def tamanho(g: str) -> int:
        try:
            return remove.plan(p.paths, g, roots).size
        except Exception:  # noqa: BLE001
            return 0

    def instalado(g: str):
        try:
            return datetime.fromtimestamp(Path(lm[g]["rom"]).stat().st_mtime, timezone.utc)
        except (OSError, KeyError):
            return None
    itens = espaco.sugestoes(lm, espaco.ultimas_jogadas(p.paths.logs / "launch.log"), tamanho,
                             datetime.now(timezone.utc), data_instalacao=instalado)
    return {"itens": [dict(i, texto=espaco.texto(i)) for i in itens[:10]]}


def desinstalar_lista(p: Ponte, a: dict) -> dict:
    """Jogos do Deck que dá para desinstalar + os que você já tirou do Steam e ainda ocupam espaço."""
    from . import plugin_bridge, remove
    lm = remove.effective_map(p.paths)
    done = json.loads(plugin_bridge.done_path(p.paths).read_text("utf-8")) if plugin_bridge.done_path(p.paths).exists() else {}
    jogos = [{"gid": g, "titulo": e.get("title", g), "console": e.get("console", "")}
             for g, e in sorted(lm.items(), key=lambda kv: kv[1].get("title", "").casefold())
             if not e.get("removed") and e.get("console") != "pc"]
    # "substituido": original escondido porque a versão traduzida entrou no lugar (não é lixo: /devolver traz)
    tirados = [{"gid": g, "titulo": e.get("title", g), "console": e.get("console", ""),
                "substituido": bool((done.get(g) or {}).get("motivo"))}
               for g, e in sorted(remove.removed_games(p.paths).items(), key=lambda kv: kv[1].get("title", "").casefold())
               if e.get("console") != "pc"]
    return {"jogos": jogos, "tirados": tirados}


def devolver(p: Ponte, a: dict) -> dict:
    if not a.get("gid"):
        raise Erro("Escolha um jogo.")
    from . import remove
    titulo = remove.bring_back(p.paths, a["gid"])
    return {"texto": f"{titulo} volta para a biblioteca em instantes."}


def perguntados_path(paths: Paths) -> Path:
    """Jogos tirados pelo Steam cuja pergunta "apagar os arquivos?" já apareceu na tela do Deck."""
    return paths.data / "removidos-perguntados.json"


def removido_perguntado(p: Ponte, a: dict) -> dict:
    if not a.get("gid"):
        raise Erro("Falta o jogo.")
    f = perguntados_path(p.paths)
    try:
        vistos = json.loads(f.read_text("utf-8"))
    except (OSError, ValueError):
        vistos = []
    if a["gid"] not in vistos:
        vistos.append(a["gid"])
        tmp = f.with_name(f.name + ".tmp")
        tmp.write_text(json.dumps(vistos), "utf-8")
        tmp.replace(f)
    return {"texto": "ok"}


# ----------------------------------------------------------------------------------------------- música
def _playlists_path(p: Ponte) -> Path:
    return p.paths.config / "playlists.json"


def musica(p: Ponte, a: dict) -> dict:
    from . import audio
    fl = audio.fluxos()
    vol = {t: max([f["volume"] for f in fl if f["tipo"] == t] or [None], key=lambda v: v or 0) for t in ("jogo", "musica")}
    from . import spotify
    sp = spotify.estado(p.paths)
    if sp["login"]:
        sp["login"]["qr"] = spotify.qr_svg(sp["login"]["url"])
    return {"tocando": audio.tocando(), "volume": vol, "playlists": audio.playlists(_playlists_path(p)), "spotify": sp,
            "minhas": sp["playlists"] if sp["conectado"] else []}


def musica_conectar(p: Ponte, a: dict) -> dict:
    """Entra na conta do Spotify (QR/link) ou, se já entrou, atualiza a lista das suas playlists."""
    from . import spotify
    try:
        r = spotify.atualizar(p.paths)
    except (OSError, RuntimeError) as e:
        raise Erro(f"Não consegui preparar o Spotify do Deck: {e}")
    if r.get("login"):
        return {"texto": "Abra o link no celular (ou leia o QR) e confirme: " + r["login"]["url"]}
    if r.get("conectado"):
        return {"texto": f"Spotify conectado: {len(r['playlists'])} playlist(s) na lista."}
    raise Erro("O Spotify do Deck não respondeu. Tente de novo em alguns segundos.")


def musica_volume(p: Ponte, a: dict) -> dict:
    from . import audio
    tipo = a.get("tipo")
    if tipo not in ("jogo", "musica"):
        raise Erro("Escolha jogo ou música.")
    n = audio.definir_volume(tipo, int(a.get("pct", 100)))
    return {"texto": f"Volume {'do jogo' if tipo == 'jogo' else 'da música'}: {int(a.get('pct', 100))}%"
            if n else ("Nenhum jogo tocando som agora." if tipo == "jogo" else "O Spotify não está tocando agora.")}


def _com_player(acao) -> bool:
    import time

    from . import audio
    if acao():
        return True
    audio.abrir_spotify()  # Spotify fechado: abre e tenta de novo por alguns segundos
    for _ in range(10):
        time.sleep(1.5)
        if acao():
            return True
    return False


def musica_midia(p: Ponte, a: dict) -> dict:
    from . import audio
    acao = a.get("acao", "tocar_pausar")
    if not _com_player(lambda: audio.midia(acao)):
        raise Erro("O Spotify não respondeu. Abra o Spotify uma vez e entre na sua conta.")
    return {"texto": "ok"}


def musica_playlist(p: Ponte, a: dict) -> dict:
    from . import audio
    uri = a.get("uri", "")
    if not uri.startswith("spotify:"):
        raise Erro("Endereço de playlist inválido (copie o link da playlist no Spotify).")
    if not _com_player(lambda: audio.abrir(uri)):
        raise Erro("O Spotify não respondeu. Abra o Spotify uma vez e entre na sua conta.")
    return {"texto": f"Tocando: {a.get('nome') or 'playlist'}"}


def _uri_spotify(link: str) -> str:
    """Aceita o link de compartilhar (https://open.spotify.com/playlist/ID?si=...) ou o spotify:playlist:ID."""
    m = re.search(r"open\.spotify\.com/(?:intl-[a-z]+/)?(playlist|album|artist|track)/([A-Za-z0-9]+)", link or "")
    return f"spotify:{m.group(1)}:{m.group(2)}" if m else (link or "").strip()


def musica_salvar(p: Ponte, a: dict) -> dict:
    from . import audio
    lista = audio.playlists(_playlists_path(p))
    if a.get("remover"):
        lista = [x for x in lista if x.get("nome") != a["remover"]]
    else:
        nome, uri = (a.get("nome") or "").strip(), _uri_spotify(a.get("uri", ""))
        if not nome or not uri.startswith("spotify:"):
            raise Erro("Dê um nome e cole o link da playlist do Spotify (Compartilhar → Copiar link).")
        lista = [x for x in lista if x.get("nome") != nome] + [{"nome": nome, "uri": uri}]
    audio.salvar_playlists(_playlists_path(p), lista)
    return {"texto": "Playlists salvas."}


# ----------------------------------------------------------------------------------------------- tradução
PERGUNTA = {"aguardando sim": "fora", "aguardando ok": "motor"}


def _perguntas(p: Ponte) -> list[dict]:
    from .traducao import run
    out = []
    for j in run.all_jobs(p.paths):
        tipo = PERGUNTA.get(j.get("status"))
        if not tipo:
            continue
        if tipo == "motor":
            from .traducao.motores import fmt_minutes
            of = j.get("oferta") or {}
            txt = (f"{j['title']} é feito em {of.get('motor', '?')}. Achei {of.get('frases', 0)} frases; tempo "
                   f"estimado: {fmt_minutes(int(of.get('minutos', 1)))}. O jogo original não é alterado (vira um mod)."
                   + (f" Obs.: {of['aviso']}" if of.get("aviso") else "") + " Quer que eu traduza?")
        else:
            txt = (f"{j['title']}: o texto não está num formato conhecido. Posso procurar as frases nos arquivos e "
                   "trocar só o que cabe no mesmo espaço (sem risco de quebrar o jogo), com as IAs locais. Traduzir?")
        out.append({"op": j["op"], "titulo": j.get("title", j["op"]), "tipo": tipo, "texto": txt})
    return out


def traducao(p: Ponte, a: dict) -> dict:
    from .traducao import comandos, ia, run
    cfg = ia.load_cfg(p.paths)
    lm = p._map()
    plan = run.library_plan(p.paths, p.store)
    tarefas = []
    vistos: set[str] = set()
    # mais nova primeiro pela data de CRIAÇÃO (o arquivo de uma tarefa velha muda quando o bot marca "avisado")
    for j in sorted(run.all_jobs(p.paths), key=lambda x: x.get("created", ""), reverse=True):
        st = j.get("status")
        if st in PERGUNTA:
            continue
        # só a tarefa MAIS NOVA de cada jogo: uma tentativa antiga que falhou não aparece com "Retomar" depois que
        # uma mais nova já terminou (ex.: Final Fantasy concluído + falhas de dias atrás)
        chave = str(j.get('game_id') or j.get('op'))
        if chave in vistos or str(st).startswith("cancelado"):
            continue
        vistos.add(chave)
        if len(tarefas) >= 15:
            break
        vivo = run._alive(j.get("pid"))
        rep = (j.get("report") or "").lower()
        # falha de FORMATO (texto do jogo não encontrado/ilegível): tentar de novo dá o mesmo resultado
        sem_saida = st == "falhou" and any(w in rep for w in (
            "não traduzi para não estragar", "engenharia reversa", "não dá para traduzir", "formato fechado",
            "nenhum arquivo de texto reconhecido", "pouco texto"))
        linha = comandos._status_line(p.paths, j)
        if sem_saida:
            linha += ("\nNão dá para traduzir este jogo sozinho ainda: o texto dele está num formato que o sistema "
                      "não lê. Tentar de novo dá o mesmo resultado; quando o sistema aprender, ele tenta sozinho.")
        tarefas.append({"op": j["op"], "titulo": j.get("title", j["op"]), "status": st,
                        "linha": linha,
                        "pode_parar": st in comandos.ATIVOS,
                        "pode_retomar": not sem_saida and (st in ("interrompida", "falhou") or (
                            st in comandos.ATIVOS and j.get("pid") and not vivo))})
    return {"automatica": bool(cfg.get("auto_traduzir", True)),
            "nao_traduzidos": [{"gid": g, "titulo": lm.get(g, {}).get("title", g), "console": lm.get(g, {}).get("console", "")}
                               for g in plan["ok"]],
            "tarefas": tarefas, "perguntas": _perguntas(p)}


def _toml_bool(path: Path, chave: str, valor: bool) -> None:
    """Grava `chave = true/false` no topo do .toml (antes da primeira [seção]) sem mexer no resto."""
    txt = path.read_text("utf-8")
    linhas = txt.splitlines()
    fim = next((i for i, ln in enumerate(linhas) if ln.lstrip().startswith("[")), len(linhas))
    nova = f"{chave} = {'true' if valor else 'false'}"
    for i in range(fim):
        if re.match(rf"\s*{re.escape(chave)}\s*=", linhas[i]):
            linhas[i] = nova
            break
    else:
        while fim > 0 and not linhas[fim - 1].strip():
            fim -= 1
        linhas.insert(fim, nova)
    novo = "\n".join(linhas) + "\n"
    tomllib.loads(novo)  # não grava nada inválido
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(novo, "utf-8")
    os.replace(tmp, path)


def traducao_automatica(p: Ponte, a: dict) -> dict:
    from .traducao import ia
    _toml_bool(ia.write_default_cfg(p.paths), "auto_traduzir", bool(a.get("ligar")))
    return {"texto": "Tradução automática ligada: jogo novo que não estiver em português entra na fila sozinho."
            if a.get("ligar") else "Tradução automática desligada: só traduz quando você pedir."}


def _trad(p: Ponte, args: list[str]) -> dict:
    from .traducao import comandos
    return {"texto": _sem_comandos(comandos.traduzir(p, args))}


def traduzir(p: Ponte, a: dict) -> dict:
    if not a.get("gid"):
        raise Erro("Escolha um jogo.")
    return _trad(p, [a["gid"]])


def traducao_parar(p: Ponte, a: dict) -> dict:
    return _trad(p, ["parar", a.get("op", "")])


def traducao_retomar(p: Ponte, a: dict) -> dict:
    return _trad(p, ["retomar", a.get("op", "")])


def traducao_responder(p: Ponte, a: dict) -> dict:
    from .traducao import run
    job = run.load_job(p.paths, a.get("op", ""))
    tipo = PERGUNTA.get((job or {}).get("status"))
    if not tipo:
        return {"texto": "Essa pergunta já foi respondida."}
    return _trad(p, [tipo, job["op"], "sim" if a.get("sim") else "nao"])


# ----------------------------------------------------------------------------------------------- PC
def _jogos_pc(p: Ponte) -> list[str]:
    from . import pc_remoto
    return sorted(e["title"] for e in p._map().values()
                  if e.get("console") == pc_remoto.CONSOLE and not e.get("removed"))


def pc(p: Ponte, a: dict) -> dict:
    from . import pc_remoto
    cfg = pc_remoto.carregar_config(p.paths)
    return {"host_casa": cfg.get("host_casa", ""), "rede_casa": cfg.get("rede_casa", ""), "mac": cfg.get("mac", ""),
            "host_tailscale": cfg.get("host_tailscale", ""), "porteiro": (cfg.get("porteiro") or [""])[0],
            "codigo_definido": bool(cfg.get("codigo")), "jogos": _jogos_pc(p),
            "guia_qr": _qr("https://github.com/guilherme-lacerda-tech/deck-commander/blob/main/docs/FIRE-STICK.md")}


def pc_salvar(p: Ponte, a: dict) -> dict:
    import ipaddress

    from . import pc_remoto
    cfg = pc_remoto.carregar_config(p.paths)
    for k, nome in (("host_casa", "IP do PC em casa"), ("host_tailscale", "IP da Tailscale")):
        if k in a:
            v = (a[k] or "").strip()
            if v:
                try:
                    ipaddress.ip_address(v)
                except ValueError:
                    raise Erro(f"{nome} inválido: use números como 192.168.0.10")
            cfg[k] = v
    if "rede_casa" in a:
        v = (a["rede_casa"] or "").strip()
        if v and not re.fullmatch(r"\d{1,3}(\.\d{1,3}){0,3}\.?", v):
            raise Erro("Rede de casa inválida: use o começo do IP, como 192.168.0.")
        cfg["rede_casa"] = v + ("." if v and not v.endswith(".") and v.count(".") < 3 else "")
    if "mac" in a:
        v = (a["mac"] or "").strip()
        if v:
            try:
                pc_remoto.magic_packet(v)
            except ValueError:
                raise Erro("MAC inválido: são 12 letras/números, como AA:BB:CC:DD:EE:FF")
        cfg["mac"] = v.upper()
    if "porteiro" in a:
        v = (a["porteiro"] or "").strip()
        if v and not re.match(r"https?://", v):
            raise Erro("Endereço do porteiro inválido: começa com http://")
        cfg["porteiro"] = [v] if v else []
    if a.get("codigo"):
        cfg["codigo"] = a["codigo"].strip()
    if a.get("apagar_codigo"):
        cfg["codigo"] = ""
    pc_remoto.salvar_config(p.paths, cfg)
    return {"texto": "Configuração do PC salva."}


def pc_testar(p: Ponte, a: dict) -> dict:
    from . import pc_remoto
    cfg = pc_remoto.carregar_config(p.paths)
    if not (cfg.get("host_casa") or cfg.get("host_tailscale")):
        raise Erro("Preencha antes o IP do PC (em casa ou da Tailscale) e salve.")
    host = pc_remoto.online(cfg)
    casa = pc_remoto.em_casa(cfg)
    return {"acordado": bool(host), "host": host or "", "em_casa": casa,
            "texto": (f"PC acordado e pronto ({host})." if host else "PC dormindo ou fora de alcance.")
            + (" O Deck está na rede de casa." if casa else " O Deck está fora de casa (precisa da Tailscale ligada).")}


def pc_acordar(p: Ponte, a: dict) -> dict:
    from . import pc_remoto
    ok, como = pc_remoto.acordar(pc_remoto.carregar_config(p.paths))
    if not ok:
        raise Erro(como)
    return {"texto": f"{como}. O PC leva de 20 a 40 segundos; depois toque em \"Testar conexão\"."}


def pc_tv(p: Ponte, a: dict) -> dict:
    from . import pc_remoto
    ok, como = pc_remoto.na_tv(pc_remoto.carregar_config(p.paths))
    if not ok:
        raise Erro(como)
    return {"texto": f"{como}. Jogue com um controle ligado no PC."}


def pc_sincronizar(p: Ponte, a: dict) -> dict:
    from . import pc_remoto
    try:
        r = pc_remoto.sincronizar(p.paths)
    except RuntimeError as e:
        raise Erro(str(e).replace("/pc acordar", "\"Acordar PC\""))
    return {"texto": pc_remoto._resumo(r).replace("/pc sincronizar", "\"Sincronizar\""), "jogos": _jogos_pc(p)}


# ----------------------------------------------------------------------------------------------- transferências
def transferir(p: Ponte, a: dict) -> dict:
    from . import transferir as tr
    jogos = [{"gid": g, "titulo": e.get("title", g), "console": e.get("console", "")}
             for g, e in tr.carregar_mapa().items() if e.get("console") != "pc"]
    jogos.sort(key=lambda j: j["titulo"].casefold())
    from . import receber
    fila = [{"titulo": e["titulo"], "status": e["status"], "nota": (e.get("nota") or "")[-200:],
             "direcao": e.get("direcao", "deck->pc")} for e in reversed(tr.ler_fila()[-10:])]
    lista_pc = receber.ler_jogos_pc()
    jogos_pc = [{"gid": j["id"], "titulo": j.get("titulo", j["id"]), "console": j.get("console", ""),
                 "tamanho": receber.gb(j.get("tamanho", 0))} for j in (lista_pc.get("jogos") or []) if j.get("id")]
    jogos_pc.sort(key=lambda j: j["titulo"].casefold())
    return {"jogos": jogos, "fila": fila, "jogos_pc": jogos_pc, "lista_pc_em": lista_pc.get("em", "")}


def transferir_preparar(p: Ponte, a: dict) -> dict:
    from . import transferir as tr
    try:
        man = tr.preparar(a.get("gid", ""), com_hash=False)
    except (KeyError, OSError) as e:
        raise Erro(f"Não deu para preparar: {str(e).strip(chr(39))}")
    return {"titulo": man["titulo"], "tamanho": tr.gb(man["total_bytes"]), "arquivos": len(man["arquivos"]),
            "resumo": tr.texto_resumo(man) + tr._linha_emulador_pc(man)}


def transferir_enviar(p: Ponte, a: dict) -> dict:
    from . import transferir as tr
    if not a.get("gid"):
        raise Erro("Escolha um jogo.")
    return {"texto": _sem_comandos(tr.comando_transferir(p, [a["gid"], "enviar"]))}


def trazer_preparar(p: Ponte, a: dict) -> dict:
    """Do PC para o Deck: o que vem (tamanho, o que vai junto, emulador que será instalado no Deck)."""
    from . import receber
    j = next((x for x in receber.ler_jogos_pc().get("jogos") or [] if x.get("id") == a.get("gid")), None)
    if not j:
        raise Erro("Esse jogo não está na lista do PC (a lista chega quando o PC liga).")
    return {"titulo": j.get("titulo", j["id"]), "tamanho": receber.gb(j.get("tamanho", 0)),
            "arquivos": j.get("arquivos", 0), "resumo": receber.texto_jogo_pc(j)}


def trazer_enviar(p: Ponte, a: dict) -> dict:
    from . import receber
    if not a.get("gid"):
        raise Erro("Escolha um jogo do PC.")
    return {"texto": _sem_comandos(receber.comando_trazer(p, [a["gid"], "enviar"]))}


# ----------------------------------------------------------------------------------------------- qualidade
def qualidade(p: Ponte, a: dict) -> dict:
    from . import controls, quality
    jogos = []
    for g, e in sorted(p._map().items(), key=lambda kv: kv[1].get("title", "").casefold()):
        c = e.get("console", "")
        if e.get("removed") or not quality.supported(c):
            continue
        atual = quality.get_override(p.paths, g)
        jogos.append({"gid": g, "titulo": e.get("title", g), "console": c,
                      "atual": quality.LABEL.get(atual, "padrão") if atual else "padrão",
                      "niveis": ["padrão"] + [quality.LABEL[n] for n in range(1, quality.MAX.get(c, 4) + 1)]})
    try:
        ctl = [{"emulador": x.emulator, "ok": x.ok, "detalhe": x.detail} for x in controls.check()]
    except Exception:  # noqa: BLE001 — aviso é conforto
        ctl = []
    try:
        lay = controls.layouts()
    except Exception:  # noqa: BLE001
        lay = []
    from . import perfil
    return {"jogos": jogos, "controles": ctl, "layouts": lay, "perfil": perfil.atual(p.paths), "perfis": perfil.PERFIS}


def perfil_definir(p: Ponte, a: dict) -> dict:
    """Beleza / Desempenho / Retrô / Automático para todos os jogos (vale ao abrir o jogo)."""
    from . import perfil
    try:
        nome = perfil.definir(p.paths, a.get("perfil", ""))
    except ValueError:
        raise Erro("Escolha Beleza, Desempenho, Retrô ou Automático.")
    return {"texto": f"Perfil: {perfil.PERFIS[nome].split(' (')[0]}. Vale na próxima vez que abrir um jogo "
                     "(com o jogo aberto, feche e abra de novo)."}


def melhorias(p: Ponte, a: dict) -> dict:
    from . import melhorias as M
    try:
        noite = bool(json.loads((p.paths.config / "shaders-noite.json").read_text("utf-8")).get("ligado"))
    except (OSError, ValueError):
        noite = False
    return {"emuladores": M.estado(Path.home()), "shaders_noite": noite}


RETRO = {"nes", "snes", "n64", "gb", "gbc", "gba", "genesis", "sms", "gg", "segacd", "saturn", "pce", "arcade", "psx", "ps2", "gc", "wii"}


def _gid_do_atalho(appid: int, home: Path | None = None) -> str | None:
    """Atalho do Steam (appid) → id do jogo no Deck Commander (fica nas opções de abertura do atalho)."""
    import glob

    from . import vdf
    h = home or Path.home()
    for sc in glob.glob(str(h / ".local/share/Steam/userdata/*/config/shortcuts.vdf")):
        try:
            for s in vdf.read_shortcuts(Path(sc)):
                if int(s.get("appid", 0)) & 0xFFFFFFFF == appid & 0xFFFFFFFF:
                    return s.get("LaunchOptions") or None
        except (OSError, ValueError, KeyError):
            continue
    return None


def contexto(p: Ponte, a: dict) -> dict:
    """O que está aberto agora, para o painel mostrar só as telas úteis (pedido 4 da 0.8)."""
    try:
        appid = int(a.get("appid") or 0)
    except (TypeError, ValueError):
        appid = 0
    if not appid:
        return {"modo": "nenhum"}
    gid = _gid_do_atalho(appid)
    if not gid:
        return {"modo": "steam"}  # jogo da própria Steam
    if gid.startswith("app-"):
        return {"modo": "app", "gid": gid}
    from . import transferir as tr
    e = tr.carregar_mapa().get(gid) or {}
    con = e.get("console", "")
    modo = ("pc" if con == "pc" or gid.startswith("pc-") else "switch" if con in ("switch", "switch2")
            else "retro" if con in RETRO else "emulador")
    return {"modo": modo, "gid": gid, "titulo": e.get("title", gid), "console": con}


def detonado(p: Ponte, a: dict) -> dict:
    """Lista de jogos (o aberto primeiro) e, com `gid`, o índice do detonado (busca na StrategyWiki na 1ª vez)."""
    from . import continuar
    from . import detonado as D
    mapa = p._map()
    aberto = (continuar.jogo_aberto(p.paths) or {}).get("game_id")
    jogos = [{"gid": g, "titulo": e.get("title", g)} for g, e in sorted(mapa.items(), key=lambda kv: (
        kv[0] != aberto, kv[1].get("title", "").casefold())) if not e.get("removed") and e.get("console") not in ("pc", "steam")]
    gid = a.get("gid") or aberto
    if not gid:
        return {"jogos": jogos, "gid": None}
    d = D.info(p.paths, gid)
    if not d or a.get("nome"):
        try:
            d = D.preparar(p.paths, gid, mapa.get(gid, {}).get("title", gid), jogo=a.get("nome") or None)
        except OSError as e:
            raise Erro(f"Sem internet para achar o detonado agora ({e.__class__.__name__}).")
    if d.get("erro"):
        return {"jogos": jogos, "gid": gid, "erro": d["erro"] + " Se souber o nome do jogo lá, digite abaixo."}
    return {"jogos": jogos, "gid": gid, "jogo": d["jogo"], "fonte": d["fonte"], "atual": d.get("atual", 0),
            "capitulos": [{"n": i, "label": (c["grupo"] + " · " if c["grupo"] != "Detonado" else "") + c["titulo"]}
                          for i, c in enumerate(d["capitulos"])]}


def detonado_capitulo(p: Ponte, a: dict) -> dict:
    """Mostra a parte `n` (lembra onde você está). Sem tradução ainda: mostra o original e traduz em segundo plano."""
    import subprocess
    from . import detonado as D
    gid, n = a.get("gid"), int(a.get("n") or 0)
    D.marcar(p.paths, gid, n)
    try:
        c = D.capitulo(p.paths, gid, n, traduzir=False)
    except OSError as e:
        raise Erro(f"Sem internet para baixar esta parte agora ({e.__class__.__name__}).")
    if c.get("erro"):
        raise Erro(c["erro"])
    if not c["traduzido"]:
        unit = "dc-detonado-" + "".join(ch for ch in gid if ch.isalnum())[:40]
        subprocess.run(["systemd-run", "--user", "--collect", f"--unit={unit}",
                        f"--working-directory={Path(__file__).resolve().parents[1]}",
                        "python3", "-m", "dc.detonado", "baixar", gid], capture_output=True)
    return c


def retro(p: Ponte, a: dict) -> dict:
    from . import continuar
    from . import retro as RT
    j = continuar.jogo_aberto(p.paths) or {}
    emu = continuar.qual(j.get("cmd") or [])
    return RT.estado() | {"continuar": continuar.ligado(p.paths), "rebobina": continuar.REBOBINA.get(emu, 0)}


def continuar_definir(p: Ponte, a: dict) -> dict:
    from . import continuar
    continuar.definir(p.paths, bool(a.get("ligar")))
    return {"texto": "Continuar de onde parou: " + ("ligado. Os jogos abrem no ponto salvo." if a.get("ligar")
                     else "desligado. Os jogos abrem do começo (os pontos ficam guardados).")}


def voltar_tempo(p: Ponte, a: dict) -> dict:
    from . import continuar
    return {"texto": continuar.voltar_no_tempo(p.paths, int(a.get("segundos") or 5))}


def retro_jogos(p: Ponte, a: dict) -> dict:
    from . import retro as RT
    return RT.jogos_para_o_painel()


def retro_definir(p: Ponte, a: dict) -> dict:
    """Ligar os botões de trás (e turbo 2x/4x), filtros de tela, ou desfazer tudo."""
    from . import retro as RT
    if a.get("desfazer"):
        return {"texto": RT.desfazer()}
    if a.get("filtros") is not None:
        from . import retro_hacks as RH
        cfg = Path.home() / RT.ARQUIVOS["RetroArch"]
        if cfg.exists():
            cfg.write_text(RH.definir(cfg.read_text("utf-8", "replace"),
                                      {"video_shader_enable": "true" if a["filtros"] else "false"}), "utf-8")
        # jogo aberto: sem a porta de comandos pela rede (fechada por segurança), a troca vale ao reabrir o jogo
        return {"texto": "Filtros de tela " + ("ligados" if a["filtros"] else "desligados") + "."
                + (" Feche e abra o jogo para ver a troca." if a.get("agora") else "")}
    turbo = float(a.get("turbo") or 2.0)
    if turbo not in (2.0, 3.0, 4.0):
        raise Erro("Turbo: 2x, 3x ou 4x.")
    return RT.preparar(turbo=turbo)  # {texto, appids, modelo}: o painel escolhe o modelo em cada jogo no Steam


def melhorias_definir(p: Ponte, a: dict) -> dict:
    from . import melhorias as M
    if a.get("shaders_noite") is not None:
        (p.paths.config / "shaders-noite.json").write_text(json.dumps({"ligado": bool(a["shaders_noite"])}), "utf-8")
        return {"texto": "Shaders à noite " + ("ligado: de madrugada, na tomada e sem jogo aberto, o Deck abre cada "
                         "jogo novo por ~1 min para gerar o cache." if a["shaders_noite"] else "desligado.")}
    try:
        return {"texto": M.definir(Path.home(), a.get("emulador", ""), a.get("opcao", ""), bool(a.get("ligar")))}
    except ValueError as e:
        raise Erro(str(e))


def qualidade_definir(p: Ponte, a: dict) -> dict:
    if not a.get("gid") or not a.get("nivel"):
        raise Erro("Escolha o jogo e o nível.")
    return {"texto": p._quality([a["gid"], a["nivel"]])}


def controle_definir(p: Ponte, a: dict) -> dict:
    """Layout dos botões de um emulador: 'xbox' (A embaixo) ou 'switch' (A na direita)."""
    from . import controls
    if a.get("modo") not in controls.MODOS:
        raise Erro("Escolha Controle de Xbox ou Controle de Switch.")
    try:
        feito = controls.definir_layout(a.get("id", ""), a["modo"])
    except ValueError as e:
        raise Erro(f"Não deu para trocar: {e}.")
    nome = controls.MODOS[a["modo"]].split(" (")[0]
    return {"texto": f"Pronto: {nome}. Vale na próxima vez que abrir o jogo." if feito else f"Já estava como {nome}."}


ACOES = {f.__name__: f for f in (
    status, diagnostico, safe_mode, telegram, telegram_botfather, telegram_token, telegram_parear, downloads,
    bateria, duplicados, remover, traducao, traducao_automatica, traduzir, traducao_parar, traducao_retomar,
    traducao_responder, pc, pc_salvar, pc_testar, pc_acordar, pc_sincronizar, transferir, transferir_preparar,
    transferir_enviar, trazer_preparar, trazer_enviar, qualidade, qualidade_definir, controle_definir,
    downloads_limpar, traducao_limpar, desinstalar_lista, devolver, removido_perguntado, musica, musica_volume,
    musica_midia, musica_playlist, musica_salvar, musica_conectar, pc_tv, espaco_sugestoes, familia, familia_salvar,
    familia_atualizar, familia_puxar, melhorias, melhorias_definir, contexto, retro, retro_definir, retro_jogos, perfil_definir, continuar_definir, voltar_tempo, detonado, detonado_capitulo)}
ACOES["downloads_pausar"] = lambda p, a: _pausar(p, a, True)
ACOES["downloads_retomar"] = lambda p, a: _pausar(p, a, False)


def _log(paths: Paths, msg: str) -> None:
    try:
        paths.logs.mkdir(parents=True, exist_ok=True)
        with open(paths.logs / "painel.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.now(timezone.utc).isoformat()} {_limpo(msg)}\n")
    except OSError:
        pass


def executar(acao: str, args: dict | None = None, paths: Paths | None = None, ponte: Ponte | None = None) -> dict:
    fn = ACOES.get(acao)
    if fn is None:
        return {"ok": False, "erro": f"Ação desconhecida: {acao}"}
    paths = paths or (ponte.paths if ponte else get_paths().ensure())
    try:
        out = fn(ponte or Ponte(paths), args or {})
        _log(paths, f"{acao}: ok")
        return {"ok": True, **out}
    except Erro as e:
        _log(paths, f"{acao}: {e}")
        return {"ok": False, "erro": _limpo(e)}
    except Exception as e:  # noqa: BLE001 — nada de stack trace na tela
        _log(paths, f"{acao}: ERRO {type(e).__name__}: {e}")
        return {"ok": False, "erro": f"Não deu certo agora ({type(e).__name__}). Nada foi apagado; tente de novo. "
                                     "Se repetir, veja o Diagnóstico."}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not argv:
        print("uso: python3 -m dc.painel <acao> [json]  — ações: " + ", ".join(sorted(ACOES)), file=sys.stderr)
        return 2
    raw = argv[1] if len(argv) > 1 else ("" if sys.stdin is None or sys.stdin.isatty() else sys.stdin.read())
    try:
        args = json.loads(raw) if raw.strip() else {}
    except ValueError:
        args = None
    res = executar(argv[0], args) if isinstance(args, dict) else {"ok": False, "erro": "parâmetros inválidos"}
    sys.stdout.write(json.dumps(res, ensure_ascii=False) + "\n")
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
