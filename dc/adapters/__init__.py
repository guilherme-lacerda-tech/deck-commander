"""M3 — adaptadores por emulador (perfil desejado -> config efetiva, com read-back).

Regras (v5.1 M3.2):
- escreve só as linhas das chaves gerenciadas; o resto do arquivo fica byte-a-byte igual;
- lê de volta e confirma;
- chave/seção ausente => schema mudou => avisa e NÃO aplica;
- valor atual diferente do último valor escrito pelo DC => override manual => não sobrescreve
  sem force=True.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .ini import IniDoc

PROFILES = ("economico", "equilibrado", "desempenho")


class SchemaChanged(RuntimeError):
    pass


class ManualOverride(RuntimeError):
    pass


@dataclass
class Change:
    section: str
    key: str
    old: str | None
    new: str


class IniAdapter:
    name = "base"
    # campo do perfil -> (seção, chave, conversor)
    FIELDS: dict = {}
    UNSUPPORTED: tuple = ()
    PROFILES: dict = {}  # console -> perfil -> {campo: valor}

    def supports(self) -> dict:
        return {"fields": sorted(self.FIELDS), "unsupported": list(self.UNSUPPORTED)}

    def desired(self, console: str, profile: str) -> dict[tuple[str, str], str]:
        if profile not in PROFILES:
            raise ValueError(f"perfil inválido: {profile}")
        out = {}
        for field, value in self.PROFILES[console][profile].items():
            section, key, conv = self.FIELDS[field]
            out[(section, key)] = conv(value)
        return out

    def plan(self, path: Path, console: str, profile: str) -> list[Change]:
        doc = IniDoc.load(path)
        changes = []
        for (section, key), new in self.desired(console, profile).items():
            old = doc.get(section, key)
            if old is None:
                raise SchemaChanged(f"{self.name}: [{section}] {key} não existe em {path} — schema mudou?")
            if old != new:
                changes.append(Change(section, key, old, new))
        return changes

    def apply(self, path: Path, console: str, profile: str, state_file: Path,
              force: bool = False, dry_run: bool = True) -> list[Change]:
        path = Path(path)
        changes = self.plan(path, console, profile)
        state = _load_state(state_file).get(str(path), {})
        # dono = DC escreveu esse valor por último; qualquer outro valor é do usuário
        overrides = [c for c in changes if state.get(f"{c.section}/{c.key}") != c.old]
        if overrides and not force:
            raise ManualOverride("valores definidos fora do Deck Commander (override manual): " +
                                 ", ".join(f"[{c.section}] {c.key}={c.old}" for c in overrides) +
                                 " — use force=True para assumir o controle")
        if dry_run or not changes:
            return changes
        doc = IniDoc.load(path)
        for c in changes:
            doc.set(c.section, c.key, c.new)
        tmp = path.with_name(path.name + ".dc-tmp")
        tmp.write_bytes(doc.dump())
        os.replace(tmp, path)
        self.read_back(path, console, profile)
        st = _load_state(state_file)
        entry = st.setdefault(str(path), {})
        for (section, key), v in self.desired(console, profile).items():
            entry[f"{section}/{key}"] = v
        _save_state(state_file, st)
        return changes

    def read_back(self, path: Path, console: str, profile: str) -> None:
        doc = IniDoc.load(path)
        bad = [f"[{s}] {k}: esperado {v!r}, lido {doc.get(s, k)!r}"
               for (s, k), v in self.desired(console, profile).items() if doc.get(s, k) != v]
        if bad:
            raise SchemaChanged("read-back divergente: " + "; ".join(bad))


def _load_state(p: Path) -> dict:
    try:
        return json.loads(Path(p).read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def _save_state(p: Path, data: dict) -> None:
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1), "utf-8")
    os.replace(tmp, p)


def get_adapter(name: str) -> IniAdapter:
    from .duckstation import DuckStation
    from .pcsx2 import PCSX2
    return {"duckstation": DuckStation, "pcsx2": PCSX2}[name]()
