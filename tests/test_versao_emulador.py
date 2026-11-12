"""Revisão retrô 12/11/2026: emulador atualizado sem aviso fazia o save state antigo sumir de surpresa."""
import json

from dc import versao_emulador as V

RA = ["flatpak", "run", "org.libretro.RetroArch", "-L", "snes9x.so", "/roms/snes/jogo.sfc"]


def test_avisa_so_quando_a_versao_muda(tmp_path):
    versoes = iter(["aaa", "aaa", "bbb"])
    ident = lambda cmd: next(versoes)  # noqa: E731
    assert V.conferir(tmp_path, "snes", RA, ident) is None  # 1ª vez: só guarda
    assert V.conferir(tmp_path, "snes", RA, ident) is None  # mesma versão
    aviso = V.conferir(tmp_path, "snes", RA, ident)
    assert "RetroArch foi atualizado" in aviso and "menu do próprio jogo" in aviso
    assert json.loads((tmp_path / "versoes-emuladores.json").read_text())["org.libretro.RetroArch"] == "bbb"


def test_switch_e_pc_nao_tem_save_state_nem_aviso(tmp_path):
    assert V.conferir(tmp_path, "switch", ["/x/Ryujinx", "jogo.nsp"], lambda c: "zzz") is None
    assert not (tmp_path / "versoes-emuladores.json").exists()


def test_appimage_com_env_na_frente(tmp_path):
    exe = tmp_path / "DuckStation-x64.AppImage"
    exe.write_bytes(b"v1")
    cmd = ["/usr/bin/env", "ENABLE_GAMESCOPE_WSI=0", str(exe), "-batch", "--", "jogo.cue"]
    assert V._qual(cmd)[1] == "DuckStation"
    assert V.conferir(tmp_path, "psx", cmd) is None
    exe.write_bytes(b"versao 2 maior")
    assert "DuckStation foi atualizado" in V.conferir(tmp_path, "psx", cmd)
