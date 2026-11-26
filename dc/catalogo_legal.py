"""Descoberta de fontes legais para pedidos feitos pelo nome do jogo.

Este módulo nunca procura torrents nem tenta obter ROMs comerciais.  Ele só monta
links de busca em lojas oficiais para PC/console atual.  Para consoles que
dependem de emulação, o Commander explica o caminho seguro: dump próprio,
homebrew ou um arquivo/link para o qual o proprietário tenha autorização.
"""
from __future__ import annotations

from urllib.parse import quote_plus


ATUAIS = {"pc", "switch", "switch2", "ps3", "x360"}


def _q(titulo: str) -> str:
    return quote_plus(" ".join((titulo or "").split()))


def pesquisar(titulo: str, console: str, rotulo: str) -> str:
    """Retorna instruções e URLs de descoberta legais, sem acessar a rede."""
    nome, query = " ".join((titulo or "").split()), _q(titulo)
    if not nome:
        return "Diga o nome do jogo primeiro."
    if console == "pc":
        return (f"🔎 Fontes legais para «{nome}» no PC:\n"
                f"• Steam: https://store.steampowered.com/search/?term={query}\n"
                f"• GOG: https://www.gog.com/en/games?query={query}\n"
                f"• itch.io: https://itch.io/search?q={query}\n\n"
                "Se você comprar ou já possuir o jogo, o Commander pode catalogá-lo/"
                "transmiti-lo pelo PC; não baixa cópias não autorizadas.")
    if console == "switch":
        return (f"🔎 Procure «{nome}» na Nintendo eShop oficial: \n"
                f"https://www.nintendo.com/us/search/#q={query}\n\n"
                "Para emulação, use somente um dump feito da sua própria mídia/conta "
                "ou homebrew autorizado; depois envie o arquivo para importação.")
    if console in {"ps3", "x360"}:
        loja = "PlayStation Store" if console == "ps3" else "Microsoft Store / Xbox"
        dominio = "store.playstation.com" if console == "ps3" else "xbox.com"
        return (f"🔎 «{nome}» — consulte {loja} oficial:\n"
                f"https://www.google.com/search?q=site%3A{dominio}+{query}\n\n"
                "O Commander não procura ROMs comerciais. Para emulação, importe apenas "
                "um dump próprio ou conteúdo autorizado.")
    return (f"🔎 «{nome}» em {rotulo}: não há uma loja oficial de ROMs que o Commander "
            "possa baixar automaticamente. Use homebrew, um dump da sua própria mídia ou "
            "um arquivo/link para o qual você tenha autorização; então o Commander valida, "
            "cataloga e prepara a biblioteca.")
