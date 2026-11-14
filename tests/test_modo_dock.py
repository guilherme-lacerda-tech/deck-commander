"""Modo dock: com monitor/TV ligado, a resolução sobe para ficar nítida na tela grande, volta ao fechar e nunca
desce o que já estava maior. Sem monitor, nada muda."""
from dc import quality, tdp
from dc.paths import get_paths


def _ini(tmp_path, monkeypatch, valor):
    f = tmp_path / "settings.ini"
    f.write_text(f"[GPU]\nResolutionScale = {valor}\n", "utf-8")
    monkeypatch.setitem(quality.TARGETS, "psx", ("ini", [f], "GPU", "ResolutionScale"))
    return f


def test_dock_raises_resolution_and_restores(tmp_path, monkeypatch):
    P = get_paths(tmp_path).ensure()
    f = _ini(tmp_path, monkeypatch, 2)
    rec = quality.apply_for_launch(P, "psx-jogo", "psx", dock=True)
    assert rec and rec["new"] == "4" and "ResolutionScale = 4" in f.read_text()
    quality.restore(P)
    assert "ResolutionScale = 2" in f.read_text()


def test_handheld_changes_nothing(tmp_path, monkeypatch):
    P = get_paths(tmp_path).ensure()
    _ini(tmp_path, monkeypatch, 2)
    assert quality.apply_for_launch(P, "psx-jogo", "psx", dock=False) is None


def test_dock_never_lowers(tmp_path, monkeypatch):
    P = get_paths(tmp_path).ensure()
    _ini(tmp_path, monkeypatch, 5)
    assert quality.apply_for_launch(P, "psx-jogo", "psx", dock=True) is None


def test_game_override_above_dock_level_is_kept(tmp_path, monkeypatch):
    P = get_paths(tmp_path).ensure()
    f = _ini(tmp_path, monkeypatch, 1)
    quality.set_override(P, "psx-jogo", "psx", "5x")
    quality.apply_for_launch(P, "psx-jogo", "psx", dock=True)
    assert "ResolutionScale = 5" in f.read_text()


def test_dock_can_be_turned_off(tmp_path, monkeypatch):
    P = get_paths(tmp_path).ensure()
    _ini(tmp_path, monkeypatch, 2)
    (P.config / "dock-desligado").write_text("")
    assert quality.apply_for_launch(P, "psx-jogo", "psx", dock=True) is None


def test_switch_not_touched_in_dock():
    assert "switch" not in quality.DOCK_RES  # Ryujinx já roda em modo dock (1080p)


def test_dock_detection(tmp_path):
    for nome, st in (("card0-eDP-1", "connected"), ("card0-DP-1", "disconnected"), ("card0-Writeback-1", "unknown")):
        (tmp_path / nome).mkdir()
        (tmp_path / nome / "status").write_text(st + "\n")
    assert tdp.em_dock(tmp_path) is False
    (tmp_path / "card0-DP-1" / "status").write_text("connected\n")
    assert tdp.em_dock(tmp_path) is True


# ---- troca de monitor com o Deck rodando (dock_watch) ----
import json  # noqa: E402

from dc import dock_watch  # noqa: E402


class FakeTdp:
    feitos = []

    def __init__(self, estado):
        pass

    def maximo(self):
        return 15

    def definir(self, w):
        FakeTdp.feitos.append(w)
        return True


def _w(P, valor):
    return dock_watch.verificar(P, detectar=lambda: valor, tdp_factory=FakeTdp)


def test_first_read_is_not_a_change(tmp_path):
    P = get_paths(tmp_path).ensure()
    assert _w(P, False) is None and _w(P, False) is None
    assert not (P.data / "launch-error.json").exists()


def test_plug_with_game_open_raises_power_now_and_warns(tmp_path):
    P = get_paths(tmp_path).ensure()
    FakeTdp.feitos = []
    _w(P, False)
    (P.state / "jogo-aberto.json").write_text(json.dumps({"game_id": "g", "console": "ps2", "title": "Okami"}))
    (P.state / "tdp-anterior.json").write_text('{"anterior": 12}')
    assert _w(P, True) == "dock: conectado · energia 15 W"
    aviso = json.loads((P.data / "launch-error.json").read_text("utf-8"))
    assert aviso["title"].endswith("monitor conectado") and aviso["message"].startswith("Okami:")
    assert _w(P, False) == "dock: desconectado · energia 12 W"
    assert FakeTdp.feitos == [15, 12]
    assert _w(P, False) is None  # sem troca, sem aviso repetido


def test_plug_without_game_only_warns(tmp_path):
    P = get_paths(tmp_path).ensure()
    FakeTdp.feitos = []
    _w(P, False)
    assert _w(P, True) == "dock: conectado"
    assert FakeTdp.feitos == []
    assert "Os próximos jogos" in json.loads((P.data / "launch-error.json").read_text("utf-8"))["message"]


def test_tdp_off_is_respected(tmp_path):
    P = get_paths(tmp_path).ensure()
    FakeTdp.feitos = []
    _w(P, False)
    (P.state / "jogo-aberto.json").write_text(json.dumps({"game_id": "g", "console": "ps2", "title": "Okami"}))
    (P.state / "tdp-anterior.json").write_text('{"anterior": 12}')
    (P.config / "tdp-desligado").write_text("")
    assert _w(P, True) == "dock: conectado" and FakeTdp.feitos == []


def test_detector_crash_never_raises(tmp_path):
    P = get_paths(tmp_path).ensure()
    assert dock_watch.verificar(P, detectar=lambda: 1 / 0).startswith("dock: erro")
