"""Falha real 15/11/2026: no Deck do irmão do usuário (com EmuDeck) a biblioteca transformou os ~400 jogos de Wii do
EmuDeck em atalhos na Steam. Jogos de outros programas só entram se o usuário liberar o console."""
import json
from pathlib import Path

import pytest

from dc import biblioteca as B
from dc import remove
from dc.library import Game
from dc.paths import get_paths


@pytest.fixture
def P(tmp_path):
    return get_paths(tmp_path / "dc").ensure()


def _emudeck(home: Path) -> Path:
    (home / "emudeck").mkdir(parents=True)
    return home


def _jogos(home: Path):
    return [Game("wii-mario", "Mario", "wii", str(home / "Emulation/roms/wii/Mario.wbfs")),
            Game("ps2-gow", "GoW", "ps2", str(home / "Emulation/roms/ps2/GoW/GoW.iso")),
            Game("ps2-gow-pt-br", "GoW (PT-BR)", "ps2", str(home / "Emulation/roms/ps2/GoW/GoW (PT-BR).iso"))]


def _baixado_pelo_bot(P, caminho: str):
    (P.state / "sync-state.json").write_text(json.dumps({"ingested": {"h": {"name": "x", "files": [caminho]}}}))


def test_sem_outro_gerenciador_tudo_entra(P, tmp_path):
    dentro, fora = B.permitidos(P, _jogos(tmp_path), home=tmp_path)
    assert len(dentro) == 3 and fora == []


def test_com_emudeck_so_entra_o_que_o_deck_commander_trouxe(P, tmp_path):
    home = _emudeck(tmp_path)
    jogos = _jogos(home)
    _baixado_pelo_bot(P, jogos[1].path)
    dentro, fora = B.permitidos(P, jogos, home=home)
    assert [g.game_id for g in dentro] == ["ps2-gow", "ps2-gow-pt-br"]  # baixado + a cópia traduzida
    assert [g.game_id for g in fora] == ["wii-mario"]  # do EmuDeck: fica de fora


def test_pasta_da_varredura_conta_como_do_deck_commander(P, tmp_path):
    home = _emudeck(tmp_path)
    (P.state / "varredura-ultima.json").write_text(json.dumps(
        {"feitos": [{"tipo": "movido", "pasta": str(home / "Emulation/roms/wii")}]}))
    dentro, _ = B.permitidos(P, _jogos(home)[:1], home=home)
    assert [g.game_id for g in dentro] == ["wii-mario"]


def test_console_liberado_entra(P, tmp_path):
    home = _emudeck(tmp_path)
    B.salvar(P, {"importar": {"wii": True}})
    dentro, _fora = B.permitidos(P, _jogos(home), home=home)
    assert "wii-mario" in [g.game_id for g in dentro]


def test_migracao_tira_uma_vez_os_jogos_do_emudeck(P, tmp_path, monkeypatch):
    home = _emudeck(tmp_path)
    jogos = _jogos(home)
    _baixado_pelo_bot(P, jogos[1].path)
    lm = {g.game_id: {"title": g.title, "console": g.console, "rom": g.path} for g in jogos}
    lm["pc-x"] = {"title": "PC", "console": "pc", "rom": ""}
    (P.data / "launch-map.json").write_text(json.dumps(lm))
    escondidos = []
    monkeypatch.setattr(remove, "hide", lambda paths, gid, motivo: escondidos.append(gid))
    msg = B.migrar(P, home=home)
    assert escondidos == ["wii-mario"] and "Wii (1)" in msg and "importar" in msg
    assert B.migrar(P, home=home) is None  # só uma vez
    assert B.migrar(P, home=tmp_path / "sem-emudeck") is None


def test_importar_e_tirar_um_console(P, tmp_path, monkeypatch):
    jogos = _jogos(tmp_path)
    lm = {g.game_id: {"title": g.title, "console": g.console, "rom": g.path, "removed": True} for g in jogos[:1]}
    (P.data / "launch-map.json").write_text(json.dumps(lm))
    voltaram, sairam = [], []
    monkeypatch.setattr(remove, "bring_back", lambda paths, gid: voltaram.append(gid))
    monkeypatch.setattr(remove, "hide", lambda paths, gid, motivo: sairam.append(gid))
    assert "1 voltaram" in B.importar(P, "wii", True)
    assert B.carregar(P)["importar"]["wii"] is True and voltaram == ["wii-mario"]
    lm["wii-mario"].pop("removed")
    (P.data / "launch-map.json").write_text(json.dumps(lm))
    assert "1 jogo(s) de wii" in B.importar(P, "wii", False) and sairam == ["wii-mario"]


def test_sync_nao_cria_atalho_para_jogo_do_emudeck(P, tmp_path, monkeypatch):
    from dc import library, syncer
    home = _emudeck(tmp_path)
    jogos = _jogos(home)
    _baixado_pelo_bot(P, jogos[1].path)
    monkeypatch.setattr(library, "scan", lambda roots: (jogos, []))
    monkeypatch.setattr(B, "outro_gerenciador", lambda home=None: "EmuDeck")
    vistos = []

    class Plano:
        add, name_conflicts = [], []
    monkeypatch.setattr(library, "plan", lambda existing, games, launcher: vistos.extend(games) or Plano())
    monkeypatch.setattr(library, "write_map", lambda p, games: None)
    monkeypatch.setattr(syncer, "shortcuts_path", lambda: tmp_path / "shortcuts.vdf")
    monkeypatch.setattr("dc.vdf.read_shortcuts", lambda p: [])
    monkeypatch.setattr("dc.ops.index_files", lambda store, games: 0)
    syncer._add_to_steam(P, object(), "op")
    assert {g.game_id for g in vistos} == {"ps2-gow", "ps2-gow-pt-br"}
