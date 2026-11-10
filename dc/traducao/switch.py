"""A2 — Tradução de jogos de Switch como MOD (LayeredFS) do Ryujinx.

Diferença para o plano original: nada de remontar NSP/XCI. O Ryujinx carrega arquivos de
`mods/contents/<titleid>/<mod>/romfs/` por cima do jogo, então o jogo original nunca é alterado e
desfazer = apagar/desligar a pasta do mod.

Entrada: o RomFS extraído do jogo (Ryujinx → botão direito no jogo → Extrair dados → RomFS, para
~/Emulation/romfs/<TitleID>/), ou extração automática com hactool se ele estiver instalado.
Segurança: todo MSBT/SARC precisa sobreviver a ler+regravar SEM mudar um byte antes de ser traduzido;
o que não passar é pulado e aparece no relatório.
"""
from __future__ import annotations

import difflib
import json
import os
import re
import shutil
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ..paths import Paths
from . import ia, nx

H = Path.home()
RYU_DIRS = [H / ".config/Ryujinx", H / ".var/app/io.github.ryubing.Ryujinx/config/Ryujinx"]
MOD_NAME = "Deck Commander PT-BR"
ARCHIVE_EXT = {".sarc", ".szs", ".zs", ".pack", ".arc", ".blarc", ".bfarc", ".sbfarc"}  # .sbfarc: fontes (BotW)
_LANG = re.compile(r"(?<![A-Za-z])(US|EU|JP|KR|CN|TW)(en|es|fr|de|it|nl|ru|ja|ko|zh|pt)(?![a-z])|"
                   r"(?<![A-Za-z])(en|es|fr|de|it|nl|ru|ja|ko|zh|pt)[-_](US|GB|ES|MX|FR|CA|DE|IT|NL|RU|JP|KR|CN|TW|BR|PT)"
                   r"(?![A-Za-z])|(?<![A-Za-z])(English|Spanish|French|German|Italian|Japanese|Dutch|Russian)(?![a-z])")


@dataclass
class TextFile:
    rel: str                    # caminho dentro do romfs
    inner: Optional[str]        # nome dentro do SARC (None = MSBT solto)
    msbt: nx.Msbt


@dataclass
class Report:
    title_id: str
    msbt_count: int = 0
    strings: int = 0
    translated: int = 0
    flagged: int = 0
    review: int = 0
    skipped_files: list[str] = field(default_factory=list)
    compression: set = field(default_factory=set)
    font: str = "fonte do sistema (tem acentos)"
    font_ok: bool = True
    similarity: Optional[float] = None
    reference: str = ""
    provider: str = ""
    tokens: int = 0
    mod_dir: str = ""
    applied: bool = False
    errors: list[str] = field(default_factory=list)
    version: Optional[dict] = None  # de qual versão do jogo o mod foi feito ({'base':…, 'update': nome|None})
    flagged_samples: list[str] = field(default_factory=list)
    rescued: int = 0      # 2ª chance: códigos remontados
    by_pieces: int = 0    # ... dessas, traduzidas por pedaços
    shortened: int = 0    # 2ª chance: encurtadas para caber na caixa

    def pct_flagged(self) -> float:
        return 100.0 * self.flagged / max(1, self.strings)

    def text(self) -> str:
        L = [f"MSBT: {self.msbt_count} · frases: {self.strings} · traduzidas: {self.translated}",
             f"com problema (original mantido): {self.flagged} ({self.pct_flagged():.1f}%) · para revisar: {self.review}",
             f"fonte: {self.font}", f"IA: {self.provider or '-'} · tokens: {self.tokens}"]
        if self.rescued or self.shortened:
            L.append(f"2ª chance: {self.rescued} frases com códigos refeitas"
                     + (f" ({self.by_pieces} por pedaços)" if self.by_pieces else "")
                     + f" · {self.shortened} encurtadas para caber na caixa")
        if self.compression:
            L.append("compressão: " + ", ".join(sorted(self.compression)))
        if self.similarity is not None:
            L.append(f"parecida com a referência ({self.reference}): {self.similarity:.0%}")
        if self.skipped_files:
            L.append(f"arquivos pulados ({len(self.skipped_files)}): " + "; ".join(self.skipped_files[:3]))
        L += [f"⚠️ {e}" for e in self.errors[:5]]
        L.append(("✅ mod ativo em " if self.applied else "⏸ mod guardado (não aplicado) em ") + self.mod_dir)
        return "\n".join(L)


