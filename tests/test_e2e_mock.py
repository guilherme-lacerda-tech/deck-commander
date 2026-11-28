"""Simulação isolada: busca, torrent, download e importação local (sem RomM)."""
import json
from pathlib import Path

from dc import bot, prowlarr, syncer, ops
from dc.paths import get_paths


TORRENT = b"d8:announce3:url4:infod4:name5:Mario12:piece lengthi16384eee"


def test_nome_torrent_e_sincronizacao_simulados(tmp_path, monkeypatch):
    paths = get_paths(tmp_path / "dc").ensure()
    downloads, roms = tmp_path / "downloads", tmp_path / "roms"
    b = bot.Bot(paths, "token")
    b.cfg["allowed"] = [1]
    respostas = []
    b.call = lambda method, **kw: respostas.append(kw) or {}
    b.limited = lambda uid: False
    class QbtMock:
        def __init__(self): self.entrou = False
        def add_file(self, data, name, category, dest, **kwargs):
            assert data == TORRENT and category == "gba"
            self.entrou = True
        def torrents(self, *a, **kw):
            return [{"hash": "a" * 40, "state": "uploading", "name": "Jogo",
                     "content_path": str(downloads / "jogo.gba"), "category": "gba"}] if self.entrou else []
    b.qbt = QbtMock()
    monkeypatch.setattr(syncer, "_cfg", lambda p: {"downloads_root": str(downloads), "roms_root": str(roms),
                                                     "sync_during_game": "block"})
    monkeypatch.setattr(ops, "game_running", lambda: False)
    monkeypatch.setattr(prowlarr, "configuracao", lambda p: ("http://localhost:9696", "k"))
    monkeypatch.setattr(prowlarr, "pesquisar", lambda p, titulo, **kw: [{"titulo": "Jogo [GBA]", "magnet": "",
                                                                         "download_url": "http://localhost:9696/d"}])
    from dc import busca
    monkeypatch.setattr(busca, "config", lambda paths: {"provedores": ["prowlarr"]})
    monkeypatch.setattr(prowlarr, "baixar_torrent", lambda p, url: TORRENT)
    monkeypatch.setattr(b, "_already", lambda *a: None)
    monkeypatch.setattr(syncer, "add_to_steam", lambda *a: [])
    def enviar(t):
        return b.handle_message({"from": {"id": 1}, "chat": {"id": 1}, "text": t})
    assert "Pesquisando" in enviar("Jogo")
    for v in b.buscas.values():
        v["future"].result(timeout=5)
    b.notify_buscas()
    assert "Jogo [GBA]" in respostas[-1]["text"]
    sid = b.cfg["ultima_busca"]["1"]
    rid = b.cfg["buscas"][sid]["resultados"][0]["rid"]
    assert "Steam Deck" in enviar(f"/bi {sid} {rid}")
    resposta = enviar(f"/bd {sid} {rid} deck")
    assert "Adicionado" in resposta
    downloads.mkdir()
    (downloads / "jogo.gba").write_bytes(b"conteudo-simulado")
    resposta = syncer.run_sync(paths, b.store, b.qbt)
    assert "jogo" in resposta.lower()
    assert list(roms.rglob("*.gba"))
