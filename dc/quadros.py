"""Limite de quadros do modo de jogo x emuladores (defeito achado no Deck 14/11/2026).

Medido: o Nova the Squirrel (NES, RetroArch) rodava a 30 quadros, ou seja, o jogo inteiro em câmera lenta (o
emulador anda no ritmo da tela). Causa: o limitador do gamescope (a camada de vídeo do modo de jogo) estava em 30 e
ficou preso — a configuração da Steam para o jogo dizia "sem limite". Com `gamescopectl debug_set_fps_limit 30` o
RetroArch mostrou 30,00; com `... 0`, 60,00 (testado com o contador do próprio RetroArch).

Num emulador, limite abaixo do ritmo do console nunca ajuda: o jogo fica lento (jogo que já roda a 30, como o God of
War do PSP, não muda). Por isso, ao abrir um jogo de emulador, o limite é tirado — duas vezes, porque a Steam aplica o
perfil dela logo depois de o jogo abrir. Jogos do PC ficam como você deixou. Para manter o seu limite também nos
emuladores: crie config/limite-quadros-manter.
"""
from __future__ import annotations

import shutil
import subprocess
import time

NAO_EMULADOR = {"pc", "steam"}
ESPERAS = (4, 12)  # s depois de abrir: a Steam aplica o perfil do jogo nesse meio tempo


def deve_soltar(paths, console: str, ambiente=None) -> bool:
    """Só jogo de emulador aberto PELA STEAM (ela põe SteamGameId no ambiente) e no modo de jogo (gamescopectl)."""
    import os
    amb = os.environ if ambiente is None else ambiente
    return (console not in NAO_EMULADOR and not (paths.config / "limite-quadros-manter").exists()
            and bool(amb.get("SteamGameId") or amb.get("SteamAppId")) and shutil.which("gamescopectl") is not None)


def soltar(rodar=subprocess.run, dormir=time.sleep, esperas=ESPERAS) -> int:
    """Tira o limite de quadros do gamescope. Devolve quantas vezes deu certo."""
    ok = 0
    for s in esperas:
        dormir(s)
        try:
            r = rodar(["gamescopectl", "debug_set_fps_limit", "0"], capture_output=True, timeout=10, check=False)
            ok += r.returncode == 0
        except (OSError, subprocess.SubprocessError):
            pass
    return ok


def em_segundo_plano(paths, console: str, abrir=subprocess.Popen, ambiente=None) -> bool:
    """Chamado pelo lançador antes de abrir o emulador (o processo segue sozinho depois do exec)."""
    if not deve_soltar(paths, console, ambiente):
        return False
    import sys
    from pathlib import Path
    try:
        abrir([sys.executable, "-m", "dc.quadros", "soltar"], cwd=str(Path(__file__).resolve().parents[1]),
              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return True
    except OSError:
        return False


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["soltar"]:
        soltar()
