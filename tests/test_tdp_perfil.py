from types import SimpleNamespace

from dc import tdp_perfil as P


def test_profile_is_per_game_and_only_accepts_sane_watts(tmp_path):
    paths = SimpleNamespace(state=tmp_path / "state")
    assert P.recomendado(paths, "ps2-dmc", "ps2") is None
    assert P.confirmar(paths, "ps2-dmc", "ps2", 13)
    assert P.recomendado(paths, "ps2-dmc", "ps2") == 13
    assert P.recomendado(paths, "ps2-dmc", "psp") is None
    assert not P.confirmar(paths, "ps2-dmc", "ps2", 13)
    assert not P.confirmar(paths, "ps2-dmc", "ps2", 2)
