"""Instalador (dc/setup.py): módulos e dependências, unidades do systemd, plugin, desinstalação — sem tocar no
sistema de verdade (systemctl, downloads e pastas do $HOME trocados por pastas temporárias)."""
import json
import zipfile

import pytest

from dc import setup
from dc.paths import get_paths


@pytest.fixture
def env(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(setup, "H", tmp_path / "home")
    monkeypatch.setattr(setup, "UNITS", tmp_path / "units")
    monkeypatch.setattr(setup, "QBT_BIN", tmp_path / "nao-existe/qbittorrent-nox")
    monkeypatch.setattr(setup, "PLUGIN_ZIP", tmp_path / "Downloads/deck-commander-plugin.zip")
    monkeypatch.setattr(setup, "_sc", lambda *a: calls.append(a) or "")
    monkeypatch.setattr(setup, "reload_plugin", lambda: True)
    monkeypatch.setattr(setup, "write_emulators_json", lambda paths, log: None)
    return get_paths(tmp_path / "dc").ensure(), calls


def test_units_are_written_once_and_services_stay_local(env):
    _paths, calls = env
    log = []
    setup.write_units(log)
    assert len(log) == len(setup.UNIT_FILES) and ("daemon-reload",) in calls
    log2 = []
    setup.write_units(log2)
    assert log2 == []  # idempotente: rodar de novo não regrava nada
    body = (setup.UNITS / "deck-commander-ollama.service").read_text("utf-8")
    assert "OLLAMA_HOST=127.0.0.1:11434" in body  # IA nunca aberta para a rede
    assert "ConditionPathExists=%h/.config/deck-commander/secrets/telegram" in \
        (setup.UNITS / "deck-commander-bot.service").read_text("utf-8")


def test_setup_m4_without_token_does_not_start_bot_and_records_modules(env):
    paths, calls = env
    log = setup.setup(paths, ["M4"], downloads=False)
    assert ("enable", "deck-commander-bot.service") in calls
    assert ("enable", "--now", "deck-commander-bot.service") not in calls  # sem token: só habilita
    assert any("qbittorrent-nox" in l for l in log)  # download pulado vira pendência visível
    mods = json.loads((paths.state / "installed-modules.json").read_text())
    assert "M4" in mods and (paths.state / "VERSION").read_text().strip()
    (paths.secrets / "telegram").write_text("123:abc")
    calls.clear()
    setup.setup(paths, ["M4"], downloads=False)
    assert ("enable", "--now", "deck-commander-bot.service") in calls


def test_setup_plugin_zip_and_in_place_update(env, tmp_path):
    _paths, _calls = env
    log = []
    setup.setup_plugin(log)
    names = zipfile.ZipFile(setup.PLUGIN_ZIP).namelist()
    assert "deck-commander/main.py" in names and "deck-commander/dist/index.js" in names
    assert any("Instalar plugin de ZIP" in l for l in log)  # ainda não instalado: explica como
    inst = tmp_path / "home/homebrew/plugins/deck-commander"
    (inst / "dist").mkdir(parents=True)
    (inst / "plugin.json").write_text(json.dumps({"name": "Deck Commander"}))
    (inst / "main.py").write_text("velho")
    log = []
    setup.setup_plugin(log)
    assert (inst / "main.py").read_bytes() == (setup.PLUGIN_SRC / "main.py").read_bytes()
    assert any("recarregado agora" in l for l in log)
    log = []
    setup.setup_plugin(log)
    assert log == ["plugin já instalado, em dia"]


def test_uninstall_module_keeps_data_and_warns_dependents(env):
    paths, calls = env
    (paths.state / "installed-modules.json").write_text(json.dumps(["M0", "M4", "M6"]))
    (paths.secrets / "telegram").write_text("123:abc")
    log = setup.uninstall_module(paths, "M4")
    assert ("disable", "--now", "deck-commander-bot.service") in calls
    assert "M4" not in json.loads((paths.state / "installed-modules.json").read_text())
    assert (paths.secrets / "telegram").exists()  # desinstalar módulo nunca apaga segredo/dado
    assert all("apagado" not in l for l in log)
