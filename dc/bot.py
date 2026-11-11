"""M4 — Bot do Telegram (long-polling com urllib; sem dependências).

Segurança (M4.3): token em secrets/telegram (600), whitelist de user_id obrigatória — o primeiro
acesso exige o código de pareamento gerado no Deck (`dc telegram pair`), rate limit por usuário,
log em bot.log sem o token. Aprovação (M12.2) por /aprovar <id> com validade de 1h.
"""
from __future__ import annotations

import json
import re
import secrets as pysecrets
import time
import urllib.parse
import urllib.request
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

from . import health, ops, quarantine, syncer
from .paths import Paths, get_paths
from .qbt import Qbt, QbtError
from .store import ApprovalError, Store

RATE = (20, 60)  # 20 comandos por 60 s
STALLED_AFTER = 30 * 60  # sem fontes por 30 min => avisa (uma vez)
PENDING_TTL = 600  # "Switch 1" vale para o próximo arquivo nos próximos 10 min

# Texto livre -> console. "switch 2" é reconhecido para responder que não é suportado.
ALIASES = [
    (r"3ds|n3ds|nintendo\s*3ds|new\s*3ds", "n3ds"),
    (r"wii\s*u|wiiu", "wiiu"),
    (r"ps\s*3|playstation\s*3|play\s*3", "ps3"),
    (r"xbox\s*360|x\s*360|\b360\b", "x360"),
    (r"xbox(?!\s*(?:one|series|s\b|x\b))(\s*cl[aá]ssico|\s*original)?", "xbox"),
    (r"dreamcast|\bdc\b", "dc"),
    (r"sega\s*cd|mega\s*cd|segacd", "segacd"),
    (r"saturn|sega\s*saturn", "saturn"),
    (r"master\s*system|\bsms\b", "sms"),
    (r"game\s*gear|\bgg\b", "gg"),
    (r"mega\s*drive|megadrive|genesis|\bmd\b", "genesis"),
    (r"pc\s*engine|turbo\s*grafx|\bpce\b", "pce"),
    (r"arcade|fbneo|neo\s*geo|mame|cps\s*[123]", "arcade"),
    (r"switch\s*2|nsw\s*2|sw2", "switch2"),
    (r"switch(\s*1)?|nsw|nintendo switch", "switch"),
    (r"ps\s*2|playstation\s*2|play\s*2", "ps2"),
    (r"ps\s*1|psx|ps\s*one|playstation(?!\s*[2-9])(\s*1)?|play\s*1", "psx"),
    (r"psp", "psp"), (r"game\s*cube|gamecube|ngc|\bgc\b", "gc"), (r"wii", "wii"),
    (r"n64|nintendo\s*64", "n64"), (r"snes|super\s*nintendo|super\s*nes", "snes"),
    (r"gba|game\s*boy\s*advance", "gba"),
    (r"nds|nintendo\s*ds|ds|dsi", "nds"),
    (r"game\s*boy\s*colou?r|gbc", "gbc"),
    (r"game\s*boy|\bgb\b", "gb"),
    (r"\bnes\b|nintendinho|famicom|nintendo\s*8", "nes"),
]


def parse_console(text: str):
    import re
    t = (text or "").strip().lower()
    for rx, c in ALIASES:
        if re.fullmatch(rf"\s*(?:{rx})\s*", t) or re.search(rf"(?:^|\W)(?:{rx})(?:$|\W)", t):
            return c
    return None
MAGNET_RX = re.compile(r"magnet:\?\S+", re.I)


def valid_magnet(m: str) -> bool:
    """Magnet de verdade: tem o código do torrent (xt=urn:btih:… ou btmh). O qBittorrent confere o resto."""
    return bool(re.search(r"(?i)xt=urn:bt(?:ih|mh):[0-9a-z]+", m or ""))


def looks_like_torrent(data: bytes) -> bool:
    """Arquivo .torrent é um dicionário bencode (começa com 'd' e 'N:chave'); página HTML/zip renomeado não é."""
    return bool(data) and data[:1] == b"d" and b":" in data[:64]


BAD_MAGNET = ("Esse magnet está incompleto ou inválido (falta o código do torrent, \"xt=urn:btih:…\"). "
              "Copie o link inteiro de novo ou encaminhe o arquivo .torrent.")
UNKNOWN_CONSOLE = ("Uso: Switch, 3DS, DS, Wii U, Wii, GameCube, N64, SNES, NES, GBA, Game Boy, PS1, PS2, PS3, PSP, "
                   "Xbox, Xbox 360, Dreamcast, Saturn, Mega Drive, Master System, Game Gear, Sega CD, PC Engine, Arcade")
# comando citado numa mensagem (só palavras simples: ids de jogo, códigos de tarefa, opções)
COMMAND_IN_TEXT = re.compile(
    r"(/(?:traduzir|converter|sync|devolver|remover|qualidade|controles|status|disk|calibrar)"
    r"(?: (?!<)[A-Za-z0-9_\-]+)*?)(?=[ 	]*(?:$|[—(.,:;→]| - ))", re.M)
HELP = """Deck Commander — comandos
Mais fácil: mande o nome do console (ex.: Switch 1, PS2) e depois encaminhe o .torrent ou cole o magnet.
Aviso aqui quando o download terminar.

/add [console] <magnet> — baixa (console: ps2 psx gc wii snes n64 gba psp nds switch)
/sync — leva downloads concluídos para a biblioteca  (/sync tudo confirma pacotes grandes)
/console <id> <console> — responde quando o /sync perguntar
/reiniciar — reinicia o Steam para mostrar jogos novos
/duplicados — jogos repetidos · /remover <nº ou nome> — tira um jogo (pede confirmação)
/qualidade <jogo> nativo|2x|3x|padrão — resolução só daquele jogo · /qualidade lista
/controles — situação dos controles em cada emulador
/baixar — baixa mesmo assim um download que parecia repetido
/devolver <nome> — traz de volta um jogo que você tirou pelo Steam
/bateria sim|nao — baixar também fora da tomada (padrão: só na tomada)
/pc listar | sincronizar | acordar | status — jogos do PC no Deck (aba "Computador")
/musica [playlist | pausar | proxima | anterior | conectar] — Spotify no Deck (conectar: toca sem abrir o app) · cole o link de uma playlist para guardar
/familia — Deck do irmão: status, jogos, puxar <jogo> (magnet + tradução pronta), par, chave, autorizar
/corrigir — mande a foto de uma frase traduzida estranha com /corrigir <jogo> na legenda
/saves <jogo> [deck|pc] — deixa os saves iguais no Deck e no PC (o mais novo vale; conflito você escolhe) · /saves auto sim|nao
/transferir <jogo> — leva o jogo com tudo (emulador, config, saves) para o PC
/trazer — jogos do PC · /trazer <jogo> — traz do PC para o Deck (instala o emulador se faltar)
/traduzir <jogo> — tradução pt-BR com IA (Switch e Pokémon GBA) · /traduzir lista | status | config
/traduzir biblioteca — traduz todos os jogos que ainda não estão em português (pergunta antes)
/converter <jogo> [organizar|descompactar] — Switch: update/DLC e NSZ
/status · /queue · /disk · /diagnostico
/voltar — desfaz a última atualização do Deck Commander (se algo parou de funcionar)
/pause · /resume — downloads
/quarantine list | review <id> | clear <id>
/aprovar <id> — aprova operação pendente (vale 1h)
/sos — safe-mode (desliga automações, não apaga nada) · /sos off"""


