"""Pedido 12/11/2026: saves do jogo guardados sozinhos (5 últimas versões), antes de cada sessão."""
import os

from dc import copia_saves as C
from dc.paths import get_paths


def _ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("DC_BACKUP_DIR", str(tmp_path / "bk"))
    monkeypatch.setenv("HOME", str(tmp_path)); monkeypatch.setenv("USERPROFILE", str(tmp_path))
    card = tmp_path / "memcards" / "Castlevania_1.mcd"
    card.parent.mkdir(parents=True)
    card.write_bytes(b"save 0")
    listar = lambda gid: [{"origem": str(card), "destino": "{EMU}/memcards/Castlevania_1.mcd"}]  # noqa: E731
    return get_paths(), card, listar


def _mexe(card, conteudo, t):
    card.write_bytes(conteudo); os.utime(card, (t, t))


def test_guarda_so_quando_muda_e_fica_com_as_5_ultimas(tmp_path, monkeypatch):
    paths, card, listar = _ambiente(tmp_path, monkeypatch)
    monkeypatch.setattr(C, "datetime", _Relogio(0))
    _mexe(card, b"save 0", 1000)
    assert C.guardar(paths, "sotn", listar=listar)
    assert C.guardar(paths, "sotn", listar=listar) is None  # nada mudou: não duplica
    for i in range(1, 8):
        monkeypatch.setattr(C, "datetime", _Relogio(i))
        _mexe(card, f"save {i}".encode(), 1000 + i)
        C.guardar(paths, "sotn", listar=listar)
    cs = C.copias(paths, "sotn")
    assert len(cs) == 5
    assert (cs[0] / "emulador/memcards/Castlevania_1.mcd").read_bytes() == b"save 7"


def test_voltar_devolve_e_guarda_o_atual_antes(tmp_path, monkeypatch):
    paths, card, listar = _ambiente(tmp_path, monkeypatch)
    monkeypatch.setattr(C, "datetime", _Relogio(1)); _mexe(card, b"bom", 1000); C.guardar(paths, "sotn", listar=listar)
    monkeypatch.setattr(C, "datetime", _Relogio(2)); _mexe(card, b"estragado", 2000)
    C.voltar(paths, "sotn", 1, listar=listar)
    assert card.read_bytes() == b"bom"
    assert (C.copias(paths, "sotn")[0] / "emulador/memcards/Castlevania_1.mcd").read_bytes() == b"estragado"


def test_retroarch_grava_o_save_do_jogo_sem_esperar_fechar():
    from dc import retro_hacks as R
    assert 'autosave_interval = "10"' in R.cfg_retroarch("")


class _Relogio:
    def __init__(self, s):
        self.s = s

    def now(self, tz=None):
        from datetime import datetime
        return datetime(2026, 11, 12, 10, 0, self.s, tzinfo=tz)


def test_bot_lista_e_volta_a_copia(tmp_path, monkeypatch):
    from dc import bot, ops
    paths = get_paths(tmp_path / "dc").ensure()
    card = tmp_path / "Castlevania_1.mcd"
    listar = lambda gid: [{"origem": str(card), "destino": "{EMU}/memcards/Castlevania_1.mcd"}]  # noqa: E731
    monkeypatch.setattr(C, "_saves", listar)
    monkeypatch.setattr(C.voltar, "__defaults__", (1, listar))
    monkeypatch.setattr(ops, "game_running", lambda: False)
    x = bot.Bot(paths, "T"); x.cfg["allowed"] = [1]
    monkeypatch.setattr(x, "_map", lambda: {"psx-sotn": {"title": "Castlevania", "console": "psx", "rom": "/x"}})
    assert "nenhuma cópia" in x.handle(1, 1, "/saves copias castlevania")
    monkeypatch.setattr(C, "datetime", _Relogio(1)); _mexe(card, b"bom", 1000); C.guardar(paths, "psx-sotn", listar=listar)
    assert "1. 2026-11-12 10-00-01 UTC" in x.handle(1, 1, "/saves copias castlevania")
    monkeypatch.setattr(C, "datetime", _Relogio(2)); _mexe(card, b"ruim", 2000)
    assert "voltaram" in x.handle(1, 1, "/saves voltar castlevania 1")
    assert card.read_bytes() == b"bom"
