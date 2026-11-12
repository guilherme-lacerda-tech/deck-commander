"""Confere a tradução Trinity (Pokémon Legends Z-A) com os arquivos REAIS do jogo. Só lê o jogo.

    python3 tools/trinity_check.py <jogo.nsp> [--piloto N] [--arquivo common/bag.dat] [--saida DIR]

1. Extrai (cache do Deck Commander) o data.trpfd, as mensagens do idioma de origem e confere as fontes.
2. Todo .dat: ler + regravar precisa dar os mesmos bytes; todo código ⟦n⟧ volta igual.
3. Com --piloto N: traduz N frases de um arquivo com a cadeia de IA configurada, monta o mod numa pasta
   (padrão: temporária; NÃO instala no Ryujinx) e confere o mod relendo tudo.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dc import syncer  # noqa: E402
from dc.dedup import base_title_id  # noqa: E402
from dc.paths import get_paths  # noqa: E402
from dc.traducao import ia, trinity
from dc.traducao import trinity_game as tg
from dc.traducao import trinity_msg as tm


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("--piloto", type=int, default=0)
    ap.add_argument("--arquivo", default="")
    ap.add_argument("--saida", default="")
    a = ap.parse_args()
    paths = get_paths().ensure()
    rom = Path(a.rom)
    tid = base_title_id(rom.name)
    cfg = ia.load_cfg(paths)
    t = time.time()
    src, info = tg.extract(paths, rom, tid, syncer.rom_roots(), cfg["idioma_origem"], print)
    print(f"extração: {len(info['mensagens'])} mensagens em {time.time() - t:.0f}s ({src})")
    for k, v in info["fontes"].items():
        print(f"  fonte {k}: {'tem todos os acentos do PT-BR' if not v else 'FALTAM ' + v}")
    ok = bad = lines = 0
    for rel in info["mensagens"]:
        raw = (src / "romfs" / rel).read_bytes()
        try:
            m = tm.read_dat(raw)
            assert tm.write_dat(m) == raw, "regravação diferente"
            for text, codes in m.texts():
                assert tm.join_codes(text, codes) == tg.from_marked(tg.to_marked(text), codes)
                lines += 1
            ok += 1
        except (tm.MsgError, AssertionError) as e:
            bad += 1
            print(f"  ❌ {rel}: {e}")
    print(f"ida-e-volta byte a byte: {ok} ok, {bad} com problema, {lines} frases")
    if not a.piloto:
        return 1 if bad else 0
    rel = a.arquivo and next(r for r in info["mensagens"] if r.endswith(a.arquivo)) or info["mensagens"][0]
    m = tm.read_dat((src / "romfs" / rel).read_bytes())
    items, texts = [], {}
    for i, (text, codes) in enumerate(m.texts()):
        mk = tg.to_marked(text)
        if mk.strip() and len(items) < a.piloto:
            items.append(ia.Item(f"{rel}#{i}", mk))
            texts[f"{rel}#{i}"] = (i, text, codes)
    print(f"piloto: {len(items)} frases de {rel}")
    res = ia.translate(paths, cfg, items, f"piloto-{tid}", ia.load_glossary(paths, "Pokemon"))
    print(f"IA: {res.provider_used} · traduzidas {len(res.translated)} · problemas {len(res.flagged)} {res.errors[:2]}")
    n = 0
    for iid, (i, text, codes) in texts.items():
        new = res.translated.get(iid)
        if not new or new == tg.to_marked(text):
            continue
        marked, codes2, fits = tg.layout(text, codes, new)
        m.lines[i].words = tg.from_marked(marked, codes2)
        n += 1
        if n <= 8:
            print(f"  {tg.to_marked(text)[:70]!r}\n   → {marked[:90]!r}{'' if fits else '  (mais linhas)'}")
    out = Path(a.saida) if a.saida else Path(tempfile.mkdtemp(prefix="trinity-piloto-"))
    problems = tg.build_mod(out / "romfs", (src / "data.trpfd").read_bytes(), {rel: m})
    fd = trinity.read_trpfd((out / "romfs" / tg.TRPFD).read_bytes())
    print(f"mod em {out}: {n} frases trocadas; {rel} fora do trpfd: {fd.pack_of(trinity.fnv1a64(rel)) is None}; "
          f"problemas: {problems or 'nenhum'}")
    return 1 if (bad or problems) else 0


if __name__ == "__main__":
    raise SystemExit(main())