# ----------------------------------------------------------------------------- localizar
def ryujinx_dir() -> Path:
    return next((d for d in RYU_DIRS if d.exists()), RYU_DIRS[0])


def keys_path() -> Optional[Path]:
    for d in RYU_DIRS:
        p = d / "system/prod.keys"
        if p.exists():
            return p
    return None


def romfs_candidates(title_id: str) -> list[Path]:
    base = H / "Emulation/romfs"
    return [base / title_id / "romfs", base / title_id, base / title_id.lower() / "romfs", base / title_id.lower()]


def find_romfs(title_id: str) -> Optional[Path]:
    for c in romfs_candidates(title_id):
        if c.is_dir() and any(c.iterdir()):
            return c
    return None


def extract_with_hactool(rom: Path, title_id: str, log: Callable[[str], None] = print) -> Optional[Path]:
    """Extração automática (opcional) com hactool + prod.keys do próprio Ryujinx. Só jogo-base .nsp."""
    tool = shutil.which("hactool") or next((str(p) for p in (H / ".local/share/deck-commander/bin/hactool",)
                                            if p.exists()), None)
    keys = keys_path()
    if not tool or not keys or rom.suffix.lower() != ".nsp":
        return None
    work = H / "Emulation/romfs" / title_id / "_nca"
    out = H / "Emulation/romfs" / title_id / "romfs"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    try:
        subprocess.run([tool, "-k", str(keys), "-t", "pfs0", "--outdir", str(work), str(rom)],
                       check=True, capture_output=True, timeout=1800)
        ncas = sorted(work.glob("*.nca"), key=lambda p: p.stat().st_size, reverse=True)
        if not ncas:
            return None
        subprocess.run([tool, "-k", str(keys), "--romfsdir", str(out), str(ncas[0])],
                       check=True, capture_output=True, timeout=3600)
        return out if out.is_dir() and any(out.iterdir()) else None
    except (subprocess.SubprocessError, OSError) as e:
        log(f"hactool falhou: {e}")
        return None
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ----------------------------------------------------------------------------- idioma
def pick_language(rels: list[str], source: str = "en") -> list[str]:
    """Só os arquivos do idioma de origem (o jogo mostra esse idioma quando o console está em inglês)."""
    tagged = [(r, _LANG.search(r)) for r in rels]
    if not any(m for _, m in tagged):
        return rels
    prefs = {"en": [r"USen", r"en[-_]US", r"EUen", r"en[-_]GB", r"English", r"(?<![A-Za-z])en(?![a-z])"]}.get(
        source, [rf"(?<![A-Za-z])(US|EU)?{source}(?![a-z])"])
    for pat in prefs:
        sel = [r for r, m in tagged if m and re.search(pat, m.group(0))]
        if sel:
            return sel + [r for r, m in tagged if not m]
    return [r for r, m in tagged if not m] or rels


# ----------------------------------------------------------------------------- varredura
def _roundtrip_ok(raw: bytes, m: nx.Msbt) -> bool:
    return nx.write_msbt(m) == raw