class Bot:
    def __init__(self, paths: Paths, token: str):
        self.paths, self.token = paths, token
        self.api = f"https://api.telegram.org/bot{token}/"
        self.cfg_path = paths.config / "telegram.json"
        self.cfg = json.loads(self.cfg_path.read_text("utf-8")) if self.cfg_path.exists() else {"allowed": []}
        self.store = Store(paths.db)
        self.qbt = Qbt()
        self.hits: dict[int, deque] = defaultdict(deque)

    # -- infra -----------------------------------------------------------------
    def log(self, msg: str) -> None:
        self.paths.logs.mkdir(parents=True, exist_ok=True)
        with open(self.paths.logs / "bot.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.now(timezone.utc).isoformat()} {msg.replace(self.token, '***')}\n")

    def call(self, method: str, **params):
        data = urllib.parse.urlencode(params).encode()
        with urllib.request.urlopen(self.api + method, data=data, timeout=70) as r:
            return json.loads(r.read())["result"]

    def _button(self, label: str, command: str) -> dict:
        """Botão que, ao tocar, executa `command` como se você tivesse digitado (guardado por um código curto,
        porque o Telegram só aceita 64 bytes no botão)."""
        import hashlib
        key = hashlib.sha1(command.encode()).hexdigest()[:12]
        bt = self.cfg.setdefault("botoes", {})
        bt[key] = command
        while len(bt) > 200:
            bt.pop(next(iter(bt)))
        return {"text": label[:60], "callback_data": "c:" + key}

    def send(self, chat: int, text: str, buttons: list | None = None) -> None:
        """`buttons`: lista de textos (o botão envia o próprio texto, ex.: "Sim") ou (rótulo, comando).
        Todo comando citado na mensagem (ex.: "/traduzir aprovar 1a2b") também vira botão."""
        text = text.replace(self.token, "***")
        btns = [(b, b) if isinstance(b, str) else tuple(b) for b in (buttons or [])]
        btns += self.__dict__.pop("next_buttons", None) or []  # botões pedidos pelo comando que gerou a resposta
        found = [m for m in COMMAND_IN_TEXT.finditer(text)
                 if " " in m.group(1) and not text[m.end():m.end() + 2] == " <"]  # só comando completo
        if len(found) <= 6:  # mensagem de ajuda (cheia de comandos) não vira painel de botões
            for m in found:
                c = m.group(1).strip()
                if c not in [x[1] for x in btns]:
                    btns.append((c, c))
        yn = {lbl.lower(): cmd for lbl, cmd in btns if lbl.lower() in ("sim", "não")}
        if len(yn) == 2:  # pergunta Sim/Não: "sim"/"não" digitado vale como tocar no botão (por 1 hora)
            self.cfg["sim_nao"] = {"chat": chat, "sim": yn["sim"], "nao": yn["não"], "at": time.time()}
        chunks = [text[i:i + 3900] for i in range(0, len(text), 3900)] or [""]
        for n, chunk in enumerate(chunks):
            extra = {}
            if btns and n == len(chunks) - 1:
                rows = [[self._button(lbl, cmd)] for lbl, cmd in btns] if len(btns) > 2 or any(
                    len(lbl) > 12 for lbl, _ in btns) else [[self._button(lbl, cmd) for lbl, cmd in btns]]
                extra["reply_markup"] = json.dumps({"inline_keyboard": rows})
                self.save_cfg()
            self.call("sendMessage", chat_id=chat, text=chunk, **extra)

    def handle_callback(self, cq: dict) -> None:
        """Toque num botão: roda o comando guardado como se a pessoa tivesse digitado."""
        try:
            self.call("answerCallbackQuery", callback_query_id=cq["id"])
        except Exception:  # noqa: BLE001
            pass
        data = cq.get("data") or ""
        command = self.cfg.get("botoes", {}).get(data[2:]) if data.startswith("c:") else None
        chat = (cq.get("message") or {}).get("chat", {}).get("id")
        if chat is None:
            return
        if not command:  # botão de uma mensagem antiga (o código já saiu da memória do bot)
            self.send(chat, "Esse botão é de uma mensagem antiga e não vale mais. Mande o comando de novo "
                            "(ou /help).")
            return
        uid = cq["from"]["id"]
        self.log(f"{uid}: botão {command}")
        try:
            reply = self.handle(uid, chat, command)
        except Exception as e:  # noqa: BLE001 — o botão nunca fica sem resposta
            self.log(f"erro no botão {command}: {e!r}")
            reply = f"❌ Deu erro ao rodar {command.split()[0]}: {e}. Nada foi apagado; tente de novo ou mande /diagnostico."
        if reply:
            self.send(chat, reply)

    def save_cfg(self) -> None:
        tmp = self.cfg_path.with_name("telegram.json.tmp")
        tmp.write_text(json.dumps(self.cfg, indent=1), "utf-8")
        tmp.replace(self.cfg_path)

    def limited(self, uid: int) -> bool:
        q, now = self.hits[uid], time.monotonic()
        while q and now - q[0] > RATE[1]:
            q.popleft()
        q.append(now)
        return len(q) > RATE[0]

    # -- comandos --------------------------------------------------------------
    def handle(self, uid: int, chat: int, text: str) -> str:
        parts = (text or "").strip().split()
        if not parts:
            return ""
        cmd, args = parts[0].split("@")[0].lower(), parts[1:]
        op = self.cfg.get("pergunta_op")
        if op and uid in self.cfg["allowed"] and text.strip().lower() in ("sim", "s", "não", "nao", "n"):
            from .traducao import run as trad_run
            self.cfg.pop("pergunta_op", None); self.save_cfg()
            yes = text.strip().lower() in ("sim", "s")
            if (trad_run.load_job(self.paths, op) or {}).get("status") == "aguardando ok":  # pergunta de motor
                return trad_run.answer_motor(self.paths, op, yes)
            return trad_run.answer_generic(self.paths, op, yes)
        if uid not in self.cfg["allowed"]:
            code = pairing_code_valid(self.paths)
            if cmd == "/start" and code and args and not pysecrets.compare_digest(args[0].encode(), code.encode()):
                pairing_failed(self.paths)
                self.log(f"código de pareamento errado de {uid}")
            if cmd == "/start" and code and args and pysecrets.compare_digest(args[0].encode(), code.encode()):
                self.cfg["allowed"].append(uid); self.save_cfg()
                (self.paths.state / "telegram-pairing").unlink()
                self.log(f"usuário {uid} pareado")
                return "Pareado ✅\n\n" + HELP
            self.log(f"recusado usuário {uid}: {cmd}")
            if cmd == "/start" and args:
                return ("Acesso negado: código errado ou vencido (vale 30 min). Gere outro no Deck: "
                        "python3 -m dc x telegram-pair — e mande /start <código>.")
            return "Acesso negado. Pareie com /start <código> (o código é gerado no Deck)."
        if self.limited(uid):
            return "Calma 🙂 muitos comandos por minuto."
        self.log(f"{uid}: {cmd} {' '.join(a if not a.startswith('magnet:') else 'magnet:…' for a in args)}")
        P, S = self.paths, self.store
        if cmd in ("/help", "/start"):
            return HELP
        if cmd == "/add":
            if not args:
                return "Uso: /add [console] <magnet>"
            if ops.in_safe_mode(P):
                return "Safe-mode ativo."
            mg = next((a for a in args if a.lower().startswith("magnet:")), None)
            if not mg:
                return BAD_MAGNET if any("magnet" in a.lower() for a in args) else                     "Link inválido: o /add precisa de um magnet (começa com magnet:?xt=…). Uso: /add [console] <magnet>"
            if not valid_magnet(mg):
                return BAD_MAGNET
            rest = " ".join(a for a in args if a is not mg)
            console = parse_console(rest) if rest else None
            if rest and not console:
                return f"Não conheço o console \"{rest[:30]}\". Não baixei.\n{UNKNOWN_CONSOLE}"
            if console == "switch2":
                return "Switch 2 ainda não é suportado no Deck (o Lichii é experimental). Não baixei."
            magnet = mg
            if ops.in_safe_mode(P):
                return "Safe-mode ativo."
            going = self._downloading(magnet)
            if going:
                return f"Esse download já está na fila ({going}). Aviso quando terminar."
            cat = console or "auto"
            from . import dedup
            dup = self._already(dedup.magnet_name(magnet), console)
            if dup:
                self.cfg["held"] = {"magnet": magnet, "cat": cat, "name": dedup.magnet_name(magnet), "at": time.time()}
                self.save_cfg()
                return f"⚠️ Parece repetido: {dup}.\nNão baixei. Se quer mesmo assim (outra versão/idioma), mande /baixar"
            try:
                self.qbt.add(magnet, cat, str(Path(syncer._cfg(P)["downloads_root"]) / cat))
            except QbtError as e:
                return f"❌ {e} (sem internet? o /sync continua funcionando com o que já baixou)"
            where = cat if console else "descubro o console quando terminar; se não der, pergunto"
            return f"Adicionado ({where}). Aviso quando terminar." + self._power_note()
        if cmd == "/sync":
            return syncer.run_sync(P, S, self.qbt, confirm_many=bool(args and args[0] == "tudo"),
                                   explicit=self.cfg.get("explicit"))
        if cmd in ("/console", "/aprovar") and not args:
            return "Uso: /console <id> <console>" if cmd == "/console" else "Uso: /aprovar <id>"
        if cmd == "/console" and len(args) == 2:
            st = syncer._state(P)
            h = next((k for k in st.get("pending", {}) if k.startswith(args[0])), None)
            if not h:
                return "Não achei esse download pendente."
            console = parse_console(args[1])
            if not console:
                return f"Não conheço o console \"{args[1][:30]}\".\n{UNKNOWN_CONSOLE}"
            if st.get("ingested", {}).get(h, {}).get("skipped"):  # tinha sido pulado: deixa o /sync tentar de novo
                st["ingested"].pop(h); syncer._save_state(P, st)
            self.cfg.setdefault("explicit", {})[h] = console; self.save_cfg()
            return f"Ok, {st['pending'][h]} = {console}. Rode /sync."
        if cmd == "/transferir":  # leva um jogo + emulador + config + saves do Deck para o PC
            from .transferir import comando_transferir
            return comando_transferir(self, args)
        if cmd == "/trazer":  # traz um jogo do PC (jogo + dados do emulador) para o Deck
            from .receber import comando_trazer
            return comando_trazer(self, args)
        if cmd == "/playlist":  # /playlist <nome> <link do Spotify>
            link = next((x for x in args if "open.spotify.com" in x or x.startswith("spotify:")), "")
            if not link:
                return "Uso: /playlist <nome> <link da playlist> (ou só cole o link do Spotify aqui)"
            return self._guardar_playlist(" ".join(x for x in args if x != link), link)
        if cmd == "/corrigir":
            return ("Mande uma FOTO (ou print) da frase estranha com a legenda /corrigir <nome do jogo>. "
                    "Pode dizer o que está errado depois de uma barra: /corrigir Zelda | o certo é Reino Cogumelo")
        if cmd == "/voltar":  # desfaz a última atualização (troca pela versão anterior guardada)
            from . import versao
            txt, self.next_buttons = versao.comando(args)
            return txt
        if cmd == "/saves":  # sincronizar saves Deck <-> PC de um jogo (o PC busca o pedido em até 5 min)
            return self._saves(args)
        if cmd == "/familia":  # dois Decks pareados: catálogo (magnet + tradução pronta) do par
            from . import familia_servico
            return familia_servico.comando(self, args)
        if cmd == "/musica":  # Spotify no Deck: tocar playlist, pausar, próxima, o que está tocando
            return self._musica(args)
        if cmd == "/pc":  # jogos do PC transmitidos para o Deck (aba "Computador")
            from . import pc_remoto
            return pc_remoto.comando_pc(self, args)
        if cmd == "/bateria":
            return self._battery(args)
        if cmd == "/baixar":
            return self._release_held()
        if cmd == "/duplicados":
            return self._duplicates()
        if cmd == "/devolver":
            return self._bring_back(args)
        if cmd in ("/traduzir", "/converter"):
            from .traducao import comandos as trad
            return (trad.traduzir if cmd == "/traduzir" else trad.converter)(self, args)
        if cmd == "/remover":
            return self._remove(args)
        if cmd == "/qualidade":
            return self._quality(args)
        if cmd == "/controles":
            from . import controls
            return "\n".join(("✅ " if c.ok else "⚠️ ") + f"{c.emulator}: {c.detail}" for c in controls.check()) + \
                "\n(o mapeamento vale para todos os jogos do emulador; ajuste por jogo: Steam → Controle no atalho)"
        if cmd == "/reiniciar":
            if ops.game_running():
                return "Tem jogo aberto — feche antes."
            try:
                return ops.restart_steam()
            except RuntimeError as e:
                return f"❌ {e}"
        if cmd == "/status":
            return health.status_text(P, S, self.qbt)
        if cmd == "/queue":
            try:
                ts = self.qbt.torrents()
            except QbtError as e:
                return str(e)
            return "\n".join(f"{t['name'][:40]} — {t['progress'] * 100:.0f}% {t['state']}" for t in ts) or "Fila vazia."
        if cmd in ("/pause", "/resume"):
            try:
                hs = [t["hash"] for t in self.qbt.torrents()]
                (self.qbt.pause if cmd == "/pause" else self.qbt.resume)(hs)
            except QbtError as e:
                return str(e)
            return f"{len(hs)} download(s) {'pausado(s)' if cmd == '/pause' else 'retomado(s)'}. (o /sync não é afetado)"
        if cmd == "/disk":
            from . import vdf
            try:
                sc = vdf.read_shortcuts(syncer.shortcuts_path())
            except (OSError, ValueError):  # Steam ainda sem login: lista sem "última vez jogado"
                sc = []
            items = health.disk_report(syncer.rom_roots(), sc)
            return "\n".join(f"{i['size'] / 1e9:5.1f} GB  {Path(i['path']).name[:40]}  (última vez: {i['last_played']})"
                             + ("  ← candidato" if i["suggest_remove"] else "") for i in items) + \
                "\n(sugestão apenas — nada é apagado automaticamente)"
        if cmd == "/diagnostico":
            fs = health.diagnose(P, S, repair=True)
            return "\n".join(f"{'✅' if x.ok else ('🔧' if x.mode == 'auto' else '❓' if x.mode == 'ask' else '⚠️')} "
                             f"{x.problem}: {x.detail}" + (f" → {x.action}" if x.action else "") for x in fs)
        if cmd == "/quarantine":
            sub = args[0] if args else "list"
            if sub == "list":
                es = quarantine.list_entries(P.quarantine)
                return "\n".join(f"{e.id}: {e.reason[:60]}" + (" [REVISÃO VENCIDA]" if e.overdue else "") for e in es) or "Quarentena vazia."
            if sub == "review" and len(args) > 1:
                e = next((e for e in quarantine.list_entries(P.quarantine) if e.id == args[1]), None)
                return f"{e.id}\nmotivo: {e.reason}\norigem: {e.original_path}\nrevisar até: {e.review_by[:10]}" if e else "Não achei."
            if sub == "clear" and len(args) > 1:
                quarantine.clear(P.quarantine, args[1]); return "Removido da quarentena."
            return "Uso: /quarantine list | review <id> | clear <id>"
        if cmd == "/aprovar" and args:
            try:
                S.approve(args[0]); return f"Aprovado {args[0]}."
            except ApprovalError as e:
                return f"Recusado: {e}"
        if cmd == "/sos":
            if args and args[0] == "off":
                return "\n".join(ops.safe_mode_off(P)) or "Safe-mode desligado."
            return "Safe-mode ATIVADO.\n" + "\n".join(ops.safe_mode_on(P, f"/sos por {uid}", S))
        return "Comando desconhecido. /help"

    # -- mensagens sem "/" (console em texto, .torrent, magnet solto) ----------
    def handle_message(self, m: dict) -> str | None:
        uid, chat = m["from"]["id"], m["chat"]["id"]
        text = m.get("text") or ""
        if text.startswith("/"):
            return self.handle(uid, chat, text)
        if uid not in self.cfg["allowed"]:
            return "Acesso negado. Pareie com /start <código> (o código é gerado no Deck)."
        if self.limited(uid):
            return "Calma 🙂 muitos comandos por minuto."
        self.cfg["notify_chat"] = chat
        yes_no = text.strip().lower().strip("!.")
        if yes_no in ("sim", "s", "não", "nao", "n"):
            if self.cfg.get("pergunta_op"):
                return self.handle(uid, chat, yes_no)
            q = self.cfg.get("sim_nao") or {}
            if q.get("chat") == chat and time.time() - q.get("at", 0) < 3600:
                self.cfg.pop("sim_nao"); self.save_cfg()
                return self.handle(uid, chat, q["sim"] if yes_no in ("sim", "s") else q["nao"])
            return "Não tem nenhuma pergunta aberta agora. Se for de uma mensagem antiga, mande o comando de novo (/help)."
        pend = self.cfg.setdefault("pending_console", {})
        doc = m.get("document")
        caption = m.get("caption") or ""
        foto = (m.get("photo") or [None])[-1] or (doc if doc and str(doc.get("mime_type", "")).startswith("image/") else None)
        if foto and caption.strip().lower().startswith("/corrigir"):
            return self._corrigir_foto(foto, caption)
        sp = re.search(r"https?://open\.spotify\.com/(?:intl-[a-z]+/)?(playlist|album|artist|track)/[A-Za-z0-9]+\S*", text)
        if sp:  # link do Spotify colado: vira playlist rápida (nome = o resto da mensagem)
            return self._guardar_playlist(text[:sp.start()] + " " + text[sp.end():], sp.group(0))
        mm = MAGNET_RX.search(text)
        if mm:  # magnet colado, sozinho ou junto do console ("Switch magnet:?…")
            rest = (text[:mm.start()] + " " + text[mm.end():]).strip()
            found = parse_console(rest) if rest else None
            if rest and not found and len(rest) <= 24:
                return f"Não conheço o console \"{rest}\". Não baixei.\n{UNKNOWN_CONSOLE}"
            c = self._console_for(uid, found)
            if c:
                pend.pop(str(uid), None)
            return self.handle(uid, chat, f"/add {c} {mm.group(0)}" if c else f"/add {mm.group(0)}")
        if doc:
            name = doc.get("file_name") or "arquivo"
            if not name.lower().endswith(".torrent"):
                return f"Recebi {name}, mas só sei usar arquivos .torrent."
            if (doc.get("file_size") or 0) > 5 * 1024 * 1024:
                return "Esse .torrent é grande demais (>5 MB) — não parece um .torrent válido."
            console = self._console_for(uid, parse_console(caption) or parse_console(name))
            if console == "switch2":
                return "Switch 2 ainda não é suportado no Deck (o Lichii é experimental). Não baixei."
            if ops.in_safe_mode(self.paths):
                return "Safe-mode ativo."
            try:
                info = self.call("getFile", file_id=doc["file_id"])
                with urllib.request.urlopen(f"https://api.telegram.org/file/bot{self.token}/{info['file_path']}",
                                            timeout=60) as r:
                    data = r.read()
            except Exception as e:  # noqa: BLE001 — rede caiu no meio
                self.log(f"falha ao baixar o .torrent {name}: {type(e).__name__}")
                return f"❌ Não consegui pegar o arquivo {name} do Telegram (internet?). Encaminhe de novo daqui a pouco."
            if not looks_like_torrent(data):
                return f"{name} não é um .torrent válido (parece outro tipo de arquivo renomeado). Não baixei."
            cat = console or "auto"
            from . import dedup
            dup = self._already(dedup.torrent_name(data) or name, console)
            if dup:
                held = self.paths.state / "held.torrent"
                held.write_bytes(data)
                self.cfg["held"] = {"file": str(held), "fname": name, "cat": cat, "name": name, "at": time.time()}
                pend.pop(str(uid), None); self.save_cfg()
                return f"⚠️ Parece repetido: {dup}.\nNão baixei. Se quer mesmo assim (outra versão/idioma), mande /baixar"
            try:
                self.qbt.add_file(data, name, cat, str(Path(syncer._cfg(self.paths)["downloads_root"]) / cat))
            except QbtError as e:
                return f"❌ {e}"
            pend.pop(str(uid), None); self.save_cfg()
            self.log(f"{uid}: torrent {name} ({cat})")
            label = {"switch": "Switch", "ps2": "PS2", "psx": "PS1", "nds": "DS", "psp": "PSP"}.get(cat, cat)
            return (f"⬇️ Baixando {name[:-8]} ({label}). Aviso aqui quando terminar."
                    if console else f"⬇️ Baixando {name[:-8]}. Não sei o console ainda — o /sync vai perguntar.") \
                + self._power_note()
        c = parse_console(text)
        if c == "switch2":
            return "Switch 2 ainda não é suportado no Deck (o Lichii é experimental)."
        if c:
            pend[str(uid)] = {"console": c, "at": time.time()}; self.save_cfg()
            return f"Ok, próximo .torrent ou magnet = {c}. Pode encaminhar."
        import re as _re
        if _re.search(r"(?i)\b(baix[ae]r?|download|instalar?|quero (o|a|jogar))\b", text) and not doc:
            return ("Eu não procuro jogos sozinho 🙂 Mande o link magnet (magnet:?xt=…) ou encaminhe o arquivo "
                    ".torrent — se quiser, mande antes o nome do console (ex.: PS2).")
        if _re.search(r"\w", text) and _re.fullmatch(r"\s*[\w .+-]{1,24}\s*", text) and len(text.split()) <= 3 and not _re.search(
                r"(?i)\b(ok|oi|ol[aá]|valeu|obrigad[oa]|blz|beleza|sim|n[aã]o|bom dia|boa (tarde|noite)|kk+|haha)\b", text):
            return (f"Não conheço o console \"{text.strip()}\". Uso: Switch, 3DS, DS, Wii U, Wii, GameCube, N64, SNES, "
                    "NES, GBA, Game Boy, PS1, PS2, PS3, PSP, Xbox, Dreamcast, Saturn, Mega Drive, Master System, "
                    "Game Gear, Sega CD, PC Engine, Arcade — mande o nome e depois o .torrent ou magnet.")
        return None  # conversa comum: ignora

    def _downloading(self, magnet: str) -> str | None:
        """Nome do torrent se esse magnet já estiver no qBittorrent (mesmo código btih)."""
        import base64
        m = re.search(r"(?i)btih:([0-9a-f]{40}|[a-z2-7]{32})", magnet)
        if not m:
            return None
        h = m.group(1).lower()
        if len(h) == 32:
            h = base64.b32decode(h.upper()).hex()
        try:
            return next((t.get("name") or h[:8] for t in self.qbt.torrents() if (t.get("hash") or "").lower() == h), None)
        except Exception:  # noqa: BLE001 — qBittorrent fora do ar: segue o fluxo normal (o add avisa)
            return None

    # -- energia ------------------------------------------------------------------
    def _power_state(self) -> dict:
        try:
            return json.loads((self.paths.state / "power-state.json").read_text("utf-8"))
        except (OSError, ValueError):
            return {}

    def _power_note(self) -> str:
        st = self._power_state()
        if st.get("state") != "PAUSE":
            return ""
        return (f"\n🔌 Por enquanto o download fica pausado: {st.get('why', 'energia')}. "
                "Ele começa sozinho quando o Deck for para a tomada (ou mande /bateria sim).")

    def _battery(self, args) -> str:
        p = self.paths.config / "power.json"
        try:
            cfg = json.loads(p.read_text("utf-8")) if p.exists() else {}
        except (OSError, ValueError):
            cfg = {}
        if args and args[0].lower() in ("sim", "s", "on", "liga"):
            cfg["allow_on_battery"] = True
        elif args and args[0].lower() in ("nao", "não", "n", "off", "desliga"):
            cfg["allow_on_battery"] = False
        else:
            st = self._power_state()
            bat = f"{st['battery']}%" if st.get("battery") is not None else "?"
            return (f"Bateria: {bat} · downloads: {'pausados' if st.get('state') == 'PAUSE' else 'rodando'}"
                    f" ({st.get('why', '?')})\nFora da tomada: {'baixa' if cfg.get('allow_on_battery') else 'não baixa'}"
                    f" (abaixo de {cfg.get('min_battery_pct', 30)}% sempre pausa). Mude com /bateria sim ou /bateria nao")
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name("power.json.tmp")
        tmp.write_text(json.dumps(cfg, indent=1), "utf-8")
        tmp.replace(p)
        return ("✅ Agora baixa também na bateria (pausa abaixo de "
                f"{cfg.get('min_battery_pct', 30)}%). Vale em até 1 min." if cfg["allow_on_battery"]
                else "✅ Agora só baixa na tomada. Vale em até 1 min.")

    # -- duplicatas / remoção / qualidade ---------------------------------------
    def _map(self) -> dict:
        from . import remove
        try:
            return remove.effective_map(self.paths)
        except (OSError, ValueError):
            return {}

    def _corrigir_foto(self, foto: dict, legenda: str) -> str:
        """Foto/print de uma frase traduzida estranha + /corrigir [jogo] [| orientação]: troca só aquela frase."""
        from .traducao import comandos as trad, corrigir_servico, ia
        try:
            info = self.call("getFile", file_id=foto["file_id"])
            with urllib.request.urlopen(f"https://api.telegram.org/file/bot{self.token}/{info['file_path']}",
                                        timeout=60) as r:
                img = r.read()
        except Exception as e:  # noqa: BLE001
            self.log(f"/corrigir: foto não baixou ({type(e).__name__})")
            return "❌ Não consegui pegar a foto do Telegram. Mande de novo daqui a pouco."
        res = corrigir_servico.corrigir(self.paths, ia.load_cfg(self.paths), img, legenda, self._map())
        if res.get("feito"):
            trad.traduzir(self, [res["gid"], "--forcar"])  # refaz o mod a partir do cache (rápido)
        return res["texto"]

    def _saves(self, args) -> str:
        from . import saves_sync, transferir
        from .remove import find
        if not args:
            pend = saves_sync.conflitos(self.paths)
            return ("Uso: /saves <jogo> — deixa os saves iguais no Deck e no PC (o mais novo vale).\n"
                    + ("Conflitos esperando você: " + ", ".join(pend) + " → /saves <jogo> deck  ou  /saves <jogo> pc"
                       if pend else "Nenhum conflito pendente."))
        if args[0].lower() == "auto":  # /saves auto [sim|nao]: sincronizar sozinho ao fechar o jogo
            flag = self.paths.config / "saves-auto-desligado"
            if args[1:2] and args[1].lower() in ("nao", "não"):
                flag.write_text("1")
            elif args[1:2] and args[1].lower() == "sim":
                flag.unlink(missing_ok=True)
            return ("💾 Saves automáticos: " + ("DESLIGADOS" if flag.exists() else "LIGADOS") + ". Ligados, ao fechar um jogo "
                    "que já foi sincronizado uma vez, os saves vão para a fila e o PC iguala quando estiver ligado "
                    "(só aviso se der conflito). /saves auto sim|nao")
        lado = args[-1].lower() if args[-1].lower() in ("deck", "pc") else None
        q = " ".join(args[:-1] if lado else args)
        lm = self._map()
        hits = find(lm, q)
        if len(hits) != 1:
            return "Não achei um só jogo com esse nome." if not hits else "Achei mais de um: seja mais específico."
        gid = hits[0]
        msg = (saves_sync.escolher(self.paths, gid, lado) + " ") if lado else ""
        transferir.enfileirar(gid, lm[gid].get("title", gid), direcao="saves")
        return f"💾 {msg}Sincronização dos saves de {lm[gid].get('title', gid)} na fila: o PC faz em até 5 min e eu aviso."

    def _guardar_playlist(self, nome: str, link: str) -> str:
        from . import painel
        from .painel import Erro
        p = painel.Ponte(self.paths, self.qbt, self.store)
        nome = " ".join(nome.replace("/playlist", " ").split())
        if not nome:
            nome = f"Playlist {len(painel.musica(p, {})['playlists']) + 1}"
        try:
            painel.musica_salvar(p, {"nome": nome, "uri": link})
        except Erro as e:
            return f"🎵 {e}"
        self.next_buttons = [("▶ Tocar agora", f"/musica {nome}")]
        return f"🎵 Playlist guardada como \"{nome}\". Toque com /musica {nome} ou no painel (Música)."

    def _musica(self, args) -> str:
        """/musica (o que toca) · /musica pausar|tocar|proxima|anterior · /musica <playlist guardada no painel>."""
        from . import painel
        from .painel import Erro
        p = painel.Ponte(self.paths, self.qbt, self.store)
        acoes = {"pausar": "pausar", "pause": "pausar", "tocar": "tocar", "play": "tocar", "proxima": "proxima",
                 "próxima": "proxima", "anterior": "anterior", "voltar": "anterior"}
        try:
            if not args:
                d = painel.musica(p, {})
                t = d["tocando"]
                lst = ", ".join(x["nome"] for x in d["playlists"]) or "nenhuma (guarde no painel do Deck → Música)"
                return ((f"🎵 {t['titulo']} — {t['artista']} ({t['estado']})" if t and t.get("titulo")
                         else "🎵 Nada tocando agora.") + f"\nPlaylists: {lst}\nUso: /musica <playlist> | pausar | proxima")
            q = " ".join(args).strip().lower()
            if q == "conectar":  # Spotify do Deck sem o app: instala o player e manda o link de login
                return "🎵 " + painel.musica_conectar(p, {})["texto"]
            if q in acoes:
                painel.musica_midia(p, {"acao": acoes[q]})
                return "🎵 ok"
            pl = next((x for x in painel.musica(p, {})["playlists"] if x["nome"].lower() == q), None)
            if not pl:
                return "Não achei essa playlist. Guarde-a no painel do Deck (Música) ou mande /musica para ver a lista."
            return "🎵 " + painel.musica_playlist(p, pl)["texto"]
        except Erro as e:
            return f"🎵 {e}"

    def _bring_back(self, args) -> str:
        from . import remove
        gone = remove.removed_games(self.paths)
        if not args:
            if not gone:
                return "Nenhum jogo removido que ainda tenha os arquivos no lugar."
            return "Removidos (arquivos ainda no Deck):\n" + "\n".join(f"• {e['title']}" for e in gone.values()) + \
                "\n\nPara trazer de volta: /devolver <nome>"
        hits = remove.find(gone, " ".join(args), include_removed=True)
        if len(hits) != 1:
            return ("Achei mais de um:\n" + "\n".join(f"• {gone[g]['title']}" for g in hits[:10])) if hits else \
                "Não achei esse jogo entre os removidos (/devolver mostra a lista)."
        title = remove.bring_back(self.paths, hits[0])
        res = syncer.run_sync(self.paths, self.store, self.qbt, explicit=self.cfg.get("explicit"))
        return f"↩️ {title} voltando para a biblioteca.\n{res}"

    def _already(self, name, console):
        if not name:
            return None
        from . import dedup
        try:
            ts = self.qbt.torrents()
        except QbtError:
            ts = []
        return dedup.find_existing(name, console, self._map(), ts)

    def _release_held(self) -> str:
        h = self.cfg.pop("held", None)
        self.save_cfg()
        if not h or time.time() - h.get("at", 0) > 3600:
            return "Nada guardado para baixar (vale por 1 hora depois do aviso)."
        dest = str(Path(syncer._cfg(self.paths)["downloads_root"]) / h["cat"])
        try:
            from .qbt import DUP_OK_TAG
            if h.get("magnet"):
                self.qbt.add(h["magnet"], h["cat"], dest, extra_tags=DUP_OK_TAG)
            else:
                self.qbt.add_file(Path(h["file"]).read_bytes(), h["fname"], h["cat"], dest, extra_tags=DUP_OK_TAG)
                Path(h["file"]).unlink(missing_ok=True)
        except (QbtError, OSError) as e:
            return f"❌ {e}"
        return f"⬇️ Baixando {h.get('name') or 'download'} mesmo assim. Aviso quando terminar." + self._power_note()

    def _duplicates(self) -> str:
        from . import dedup, remove
        lm = self._map()
        entries, lines = [], []
        for grp in dedup.library_dups(lm):
            lines.append("Mesmo jogo:")
            for g in grp:
                entries.append({"gid": g})
                try:
                    size = remove.plan(self.paths, g, syncer.rom_roots()).size
                except (KeyError, OSError):
                    size = 0
                where = "cartão SD" if str(lm[g]["rom"]).startswith("/run/media/") else "memória interna"
                lines.append(f"  {len(entries)}. {lm[g]['title']} — {size / 1e9:.1f} GB · {where}")
        st = syncer._state(self.paths)
        try:
            live = {t["hash"]: t for t in self.qbt.torrents()}
        except QbtError:
            live = {}
        extra = [(h, v) for h, v in st.get("ingested", {}).items()
                 if v.get("duplicate_of") and h in live and not v.get("removed")]
        if extra:
            lines.append("Downloads repetidos que ainda ocupam espaço:")
            for h, v in extra:
                entries.append({"hash": h, "name": v["name"]})
                lines.append(f"  {len(entries)}. {v['name']} — {live[h].get('size', 0) / 1e9:.1f} GB (cópia de «{v['duplicate_of']}»)")
        self.cfg["listing"] = entries
        self.save_cfg()
        if not entries:
            return "Nenhum jogo repetido 👍"
        return "\n".join(lines) + "\n\nPara tirar um: /remover <nº>  (mostra o que vai acontecer e pede confirmação)"

    def _remove(self, args) -> str:
        from . import remove
        if not args:
            return "Uso: /remover <nº do /duplicados ou nome do jogo>"
        confirm = args[-1].lower() in ("confirmar", "sim")
        q = args[:-1] if confirm else args
        lm = self._map()
        listing = self.cfg.get("listing") or []
        if len(q) == 1 and q[0].isdigit() and 0 < int(q[0]) <= len(listing):
            e = listing[int(q[0]) - 1]
            if "hash" in e:
                if not confirm:
                    return f"Apagar o download repetido «{e['name']}» (o jogo original fica)?\nConfirme: /remover {q[0]} confirmar"
                try:
                    self.qbt.delete(e["hash"], delete_files=True)
                except QbtError as ex:
                    return f"❌ {ex}"
                st = syncer._state(self.paths)
                st.get("ingested", {}).get(e["hash"], {})["removed"] = True
                syncer._save_state(self.paths, st)
                return "🗑️ Download repetido removido. A cópia na quarentena some de vez com /quarantine clear <id>."
            hits = [e["gid"]]
        else:
            hits = remove.find(lm, " ".join(q))
        if not hits:
            return "Não achei esse jogo. Veja os números em /duplicados."
        if len(hits) > 1:
            return "Achei mais de um, seja mais específico:\n" + "\n".join(
                f"• {lm[g]['title']} ({lm[g]['console']})" for g in hits[:10])
        if ops.game_running():
            return "Feche o jogo antes de remover."
        try:
            rp = remove.plan(self.paths, hits[0], syncer.rom_roots())
        except KeyError as ex:
            return str(ex)
        if not confirm:
            return rp.describe() + f"\n\nConfirme: /remover {' '.join(q)} confirmar"
        out = remove.apply(self.paths, self.store, rp, self.qbt)
        self.cfg.pop("listing", None)
        self.save_cfg()
        return "🗑️ Removido: " + rp.title + "\n" + "\n".join("• " + x for x in out)

    def _quality(self, args) -> str:
        from . import quality, remove
        lm = self._map()
        if not args or args[0] == "lista":
            ls = quality.listing(self.paths, lm)
            return ("Jogos com qualidade própria:\n" + "\n".join(ls)) if ls else \
                "Nenhum jogo com qualidade própria — todos usam o padrão do console.\nUso: /qualidade <jogo> nativo|2x|3x|padrão"
        if len(args) < 2:
            return "Uso: /qualidade <jogo> nativo|2x|3x|padrão"
        hits = remove.find(lm, " ".join(args[:-1]))
        if len(hits) != 1:
            return ("Achei mais de um:\n" + "\n".join(f"• {lm[g]['title']}" for g in hits[:10])) if hits else "Não achei esse jogo."
        g = hits[0]
        try:
            return f"{lm[g]['title']}: " + quality.set_override(self.paths, g, lm[g]["console"], args[-1].lower())
        except ValueError as ex:
            return str(ex)

    def _console_for(self, uid: int, found):
        if found:
            return found
        p = self.cfg.get("pending_console", {}).get(str(uid))
        if p and time.time() - p["at"] < PENDING_TTL:
            return p["console"]
        return None

    def notify_finished(self) -> None:
        """Avisa uma vez quando cada download termina."""
        chat = self.cfg.get("notify_chat")
        if not chat:
            return
        from .qbt import DONE_STATES
        done = set(self.cfg.get("notified", []))
        try:
            ts = self.qbt.torrents()
        except QbtError:
            return
        new = [t for t in ts if t["state"] in DONE_STATES and t["hash"] not in done]
        if not new:
            self._retry_stuck(chat, ts)
            return
        names = ", ".join(t["name"] for t in new)
        # Decisão do usuário (2026-11-06): download concluído => /sync automático (substitui o /sync manual da v5.1)
        auto = syncer._cfg(self.paths).get("auto_sync", True)
        if auto and ops.game_running():
            if not self.cfg.get("waiting_game"):
                self.send(chat, f"✅ Download concluído: {names}\nVou colocar na biblioteca quando você fechar o jogo.")
                self.cfg["waiting_game"] = True; self.save_cfg()
            return  # tenta de novo no próximo ciclo
        self.cfg["waiting_game"] = False
        self.cfg["notified"] = sorted(done | {t["hash"] for t in new})[-500:]
        self.save_cfg()
        if not auto:
            self.send(chat, f"✅ Download concluído: {names}\nMande /sync para colocar na biblioteca.")
            return
        self.cfg["last_retry"] = time.time(); self.save_cfg()  # acabou de sincronizar: nova tentativa só em 1 h
        result = syncer.run_sync(self.paths, self.store, self.qbt, explicit=self.cfg.get("explicit"))
        self.send(chat, f"✅ Download concluído: {names}\n\n{result}")

    def notify_removidos(self) -> None:
        """Você tirou um jogo pelo próprio Steam ("Remover da biblioteca"): pergunta UMA vez se quer apagar os
        arquivos também (como o "Desinstalar" do Steam). Originais escondidos pela versão traduzida não entram."""
        from . import plugin_bridge, remove
        chat = self.cfg.get("notify_chat")
        done = json.loads(plugin_bridge.done_path(self.paths).read_text("utf-8")) \
            if plugin_bridge.done_path(self.paths).exists() else {}
        tirados = {g for g, e in remove.removed_games(self.paths).items()
                   if not (done.get(g) or {}).get("motivo") and e.get("console") != "pc"}
        if "removidos_avisados" not in self.cfg:  # 1ª vez: o que já estava tirado não vira enxurrada de perguntas
            self.cfg["removidos_avisados"] = sorted(tirados)
            self.save_cfg()
            return
        try:  # já perguntado na tela do Deck (painel): não pergunta de novo pelo Telegram
            from .painel import perguntados_path
            na_tela = set(json.loads(perguntados_path(self.paths).read_text("utf-8")))
        except (OSError, ValueError, ImportError):
            na_tela = set()
        novos = sorted(tirados - set(self.cfg["removidos_avisados"]) - na_tela)
        if not novos or not chat:
            return
        lm = remove.effective_map(self.paths)
        for g in novos:
            t = lm.get(g, {}).get("title", g)
            self.send(chat, f"🗑️ Você tirou {t} da biblioteca do Steam. Os arquivos ainda estão no Deck ocupando espaço.\n"
                            "Quer apagar também? (vão para a quarentena por 30 dias, dá para desfazer)",
                      buttons=[("Apagar os arquivos", f"/remover {g} confirmar"), ("Trazer de volta", f"/devolver {g}")])
        self.cfg["removidos_avisados"] = sorted(set(self.cfg["removidos_avisados"]) | set(novos))
        self.save_cfg()

    def notify_stalled(self, now: float | None = None) -> None:
        """Avisa UMA vez por download: sem fontes há 30 min (ninguém compartilhando) ou parado com erro
        (disco cheio, cartão SD removido). O resto da fila segue andando (QUEUE_PREFS no qbt.py)."""
        chat = self.cfg.get("notify_chat")
        if not chat:
            return
        try:
            ts = self.qbt.torrents()
        except QbtError:
            return
        now = time.time() if now is None else now
        seen = self.cfg.setdefault("stalled_notified", {})
        msgs = []
        for t in ts:
            h, name = t.get("hash"), (t.get("name") or "download")[:60]
            if not h or seen.get(h):
                continue
            st = t.get("state", "")
            if st in ("error", "missingFiles"):
                msgs.append(f"❌ «{name}» parou com erro no qBittorrent: disco cheio ou cartão SD removido? "
                            "Libere espaço (/disk mostra os maiores) ou recoloque o cartão; depois mande /resume.")
                seen[h] = "erro"
            elif (st in ("metaDL", "stalledDL", "forcedMetaDL") and (t.get("progress") or 0) < 1
                  and now - (t.get("added_on") or now) > STALLED_AFTER and not t.get("num_seeds")):
                pct = (t.get("progress") or 0) * 100
                msgs.append(f"⚠️ «{name}» está há mais de {STALLED_AFTER // 60} min sem fontes "
                            f"(ninguém compartilhando; {pct:.0f}% baixado). Os outros downloads continuam normalmente. "
                            "Ele segue tentando sozinho; se não andar, procure outro torrent do mesmo jogo.")
                seen[h] = "sem-fontes"
        live = {t.get("hash") for t in ts}
        for h in [h for h in seen if h not in live]:  # download apagado: esquece
            seen.pop(h)
        if msgs:
            self.save_cfg()
            self.send(chat, "\n\n".join(msgs))

    def _retry_stuck(self, chat, ts) -> None:
        """Download concluído que não entrou na biblioteca (ex.: erro corrigido depois): tenta de novo
        a cada hora, em silêncio; avisa só se algum jogo entrar."""
        if not syncer._cfg(self.paths).get("auto_sync", True) or ops.game_running():
            return
        from .qbt import DONE_STATES
        st = syncer._state(self.paths)
        stuck = [t for t in ts if t["state"] in DONE_STATES and t["hash"] not in st.get("ingested", {})
                 and t["hash"] not in st.get("pending", {})]
        last = self.cfg.get("last_retry", 0)
        if not stuck or time.time() - last < 3600:
            return
        self.cfg["last_retry"] = time.time(); self.save_cfg()
        result = syncer.run_sync(self.paths, self.store, self.qbt, explicit=self.cfg.get("explicit"))
        if result.split(" ", 1)[0] not in ("0", "Feche", "Safe-mode", "Jogo"):
            self.send(chat, "🔁 Nova tentativa automática:\n" + result)

    def notify_safe_mode(self) -> None:
        """Safe-mode ligado sozinho (testes, /sync travando): avisa uma vez, com o motivo e a saída."""
        chat = self.cfg.get("notify_chat")
        flag = ops.safe_mode_flag(self.paths)
        cur = flag.read_text("utf-8").strip() if flag.exists() else ""
        if not chat or cur == self.cfg.get("safe_notified", ""):
            return
        self.cfg["safe_notified"] = cur
        self.save_cfg()
        if cur:
            reason = cur.split(" ", 1)[1] if " " in cur else cur
            self.send(chat, f"🛑 O Deck Commander entrou em modo de segurança: {reason}.\n"
                            "Downloads e automações pararam; nada foi apagado. O bot continua aqui.\n"
                            "Para voltar ao normal: /sos off  (veja antes com /diagnostico)")

    def run(self) -> None:
        offset = self.cfg.get("offset", 0)
        self.log("bot iniciado")
        while True:
            try:
                ups = self.call("getUpdates", offset=offset, timeout=50,
                                allowed_updates='["message","callback_query"]')
            except Exception as e:  # noqa: BLE001 — sem rede: espera e tenta de novo
                self.log(f"rede: {type(e).__name__}"); time.sleep(30); continue
            for u in ups:
                offset = u["update_id"] + 1
                if u.get("callback_query"):
                    try:
                        self.handle_callback(u["callback_query"])
                    except Exception as e:  # noqa: BLE001
                        self.log(f"erro no botão: {e}")
                    continue
                m = u.get("message") or {}
                if "from" not in m:
                    continue
                try:
                    reply = self.handle_message(m)
                except Exception as e:  # noqa: BLE001
                    self.log(f"erro: {e}"); reply = f"❌ erro interno: {e}"
                if reply:
                    try:
                        self.send(m["chat"]["id"], reply)
                    except Exception as e:  # noqa: BLE001
                        self.log(f"falha ao responder: {e}")
            try:
                self.notify_safe_mode()
            except Exception as e:  # noqa: BLE001
                self.log(f"aviso de safe-mode: {e}")
            try:
                from .traducao import comandos as trad
                trad.notify(self)
                trad.progress_notify(self)
            except Exception as e:  # noqa: BLE001
                self.log(f"aviso de tradução: {e}")
            try:
                self.notify_finished()
            except Exception as e:  # noqa: BLE001
                self.log(f"aviso de download: {e}")
            try:
                self.notify_stalled()
            except Exception as e:  # noqa: BLE001
                self.log(f"aviso de download parado: {e}")
            try:
                from . import transferir
                transferir.notificar(self)
            except Exception as e:  # noqa: BLE001
                self.log(f"aviso de transferência: {e}")
            try:
                from . import familia_servico
                familia_servico.avisar_presenca(self)
            except Exception as e:  # noqa: BLE001
                self.log(f"família: {e}")
            try:
                self.notify_removidos()
            except Exception as e:  # noqa: BLE001
                self.log(f"aviso de jogo tirado do Steam: {e}")
            self.cfg["offset"] = offset; self.save_cfg()


