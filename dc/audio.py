"""Áudio do Deck: volume do jogo × música (PipeWire/pactl) e controle do Spotify/outro player (MPRIS pelo busctl).

Escrito pela IA local (qwen3-coder) e revisado.
"""
import json
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Optional, Any

def run(args: List[str], **kwargs) -> subprocess.CompletedProcess:
    """Executa comando com timeout e captura de saída."""
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)
    kwargs.setdefault("timeout", 5)
    try:
        return subprocess.run(args, **kwargs)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return subprocess.CompletedProcess(args, 1, "", "")

def fluxos(run=run) -> List[Dict]:
    """Retorna lista de fluxos com tipo, nome, volume e mudo."""
    result = run(["pactl", "-f", "json", "list", "sink-inputs"])
    if result.returncode != 0:
        return []
    
    try:
        inputs = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    fluxos_list = []
    for inp in inputs:
        app_name = inp.get("properties", {}).get("application.name", "")
        binary = inp.get("properties", {}).get("application.process.binary", "")
        nome = app_name or binary
        chave = f"{app_name} {binary}".lower()

        if "spotify" in chave:
            tipo = "musica"
        elif app_name == "Steam" or any(x in chave for x in ("steamwebhelper", "speech-dispatcher")):
            tipo = "sistema"
        else:
            tipo = "jogo"

        # pactl -f json: "volume" = {"front-left": {"value_percent": "65%", ...}, "front-right": {...}}
        canais = [c for c in (inp.get("volume") or {}).values() if isinstance(c, dict)]
        volume_percent = int(sum(float(str(c.get("value_percent", "0%")).rstrip("%")) for c in canais) / len(canais)) \
            if canais else 0

        fluxos_list.append({
            "index": inp["index"],
            "nome": nome,
            "tipo": tipo,
            "volume": volume_percent,
            "mudo": inp.get("mute", False)
        })

    return fluxos_list

def definir_volume(tipo: str, pct: int, run=run) -> int:
    """Define volume para todos os fluxos do tipo especificado."""
    pct = max(0, min(150, pct))
    fluxos_list = fluxos(run)
    indices = [f["index"] for f in fluxos_list if f["tipo"] == tipo]
    
    count = 0
    for index in indices:
        result = run(["pactl", "set-sink-input-volume", str(index), f"{pct}%"])
        if result.returncode == 0:
            count += 1
    
    return count

def achar_player_spotify(run=run) -> Optional[str]:
    """Acha o nome do player MPRIS do Spotify."""
    result = run(["busctl", "--user", "list", "--no-pager"])
    if result.returncode != 0:
        return None

    lines = result.stdout.strip().split("\n")
    players = [line.split()[0] for line in lines if line.startswith("org.mpris.MediaPlayer2.")]
    
    spotify_player = next((p for p in players if "spotify" in p.lower()), None)
    if spotify_player:
        return spotify_player
    
    return players[0] if players else None

def tocando(run=run) -> Optional[Dict]:
    """Retorna informações do player MPRIS atual."""
    player = achar_player_spotify(run)
    if not player:
        return None

    result = run([
        "busctl", "--user", "--json=short", "get-property",
        player, "/org/mpris/MediaPlayer2",
        "org.mpris.MediaPlayer2.Player", "Metadata"
    ])
    if result.returncode != 0:
        return None

    try:
        metadata = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None

    status_result = run([
        "busctl", "--user", "--json=short", "get-property",
        player, "/org/mpris/MediaPlayer2",
        "org.mpris.MediaPlayer2.Player", "PlaybackStatus"
    ])
    if status_result.returncode != 0:
        return None

    try:
        status = json.loads(status_result.stdout)
        estado = status["data"]
    except (json.JSONDecodeError, KeyError):
        estado = ""

    titulo = metadata.get("data", {}).get("xesam:title", {}).get("data", "")
    artistas = metadata.get("data", {}).get("xesam:artist", {}).get("data", [])
    artista = ", ".join(artistas) if isinstance(artistas, list) else str(artistas)

    return {
        "player": player,
        "titulo": titulo,
        "artista": artista,
        "estado": estado
    }

def midia(acao: str, run=run) -> bool:
    """Envia comando MPRIS para o player."""
    player = achar_player_spotify(run)
    if not player:
        return False

    metodos = {
        "tocar_pausar": "PlayPause",
        "proxima": "Next",
        "anterior": "Previous",
        "tocar": "Play",
        "pausar": "Pause"
    }

    metodo = metodos.get(acao)
    if not metodo:
        return False

    result = run([
        "busctl", "--user", "call", player,
        "/org/mpris/MediaPlayer2",
        "org.mpris.MediaPlayer2.Player",
        metodo
    ])
    return result.returncode == 0

def abrir(uri: str, run=run) -> bool:
    """Abre URI no player MPRIS."""
    player = achar_player_spotify(run)
    if not player:
        return False

    result = run([
        "busctl", "--user", "call", player,
        "/org/mpris/MediaPlayer2",
        "org.mpris.MediaPlayer2.Player",
        "OpenUri", "s", uri
    ])
    return result.returncode == 0

def playlists(cfg_path: Path) -> List[Dict]:
    """Lê lista de playlists do arquivo JSON."""
    if not cfg_path.exists():
        return []
    
    try:
        with open(cfg_path, "r") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []

def salvar_playlists(cfg_path: Path, lista: List[Dict]) -> None:
    """Salva lista de playlists no arquivo JSON."""
    try:
        with open(cfg_path, "w") as f:
            json.dump(lista, f, indent=2)
    except OSError:
        pass

def abrir_spotify(run=run) -> bool:
    """Inicia Spotify se não estiver rodando."""
    if achar_player_spotify(run):
        return True

    try:
        subprocess.Popen(
            ["flatpak", "run", "com.spotify.Client"],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return True
    except (FileNotFoundError, OSError):
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)

    comando = sys.argv[1]
    
    if comando == "fluxos":
        print(json.dumps(fluxos()))
    elif comando == "volume":
        if len(sys.argv) != 4:
            sys.exit(1)
        tipo = sys.argv[2]
        pct = int(sys.argv[3])
        print(definir_volume(tipo, pct))
    elif comando == "tocando":
        result = tocando()
        print(json.dumps(result) if result else "null")
    elif comando in ["tocar_pausar", "proxima", "anterior", "tocar", "pausar"]:
        print(json.dumps(midia(comando)))
    elif comando == "abrir":
        if len(sys.argv) != 3:
            sys.exit(1)
        uri = sys.argv[2]
        print(json.dumps(abrir(uri)))
    else:
        sys.exit(1)


def atalho_spotify(paths) -> str:
    """Põe o Spotify na biblioteca do Steam (para entrar na conta e abrir no modo de jogo, sem o modo Desktop)."""
    from . import plugin_bridge
    bin_dir = paths.data / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    sh = bin_dir / "spotify.sh"
    sh.write_text("#!/bin/sh\n# aberto pelo atalho \"Spotify\" do Deck Commander (o argumento é o id do atalho)\n"
                  "exec /usr/bin/flatpak run com.spotify.Client\n", "utf-8")
    sh.chmod(0o755)
    n = plugin_bridge.enqueue(paths, [{"LaunchOptions": "app-spotify", "AppName": "Spotify", "exe": str(sh),
                                       "StartDir": str(bin_dir)}])
    return "Spotify vai aparecer na biblioteca em ~10 s." if n else "O Spotify já está na biblioteca."
