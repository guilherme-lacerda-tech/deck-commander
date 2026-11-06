"""M4 bot (pareamento, whitelist, rate limit, comandos) · M20 regras · M17 export sem segredos · M6 conflito."""
import json
import zipfile

import pytest

from dc import backup, bot, export, health
from dc.paths import get_paths


class FakeQbt:
    def __init__(self):
        self.added, self.paused = [], []

    def add(self, magnet, cat, path):
        if not magnet.startswith("magnet:?"):
            from dc.qbt import QbtError
            raise QbtError("link inválido")
        self.added.append((magnet, cat, path))

    def torrents(self, *a, **k):
        return [{"hash": "h1", "name": "Jogo", "progress": 0.5, "state": "downloading"}]

    def pause(self, hs):
        self.paused += hs

    def resume(self, hs):
        pass

    def version(self):
        return "v5.1.4"


@pytest.fixture
def b(tmp_path, monkeypatch):
    paths = get_paths(tmp_path).ensure()
    monkeypatch.setattr(bot.ops, "game_running", lambda: False)
    monkeypatch.setattr(bot.ops, "unit_dir", lambda: tmp_path / "units")   # nunca mexe nos serviços reais
    monkeypatch.setattr(bot.ops, "_systemctl", lambda *a: None)
    x = bot.Bot(paths, "TOKEN123")
    x.qbt = FakeQbt()
    return x


def test_pairing_and_whitelist(b):
    assert "negado" in b.handle(1, 1, "/status")
    code = bot.pair_code(b.paths)
    assert "negado" in b.handle(1, 1, "/start 000000" if code != "000000" else "/start 111111")
    assert "Pareado" in b.handle(1, 1, f"/start {code}")
    assert "negado" in b.handle(2, 2, f"/start {code}")  # código é de uso único
    assert json.loads(b.cfg_path.read_text())["allowed"] == [1]


def test_commands_and_rate_limit(b):
    b.cfg["allowed"] = [1]
    assert "Adicionado (ps2)" in b.handle(1, 1, "/add ps2 magnet:?xt=urn:btih:abc")
    assert b.qbt.added[0][1] == "ps2"
    assert "inválido" in b.handle(1, 1, "/add ps2 http://x")
    assert "Jogo" in b.handle(1, 1, "/queue")
    assert "pausado" in b.handle(1, 1, "/pause") and b.qbt.paused == ["h1"]
    assert "Safe-mode ATIVADO" in b.handle(1, 1, "/sos")
    assert "Safe-mode ativo" in b.handle(1, 1, "/add magnet:?xt=1")
    for _ in range(25):
        last = b.handle(1, 1, "/help")
    assert "Calma" in last
    log = (b.paths.logs / "bot.log").read_text()
    assert "TOKEN123" not in log and "magnet:?xt" not in log


def test_resource_rules_never_assume_unknown():
    S = health.Sensor
    base = {"jogo": S("jogo", "ok", 0.0), "carregador": S("carregador", "indisponivel", None),
            "bateria": S("bateria", "indisponivel", None)}
    ok, why = health.can_run("backup_heavy", base)
    assert not ok and "desconhecido" in why
    base["bateria"] = S("bateria", "ok", 25.0); base["carregador"] = S("carregador", "ok", 0.0)
    assert not health.can_run("backup_heavy", base)[0]          # 25% < 30%
    assert health.can_run("extract_big", base)[0]               # 25% >= 20%
    base["jogo"] = S("jogo", "ok", 1.0)
    assert not health.can_run("benchmark", base)[0]
    base["carregador"] = S("carregador", "ok", 1.0)
    assert health.can_run("nonessential", base)[0]


def test_export_has_no_secrets_and_no_home(tmp_path):
    paths = get_paths(tmp_path / "r").ensure()
    home = tmp_path / "home"
    (paths.secrets / "telegram").write_text("SEGREDO")
    (paths.config / "telegram.json").write_text('{"allowed":[123456789]}')
    (paths.config / "emulators.json").write_text(json.dumps({"psx": [str(home / "Applications/x")]}))
    out = tmp_path / "e.zip"
    names = export.export_config(paths, out, home=home)
    z = zipfile.ZipFile(out)
    blob = b"".join(z.read(n) for n in z.namelist())
    assert b"SEGREDO" not in blob and b"123456789" not in blob and str(home).encode() not in blob
    assert "config/emulators.json" in names
    assert export.import_config(paths, out, home=home)[0].startswith("(dry-run)")


def test_save_import_never_overwrites_conflict(tmp_path):
    src = tmp_path / "saves"; src.mkdir(); (src / "slot1.mcd").write_bytes(b"VELHO")
    res = backup.create_snapshot({"duck": src}, tmp_path / "bk", tmp_path / "q", kind="saves")
    (src / "slot1.mcd").write_bytes(b"NOVO-PROGRESSO")
    (src / "slot2.mcd").unlink(missing_ok=True)
    rep = health.import_saves(res.path, dry_run=False)
    assert (src / "slot1.mcd").read_bytes() == b"NOVO-PROGRESSO"  # nunca sobrescreve
    assert len(rep["conflitos"]) == 1 and list(src.glob("slot1.mcd.conflito-*"))


