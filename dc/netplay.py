import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

PORTA = 55435
VALIDADE = 300


def ip_tailscale(run=subprocess.run) -> str | None:
    """Obtém o IP Tailscale IPv4 ou None se não disponível."""
    # no Steam Deck a Tailscale fica em /opt/tailscale (fora do PATH) — falha real no teste de 11/11
    for exe in ("tailscale", "/opt/tailscale/tailscale"):
        try:
            result = run([exe, "ip", "-4"], capture_output=True, text=True, timeout=10)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
        match = re.search(r"\d+\.\d+\.\d+\.\d+", result.stdout or "") if result.returncode == 0 else None
        if match:
            return match.group()
    try:  # último recurso: o endereço da interface tailscale0
        r = run(["ip", "-4", "addr", "show", "tailscale0"], capture_output=True, text=True, timeout=10)
        m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", r.stdout or "")
        return m.group(1) if m else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def pedir(estado: Path, game_id: str, papel: str, ip: str | None = None, agora: float | None = None) -> None:
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


def argumentos(estado: Path, game_id: str, agora: float | None = None) -> list[str]:
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


def aplicar_no_comando(cmd: list[str], extra: list[str]) -> list[str]:
    """Insere argumentos extras antes do arquivo de ROM em comandos RetroArch."""
    retroarch = any("org.libretro.RetroArch" in c or c.endswith("retroarch") for c in cmd)
    if not retroarch:
        return cmd
    if not extra or not cmd:
        return cmd
    # a ROM é sempre o último item do comando (corrigido: a 1ª versão procurava por extensão e esquecia .nes/.gba…)
    return cmd[:-1] + list(extra) + cmd[-1:]


def convite(estado: Path, de: str, game_id: str, titulo: str, ip: str, agora: float | None = None) -> None:
    """Grava um convite para outro Deck."""
    data = {
        "de": de,
        "game_id": game_id,
        "titulo": titulo,
        "ip": ip,
        "quando": agora or time.time()
    }
    (estado / "netplay-convite.json").write_text(json.dumps(data))


def convite_pendente(estado: Path, agora: float | None = None) -> dict[str, Any] | None:
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


def aceitar(estado: Path) -> dict[str, Any]:
    """Aceita o convite e inicia como cliente."""
    conv = convite_pendente(estado)
    if not conv:
        raise ValueError("nenhum convite")
    pedir(estado, conv["game_id"], "cliente", ip=conv["ip"])
    (estado / "netplay-convite.json").unlink(missing_ok=True)
    return conv


def comando_convidar_remoto(alvo: str, chave: str, de: str, game_id: str, titulo: str, ip: str) -> list[str]:
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


def main(argv: list[str]) -> None:
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
