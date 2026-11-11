"""/corrigir com foto: lê a frase da imagem (OCR com o modelo de visão do PC), acha a frase no cache de tradução do
jogo, pede uma versão melhor à IA e troca SÓ ela; depois o mod é refeito a partir do cache (as outras frases não são
traduzidas de novo). Usa o módulo `corrigir` (escrito pela IA local e revisado)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..paths import Paths
from . import corrigir as C

OCR_MODELO = "qwen2.5vl:7b"


def _jogo_alvo(paths: Paths, lm: dict, nome: str) -> str | None:
    """Jogo citado na legenda (/corrigir <jogo>) ou, sem nome, o último aberto pelo Deck Commander."""
    from ..remove import find
    if nome:
        hits = find(lm, nome)
        return hits[0] if len(hits) == 1 else None
    from .. import espaco
    ult = espaco.ultimas_jogadas(paths.logs / "launch.log")
    vivos = {g: t for g, t in ult.items() if g in lm and lm[g].get("console") != "pc"}
    return max(vivos, key=vivos.get) if vivos else None


def caches_do_jogo(paths: Paths, entrada: dict) -> list[Path]:
    """Arquivos de cache de tradução daquele jogo (pelo Title ID do Switch ou pelo nome)."""
    from ..dedup import base_title_id
    cdir = paths.data / "traducao" / "cache"
    if not cdir.exists():
        return []
    rom = Path(entrada.get("rom", ""))
    chaves = [k.lower() for k in (base_title_id(rom.name) or "", entrada.get("title", ""), rom.stem) if k]
    return [f for f in cdir.glob("*.json")
            if not f.name.startswith("medicao") and any(k in f.stem.lower() for k in chaves)]


def corrigir(paths: Paths, cfg: dict, imagem: bytes, legenda: str, lm: dict,
             ocr_fn=None, perguntar_fn=None) -> dict:
    """Devolve {"texto": mensagem, "gid": jogo, "feito": bool}."""
    from . import ia
    pedido = re.sub(r"^/corrigir\S*\s*", "", legenda or "").strip()
    nome, _, orientacao = pedido.partition("|")  # "/corrigir Zelda | o nome certo é Reino Cogumelo"
    gid = _jogo_alvo(paths, lm, nome.strip())
    if not gid:
        return {"texto": "Não sei de qual jogo é. Mande a foto com /corrigir <nome do jogo> na legenda.", "feito": False}
    caches = caches_do_jogo(paths, lm[gid])
    frases: dict[str, str] = {}
    for f in caches:
        try:
            frases.update(json.loads(f.read_text("utf-8")))
        except (OSError, ValueError):
            pass
    if not frases:
        return {"texto": f"{lm[gid]['title']} não tem tradução feita pelo Deck Commander para corrigir.", "feito": False}
    url = (cfg.get("providers", {}).get("ollama_pc", {}) or {}).get("url") or "http://127.0.0.1:11435"
    try:
        texto_img = (ocr_fn or (lambda img: C.ocr(url, cfg.get("ocr_modelo") or OCR_MODELO, img)))(imagem)
    except RuntimeError as e:
        return {"texto": f"Não consegui ler a imagem: {e} (o PC está ligado?)", "feito": False}
    achou = C.parecidas(texto_img, frases)
    if not achou:
        return {"texto": f"Li na imagem: “{texto_img[:200]}”, mas não achei essa frase na tradução de "
                         f"{lm[gid]['title']}. Tente uma foto mais de perto da legenda.", "feito": False}
    chave, nota, antiga = achou[0]
    sistema, usuario = C.pedido_ia(antiga, orientacao.strip())
    if perguntar_fn is None:
        chain = [p for p in ia.build_chain(paths, cfg) if ia._instructable(p)]
        perguntar_fn = lambda s, u: ia._ask(chain, s, u, lambda r: C.marcadores_ok(antiga, C.limpar_resposta(r)))  # noqa: E731
    bruto = perguntar_fn(sistema, usuario)
    nova = C.limpar_resposta(bruto or "")
    if not nova or not C.marcadores_ok(antiga, nova) or nova == antiga:
        return {"texto": f"Achei a frase (“{antiga[:120]}”), mas a IA não deu uma versão melhor que mantivesse os "
                         "códigos do jogo. Mande de novo com uma orientação: /corrigir <jogo> | o que está errado",
                "feito": False}
    C.aplicar(caches, chave, nova)
    return {"texto": f"✏️ {lm[gid]['title']}\nAntes: {C.MARCADOR.sub('…', antiga)}\nDepois: {C.MARCADOR.sub('…', nova)}\n"
                     "Refazendo o mod com a frase nova (só ela muda; o resto vem do cache).",
            "gid": gid, "feito": True}
