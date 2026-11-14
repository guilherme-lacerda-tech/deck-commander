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
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..paths import Paths
from . import ia

H = Path.home()
BIN_CANDIDATES = [H / ".local/share/deck-commander/bin/romtranslate"]
SUPPORTED = {"psx", "ps2", "psp", "gba", "snes", "n64", "gc", "nds", "nes", "gb", "gbc", "genesis", "sms", "gg",
             "segacd", "saturn", "pce"}
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
    audit_left: int | None = None
    provider: str = ""
    output: str = ""
    patch: str = ""
    errors: list[str] = field(default_factory=list)
    source_lang: str = ""
    encoding: str = ""

    def text(self) -> str:
        L = [f"trechos achados: {self.found} · frases de verdade: {self.candidates} · traduzidas e gravadas: "
             f"{self.translated}",
             f"ficaram no original: {self.flagged} (não coube no espaço / IA errou)"
             + (f" + {self.skipped_multiline} com várias linhas" if self.skipped_multiline else ""),
             f"IA: {self.provider or '-'}"
             + (f" · idioma original: {self.source_lang}" if self.source_lang else "")
             + (f" · codificação: {self.encoding}" if self.encoding and self.encoding != "padrão" else "")]
        if self.audit_left is not None:
            L.append(f"conferência na cópia gravada: {self.audit_left} trecho(s) ainda em inglês")
        L += [f"⚠️ {e}" for e in self.errors[:5]]
        if self.output:
            L.append(f"jogo traduzido: {Path(self.output).name}" + (f" · patch: {Path(self.patch).name}" if self.patch else ""))
        return "\n".join(L)


def bin_path() -> str | None:
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


def is_sentence(text: str) -> bool:
    """Frase que alguém lê no jogo, em qualquer língua (regras em dc.traducao.idioma). Rígido de propósito:
    a varredura genérica acha muito lixo (bytes de dados que parecem letras), e gravar tradução em cima de
    dado quebra o jogo."""
    from .idioma import is_sentence as _s
    return _s(text)


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


def restantes(au: dict) -> int:
    """Trechos que ficaram no idioma de origem segundo o `romtranslate audit --json`. O campo "remaining" é a LISTA
    dos trechos (falha real 14/11/2026, Nova the Squirrel: int(lista) quebrava a conferência)."""
    for chave in ("remaining", "sourceLanguage", "untranslated"):
        v = au.get(chave)
        if isinstance(v, list):
            return len(v)
        if v not in (None, ""):
            try:
                return int(v)
            except (TypeError, ValueError):
                continue
    return 0


def output_name(rom: Path) -> Path:
    stem = re.sub(r"\s*\((pt-?br|br)\)\s*$", "", rom.stem, flags=re.IGNORECASE)
    return rom.with_name(f"{stem} (PT-BR){rom.suffix}")


def _write_cue(orig_cue: Path, data_bin: str, new_bin: Path) -> Path:
    """.cue novo apontando a trilha de dados para o .bin traduzido (as de áudio continuam as originais)."""
    txt = orig_cue.read_text("utf-8", "replace")
    new = re.sub(r'FILE\s+"' + re.escape(data_bin) + r'"', f'FILE "{new_bin.name}"', txt, count=1)
    out = output_name(orig_cue)
    out.write_text(new, "utf-8")
    return out


def _project(paths: Paths, rom: Path, tag: str) -> Path:
    proj = paths.data / "traducao" / "rts" / (re.sub(r"\W+", "_", rom.stem)[:60] + (f".{tag}" if tag else "") + ".rtsproj")
    if not proj.exists():
        proj.parent.mkdir(parents=True, exist_ok=True)
        _run(["create", str(rom), str(proj), "--target", "pt-BR", "--source", "en-US"])
    return proj


def _export(proj: Path) -> list[dict]:
    exp = proj / "exports" / "deck-commander.json"
    _run(["export", str(proj), str(exp), "--format", "json"])
    return json.loads(exp.read_text("utf-8"))


