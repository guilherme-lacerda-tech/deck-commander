"""Diretórios do Deck Commander (separação física obrigatória — v5.1 'DIRETÓRIOS').

Código, configs, banco, backups, logs e lock ficam em lugares diferentes.
`DC_ROOT` (env) redireciona tudo para uma raiz isolada — usado em testes/spikes.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    config: Path
    secrets: Path
    data: Path
    db: Path
    backups: Path
    quarantine: Path
    state: Path
    logs: Path
    lock: Path

    def ensure(self) -> Paths:
        for d in (self.config, self.secrets, self.data, self.backups,
                  self.quarantine, self.state, self.logs):
            d.mkdir(parents=True, exist_ok=True)
        if os.name == "posix":
            os.chmod(self.secrets, 0o700)
        return self


def get_paths(root: str | os.PathLike | None = None) -> Paths:
    root = root or os.environ.get("DC_ROOT")
    if root:
        home = Path(root)
        cfg, share, state = home / ".config", home / ".local/share", home / ".local/state"
    else:
        home = Path.home()
        cfg = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
        share = Path(os.environ.get("XDG_DATA_HOME") or home / ".local/share")
        state = Path(os.environ.get("XDG_STATE_HOME") or home / ".local/state")

    backups = Path(os.environ.get("DC_BACKUP_DIR") or home / "Backups/DeckCommander")
    config = cfg / "deck-commander"
    data = share / "deck-commander"
    st = state / "deck-commander"
    return Paths(
        config=config,
        secrets=config / "secrets",
        data=data,
        db=data / "deck.db",
        backups=backups,
        quarantine=backups / "quarantine",
        state=st,
        logs=st,
        lock=st / "operation.lock",
    )
