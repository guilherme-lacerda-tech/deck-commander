"""Matriz de instalação: plugin vazio, parcial, correto, inválido e emuladores bons/ruins.

Estes cenários simulam os estados que uma instalação real pode ter antes de o Deck Commander
ser instalado ou atualizado. Tudo acontece em diretórios temporários; nenhum Deck real é alterado.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from dc import setup
from dc.paths import get_paths


@pytest.fixture
def plugin_env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setattr(setup, "H", home)
    monkeypatch.setattr(setup, "PLUGIN_ZIP", tmp_path / "Downloads/deck-commander-plugin.zip")
    monkeypatch.setattr(setup, "reload_plugin", lambda: True)
    return home


def _installed(home: Path) -> Path:
    d = home / "homebrew/plugins/deck-commander"
    d.mkdir(parents=True)
    (d / "plugin.json").write_text('{"name": "Deck Commander"}', "utf-8")
    return d


def _source_files():
    return [f.relative_to(setup.PLUGIN_SRC) for f in setup.PLUGIN_SRC.rglob("*")
            if f.is_file() and "__pycache__" not in f.parts]


def test_plugin_matrix_empty_install_creates_zip_without_touching_other_plugins(plugin_env):
    unrelated = plugin_env / "homebrew/plugins/Outro"; unrelated.mkdir(parents=True)
    (unrelated / "plugin.json").write_text('{"name": "Outro"}', "utf-8")
    log = []
    setup.setup_plugin(log)
    assert any("Instalar plugin de ZIP" in row for row in log)
    assert unrelated.joinpath("plugin.json").read_text("utf-8") == '{"name": "Outro"}'
    with zipfile.ZipFile(setup.PLUGIN_ZIP) as z:
        assert {Path(n).relative_to("deck-commander") for n in z.namelist()} >= set(_source_files())


def test_plugin_matrix_partial_install_is_repaired(plugin_env):
    inst = _installed(plugin_env)
    (inst / "main.py").write_text("versão antiga", "utf-8")
    log = []
    setup.setup_plugin(log)
    assert all((inst / rel).read_bytes() == (setup.PLUGIN_SRC / rel).read_bytes() for rel in _source_files())
    assert any("plugin atualizado" in row and "recarregado agora" in row for row in log)


def test_plugin_matrix_correct_install_is_idempotent(plugin_env):
    inst = _installed(plugin_env)
    for rel in _source_files():
        target = inst / rel; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((setup.PLUGIN_SRC / rel).read_bytes())
    log = []
    setup.setup_plugin(log)
    assert log == ["plugin já instalado, em dia"]


def test_plugin_matrix_invalid_manifest_is_not_mistaken_for_installed(plugin_env):
    bad = plugin_env / "homebrew/plugins/quebrado"; bad.mkdir(parents=True)
    (bad / "plugin.json").write_text("{não é json", "utf-8")
    log = []
    setup.setup_plugin(log)
    assert any("Instalar plugin de ZIP" in row for row in log)
    assert (bad / "plugin.json").read_text("utf-8") == "{não é json"


def test_plugin_matrix_permission_error_keeps_existing_plugin(plugin_env, monkeypatch):
    inst = _installed(plugin_env)
    (inst / "main.py").write_text("antigo", "utf-8")
    original = setup.shutil.copyfile

    def denied(src, dst, *args, **kwargs):
        if Path(dst).is_relative_to(inst):
            raise PermissionError("somente leitura")
        return original(src, dst, *args, **kwargs)

    monkeypatch.setattr(setup.shutil, "copyfile", denied)
    log = []
    setup.setup_plugin(log)
    assert any("sem permissão" in row for row in log)
    assert (inst / "main.py").read_text("utf-8") == "antigo"


@pytest.mark.parametrize("bad_config", ["{quebrado", "[]", '{"ps2": []}', '{"ps2": "não é lista"}'])
def test_emulator_matrix_recovers_invalid_config_and_uses_detected_emulator(tmp_path, monkeypatch, bad_config):
    paths = get_paths(tmp_path / "dc").ensure()
    good = tmp_path / "PCSX2"; good.write_text("binário", "utf-8")
    monkeypatch.setattr(setup.emulators, "detect", lambda: {"ps2": [str(good), "{rom}"]})
    (paths.config / "emulators.json").write_text(bad_config, "utf-8")
    log = []
    setup.write_emulators_json(paths, log)
    data = json.loads((paths.config / "emulators.json").read_text("utf-8"))
    assert data["ps2"] == [str(good), "{rom}"]
    assert any("inválida" in row or "emulador de ps2" in row for row in log)


def test_emulator_matrix_keeps_valid_choice_and_replaces_missing_one(tmp_path, monkeypatch):
    paths = get_paths(tmp_path / "dc").ensure()
    chosen = tmp_path / "emulador-escolhido"; chosen.write_text("binário", "utf-8")
    found = tmp_path / "emulador-detectado"; found.write_text("binário", "utf-8")
    monkeypatch.setattr(setup.emulators, "detect", lambda: {
        "ps2": [str(found), "{rom}"], "psx": [str(found), "{rom}"]
    })
    (paths.config / "emulators.json").write_text(json.dumps({
        "ps2": [str(chosen), "--custom", "{rom}"], "psx": [str(tmp_path / "sumiu"), "{rom}"]
    }), "utf-8")
    setup.write_emulators_json(paths, [])
    data = json.loads((paths.config / "emulators.json").read_text("utf-8"))
    assert data["ps2"] == [str(chosen), "--custom", "{rom}"]
    assert data["psx"] == [str(found), "{rom}"]
