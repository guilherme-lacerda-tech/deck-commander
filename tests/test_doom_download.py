import hashlib
import zipfile

import pytest

from dc import catalogo_downloads as catalog
from dc import content, emulators, setup
from dc.paths import get_paths


def test_doom_catalog_and_wii_wad_ambiguity(tmp_path):
    item = catalog.pesquisar(get_paths(tmp_path).ensure(), "Doom")[0]
    assert item["console"] == "doom"
    assert item["archive_member"] == "Doom/doom1.wad"
    assert content.classify("ambiguous.wad") is None
    assert content.classify("doom1.wad", "doom") == "doom"
    assert content.classify("Wii game.wad") == "wii"
    assert "prboom_libretro.so" in emulators.RA_CORE_FILES


def test_zip_extracts_only_pinned_member(tmp_path):
    game = b"IWAD" + bytes(100)
    source = tmp_path / "game.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("Doom/doom1.wad", game)
        archive.writestr("../../outside", b"ignored")
    item = {"filename": "doom1.wad", "archive_member": "Doom/doom1.wad",
            "file_size": len(game), "file_sha256": hashlib.sha256(game).hexdigest(),
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
    output = catalog._payload(source, item)
    assert output.read_bytes() == game
    assert set(tmp_path.iterdir()) == {source, output}
    assert catalog._payload(source, item) == output


def test_zip_bad_member_hash_never_publishes(tmp_path):
    source = tmp_path / "game.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("doom1.wad", b"IWAD")
    item = {"filename": "doom1.wad", "archive_member": "doom1.wad",
            "file_size": 4, "file_sha256": "0" * 64, "sha256": "1" * 64}
    with pytest.raises(ValueError):
        catalog._payload(source, item)
    assert list(tmp_path.iterdir()) == [source]


def test_doom_data_uses_existing_emudeck_system_directory(tmp_path, monkeypatch):
    bios = tmp_path / "Emulation/bios"
    bios.mkdir(parents=True)
    ra = tmp_path / "retroarch"
    ra.mkdir()
    config = ra / "retroarch.cfg"
    config.write_text(f'system_directory = "{bios.as_posix()}"\n')
    original = config.read_bytes()
    monkeypatch.setattr(emulators, "RA_DIR", ra)
    calls = []

    def download(url, path, sha):
        calls.append((url, path, sha))
        path.write_bytes(b"prboom-data")

    monkeypatch.setattr(setup, "download", download)
    setup.install_doom_data([])
    setup.install_doom_data([])
    assert len(calls) == 1
    assert calls[0][1] == bios / "prboom.wad"
    assert len(calls[0][2]) == 64
    assert config.read_bytes() == original
