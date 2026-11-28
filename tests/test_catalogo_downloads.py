import hashlib
import io
import json
from pathlib import Path

import pytest

from dc import catalogo_downloads as catalog
from dc import ops, syncer
from dc.paths import get_paths
from dc.store import Store


@pytest.fixture
def context(tmp_path, monkeypatch):
    monkeypatch.setenv("DC_ROOT", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    paths = get_paths().ensure()
    (paths.config / "deck.json").write_text(json.dumps({"roms_root": str(tmp_path / "roms")}))
    store = Store(paths.db)
    monkeypatch.setattr(catalog, "iniciar", lambda p: None)
    monkeypatch.setattr(ops, "game_running", lambda: False)
    payload = b"NES\x1a" + bytes(12) + b"game-data"
    item = {"id": "example-nes", "titulo": "Example", "filename": "Example.nes", "console": "nes",
            "url": "https://games.example/Example.nes", "sha256": hashlib.sha256(payload).hexdigest(),
            "size": len(payload), "license": "CC0-1.0", "source_url": "https://games.example/license"}

    def response(*args, **kwargs):
        result = io.BytesIO(payload)
        result.geturl = lambda: item["url"]
        return result

    monkeypatch.setattr(catalog.urllib.request, "urlopen", response)
    yield paths, store, item
    store.close()


def test_exact_name_and_platform(context):
    paths, _, item = context
    (paths.config / "download-catalog.json").write_text(json.dumps({"version": 1, "games": [item]}))
    assert catalog.pesquisar(paths, "example", "nes") == [item]
    assert catalog.pesquisar(paths, "Example 2", "nes") == []
    assert catalog.pesquisar(paths, "Example", "snes") == []
    assert catalog.pesquisar(paths, "Super Tilt Bro.", "nes")[0]["size"] == 40976


def test_schedule_survives_reopen_and_deduplicates(context):
    paths, store, item = context
    op_id = catalog.agendar(paths, store, item)
    other = Store(paths.db)
    try:
        assert catalog.agendar(paths, other, item) == op_id
        assert other.get(op_id).params["item"] == item
        assert len(other.list()) == 1
    finally:
        other.close()


def test_bad_checksum_never_installs(context):
    paths, store, item = context
    item["sha256"] = "0" * 64
    op_id = catalog.agendar(paths, store, item)
    catalog.run_pending(paths, store)
    assert store.get(op_id).state == "failed"
    assert not list(paths.data.rglob("*.nes"))
    assert not (paths.config.parent.parent / "roms").exists()


def test_no_steam_keeps_installed_file_and_retry_reuses_it(context, monkeypatch):
    paths, store, item = context

    def no_steam():
        raise FileNotFoundError("sem usuário Steam")

    monkeypatch.setattr(syncer, "shortcuts_path", no_steam)
    op_id = catalog.agendar(paths, store, item)
    catalog.run_pending(paths, store)
    first = store.get(op_id)
    result = json.loads(first.result)
    target = Path(result["files"][0])
    assert first.state == "pending"
    assert result["phase"] == "waiting_steam"
    assert hashlib.sha256(target.read_bytes()).hexdigest() == item["sha256"]
    assert len(json.loads((paths.data / "launch-map.json").read_text())) == 1
    monkeypatch.setattr(catalog.urllib.request, "urlopen", lambda *a, **k: pytest.fail("baixou novamente"))
    store.conn.execute("UPDATE operations SET finished_at=NULL WHERE id=?", (op_id,))
    catalog.run_pending(paths, store)
    assert json.loads(store.get(op_id).result)["files"] == result["files"]
    assert len(list(target.parent.parent.rglob("*.nes"))) == 1


def test_network_failure_retries_then_fails_without_blocking_another(context, monkeypatch):
    paths, store, item = context

    def offline(*args, **kwargs):
        raise TimeoutError("endpoint private-token")

    monkeypatch.setattr(catalog.urllib.request, "urlopen", offline)
    op_id = catalog.agendar(paths, store, item)
    for _ in range(3):
        catalog.run_pending(paths, store)
        store.conn.execute("UPDATE operations SET finished_at=NULL WHERE id=?", (op_id,))
    result = store.get(op_id)
    assert result.state == "failed"
    assert result.attempts == 3
    assert "private-token" not in result.error
    assert "private-token" not in (paths.logs / "operations.log").read_text()


def test_existing_different_file_is_preserved(context):
    paths, store, item = context
    target = paths.config.parent.parent / "roms/nes/Example/Example.nes"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"user version")
    op_id = catalog.agendar(paths, store, item)
    catalog.run_pending(paths, store)
    assert store.get(op_id).state == "failed"
    assert target.read_bytes() == b"user version"


