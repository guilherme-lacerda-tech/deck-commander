"""Limite de quadros preso em 30 deixava o NES em câmera lenta (achado no Deck 14/11/2026)."""
from dc import quadros as Q
from dc.paths import get_paths


class _R:
    returncode = 0


def test_solta_o_limite_duas_vezes(monkeypatch):
    chamadas, esperas = [], []
    n = Q.soltar(rodar=lambda cmd, **k: chamadas.append(cmd) or _R(), dormir=esperas.append)
    assert n == 2 and chamadas == [["gamescopectl", "debug_set_fps_limit", "0"]] * 2 and esperas == list(Q.ESPERAS)


def test_so_emulador_e_respeita_quem_quer_manter(tmp_path, monkeypatch):
    p = get_paths(tmp_path).ensure()
    monkeypatch.setattr(Q.shutil, "which", lambda n: "/usr/bin/gamescopectl")
    steam = {"SteamGameId": "123"}
    assert Q.deve_soltar(p, "nes", steam) and Q.deve_soltar(p, "ps2", steam)
    assert not Q.deve_soltar(p, "pc", steam) and not Q.deve_soltar(p, "steam", steam)  # PC: fica o que você escolheu
    assert not Q.deve_soltar(p, "nes", {})  # fora da Steam (testes, terminal): não mexe na tela
    (p.config / "limite-quadros-manter").write_text("1")
    assert not Q.deve_soltar(p, "nes", steam)


def test_fora_do_modo_de_jogo_nao_faz_nada(tmp_path, monkeypatch):
    p = get_paths(tmp_path).ensure()
    monkeypatch.setattr(Q.shutil, "which", lambda n: None)
    abertos = []
    steam = {"SteamGameId": "123"}
    assert not Q.em_segundo_plano(p, "nes", abrir=lambda *a, **k: abertos.append(a), ambiente=steam)
    monkeypatch.setattr(Q.shutil, "which", lambda n: "/usr/bin/gamescopectl")
    assert Q.em_segundo_plano(p, "nes", abrir=lambda *a, **k: abertos.append(a), ambiente=steam)
    assert abertos[0][0][-2:] == ["dc.quadros", "soltar"]
