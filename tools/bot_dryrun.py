#!/usr/bin/env python3
"""Diagnóstico: roda comandos do bot no Deck SEM mandar nada no Telegram e sem tocar na config real do
bot (usa uma cópia em /tmp). Mostra a resposta que o bot daria.
Uso: python3 tools/bot_dryrun.py "/duplicados" "/qualidade lista" ..."""
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dc import bot  # noqa: E402
from dc.paths import get_paths  # noqa: E402

paths = get_paths()
tmp = Path(tempfile.mkdtemp()) / "telegram.json"
shutil.copy(paths.config / "telegram.json", tmp)
b = bot.Bot(paths, "dry-run-sem-token")
b.cfg_path = tmp
b.cfg = json.loads(tmp.read_text("utf-8"))
uid = b.cfg["allowed"][0]
b.send = lambda chat, text: print(f"[enviaria para {chat}]\n{text}")
for cmd in sys.argv[1:]:
    print(f">>> {cmd}")
    print(b.handle(uid, uid, cmd) if cmd.startswith("/") else b.handle_message(
        {"from": {"id": uid}, "chat": {"id": uid}, "text": cmd}))
    print()