def scan(romfs: Path, report: Report, source: str = "en") -> tuple[list[TextFile], dict]:
    """Encontra MSBT soltos e dentro de pacotes. Devolve (arquivos de texto, contêineres abertos)."""
    rels = sorted(str(p.relative_to(romfs)).replace(os.sep, "/") for p in romfs.rglob("*") if p.is_file())
    rels = pick_language(rels, source)
    files: list[TextFile] = []
    containers: dict[str, tuple[nx.Sarc, Optional[str], bytes]] = {}
    fonts: list[tuple[str, bytes]] = []
    for rel in rels:
        low = rel.lower()
        p = romfs / rel
        if low.endswith((".bffnt", ".bffnt.zs", ".bcfnt")):  # Switch / 3DS
            try:
                fonts.append((rel, nx.unpack_layer(rel, p.read_bytes())[0]))
            except nx.FormatError:
                pass
            continue
        if low.endswith(".msbt") or low.endswith(".msbt.zs"):
            raw = p.read_bytes()
            try:
                body, kind = nx.unpack_layer(rel, raw)
                m = nx.read_msbt(body)
                if not _roundtrip_ok(body, m):
                    report.skipped_files.append(f"{rel} (formato não reproduzido com exatidão)")
                    continue
                if kind:
                    report.compression.add(kind)
                    containers[rel] = (None, kind, raw)
                files.append(TextFile(rel, None, m))
            except nx.FormatError as e:
                report.skipped_files.append(f"{rel} ({e})")
            continue
        if Path(low).suffix in ARCHIVE_EXT or low.endswith(".sarc.zs"):
            raw = p.read_bytes()
            try:
                body, kind = nx.unpack_layer(rel, raw)
                if body[:4] != b"SARC":
                    continue
                s = nx.read_sarc(body)
            except nx.FormatError as e:
                report.skipped_files.append(f"{rel} ({e})")
                continue
            inner_txt = _scan_sarc(rel, s, "", report, fonts, containers)
            if inner_txt:
                if kind:
                    report.compression.add(kind)
                # o pacote também precisa sobreviver a ser regravado (com os mesmos arquivos)
                again = nx.read_sarc(nx.write_sarc(s))
                if again.files != s.files:
                    report.skipped_files.append(f"{rel} (pacote não reproduzido)")
                    continue
                containers[rel] = (s, kind, raw)
                files += inner_txt
    report.msbt_count = len(files)
    _check_fonts(fonts, report)
    return files, containers


NEST_SEP = "|"  # pacote dentro de pacote: inner = "Message/Msg_USen.product.ssarc|ActorType/Foo.msbt"
NESTED_EXT = ARCHIVE_EXT | {".ssarc", ".sblarc", ".sbfarc", ".sgenvb", ".sbactorpack"}
MAX_NEST = 3


def _scan_sarc(rel: str, s: "nx.Sarc", prefix: str, report: Report, fonts: list, containers: dict,
               depth: int = 0) -> list[TextFile]:
    """MSBT dentro de um SARC, abrindo SARC (com ou sem Yaz0/zstd) que estejam dentro dele — ex.: Zelda BotW:
    Pack/Bootup_USen.pack → Message/Msg_USen.product.ssarc (Yaz0) → *.msbt."""
    out: list[TextFile] = []
    for name, data in s.files.items():
        low, key = name.lower(), prefix + name
        if low.endswith(".msbt"):
            try:
                m = nx.read_msbt(data)
                if _roundtrip_ok(data, m):
                    out.append(TextFile(rel, key, m))
                else:
                    report.skipped_files.append(f"{rel}:{key} (formato não reproduzido)")
            except nx.FormatError as e:
                report.skipped_files.append(f"{rel}:{key} ({e})")
        elif low.endswith(".bffnt"):
            fonts.append((f"{rel}:{key}", data))
        elif depth < MAX_NEST and (data[:4] == b"SARC" or Path(low).suffix in NESTED_EXT):
            try:
                body, kind = nx.unpack_layer(name, data)
                if body[:4] != b"SARC":
                    continue
                sub = nx.read_sarc(body)
            except nx.FormatError as e:
                report.skipped_files.append(f"{rel}:{key} ({e})")
                continue
            inner = _scan_sarc(rel, sub, key + NEST_SEP, report, fonts, containers, depth + 1)
            if not inner:
                continue
            if nx.read_sarc(nx.write_sarc(sub)).files != sub.files:
                report.skipped_files.append(f"{rel}:{key} (pacote interno não reproduzido)")
                continue
            if kind:
                report.compression.add(kind)
            containers[rel + NEST_SEP + key] = (sub, kind, data)
            out += inner
    return out


def _rebuild_sarc(rel: str, sarc: "nx.Sarc", prefix: str, fs: list[TextFile], containers: dict) -> None:
    """Grava as traduções no SARC, remontando de dentro para fora os pacotes internos."""
    children: dict[str, list[TextFile]] = {}
    for f in fs:
        sub = f.inner[len(prefix):]
        if NEST_SEP in sub:
            children.setdefault(sub.split(NEST_SEP, 1)[0], []).append(f)
        else:
            sarc.files[sub] = nx.write_msbt(f.msbt)
    for name, cfs in children.items():
        key = prefix + name
        inner, kind, _raw = containers[rel + NEST_SEP + key]
        _rebuild_sarc(rel, inner, key + NEST_SEP, cfs, containers)
        data = nx.write_sarc(inner)
        packed = nx.pack_layer(data, kind)
        if nx.unpack_layer(name, packed)[0] != data:
            raise nx.FormatError(f"recompressão de {rel}:{key} não confere")
        sarc.files[name] = packed


