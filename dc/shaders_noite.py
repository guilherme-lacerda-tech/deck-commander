import json
from datetime import datetime
from pathlib import Path

CONSOLES_COM_SHADER = {"switch", "switch2", "wiiu", "ps3", "gc", "wii", "ps2", "x360", "n3ds"}


def pode_rodar(agora: datetime, na_tomada: bool, jogo_aberto: bool, inicio: int = 2, fim: int = 6) -> bool:
    """Retorna True se o Deck estiver na tomada, sem jogo aberto e for hora de rodar."""
    return na_tomada and not jogo_aberto and inicio <= agora.hour < fim


def pendentes(launch_map: dict, feitos: dict[str, str], ultimas: dict[str, datetime]) -> list[str]:
    """Retorna lista de game_ids pendentes para pré-compilação de shaders."""
    jogos = []
    for game_id, dados in launch_map.items():
        if (dados.get("removed") is not True and
            game_id not in feitos and
            game_id not in ultimas and
            dados.get("console") in CONSOLES_COM_SHADER):
            jogos.append(game_id)
    return sorted(jogos, key=lambda gid: launch_map[gid].get("title", ""))


class Estado:
    """Gerencia o estado persistente de pré-compilação."""
    
    def __init__(self, path: Path):
        self.path = path
        self.feitos = {}
        self.ultima_rodada = None
        try:  # já lê o que foi feito nas noites anteriores (senão refaria tudo toda noite)
            self.carregar()
        except (OSError, ValueError):
            pass

    def carregar(self):
        """Carrega o estado do arquivo JSON."""
        if self.path.exists():
            with open(self.path, "r", encoding="utf-8") as f:
                dados = json.load(f)
                self.feitos = dados.get("feitos", {})
                self.ultima_rodada = datetime.fromisoformat(dados.get("ultima_rodada")) if dados.get("ultima_rodada") else None

    def salvar(self):
        """Salva o estado no arquivo JSON."""
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({
                "feitos": self.feitos,
                "ultima_rodada": self.ultima_rodada.isoformat() if self.ultima_rodada else None
            }, f, indent=2, ensure_ascii=False)

    def marcar(self, game_id: str, quando: datetime):
        """Marca um jogo como já pré-compilado."""
        self.feitos[game_id] = quando.isoformat()
        self.ultima_rodada = quando


def rodada(launch_map, estado: Estado, ultimas, abrir, agora: datetime, na_tomada: bool, jogo_aberto: callable,
           maximo: int = 5, segundos: int = 60, log=print) -> list[str]:
    """Executa uma rodada de pré-compilação de shaders."""
    if not pode_rodar(agora, na_tomada, jogo_aberto()):
        return []

    processados = []
    pendentes_ids = pendentes(launch_map, estado.feitos, ultimas)
    
    for game_id in pendentes_ids[:maximo]:
        if jogo_aberto():
            log("Usuário abriu jogo, parando pré-compilação.")
            break

        sucesso = abrir(game_id, segundos)
        estado.marcar(game_id, agora)
        estado.salvar()
        processados.append(game_id)
        titulo = launch_map[game_id].get('title', game_id)
        log(f"Pré-compilado: {titulo}" if sucesso else f"Não abriu (fica marcado para não repetir): {titulo}")

    return processados
