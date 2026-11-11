"""Spotify do Deck: conta e playlists pelo go-librespot (ligado só quando precisa); tocar é pelo app oficial."""
import hashlib
import io
import json
import tarfile
import time
from types import SimpleNamespace

import pytest

from dc import spotify
from dc.paths import get_paths


def _pacote(conteudo=b"\x7fELF bin"):
    b = io.BytesIO()
    with tarfile.open(fileobj=b, mode="w:gz") as tf:
        ti = tarfile.TarInfo("go-librespot"); ti.size = len(conteudo)
        tf.addfile(ti, io.BytesIO(conteudo))
    return b.getvalue()


class Systemd:
    def __init__(self):
        self.ativo, self.chamadas = False, []

    def __call__(self, args, **k):
        self.chamadas.append(args)
        if "start" in args:
            self.ativo = True
        if "stop" in args:
            self.ativo = False
        rc = 0 if ("is-active" not in args or self.ativo) else 3
        return SimpleNamespace(returncode=rc, stdout="", stderr="")


def test_instalar_confere_sha256(tmp_path, monkeypatch):
    monkeypatch.setattr(spotify.Path, "home", lambda: tmp_path)
    paths = get_paths(tmp_path / "dc").ensure()
    run = Systemd()
    with pytest.raises(RuntimeError, match="não confere"):
        spotify.instalar(paths, baixar=lambda u: b"outra coisa", run=run)
    assert not spotify._bin(paths).exists()
    pac = _pacote()
    monkeypatch.setattr(spotify, "SHA256", hashlib.sha256(pac).hexdigest())
    spotify.instalar(paths, baixar=lambda u: pac, run=run)
    assert spotify._bin(paths).read_bytes() == b"\x7fELF bin" and spotify.instalado(paths)
    conf = (spotify._conf_dir(paths) / "config.yml").read_text("utf-8")
    assert "type: device_auth" in conf and "address: 127.0.0.1" in conf and "zeroconf_enabled: false" in conf
    unit = spotify._unit_path().read_text()
    assert f"--config_dir {spotify._conf_dir(paths)}" in unit  # "-config_dir" virava "-c onfig_dir"
    assert "[Install]" not in unit  # não liga no boot (não vira aparelho fantasma no Spotify)


def test_login_depois_lista_e_desliga(tmp_path, monkeypatch):
    monkeypatch.setattr(spotify, "instalado", lambda p: True)
    paths = get_paths(tmp_path / "dc").ensure()
    run = Systemd()
    resp = {"/auth/code": (200, {"url": "https://spotify.com/pair?code=AB12", "code": "AB12"}), "/status": (0, None)}
    chamar = lambda m, c, *a, **k: resp.get(c.split("?")[0], (404, None))
    r = spotify.atualizar(paths, chamar, run, espera=0)
    assert r["login"]["code"] == "AB12" and run.ativo  # fica ligado esperando a confirmação no celular
    st = spotify.estado(paths, chamar, run)
    assert not st["conectado"] and st["login"]["url"].endswith("AB12")
    resp.update({"/auth/code": (204, None), "/status": (200, {"username": "x"}),
                 "/library/playlists": (200, {"items": [{"uri": "spotify:playlist:1", "name": "Foco "}, {"name": "?"}]})})
    st = spotify.estado(paths, chamar, run)  # confirmou: guarda a lista e desliga
    assert st["conectado"] and st["playlists"] == [{"nome": "Foco", "uri": "spotify:playlist:1", "imagem": None}]
    assert not run.ativo
    n = len(run.chamadas)
    assert spotify.estado(paths, lambda *a, **k: 1 / 0, run)["conectado"]  # lista nova: nem consulta
    assert all("start" not in c for c in run.chamadas[n:])


def test_lista_velha_atualiza(tmp_path, monkeypatch):
    monkeypatch.setattr(spotify, "instalado", lambda p: True)
    paths = get_paths(tmp_path / "dc").ensure()
    spotify._cache(paths).write_text(json.dumps({"em": time.time() - 7 * 3600, "playlists": []}))
    resp = {"/auth/code": (204, None), "/status": (200, {"username": "x"}),
            "/library/playlists": (200, {"items": [{"uri": "spotify:playlist:2", "name": "Nova"}]})}
    st = spotify.estado(paths, lambda m, c, *a, **k: resp[c.split("?")[0]], Systemd())
    assert [x["nome"] for x in st["playlists"]] == ["Nova"]


def test_qr_usa_o_gerador_do_painel():
    assert spotify.qr_svg("https://spotify.com/pair?code=AB12").startswith("data:image/svg+xml;base64,")
