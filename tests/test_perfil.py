"""Pedido 13/11/2026: perfis Beleza / Desempenho / Retrô com 1 toque (como no PS5)."""
from dc import perfil, quality
from dc.paths import get_paths


def test_perfis_mudam_a_resolucao_e_os_filtros(tmp_path):
    p = get_paths(tmp_path).ensure()
    assert perfil.atual(p) == "auto" and perfil.nivel(p, "ps2", 2, 4) == 2 and perfil.filtros(p) is None
    perfil.definir(p, "beleza")
    assert perfil.nivel(p, "ps2", None, 4) == 3 and perfil.nivel(p, "ps2", 4, 4) == 4  # nunca desce no Beleza
    assert perfil.nivel(p, "nes", None, 4) is None  # console sem resolução: não inventa nível
    assert perfil.filtros(p) is True and not perfil.aprende(p)
    perfil.definir(p, "desempenho")
    assert perfil.nivel(p, "psx", 4, 5) == 1 and perfil.filtros(p) is False
    perfil.definir(p, "retro")
    assert perfil.nivel(p, "psx", 4, 5) == 1 and perfil.filtros(p) is True
    (p.config / "perfil.json").write_text("{lixo")
    assert perfil.atual(p) == "auto"  # arquivo estragado volta ao Automático


def test_desempenho_vale_ate_na_dock(tmp_path, monkeypatch):
    p = get_paths(tmp_path).ensure()
    monkeypatch.setattr(quality, "_target", lambda c: ("ini", tmp_path / "PCSX2.ini", "EmuCore/GS", "upscale_multiplier"))
    assert quality._plan(p, "ps2-gow", "ps2", dock=True)[0][-1] == "2"  # Automático na dock: sobe para 2x
    perfil.definir(p, "desempenho")
    assert quality._plan(p, "ps2-gow", "ps2", dock=True)[0][-1] == "1"
    perfil.definir(p, "beleza")
    assert quality._plan(p, "ps2-gow", "ps2", dock=True)[0][-1] == "3"


def test_bot_perfil(tmp_path):
    from dc import bot
    paths = get_paths(tmp_path).ensure()
    x = bot.Bot(paths, "T"); x.cfg["allowed"] = [1]
    assert "Automático" in x.handle(1, 1, "/perfil")
    assert "Beleza" in x.handle(1, 1, "/perfil beleza") and perfil.atual(paths) == "beleza"
