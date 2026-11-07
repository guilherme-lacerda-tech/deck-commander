"""dc-launch <game_id> — resolve o jogo no mapa e executa o emulador certo (substitui o processo)."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .library import build_command
from .paths import get_paths


def main(argv: list[str]) -> None:
    paths = get_paths()
    log = paths.logs / "launch.log"
    paths.logs.mkdir(parents=True, exist_ok=True)

    def say(msg: str) -> None:
        with open(log, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now(timezone.utc).isoformat()} {msg}\n")

    if not argv:
        say("erro: sem game_id"); sys.exit(2)
    game_id = argv[0]
    try:
        launch_map = json.loads((paths.data / "launch-map.json").read_text("utf-8"))
        emu_cfg = paths.config / "emulators.json"
        emulators = json.loads(emu_cfg.read_text("utf-8")) if emu_cfg.exists() else {}
        cmd = build_command(game_id, launch_map, emulators)
    except Exception as e:  # noqa: BLE001
        say(f"erro ao resolver {game_id}: {e}"); sys.exit(1)
    if not Path(cmd[-1]).exists():
        say(f"erro: ROM não encontrada {cmd[-1]} (cartão SD fora?)"); sys.exit(1)
    from . import quality
    try:
        msg = quality.restore(paths)  # sobra de um jogo anterior fechado à força
        if msg:
            say(f"qualidade: {msg}")
        rec = quality.apply_for_launch(paths, game_id, launch_map[game_id]["console"])
    except Exception as e:  # noqa: BLE001 — ajuste de qualidade nunca impede o jogo de abrir
        say(f"qualidade: ignorado ({e})"); rec = None
    say(f"lançando {game_id}: {cmd}")
    if not rec:
        os.execvp(cmd[0], cmd)
    say(f"qualidade deste jogo: {rec['key']} {rec['old']} -> {rec['new']} (volta ao fechar)")
    import signal
    import subprocess
    child = subprocess.Popen(cmd)

    def _stop(signum, _frame):  # "Sair do jogo" do Steam: fecha o emulador e ainda devolve a qualidade
        child.send_signal(signum)
        try:
            child.wait(timeout=8)
        except subprocess.TimeoutExpired:
            child.kill()
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGHUP, _stop)
    try:
        code = child.wait()
    finally:
        try:
            say(f"qualidade: {quality.restore(paths)}")
        except Exception as e:  # noqa: BLE001
            say(f"qualidade: devolução falhou ({e}); o serviço tenta de novo")
    sys.exit(code)
