#!/usr/bin/env python3
"""Teste de ponta a ponta com UM arquivo de texto real de um RomFS: extrai esse MSBT do pacote, traduz
com a IA configurada, grava o mod numa pasta temporária (NÃO instala no Ryujinx) e confere que o
resultado abre, que as tags do jogo ficaram idênticas e que o texto mudou.
Uso: python3 tools/switch_e2e_real.py <romfs> <pacote relativo> <msbt dentro do pacote>"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dc.paths import get_paths  # noqa: E402
from dc.traducao import nx, switch  # noqa: E402

romfs, pack, inner = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
raw = nx.unpack_layer(pack, (romfs / pack).read_bytes())[0]
orig = nx.read_sarc(raw).files[inner]
with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    test_romfs = d / "romfs/Message/USen"
    test_romfs.mkdir(parents=True)
    (test_romfs / Path(inner).name).write_bytes(orig)
    switch.RYU_DIRS[:] = [d / "Ryujinx"]  # mod vai para a pasta temporária
    paths = get_paths(d / "dc").ensure()
    rep = switch.translate_game(paths, "0100000000000000", d / "romfs", "teste")
    print(rep.text())
    out = Path(rep.mod_dir) / "romfs/Message/USen" / Path(inner).name
    a, b = nx.read_msbt(orig), nx.read_msbt(out.read_bytes())
    same_tags = [t for _, t in a.texts()] == [t for _, t in b.texts()]
    changed = sum(1 for x, y in zip(a.texts(), b.texts()) if x[0] != y[0])
    for (x, _), (y, _) in list(zip(a.texts(), b.texts()))[:12]:
        print(f"  {x[:60]!r} -> {y[:60]!r}")
    ok = same_tags and changed > 0 and a.labels == b.labels
    print(f"tags idênticas: {same_tags} · frases alteradas: {changed} · rótulos iguais: {a.labels == b.labels}")
    print("RESULTADO:", "TUDO OK" if ok else "FALHOU")
