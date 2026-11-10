"""dc x diagnose: jogo removido pelo /remover não é "lançador quebrado" (falso alarme visto no Deck em 10/11:
psx-sles-00524) e a dica do banco aponta para um comando que existe."""
import json

from dc import health, inventory
from dc.paths import get_paths
from dc.store import Store


def _run(tmp_path, monkeypatch, lm):
    P = get_paths(tmp_path).ensure()
    (P.data / "launch-map.json").write_text(json.dumps(lm), "utf-8")
    monkeypatch.setattr(health, "H", tmp_path)
    monkeypatch.setattr(inventory, "collect", lambda *a, **k: {"bios": {"required_ok": {}}})
    monkeypatch.setattr(health.ops, "dc_units", lambda *a: [])
    return {x.problem: x for x in health.diagnose(P, Store(P.db))}


def test_removed_game_is_not_a_broken_launcher(tmp_path, monkeypatch):
    lm = {"psx-sles-00524": {"title": "SLES_00524", "console": "psx", "rom": str(tmp_path / "sumiu.mds"),
                              "removed": True}}
    assert _run(tmp_path, monkeypatch, lm)["config"].ok


def test_missing_rom_still_flagged(tmp_path, monkeypatch):
    lm = {"psx-x": {"title": "X", "console": "psx", "rom": str(tmp_path / "sumiu.bin")}}
    f = _run(tmp_path, monkeypatch, lm)["config"]
    assert not f.ok and "psx-x" in f.detail


def test_db_hint_is_a_real_command():
    src = open(health.__file__, encoding="utf-8").read()
    assert "python3 -m dc x db index" in src and '"dc db index' not in src


def test_diagnose_without_steam_login_does_not_crash(tmp_path, monkeypatch):
    from dc import syncer
    def no_user():
        raise FileNotFoundError("nenhum usuário Steam")
    monkeypatch.setattr(syncer, "shortcuts_path", no_user)
    assert "db" in _run(tmp_path, monkeypatch, {})
