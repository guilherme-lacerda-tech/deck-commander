"""Aviso quando o emulador muda de versão entre duas aberturas de jogo.

Revisão retrô 12/11/2026: o save state (L4/R4) é uma foto da memória do emulador e pode não abrir depois que o
emulador atualiza (Flatpak se atualiza sozinho no Deck). O save do próprio jogo (o do menu dele) sempre abre. Sem
aviso, a pessoa só descobre quando o save state some.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

NOMES = {"org.libretro.RetroArch": "RetroArch", "net.pcsx2.PCSX2": "PCSX2", "org.DolphinEmu.dolphin-emu": "Dolphin",
         "org.ppsspp.PPSSPP": "PPSSPP"}
# consoles em que o Deck Commander põe save state nos botões de trás (Switch/PC não têm)
COM_SAVE_STATE = {"psx", "ps2", "gc", "wii", "nes", "snes", "n64", "gb", "gbc", "gba", "genesis", "sms", "gg",
                  "segacd", "saturn", "pce", "arcade", "psp"}


def _sem_env(cmd: list[str]) -> list[str]:
    """Tira os "/usr/bin/env VAR=x" da frente — podem ser vários: o medidor de desempenho (MangoHud) põe o dele antes
    do da camada WSI. Falha vista no Deck 13/11/2026: com um só, a versão lida era a do /usr/bin/env e o ponto de
    continuar era recusado como "emulador de outra versão"."""
    while cmd and Path(cmd[0]).name == "env":
        cmd = cmd[1:]
        while cmd and "=" in cmd[0] and not cmd[0].startswith("/"):
            cmd = cmd[1:]
    return cmd


def _qual(cmd: list[str]) -> tuple[str, str] | None:
    """(chave, nome legível) do emulador do comando."""
    cmd = _sem_env(cmd)
    if not cmd:
        return None
    if Path(cmd[0]).name == "flatpak":
        app = next((a for a in cmd[2:] if not a.startswith("-") and "." in a), None)
        return (app, NOMES.get(app, app)) if app else None
    nome = Path(cmd[0]).name
    return nome, ("DuckStation" if "duckstation" in nome.lower() else nome)


def identidade(cmd: list[str]) -> str | None:
    cmd = _sem_env(cmd)
    q = _qual(cmd)
    if not q:
        return None
    if Path(cmd[0]).name == "flatpak":
        r = subprocess.run(["flatpak", "info", "--show-commit", q[0]], capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or None
    if not os.path.exists(cmd[0]):
        return None
    st = os.stat(cmd[0])
    return f"{st.st_size}-{int(st.st_mtime)}"


def conferir(state_dir: Path, console: str, cmd: list[str], ident=identidade) -> str | None:
    """Guarda a versão vista agora; devolve o aviso se ela mudou desde a última abertura."""
    if console not in COM_SAVE_STATE:
        return None
    q = _qual(cmd)
    atual = ident(cmd) if q else None
    if not atual:
        return None
    arq = Path(state_dir) / "versoes-emuladores.json"
    try:
        vistos = json.loads(arq.read_text("utf-8"))
    except (OSError, ValueError):
        vistos = {}
    antes = vistos.get(q[0])
    if antes == atual:
        return None
    vistos[q[0]] = atual
    arq.parent.mkdir(parents=True, exist_ok=True)
    tmp = arq.with_name(f"{arq.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(vistos), "utf-8")
    tmp.replace(arq)
    if antes is None:  # primeira vez que vemos este emulador: nada a comparar
        return None
    return (f"O {q[1]} foi atualizado. Save states antigos (R4) podem não abrir nesta versão — "
            "salve também pelo menu do próprio jogo.")
