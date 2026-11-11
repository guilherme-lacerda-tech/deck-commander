"""A1 — Tradução retrô com IA. Motor de extração/reinserção: Meowth GBA Translator (MIT).

O "RomTranslate Studio" do plano não existe; o Meowth é a ferramenta real mais próxima, e cobre
Pokémon de GBA (Gen 3 e hacks). Ele não aceita português como destino, então:
  meowth extract (como espanhol, mesmo alfabeto latino) -> NOSSA tradução pt-BR (ia.py, com
  glossário/few-shot/cache) -> meowth build -> ROM nova "(PT-BR)" + patch .bps. Original intacta.
O alfabeto de texto do GBA (PCS) não tem ã/õ: viram a/o e isso aparece no relatório.
Outros consoles: não há extrator genérico confiável — o bot responde com clareza em vez de tentar.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .. import patches
from ..paths import Paths
from . import ia

H = Path.home()
MEOWTH_CANDIDATES = [H / ".local/share/deck-commander/meowth-venv/bin/meowth"]
SUPPORTED = {"gba"}
GBA_CODES = re.compile(r"\[[^\]\n]{1,24}\]|\{[^}\n]{1,24}\}|\\[nlpv]|\\[0-9A-Fa-f]{2}|\\x[0-9A-Fa-f]{2}")
NO_GLYPH = {"ã": "a", "õ": "o", "Ã": "A", "Õ": "O"}


@dataclass
class RetroReport:
    rom: str
    strings: int = 0
    translated: int = 0
    flagged: int = 0
    review: int = 0
    replaced_chars: int = 0
    provider: str = ""
    tokens: int = 0
    output: str = ""
    patch: str = ""
    errors: list[str] = field(default_factory=list)
    flagged_samples: list[str] = field(default_factory=list)

    def pct_flagged(self) -> float:
        return 100.0 * self.flagged / max(1, self.strings)

    def text(self) -> str:
        L = [f"frases: {self.strings} · traduzidas: {self.translated}",
             f"com problema (original mantido): {self.flagged} ({self.pct_flagged():.1f}%) · para revisar: {self.review}",
             f"IA: {self.provider or '-'} · tokens: {self.tokens}"]
        if self.replaced_chars:
            L.append(f"ã/õ trocados por a/o em {self.replaced_chars} lugar(es) (o GBA não tem essas letras)")
        L += [f"⚠️ {e}" for e in self.errors[:5]]
        if self.output:
            L.append(f"ROM traduzida: {Path(self.output).name} · patch: {Path(self.patch).name}")
        return "\n".join(L)


def meowth_bin() -> Optional[str]:
    for c in MEOWTH_CANDIDATES:
        if c.exists():
            return str(c)
    return shutil.which("meowth")


def supported(console: str) -> bool:
    return console in SUPPORTED


POKEMON_GBA_CODES = ("BPR", "BPG", "BPE", "AXV", "AXP")  # FireRed, LeafGreen, Emerald, Ruby, Sapphire (e hacks deles)


def is_pokemon_gba(rom: Path) -> bool:
    try:
        with open(rom, "rb") as f:
            f.seek(0xAC)
            code = f.read(4).decode("ascii", "replace")
        return code[:3] in POKEMON_GBA_CODES
    except OSError:
        return False


def _entries(data: dict) -> list[dict]:
    """Todas as entradas do JSON do Meowth (formato com tabelas ou plano)."""
    out = []
    for t in data.get("tables", []):
        out += t.get("entries", [])
    out += data.get("free_texts", [])
    out += data.get("entries", [])
    return [e for e in out if isinstance(e, dict) and isinstance(e.get("original"), str)]


def _run(cmd: list[str], cwd: Path, timeout: int = 3600) -> None:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[-400:] or f"{cmd[1]} falhou")


def extract(rom: Path, work: Path, source: str = "en") -> dict:
    mb = meowth_bin()
    if not mb:
        raise RuntimeError("Meowth não instalado: rode ./setup-deck.sh --modules A1")
    work.mkdir(parents=True, exist_ok=True)
    out = work / "texts.json"
    _run([mb, "extract", str(rom), "-o", str(out), "--source", source, "--target", "es"], cwd=work)
    return json.loads(out.read_text("utf-8"))


def pairs_from_reference(ref: dict, source: str = "en") -> list[tuple[str, str]]:
    """Mesma ROM em duas versões (original e traduzida): pares alinhados pelo id da entrada."""
    with tempfile.TemporaryDirectory() as d:
        a = extract(Path(ref["original"]).expanduser(), Path(d) / "a", source)
        b = extract(Path(ref["traduzido"]).expanduser(), Path(d) / "b", source)
    bm = {e.get("id"): e["original"] for e in _entries(b) if e.get("id")}
    return [(e["original"], bm[e["id"]]) for e in _entries(a) if e.get("id") in bm and bm[e["id"]] != e["original"]]


def output_paths(rom: Path) -> tuple[Path, Path]:
    stem = re.sub(r"\s*\((pt-?br|br)\)\s*$", "", rom.stem, flags=re.I)
    return rom.with_name(f"{stem} (PT-BR){rom.suffix}"), rom.with_name(f"{stem} (PT-BR).bps")


def translate_rom(paths: Paths, rom: Path, game_name: str = "", chain=None,
                  progress=lambda d, t: None, should_pause=lambda: False,
                  log: Callable[[str], None] = lambda s: None, source: Optional[str] = None) -> RetroReport:
    cfg = ia.load_cfg(paths)
    if source:  # ex.: versão espanhola de um jogo: traduz do espanhol
        cfg["idioma_origem"] = source
    rep = RetroReport(str(rom))
    work = paths.data / "traducao" / "work" / re.sub(r"\W+", "_", rom.stem)
    shutil.rmtree(work, ignore_errors=True)
    data = extract(rom, work, cfg["idioma_origem"])
    entries = _entries(data)
    rep.strings = len(entries)
    examples = []
    if cfg.get("few_shot"):
        from .switch import load_references
        for ref in load_references(paths):
            if ref.get("console") in SUPPORTED:
                try:
                    examples += pairs_from_reference(ref, cfg["idioma_origem"])[:400]
                except (OSError, RuntimeError, KeyError, ValueError) as e:
                    log(f"referência {ref.get('titulo')}: {e}")
    items, codes = [], {}
    for n, e in enumerate(entries):
        prot, cs = ia.protect(e["original"], GBA_CODES)
        codes[str(n)] = cs
        if prot.strip():
            items.append(ia.Item(str(n), prot))
    res = ia.translate(paths, cfg, items, f"retro-{rom.stem}", ia.load_glossary_jogo(paths, cfg, items, game_name), examples,
                       chain=chain, progress=progress, should_pause=should_pause)
    rep.provider, rep.tokens, rep.errors = res.provider_used, res.tokens, res.errors
    rep.flagged, rep.review = len(res.flagged), len(res.review)
    rep.flagged_samples = [f"{entries[int(k)]['original'][:60]} → {v}" for k, v in list(res.flagged.items())[:20]]
    for n, e in enumerate(entries):
        t = res.translated.get(str(n))
        if t is None:
            continue
        for a, b in NO_GLYPH.items():
            rep.replaced_chars += t.count(a)
            t = t.replace(a, b)
        e["translated"] = ia.restore(t, codes[str(n)])
        rep.translated += 1
    if not rep.translated:
        rep.errors.append("nenhuma frase traduzida")
        return rep
    tj = work / "texts_translated.json"
    tj.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    out_rom, out_patch = output_paths(rom)
    if rep.pct_flagged() > float(cfg.get("flagged_threshold", 10)):
        # muita frase com problema: não entra na biblioteca sozinho; fica guardado para /traduzir aplicar
        pend = paths.data / "traducao" / "pendente"
        pend.mkdir(parents=True, exist_ok=True)
        out_rom, out_patch = pend / out_rom.name, pend / out_patch.name
        rep.errors.append(f"{rep.pct_flagged():.0f}% das frases com problema: guardado sem aplicar")
    tmp_rom = work / ("out" + rom.suffix)
    _run([meowth_bin(), "build", str(rom), "--translations", str(tj), "-o", str(tmp_rom), "--target", "es"], cwd=work)
    src, tgt = rom.read_bytes(), tmp_rom.read_bytes()
    bps = patches.create_bps(src, tgt)
    if patches.apply_bps(src, bps) != tgt:  # o patch precisa reproduzir a ROM traduzida exatamente
        raise RuntimeError("patch gerado não reproduz a ROM traduzida")
    out_patch.write_bytes(bps)
    shutil.copyfile(tmp_rom, out_rom)
    rep.output, rep.patch = str(out_rom), str(out_patch)
    shutil.rmtree(work, ignore_errors=True)
    return rep
