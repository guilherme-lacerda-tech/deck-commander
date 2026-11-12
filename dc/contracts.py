"""M27 — contratos entre módulos (modules/<M>/contract.toml) + validação.

Detecta: campos faltando, reversibilidade inválida, dependência inexistente, ciclos de
dependência e conflito de `owns` (dois módulos donos do mesmo recurso) e owns×forbids no mesmo módulo.
`dependents()` é usado pelo uninstall-module (M15) para avisar quem depende do alvo.
"""
from __future__ import annotations

from pathlib import Path

import tomllib

REQUIRED = ("id", "name", "inputs", "outputs", "owns", "forbids", "depends_on",
            "optional_depends", "fail_mode", "reversibility")
REVERSIBILITY = {"rollback_full", "compensation", "irreversible_requires_approval", "read_only"}


def load(modules_dir: Path) -> dict[str, dict]:
    out = {}
    for f in sorted(Path(modules_dir).glob("*/contract.toml")):
        c = tomllib.loads(f.read_text("utf-8"))
        c["_file"] = str(f)
        out[c.get("id", f.parent.name)] = c
    return out


def _cycles(graph: dict[str, list[str]]) -> list[list[str]]:
    found, state, stack = [], {}, []

    def visit(n):
        state[n] = 1; stack.append(n)
        for m in graph.get(n, []):
            if state.get(m) == 1:
                found.append(stack[stack.index(m):] + [m])
            elif m in graph and not state.get(m):
                visit(m)
        stack.pop(); state[n] = 2

    for n in graph:
        if not state.get(n):
            visit(n)
    return found


def validate_contracts(cs: dict[str, dict]) -> list[str]:
    problems = []
    for mid, c in cs.items():
        miss = [k for k in REQUIRED if k not in c]
        if miss:
            problems.append(f"{mid}: campos ausentes {miss}")
        if c.get("reversibility") not in REVERSIBILITY:
            problems.append(f"{mid}: reversibility inválida {c.get('reversibility')!r}")
        for d in c.get("depends_on", []) + c.get("optional_depends", []):
            if d not in cs:
                problems.append(f"{mid}: depende de módulo inexistente {d}")
        overlap = set(c.get("owns", [])) & set(c.get("forbids", []))
        if overlap:
            problems.append(f"{mid}: owns e forbids ao mesmo tempo: {sorted(overlap)}")
    owners: dict[str, str] = {}
    for mid, c in cs.items():
        for res in c.get("owns", []):
            if res in owners:
                problems.append(f"conflito de owns: '{res}' é de {owners[res]} e de {mid}")
            owners[res] = mid
    for cyc in _cycles({m: c.get("depends_on", []) for m, c in cs.items()}):
        problems.append("ciclo de dependência: " + " -> ".join(cyc))
    return problems


def validate(modules_dir: Path) -> list[str]:
    return validate_contracts(load(modules_dir))


def dependents(cs: dict[str, dict], target: str) -> list[str]:
    """Módulos que dependem (obrigatoriamente, direta ou indiretamente) de `target`."""
    out, frontier = set(), {target}
    while frontier:
        nxt = {m for m, c in cs.items() if set(c.get("depends_on", [])) & frontier} - out
        out |= nxt; frontier = nxt
    return sorted(out)
