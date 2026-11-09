"""M4 — /sync: downloads concluídos -> biblioteca.

Classificação (M4.2): categoria explícita do /add > extensão + nome > pergunta.
Integridade (M4.5): sem referência => 'unverified' (nunca 'corrupted' sem evidência).
ZIP (M4.6): extração protegida; suspeito => quarentena. >3 jogáveis => pede confirmação.
ROM hack (M4.10): detecta [BR]/(Translated)/(T x.y) e mantém a versão original separada.
Multidisco (M4.11): CD1/CD2/(Disc 1) de PS1 => gera .m3u e vira UM jogo.
"""
from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import safe_extract
from .emulators import CONSOLES
from .quarantine import quarantine

ARCHIVES = {".zip", ".7z", ".rar"}
AMBIGUOUS = {".iso", ".chd", ".zip", ".bin", ".cue", ".pbp"}  # existe em vários consoles
_DISC = re.compile(r"\s*[\(\[]?\s*(disc|disco|cd)\s*([0-9]+)\s*[\)\]]?", re.I)
_HACK = re.compile(r"\[(br|pt-?br|t[-+]?por?)\]|\((br|pt-?br|translated|traduzido)\)|\(t\s?\d", re.I)
NAME_HINTS = [(re.compile(p, re.I), c) for p, c in (
    (r"\bps2\b|playstation 2", "ps2"), (r"\bpsx\b|\bps1\b|playstation(?! [2-9])", "psx"),
    (r"gamecube|\bngc\b", "gc"), (r"\bwii\b", "wii"), (r"\bpsp\b", "psp"), (r"\bswitch\b|\bnsw\b", "switch"),
    (r"\bsnes\b|super nintendo", "snes"), (r"\bn64\b|nintendo 64", "n64"), (r"\bgba\b|game boy advance", "gba"),
    (r"\bnds\b|nintendo ds\b|\(ds\)|\[ds\]", "nds"))]


def _link_or_copy(src: Path, dst: Path) -> None:
    """Hardlink no mesmo disco (instantâneo, 0 bytes extras); cópia entre discos."""
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def classify(name: str, explicit: Optional[str] = None) -> Optional[str]:
    if explicit:
        return explicit if explicit in CONSOLES else None
    for rx, c in NAME_HINTS:
        if rx.search(name):
            return c
    ext = Path(name).suffix.lower()
    owners = [c for c, spec in CONSOLES.items() if ext in spec["exts"]]
    if len(owners) == 1 and ext not in AMBIGUOUS:
        return owners[0]
    return None  # ambíguo -> bot pergunta


def is_translation(name: str) -> bool:
    return bool(_HACK.search(name))


def playable(files: list[Path], console: str) -> list[Path]:
    exts = CONSOLES[console]["exts"]
    out = [f for f in files if f.suffix.lower() in exts and f.suffix.lower() != ".zip"]
    if console == "switch":
        from .library import switch_kind
        out = [f for f in out if switch_kind(f.name) in ("base", "unknown")]
    return out


def make_m3u(discs: list[Path], folder: Path) -> Optional[Path]:
    """PS1 multidisco: (Disc 1)/(Disc 2) -> '<jogo>.m3u' com caminhos relativos, preservando nomes."""
    numbered = [(int(m.group(2)), d) for d in discs if (m := _DISC.search(d.stem))]
    if len(numbered) < 2:
        return None
    numbered.sort()
    base = _DISC.sub("", numbered[0][1].stem).strip()
    m3u = folder / f"{base}.m3u"
    m3u.write_text("\n".join(d.name for _, d in numbered) + "\n", "utf-8")
    return m3u


@dataclass
class SyncItem:
    name: str
    console: Optional[str]
    status: str                    # added / ask_console / ask_many / quarantined / skipped
    files: list[str] = field(default_factory=list)
    note: str = ""
    integrity: str = "unverified"


def ingest(content: Path, console: Optional[str], roms_root: Path, quarantine_root: Path,
           work: Path, confirm_many: bool = False) -> SyncItem:
    """Leva um download concluído (arquivo ou pasta) para roms_root/<console>/<pasta>/."""
    content = Path(content)
    name = content.name
    console = classify(name, console)
    if console is None:
        files = [content] if content.is_file() else [f for f in content.rglob("*") if f.is_file()]
        guesses = {classify(f.name) for f in files} - {None}
        if len(guesses) == 1:
            console = guesses.pop()
        else:
            return SyncItem(name, None, "ask_console", note="não consegui identificar o console")
    staging = work / f"stage-{abs(hash(str(content))) % 10**8}"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        src_files = [content] if content.is_file() else sorted(f for f in content.rglob("*") if f.is_file())
        collected: list[Path] = []
        for f in src_files:
            if f.suffix.lower() in ARCHIVES:
                try:
                    out = safe_extract.extract_any(f, staging / f.stem)
                except safe_extract.NoSpace as e:
                    return SyncItem(name, console, "no_space", note=f"{e} — libere espaço (/disk); tento de novo sozinho")
                except safe_extract.UnsafeArchive as e:
                    q = quarantine(f, quarantine_root, f"arquivo suspeito no /sync: {e}")
                    return SyncItem(name, console, "quarantined", note=f"{e} (em {q.name})")
                collected += out
            else:
                dst = staging / f.relative_to(content.parent if content.is_file() else content)
                dst.parent.mkdir(parents=True, exist_ok=True)
                _link_or_copy(f, dst)
                collected.append(dst)
        empty = [f for f in collected if f.stat().st_size == 0]
        if empty:
            q = quarantine(staging, quarantine_root, f"arquivos vazios: {[e.name for e in empty][:3]}")
            return SyncItem(name, console, "quarantined", note=f"arquivo vazio (em {q.name})", integrity="corrupted")
        if console == "ps2":  # imagem .mdf de DVD = setores de 2048 bytes = .iso (o PCSX2 abre .iso)
            for i, f in enumerate(collected):
                if f.suffix.lower() == ".mdf" and f.stat().st_size % 2048 == 0:
                    iso = f.with_suffix(".iso")
                    f.rename(iso)
                    collected[i] = iso
        games = playable(collected, console)
        if not games:
            return SyncItem(name, console, "skipped", note="nenhum arquivo jogável para " + console)
        title = re.sub(r"\.(zip|7z|rar)$", "", name, flags=re.I)
        if console == "psx":
            m3u = make_m3u([g for g in games if g.suffix.lower() in (".cue", ".chd", ".pbp")], staging)
            if m3u:
                games = [m3u]
        if len(games) > 3 and not confirm_many:
            return SyncItem(name, console, "ask_many", files=[g.name for g in games],
                            note=f"{len(games)} jogos no mesmo download — confirme com /sync tudo")
        dest, n = roms_root / console / title, 1
        while dest.exists():  # nunca mistura com uma pasta que já existe
            dest = roms_root / console / (f"{title} (novo)" if n == 1 else f"{title} (novo {n})")
            n += 1
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staging), str(dest))
        moved = [str(dest / g.relative_to(staging)) for g in games]
        note = "parece tradução/ROM hack — adicionado separado, original intacto" if is_translation(name) else ""
        return SyncItem(name, console, "added", files=moved, note=note)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
