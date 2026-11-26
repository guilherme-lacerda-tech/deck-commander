"""Busca de releases no Prowlarr configurado pelo proprietário."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path


class BuscaErro(RuntimeError):
    pass


def configuracao(paths):
    arquivo = paths.config / "prowlarr.json"
    try:
        cfg = json.loads(arquivo.read_text("utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise BuscaErro("configuração do Prowlarr ilegível") from exc
    endereco = str(cfg.get("url", "")).rstrip("/")
    chave = str(cfg.get("api_key", ""))
    u = urllib.parse.urlsplit(endereco)
    if u.scheme not in ("http", "https") or not u.hostname or u.username or u.password or not chave:
        raise BuscaErro("configuração do Prowlarr incompleta")
    return endereco, chave


def pesquisar(paths, titulo: str, abrir=None) -> list[dict] | None:
    """Lista resultados com magnet; None significa fonte não configurada."""
    cfg = configuracao(paths)
    if cfg is None:
        return None
    endereco, chave = cfg
    query = urllib.parse.urlencode({"query": titulo, "type": "search"})
    req = urllib.request.Request(endereco + "/api/v1/search?" + query,
                                 headers={"X-Api-Key": chave, "Accept": "application/json"})
    try:
        with (abrir or urllib.request.urlopen)(req, timeout=30) as resp:
            dados = json.loads(resp.read(4 * 1024 * 1024 + 1))
    except (OSError, ValueError) as exc:
        raise BuscaErro("não consegui consultar o Prowlarr") from exc
    if not isinstance(dados, list):
        raise BuscaErro("resposta inválida do Prowlarr")
    saida = []
    for item in dados[:1000]:
        if not isinstance(item, dict):
            continue
        magnet = item.get("magnetUrl") or ""
        nome = item.get("title") or ""
        if isinstance(magnet, str) and magnet.startswith("magnet:?") and isinstance(nome, str) and nome:
            saida.append({"titulo": nome[:300], "magnet": magnet, "seeders": item.get("seeders") or 0})
    return saida
