"""Falha real 14/11/2026: a cópia do Nova the Squirrel traduzida pela IA travava depois do Start e tinha SUBSTITUÍDO
o original na biblioteca. Tradução por IA (não conferida jogando) entra AO LADO do original."""
import json
from pathlib import Path

from dc import remove, syncer
from dc.paths import get_paths
from dc.traducao import rts, run


class _Rep:
    def __init__(self, out):
        self.output, self.candidates, self.translated, self.flagged = str(out), 100, 50, 0
        self.provider, self.patch, self.errors = "ia", "", []

    def text(self):
        return "ok"


def test_ia_retro_nao_esconde_o_original(tmp_path, monkeypatch):
    P = get_paths(tmp_path).ensure()
    rom = tmp_path / "roms/nes/Nova/Nova.nes"
    rom.parent.mkdir(parents=True)
    rom.write_bytes(b"NES\x1a" + b"\0" * 64)
    (P.data / "launch-map.json").write_text(json.dumps({"nes-nova": {"title": "Nova", "console": "nes",
                                                                      "rom": str(rom)}}))
    saida = rom.with_name("Nova (PT-BR).nes")
    monkeypatch.setattr(rts, "supported", lambda c, r: (True, ""))
    monkeypatch.setattr(rts, "translate_rom", lambda *a, **k: (saida.write_bytes(b"x"), _Rep(saida))[1])
    monkeypatch.setattr(syncer, "add_to_steam", lambda *a: [])
    escondidos = []
    monkeypatch.setattr(remove, "hide", lambda paths, gid, motivo: escondidos.append(gid))
    monkeypatch.setattr(run, "_herdar_detonado", lambda *a: None)
    monkeypatch.setattr(run, "_refresh_tabs", lambda *a: None)

    class Store:
        def enqueue(self, *a, **k): return "op"
        def claim(self, op): pass
        def finish(self, *a, **k): pass
    job = {"op": "j1", "type": "translate_retro", "game_id": "nes-nova", "args": {}}
    _res, texto, ok = run._dispatch(P, Store(), job, {}, lambda *a: None, lambda: False)
    assert ok and escondidos == []  # o original continua na biblioteca
    assert Path(saida).exists()
