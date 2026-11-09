"""A1 — Tradução retrô com o RomTranslate Studio (MIT): PS1, PS2, PSP, GBA, SNES, NES, N64, GameCube, DS…

Divisão de trabalho (cada um faz o que faz melhor):
- RomTranslate (`romtranslate`, compilado no Deck por ./setup-deck.sh --modules A1): acha o texto dentro
  da ROM/disco, regrava no lugar certo (setores de CD com EDC/ECC, checksums de cartucho), confere a
  cópia e gera o patch. O original NUNCA é alterado (ele grava numa cópia de trabalho).
- Deck Commander: escolhe SÓ trechos que são frases de verdade (a varredura genérica acha muito lixo:
  mensagens de depuração e bytes que parecem letras — traduzir isso quebraria o jogo), traduz com a
  cadeia de IA (Index-Translate -> IA do PC -> IA do Deck), respeitando o espaço de cada frase, e tira
  acentos quando a codificação do jogo não tem acento.
Resultado: "<jogo> (PT-BR)" ao lado do original (+ .bps) e o atalho do original sai da biblioteca.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ..paths import Paths
from . import ia

H = Path.home()
BIN_CANDIDATES = [H / ".local/share/deck-commander/bin/romtranslate"]
SUPPORTED = {"psx", "ps2", "psp", "gba", "snes", "n64", "gc", "nds", "nes", "gb", "gbc", "genesis"}
UNSUPPORTED_EXT = {".chd": "CHD (comprimido)", ".cso": "CSO (comprimido)", ".rvz": "RVZ (comprimido)",
                   ".pbp": "PBP (comprimido)", ".m3u": "lista de discos (.m3u)", ".zip": "ZIP", ".7z": "7z"}
NO_ACCENT_ENCODINGS = {"ascii", "table", "tbl", "pcs"}
RETRO_CODES = re.compile(r"%[-+0-9.]*[sdxXuc]|\\[nrt]|\[[^\]\n]{1,16}\]|\{[^}\n]{1,16}\}|<[^>\n]{1,16}>")
MIN_SENTENCES = 3


@dataclass
class RtsReport:
    rom: str
    found: int = 0
    candidates: int = 0
    translated: int = 0
    flagged: int = 0
    skipped_multiline: int = 0
    audit_left: Optional[int] = None
    provider: str = ""
    output: str = ""
    patch: str = ""
    errors: list[str] = field(default_factory=list)

    def text(self) -> str:
        L = [f"trechos achados: {self.found} · frases de verdade: {self.candidates} · traduzidas e gravadas: "
             f"{self.translated}",
             f"ficaram no original: {self.flagged} (não coube no espaço / IA errou)"
             + (f" + {self.skipped_multiline} com várias linhas" if self.skipped_multiline else ""),
             f"IA: {self.provider or '-'}"]
        if self.audit_left is not None:
            L.append(f"conferência na cópia gravada: {self.audit_left} trecho(s) ainda em inglês")
        L += [f"⚠️ {e}" for e in self.errors[:5]]
        if self.output:
            L.append(f"jogo traduzido: {Path(self.output).name}" + (f" · patch: {Path(self.patch).name}" if self.patch else ""))
        return "\n".join(L)


def bin_path() -> Optional[str]:
    for c in BIN_CANDIDATES:
        if c.exists():
            return str(c)
    return shutil.which("romtranslate")


def supported(console: str, rom: Path) -> tuple[bool, str]:
    if console not in SUPPORTED:
        return False, f"{console.upper()} ainda não tem tradutor automático"
    why = UNSUPPORTED_EXT.get(rom.suffix.lower())
    if why:
        return False, f"o arquivo está em {why}; o tradutor precisa da imagem descomprimida (.iso ou .bin+.cue)"
    return True, ""


COMMON_WORDS = set("""a an the and or but if of to in on at by for from with without into out up down over under
again here there this that these those it its is are was were be been being am do does did done have has had will
would can could shall should may might must not no yes you your yours we our us me my mine he him his she her they
them their what which who whom whose when where why how all any some each every more most other such only own same
so than too very just now then also get got go goes going gone come came take took make made see saw look find found
give gave tell told say said ask know knew think want need use used try press start select pause continue game play
player save load new quit exit menu options option level stage world area time score lives life points item items
key door open close back next ok cancel please insert memory card data file controller battle attack fight defeat
win lose won lost good great well done let lets ready come welcome thank thanks hello help sorry one two three
first last left right up down move jump run walk talk visit return leave enter""".split())


SYSTEM_TEXT = re.compile(r"Sony Computer Entertainment|Licensed by|PS-X EXE|Nintendo of America|SEGA ENTERPRISES", re.I)


def is_sentence(text: str) -> bool:
    """Frase que alguém lê no jogo. Bem rígido de propósito: a varredura genérica acha muito lixo (bytes de
    dados que parecem letras, como 'VDD33Ce'), e gravar tradução em cima de dado quebra o jogo."""
    t = text.strip()
    if SYSTEM_TEXT.search(t):
        return False  # licença/cabeçalho do console: não se mexe
    if len(t) < 5 or re.search(r"[_\\/|{}=<>@#$^~`%*]|\.(bin|dat|tim|str|xa|exe|ovl|bmp|vab)\b", t, re.I):
        return False
    words = [w.strip(".,!?'\":;()-") for w in t.split()]
    words = [w for w in words if w]
    if len(words) < 2:
        return False
    alpha = [w for w in words if w.isalpha()]
    if len(alpha) < max(2, int(0.75 * len(words) + 0.5)):
        return False
    for w in alpha:  # forma de palavra: minúscula, Capitalizada ou TODA MAIÚSCULA; com vogal; tamanho normal
        if not (w.islower() or w.isupper() or (w[0].isupper() and w[1:].islower())) or len(w) > 16:
            return False
        vowel = re.search(r"[aeiouyAEIOUY]", w)
        if len(w) == 2 and not vowel and not w.isupper():
            return False  # "nq" (sigla como "CD" pode)
        if len(w) >= 3 and (not vowel or not re.search(r"[^aeiouAEIOU]", w)):
            return False  # sem vogal ("Bh4") ou só vogais ("EAI")
    long_ = [w for w in alpha if len(w) >= 2]
    if len(long_) < 2 or sum(map(len, long_)) < 6:
        return False  # "on Tu"
    if len(long_) <= 3 and any(w.isupper() for w in long_) and any(w.islower() for w in long_):
        return False  # trecho curto misturando "nq NO", "yb SO": texto de jogo não faz isso
    low = [w.lower() for w in long_]
    if sum(w in COMMON_WORDS for w in low) >= (1 if len(low) <= 4 else 2):
        return True
    # título/menu em maiúsculas ("VISIT TO THEBES", "BATTLE OF TITANS")
    return all(w.isupper() for w in alpha) and sum(len(w) >= 3 for w in alpha) >= 2


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).replace("ç", "c")


def _run(args: list[str], timeout: int = 7200) -> dict:
    exe = bin_path()
    if not exe:
        raise RuntimeError("RomTranslate não instalado: rode ./setup-deck.sh --modules A1")
    r = subprocess.run([exe, "--json", *args], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        msg = (r.stderr or r.stdout).strip()
        raise RuntimeError(msg.splitlines()[-1][:300] if msg else f"romtranslate {args[0]} falhou ({r.returncode})")
    line = (r.stdout.strip().splitlines() or ["{}"])[-1]
    try:
        return json.loads(line)
    except ValueError:
        return {"raw": line}


def output_name(rom: Path) -> Path:
    stem = re.sub(r"\s*\((pt-?br|br)\)\s*$", "", rom.stem, flags=re.I)
    return rom.with_name(f"{stem} (PT-BR){rom.suffix}")


def _write_cue(orig_cue: Path, data_bin: str, new_bin: Path) -> Path:
    """.cue novo apontando a trilha de dados para o .bin traduzido (as de áudio continuam as originais)."""
    txt = orig_cue.read_text("utf-8", "replace")
    new = re.sub(r'FILE\s+"' + re.escape(data_bin) + r'"', f'FILE "{new_bin.name}"', txt, count=1)
    out = output_name(orig_cue)
    out.write_text(new, "utf-8")
    return out


def translate_rom(paths: Paths, rom: Path, console: str, title: str = "", chain=None,
                  progress=lambda d, t: None, should_pause=lambda: False,
                  log: Callable[[str], None] = lambda s: None) -> RtsReport:
    cfg = ia.load_cfg(paths)
    rep = RtsReport(str(rom))
    ok, why = supported(console, rom)
    if not ok:
        rep.errors.append(why)
        return rep
    proj = paths.data / "traducao" / "rts" / (re.sub(r"\W+", "_", rom.stem)[:60] + ".rtsproj")
    if not proj.exists():
        proj.parent.mkdir(parents=True, exist_ok=True)
        _run(["create", str(rom), str(proj), "--target", "pt-BR", "--source", "en-US"])
    ex = _run(["extract", str(proj)])
    if not ex.get("saved"):
        _run(["scan", str(proj), "--only-text"])
    exp = proj / "exports" / "deck-commander.json"
    _run(["export", str(proj), str(exp), "--format", "json"])
    entries = json.loads(exp.read_text("utf-8"))
    rep.found = len(entries)
    picked = [e for e in entries if e.get("sourceText") and is_sentence(e["sourceText"])
              and e.get("status") != "not_text"]
    multi = [e for e in picked if "\n" in e["sourceText"]]
    picked = [e for e in picked if "\n" not in e["sourceText"]]  # o "apply" do RomTranslate é uma frase por linha
    rep.skipped_multiline = len(multi)
    rep.candidates = len(picked)
    if rep.candidates < MIN_SENTENCES:
        rep.errors.append("quase não há texto comum neste jogo (falas em voz/imagem ou texto comprimido); "
                          "nada foi alterado")
        return rep
    items, codes, enc = [], {}, {}
    for e in picked:
        prot, cs = ia.protect(e["sourceText"], RETRO_CODES)
        codes[e["id"]] = cs
        enc[e["id"]] = (e.get("encoding") or "").lower()
        items.append(ia.Item(e["id"], prot, max_len=int(e.get("maxBytes") or 0) or None))
    res = ia.translate(paths, cfg, items, f"rts-{proj.stem}", ia.load_glossary(paths, title), chain=chain,
                       progress=progress, should_pause=should_pause)
    rep.provider, rep.flagged = res.provider_used, len(res.flagged)
    rep.errors += res.errors[:3]
    lines = []
    for e in picked:
        t = res.translated.get(e["id"])
        if t is None:
            continue
        t = ia.restore(t, codes[e["id"]])
        if enc[e["id"]] in NO_ACCENT_ENCODINGS or not enc[e["id"]]:
            t = strip_accents(t)
        if len(t.encode("utf-8" if enc[e["id"]] not in NO_ACCENT_ENCODINGS else "ascii", "replace")) > int(
                e.get("maxBytes") or 10**9) or "\t" in t or "\n" in t:
            rep.flagged += 1
            continue
        lines.append(f"{e['id']}\t{t}")
    if not lines:
        rep.errors.append("nenhuma tradução coube no espaço original; nada foi alterado")
        return rep
    tsv = proj / "exports" / "deck-commander.tsv"
    tsv.write_text("\n".join(lines) + "\n", "utf-8")
    _run(["apply", str(proj), str(tsv)])
    ri = _run(["reinsert", str(proj), "--policy", "skip"], timeout=3 * 3600)
    working = Path(ri.get("workingPath") or ri.get("working_path") or "")
    if not working.is_file():
        cands = sorted((proj / "working").glob("*"), key=lambda p: p.stat().st_size, reverse=True)
        working = next((c for c in cands if c.suffix != ".tmp"), Path())
    if not working.is_file():
        rep.errors.append("o RomTranslate não gerou a cópia traduzida")
        return rep
    rep.translated = int(ri.get("written") or ri.get("applied") or len(lines))
    try:
        au = _run(["audit", str(proj)])
        rep.audit_left = int(au.get("remaining") or au.get("sourceLanguage") or au.get("untranslated") or 0)
    except (RuntimeError, ValueError, TypeError) as e:
        rep.errors.append(f"conferência: {e}")
    if rom.suffix.lower() == ".cue":
        new_bin = rom.with_name(output_name(working).name)
        shutil.copyfile(working, new_bin)
        rep.output = str(_write_cue(rom, working.name, new_bin))
    else:
        out = output_name(rom)
        shutil.copyfile(working, out)
        rep.output = str(out)
    try:
        pt = _run(["patch", str(proj), "--format", "bps"])
        p = Path(pt.get("patch") or pt.get("path") or next(iter((proj / "exports").glob("*.bps")), ""))
        if p.is_file():
            dst = Path(rep.output).with_suffix(".bps")
            shutil.copyfile(p, dst)
            rep.patch = str(dst)
    except RuntimeError as e:
        rep.errors.append(f"patch: {e}")
    return rep
