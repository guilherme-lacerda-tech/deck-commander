"""A1 — Tradução retrô com o RomTranslate Studio (MIT): PS1, PS2, GBA, SNES, NES, N64, PSP, GameCube, DS…

O Deck Commander só orquestra o `romtranslate` (CLI compilado no Deck por `./setup-deck.sh --modules A1`):
  create -> extract (ou scan) -> translate -> validate -> reinsert -> audit -> patch
O original nunca é alterado: o RomTranslate grava numa cópia de trabalho; essa cópia vira o jogo
"<nome> (PT-BR)" na mesma pasta (e o atalho do original sai da biblioteca, sem duplicar).
IA: a mesma cadeia do traducao.toml (Index-Translate -> Ollama), escrita no formato do RomTranslate.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ..paths import Paths
from . import ia

H = Path.home()
BIN_CANDIDATES = [H / ".local/share/deck-commander/bin/romtranslate"]
# consoles do Deck Commander que o RomTranslate trata (cue/bin, iso, cartuchos)
SUPPORTED = {"psx", "ps2", "psp", "gba", "snes", "n64", "gc", "nds", "nes", "gb", "gbc", "genesis"}
UNSUPPORTED_EXT = {".chd": "CHD (comprimido)", ".cso": "CSO (comprimido)", ".rvz": "RVZ (comprimido)",
                   ".pbp": "PBP (comprimido)", ".m3u": "lista de discos (.m3u)", ".zip": "ZIP"}


@dataclass
class RtsReport:
    rom: str
    entries: int = 0
    translated: int = 0
    errors_left: int = 0
    audit_left: Optional[int] = None
    provider: str = ""
    output: str = ""
    patch: str = ""
    errors: list[str] = field(default_factory=list)

    def text(self) -> str:
        L = [f"frases encontradas: {self.entries} · traduzidas e gravadas: {self.translated}",
             f"com problema (ficaram no original): {self.errors_left}", f"IA: {self.provider or '-'}"]
        if self.audit_left is not None:
            L.append(f"conferência final: {self.audit_left} frase(s) ainda no idioma original")
        L += [f"⚠️ {e}" for e in self.errors[:5]]
        if self.output:
            L.append(f"jogo traduzido: {Path(self.output).name} · patch: {Path(self.patch).name if self.patch else '-'}")
        return "\n".join(L)


def bin_path() -> Optional[str]:
    for c in BIN_CANDIDATES:
        if c.exists():
            return str(c)
    return shutil.which("romtranslate")


def supported(console: str, rom: Path) -> tuple[bool, str]:
    if console not in SUPPORTED:
        return False, f"{console.upper()} não é tratado pelo RomTranslate Studio"
    why = UNSUPPORTED_EXT.get(rom.suffix.lower())
    if why:
        return False, f"o arquivo está em {why}; o RomTranslate precisa da imagem descomprimida (.iso/.bin+.cue)"
    return True, ""


def config_dir(paths: Paths, provider: str, cfg: dict) -> Path:
    """Escreve o settings.toml do RomTranslate para o provedor pedido (index_translate | ollama | ...)."""
    d = paths.data / "traducao" / "rts-config" / provider
    d.mkdir(parents=True, exist_ok=True)
    spec = cfg["providers"].get(provider, {})
    if spec.get("tipo") == "ollama":
        body = (f'provider = "ollama"\nbatchSize = 10\nparallel = 1\ntimeoutSecs = 300\n'
                f'[ollama]\nbaseUrl = "{spec.get("url", "http://127.0.0.1:11434")}"\nmodel = "{spec.get("modelo_rts", "qwen2.5:7b")}"\n')
    else:
        body = (f'provider = "openai_compatible"\nallowRemoteTranslation = true\nbatchSize = 8\nparallel = 2\n'
                f'timeoutSecs = 90\n[openaiCompatible]\nbaseUrl = "{spec.get("url")}"\nmodel = "{spec.get("modelo")}"\n')
        key = ia.secret(paths, spec["segredo"]) if spec.get("segredo") else (spec.get("chave") or "deck-commander")
        sec = d / "secrets.json"
        sec.write_text(json.dumps({"openai_api_key": key}), "utf-8")
        sec.chmod(0o600)
    (d / "settings.toml").write_text(body, "utf-8")
    return d


def _run(args: list[str], timeout: int = 7200, cwd: Optional[Path] = None) -> dict:
    exe = bin_path()
    if not exe:
        raise RuntimeError("RomTranslate não instalado: rode ./setup-deck.sh --modules A1")
    r = subprocess.run([exe, "--json", *args], capture_output=True, text=True, timeout=timeout, cwd=cwd)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip().splitlines()[-1][:300] if (r.stderr or r.stdout).strip()
                           else f"romtranslate {args[0]} falhou ({r.returncode})")
    line = (r.stdout.strip().splitlines() or ["{}"])[-1]
    try:
        return json.loads(line)
    except ValueError:
        return {"raw": line}


def _num(d: dict, *keys) -> int:
    for k in keys:
        v = d.get(k)
        if isinstance(v, int):
            return v
    return 0


def output_name(rom: Path) -> Path:
    stem = re.sub(r"\s*\((pt-?br|br)\)\s*$", "", rom.stem, flags=re.I)
    return rom.with_name(f"{stem} (PT-BR){rom.suffix}")


def translate_rom(paths: Paths, rom: Path, console: str, log: Callable[[str], None] = lambda s: None,
                  source: str = "en-US") -> RtsReport:
    cfg = ia.load_cfg(paths)
    rep = RtsReport(str(rom))
    proj = paths.data / "traducao" / "rts" / (re.sub(r"\W+", "_", rom.stem)[:60] + ".rtsproj")
    if not proj.exists():
        _run(["create", str(rom), str(proj), "--target", "pt-BR", "--source", source])
    ex = _run(["extract", str(proj)])
    rep.entries = _num(ex, "entries", "count", "extracted", "total")
    if rep.entries == 0:  # extração estruturada não achou: varredura genérica de texto
        sc = _run(["scan", str(proj), "--only-text"])
        rep.entries = _num(sc, "entries", "count", "found", "total")
    if rep.entries == 0:
        rep.errors.append("nenhum texto encontrado (o jogo pode guardar o texto comprimido ou como imagem)")
        return rep
    chain = [p for p in [cfg["provider"], *cfg.get("fallback", [])] if p in cfg["providers"]]
    for i, prov in enumerate(chain):
        spec = cfg["providers"][prov]
        if spec.get("segredo") and not ia.secret(paths, spec["segredo"]):
            continue
        try:
            args = ["translate", str(proj), "--config-dir", str(config_dir(paths, prov, cfg))]
            if i > 0 or rep.provider:
                args.append("--redo-errors")
            _run(args, timeout=6 * 3600)
            rep.provider = rep.provider or prov
            v = _run(["validate", str(proj)])
            if _num(v, "errors", "invalid", "issues") == 0:
                break
        except (RuntimeError, subprocess.TimeoutExpired) as e:
            rep.errors.append(f"{prov}: {e}")
            continue
    v = _run(["validate", str(proj)])
    rep.errors_left = _num(v, "errors", "invalid", "issues")
    ri = _run(["reinsert", str(proj), "--policy", "skip"], timeout=3 * 3600)
    working = Path(ri.get("working_path") or ri.get("workingPath") or "")
    if not working.is_file():
        cands = sorted((proj / "working").glob("*"), key=lambda p: p.stat().st_size, reverse=True)
        working = cands[0] if cands else Path()
    if not working.is_file():
        rep.errors.append("o RomTranslate não gerou a cópia traduzida")
        return rep
    rep.translated = _num(ri, "written", "applied", "reinserted", "count")
    try:
        au = _run(["audit", str(proj)])
        rep.audit_left = _num(au, "remaining", "untranslated", "source_language", "count")
    except RuntimeError as e:
        rep.errors.append(f"conferência: {e}")
    try:
        pt = _run(["patch", str(proj), "--format", "bps"])
        rep.patch = pt.get("patch") or pt.get("path") or str(next((proj / "exports").glob("*.bps"), ""))
    except RuntimeError as e:
        rep.errors.append(f"patch: {e}")
    out = output_name(rom)
    if out.exists():
        out.unlink()
    shutil.copyfile(working, out)
    if rom.suffix.lower() == ".bin":
        pass
    rep.output = str(out)
    if rep.patch and Path(rep.patch).exists():
        shutil.copyfile(rep.patch, out.with_suffix(".bps"))
        rep.patch = str(out.with_suffix(".bps"))
    return rep
