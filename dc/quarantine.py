"""M0.4 — Quarentena com prazo de revisão (review_by = +30 dias). Nunca apaga sozinha."""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

REVIEW_DAYS = 30


@dataclass
class QuarantineEntry:
    id: str
    path: Path
    reason: str
    original_path: str
    quarantined_at: str
    review_by: str
    overdue: bool


def _now() -> datetime:
    return datetime.now(timezone.utc)


def quarantine(item: Path, root: Path, reason: str, now: Callable[[], datetime] = _now) -> Path:
    """Move `item` (arquivo ou pasta) para root/<id>/ com meta.json. Retorna a pasta da entrada."""
    item = Path(item)
    root.mkdir(parents=True, exist_ok=True)
    t = now()
    base = f"{t.strftime('%Y%m%dT%H%M%S')}-{item.name}"
    entry, n = root / base, 1
    while entry.exists():
        entry, n = root / f"{base}-{n}", n + 1
    entry.mkdir()
    shutil.move(str(item), str(entry / item.name))
    meta = {"reason": reason, "original_path": str(item), "quarantined_at": t.isoformat(),
            "review_by": (t + timedelta(days=REVIEW_DAYS)).isoformat()}
    (entry / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), "utf-8")
    return entry


def list_entries(root: Path, now: Callable[[], datetime] = _now) -> list[QuarantineEntry]:
    out = []
    if not root.exists():
        return out
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        try:
            m = json.loads((d / "meta.json").read_text("utf-8"))
        except (OSError, ValueError):
            m = {"reason": "meta.json ausente/ilegível", "original_path": "?",
                 "quarantined_at": "?", "review_by": "?"}
        try:
            overdue = now() >= datetime.fromisoformat(m["review_by"])
        except ValueError:
            overdue = True
        out.append(QuarantineEntry(d.name, d, m["reason"], m["original_path"],
                                   m["quarantined_at"], m["review_by"], overdue))
    return out


def clear(root: Path, entry_id: str) -> None:
    """Remoção explícita pedida pelo usuário (/quarantine clear <id>)."""
    target = (root / entry_id).resolve()
    if target.parent != root.resolve() or not target.is_dir():
        raise ValueError(f"entrada inválida: {entry_id}")
    shutil.rmtree(target)
