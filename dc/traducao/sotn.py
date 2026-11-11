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
        trechos += sem_sobreposicao(S.achar_menos20(nome, d) + S.achar_ascii(nome, d))
    return trechos


def sem_sobreposicao(trechos: list[S.Trecho]) -> list[S.Trecho]:
    """Os dois leitores podem pegar o mesmo pedaço (falha real: DRA.BIN @260864): fica o primeiro da lista
    (nomes em -0x20 têm prioridade, porque terminam no 0xFF exato) e cai quem encostar nele."""
    ocupado: list[tuple[int, int]] = []
    out = []
    for t in trechos:
        if any(t.pos < fim and ini < t.pos + t.tam for ini, fim in ocupado):
            continue
        ocupado.append((t.pos, t.pos + t.tam))
        out.append(t)
    return sorted(out, key=lambda t: t.pos)


def agrupar(trechos: list[S.Trecho], dados: dict[str, bytes]) -> list[list[S.Trecho]]:
    """Junta as linhas de uma mesma fala (trechos ASCII separados só por códigos de controle curtos, sem 0x00),
    para a IA traduzir a frase inteira e não pedaços soltos ("Whatever we do," + "the castle…")."""
    grupos: list[list[S.Trecho]] = []
    for t in sorted(trechos, key=lambda x: (x.arquivo, x.pos)):
        g = grupos[-1] if grupos else None
        if g and t.tipo == "ascii" and g[-1].tipo == "ascii" and g[-1].arquivo == t.arquivo:
            vao = dados[t.arquivo][g[-1].pos + g[-1].tam:t.pos]
            if 0 < len(vao) <= 4 and all(0 < b < 0x20 for b in vao):
                g.append(t)
                continue
        grupos.append([t])
    return grupos


def distribuir(texto: str, grupo: list[S.Trecho]) -> list[str]:
    """Reparte a frase traduzida pelas linhas originais (cada linha cabe no espaço dela; palavra inteira)."""
    palavras = S.sem_acento(texto).split()
    saida = []
    for k, t in enumerate(grupo):
        linha = ""
        while palavras:
            cand = (linha + " " + palavras[0]).strip()
            if len(S.codificar(cand, 10 ** 4, t.tipo).rstrip()) > t.tam and linha:
                break
            linha = cand
            palavras.pop(0)
            if k == len(grupo) - 1:
                continue
        saida.append(linha)
    if palavras and saida:  # sobrou: vai para a última linha (codificar corta no espaço que couber)
        saida[-1] = (saida[-1] + " " + " ".join(palavras)).strip()
    return saida


def translate_rom(paths: Paths, rom: Path, title: str = "", chain=None, progress=lambda d, t: None,
                  should_pause=lambda: False) -> RtsReport:
    cfg = ia.load_cfg(paths)
    rep = RtsReport(rom=str(rom), encoding="SOTN (ASCII e ASCII-0x20)")
    bin_ = _bin_da_cue(rom) if rom.suffix.lower() == ".cue" else rom
    disco = Disco(bin_)
    trechos = coletar(disco)
    rep.found = rep.candidates = len(trechos)
    dados = {nome: disco.ler(nome) for nome in {t.arquivo for t in trechos}}
    # cada fala (grupo de linhas) vira UMA frase para a IA; frases iguais em vários lugares traduzem uma vez só
    por_texto: dict[str, list[list[S.Trecho]]] = {}
    for g in agrupar(trechos, dados):
        por_texto.setdefault(" ".join(t.texto for t in g), []).append(g)
    itens = [ia.Item(f"t{n}", txt, max_len=min(sum(t.tam for t in g) for g in gs))
             for n, (txt, gs) in enumerate(por_texto.items())]
    ids = {f"t{n}": txt for n, txt in enumerate(por_texto)}
    res = ia.translate(paths, cfg, itens, f"sotn-{rom.stem}", ia.load_glossary_jogo(paths, cfg, itens, title),
                       chain=chain, progress=progress, should_pause=should_pause)
    rep.provider = res.provider_used
    trocas: dict[str, list[tuple[S.Trecho, str]]] = {}
    for iid, novo in res.translated.items():
        orig = ids.get(iid)
        if not orig or not novo.strip() or S.sem_acento(novo).strip() == orig.strip():
            continue
        for g in por_texto[orig]:
            for t, linha in zip(g, distribuir(novo, g)):
                trocas.setdefault(t.arquivo, []).append((t, linha))
            rep.translated += 1
    rep.flagged = len(res.flagged)
    rep.errors += res.errors[:3]
    if not trocas:
        rep.errors.append("nenhuma frase traduzida")
        return rep
    novos = {nome: S.aplicar(dados[nome], ts) for nome, ts in trocas.items()}
    stem = rom.stem
    bin_pt = bin_.with_name(f"{stem} (PT-BR).bin")
    disco.gravar_copia(bin_pt, novos)
    if rom.suffix.lower() == ".cue":
        cue_pt = rom.with_name(f"{stem} (PT-BR).cue")
        gravar_cue(rom, cue_pt, bin_pt.name)
        rep.output = str(cue_pt)
    else:
        rep.output = str(bin_pt)
    originais = {t.texto for t in trechos}
    rep.audit_left = sum(1 for t in coletar(Disco(bin_pt)) if t.texto in originais)
    return rep
