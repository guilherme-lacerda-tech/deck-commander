"""Ports nativos e outros jogos não-Steam na aba do console (pedido 15/11/2026: "um jogo dele não foi detectado por ser
um port nativo que a comunidade fez de um jogo, que deveria estar lá").

Port nativo = jogo que a comunidade transformou em programa de PC (não é ROM). Ele entra na Steam como "jogo
não-Steam" (o próprio port, o Lutris, o EmuDeck…) e o Deck Commander não sabia de qual console ele é. Aqui você diz:
o atalho X vai para a aba do console Y — e ele aparece junto dos jogos daquele console.

    python3 -m dc.ports                          -> lista os jogos não-Steam e a aba de cada um
    python3 -m dc.ports marcar "<nome>" switch   -> põe na aba do Switch (console vazio tira)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _arq(paths) -> Path:
    return paths.data / "ports.json"


def carregar(paths) -> dict[str, str]:
    try:
        return json.loads(_arq(paths).read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def _do_proprio_dc(r: dict) -> bool:
    exe = (r.get("exe") or r.get("Exe") or "").lower()
    return "dc-launch" in exe or "unifideck" in exe


def candidatos(shortcuts: list[dict], paths) -> list[dict]:
    """Jogos não-Steam que não são do Deck Commander nem das lojas (Epic/GOG): o usuário escolhe a aba."""
    marcados = carregar(paths)
    vistos, out = set(), []
    for r in shortcuts:
        nome = r.get("AppName") or r.get("appname") or ""
        if not nome or _do_proprio_dc(r) or nome.casefold() in vistos:
            continue
        vistos.add(nome.casefold())
        out.append({"nome": nome, "console": marcados.get(nome, "")})
    return sorted(out, key=lambda x: x["nome"].casefold())


def marcar(paths, nome: str, console: str) -> str:
    from .emulators import CONSOLES
    if console and console not in CONSOLES:
        raise ValueError(f"console desconhecido: {console}")
    m = carregar(paths)
    if console:
        m[nome] = console
    else:
        m.pop(nome, None)
    _arq(paths).parent.mkdir(parents=True, exist_ok=True)
    _arq(paths).write_text(json.dumps(m, indent=1, ensure_ascii=False), "utf-8")
    if not console:
        return f"{nome} saiu da aba de console."
    return f"{nome} vai aparecer na aba {CONSOLES[console]['label']} (em alguns segundos)."


def main(argv: list[str]) -> int:
    from . import syncer, vdf
    from .paths import get_paths
    paths = get_paths().ensure()
    if argv[:1] == ["marcar"] and len(argv) in (2, 3):
        print(marcar(paths, argv[1], argv[2] if len(argv) == 3 else ""))
    elif not argv:
        for c in candidatos(vdf.read_shortcuts(syncer.shortcuts_path()), paths):
            print(f"{c['nome']}  ->  {c['console'] or '(sem aba de console)'}")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