def test_game_running_defers_steam_publication(context, monkeypatch):
    paths, store, item = context
    monkeypatch.setattr(ops, "game_running", lambda: True)
    monkeypatch.setattr(syncer, "add_to_steam", lambda *a: pytest.fail("publicou com jogo aberto"))
    op_id = catalog.agendar(paths, store, item)
    catalog.run_pending(paths, store)
    op = store.get(op_id)
    assert op.state == "pending"
    assert json.loads(op.result)["phase"] == "waiting_game"


def test_invalid_destination_rejected_before_enqueue(context):
    paths, store, item = context
    item["filename"] = "../../other.nes"
    with pytest.raises(ValueError):
        catalog.agendar(paths, store, item)
    assert store.list() == []


@pytest.mark.parametrize("range_supported", [True, False])
def test_resume_or_restart_when_server_ignores_range(context, monkeypatch, range_supported):
    paths, _, item = context
    payload = catalog.urllib.request.urlopen(None).read()
    directory = paths.data / "catalog-downloads" / item["sha256"]
    directory.mkdir(parents=True)
    partial = directory / (item["filename"] + ".part")
    partial.write_bytes(payload[:8])

    def response(request, **kwargs):
        assert request.get_header("Range") == "bytes=8-"
        result = io.BytesIO(payload[8:] if range_supported else payload)
        result.status = 206 if range_supported else 200
        result.headers = {"Content-Range": f"bytes 8-{len(payload) - 1}/{len(payload)}"}
        result.geturl = lambda: item["url"]
        return result

    monkeypatch.setattr(catalog.urllib.request, "urlopen", response)
    target = catalog._download(paths, item)
    assert target.read_bytes() == payload
    assert not partial.exists()


def test_connection_drop_keeps_received_bytes_for_next_attempt(context, monkeypatch):
    paths, _, item = context
    payload = catalog.urllib.request.urlopen(None).read()

    class Disconnect(io.BytesIO):
        status = 200
        headers = {}

        def geturl(self):
            return item["url"]

        def read(self, size=-1):
            if self.tell():
                raise ConnectionResetError("rede caiu")
            return super().read(8)

    monkeypatch.setattr(catalog.urllib.request, "urlopen", lambda *a, **k: Disconnect(payload))
    with pytest.raises(ConnectionResetError):
        catalog._download(paths, item)
    partial = paths.data / "catalog-downloads" / item["sha256"] / (item["filename"] + ".part")
    assert partial.read_bytes() == payload[:8]
    assert not partial.with_suffix("").exists()


def test_wrong_content_range_is_rejected(context, monkeypatch):
    paths, _, item = context
    payload = catalog.urllib.request.urlopen(None).read()
    directory = paths.data / "catalog-downloads" / item["sha256"]
    directory.mkdir(parents=True)
    partial = directory / (item["filename"] + ".part")
    partial.write_bytes(payload[:8])

    def response(*args, **kwargs):
        result = io.BytesIO(payload[8:])
        result.status = 206
        result.headers = {"Content-Range": f"bytes 0-{len(payload) - 1}/{len(payload)}"}
        result.geturl = lambda: item["url"]
        return result

    monkeypatch.setattr(catalog.urllib.request, "urlopen", response)
    with pytest.raises(ValueError, match="intervalo"):
        catalog._download(paths, item)
    assert not list(directory.iterdir())


def test_completed_partial_after_crash_is_published_without_network(context, monkeypatch):
    paths, _, item = context
    payload = catalog.urllib.request.urlopen(None).read()
    directory = paths.data / "catalog-downloads" / item["sha256"]
    directory.mkdir(parents=True)
    (directory / (item["filename"] + ".part")).write_bytes(payload)
    monkeypatch.setattr(catalog.urllib.request, "urlopen", lambda *a, **k: pytest.fail("redownload"))
    assert catalog._download(paths, item).read_bytes() == payload


def test_short_response_is_retryable_and_preserved(context, monkeypatch):
    paths, store, item = context
    payload = catalog.urllib.request.urlopen(None).read()

    def response(*args, **kwargs):
        result = io.BytesIO(payload[:8])
        result.geturl = lambda: item["url"]
        return result

    monkeypatch.setattr(catalog.urllib.request, "urlopen", response)
    operation = catalog.agendar(paths, store, item)
    catalog.run_pending(paths, store)
    assert store.get(operation).state == "pending"
    assert json.loads(store.get(operation).result)["phase"] == "retry"
    partial = paths.data / "catalog-downloads" / item["sha256"] / (item["filename"] + ".part")
    assert partial.read_bytes() == payload[:8]
