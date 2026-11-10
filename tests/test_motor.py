"""Nada fica 'impossível' para sempre: marca/falha de versão antiga é tentada de novo; o bot diz o motor."""
from dc.traducao import motor, run


class _Store:
    def list(self, *a, **k):
        return []


def test_identify_engines():
    assert motor.identify(["FFRS/Content/Paks/FFRS-Switch.pak", "FFRS/Content/Paks/FFRS-Switch.utoc"])["motor"] \
        == "Unreal Engine"
    assert motor.identify(["Data/data.unity3d"])["motor"] == "Unity"
    assert motor.identify(["Message/Talk.msbt"])["traduzo"]
    assert motor.identify(["natives/stm/message/a.msg.539100710"])["motor"] == "RE Engine (Capcom)"
    u = motor.identify(["a/b.xyz", "a/c.xyz", "d.bin"])
    assert u["motor"] == "desconhecido" and ".xyz" in u["caminho"]


def test_stale_marks_are_retried():
    assert motor.stale({}) and motor.stale({"motor_versao": motor.VERSAO - 1})
    assert not motor.stale({"motor_versao": motor.VERSAO})


def test_translator_for_retries_old_closed_and_failed(tmp_path):
    from dc.paths import get_paths
    paths = get_paths(tmp_path / "dc").ensure()
    g = {"title": "Jogo", "console": "switch", "rom": "/x/Jogo [0100AAAA00000000][v0].nsp"}
    old = {"j": {"formato": "fechado"}}
    assert run.translator_for(paths, _Store(), "j", g, old, [])[0] == "ok"
    new = {"j": {"formato": "fechado", "motor_versao": motor.VERSAO}}
    assert run.translator_for(paths, _Store(), "j", g, new, [])[0] == "sem"
    failed_old = [{"game_id": "j", "type": "translate_switch", "status": "falhou"}]
    failed_new = [{**failed_old[0], "motor_versao": motor.VERSAO}]
    assert run.translator_for(paths, _Store(), "j", g, {}, failed_old)[0] == "ok"
    assert run.translator_for(paths, _Store(), "j", g, {}, failed_new)[0] == "falhou"
