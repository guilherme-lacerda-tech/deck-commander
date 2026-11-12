"""Revisão de lançamento 12/11/2026: o painel de desempenho carrega o código do Deck Commander dentro do processo do
Decky. Depois de uma implantação ele seguia rodando a versão VELHA até o Decky reiniciar."""
import importlib.util
import os
import sys
import time
from pathlib import Path


def _repo_falso(raiz: Path, valor: int) -> None:
    dc = raiz / "deck-commander/dc"
    dc.mkdir(parents=True, exist_ok=True)
    (dc / "__init__.py").write_text("")
    for m in ("perf", "quality", "tuning"):
        (dc / f"{m}.py").write_text("")
    (dc / "paths.py").write_text("def get_paths():\n    return 'p'\n")
    (dc / "autotune.py").write_text(f"VALOR = {valor}\n")


def test_painel_usa_o_codigo_novo_sem_reiniciar_o_decky(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("dcplugin_novo", Path(__file__).resolve().parents[1] / "decky-plugin/main.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    monkeypatch.setattr(m, "HOME", str(tmp_path))
    monkeypatch.setenv("HOME", os.environ.get("HOME", ""))  # o _dc() mexe no HOME: volta depois
    guardados = {k: v for k, v in sys.modules.items() if k == "dc" or k.startswith("dc.")}
    caminho = list(sys.path)
    try:
        for k in guardados:
            del sys.modules[k]
        _repo_falso(tmp_path, 1)
        p = m.Plugin()
        p._dc()
        assert p.autotune.VALOR == 1
        p._dc()  # nada mudou: não recarrega à toa
        assert p.autotune.VALOR == 1
        _repo_falso(tmp_path, 2)  # implantação nova
        novo = time.time() + 5
        os.utime(tmp_path / "deck-commander/dc/autotune.py", (novo, novo))
        p._dc()
        assert p.autotune.VALOR == 2
    finally:
        for k in [k for k in sys.modules if k == "dc" or k.startswith("dc.")]:
            del sys.modules[k]
        sys.modules.update(guardados)
        sys.path[:] = caminho
