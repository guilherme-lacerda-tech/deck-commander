"""M17 — export/import de configurações para outro Deck.

Exporta: configs do DC (sem secrets/ e sem telegram.json, que tem IDs privados), mapa de jogos e
inventory.json com a procedência. Caminhos absolutos do home viram "~". Saves NÃO entram (M6 cuida).
"""
from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime
from pathlib import Path

from .paths import Paths

PRIVATE = ("secrets/", "telegram.json")


def _scrub(text: str, home: Path) -> str:
    return text.replace(str(home), "~")


def export_config(paths: Paths, out: Path, home: Path = Path.home()) -> list[str]:
    names = []
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(paths.config.rglob("*")):
            rel = f.relative_to(paths.config).as_posix()
            if f.is_dir() or rel.startswith(PRIVATE[0]) or rel == PRIVATE[1]:
                continue
            z.writestr(f"config/{rel}", _scrub(f.read_text("utf-8", "replace"), home)); names.append(f"config/{rel}")
        for extra, src in (("launch-map.json", paths.data / "launch-map.json"),
                           ("inventory.json", paths.state / "inventory.json")):
            if src.exists():
                z.writestr(extra, _scrub(src.read_text("utf-8"), home)); names.append(extra)
        z.writestr("EXPORT.txt", f"Deck Commander export {datetime.now().isoformat()}\nsem tokens, sem IDs privados\n")
    return names


def import_config(paths: Paths, archive: Path, home: Path = Path.home(), dry_run: bool = True) -> list[str]:
    done = []
    with zipfile.ZipFile(archive) as z:
        for n in z.namelist():
            if not n.startswith("config/") or ".." in n:
                continue
            rel = n[len("config/"):]
            if rel.startswith(PRIVATE[0]) or rel == PRIVATE[1]:
                continue
            dst = paths.config / rel
            done.append(f"{'(dry-run) ' if dry_run else ''}{dst}" + (" [substitui]" if dst.exists() else ""))
            if not dry_run:
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_text(z.read(n).decode("utf-8").replace("~", str(home)), "utf-8")
    return done
