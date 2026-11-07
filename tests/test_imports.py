"""Todo módulo precisa ao menos importar (pega erro de sintaxe em arquivo sem teste próprio) e os
comandos de terminal mais usados precisam rodar sem quebrar."""
import importlib
import json
import pkgutil
import sys

import pytest

import dc


@pytest.mark.parametrize("name", sorted(m.name for m in pkgutil.walk_packages(dc.__path__, "dc.")))
def test_module_imports(name):
    if name == "dc.__main__":
        pytest.skip("executa a CLI")
    importlib.import_module(name)


def test_cli_new_commands_run(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DC_ROOT", str(tmp_path))
    from dc import cli, syncer
    from dc.paths import get_paths
    paths = get_paths().ensure()
    (paths.data / "launch-map.json").write_text(json.dumps({
        "ps2-okami": {"title": "Okami", "console": "ps2", "rom": str(tmp_path / "a.iso")},
        "ps2-okami-usa": {"title": "Okami (USA)", "console": "ps2", "rom": str(tmp_path / "b.iso")}}))
    monkeypatch.setattr(syncer, "rom_roots", lambda: [tmp_path])
    assert cli.main(["x", "duplicados"]) == 0
    assert "ps2-okami-usa" in capsys.readouterr().out
    assert cli.main(["x", "remover", "nada-disso"]) == 1
    assert cli.main(["x", "qualidade"]) == 0
    assert cli.main(["x", "qualidade", "okami usa", "2x"]) == 0
    assert "2x" in capsys.readouterr().out
    assert cli.main(["x", "remover", "ps2-okami-usa"]) == 0  # sem --confirm: só o plano
    assert "nada foi feito" in capsys.readouterr().out
    assert cli.main(["x", "controles"]) == 0
    # opções com "--" passam para os subcomandos (antes o argparse recusava)
    (tmp_path / "b.iso").write_bytes(b"x")
    assert cli.main(["x", "remover", "ps2-okami-usa", "--confirm"]) == 0
    assert "ps2-okami-usa" not in json.loads((paths.data / "launch-map.json").read_text())
    assert cli.main(["x", "configure"]) == 0  # dry-run sem --apply continua aceito

