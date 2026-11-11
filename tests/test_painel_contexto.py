"""Painel por contexto: o jogo aberto decide quais telas aparecem (0.8, módulo 4)."""
from types import SimpleNamespace

from dc import painel, transferir, vdf


def test_contexto(tmp_path, monkeypatch):
    monkeypatch.setattr(painel.Path, "home", lambda: tmp_path)
    cfg = tmp_path / ".local/share/Steam/userdata/1/config"
    cfg.mkdir(parents=True)
    sc = {"0": {"appid": 3000000001 - (1 << 32), "AppName": "Mario", "LaunchOptions": "snes-mario"},
          "1": {"appid": 3000000002 - (1 << 32), "AppName": "Zelda", "LaunchOptions": "switch-zelda"},
          "2": {"appid": 3000000003 - (1 << 32), "AppName": "Spotify", "LaunchOptions": "app-spotify"}}
    (cfg / "shortcuts.vdf").write_bytes(vdf.dump_binary({"shortcuts": sc}))
    monkeypatch.setattr(transferir, "carregar_mapa", lambda *a, **k: {
        "snes-mario": {"title": "Super Mario World", "console": "snes"},
        "switch-zelda": {"title": "Zelda", "console": "switch"}})
    p = SimpleNamespace()
    assert painel.contexto(p, {})["modo"] == "nenhum"
    assert painel.contexto(p, {"appid": 3000000001})["modo"] == "retro"
    assert painel.contexto(p, {"appid": 3000000002})["titulo"] == "Zelda"
    assert painel.contexto(p, {"appid": 3000000003})["modo"] == "app"
    assert painel.contexto(p, {"appid": 1245620})["modo"] == "steam"
