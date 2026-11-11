"""TDP automático por console (dc/tdp.py)."""
from types import SimpleNamespace

from dc import tdp


class Fake:
    def __init__(self, atual=12, maximo=15):
        self.atual, self.max, self.setados = atual, maximo, []

    def __call__(self, args, **kw):
        if "set-property" in args:
            self.atual = int(args[-1]); self.setados.append(self.atual)
            return SimpleNamespace(returncode=0, stdout="")
        prop = args[-1]
        return SimpleNamespace(returncode=0, stdout=f"u {self.max if prop == 'TdpLimitMax' else self.atual}\n")


def test_aplica_e_restaura(tmp_path):
    f = Fake()
    t = tdp.Tdp(tmp_path / "st.json", run=f)
    assert t.aplicar_console("psx") == "TDP 7 W para psx (antes 12 W)"
    assert t.aplicar_console("snes") == "TDP 5 W para snes (antes 12 W)"  # o anterior original fica
    assert "12 W" in t.restaurar() and f.atual == 12 and not (tmp_path / "st.json").exists()
    t.aplicar_console("ps2", em_dock=True)
    assert f.atual == 15
    assert "não reconhecido" in t.aplicar_console("zx81")


def test_dock(tmp_path):
    for nome, st in (("card0-eDP-1", "connected"), ("card0-DP-1", "disconnected")):
        (tmp_path / nome).mkdir(); (tmp_path / nome / "status").write_text(st + "\n")
    assert not tdp.em_dock(tmp_path)
    (tmp_path / "card0-DP-1" / "status").write_text("connected\n")
    assert tdp.em_dock(tmp_path)
