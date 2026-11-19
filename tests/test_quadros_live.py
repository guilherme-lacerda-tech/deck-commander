"""Correção imediata do limitador de FPS do SteamOS."""
from types import SimpleNamespace

from dc import quadros


def test_soltar_agora_during_a_running_game():
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0)

    assert quadros.soltar_agora(run) is True
    assert calls == [(["gamescopectl", "debug_set_fps_limit", "0"],
                      {"capture_output": True, "timeout": 3, "check": False})]


def test_soltar_agora_does_not_crash_the_game_if_gamescope_is_unavailable():
    def run(*args, **kwargs):
        raise OSError("sem gamescope")

    assert quadros.soltar_agora(run) is False
