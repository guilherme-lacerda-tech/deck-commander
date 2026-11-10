"""Assistente do bot do Telegram (instalação fácil, ex.: o Deck de outra pessoa).

    python3 -m dc x telegram-setup

1. Mostra um QR code: o celular abre o @BotFather (onde se cria o bot) — passo a passo na tela.
2. Pede o token (colado sem aparecer na tela), confere com o Telegram e guarda em secrets/ (permissão 600).
3. Liga o serviço do bot e mostra outro QR: o celular abre O SEU bot já com o código de pareamento —
   é só tocar em "Iniciar". Só essa conta passa a mandar no Deck.
Nada disso vai para o git: o token fica só em ~/.config/deck-commander/secrets/telegram.
"""
from __future__ import annotations

import getpass
import json
import os
import re
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from . import qr
from .paths import Paths

TOKEN_RX = re.compile(r"\d{6,12}:[A-Za-z0-9_-]{30,50}")
BOTFATHER = "https://t.me/BotFather"


def save_secret(paths: Paths, name: str, value: str) -> Path:
    paths.ensure()
    p = paths.secrets / name
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(value + "\n")
    return p


def bot_username(token: str) -> Optional[str]:
    """Pergunta ao Telegram de quem é o token (getMe). None = token recusado ou sem internet."""
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getMe", timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
        return data["result"]["username"] if data.get("ok") else None
    except Exception:  # noqa: BLE001 — qualquer falha = não confirmou
        return None


def _start_bot_service() -> None:
    for args in (["enable", "--now", "deck-commander-bot"], ["restart", "deck-commander-bot"]):
        try:
            subprocess.run(["systemctl", "--user", *args], capture_output=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            pass


def _show_qr(link: str, png_name: str, out: Callable[[str], None]) -> None:
    out(qr.terminal(link))
    desk = Path.home() / "Desktop"
    if desk.is_dir():
        try:
            out(f"(o mesmo QR está salvo em {qr.png(link, desk / png_name)})")
        except OSError:
            pass
    out(f"Sem câmera? Abra no celular: {link}")


def run(paths: Paths, ask_token: Callable[[str], str] = getpass.getpass, out: Callable[[str], None] = print,
        whoami: Callable[[str], Optional[str]] = bot_username, start_service: Callable[[], None] = _start_bot_service,
        wait_s: int = 600, sleep: Callable[[float], None] = time.sleep) -> int:
    from .bot import pair_code
    tok_file = paths.secrets / "telegram"
    username = None
    if tok_file.exists():
        username = whoami(tok_file.read_text().strip())
        if username:
            out(f"Já existe um bot configurado: @{username}. Vou só gerar um novo código de pareamento.")
    if not username:
        out("PASSO 1 de 2 — criar o seu bot no Telegram\n"
            "Aponte a câmera do celular para o QR abaixo (ele abre o @BotFather, o robô oficial do Telegram):")
        _show_qr(BOTFATHER, "deck-commander-botfather.png", out)
        out("No @BotFather: toque em INICIAR → mande /newbot → escolha um nome (ex.: Deck do João) → escolha um\n"
            "usuário que termine em bot (ex.: deckdojoao_bot). Ele responde com um TOKEN parecido com\n"
            "123456789:AAH...  — toque nele para copiar e mande para você mesmo (ou digite aqui).")
        for _ in range(3):
            tok = ask_token("Cole o token e aperte Enter (não aparece na tela): ").strip()
            if len(tok) % 2 == 0 and tok[:len(tok) // 2] == tok[len(tok) // 2:]:
                tok = tok[:len(tok) // 2]  # colado duas vezes
            if not TOKEN_RX.fullmatch(tok):
                out("Isso não parece um token (formato número:letras). Tente de novo.")
                continue
            username = whoami(tok)
            if not username:
                out("O Telegram não reconheceu esse token (ou o Deck está sem internet). Tente de novo.")
                continue
            save_secret(paths, "telegram", tok)
            out(f"✅ Token guardado (só neste Deck, nunca no git). Seu bot: @{username}")
            break
        else:
            out("Não deu desta vez. Rode de novo quando tiver o token:  python3 -m dc x telegram-setup")
            return 1
    start_service()
    code = pair_code(paths)
    out("\nPASSO 2 de 2 — ligar o bot ao SEU Telegram\n"
        "Aponte a câmera para este QR: abre o seu bot. Toque em INICIAR e pronto.")
    _show_qr(f"https://t.me/{username}?start={code}", "deck-commander-parear.png", out)
    out(f"(Ou mande para @{username} a mensagem:  /start {code}  — vale 30 minutos)")
    pairing = paths.state / "telegram-pairing"
    for _ in range(max(0, wait_s) // 5):
        if not pairing.exists():
            out("🎉 Pareado! Mande  Switch  (ou PS2, GBA…) para o bot e depois o .torrent ou link magnet.")
            return 0
        sleep(5)
    if wait_s:
        out("Ainda não vi o pareamento. Se já tocou em INICIAR, confira mandando /status para o bot.")
    return 0
