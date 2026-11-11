"""Aplicar a 0.8 retrô no disco: emuladores + Steam Input dos atalhos (com cópia antes de mudar)."""
from dc import retro, vdf
from tests.test_retro_hacks import LAYOUT


def _deck(tmp_path):
    h = tmp_path
    ra = h / retro.ARQUIVOS["RetroArch"]
    ra.parent.mkdir(parents=True)
    ra.write_text('input_save_state = "f2"\nvideo_shader_enable = "false"\n')
    ds = h / retro.ARQUIVOS["DuckStation"]
    ds.parent.mkdir(parents=True)
    ds.write_text("[Hotkeys]\nFastForward = Keyboard/Tab\n\n[Main]\nX = 1\n")
    (h / ".var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu").mkdir(parents=True)
    tpl = h / ".local/share/Steam/controller_base/templates/controller_neptune_gamepad+mouse.vdf"
    tpl.parent.mkdir(parents=True)
    tpl.write_text("﻿" + LAYOUT, "utf-8")
    cfg = h / ".local/share/Steam/userdata/42/config"
    cfg.mkdir(parents=True)
    sc = {"0": {"appid": 1, "AppName": "Castlevania SOTN", "LaunchOptions": "psx-cv"},
          "1": {"appid": 2, "AppName": "Zelda BOTW", "LaunchOptions": "switch-z"}}
    (cfg / "shortcuts.vdf").write_bytes(vdf.dump_binary({"shortcuts": sc}))
    base = h / ".local/share/Steam/steamapps/common/Steam Controller Configs/42/config"
    base.mkdir(parents=True)
    (base / "configset_controller_neptune.vdf").write_text(
        '"controller_config"\n{\n\t"pcsx2"\n\t{\n\t\t"autosave"\t\t"1"\n\t}\n\t"castlevania sotn"\n\t{\n'
        '\t\t"template"\t\t"controller_neptune_gamepad+mouse.vdf"\n\t}\n}\n')
    return h, base


MAPA = {"psx-cv": {"console": "psx"}, "switch-z": {"console": "switch"}}


def test_aplicar_e_desfazer(tmp_path):
    h, base = _deck(tmp_path)
    msg = retro.aplicar(h, MAPA)
    assert "em 1 jogo" in msg and "RetroArch" in msg and "DuckStation" in msg and "Dolphin" in msg
    ra = (h / retro.ARQUIVOS["RetroArch"]).read_text()
    assert 'input_save_state = "f9"' in ra and 'video_shader_enable = "true"' in ra
    assert (h / retro.RA / "config/Snes9x/Snes9x.slangp").exists()
    assert 'run_ahead_enabled = "false"' in (h / retro.RA / "config/Mupen64Plus-Next/Mupen64Plus-Next.cfg").read_text()
    lay = (base / "castlevania sotn/controller_neptune.vdf").read_text()
    assert "key_press F9" in lay and not (base / "zelda botw").exists()  # Switch não usa estes emuladores
    cs = vdf.load_text((base / "configset_controller_neptune.vdf").read_text())["controller_config"]
    assert cs["castlevania sotn"] == {"autosave": "1"} and cs["pcsx2"] == {"autosave": "1"}
    r = retro.preparar(h, MAPA)  # o painel escolhe este modelo em cada jogo, ao vivo (testado no Deck em 11/11)
    assert r["appids"] == [1] and r["modelo"] == "template://controller_neptune_dc_retro.vdf"
    modelo = (h / ".local/share/Steam/controller_base/templates/controller_neptune_dc_retro.vdf").read_text()
    assert "key_press F12, Turbo liga-desliga" in modelo  # (o título "Deck Commander Retro" troca o do modelo real do Steam)
    assert retro.estado(h)["aplicado"] and retro.estado(h)["turbo"] == 2.0
    assert "RetroArch" in retro.desfazer(h)
    assert 'input_save_state = "f2"' in (h / retro.ARQUIVOS["RetroArch"]).read_text()


def test_vdf_texto_ida_e_volta():
    d = {"controller_config": {"a b": {"autosave": "1"}, "x": {"template": 'c"d'}}}
    assert vdf.load_text(vdf.dump_text(d)) == d
