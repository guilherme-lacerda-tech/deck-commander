import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

EXT_JOGO = (
    ".nsp", ".xci", ".nsz", ".xcz", ".iso", ".chd", ".cso", ".rvz",
    ".wbfs", ".wua", ".wux", ".rpx", ".3ds", ".cia", ".nds", ".gba",
    ".gbc", ".gb", ".sfc", ".smc", ".nes", ".n64", ".z64", ".v64",
    ".pbp", ".cue", ".img", ".ccd", ".mds", ".mdf", ".7z", ".zip",
    ".rar", ".pkg", ".xex", ".god"
)

def montar_catalogo(launch_map: dict[str, dict], ingeridos: dict[str, dict], magnets: dict[str, str], pacotes: dict[str, list[str]]) -> list[dict]:
    """Monta catálogo de jogos com base em dados de launch map, ingeridos, magnets e pacotes."""
    resultado = []
    
    for gid, info in launch_map.items():
        if info.get("removed") or info.get("console") == "pc":
            continue
            
        rom_path = Path(info["rom"])
        hash_torrent = None
        magnet_link = None
        
        # Torrent do jogo: o arquivo exato, ou outro arquivo na MESMA pasta própria do jogo. Jogo solto na pasta do
        # console (ex.: roms/gba/x.gba) só vale pelo arquivo exato (senão casaria com outro jogo da mesma pasta).
        pasta = rom_path.parent
        pasta_propria = pasta.name.lower() not in ((info.get("console") or "").lower(), "roms")
        for hash_val, dados in ingeridos.items():
            arqs = [str(f) for f in dados.get("files", [])]
            if str(rom_path) in arqs or (pasta_propria and any(Path(f).parent == pasta for f in arqs)):
                hash_torrent = hash_val
                magnet_link = magnets.get(hash_val)
                break
        
        pacote = pacotes.get(gid, [])
        
        # Só inclui se tem magnet ou pacote
        if magnet_link or pacote:
            item = {
                "gid": gid,
                "titulo": info["title"],
                "console": info["console"],
                "hash": hash_torrent,
                "magnet": magnet_link,
                "pacote": pacote,
                "tem_traducao": bool(pacote)
            }
            resultado.append(item)
    
    return sorted(resultado, key=lambda x: x["titulo"].casefold())

def filtrar_pacote(arquivos: list[str]) -> tuple[list[str], list[str]]:
    """Filtra arquivos de pacote, separando permitidos e recusados."""
    permitidos = []
    recusados = []
    
    for caminho in arquivos:
        try:
            # Verifica tamanho
            if os.path.getsize(caminho) > 300 * 1024 * 1024:  # 300 MB
                recusados.append(caminho)
                continue
                
            p = Path(caminho)
            
            # Verifica extensão
            if p.suffix.lower() in EXT_JOGO or p.name == "main" or "exefs" in p.parts:
                recusados.append(caminho)
                continue
                
            permitidos.append(caminho)
        except (OSError, FileNotFoundError):
            recusados.append(caminho)
    
    return permitidos, recusados

def ssh_base(alvo: str, chave: str) -> list[str]:
    """Monta comando base SSH."""
    return ["ssh", "-i", chave, "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", alvo]

def par_online(alvo: str, chave: str, run: Any = subprocess.run) -> bool:
    """Verifica se o par está online via SSH."""
    cmd = ssh_base(alvo, chave) + ["echo", "ok"]
    try:
        result = run(cmd, capture_output=True, text=True, timeout=12)
        return result.returncode == 0 and "ok" in result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False

def rsync_cmd(arquivos: list[str], alvo: str, chave: str, destino: str) -> list[str]:
    """Monta comando rsync para enviar arquivos."""
    permitidos, _ = filtrar_pacote(arquivos)
    
    if not permitidos:
        return []
        
    cmd = ["rsync", "-a", "--partial", "--protect-args", "-e"]
    cmd.append("ssh -i " + chave + " -o BatchMode=yes -o ConnectTimeout=8")
    
    # Adiciona caminhos relativos
    for caminho in permitidos:
        rel_path = os.path.relpath(caminho, "/home/deck/")
        cmd.append("/home/deck/./" + rel_path)
        
    cmd.append(alvo + ":" + destino)
    return cmd

def registrar_pedido(estado: Path, item: dict[str, Any], de: str) -> dict[str, Any]:
    """Registra um novo pedido no arquivo de estado."""
    try:
        with open(estado, "r") as f:
            pedidos = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        pedidos = []
        
    # Verifica se já existe um pedido igual com status "baixando"
    for p in pedidos:
        if p.get("gid") == item["gid"] and p.get("status") == "baixando":
            return p
            
    novo_pedido = {
        "gid": item["gid"],
        "titulo": item["titulo"],
        "console": item["console"],
        "hash": item["hash"],
        "magnet": item["magnet"],
        "de": de,
        "status": "baixando",
        "pedido": datetime.now().isoformat()
    }
    
    pedidos.append(novo_pedido)
    
    with open(estado, "w") as f:
        json.dump(pedidos, f, indent=2)
        
    return novo_pedido

def pedidos(estado: Path) -> list[dict[str, Any]]:
    """Retorna todos os pedidos do arquivo de estado."""
    try:
        with open(estado, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def marcar(estado: Path, gid: str, status: str, nota: str = "") -> None:
    """Marca o status de um pedido."""
    try:
        with open(estado, "r") as f:
            pedidos = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return
        
    for p in pedidos:
        if p.get("gid") == gid:
            p["status"] = status
            if nota:
                p["nota"] = nota
            break
            
    with open(estado, "w") as f:
        json.dump(pedidos, f, indent=2)

def aplicar_pacote(pasta_pacote: Path, home: Path) -> list[str]:
    """Aplica pacote de tradução copiando arquivos para o destino."""
    gravados = []
    
    for arquivo_origem in pasta_pacote.rglob("*"):
        if not arquivo_origem.is_file():
            continue
            
        rel_path = arquivo_origem.relative_to(pasta_pacote)
        destino = home / rel_path
        
        # Filtra arquivos
        if not arquivo_origem.name.endswith(".antes-familia"):
            permitidos, _ = filtrar_pacote([str(arquivo_origem)])
            if not permitidos:
                continue
                
        # Cria diretórios se necessário
        destino.parent.mkdir(parents=True, exist_ok=True)
        
        # Verifica se já existe e faz backup
        if destino.exists():
            if destino.is_file():
                # Compara conteúdo (simplesmente verifica se é diferente)
                try:
                    import filecmp  # compara por pedaços (não carrega os dois arquivos inteiros na memória)
                    if not filecmp.cmp(arquivo_origem, destino, shallow=False):
                        backup = destino.with_suffix(destino.suffix + ".antes-familia")
                        shutil.copy2(destino, backup)
                except OSError:
                    pass  # Ignora erro de comparação
            else:
                # Se não for arquivo, não faz nada
                continue
        
        # Copia o arquivo
        shutil.copy2(arquivo_origem, destino)
        gravados.append(str(destino))
        
    return gravados