PAIR_TTL = 30 * 60   # o código de pareamento vale 30 minutos
PAIR_MAX_FAILS = 5   # 5 códigos errados (de qualquer pessoa) e ele deixa de valer: gere outro no Deck


def pair_code(paths: Paths) -> str:
    code = f"{pysecrets.randbelow(10**6):06d}"
    paths.state.mkdir(parents=True, exist_ok=True)
    (paths.state / "telegram-pairing").write_text(code, "utf-8")
    (paths.state / "telegram-pairing.fails").unlink(missing_ok=True)
    return code


def pairing_code_valid(paths: Paths) -> str | None:
    """Código de pareamento em vigor, ou None (não existe, venceu ou errou demais). Sem isso, qualquer pessoa
    que achasse o bot podia tentar os 1 milhão de códigos sem limite."""
    f = paths.state / "telegram-pairing"
    try:
        if time.time() - f.stat().st_mtime > PAIR_TTL:
            f.unlink(missing_ok=True)
            return None
        return f.read_text().strip() or None
    except OSError:
        return None


def pairing_failed(paths: Paths) -> None:
    fails_p = paths.state / "telegram-pairing.fails"
    try:
        n = int(fails_p.read_text()) + 1
    except (OSError, ValueError):
        n = 1
    if n >= PAIR_MAX_FAILS:
        (paths.state / "telegram-pairing").unlink(missing_ok=True)
        fails_p.unlink(missing_ok=True)
    else:
        fails_p.write_text(str(n))


def main() -> None:
    paths = get_paths().ensure()
    tok = (paths.secrets / "telegram")
    if not tok.exists():
        raise SystemExit("sem token: rode  python3 -m dc secret telegram")
    Bot(paths, tok.read_text().strip()).run()
