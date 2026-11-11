"""Lado do Deck da dublagem (0.8): os vídeos de cena de um jogo de Switch saem do RomFS para o PC dublar
(tools/pc/dublar.py: Whisper na placa de vídeo + tradução + voz edge-tts + ffmpeg) e voltam como mod do Ryujinx
(LayeredFS: o jogo original nunca é tocado; apagar a pasta do mod desfaz).

    python3 -m dc.dublagem_deck listar <jogo>                 -> JSON [{"caminho", "mb"}]
    python3 -m dc.dublagem_deck extrair <jogo> <caminho> <arquivo de saída>
    python3 -m dc.dublagem_deck instalar <jogo> <caminho> <arquivo dublado>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

EXT = (".mp4", ".webm", ".mkv", ".mov")


def _romfs(game_id: str):
    from . import syncer, transferir
    from .dedup import base_title_id
    from .traducao import converter, extract, nca, switch
    e = transferir.carregar_mapa().get(game_id)
    if not e or e.get("console") not in ("switch", "switch2"):
        raise ValueError("dublagem: só jogos de Switch por enquanto")
    rom = Path(e["rom"])
    tid = base_title_id(rom.name)
    kp = switch.keys_path()
    if not tid or not kp:
        raise ValueError("não achei o title id ou as keys do Switch")
    upd = extract.latest_update(converter.collect(syncer.rom_roots(), tid))
    rfs, _h = nca.open_romfs(rom, nca.load_keys(kp), upd)
    return rfs, tid


def listar(game_id: str) -> list[dict]:
    rfs, _tid = _romfs(game_id)
    return [{"caminho": p, "mb": round(n / 1e6, 1)} for p, (_o, n) in sorted(rfs.files().items())
            if p.lower().endswith(EXT)]


def extrair(game_id: str, caminho: str, saida: Path) -> int:
    rfs, _tid = _romfs(game_id)
    off, n = rfs.files()[caminho]
    saida.parent.mkdir(parents=True, exist_ok=True)
    with open(saida, "wb") as f:
        pos = 0
        while pos < n:  # em blocos de 8 MB (vídeos de centenas de MB)
            k = min(8 << 20, n - pos)
            f.write(rfs.read_at(off + pos, k))
            pos += k
    return n


def instalar(game_id: str, caminho: str, arquivo: Path) -> Path:
    from .traducao import switch
    _rfs, tid = _romfs(game_id)
    destino = switch.mod_target(tid).parent / "Dublagem PT-BR (Deck Commander)" / "romfs" / caminho.lstrip("/")
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(destino.name + ".tmp")
    tmp.write_bytes(arquivo.read_bytes())
    tmp.replace(destino)
    return destino


def main(argv: list[str]) -> int:
    if argv[:1] == ["listar"] and len(argv) == 2:
        print(json.dumps(listar(argv[1]), ensure_ascii=False))
    elif argv[:1] == ["extrair"] and len(argv) == 4:
        print(extrair(argv[1], argv[2], Path(argv[3])))
    elif argv[:1] == ["instalar"] and len(argv) == 4:
        print(instalar(argv[1], argv[2], Path(argv[3])))
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
