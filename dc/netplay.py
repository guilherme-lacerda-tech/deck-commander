import json
import re
import subprocess
import time
from pathlib import Path
from typing import List, Dict, Optional, Any

PORTA = 55435
VALIDADE = 300


def ip_tailscale(run=subprocess.run) -> Optional[str]:
    """Obtém o IP Tailscale IPv4 ou None se não disponível."""
    try:
        result = run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            match = re.search(r"\d+\.\d+\.\d+\.\d+", result.stdout)
            return match.group() if match else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def pedir(estado: Path, game_id: str, papel: str, ip: Optional[str] = None, agora: Optional[float] = None) -> None:
    """Grava um pedido de netplay."""
    if papel == "cliente" and not ip:
        raise ValueError("Cliente precisa de IP")
    data = {
        "game_id": game_id,
        "papel": papel,
        "ip": ip,
        "quando": agora or time.time()
    }
    (estado / "netplay-pedido.json").write_text(json.dumps(data))


def argumentos(estado: Path, game_id: str, agora: Optional[float] = None) -> List[str]:
    """Lê o pedido de netplay e retorna os argumentos para RetroArch."""
    arquivo = estado / "netplay-pedido.json"
    if not arquivo.exists():
        return []
    try:
        with open(arquivo, "r") as f:
            dados = json.load(f)
    except (json.JSONDecodeError, OSError):
        arquivo.unlink(missing_ok=True)
        return []
    if dados.get("game_id") != game_id:
        return []
    if agora is None:
        agora = time.time()
    if agora - dados["quando"] >= VALIDADE:
        arquivo.unlink(missing_ok=True)
        return []
    arquivo.unlink(missing_ok=True)
    papel = dados["papel"]
    if papel == "host":
        return ["--host", "--port", str(PORTA)]
    elif papel == "cliente" and dados.get("ip"):
        return ["--connect", dados["ip"], "--port", str(PORTA)]
    return []


def aplicar_no_comando(cmd: List[str], extra: List[str]) -> List[str]:
    """Insere argumentos extras antes do arquivo de ROM em comandos RetroArch."""
    retroarch = any("org.libretro.RetroArch" in c or c.endswith("retroarch") for c in cmd)
    if not retroarch:
        return cmd
    novo_cmd = cmd.copy()
    idx_rom = -1
    for i, c in enumerate(cmd):
        if c.endswith((".sfc", ".iso", ".bin")):
            idx_rom = i
            break
    if idx_rom >= 0:
        novo_cmd.insert(idx_rom, *extra)
    return novo_cmd


def convite(estado: Path, de: str, game_id: str, titulo: str, ip: str, agora: Optional[float] = None) -> None:
    """Grava um convite para outro Deck."""
    data = {
        "de": de,
        "game_id": game_id,
        "titulo": titulo,
        "ip": ip,
        "quando": agora or time.time()
    }
    (estado / "netplay-convite.json").write_text(json.dumps(data))


def convite_pendente(estado: Path, agora: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """Lê o convite pendente ou None se vencido."""
    arquivo = estado / "netplay-convite.json"
    if not arquivo.exists():
        return None
    try:
        with open(arquivo, "r") as f:
            dados = json.load(f)
    except (json.JSONDecodeError, OSError):
        arquivo.unlink(missing_ok=True)
        return None
    if agora is None:
        agora = time.time()
    if agora - dados["quando"] >= VALIDADE:
        arquivo.unlink(missing_ok=True)
        return None
    return dados


def aceitar(estado: Path) -> Dict[str, Any]:
    """Aceita o convite e inicia como cliente."""
    conv = convite_pendente(estado)
    if not conv:
        raise ValueError("nenhum convite")
    pedir(estado, conv["game_id"], "cliente", ip=conv["ip"])
    (estado / "netplay-convite.json").unlink(missing_ok=True)
    return conv


def comando_convidar_remoto(alvo: str, chave: str, de: str, game_id: str, titulo: str, ip: str) -> List[str]:
    """Gera o comando SSH para enviar um convite ao Deck remoto."""
    import shlex
    dados = {
        "de": de,
        "game_id": game_id,
        "titulo": titulo,
        "ip": ip
    }
    cmd = [
        "ssh", "-i", chave, "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
        alvo,
        f"cd ~/deck-commander && python3 -m dc.netplay receber {shlex.quote(json.dumps(dados))}"
    ]
    return cmd


def main(argv: List[str]) -> None:
    """Subcomando 'receber' para processar convites recebidos via SSH."""
    if len(argv) < 2 or argv[1] != "receber":
        raise SystemExit("Uso: dc.netplay receber <json>")
    dados = json.loads(argv[2])
    estado = Path.home() / ".local/state/deck-commander"
    convite(
        estado=estado,
        de=dados["de"],
        game_id=dados["game_id"],
        titulo=dados["titulo"],
        ip=dados["ip"]
    )
    print("ok")
