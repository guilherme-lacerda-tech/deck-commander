"""Escolha simples do layout dos botões (Controle de Xbox / Controle de Switch) no Ryujinx e no Lichii."""
import json

from dc import controls

LICHII = '''[Controls]
player_0_button_a="engine:sdl,guid:abc,port:0,button:0"
player_0_button_b="engine:sdl,guid:abc,port:0,button:1"
player_0_button_x="engine:sdl,guid:abc,port:0,button:2"
player_0_button_y="engine:sdl,guid:abc,port:0,button:3"
player_0_button_l="engine:sdl,guid:abc,port:0,button:9"
'''


def test_lichii_troca_e_volta(tmp_path):
    p = tmp_path / ".config/eden/qt-config.ini"
    p.parent.mkdir(parents=True)
    p.write_text(LICHII, "utf-8")
    assert controls.layouts(tmp_path) == [{"id": "lichii", "emulador": "Nintendo Switch 2 (Lichii)", "atual": "xbox",
                                           "opcoes": controls.MODOS}]
    assert controls.definir_layout("lichii", "switch", tmp_path)
    txt = p.read_text("utf-8")
    assert 'player_0_button_a="engine:sdl,guid:abc,port:0,button:1"' in txt and "button:9" in txt
    assert controls.layouts(tmp_path)[0]["atual"] == "switch"
    assert (tmp_path / ".config/eden/qt-config.ini.antes-deck-commander").read_text("utf-8") == LICHII
    controls.definir_layout("lichii", "xbox", tmp_path)
    assert p.read_text("utf-8") == LICHII
    assert controls.definir_layout("lichii", "xbox", tmp_path) == []  # já estava


def test_ryujinx_layout(tmp_path):
    p = tmp_path / ".config/Ryujinx/Config.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"input_config": [{"backend": "GamepadSDL2", "right_joycon": dict(controls.POSITIONAL)}]}))
    assert controls.layouts(tmp_path)[0]["atual"] == "switch"
    controls.definir_layout("ryujinx", "xbox", tmp_path)
    assert controls.layouts(tmp_path)[0]["atual"] == "xbox"


def test_painel_controle_definir(monkeypatch):
    from dc import painel
    monkeypatch.setattr(controls, "definir_layout", lambda i, m, home=controls.H: ["ok"])
    out = painel.controle_definir(None, {"id": "lichii", "modo": "switch"})
    assert "Controle de Switch" in out["texto"]
    import pytest
    with pytest.raises(painel.Erro):
        painel.controle_definir(None, {"id": "lichii", "modo": "ps"})