def _pick(entries: list[dict]) -> list[dict]:
    return [e for e in entries if e.get("sourceText") and is_sentence(e["sourceText"]) and e.get("status") != "not_text"]


def _best_extraction(paths: Paths, rom: Path, log=lambda s: None) -> tuple[Path, list, list, str]:
    """Extração estruturada do RomTranslate; se achar pouca frase, tenta outras codificações (UTF-8, UTF-16 e
    tabelas cirílicas CP1251/CP866/KOI8-R — versões russas de jogos de PlayStation costumam usar uma delas),
    cada uma em projeto separado, e fica com a que tiver mais frases de verdade."""
    from . import idioma
    proj = _project(paths, rom, "")
    ex = _run(["extract", str(proj)])
    if not ex.get("saved"):
        _run(["scan", str(proj), "--only-text"])
    entries = _export(proj)
    best = (proj, entries, _pick(entries), "padrão")
    if len(best[2]) >= 50:
        return best
    tries = [("utf8", ["--encoding", "utf8"]), ("utf16le", ["--encoding", "utf16_le"])]
    for codec in idioma.CYRILLIC_CODECS:
        tbl = idioma.write_tbl(paths.data / "traducao" / "tbl" / f"{codec}.tbl", codec)
        tries.append((codec, ["--encoding", "table", "--tbl", str(tbl)]))
    for tag, args in tries:
        try:
            p = _project(paths, rom, tag)
            _run(["scan", str(p), "--only-text", *args], timeout=3 * 3600)
            ents = _export(p)
        except (RuntimeError, ValueError, OSError) as e:
            log(f"varredura {tag}: {e}")
            continue
        picked = _pick(ents)
        log(f"varredura {tag}: {len(picked)} frases")
        if len(picked) > len(best[2]):
            best = (p, ents, picked, tag)
    return best


def translate_rom(paths: Paths, rom: Path, console: str, title: str = "", chain=None,
                  progress=lambda d, t: None, should_pause=lambda: False,
                  log: Callable[[str], None] = lambda s: None) -> RtsReport:
    cfg = ia.load_cfg(paths)
    rep = RtsReport(str(rom))
    ok, why = supported(console, rom)
    if not ok:
        rep.errors.append(why)
        return rep
    proj, entries, picked, enc_used = _best_extraction(paths, rom, log)
    rep.found = len(entries)
    multi = [e for e in picked if "\n" in e["sourceText"]]
    picked = [e for e in picked if "\n" not in e["sourceText"]]  # o "apply" do RomTranslate é uma frase por linha
    rep.skipped_multiline = len(multi)
    rep.candidates = len(picked)
    if rep.candidates < MIN_SENTENCES:
        rep.errors.append("quase não há texto comum neste jogo (falas em voz/imagem, texto comprimido ou "
                          "codificação desconhecida); nada foi alterado")
        return rep
    from . import idioma
    ok, why = idioma.extraction_is_clean([e["sourceText"] for e in picked], idioma.language_from_name(rom.name))
    if not ok:
        rep.errors.append(f"não traduzi para não estragar o jogo: {why}; precisa de engenharia reversa do "
                          "formato de texto deste jogo. Nada foi alterado")
        return rep
    src = idioma.dominant_language([e["sourceText"] for e in picked]) or "en"
    cfg["idioma_origem"] = src  # traduz a partir da língua em que o jogo veio (russo, japonês, inglês…)
    rep.source_lang, rep.encoding = src, enc_used
    items, codes, enc = [], {}, {}
    for e in picked:
        prot, cs = ia.protect(e["sourceText"], RETRO_CODES)
        codes[e["id"]] = cs
        enc[e["id"]] = (e.get("encoding") or "").lower()
        items.append(ia.Item(e["id"], prot, max_len=int(e.get("maxBytes") or 0) or None))
    res = ia.translate(paths, cfg, items, f"rts-{proj.stem}", ia.load_glossary_jogo(paths, cfg, items, title), chain=chain,
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
        rep.audit_left = restantes(au)
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