def test_parse_console_aliases():
    from dc.bot import parse_console
    assert parse_console("Switch 1") == "switch" and parse_console("switch") == "switch"
    assert parse_console("Switch 2") == "switch2"
    assert parse_console("PS2") == "ps2" and parse_console("PlayStation 2") == "ps2"
    assert parse_console("ps1") == "psx" and parse_console("Super Nintendo") == "snes"
    assert parse_console("bom dia") is None


def test_forwarded_torrent_after_console_text(b, monkeypatch):
    b.cfg["allowed"] = [1]
    got = {}
    b.qbt.add_file = lambda data, name, cat, path: got.update(data=data, name=name, cat=cat)
    b.call = lambda method, **p: {"file_path": "documents/x.torrent"}

    class R:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b"d8:announce..."
    monkeypatch.setattr(bot.urllib.request, "urlopen", R)
    msg = lambda **k: {"from": {"id": 1}, "chat": {"id": 9}, **k}
    assert "próximo" in b.handle_message(msg(text="Switch 1"))
    r = b.handle_message(msg(document={"file_id": "F", "file_name": "Castlevania - Belmonts Curse.torrent"}))
    assert "Baixando Castlevania - Belmonts Curse (Switch)" in r and got["cat"] == "switch"
    assert b.cfg["pending_console"] == {}  # usado uma vez
    r = b.handle_message(msg(document={"file_id": "F", "file_name": "Jogo.torrent"}, caption="ps2"))
    assert got["cat"] == "ps2"
    assert "não é suportado" in b.handle_message(msg(document={"file_id": "F", "file_name": "DK.torrent"}, caption="switch 2"))
    assert "só sei usar" in b.handle_message(msg(document={"file_id": "F", "file_name": "foto.jpg"}))
    assert b.handle_message(msg(text="valeu")) is None
    assert "negado" in b.handle_message({"from": {"id": 7}, "chat": {"id": 7}, "text": "ps2"})
    assert "TOKEN123" not in (b.paths.logs / "bot.log").read_text()


def test_finished_download_auto_syncs_once(b, monkeypatch):
    b.cfg["notify_chat"] = 9
    sent, syncs = [], []
    b.send = lambda chat, text: sent.append(text)
    monkeypatch.setattr(bot.syncer, "run_sync", lambda *a, **k: syncs.append(1) or "1 jogo(s) novo(s) no Steam")
    b.qbt.torrents = lambda *a, **k: [{"hash": "h", "name": "Castlevania", "state": "stalledUP"},
                                      {"hash": "i", "name": "Outro", "state": "downloading"}]
    b.notify_finished(); b.notify_finished()
    assert len(sent) == 1 and "Castlevania" in sent[0] and "Outro" not in sent[0] and syncs == [1]


def test_finished_download_waits_for_game(b, monkeypatch):
    b.cfg["notify_chat"] = 9
    sent, syncs = [], []
    b.send = lambda chat, text: sent.append(text)
    monkeypatch.setattr(bot.syncer, "run_sync", lambda *a, **k: syncs.append(1) or "ok")
    b.qbt.torrents = lambda *a, **k: [{"hash": "h", "name": "Castlevania", "state": "stalledUP"}]
    monkeypatch.setattr(bot.ops, "game_running", lambda: True)
    b.notify_finished(); b.notify_finished()
    assert len(sent) == 1 and "fechar o jogo" in sent[0] and syncs == []
    monkeypatch.setattr(bot.ops, "game_running", lambda: False)
    b.notify_finished()
    assert syncs == [1] and len(sent) == 2


def test_stuck_download_retried_hourly_and_silent_when_nothing_added(b, monkeypatch):
    b.cfg["notify_chat"] = 9
    b.cfg["notified"] = ["h"]
    sent, syncs = [], []
    b.send = lambda chat, text: sent.append(text)
    monkeypatch.setattr(bot.syncer, "run_sync", lambda *a, **k: syncs.append(1) or "0 jogo(s) novo(s) no Steam")
    b.qbt.torrents = lambda *a, **k: [{"hash": "h", "name": "Hercules", "state": "stalledUP"}]
    b.notify_finished(); b.notify_finished()
    assert syncs == [1] and sent == []          # 1 tentativa por hora, sem mensagem se nada entrou
    b.cfg["last_retry"] = 0
    monkeypatch.setattr(bot.syncer, "run_sync", lambda *a, **k: "1 jogo(s) novo(s) no Steam: Hercules")
    b.notify_finished()
    assert "Hercules" in sent[0]
