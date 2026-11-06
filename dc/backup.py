"""M0.1/M0.2 — Backup verificado, fallback para o anterior, quarentena e restore.

Fluxo de criação: cópia em pasta temporária -> manifesto SHA-256 -> re-hash ->
test-restore em sandbox (configs; ROMs = amostral, correção F10) -> só então vira snapshot.
Falha em qualquer etapa -> quarentena (nunca apaga).
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Optional

from .quarantine import quarantine

MANIFEST = "manifest.json"
STEAM_SENSITIVE = ("shortcuts.vdf", "localconfig.vdf")


class BackupError(RuntimeError):
    pass


class AllBackupsCorrupt(BackupError):
    pass


@dataclass
class SnapshotResult:
    ok: bool
    path: Optional[Path]
    warnings: list[str] = field(default_factory=list)
    error: Optional[str] = None


def sha256_file(p: Path, bufsize: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(bufsize):
            h.update(chunk)
    return h.hexdigest()


def _iter_files(src: Path) -> Iterable[Path]:
    if src.is_file():
        yield src
    elif src.is_dir():
        for p in sorted(src.rglob("*")):
            if p.is_file() and not p.is_symlink():
                yield p


def _size_of(sources: dict[str, Path]) -> int:
    return sum(f.stat().st_size for s in sources.values() for f in _iter_files(Path(s)))


def same_device(a: Path, b: Path) -> bool:
    """Correção F15: compara st_dev (df engana com bind mounts)."""
    def existing(p: Path) -> Path:
        p = Path(p).resolve()
        while not p.exists():
            p = p.parent
        return p
    return os.stat(existing(a)).st_dev == os.stat(existing(b)).st_dev


def _hash_tree(data_dir: Path) -> dict[str, dict]:
    return {f.relative_to(data_dir).as_posix(): {"sha256": sha256_file(f), "size": f.stat().st_size}
            for f in _iter_files(data_dir)}


def verify_snapshot(snap: Path, sample: Optional[int] = None) -> list[str]:
    """Lista de problemas ([] = válido). `sample` verifica só N arquivos aleatórios."""
    problems: list[str] = []
    try:
        man = json.loads((snap / MANIFEST).read_text("utf-8"))
        files: dict = man["files"]
    except (OSError, ValueError, KeyError) as e:
        return [f"manifesto ausente/ilegível: {e}"]
    data = snap / "data"
    names = list(files)
    if sample is not None and sample < len(names):
        names = random.sample(names, sample)
    for rel in names:
        p = data / rel
        meta = files[rel]
        if not p.is_file():
            problems.append(f"faltando: {rel}")
        elif p.stat().st_size != meta["size"]:
            problems.append(f"tamanho divergente: {rel}")
        elif sha256_file(p) != meta["sha256"]:
            problems.append(f"hash divergente: {rel}")
    if sample is None:
        extra = set(_hash_tree_names(data)) - set(files)
        problems += [f"arquivo não listado: {e}" for e in sorted(extra)]
    return problems


def _hash_tree_names(data: Path) -> list[str]:
    return [f.relative_to(data).as_posix() for f in _iter_files(data)] if data.exists() else []


def create_snapshot(sources: dict[str, Path], dest_root: Path, quarantine_root: Path,
                    kind: str = "config", keep: int = 5,
                    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                    _corrupt_hook: Optional[Callable[[Path], None]] = None) -> SnapshotResult:
    dest_root = Path(dest_root)
    dest_root.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    missing = [n for n, p in sources.items() if not Path(p).exists()]
    if missing:
        warnings.append(f"fontes inexistentes ignoradas: {', '.join(missing)}")
    sources = {n: Path(p) for n, p in sources.items() if Path(p).exists()}
    if not sources:
        return SnapshotResult(False, None, warnings, "nenhuma fonte existente")

    for p in sources.values():
        if same_device(p, dest_root):
            warnings.append("backup no MESMO dispositivo físico da origem: falha de SSD perde ambos "
                            "(use DC_BACKUP_DIR num cartão SD/HD externo)")
            break

    total = _size_of(sources)
    need = int(total * (2.1 if kind == "config" else 1.1))  # cópia + sandbox
    free = shutil.disk_usage(dest_root).free
    if free < need:
        return SnapshotResult(False, None, warnings, f"espaço insuficiente: precisa {need} B, livre {free} B")

    t = now()
    snap_id = f"{t.strftime('%Y%m%dT%H%M%S')}-{kind}-{uuid.uuid4().hex[:6]}"
    tmp = dest_root / f".tmp-{snap_id}"
    data = tmp / "data"
    try:
        data.mkdir(parents=True)
        for name, src in sources.items():
            target = data / name
            if src.is_file():
                target.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target / src.name)
            else:
                shutil.copytree(src, target, symlinks=True)
        manifest = {"id": snap_id, "kind": kind, "created_at": t.isoformat(),
                    "sources": {n: str(p) for n, p in sources.items()},
                    "source_is_file": {n: p.is_file() for n, p in sources.items()},
                    "files": _hash_tree(data)}
        (tmp / MANIFEST).write_text(json.dumps(manifest, indent=1), "utf-8")
        if _corrupt_hook:
            _corrupt_hook(tmp)
        problems = verify_snapshot(tmp)
        if not problems:
            problems = _sandbox_restore(tmp, full=(kind == "config"))
        if problems:
            q = quarantine(tmp, quarantine_root, "backup falhou na verificação: " + "; ".join(problems[:5]), now)
            return SnapshotResult(False, None, warnings, f"verificação falhou; em quarentena: {q}")
        final = dest_root / snap_id
        os.replace(tmp, final)
    except BaseException:
        if tmp.exists():
            quarantine(tmp, quarantine_root, "backup interrompido por erro", now)
        raise
    warnings += apply_retention(dest_root, kind, keep)
    return SnapshotResult(True, final, warnings)


def _sandbox_restore(snap: Path, full: bool) -> list[str]:
    sandbox = snap.parent / f".sandbox-{snap.name}"
    try:
        man = json.loads((snap / MANIFEST).read_text("utf-8"))
        names = list(man["files"])
        if not full and len(names) > 20:
            names = random.sample(names, 20)
        for rel in names:
            dst = sandbox / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(snap / "data" / rel, dst)
            if sha256_file(dst) != man["files"][rel]["sha256"]:
                return [f"test-restore divergente: {rel}"]
        return []
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)


def list_snapshots(dest_root: Path, kind: Optional[str] = None) -> list[Path]:
    """Mais novo primeiro. Ignora .tmp-/.sandbox- e quarentena."""
    if not Path(dest_root).exists():
        return []
    snaps = [p for p in Path(dest_root).iterdir()
             if p.is_dir() and not p.name.startswith(".") and p.name != "quarantine"]
    if kind:
        snaps = [p for p in snaps if f"-{kind}-" in p.name]
    return sorted(snaps, key=lambda p: p.name, reverse=True)


def apply_retention(dest_root: Path, kind: str, keep: int) -> list[str]:
    """Mantém os `keep` snapshots VÁLIDOS mais novos; só remove válidos excedentes."""
    msgs = []
    valid = [s for s in list_snapshots(dest_root, kind) if not verify_snapshot(s, sample=3)]
    for old in valid[keep:]:
        shutil.rmtree(old)
        msgs.append(f"retenção: removido snapshot antigo {old.name}")
    return msgs


def latest_valid(dest_root: Path, quarantine_root: Path, kind: Optional[str] = None,
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> tuple[Path, list[str]]:
    """Percorre do mais novo ao mais velho; inválidos vão para quarentena com aviso."""
    warnings = []
    for snap in list_snapshots(dest_root, kind):
        problems = verify_snapshot(snap)
        if not problems:
            return snap, warnings
        q = quarantine(snap, quarantine_root, "snapshot inválido: " + "; ".join(problems[:5]), now)
        warnings.append(f"snapshot {snap.name} inválido -> quarentena ({q.name}); caindo para o anterior")
    raise AllBackupsCorrupt("nenhum snapshot válido — acionar /sos")


def touches_steam(snap: Path) -> bool:
    man = json.loads((snap / MANIFEST).read_text("utf-8"))
    return any(Path(rel).name in STEAM_SENSITIVE for rel in man["files"])


def restore_snapshot(snap: Path, dry_run: bool = True, target_root: Optional[Path] = None,
                     steam_guard=None) -> list[tuple[str, str]]:
    """Restaura cada fonte ao caminho original (ou sob `target_root`, para testes).

    Se o snapshot contém shortcuts.vdf/localconfig.vdf, exige `steam_guard` (context manager
    que fecha o Steam antes e reabre depois). Sem guard -> recusa (M0.2).
    Retorna o plano [(origem_no_snapshot, destino)].
    """
    problems = verify_snapshot(snap)
    if problems:
        raise BackupError("snapshot inválido: " + "; ".join(problems[:5]))
    man = json.loads((snap / MANIFEST).read_text("utf-8"))
    plan: list[tuple[str, str]] = []
    for rel in man["files"]:
        name, _, rest = rel.partition("/")
        orig = Path(man["sources"][name])
        if man.get("source_is_file", {}).get(name):
            dst = orig
        else:
            dst = orig / rest
        if target_root is not None:
            dst = Path(target_root) / dst.relative_to(dst.anchor)
        plan.append((rel, str(dst)))
    if dry_run:
        return plan
    if touches_steam(snap) and steam_guard is None:
        raise BackupError("restore toca shortcuts.vdf/localconfig.vdf: é obrigatório fechar o Steam "
                          "antes (passe steam_guard)")

    def _do():
        for rel, dst in plan:
            d = Path(dst)
            d.parent.mkdir(parents=True, exist_ok=True)
            tmp = d.with_name(d.name + ".dc-restore")
            shutil.copy2(snap / "data" / rel, tmp)
            os.replace(tmp, d)

    if steam_guard is not None and touches_steam(snap):
        with steam_guard:
            _do()
    else:
        _do()
    return plan
