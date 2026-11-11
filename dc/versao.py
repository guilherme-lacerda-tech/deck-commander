"""Versão instalada no Deck e /voltar (desfaz a última implantação em 1 comando).

tools/implantar.py guarda a versão que estava rodando em ~/deck-commander.anterior antes de copiar a nova e escreve
VERSAO.txt ("<commit> <data>") nas duas. /voltar troca as duas pastas (rodar /voltar de novo desfaz a volta),
reinicia o bot e o serviço de energia e reinstala o plugin do Decky daquela versão.
A troca roda fora do serviço do bot (systemd-run), porque reiniciar o bot mataria quem está trocando.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


def _pastas(home: Path | None = None) -> tuple[Path, Path]:
    h = home or Path.home()
    return h / "deck-commander", h / "deck-commander.anterior"


def _ler(p: Path) -> str:
    try:
        return (p / "VERSAO.txt").read_text("utf-8").strip() or "sem registro"
    except OSError:
        return "sem registro"


def descrever(home: Path | None = None) -> dict:
    atual, anterior = _pastas(home)
    return {"atual": _ler(atual), "anterior": _ler(anterior) if anterior.is_dir() else None}


def script_troca(home: Path | None = None) -> str:
    atual, anterior = _pastas(home)
    tmp = atual.with_name("deck-commander.trocando")
    return (f"set -e; sleep 2; rm -rf '{tmp}'; mv '{atual}' '{tmp}'; mv '{anterior}' '{atual}'; mv '{tmp}' '{anterior}'; "
            f"systemctl --user restart deck-commander-bot deck-commander-power; cd '{atual}'; "
            "python3 -c 'from dc import setup; l=[]; setup.setup_plugin(l)'")


def voltar(home: Path | None = None, run=subprocess.run) -> str:
    d = descrever(home)
    if not d["anterior"]:
        return "Não há versão anterior guardada (ela é guardada a partir da próxima atualização)."
    r = run(["systemd-run", "--user", "--collect", "--unit", "dc-voltar", "bash", "-c", script_troca(home)],
            capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        return "Não consegui voltar: " + (r.stderr or r.stdout).strip()[-300:]
    return (f"↩️ Voltando para a versão {d['anterior']} (estava na {d['atual']}). O bot reinicia em alguns segundos; "
            "/voltar de novo desfaz.")


def comando(args: list[str], home: Path | None = None, run=subprocess.run) -> tuple[str, list]:
    """/voltar → mostra as versões e pede confirmação; /voltar sim → troca."""
    if args[:1] == ["sim"]:
        return voltar(home, run), []
    d = descrever(home)
    if not d["anterior"]:
        return f"Versão instalada: {d['atual']}. Ainda não há versão anterior guardada.", []
    return (f"Versão instalada: {d['atual']}\nVersão anterior: {d['anterior']}\n\nVoltar para a anterior? Use se algo "
            "parou de funcionar depois da última atualização. Seus jogos, traduções e configurações não mudam.",
            [("Voltar versão", "/voltar sim")])
