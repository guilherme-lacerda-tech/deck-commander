"""Qual motor (engine) o jogo de Switch usa, olhando só a lista de arquivos do RomFS — para o bot dizer
COM QUE o jogo foi feito e qual é o caminho para traduzir, em vez de só "formato fechado".

VERSAO sobe sempre que o Deck Commander aprende um formato novo. Jogo marcado "fechado" ou que "falhou"
numa versão anterior volta a ser tentado sozinho (nada fica impossível para sempre).
"""
from __future__ import annotations

from pathlib import PurePosixPath

# 1: MSBT  2: Pokémon (trinity), LM3, GBA  3: SARC aninhado (BotW) + Unreal (.locres)
VERSAO = 3

# (nome, teste, já traduzo?, caminho)
_MOTORES = [
    ("Nintendo (MSBT)", lambda n, e: ".msbt" in e or any(x.endswith(".ssarc") or "/bootup_" in x for x in n), True,
     "tradutor padrão"),
    ("Unreal Engine", lambda n, e: any("/content/paks/" in x for x in n) and (".pak" in e or ".utoc" in e), True,
     "lê o .locres do .pak; se o pak for criptografado, a chave AES fica no executável do jogo e pode ser "
     "achada testando os blocos dele contra o índice do pak (ainda não automático)"),
    ("Unity", lambda n, e: any(x.endswith(("globalgamemanagers", "data.unity3d")) or "/streamingassets/" in x
                               for x in n) or ".assets" in e, False,
     "textos em .assets/AssetBundle (tabelas I2 Localization ou TextAsset); precisa de leitor do formato "
     "serializado da Unity e, às vezes, refazer o atlas da fonte (TextMeshPro) com ã/õ — esforço médio/grande"),
    ("RE Engine (Capcom)", lambda n, e: any(".msg." in x for x in n) or any(x.startswith("natives/") for x in n),
     False, "arquivos .msg documentados pela comunidade; tradutor dedicado — esforço médio"),
    ("CRI Middleware (CPK)", lambda n, e: ".cpk" in e, False,
     "pacote .cpk é aberto (CRILAYLA é documentado); o texto dentro é formato de cada jogo — por jogo"),
    ("Godot", lambda n, e: ".pck" in e, False, "pacote .pck + traduções .translation/.csv — esforço médio"),
    ("GameMaker", lambda n, e: any(x.endswith("game.droid") or x.endswith("data.win") for x in n), False,
     "textos dentro do data.win/game.droid (formato documentado) — esforço médio"),
    ("RPG Maker", lambda n, e: any("/www/data/" in x or x.endswith(".rvdata2") for x in n), False,
     "JSON/rvdata com os textos — esforço pequeno/médio"),
]


def identify(paths: list[str]) -> dict:
    """{'motor', 'traduzo', 'caminho'} a partir dos caminhos do RomFS."""
    n = [p.lower() for p in paths]
    e = {PurePosixPath(p).suffix for p in n}
    for nome, test, ok, caminho in _MOTORES:
        if test(n, e):
            return {"motor": nome, "traduzo": ok, "caminho": caminho}
    top = sorted({PurePosixPath(p).suffix for p in n if PurePosixPath(p).suffix}, key=lambda s: -sum(
        x.endswith(s) for x in n))[:5]
    return {"motor": "desconhecido", "traduzo": False,
            "caminho": "formato próprio (extensões mais comuns: " + ", ".join(top or ["nenhuma"]) +
                       "); dá para estudar com a tradução fora do padrão ou engenharia reversa"}


def stale(entry: dict) -> bool:
    """Marca/falha feita por uma versão mais antiga do Deck Commander: vale tentar de novo."""
    return int(entry.get("motor_versao", 0) or 0) < VERSAO
