from datetime import datetime

from dc import shaders_noite as S


def test_rodada(tmp_path):
    lm = {"switch-a": {"title": "A", "console": "switch"}, "snes-b": {"title": "B", "console": "snes"},
          "ps2-c": {"title": "C", "console": "ps2"}, "wii-d": {"title": "D", "console": "wii", "removed": True},
          "gc-e": {"title": "E", "console": "gc"}}
    ult = {"gc-e": datetime(2026, 1, 1)}
    assert S.pendentes(lm, {}, ult) == ["switch-a", "ps2-c"] or S.pendentes(lm, {}, ult) == ["switch-a", "ps2-c"][::-1] \
        or sorted(S.pendentes(lm, {}, ult)) == ["ps2-c", "switch-a"]
    assert not S.pode_rodar(datetime(2026, 1, 1, 14), True, False)
    assert not S.pode_rodar(datetime(2026, 1, 1, 3), False, False)
    est = S.Estado(tmp_path / "s.json")
    abertos = []
    feitos = S.rodada(lm, est, ult, lambda g, s: abertos.append(g) or True, datetime(2026, 1, 1, 3), True,
                      lambda: False, log=lambda *a: None)
    assert sorted(feitos) == ["ps2-c", "switch-a"] and abertos == feitos and len(abertos) == 2
    assert S.rodada(lm, S.Estado(tmp_path / "s.json"), ult, lambda g, s: True, datetime(2026, 1, 1, 3), True,
                    lambda: False, log=lambda *a: None) == []
    # usuário abriu um jogo no meio: para
    est2 = S.Estado(tmp_path / "s2.json")
    chamadas = iter([False, False, True, True])
    assert len(S.rodada(lm, est2, ult, lambda g, s: True, datetime(2026, 1, 1, 3), True, lambda: next(chamadas),
                        log=lambda *a: None)) == 1
