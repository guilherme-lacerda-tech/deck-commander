"""M4 — Bot do Telegram (long-polling com urllib; sem dependências).

Segurança (M4.3): token em secrets/telegram (600), whitelist de user_id obrigatória — o primeiro
acesso exige o código de pareamento gerado no Deck (`dc telegram pair`), rate limit por usuário,
log em bot.log sem o token. Aprovação (M12.2) por /aprovar <id> com validade de 1h.
"""
from __future__ import annotations

import json
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
HELP = """Deck Commander — comandos
/add [console] <magnet> — baixa (console: ps2 psx gc wii snes n64 gba psp switch)
/sync — leva downloads concluídos para a biblioteca  (/sync tudo confirma pacotes grandes)
/console <id> <console> — responde quando o /sync perguntar
/reiniciar — reinicia o Steam para mostrar jogos novos
/status · /queue · /disk · /diagnostico
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

    def send(self, chat: int, text: str) -> None:
        for i in range(0, len(text), 3900):
            self.call("sendMessage", chat_id=chat, text=text[i:i + 3900])

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
        parts = text.strip().split()
        cmd, args = parts[0].split("@")[0].lower(), parts[1:]
        if uid not in self.cfg["allowed"]:
            code = (self.paths.state / "telegram-pairing").read_text().strip() \
                if (self.paths.state / "telegram-pairing").exists() else None
            if cmd == "/start" and code and args and pysecrets.compare_digest(args[0], code):
                self.cfg["allowed"].append(uid); self.save_cfg()
                (self.paths.state / "telegram-pairing").unlink()
                self.log(f"usuário {uid} pareado")
                return "Pareado ✅\n\n" + HELP
            self.log(f"recusado usuário {uid}: {cmd}")
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
            console, magnet = (args[0], args[1]) if len(args) > 1 else (None, args[0])
            if ops.in_safe_mode(P):
                return "Safe-mode ativo."
            cat = console or "auto"
            try:
                self.qbt.add(magnet, cat, str(Path(syncer._cfg(P)["downloads_root"]) / cat))
            except QbtError as e:
                return f"❌ {e} (sem internet? o /sync continua funcionando com o que já baixou)"
            return f"Adicionado ({cat}). Use /sync quando terminar."
        if cmd == "/sync":
            return syncer.run_sync(P, S, self.qbt, confirm_many=bool(args and args[0] == "tudo"),
                                   explicit=self.cfg.get("explicit"))
        if cmd == "/console" and len(args) == 2:
            st = syncer._state(P)
            h = next((k for k in st.get("pending", {}) if k.startswith(args[0])), None)
            if not h:
                return "Não achei esse download pendente."
            self.cfg.setdefault("explicit", {})[h] = args[1]; self.save_cfg()
            return f"Ok, {st['pending'][h]} = {args[1]}. Rode /sync."
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
            items = health.disk_report(syncer.rom_roots(), vdf.read_shortcuts(syncer.shortcuts_path()))
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

    def run(self) -> None:
        offset = self.cfg.get("offset", 0)
        self.log("bot iniciado")
        while True:
            try:
                ups = self.call("getUpdates", offset=offset, timeout=50, allowed_updates='["message"]')
            except Exception as e:  # noqa: BLE001 — sem rede: espera e tenta de novo
                self.log(f"rede: {type(e).__name__}"); time.sleep(30); continue
            for u in ups:
                offset = u["update_id"] + 1
                m = u.get("message") or {}
                if not m.get("text", "").startswith("/"):
                    continue
                try:
                    reply = self.handle(m["from"]["id"], m["chat"]["id"], m["text"])
                except Exception as e:  # noqa: BLE001
                    self.log(f"erro: {e}"); reply = f"❌ erro interno: {e}"
                try:
                    self.send(m["chat"]["id"], reply)
                except Exception as e:  # noqa: BLE001
                    self.log(f"falha ao responder: {e}")
            self.cfg["offset"] = offset; self.save_cfg()


def pair_code(paths: Paths) -> str:
    code = f"{pysecrets.randbelow(10**6):06d}"
    paths.state.mkdir(parents=True, exist_ok=True)
    (paths.state / "telegram-pairing").write_text(code, "utf-8")
    return code


def main() -> None:
    paths = get_paths().ensure()
    tok = (paths.secrets / "telegram")
    if not tok.exists():
        raise SystemExit("sem token: rode  python3 -m dc secret telegram")
    Bot(paths, tok.read_text().strip()).run()
