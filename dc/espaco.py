"""Limpeza de disco: jogos grandes que você não joga há tempo (último "lançando" no launch.log).

Escrito pela IA local (qwen3-coder) e revisado.
"""
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path


def ultimas_jogadas(log_path: Path) -> dict[str, datetime]:
    """Retorna mapeamento de game_id para a última vez que foi jogado."""
    if not log_path.exists():
        return {}
    
    # "<data ISO> lançando <game_id>: ..." (o dc-launch grava microssegundos e fuso "+00:00")
    regex = re.compile(r'^(\S+) lançando ([^:\s]+):')
    ultimas = {}
    try:
        with log_path.open('r', encoding='utf-8', errors='replace') as f:
            for linha in f:
                match = regex.match(linha.strip())
                if not match:
                    continue
                try:
                    data = datetime.fromisoformat(match.group(1))
                except ValueError:
                    continue  # linha mal formada: ignora só ela
                game_id = match.group(2)
                ultimas[game_id] = max(ultimas.get(game_id, data), data)
    except OSError:
        pass
    
    return ultimas

def sugestoes(
    launch_map: dict[str, dict],
    ultimas: dict[str, datetime],
    tamanho: Callable[[str], int],
    agora: datetime,
    dias: int = 90,
    min_bytes: int = 2 * 1024**3,
    data_instalacao: Callable[[str], datetime | None] = lambda gid: None
) -> list[dict]:
    """Gera sugestões de jogos para limpar espaço."""
    sugestoes = []
    
    for gid, info in launch_map.items():
        if info.get("removed", False) or info["console"] == "pc":
            continue
            
        ultima_jogada = ultimas.get(gid)
        data_parado = ultima_jogada
        
        if data_parado is None:
            data_parado = data_instalacao(gid)
            nunca_jogado = True
        else:
            nunca_jogado = False
            
        if data_parado is None:
            continue
            
        dias_parado = (agora - data_parado).days
        
        if dias_parado >= dias:
            bytes_ = tamanho(gid)
            if bytes_ >= min_bytes:
                gb = round(bytes_ / 1024**3, 1)
                sugestoes.append({
                    "gid": gid,
                    "titulo": info["title"],
                    "console": info["console"],
                    "bytes": bytes_,
                    "gb": gb,
                    "dias_parado": dias_parado,
                    "nunca_jogado": nunca_jogado
                })
    
    return sorted(sugestoes, key=lambda x: x["bytes"], reverse=True)

def texto(item: dict) -> str:
    """Gera uma frase descritiva em português."""
    dias = item["dias_parado"]
    dias_str = f"{dias} dia" if dias == 1 else f"{dias} dias"
    
    if item["nunca_jogado"]:
        return f"Você instalou {item['titulo']} há {dias_str}, nunca jogou, e ele ocupa {item['gb']} GB."
    else:
        return f"Você não joga {item['titulo']} há {dias_str} e ele ocupa {item['gb']} GB."
