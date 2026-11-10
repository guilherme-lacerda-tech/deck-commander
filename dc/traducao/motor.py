"""Qual motor (engine) o jogo de Switch usa, olhando só a lista de arquivos do RomFS — para o bot dizer
COM QUE o jogo foi feito e qual é o caminho para traduzir, em vez de só "formato fechado".

VERSAO sobe sempre que o Deck Commander aprende um formato novo. Jogo marcado "fechado" ou que "falhou"
numa versão anterior volta a ser tentado sozinho (nada fica impossível para sempre).
"""
from __future__ import annotations

from pathlib import PurePosixPath

# 1: MSBT  2: Pokémon (trinity), LM3, GBA  3: SARC aninhado (BotW) + Unreal (.locres)
# 4: adaptadores por motor (Unity, GameMaker, Godot, RE Engine, RPG Maker, CRI) — perguntam antes no Telegram
VERSAO = 4

# (nome, teste, já traduzo?, caminho)
_MOTORES = [
    ("Nintendo (MSBT)", lambda n, e: ".msbt" in e or any(x.endswith(".ssarc") or "/bootup_" in x for x in n), True,
     "tradutor padrão"),
    ("Unreal Engine", lambda n, e: any("/content/paks/" in x for x in n) and (".pak" in e or ".utoc" in e), True,
     "lê o .locres do .pak e instala um pak de mod; pacote criptografado: não traduzo (seria preciso quebrar a "
     "proteção do jogo)"),
    ("Unity", lambda n, e: any(x.endswith(("globalgamemanagers", "data.unity3d")) or "/streamingassets/" in x
                               for x in n) or ".assets" in e, True,
     "TextAsset (csv/json/xml/ink/yarn) e I2 Localization com typetree; pergunta antes (Sim/Não + tempo)"),
    ("RE Engine (Capcom)", lambda n, e: any(".msg." in x for x in n) or any(x.startswith("natives/") for x in n),
     True,
     ".msg (v12–23) solto ou em .pak (sem zstd/criptografia); pergunta antes"),
    ("CRI Middleware (CPK)", lambda n, e: ".cpk" in e, True,
     "abre o .cpk (CRILAYLA) e traduz os arquivos de texto de dentro; formato binário próprio do jogo fica de fora"),
    ("Godot", lambda n, e: ".pck" in e, True,
     ".pck (Godot 3/4) com csv/json/cenas/.translation; tradução comprimida (Optimized) ainda não"),
    ("GameMaker", lambda n, e: any(x.endswith("game.droid") or x.endswith("data.win") for x in n), True,
     "tabela STRG do data.win + arquivos de idioma ao lado; jogo YYC tem texto no executável"),
    ("RPG Maker", lambda n, e: any("/www/data/" in x or x.endswith(".rvdata2") for x in n), True,
     "JSON do MV/MZ (diálogos, escolhas, banco de dados); VX Ace (.rvdata2) ainda não"),
]


# motores com adaptador: o rótulo só vale se o adaptador também reconhece o jogo (ex.: ".pck" também é pacote
# de áudio Wwise — Luigi's Mansion 3 e Pokémon Z-A não são Godot)
_ADAPTADOR = {"Unity": "eng_unity", "RE Engine (Capcom)": "eng_re", "CRI Middleware (CPK)": "eng_cri",
              "Godot": "eng_godot", "GameMaker": "eng_gamemaker", "RPG Maker": "eng_rpgmaker"}


def _adapter_agrees(nome: str, paths: list[str]) -> bool:
    mod = _ADAPTADOR.get(nome)
    if not mod:
        return True
    import importlib
    try:
        return bool(importlib.import_module(f".{mod}", __package__).detect(list(paths)))
    except Exception:  # noqa: BLE001 - detector com defeito: fica com o teste simples
        return True


def identify(paths: list[str]) -> dict:
    """{'motor', 'traduzo', 'caminho'} a partir dos caminhos do RomFS."""
    n = [p.lower() for p in paths]
    e = {PurePosixPath(p).suffix for p in n}
    for nome, test, ok, caminho in _MOTORES:
        if test(n, e) and _adapter_agrees(nome, paths):
            return {"motor": nome, "traduzo": ok, "caminho": caminho}
    top = sorted({PurePosixPath(p).suffix for p in n if PurePosixPath(p).suffix}, key=lambda s: -sum(
        x.endswith(s) for x in n))[:5]
    return {"motor": "desconhecido", "traduzo": False,
            "caminho": "formato próprio (extensões mais comuns: " + ", ".join(top or ["nenhuma"]) +
                       "); dá para estudar com a tradução fora do padrão ou engenharia reversa"}


def stale(entry: dict) -> bool:
    """Marca/falha feita por uma versão mais antiga do Deck Commander: vale tentar de novo."""
    return int(entry.get("motor_versao", 0) or 0) < VERSAO
