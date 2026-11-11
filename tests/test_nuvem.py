"""Saves na nuvem (rclone + Google Drive) — docs/specs/nuvem.md."""
from types import SimpleNamespace

import pytest

from dc import nuvem as N


def test_conf():
    c = N.conf_rclone('{"access_token":"a","refresh_token":"r","expiry":"x"}')
    assert "[gdrive]" in c and "type = drive" in c and "scope = drive.file" in c and "token = {" in c
    with pytest.raises(ValueError):
        N.conf_rclone('{"x":1}')
    assert all(not p.endswith((".iso", ".nsp")) and "Games" not in p for _, p in N.PASTAS)  # só saves


def test_sincronizar(tmp_path):
    home = tmp_path / "home"
    (home / ".local/share/duckstation/memcards").mkdir(parents=True)
    conf = tmp_path / "rclone.conf"
    conf.write_text(N.conf_rclone('{"access_token":"a","refresh_token":"r"}'))
    cmds = []
    run = lambda args, **k: cmds.append(args) or SimpleNamespace(returncode=0, stdout="", stderr="")
    n = N.Nuvem(home, tmp_path / "rclone", conf, tmp_path / "estado/nuvem.json", run=run)
    assert n.configurada()
    assert n.sincronizar() == ["☁️ DuckStation/memcards: em dia"]
    assert cmds[0][1] == "mkdir" and "--resync" in cmds[1] and "gdrive:DeckCommander/DuckStation/memcards" in cmds[1]
    assert "--max-delete" in cmds[1]
    n.sincronizar()
    assert "--resync" not in cmds[-1]
    assert "DuckStation/memcards" in n.resumo()


def test_instalar_confere(tmp_path):
    import hashlib
    import io
    import zipfile
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("rclone-v1.76.0-linux-amd64/rclone", b"ELF")
        z.writestr("rclone-v1.76.0-linux-amd64/README.txt", b"x")
    dados = b.getvalue()
    with pytest.raises(RuntimeError):
        N.instalar_rclone(tmp_path, lambda u: dados, sha256="0" * 64)
    p = N.instalar_rclone(tmp_path, lambda u: dados, sha256=hashlib.sha256(dados).hexdigest())
    assert p.read_bytes() == b"ELF" and not (tmp_path / "README.txt").exists()
