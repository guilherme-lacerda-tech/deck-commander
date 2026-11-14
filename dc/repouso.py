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


_PERMITIDO: dict = {}


def permitido(regra: Path = REGRA, testar=None) -> bool:
    """A permissão vale? Testa a própria trava (1 vez a cada 10 min). Olhar o arquivo não serve: a pasta
    /etc/polkit-1/rules.d só o administrador lê (visto no Deck 14/11/2026: regra instalada e exists() = False)."""
    import time
    if regra != REGRA:  # testes
        return regra.exists()
    if _PERMITIDO and time.time() - _PERMITIDO["quando"] < 600:
        return _PERMITIDO["ok"]
    if testar is None:
        def testar():
            return subprocess.run(["systemd-inhibit", "--what=sleep", "--mode=block", "--who=Deck Commander",
                                   "--why=teste", "true"], capture_output=True, timeout=10).returncode == 0
    try:
        ok = bool(testar())
    except (OSError, subprocess.SubprocessError):
        ok = False
    _PERMITIDO.update(ok=ok, quando=time.time())
    return ok


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

    def __init__(self, abrir=subprocess.Popen, marca: Path | None = None):
        self._abrir = abrir
        self.marca = marca  # arquivo "segurando agora" (o botão de ligar só apaga a tela se houver trava)
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
            if self.marca:
                self.marca.write_text(porque, "utf-8")
            return f"repouso: o Deck não dorme enquanto houver {porque} (na tomada)"
        if not porque and vivo:
            self.proc.terminate()
            self.proc = None
            if self.marca:
                self.marca.unlink(missing_ok=True)
            antes, self.porque = self.porque, None
            return f"repouso: terminou ({antes}); o Deck pode dormir"
        return None


# ------------------------------------------------------------------------------------------------ tela
# Testado no Deck 14/11/2026: com a trava, o pedido de dormir da Steam é recusado ("BlockedByInhibitorLock") e a TELA
# FICA ACESA. O brilho (/sys/class/backlight/*/brightness) é gravável pelo usuário deck: o botão de ligar apaga a tela
# enquanto há trabalho; apertar de novo acende; quando o trabalho acaba com a tela apagada, o Deck dorme sozinho.
BRILHO = Path("/sys/class/backlight/amdgpu_bl0/brightness")


def _ativo_path(paths) -> Path:
    return paths.state / "repouso-ativo"


def _tela_path(paths) -> Path:
    return paths.state / "repouso-tela.json"


def tela_apagada(paths) -> bool:
    return _tela_path(paths).exists()


def apagar(paths, brilho: Path = BRILHO) -> None:
    antes = int(brilho.read_text().strip() or 0)
    _tela_path(paths).write_text(json.dumps({"antes": antes}), "utf-8")
    brilho.write_text("0")


def acender(paths, brilho: Path = BRILHO) -> None:
    try:
        antes = json.loads(_tela_path(paths).read_text("utf-8")).get("antes") or 30000
    except (OSError, ValueError):
        return
    brilho.write_text(str(antes))
    _tela_path(paths).unlink(missing_ok=True)


def botao(paths, brilho: Path = BRILHO) -> str:
    """Botão de ligar apertado (o plugin avisa). Com o repouso segurando: apaga/acende a tela."""
    if not _ativo_path(paths).exists():
        return "repouso: nada segurando (o Deck dorme normal)"
    if tela_apagada(paths):
        acender(paths, brilho)
        return "repouso: tela acesa"
    apagar(paths, brilho)
    return "repouso: tela apagada, trabalho continua"


def ao_terminar(paths, dormir=None, brilho: Path = BRILHO) -> str | None:
    """Trava solta: se a tela foi apagada pelo repouso, acende e põe o Deck para dormir (o que você pediu antes)."""
    if not tela_apagada(paths):
        return None
    acender(paths, brilho)
    if dormir is None:
        def dormir():
            from .steam_cdp import steam
            steam("SteamClient.System.SuspendPC(), 1")
    try:
        dormir()
        return "repouso: terminou com a tela apagada; o Deck foi dormir"
    except Exception as e:  # noqa: BLE001
        return f"repouso: terminou, mas não consegui pôr o Deck para dormir ({e})"


def vigiar_botao(paths, abrir=subprocess.Popen, agora=None) -> None:
    """Escuta o registro do sistema: cada pedido de dormir recusado pela trava ("BlockedByInhibitorLock", gravado
    pela Steam) é um aperto no botão de ligar -> apaga/acende a tela. Testado no Deck 14/11/2026: o aviso do plugin
    (PrepareForSystemSuspendProgress) não dispara quando o pedido é recusado; esta linha aparece sempre."""
    import time
    agora = agora or time.time
    proc = abrir(["journalctl", "-f", "-n", "0", "-o", "cat", "-t", "steam"], stdout=subprocess.PIPE,
                 stderr=subprocess.DEVNULL, text=True)
    ultimo = 0.0
    for linha in proc.stdout:
        if "BlockedByInhibitorLock" in linha and agora() - ultimo > 3:  # um aperto gera mais de uma linha
            ultimo = agora()
            try:
                botao(paths)
            except OSError:
                pass


def main(argv: list[str]) -> int:
    from .paths import get_paths
    if argv[:1] == ["botao"]:
        print(botao(get_paths()))
        return 0
    print("uso: python3 -m dc.repouso botao")
    return 2


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
