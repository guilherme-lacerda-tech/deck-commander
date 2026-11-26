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


def pesquisar(paths, titulo: str, abrir=None, indexadores=None, timeout=15) -> list[dict] | None:
    """Consulta fontes individualmente quando fornecidas; uma falha não impede as demais."""
    cfg = configuracao(paths)
    if cfg is None:
        return None
    endereco, chave = cfg
    if indexadores is None:
        try:
            dados_cfg = json.loads((paths.config / "prowlarr.json").read_text("utf-8"))
            ids = dados_cfg.get("indexer_ids", [])
            if not isinstance(ids, list) or len(ids) > 10:
                raise ValueError("lista inválida")
            indexadores = [int(i) for i in ids if int(i) > 0]
        except (OSError, ValueError, TypeError) as exc:
            raise BuscaErro("lista de indexadores inválida") from exc
    saida = []
    sucesso = False
    for indice in (indexadores or [None]):
        params = {"query": titulo, "type": "search"}
        if indice is not None:
            params["indexerIds"] = str(int(indice))
        query = urllib.parse.urlencode(params)
        req = urllib.request.Request(endereco + "/api/v1/search?" + query,
                                     headers={"X-Api-Key": chave, "Accept": "application/json"})
        try:
            with (abrir or urllib.request.urlopen)(req, timeout=timeout) as resp:
                dados = json.loads(resp.read(4 * 1024 * 1024 + 1))
            if not isinstance(dados, list):
                continue
            sucesso = True
        except (OSError, ValueError):
            continue
        for item in dados[:1000]:
            if not isinstance(item, dict):
                continue
            magnet, link, nome = item.get("magnetUrl") or "", item.get("downloadUrl") or "", item.get("title") or ""
            # Um link de download é aceito apenas se apontar para o próprio Prowlarr.
            u, origem = urllib.parse.urlsplit(link), urllib.parse.urlsplit(endereco)
            local = u.scheme == origem.scheme and u.netloc == origem.netloc
            if isinstance(nome, str) and nome and ((isinstance(magnet, str) and magnet.startswith("magnet:?")) or local):
                saida.append({"titulo": nome[:300], "magnet": magnet, "download_url": link if local else "",
                              "seeders": item.get("seeders") or 0})
    if not sucesso:
        raise BuscaErro("não consegui consultar o Prowlarr")
    return saida


def baixar_torrent(paths, url: str, abrir=None) -> bytes:
    """Lê torrent através do Prowlarr local, com limite e sem enviar a chave a outro host."""
    cfg = configuracao(paths)
    if cfg is None:
        raise BuscaErro("Prowlarr não configurado")
    base, chave = cfg
    a, b = urllib.parse.urlsplit(base), urllib.parse.urlsplit(url)
    if (a.scheme, a.netloc) != (b.scheme, b.netloc) or b.username or b.password:
        raise BuscaErro("endereço de download fora do Prowlarr")
    req = urllib.request.Request(url, headers={"X-Api-Key": chave})
    class SemRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    try:
        with (abrir or urllib.request.build_opener(SemRedirect()).open)(req, timeout=30) as resp:
            final = urllib.parse.urlsplit(resp.geturl())
            if (a.scheme, a.netloc) != (final.scheme, final.netloc):
                raise BuscaErro("o download redirecionou para outro servidor")
            dados = resp.read(5 * 1024 * 1024 + 1)
    except OSError as exc:
        raise BuscaErro("não consegui baixar o torrent") from exc
    if len(dados) > 5 * 1024 * 1024 or not dados.startswith(b"d"):
        raise BuscaErro("arquivo torrent inválido ou muito grande")
    return dados