def _inner_bytes(sarc: "nx.Sarc", inner: str) -> bytes:
    parts = inner.split(NEST_SEP)
    for name in parts[:-1]:
        sarc = nx.read_sarc(nx.unpack_layer(name, sarc.files[name])[0])
    return sarc.files[parts[-1]]


def _check_fonts(fonts: list[tuple[str, bytes]], report: Report) -> None:
    if not fonts:
        return  # usa a fonte do sistema do Switch, que tem os acentos
    missing, unread = {}, []
    for name, data in fonts:
        chars = nx.bffnt_chars(data)
        if chars is None:
            unread.append(name)
            continue
        miss = nx.missing_ptbr(chars)
        if miss:
            missing[name] = miss
    complete = [n for n, _ in fonts if n not in missing and n not in unread]
    if missing and complete:
        # o jogo tem fonte com todos os acentos (a do texto corrido); as que faltam costumam ser de título/logo
        # (BotW: Normal tem tudo, Caption/Special não têm ã/õ) — traduz e avisa onde pode aparecer quadradinho
        report.font = (f"fonte principal com os acentos ✅ ({Path(complete[0].split(':')[-1]).name}); "
                       f"⚠️ sem {'/'.join(sorted(set(''.join(missing.values()))))[:40]} em: "
                       + ", ".join(Path(n.split(":")[-1]).name for n in list(missing)[:4])
                       + " (títulos podem mostrar quadradinho)")
    elif missing:
        n, miss = next(iter(missing.items()))
        report.font = f"⚠️ a fonte do jogo não tem: {miss} ({n})"
        report.font_ok = False
    elif unread and len(unread) == len(fonts):
        report.font = "⚠️ não consegui ler as fontes do jogo para conferir os acentos"
        report.font_ok = False
    else:
        report.font = "fonte do jogo tem os acentos do português ✅"


# ----------------------------------------------------------------------------- referências
def load_references(paths: Paths) -> list[dict]:
    p = paths.config / "referencias.toml"
    if not p.exists():
        return []
    return tomllib.loads(p.read_text("utf-8")).get("ref", [])


def reference_pairs(ref: dict, source: str = "en") -> dict[str, tuple[str, str]]:
    """{rel#rótulo: (original, tradução)} alinhando por rótulo do MSBT (o mesmo jogo nas duas versões)."""
    orig, trad = Path(ref["original"]).expanduser(), Path(ref["traduzido"]).expanduser()
    out = {}
    r1, r2 = Report("ref"), Report("ref")
    a, _ = scan(orig, r1, source)
    b, _ = scan(trad, r2, ref.get("idioma_scan", source))
    bmap = {(f.rel, f.inner): f for f in b}
    for f in a:
        g = bmap.get((f.rel, f.inner))
        if not g:
            continue
        ta, tb = f.msbt.texts(), g.msbt.texts()
        for idx, label in f.msbt.labels.items():
            j = next((k for k, v in g.msbt.labels.items() if v == label), None)
            if j is not None and idx < len(ta) and j < len(tb):
                out[f"{f.rel}:{f.inner}#{label}"] = (ta[idx][0], tb[j][0])
    return out


# ----------------------------------------------------------------------------- pipeline
def item_id(f: TextFile, i: int) -> str:
    return f"{f.rel}:{f.inner or ''}#{i}"


