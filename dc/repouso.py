"""Modo repouso (pedido 13/11/2026, como o do PS5): na tomada, com download ou tradução andando, o Deck não dorme —
a tela apaga normalmente e o trabalho continua; quando acaba, a trava sai e o Deck volta a dormir sozinho.

Por que precisa de UMA permissão de administrador: medido no Deck em 13/11/2026, só programas da sessão da tela podem
segurar o descanso ("Access denied ... interactive authentication"); os serviços do Deck Commander não são da sessão,
e a Steam não oferece nenhum jeito de segurar (procurado em todo o SteamClient). A regra do sistema
(tools/deck/permitir-repouso.sh, rodada pelo próprio usuário com sudo) libera só isto: o usuário "deck" segurar o
descanso. Sem a regra, o repouso fica desligado e nada muda.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

REGRA = Path("/etc/polkit-1/rules.d/49-deck-commander-repouso.rules")
ATIVOS = ("downloading", "stalledDL", "metaDL", "queuedDL", "forcedDL", "checkingDL")
TRADUZINDO = ("rodando", "na fila")


def permitido(regra: Path = REGRA) -> bool:
    return regra.exists()


def ligado(paths) -> bool:
    return not (paths.config / "repouso-desligado").exists()


def traducao_andando(paths) -> bool:
    d = paths.state / "traducao"
    for f in d.glob("*.json") if d.exists() else []:
        try:
            if json.loads(f.read_text("utf-8")).get("status") in TRADUZINDO:
                return True
        except (OSError, ValueError):
            continue
    return False


def motivo(paths, torrents: list[dict], ac: bool) -> str | None:
    """Por que segurar agora (texto) ou None."""
    if not ac or not ligado(paths):
        return None
    n = sum(1 for t in torrents if t.get("state") in ATIVOS)
    partes = []
    if n:
        partes.append(f"{n} download(s)")
    if traducao_andando(paths):
        partes.append("tradução")
    return " e ".join(partes) or None


class Trava:
    """Segura o descanso com systemd-inhibit enquanto houver motivo. Uma por serviço."""

    def __init__(self, abrir=subprocess.Popen):
        self._abrir = abrir
        self.proc = None
        self.porque = None

    def ajustar(self, porque: str | None) -> str | None:
        """Liga/desliga conforme o motivo. Devolve o que mudou (para o registro) ou None."""
        vivo = self.proc is not None and self.proc.poll() is None
        if porque and not vivo:
            self.proc = self._abrir(["systemd-inhibit", "--what=sleep:idle", "--mode=block", "--who=Deck Commander",
                                     f"--why=Repouso: {porque} na tomada", "sleep", "infinity"],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.porque = porque
            return f"repouso: o Deck não dorme enquanto houver {porque} (na tomada)"
        if not porque and vivo:
            self.proc.terminate()
            self.proc = None
            antes, self.porque = self.porque, None
            return f"repouso: terminou ({antes}); o Deck pode dormir"
        return None
