"""Família: catálogo (magnet + pacote de tradução), sem nunca enviar arquivo de jogo."""
from types import SimpleNamespace

from dc import familia


def test_catalogo_e_filtro(tmp_path):
    rom = tmp_path / "roms/ps2/Jogo/Jogo.iso"; rom.parent.mkdir(parents=True); rom.write_bytes(b"x")
    mod = tmp_path / "mods/ptbr.bps"; mod.parent.mkdir(parents=True); mod.write_bytes(b"p")
    lm = {"ps2-jogo": {"title": "Jogo", "console": "ps2", "rom": str(rom)},
          "pc-x": {"title": "X", "console": "pc", "rom": "x"},
          "gba-sem": {"title": "Sem", "console": "gba", "rom": str(tmp_path / "roms/gba/s.gba")}}
    ing = {"h1": {"name": "Jogo", "files": [str(rom)]}}
    cat = familia.montar_catalogo(lm, ing, {"h1": "magnet:?xt=urn:btih:h1"}, {"ps2-jogo": [str(mod)]})
    assert [c["gid"] for c in cat] == ["ps2-jogo"]
    assert cat[0]["magnet"].startswith("magnet:") and cat[0]["tem_traducao"]
    ok, nao = familia.filtrar_pacote([str(mod), str(rom), str(tmp_path / "nao-existe.bps")])
    assert ok == [str(mod)] and str(rom) in nao


def test_rsync_nunca_leva_jogo(tmp_path):
    a = tmp_path / "x.bps"; a.write_bytes(b"1")
    iso = tmp_path / "j.iso"; iso.write_bytes(b"1")
    cmd = familia.rsync_cmd([str(a), str(iso)], "deck@100.64.0.20", "/k", "/home/deck/")
    assert cmd and cmd[0] == "rsync" and not any(x.endswith(".iso") for x in cmd)
    assert familia.rsync_cmd([str(iso)], "deck@h", "/k", "/home/deck/") == []


def test_pedidos_e_online(tmp_path):
    est = tmp_path / "pedidos.json"
    it = {"gid": "ps2-jogo", "titulo": "Jogo", "console": "ps2", "hash": "h1", "magnet": "magnet:?xt=urn:btih:h1"}
    familia.registrar_pedido(est, it, "Irmão")
    familia.registrar_pedido(est, it, "Irmão")
    assert len(familia.pedidos(est)) == 1 and familia.pedidos(est)[0]["status"] == "baixando"
    familia.marcar(est, "ps2-jogo", "pronto")
    assert familia.pedidos(est)[0]["status"] == "pronto"
    assert familia.par_online("deck@h", "/k", run=lambda a, **k: SimpleNamespace(returncode=0, stdout="ok\n"))
    assert not familia.par_online("deck@h", "/k", run=lambda a, **k: SimpleNamespace(returncode=255, stdout=""))


def test_aplicar_pacote(tmp_path):
    pac = tmp_path / "pac"; home = tmp_path / "home"
    (pac / ".config/Ryujinx/mods").mkdir(parents=True)
    (pac / ".config/Ryujinx/mods/a.msbt").write_bytes(b"novo")
    (pac / "jogo.nsp").write_bytes(b"jogo")
    (home / ".config/Ryujinx/mods").mkdir(parents=True)
    (home / ".config/Ryujinx/mods/a.msbt").write_bytes(b"velho")
    feitos = familia.aplicar_pacote(pac, home)
    assert (home / ".config/Ryujinx/mods/a.msbt").read_bytes() == b"novo"
    assert (home / ".config/Ryujinx/mods/a.msbt.antes-familia").read_bytes() == b"velho"
    assert not (home / "jogo.nsp").exists() and len(feitos) == 1