def translate_game(paths: Paths, title_id: str, romfs: Path, game_name: str = "",
                   force_font: bool = False, chain=None, log: Callable[[str], None] = lambda s: None,
                   progress=lambda d, t: None, should_pause=lambda: False,
                   install: Optional[Callable[[str, Path], Path]] = None, tag: str = "switch") -> Report:
    """Traduz os MSBT de um RomFS e grava o mod. `install` decide onde o mod vai (padrão: Ryujinx);
    o 3DS (Azahar) e o Wii U (Cemu) usam a mesma tradução com outro destino."""
    cfg = ia.load_cfg(paths)
    sw = {"permitir_sem_fonte_ptbr": False, "validar_com_referencia": True, "similaridade_minima": 0.75}
    try:
        sw.update(tomllib.loads((paths.config / "traducao.toml").read_text("utf-8")).get("switch", {}))
    except (OSError, ValueError):
        pass
    rep = Report(title_id)
    try:  # carimbo da extração automática: guarda no mod de qual versão (base/atualização) os textos vieram
        rep.version = json.loads((romfs.parent / "extraido-por-deck-commander.json").read_text("utf-8"))
    except (OSError, ValueError):
        rep.version = None
    files, containers = scan(romfs, rep, cfg["idioma_origem"])
    if not files:
        rep.errors.append("nenhum texto MSBT encontrado neste RomFS")
        return rep
    if not rep.font_ok and not (force_font or sw.get("permitir_sem_fonte_ptbr")):
        rep.errors.append("tradução bloqueada: a fonte do jogo não mostra os acentos do português "
                          "(use /traduzir <jogo> --forcar para aplicar assim mesmo)")
        return rep
    # memória de tradução e few-shot a partir das referências
    memory, examples, ref_name = {}, [], ""
    for ref in load_references(paths):
        if ref.get("console") != tag:
            continue
        try:
            pairs = reference_pairs(ref, cfg["idioma_origem"])
        except (OSError, nx.FormatError, KeyError) as e:
            log(f"referência {ref.get('titulo')}: {e}")
            continue
        same = str(ref.get("title_id", "")).upper() == title_id.upper()
        if same:
            ref_name = ref.get("titulo", title_id)
            memory.update({o: t for o, t in pairs.values() if o and t})
        if cfg.get("few_shot"):
            examples += [p for p in pairs.values() if p[0] and p[1] and len(p[0]) < 160][:400]
    items, all_texts = [], {}
    for f in files:
        for i, (text, tags) in enumerate(f.msbt.texts()):
            iid = item_id(f, i)
            all_texts[iid] = (f, i, text, tags)
            if text.strip() and text not in memory:
                items.append(ia.Item(iid, text))
    rep.strings = len(all_texts)
    glossary = ia.load_glossary(paths, game_name)
    res = ia.translate(paths, cfg, items, f"{tag}-{title_id}", glossary, examples, chain=chain,
                       progress=progress, should_pause=should_pause)
    rep.provider, rep.tokens, rep.errors = res.provider_used, res.tokens, rep.errors + res.errors
    rep.flagged, rep.review = len(res.flagged), len(res.review)
    rep.flagged_samples = [f"{all_texts[k][2][:60]} → {v}" for k, v in list(res.flagged.items())[:20]]
    sims = []
    for iid, (f, i, text, tags) in all_texts.items():
        new = memory.get(text) or res.translated.get(iid)
        if new is None or new == text:
            continue
        if text in memory and iid in res.translated:
            sims.append(difflib.SequenceMatcher(None, res.translated[iid], memory[text]).ratio())
        f.msbt.set_text(i, new, tags)
        rep.translated += 1
    if sims:
        rep.similarity = sum(sims) / len(sims)
    rep.reference = ref_name
    return _write_mod(paths, rep, files, containers, cfg, install or install_mod)


