"""Continuar de onde parou (pedido 13/11/2026): ponto salvo por jogo, sem tocar nos saves do L4, e abrir nele."""
import json
from pathlib import Path

from dc import continuar as C
from dc.paths import get_paths

DUCK = ["/usr/bin/env", "ENABLE_GAMESCOPE_WSI=0", "/x/DuckStation-x64.AppImage", "-fullscreen", "-batch", "--", "/r/j.cue"]
PSP = ["flatpak", "run", "org.ppsspp.PPSSPP", "/r/jogo.iso"]


def _emus(monkeypatch, tmp_path):
    pastas = {}
    for k, e in C.EMUS.items():
        d = tmp_path / "estados" / k
        d.mkdir(parents=True)
        pastas[k] = d
        monkeypatch.setattr(e, "pastas", [d])
    return pastas


def test_duckstation_salva_o_ponto_e_abre_nele(tmp_path, monkeypatch):
    p = get_paths(tmp_path / "dc").ensure()
    pastas = _emus(monkeypatch, tmp_path)
    (pastas["duckstation"] / "SLES-00524_1.sav").write_bytes(b"save do L4")
    apertos = []

    def tecla(display, t):
        apertos.append((display, t))
        (pastas["duckstation"] / "savestate_10.sav").write_bytes(b"ponto")
        return True

    arq = C.salvar_ponto(p, "psx-sotn", DUCK, ":1", tecla_fn=tecla)
    assert apertos == [(":1", "ctrl+F9")] and Path(arq).read_bytes() == b"ponto"
    assert (pastas["duckstation"] / "SLES-00524_1.sav").read_bytes() == b"save do L4"  # o seu save não muda
    cmd, msg = C.ao_abrir(p, "psx-sotn", DUCK, "/r/j.cue", versao_fn=lambda c: None)
    assert cmd[cmd.index("-statefile") + 1] == arq and cmd.index("-statefile") < cmd.index("--")
    assert "ponto salvo" in msg


def test_versao_diferente_abre_normal(tmp_path, monkeypatch):
    p = get_paths(tmp_path / "dc").ensure()
    pastas = _emus(monkeypatch, tmp_path)
    monkeypatch.setattr("dc.versao_emulador.identidade", lambda c: "v1")
    C.salvar_ponto(p, "psx-sotn", DUCK, ":1",
                   tecla_fn=lambda d, t: (pastas["duckstation"] / "savestate_10.sav").write_bytes(b"x") or True)
    cmd, msg = C.ao_abrir(p, "psx-sotn", DUCK, "/r/j.cue", versao_fn=lambda c: "v2")
    assert cmd == DUCK and "mudou de versão" in msg  # estado de outra versão pode travar: não carrega


def test_ppsspp_devolve_o_espaco_que_usou(tmp_path, monkeypatch):
    p = get_paths(tmp_path / "dc").ensure()
    pastas = _emus(monkeypatch, tmp_path)
    slot = pastas["ppsspp"] / "ULUS10041_1.00_0.ppst"
    slot.write_bytes(b"save do usuario")

    def tecla(display, t):
        assert t == "F2"
        import os
        import time
        slot.write_bytes(b"ponto novo"); os.utime(slot, (time.time() + 1, time.time() + 1))
        return True

    arq = C.salvar_ponto(p, "psp-jogo", PSP, ":1", tecla_fn=tecla)
    assert Path(arq).read_bytes() == b"ponto novo" and slot.read_bytes() == b"save do usuario"
    cmd, _ = C.ao_abrir(p, "psp-jogo", PSP, "/r/jogo.iso", versao_fn=lambda c: None)
    assert cmd[-2] == f"--state={arq}" and cmd[-1] == "/r/jogo.iso"


def test_sem_save_rapido_ou_desligado_nao_faz_nada(tmp_path, monkeypatch):
    p = get_paths(tmp_path / "dc").ensure()
    _emus(monkeypatch, tmp_path)
    ryu = ["/x/Ryujinx", "jogo.nsp"]
    assert C.salvar_ponto(p, "switch-x", ryu, ":1", tecla_fn=lambda d, t: 1 / 0) is None
    assert C.ao_abrir(p, "switch-x", ryu, "jogo.nsp") == (ryu, None)
    C.definir(p, False)
    assert C.salvar_ponto(p, "psx-sotn", DUCK, ":1", tecla_fn=lambda d, t: 1 / 0) is None


def test_tecla_sem_resposta_nao_guarda_nada(tmp_path, monkeypatch):
    p = get_paths(tmp_path / "dc").ensure()
    _emus(monkeypatch, tmp_path)
    assert C.salvar_ponto(p, "psx-sotn", DUCK, ":1", espera=0.5, tecla_fn=lambda d, t: True) is None
    assert C.ponto(p, "psx-sotn") is None


