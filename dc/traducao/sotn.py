"""Tradução PT-BR do Castlevania: Symphony of the Night (PS1) — engenharia reversa de 11/11/2026.

O texto do jogo fica em DRA.BIN (itens, menus, descrições), BOSS/*/*.BIN e ST/*/*.BIN (diálogos de cada fase), em dois
formatos (dc.traducao.eng_sotn). Cada trecho traduzido ocupa EXATAMENTE os bytes do original (sem acento: a fonte
do jogo só tem ASCII), então nenhum ponteiro nem tamanho de arquivo muda e o disco novo é uma cópia "(PT-BR)" do
.bin/.cue ao lado do original (o original nunca é tocado).
"""
from __future__ import annotations

import re
from pathlib import Path

from ..paths import Paths
from . import eng_sotn as S
from . import ia
from .psx_disco import Disco, gravar_cue
from .rts import RtsReport

SERIAIS = ("SLES_005.24", "SLUS_000.67", "SLES_005.25", "SLES_005.26", "SLES_005.27")  # SOTN EUR/EUA
_PULA = re.compile(r"(^|/)(F_|SD_)|\.(STR|XA|VB|VH|TIM|CCS|DA)$", re.I)


def _bin_da_cue(cue: Path) -> Path:
    m = re.search(r'FILE\s+"([^"]+)"\s+BINARY', cue.read_text("utf-8", "replace"))
    if not m:
        raise ValueError("cue sem FILE … BINARY")
    return cue.with_name(m.group(1))


def reconhece(rom: Path) -> bool:
    """É o SOTN de PS1? (lê o SYSTEM.CNF do disco)"""
    try:
        b = _bin_da_cue(rom) if rom.suffix.lower() == ".cue" else rom
        cnf = Disco(b).ler("SYSTEM.CNF").decode("ascii", "replace").upper()
    except (OSError, ValueError, KeyError, StopIteration):
        return False
    return any(s in cnf for s in SERIAIS)


def coletar(disco: Disco) -> list[S.Trecho]:
    trechos = []
    for nome in sorted(disco.arquivos()):
        if not nome.upper().endswith(".BIN") or _PULA.search(nome) or not (
                nome.upper() == "DRA.BIN" or nome.upper().startswith(("ST/", "BOSS/"))):
            continue
        d = disco.ler(nome)
        trechos += S.achar_ascii(nome, d) + S.achar_menos20(nome, d)
    return trechos


def translate_rom(paths: Paths, rom: Path, title: str = "", chain=None, progress=lambda d, t: None,
                  should_pause=lambda: False) -> RtsReport:
    cfg = ia.load_cfg(paths)
    rep = RtsReport(rom=str(rom), encoding="SOTN (ASCII e ASCII-0x20)")
    bin_ = _bin_da_cue(rom) if rom.suffix.lower() == ".cue" else rom
    disco = Disco(bin_)
    trechos = coletar(disco)
    rep.found = rep.candidates = len(trechos)
    por_texto: dict[str, list[S.Trecho]] = {}
    for t in trechos:
        por_texto.setdefault(t.texto, []).append(t)
    itens = [ia.Item(f"t{n}", txt, max_len=min(x.tam for x in ts)) for n, (txt, ts) in enumerate(por_texto.items())]
    ids = {f"t{n}": txt for n, txt in enumerate(por_texto)}
    res = ia.translate(paths, cfg, itens, f"sotn-{rom.stem}", ia.load_glossary_jogo(paths, cfg, itens, title),
                       chain=chain, progress=progress, should_pause=should_pause)
    rep.provider = res.provider_used
    trocas: dict[str, list[tuple[S.Trecho, str]]] = {}
    for iid, novo in res.translated.items():
        orig = ids.get(iid)
        if not orig or not novo.strip() or S.sem_acento(novo).strip() == orig.strip():
            continue
        for t in por_texto[orig]:
            trocas.setdefault(t.arquivo, []).append((t, novo))
            rep.translated += 1
    rep.flagged = len(res.flagged)
    rep.errors += res.errors[:3]
    if not trocas:
        rep.errors.append("nenhuma frase traduzida")
        return rep
    novos = {nome: S.aplicar(disco.ler(nome), ts) for nome, ts in trocas.items()}
    stem = rom.stem
    bin_pt = bin_.with_name(f"{stem} (PT-BR).bin")
    disco.gravar_copia(bin_pt, novos)
    if rom.suffix.lower() == ".cue":
        cue_pt = rom.with_name(f"{stem} (PT-BR).cue")
        gravar_cue(rom, cue_pt, bin_pt.name)
        rep.output = str(cue_pt)
    else:
        rep.output = str(bin_pt)
    rep.audit_left = sum(1 for t in coletar(Disco(bin_pt)) if t.texto in por_texto and t.texto.strip())
    return rep
