"""Família ligada ao Deck: config, puxar (magnet na fila + pacote por SSH), aplicar quando chega."""
import io
import json
import tarfile
from types import SimpleNamespace

from dc import familia_servico as fs
from dc.paths import get_paths


def _tar(arquivos: dict) -> bytes:
    b = io.BytesIO()
    with tarfile.open(fileobj=b, mode="w") as tf:
        for nome, dado in arquivos.items():
            ti = tarfile.TarInfo(nome); ti.size = len(dado)
            tf.addfile(ti, io.BytesIO(dado))
    return b.getvalue()


def test_puxar_e_aplicar(tmp_path, monkeypatch):
    paths = get_paths(tmp_path / "dc").ensure()
    monkeypatch.setattr(fs.Path, "home", lambda: tmp_path / "home")
    fs.salvar_config(paths, {"par": {"nome": "Irmão", "alvo": "deck@100.64.0.20", "chave": "/k"}})
    cat = {"de": "Irmão", "glossario": "/home/deck/.config/deck-commander/glossary.json", "jogos": [
        {"gid": "switch-jogo", "titulo": "Jogo", "console": "switch", "hash": "h1", "magnet": "magnet:?xt=urn:btih:h1",
         "pacote": ["/home/deck/.config/Ryujinx/mods/contents/0100/PT/romfs/a.msbt", "/home/deck/x/jogo.nsp"],
         "tem_traducao": True}]}
    pacote = _tar({".config/Ryujinx/mods/contents/0100/PT/romfs/a.msbt": b"pt",
                   ".config/deck-commander/glossary.json": json.dumps({"mario": {"Toad": "Toad"}}).encode()})
    pedidos_ssh = []

    def run(args, **kw):
        pedidos_ssh.append(args)
        if "cat" in args:
            return SimpleNamespace(returncode=0, stdout=json.dumps(cat))
        if "tar" in args:
            assert not any(a.endswith(".nsp") for a in args)  # arquivo de jogo nunca é pedido
            return SimpleNamespace(returncode=0, stdout=pacote)
        return SimpleNamespace(returncode=0, stdout="ok")

    adds = []
    qbt = SimpleNamespace(add=lambda m, c, d, extra_tags="": adds.append((m, c, extra_tags)))
    monkeypatch.setattr(fs, "_par", lambda p: {"nome": "Irmão", "alvo": "deck@h", "chave": "/k"})
    import dc.syncer as sy
    monkeypatch.setattr(sy, "_cfg", lambda p: {"downloads_root": str(tmp_path / "dl")})
    msg = fs.puxar(paths, qbt, "switch-jogo", run=run)
    assert "download na fila" in msg and "tradução recebida" in msg
    assert adds == [("magnet:?xt=urn:btih:h1", "switch", "dc-familia")]
    assert fs.aplicar_prontos(paths) == []  # ainda baixando
    (paths.state / "sync-state.json").write_text(json.dumps({"ingested": {"h1": {"files": []}}}))
    av = fs.aplicar_prontos(paths)
    assert av and "traduzido" in av[0]
    assert (tmp_path / "home/.config/Ryujinx/mods/contents/0100/PT/romfs/a.msbt").read_bytes() == b"pt"
    from dc.traducao import ia
    assert json.loads(ia.glossary_path(paths).read_text("utf-8"))["mario"]["Toad"] == "Toad"


def test_autorizar(tmp_path, monkeypatch):
    monkeypatch.setattr(fs.Path, "home", lambda: tmp_path)
    assert "autorizado" in fs.autorizar("ssh-ed25519 AAAAC3Nza deck-commander-familia")
    assert "já estava" in fs.autorizar("ssh-ed25519 AAAAC3Nza deck-commander-familia")
    import pytest
    with pytest.raises(ValueError):
        fs.autorizar("rm -rf /")
