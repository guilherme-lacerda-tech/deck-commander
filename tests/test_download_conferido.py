"""Revisão de lançamento 11/11/2026: Ollama, Xenia e qBittorrent eram instalados sem conferir o arquivo baixado."""
import hashlib
import io

import pytest

from dc import setup


def _api(nome, digest):
    return lambda url: {"assets": [{"name": nome, "digest": digest}]}


def test_sha256_publicado_le_o_digest_do_release():
    url = "https://github.com/a/b/releases/download/v1/prog.tar.xz"
    vistos = []

    def get(u):
        vistos.append(u)
        return {"assets": [{"name": "outro", "digest": "sha256:00"}, {"name": "prog.tar.xz", "digest": "sha256:ab"}]}
    assert setup.sha256_publicado(url, get) == "ab" and vistos == ["https://api.github.com/repos/a/b/releases/tags/v1"]
    assert setup.sha256_publicado("https://github.com/a/b/releases/latest/download/x", _api("x", "sha256:cd")) == "cd"
    assert setup.sha256_publicado("https://exemplo.com/x.zip") is None


def test_download_conferido(tmp_path, monkeypatch):
    dados = b"programa de verdade"

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    monkeypatch.setattr(setup.urllib.request, "urlopen", lambda *a, **k: Resp(dados))
    url = "https://github.com/a/b/releases/latest/download/prog"
    certo = hashlib.sha256(dados).hexdigest()
    setup.download_conferido(url, tmp_path / "ok", _api("prog", "sha256:" + certo))
    assert (tmp_path / "ok").read_bytes() == dados
    with pytest.raises(OSError, match="não confere"):  # arquivo adulterado: não fica nada no disco
        setup.download_conferido(url, tmp_path / "ruim", _api("prog", "sha256:" + "0" * 64))
    assert not (tmp_path / "ruim").exists() and not (tmp_path / "ruim.part").exists()
    with pytest.raises(OSError, match="não publicou"):  # sem assinatura publicada: recusa
        setup.download_conferido(url, tmp_path / "sem", _api("prog", None))
