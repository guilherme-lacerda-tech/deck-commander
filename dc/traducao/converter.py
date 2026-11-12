"""A3 — /converter: normalizar jogos de Switch no Deck.

O que o plano original pedia e por que mudou:
- fundir base+update+DLC num arquivo: o Ryujinx já carrega update/DLC separados (pastas de
  carregamento automático) — fundir só gasta espaço e tempo. Aqui: ORGANIZAR numa pasta por jogo.
- NSP<->XCI: o Ryujinx abre os dois; não há ganho. Não é feito.
- dividir para FAT32: só importa se o cartão for FAT32 (o do Deck normalmente é ext4/exFAT) —
  detectado e avisado.
- NSZ/XCZ: descompactados com a ferramenta `nsz` (se instalada), usando as chaves do seu Ryujinx;
  o arquivo comprimido vai para a quarentena (30 dias), nunca é apagado.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .. import dedup
from ..paths import Paths
from ..quarantine import quarantine

H = Path.home()
SWITCH_EXT = {".nsp", ".xci", ".nsz", ".xcz"}
FAT32_MAX = 4 * 1024**3 - 1


@dataclass
class TitleFiles:
    base_tid: str
    base: list[Path] = field(default_factory=list)
    updates: list[Path] = field(default_factory=list)
    dlc: list[Path] = field(default_factory=list)
    unknown: list[Path] = field(default_factory=list)

    def all(self) -> list[Path]:
        return self.base + self.updates + self.dlc


def kind_of(name: str) -> str | None:
    m = re.search(r"\[([0-9A-Fa-f]{16})\]", name)
    if not m:
        return None
    v = int(m.group(1), 16)
    return "base" if v & 0x1FFF == 0 else "update" if v & 0x1FFF == 0x800 else "dlc"


def collect(roots: list[Path], base_tid: str) -> TitleFiles:
    tf = TitleFiles(base_tid.upper())
    for root in roots:
        d = root / "switch"
        if not d.is_dir():
            continue
        for f in d.rglob("*"):
            if f.is_file() and f.suffix.lower() in SWITCH_EXT and dedup.base_title_id(f.name) == tf.base_tid:
                {"base": tf.base, "update": tf.updates, "dlc": tf.dlc}.get(kind_of(f.name), tf.unknown).append(f)
    return tf


def fs_type(path: Path) -> str:
    try:
        r = subprocess.run(["findmnt", "-no", "FSTYPE", "-T", str(path)], capture_output=True, text=True, timeout=5)
        return r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def looks_valid(p: Path) -> bool:
    with open(p, "rb") as f:
        head = f.read(0x110)
    return head[:4] == b"PFS0" or head[0x100:0x104] == b"HEAD"


def diagnose(tf: TitleFiles, title: str) -> list[str]:
    L = [f"{title} [{tf.base_tid}]",
         f"• jogo-base: {len(tf.base)} · atualizações: {len(tf.updates)} · DLC: {len(tf.dlc)}"]
    if not tf.base:
        L.append("⚠️ não achei o jogo-base (só atualização/DLC?)")
    comp = [p for p in tf.all() if p.suffix.lower() in (".nsz", ".xcz")]
    if comp:
        L.append(f"• comprimidos (NSZ/XCZ): {len(comp)} — /converter {title} descompactar")
    folders = {p.parent for p in tf.all()}
    if len(folders) > 1:
        L.append(f"• espalhado em {len(folders)} pastas — /converter {title} organizar")
    big_fat = [p for p in tf.all() if p.stat().st_size > FAT32_MAX and fs_type(p) == "vfat"]
    if big_fat:
        L.append("⚠️ arquivo maior que 4 GB num cartão FAT32: formate o cartão em exFAT/ext4 (dividir não é suportado)")
    bad = [p.name for p in tf.all() if p.suffix.lower() in (".nsp", ".xci") and not looks_valid(p)]
    if bad:
        L.append(f"⚠️ arquivo que não parece NSP/XCI válido: {bad[:3]}")
    if len(L) == 2:
        L.append("✅ nada a fazer: o Ryujinx já abre assim (atualização e DLC entram sozinhas)")
    return L


def organize(tf: TitleFiles, title: str) -> list[str]:
    """Move base/update/DLC para '<Título> [TitleID]/' na mesma pasta switch do jogo-base. Só move."""
    if not tf.base:
        return ["sem jogo-base: nada movido"]
    root = next(p for p in tf.base[0].parents if p.name == "switch")
    safe = re.sub(r'[<>:"/\\|?*]', "", title).strip() or tf.base_tid
    dest = root / f"{safe} [{tf.base_tid}]"
    dest.mkdir(exist_ok=True)
    out = []
    for p in tf.all():
        if p.parent == dest:
            continue
        target = dest / p.name
        if target.exists():
            out.append(f"já existe, não movido: {p.name}")
            continue
        if p.stat().st_dev != dest.stat().st_dev:
            out.append(f"em outro disco, não movido: {p.name}")
            continue
        p.rename(target)
        out.append(f"movido: {p.name}")
        try:
            p.parent.rmdir()  # pasta antiga ficou vazia
        except OSError:
            pass
    return out or ["já estava organizado"]


def nsz_bin() -> str | None:
    for c in (H / ".local/share/deck-commander/nsz-venv/bin/nsz",):
        if c.exists():
            return str(c)
    return shutil.which("nsz")


def ensure_keys() -> bool:
    """A ferramenta nsz procura as chaves em ~/.switch/prod.keys: aponta para as do seu Ryujinx."""
    from .switch import keys_path
    src = keys_path()
    dst = H / ".switch/prod.keys"
    if dst.exists():
        return True
    if not src:
        return False
    dst.parent.mkdir(exist_ok=True)
    dst.symlink_to(src)
    return True


def decompress_temp(p: Path, work: Path) -> Path | None:
    """Descompacta um .nsz/.xcz numa pasta temporária SÓ para ler (o arquivo da biblioteca não muda).
    Devolve o .nsp/.xci temporário, ou None se não der (sem nsz, sem chaves, sem espaço)."""
    tool = nsz_bin()
    if not tool or not ensure_keys():
        return None
    work.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(work).free < p.stat().st_size * 2:
        return None
    r = subprocess.run([tool, "-D", "-o", str(work), str(p)], capture_output=True, text=True, timeout=7200)
    made = [f for f in work.iterdir() if f.suffix.lower() in (".nsp", ".xci") and f.stem == p.stem]
    if r.returncode != 0 or len(made) != 1 or not looks_valid(made[0]):
        return None
    return made[0]


def decompress(paths: Paths, tf: TitleFiles) -> list[str]:
    tool = nsz_bin()
    if not tool:
        return ["a ferramenta nsz não está instalada: rode ./setup-deck.sh --modules A3"]
    if not ensure_keys():
        return ["sem prod.keys no Ryujinx — abra um jogo no Ryujinx primeiro"]
    out = []
    for p in [x for x in tf.all() if x.suffix.lower() in (".nsz", ".xcz")]:
        need = p.stat().st_size * 2
        if shutil.disk_usage(p.parent).free < need:
            out.append(f"sem espaço para descompactar {p.name}"); continue
        tmp = p.parent / ".dc-descompactando"
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir()
        r = subprocess.run([tool, "-D", "-o", str(tmp), str(p)], capture_output=True, text=True, timeout=7200)
        made = [f for f in tmp.iterdir() if f.suffix.lower() in (".nsp", ".xci")]
        if r.returncode != 0 or len(made) != 1 or not looks_valid(made[0]) or made[0].stat().st_size < p.stat().st_size:
            shutil.rmtree(tmp, ignore_errors=True)
            out.append(f"❌ {p.name}: não descompactou ({(r.stderr or '').strip()[-120:]})"); continue
        final = p.with_suffix(made[0].suffix)
        if final.exists():
            shutil.rmtree(tmp, ignore_errors=True)
            out.append(f"já existe {final.name}; nada feito"); continue
        os.replace(made[0], final)
        shutil.rmtree(tmp, ignore_errors=True)
        from ..remove import (
            _quarantine_root,  # no cartão SD, a quarentena fica no próprio cartão
        )
        q = quarantine(p, _quarantine_root(p, paths.quarantine), f"original comprimido de {final.name} (descompactado)")
        out.append(f"✅ {p.name} → {final.name} (original na quarentena: {q.name})")
    return out or ["nada comprimido"]
