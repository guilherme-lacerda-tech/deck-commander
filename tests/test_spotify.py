"""Spotify do Deck (go-librespot): instalação conferida, login por código, playlists e controle pela API local."""
import hashlib
import io
import tarfile
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


def test_instalar_confere_sha256(tmp_path, monkeypatch):
    monkeypatch.setattr(spotify.Path, "home", lambda: tmp_path)
    paths = get_paths(tmp_path / "dc").ensure()
    run = lambda *a, **k: SimpleNamespace(returncode=0, stdout="", stderr="")
    with pytest.raises(RuntimeError, match="não confere"):
        spotify.instalar(paths, baixar=lambda u: b"outra coisa", run=run)
    assert not spotify._bin(paths).exists()
    pac = _pacote()
    monkeypatch.setattr(spotify, "SHA256", hashlib.sha256(pac).hexdigest())
    chamadas = []
    run = lambda args, **k: chamadas.append(args) or SimpleNamespace(returncode=0, stdout="", stderr="")
    spotify.instalar(paths, baixar=lambda u: pac, run=run)
    assert spotify._bin(paths).read_bytes() == b"\x7fELF bin" and spotify.instalado(paths)
    conf = (spotify._conf_dir(paths) / "config.yml").read_text("utf-8")
    assert "type: device_auth" in conf and "address: 127.0.0.1" in conf  # API só no próprio Deck
    assert ["systemctl", "--user", "enable", "--now", spotify.UNIDADE] in chamadas


def test_estado_login_e_conectado(tmp_path, monkeypatch):
    monkeypatch.setattr(spotify, "instalado", lambda p: True)
    paths = get_paths(tmp_path / "dc").ensure()
    fora = lambda m, c, *a, **k: (0, None)
    assert spotify.estado(paths, fora)["rodando"] is False
    resp = {"/status": (204, None), "/auth/code": (200, {"url": "https://spotify.com/pair?code=AB12", "code": "AB12"})}
    st = spotify.estado(paths, lambda m, c, *a, **k: resp[c])
    assert not st["conectado"] and st["login"]["code"] == "AB12"
    resp["/status"] = (200, {"username": "gui", "paused": False,
                             "track": {"name": "Faixa", "artist_names": ["A", "B"], "album_cover_url": None}})
    st = spotify.estado(paths, lambda m, c, *a, **k: resp[c])
    assert st["conectado"] and st["usuario"] == "gui" and st["tocando"]["artista"] == "A, B" and st["login"] is None


def test_playlists_e_controle():
    d = {"items": [{"uri": "spotify:playlist:1", "name": "Foco", "image_url": None}, {"name": "sem uri"}]}
    assert spotify.minhas_playlists(lambda *a, **k: (200, d)) == [{"nome": "Foco", "uri": "spotify:playlist:1", "imagem": None}]
    assert spotify.minhas_playlists(lambda *a, **k: (404, None)) == []
    feitas = []
    ok = lambda m, c, corpo=None, **k: feitas.append((m, c, corpo)) or (200, None)
    assert spotify.tocar("spotify:playlist:1", ok) and feitas[-1] == ("POST", "/player/play", {"uri": "spotify:playlist:1"})
    assert spotify.midia("proxima", ok) and feitas[-1][1] == "/player/next"
    assert not spotify.midia("explodir", ok)
