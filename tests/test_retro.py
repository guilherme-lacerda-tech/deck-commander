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


def test_jogo_novo_depois_de_ligado_ganha_os_botoes(tmp_path):
    """Falha real 11/11/2026: a cópia PT-BR do Castlevania entrou como atalho NOVO depois dos botões ligados e ficou
    sem L4/R4/L5/R5 (turbo e salvar "pararam"). Todo jogo retrô que entrar depois precisa ganhar os botões."""
    h, base = _deck(tmp_path)
    assert retro.jogos_para_o_painel(h, MAPA) == {"appids": [], "modelo": None}  # ainda não ligado: não mexe
    retro.aplicar(h, MAPA)
    cfg = h / ".local/share/Steam/userdata/42/config/shortcuts.vdf"
    novos = {"0": {"appid": 1, "AppName": "Castlevania SOTN", "LaunchOptions": "psx-cv"},
             "1": {"appid": 3, "AppName": "Castlevania SOTN (PT-BR)", "LaunchOptions": "psx-cv-pt"}}
    cfg.write_bytes(vdf.dump_binary({"shortcuts": novos}))
    r = retro.jogos_para_o_painel(h, dict(MAPA, **{"psx-cv-pt": {"console": "psx"}}))
    assert r["appids"] == [3] and r["modelo"] == "template://controller_neptune_dc_retro.vdf"  # só o novo
    assert "key_press F9" in (base / "castlevania sotn (pt-br)/controller_neptune.vdf").read_text()


def test_layout_que_o_usuario_trocou_nao_e_sobrescrito(tmp_path):
    """Revisão de lançamento 12/11/2026: a cada reinício do Decky o painel reaplicava o modelo em TODOS os jogos e
    regravava o layout de quem tinha tirado os botões de trás. Cada jogo é mexido uma vez; depois é do usuário."""
    h, base = _deck(tmp_path)
    retro.aplicar(h, MAPA)
    lay = base / "castlevania sotn/controller_neptune.vdf"
    lay.write_text(LAYOUT)  # usuário montou o layout dele, sem os botões de trás
    for _ in range(3):  # vários "reinícios" do Decky
        assert retro.jogos_para_o_painel(h, MAPA)["appids"] == []
    assert lay.read_text() == LAYOUT
    retro.preparar(h, MAPA)  # mas se ELE apertar "Ligar" de novo, vale para todos
    assert "key_press F9" in lay.read_text()


def test_desfazer_devolve_os_layouts_do_steam(tmp_path):
    """Desinstalar/desfazer deixava os layouts de controle e o modelo "Deck Commander Retro" para trás."""
    h, base = _deck(tmp_path)
    retro.aplicar(h, MAPA)
    tpl = h / ".local/share/Steam/controller_base/templates" / retro.MODELO
    assert tpl.exists() and (base / "castlevania sotn/controller_neptune.vdf").exists()
    msg = retro.desfazer(h)
    assert "1 jogo" in msg and not tpl.exists()
    assert not (base / "castlevania sotn/controller_neptune.vdf").exists()  # foi ele que criou: some
    cs = vdf.load_text((base / "configset_controller_neptune.vdf").read_text())["controller_config"]
    assert cs["castlevania sotn"] == {"template": "controller_neptune_gamepad+mouse.vdf"}  # o que o usuário tinha


def test_painel_aplica_botoes_em_jogo_novo_sozinho():
    """Mesma falha: o ciclo do painel (a cada 10 s) precisa chamar retro_jogos e escolher o modelo nos appids novos."""
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / "decky-plugin/dist/index.js").read_text("utf-8")
    assert '["botões de trás", retroBotoes]' in js and 'call("painel", "retro_jogos"' in js
    from dc import painel
    assert "retro_jogos" in painel.ACOES


def test_painel_nao_abre_python_a_cada_minuto():
    """Revisão de lançamento 12/11/2026 (bateria): o ciclo abria um Python a cada ~1 min, até durante o jogo.
    Agora: ao ligar, quando entra atalho novo (algumas tentativas) e uma checagem a cada 30 min."""
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / "decky-plugin/dist/index.js").read_text("utf-8")
    assert "retroConta++ % 6" not in js and "% 180 !== 0" in js
    assert js.count("retroPendente = 12") == 2  # fila (atalho novo) e autocorreção (atalho recriado)


def test_save_state_nao_apaga_o_anterior(tmp_path):
    """Revisão retrô 12/11/2026: L4 gravava sempre no mesmo espaço; um toque sem querer apagava o save bom."""
    h, _base = _deck(tmp_path)
    retro.aplicar(h, MAPA)
    ra = (h / retro.ARQUIVOS["RetroArch"]).read_text()
    assert 'savestate_auto_index = "true"' in ra and 'savestate_max_keep = "10"' in ra
    ds = (h / retro.ARQUIVOS["DuckStation"]).read_text()
    assert "CreateSaveStateBackups = true" in ds


def test_config_antiga_fecha_a_porta_e_tira_o_hardcore(tmp_path, monkeypatch):
    """Quem ligou o Retrô antes da 0.8.1 ficou com a porta 55355 aberta para a rede e o hardcore marcado."""
    ra = tmp_path / retro.ARQUIVOS["RetroArch"]
    ra.parent.mkdir(parents=True)
    ra.write_text('network_cmd_enable = "true"\ncheevos_enable = "false"\ncheevos_hardcore_mode_enable = "true"\n')
    monkeypatch.setattr(retro, "_retroarch_aberto", lambda: True)
    assert retro.corrigir_retroarch_antigo(tmp_path) is False  # aberto: ele regravaria ao fechar
    monkeypatch.setattr(retro, "_retroarch_aberto", lambda: False)
    assert retro.corrigir_retroarch_antigo(tmp_path) is True
    t = ra.read_text()
    assert 'network_cmd_enable = "false"' in t and 'cheevos_hardcore_mode_enable = "false"' in t
    assert retro.corrigir_retroarch_antigo(tmp_path) is False  # já está certo: não regrava