def _write_mod(paths: Paths, rep: Report, files: list[TextFile], containers: dict, cfg: dict,
               install: Callable[[str, Path], Path] = None) -> Report:
    threshold = float(cfg.get("flagged_threshold", 10))
    stage = paths.data / "traducao" / "mods" / rep.title_id / "romfs"
    shutil.rmtree(stage.parent, ignore_errors=True)
    by_rel: dict[str, list[TextFile]] = {}
    for f in files:
        by_rel.setdefault(f.rel, []).append(f)
    for rel, fs in by_rel.items():
        dst = stage / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if fs[0].inner is None:
            data = nx.write_msbt(fs[0].msbt)
            nx.read_msbt(data)  # validação: precisa abrir de novo
            kind = containers.get(rel, (None, None, b""))[1]
            dst.write_bytes(nx.pack_layer(data, kind))
        else:
            sarc, kind, _raw = containers[rel]
            _rebuild_sarc(rel, sarc, "", fs, containers)
            data = nx.write_sarc(sarc)
            back = nx.read_sarc(data)
            for f in fs:
                nx.read_msbt(_inner_bytes(back, f.inner))
            packed = nx.pack_layer(data, kind)
            if nx.unpack_layer(rel, packed)[0] != data:
                raise nx.FormatError(f"recompressão de {rel} não confere")
            dst.write_bytes(packed)
    (stage.parent / "relatorio.json").write_text(json.dumps(
        {"title_id": rep.title_id, "msbt": rep.msbt_count, "strings": rep.strings, "translated": rep.translated,
         "flagged": rep.flagged, "flagged_samples": rep.flagged_samples, "font": rep.font,
         "skipped": rep.skipped_files}, ensure_ascii=False, indent=1), "utf-8")
    if rep.version is not None:
        (stage.parent / "versao.json").write_text(json.dumps(rep.version, ensure_ascii=False), "utf-8")
    rep.mod_dir = str(stage.parent)
    if rep.translated and rep.pct_flagged() <= threshold and not rep.errors:
        rep.mod_dir = str((install or install_mod)(rep.title_id, stage.parent))
        rep.applied = True
    return rep


def mod_target(title_id: str) -> Path:
    return ryujinx_dir() / "mods/contents" / title_id.lower() / MOD_NAME


def install_mod(title_id: str, staged: Path) -> Path:
    """Copia o mod para o Ryujinx (substitui só o mod do Deck Commander daquele jogo)."""
    dst = mod_target(title_id)
    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(staged / "romfs", dst / "romfs")
    return dst


def uninstall_mod(title_id: str) -> bool:
    dst = mod_target(title_id)
    if dst.exists():
        shutil.rmtree(dst)
        return True
    return False


def mod_version(title_id: str, data_dir: Optional[Path] = None) -> Optional[dict]:
    """De qual versão o mod de tradução foi feito (None = não se sabe: mods antigos, Z-A, LM3)."""
    if data_dir is None:
        from ..paths import get_paths
        data_dir = get_paths().data
    try:
        info = json.loads((data_dir / "traducao/mods" / title_id / "versao.json").read_text("utf-8"))
        return info if "update" in info else None
    except (OSError, ValueError):
        return None


def ensure_update_selected(title_id: str, roots: list[Path], data_dir: Optional[Path] = None) -> Optional[str]:
    """Antes de abrir, põe o Ryujinx na MESMA versão de que o mod de tradução foi feito (games/<tid>/updates.json).
    Versão diferente = textos que não batem (jogo em inglês ou travando — lição do LM3/Z-A). Se o mod guardou a
    versão (versao.json), vale ela — inclusive "sem atualização"; senão (mods antigos), a atualização mais nova.
    Devolve o que fez (ou None)."""
    if not mod_target(title_id).exists():
        return None
    from . import converter, extract
    tf = converter.collect(roots, title_id)
    info = mod_version(title_id, data_dir)
    hint = ""
    if info is None:
        want = extract.latest_update(tf)
        if not want:
            return None
        sel, label = str(want), f"a atualização {want.name}"
    elif info["update"] is None:
        sel, label = "", "a versão sem atualização"
        if extract.latest_update(tf):
            hint = " — para jogar com a atualização, refaça a tradução: /traduzir <jogo> --forcar"
    else:
        want = next((u for u in getattr(tf, "updates", []) or [] if u.name == info["update"]), None)
        if not want:
            return (f"⚠️ a tradução foi feita para a atualização {info['update']}, que não está mais no Deck: "
                    "refaça com /traduzir <jogo> --forcar")
        sel, label = str(want), f"a atualização {want.name}"
    for d in RYU_DIRS:
        f = d / "games" / title_id.lower() / "updates.json"
        if not f.parent.parent.exists():
            continue
        try:
            data = json.loads(f.read_text("utf-8"))
        except (OSError, ValueError):
            data = {"selected": "", "paths": []}
        if (data.get("selected") or "") == sel:
            return None
        data["selected"] = sel
        if sel:
            data["paths"] = sorted(set(data.get("paths") or []) | {sel})
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_name(f.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")
        os.replace(tmp, f)
        return f"tradução: selecionei {label} no Ryujinx (o mod foi feito para ela){hint}"
    return None
