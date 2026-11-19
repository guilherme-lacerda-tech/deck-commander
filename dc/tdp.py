"""TDP (limite de energia, W) automático por console ao abrir o jogo e volta ao valor anterior ao fechar; dock/TV.

Usa o SteamOS Manager pelo D-Bus de sessão (sem root). Escrito pela IA local (qwen3-coder) e revisado.
"""
import json
import subprocess
from pathlib import Path

TDP_POR_CONSOLE: dict[str, int] = {
    # Piso inicial por console. Não é uma regra de "bateria antes do jogo" nem um teto fixo:
    # o controlador ao vivo sobe um watt por vez se a velocidade nativa cair e só devolve
    # potência após estabilidade prolongada. Assim uma cena leve não gasta como uma batalha pesada.
    "nes": 5, "snes": 5, "gb": 5, "gbc": 5, "gba": 5, "sms": 5, "gg": 5, "genesis": 5, "pce": 5,
    "arcade": 5, "pc": 5,
    "psx": 7, "n64": 7, "nds": 7, "segacd": 7, "saturn": 7,
    "psp": 9, "dc": 9,
    "gc": 12, "wii": 12, "ps2": 12, "xbox": 12, "n3ds": 12,
    "switch": 15, "switch2": 15, "wiiu": 15, "ps3": 15, "x360": 15
}

class Tdp:
    def __init__(self, estado: Path, run=subprocess.run):
        self.estado = estado
        self.run = run
        self.piso: int | None = None
        # Só reduzimos potência que esta execução elevou. Um limite manual maior do usuário é respeitado.
        self.gerenciado: int | None = None

    def ler(self) -> int | None:
        try:
            result = self.run(
                ["busctl", "--user", "get-property", "com.steampowered.SteamOSManager1",
                 "/com/steampowered/SteamOSManager1",
                 "com.steampowered.SteamOSManager1.TdpLimit1", "TdpLimit"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return int(result.stdout.split()[-1])
        except Exception:
            pass
        return None

    def maximo(self) -> int | None:
        try:
            result = self.run(
                ["busctl", "--user", "get-property", "com.steampowered.SteamOSManager1",
                 "/com/steampowered/SteamOSManager1",
                 "com.steampowered.SteamOSManager1.TdpLimit1", "TdpLimitMax"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return int(result.stdout.split()[-1])
        except Exception:
            pass
        return None

    def definir(self, watts: int) -> bool:
        maximo = self.maximo()
        if maximo is None:
            maximo = 15
        watts = max(3, min(watts, maximo))
        try:
            result = self.run(
                ["busctl", "--user", "set-property", "com.steampowered.SteamOSManager1",
                 "/com/steampowered/SteamOSManager1",
                 "com.steampowered.SteamOSManager1.TdpLimit1", "TdpLimit", "u", str(watts)],
                capture_output=True, text=True, timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

    def aplicar_console(self, console: str, em_dock: bool = False) -> str:
        if console not in TDP_POR_CONSOLE:
            return f"Console {console} não reconhecido."

        tdp = TDP_POR_CONSOLE[console]
        if em_dock:
            maximo = self.maximo()
            if maximo is None:
                maximo = 15
            tdp = maximo
        self.piso = tdp

        if not self.estado.exists():  # jogo aberto em cima de outro não perde o valor original
            anterior = self.ler()
            if anterior is not None:
                self.estado.parent.mkdir(parents=True, exist_ok=True)
                with open(self.estado, "w") as f:
                    json.dump({"anterior": anterior}, f)
        try:
            anterior = json.loads(self.estado.read_text()).get("anterior")
        except (OSError, ValueError):
            anterior = None
        atual = self.ler()
        # Se o usuário deixou um valor mais alto, o Commander não o derruba ao abrir o jogo.
        alvo = max(tdp, atual or tdp)
        if atual != alvo and not self.definir(alvo):
            return f"Não consegui ajustar o TDP para {console} (SteamOS Manager não respondeu)."
        if atual is not None and atual < alvo:
            self.gerenciado = alvo
        return f"TDP inicial {alvo} W para {console}" + (f" (antes {anterior} W)" if anterior is not None else "")

    def aumentar_passo(self) -> str | None:
        """Sob demanda, acrescenta somente 1 W ao TDP da partida em curso."""
        atual = self.ler()
        maximo = self.maximo() or 15
        if atual is None:
            return None
        alvo = min(maximo, atual + 1)
        if alvo == atual:
            return "TDP já estava no máximo"
        if self.definir(alvo):
            self.gerenciado = alvo
            return f"TDP elevado agora de {atual} para {alvo} W"
        return None

    def usar_piso_portatil(self, console: str) -> None:
        """Após sair da dock, permite que a redução gradual volte ao piso portátil do console."""
        if console in TDP_POR_CONSOLE:
            self.piso = TDP_POR_CONSOLE[console]

    def reduzir_passo(self) -> str | None:
        """Devolve 1 W apenas depois de estabilidade e nunca abaixo do piso do console."""
        if self.gerenciado is None or self.piso is None:
            return None
        atual = self.ler()
        if atual is None or atual <= self.piso:
            return None
        alvo = max(self.piso, atual - 1)
        if self.definir(alvo):
            self.gerenciado = alvo
            return f"TDP reduzido de {atual} para {alvo} W após estabilidade"
        return None

    def priorizar_desempenho(self) -> str | None:
        """Compatibilidade: novos chamadores devem usar aumentar_passo()."""
        return self.aumentar_passo()

    def restaurar(self) -> str:
        if not self.estado.exists():
            return "Nenhum TDP guardado para restaurar."
        with open(self.estado, "r") as f:
            dados = json.load(f)
        anterior = dados.get("anterior")
        if anterior is not None:
            self.definir(anterior)
            self.estado.unlink()
            return f"TDP restaurado para {anterior} W"
        return "Nenhum TDP guardado para restaurar."

def em_dock(drm: Path = Path("/sys/class/drm")) -> bool:
    try:
        for card in drm.iterdir():
            nome = card.name
            if "eDP" in nome or not ("-DP-" in nome or "-HDMI-" in nome):
                continue  # eDP = tela do próprio Deck
            status_file = card / "status"
            if status_file.exists() and status_file.read_text().strip() == "connected":  # não "disconnected"
                return True
    except Exception:
        pass
    return False

if __name__ == "__main__":
    import sys
    from pathlib import Path

    from .paths import get_paths
    tdp = Tdp(get_paths().state / "tdp-anterior.json")
    args = sys.argv[1:]

    if not args:
        print("Uso: python3 -m dc.tdp ler|aplicar <console>|restaurar|dock")
        sys.exit(1)

    comando = args[0]
    if comando == "ler":
        valor = tdp.ler()
        print(f"TDP atual: {valor} W" if valor is not None else "Falha ao ler TDP")
    elif comando == "maximo":
        valor = tdp.maximo()
        print(f"TDP máximo: {valor} W" if valor is not None else "Falha ao ler TDP máximo")
    elif comando == "aplicar":
        if len(args) < 2:
            print("Uso: python3 -m dc.tdp aplicar <console>")
            sys.exit(1)
        console = args[1]
        em_dock_ = em_dock()
        print(tdp.aplicar_console(console, em_dock_))
    elif comando == "restaurar":
        print(tdp.restaurar())
    elif comando == "dock":
        print("Dock conectado" if em_dock() else "Dock não conectado")
    else:
        print("Comando desconhecido. Use: ler, aplicar, restaurar ou dock")
        sys.exit(1)
