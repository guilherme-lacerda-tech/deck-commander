"""M27 — validador de contratos + contratos reais do repositório."""
from pathlib import Path

from dc import contracts

MODULES = Path(__file__).resolve().parents[1] / "modules"


def c(mid, deps=(), owns=(), rev="read_only"):
    return {"id": mid, "name": mid, "inputs": [], "outputs": [], "owns": list(owns), "forbids": [],
            "depends_on": list(deps), "optional_depends": [], "fail_mode": "x", "reversibility": rev}


def test_repo_contracts_valid():
    cs = contracts.load(MODULES)
    assert len(cs) >= 21
    assert contracts.validate_contracts(cs) == []


def test_detects_cycle_and_owns_conflict_and_missing_dep():
    cs = {"A": c("A", ["B"], ["x"]), "B": c("B", ["A"], ["x"]), "C": c("C", ["Z"], rev="talvez")}
    p = " | ".join(contracts.validate_contracts(cs))
    assert "ciclo" in p and "conflito de owns" in p and "inexistente Z" in p and "reversibility" in p


def test_dependents_for_uninstall_warning():
    cs = contracts.load(MODULES)
    deps = contracts.dependents(cs, "M18+M19")
    assert {"M0", "M2", "M3", "M4"} <= set(deps)
    assert "M3" not in contracts.dependents(cs, "M2")  # spec: avisar SE M3 depender de M2
