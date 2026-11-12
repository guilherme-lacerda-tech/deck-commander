"""Cópia automática dos saves de cada jogo: as 5 últimas versões, guardadas ANTES de o jogo abrir.

    python3 -m dc.copia_saves <game_id>                  -> guarda agora (o dc-launch chama sozinho, em segundo plano)
    python3 -m dc.copia_saves lista <game_id>            -> cópias guardadas (a 1 é a mais nova)
    python3 -m dc.copia_saves voltar <game_id> [n]       -> devolve a cópia n (padrão 1); o estado atual vira cópia antes

Pedido do usuário em 12/11/2026 ("não posso confiar no save rápido?"). Guarda o save do jogo (cartão de memória,
bateria do cartucho) e os saves rápidos, na memória interna (~/Backups/DeckCommander/saves/<jogo>/<data>/). Como a
cópia é feita antes de cada sessão, um save estragado durante o jogo, um emulador que atualizou ou um toque errado no
L4 nunca levam o progresso anterior: ele está na cópia. Só copia quando algo mudou desde a última cópia.
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from .paths import Paths, get_paths

MANTER = 5


def _pasta(paths: Paths, game_id: str) -> Path:
    return paths.backups / "saves" / game_id


def _saves(game_id: str) -> list[dict]:
    """[{origem, destino}] dos saves do jogo (a mesma lista da transferência Deck ↔ PC)."""
    from . import transferir
    man = transferir.preparar(game_id, com_hash=False, so_dados=True)
    return [{"origem": a["origem"], "destino": a["destino"]} for a in man.get("arquivos", [])
            if a.get("categoria") == "save" and Path(a["origem"]).is_file()]


def _assinatura(arqs: list[dict]) -> list:
    out = []
    for a in arqs:
        st = Path(a["origem"]).stat()
        out.append([a["destino"], st.st_size, int(st.st_mtime)])
    return sorted(out)


def copias(paths: Paths, game_id: str) -> list[Path]:
    """Cópias guardadas, a mais nova primeiro."""
    d = _pasta(paths, game_id)
    return sorted((p for p in d.iterdir() if (p / "copia.json").exists()), reverse=True) if d.exists() else []


def guardar(paths: Paths, game_id: str, manter: int = MANTER, listar=_saves) -> Path | None:
    """Guarda uma cópia se os saves mudaram desde a última. Devolve a pasta criada (ou None)."""
    arqs = listar(game_id)
    if not arqs:
        return None
    assin = _assinatura(arqs)
    antigas = copias(paths, game_id)
    if antigas:
        try:
            if json.loads((antigas[0] / "copia.json").read_text("utf-8"))["assinatura"] == assin:
                return None  # nada mudou desde a última cópia
        except (OSError, ValueError, KeyError):
            pass
    nome = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    dest = _pasta(paths, game_id) / nome
    tmp = dest.with_name(nome + ".parcial")
    shutil.rmtree(tmp, ignore_errors=True)
    for a in arqs:
        alvo = tmp / a["destino"].replace("{EMU}", "emulador").lstrip("/")
        alvo.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(a["origem"], alvo)
        a["copia"] = str(alvo.relative_to(tmp))
    (tmp / "copia.json").write_text(json.dumps({"jogo": game_id, "arquivos": arqs, "assinatura": assin},
                                               ensure_ascii=False, indent=1), "utf-8")
    tmp.replace(dest)  # só vira cópia "de verdade" quando está inteira
    for velha in copias(paths, game_id)[manter:]:
        shutil.rmtree(velha, ignore_errors=True)
    return dest


def voltar(paths: Paths, game_id: str, n: int = 1, listar=_saves) -> str:
    """Devolve a cópia n. Antes, o estado atual também vira cópia (voltar nunca perde nada)."""
    lista = copias(paths, game_id)
    if not 1 <= n <= len(lista):
        raise ValueError(f"não há a cópia {n} (há {len(lista)})")
    escolhida = lista[n - 1]  # escolhida antes de guardar o atual, que entra como mais nova
    guardar(paths, game_id, manter=MANTER + 1, listar=listar)
    info = json.loads((escolhida / "copia.json").read_text("utf-8"))
    for a in info["arquivos"]:
        Path(a["origem"]).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(escolhida / a["copia"], a["origem"])
    return f"{len(info['arquivos'])} arquivo(s) de save voltaram para a cópia de {escolhida.name} (UTC)"


def main(argv: list[str]) -> int:
    paths = get_paths()
    if len(argv) >= 2 and argv[0] == "lista":
        for i, c in enumerate(copias(paths, argv[1]), 1):
            print(i, c.name)
        return 0
    if len(argv) >= 2 and argv[0] == "voltar":
        print(voltar(paths, argv[1], int(argv[2]) if len(argv) > 2 else 1))
        return 0
    if len(argv) == 1:
        d = guardar(paths, argv[0])
        print(d or "nada mudou desde a última cópia")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