def test_atalho_do_ponto_vai_para_a_configuracao(tmp_path, monkeypatch):
    ini = tmp_path / "settings.ini"
    ini.write_text("[Main]\nA = 1\n[Hotkeys]\nSaveSelectedSaveState = Keyboard/F9\n[PIO]\nX = 1\n")
    monkeypatch.setitem(C.ATALHOS, "duckstation", [(ini, "Hotkeys", "SaveGameState10", "Keyboard/Control & Keyboard/F9")])
    assert C.preparar("duckstation")
    t = ini.read_text()
    assert t.index("SaveGameState10 = Keyboard/Control & Keyboard/F9") < t.index("[PIO]")
    assert "SaveSelectedSaveState = Keyboard/F9" in t and not C.preparar("duckstation")  # 2ª vez: nada


def test_salvar_agora_usa_o_jogo_aberto(tmp_path, monkeypatch):
    p = get_paths(tmp_path / "dc").ensure()
    (p.state / "jogo-aberto.json").write_text(json.dumps({"game_id": "psx-sotn", "cmd": DUCK, "display": ":1"}))
    chamado = {}
    monkeypatch.setattr(C, "salvar_ponto", lambda *a, **k: chamado.setdefault("a", a) or "x")
    assert "salvo" in C.salvar_agora(p, "botão Steam") and chamado["a"][1] == "psx-sotn"
    (p.state / "jogo-aberto.json").unlink()
    assert C.salvar_agora(p) == "nenhum jogo aberto"


def test_voltar_no_tempo_segura_o_f11(tmp_path, monkeypatch):
    p = get_paths(tmp_path / "dc").ensure()
    monkeypatch.setattr(C.time, "sleep", lambda s: acoes.append(("espera", s)))
    acoes = []
    (p.state / "jogo-aberto.json").write_text(json.dumps({"game_id": "psx-sotn", "cmd": DUCK, "display": ":1"}))
    msg = C.voltar_no_tempo(p, 30, tecla_fn=acoes.append)
    assert acoes == ["keydown", ("espera", 5.0), "keyup"] and "10 s" in msg  # DuckStation guarda 10 s
    (p.state / "jogo-aberto.json").write_text(json.dumps({"game_id": "ps2-gow", "cmd": ["flatpak", "run",
                                                         "net.pcsx2.PCSX2", "x.iso"], "display": ":1"}))
    assert "não tem voltar no tempo" in C.voltar_no_tempo(p, 5, tecla_fn=acoes.append)


def test_bot_continuar(tmp_path):
    from dc import bot
    paths = get_paths(tmp_path).ensure()
    x = bot.Bot(paths, "T"); x.cfg["allowed"] = [1]
    assert "LIGADO" in x.handle(1, 1, "/continuar")
    assert "DESLIGADO" in x.handle(1, 1, "/continuar nao") and not C.ligado(paths)


def test_meta_de_quadros_pal():
    """Castlevania PAL (50 quadros) era julgado "travando" porque a meta era sempre 60."""
    from dc import perf
    assert perf.meta_quadros([50.0] * 100) == 50 and perf.meta_quadros([59.9] * 90 + [40.0] * 10) == 60
    assert perf.meta_quadros([30.0] * 50) == 30 and perf.meta_quadros([25.0] * 50) == 25
    assert perf.verdict(49.8, 49, 0.0, perf.meta_quadros([49.8] * 100)) == "liso"


def test_medidor_de_desempenho_na_frente_nao_confunde(tmp_path, monkeypatch):
    """Falha no Deck 13/11/2026: o MangoHud põe outro "/usr/bin/env" na frente; a versão lida era a do env."""
    from dc import versao_emulador as V
    com_medidor = ["/usr/bin/env", "MANGOHUD=1", "MANGOHUD_CONFIG=a=0"] + DUCK
    assert V._sem_env(com_medidor)[0] == "/x/DuckStation-x64.AppImage" and C.qual(com_medidor) == "duckstation"


def test_flatpak_com_opcoes_do_medidor():
    """Falha no Deck 13/11/2026: o MangoHud põe --env/--filesystem entre "run" e o app; o PCSX2 não era reconhecido."""
    cmd = ["flatpak", "run", "--env=MANGOHUD=1", "--filesystem=/x", "--env=VK_ADD_LAYER_PATH=/y", "net.pcsx2.PCSX2",
           "-fullscreen", "-batch", "--", "/roms/ps2/Dolphin (Retroarch).iso"]
    assert C.qual(cmd) == "pcsx2" and C.qual(["/x/Ryujinx", "/roms/ps2/duckstation.iso"]) is None
