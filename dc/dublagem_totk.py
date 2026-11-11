"""Dublagem PT-BR do Zelda Tears of the Kingdom (lado do Deck) — engenharia reversa de 11/11/2026.

Cada fala dublada do jogo é um arquivo Voice/Resource/USen/EventFlowMsg/<cena>_Stream/<rótulo>.bwav e o texto
dela está em Mals/USen.Product.*.sarc.zs → EventFlowMsg/<cena>.msbt com o MESMO rótulo (ex. Dm_ZE_0011_Text_008_b).
O PC (tools/pc/dublar_totk.py) traduz o texto, gera a voz PT-BR do mesmo tamanho e manda o .bwav de volta; aqui ele
é instalado como mod do Ryujinx (LayeredFS: o jogo original nunca é tocado; apagar a pasta do mod desfaz).

    python3 -m dc.dublagem_totk cenas                       -> JSON [cena…]
    python3 -m dc.dublagem_totk falas <cena>                -> JSON [{"rotulo", "texto", "amostras"}]
    python3 -m dc.dublagem_totk original <cena> <rótulo> <arquivo.bwav>
    python3 -m dc.dublagem_totk instalar <cena> <rótulo> <arquivo.bwav>
"""
from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path

JOGO = "switch-the-legend-of-zelda-tears-of-the-kingdom"
VOZ = "Voice/Resource/USen/EventFlowMsg"
MOD = "Dublagem PT-BR (Deck Commander)"


@lru_cache(maxsize=1)
def _romfs():
    from . import dublagem_deck
    return dublagem_deck._romfs(JOGO)


def _ler(caminho: str) -> bytes:
    rfs, _tid = _romfs()
    off, n = rfs.files()[caminho]
    return rfs.read_at(off, n)


@lru_cache(maxsize=1)
def _textos() -> dict[str, str]:
    """rótulo -> texto em inglês de todas as falas de cena (EventFlowMsg)."""
    from compression import zstd  # Python 3.14+
    from .traducao import nx
    rfs, _tid = _romfs()
    dic = zstd.ZstdDict(nx.read_sarc(zstd.decompress(_ler("Pack/ZsDic.pack.zs"))).files["zs.zsdic"])
    mals = sorted(p for p in rfs.files() if p.startswith("Mals/USen.Product"))[-1]
    sarc = nx.read_sarc(zstd.decompress(_ler(mals), zstd_dict=dic))
    out = {}
    for nome, dados in sarc.files.items():
        if nome.startswith("EventFlowMsg/") and nome.endswith(".msbt"):
            m = nx.read_msbt(dados)
            for idx, rot in m.labels.items():
                out[rot] = "".join(p for p in m.strings[idx] if isinstance(p, str)).strip()
    return out


def cenas() -> list[str]:
    rfs, _tid = _romfs()
    return sorted({p.split("/")[4][:-len("_Stream")] for p in rfs.files()
                   if p.startswith(VOZ + "/") and p.split("/")[4].endswith("_Stream")})


def falas(cena: str) -> list[dict]:
    """Falas da cena que têm texto (gemidos/respiração sem legenda ficam com a voz original)."""
    from .traducao import bwav
    rfs, _tid = _romfs()
    textos = _textos()
    out = []
    for p in sorted(rfs.files()):
        if p.startswith(f"{VOZ}/{cena}_Stream/") and p.endswith(".bwav"):
            rot = Path(p).stem
            texto = textos.get(rot, "")
            if texto:
                b = bwav.ler(_ler(p))
                out.append({"rotulo": rot, "texto": texto, "amostras": b.amostras})
    return out


def instalar(cena: str, rotulo: str, arquivo: Path) -> Path:
    from .traducao import bwav, switch
    bwav.ler(arquivo.read_bytes())  # confere que é um BWAV válido antes de pôr no jogo
    _rfs, tid = _romfs()
    destino = switch.mod_target(tid).parent / MOD / "romfs" / VOZ / f"{cena}_Stream" / f"{rotulo}.bwav"
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(destino.name + ".tmp")
    tmp.write_bytes(arquivo.read_bytes())
    tmp.replace(destino)
    return destino


def originais_tar(cena: str, saida: Path) -> int:
    """Todas as vozes originais da cena num .tar (uma ida só para o PC)."""
    import io
    import tarfile
    rfs, _tid = _romfs()
    n = 0
    with tarfile.open(saida, "w") as tf:
        for p in sorted(rfs.files()):
            if p.startswith(f"{VOZ}/{cena}_Stream/") and p.endswith(".bwav"):
                dados = _ler(p)
                ti = tarfile.TarInfo(Path(p).name)
                ti.size = len(dados)
                tf.addfile(ti, io.BytesIO(dados))
                n += 1
    return n


def instalar_tar(cena: str, arquivo: Path) -> int:
    """Instala todas as vozes dubladas de um .tar (só arquivos .bwav soltos, conferidos um a um)."""
    import tarfile
    import tempfile
    n = 0
    with tarfile.open(arquivo) as tf, tempfile.TemporaryDirectory() as t:
        for m in tf.getmembers():
            if m.isfile() and "/" not in m.name and m.name.endswith(".bwav"):
                p = Path(t) / m.name
                p.write_bytes(tf.extractfile(m).read())
                instalar(cena, Path(m.name).stem, p)
                n += 1
    return n


def main(argv: list[str]) -> int:
    if argv[:1] == ["originais"] and len(argv) == 3:
        print(originais_tar(argv[1], Path(argv[2])))
        return 0
    if argv[:1] == ["instalar_tar"] and len(argv) == 3:
        print(instalar_tar(argv[1], Path(argv[2])))
        return 0
    if argv[:1] == ["cenas"]:
        print(json.dumps(cenas()))
    elif argv[:1] == ["falas"] and len(argv) == 2:
        print(json.dumps(falas(argv[1]), ensure_ascii=False))
    elif argv[:1] == ["original"] and len(argv) == 4:
        Path(argv[3]).write_bytes(_ler(f"{VOZ}/{argv[1]}_Stream/{argv[2]}.bwav"))
    elif argv[:1] == ["instalar"] and len(argv) == 4:
        print(instalar(argv[1], argv[2], Path(argv[3])))
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
