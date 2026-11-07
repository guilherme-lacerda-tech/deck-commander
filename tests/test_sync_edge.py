"""/sync: cópia confirmada com /baixar entra; terceira cópia com o mesmo nome nunca se mistura com pasta existente."""
import json

from dc import content
from dc.paths import get_paths
from dc.store import Store


class Q:
    def __init__(self, ts):
        self.ts = ts

    def torrents(self, *a, **k):
        return self.ts


def _env(tmp_path, monkeypatch):
    from dc import syncer
    paths = get_paths(tmp_path / "dc").ensure()
    roms = tmp_path / "roms"
    (paths.config / "deck.json").write_text(json.dumps({"roms_root": str(roms)}))
    monkeypatch.setattr(syncer.ops, "game_running", lambda: False)
    monkeypatch.setattr(syncer, "rom_roots", lambda: [roms])
    monkeypatch.setattr(syncer, "add_to_steam", lambda *a: [])
    old = roms / "ps2/Okami/Okami.iso"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"a" * 2048)
    (paths.data / "launch-map.json").write_text(json.dumps({"ps2-okami": {"title": "Okami", "console": "ps2", "rom": str(old)}}))
    return syncer, paths, roms


def test_baixar_confirmed_copy_is_accepted(tmp_path, monkeypatch):
    syncer, paths, roms = _env(tmp_path, monkeypatch)
    dl = tmp_path / "dl/Okami (Dublado)"
    dl.mkdir(parents=True)
    (dl / "Okami (Dublado).iso").write_bytes(b"b" * 2048)
    t = {"hash": "H", "name": "Okami (Dublado)", "state": "uploading", "content_path": str(dl), "category": "ps2",
         "tags": "deck-commander, dc-dup-ok"}
    out = syncer.run_sync(paths, Store(paths.db), Q([t]))
    assert "já tem" not in out and (roms / "ps2/Okami (Dublado)/Okami (Dublado).iso").exists()


def test_removed_in_steam_hidden_from_dups_and_devolver_brings_back(tmp_path, monkeypatch):
    from dc import bot, dedup, remove
    syncer, paths, roms = _env(tmp_path, monkeypatch)
    lm = json.loads((paths.data / "launch-map.json").read_text())
    dub = roms / "ps2/Okami (USA)/Okami (USA).iso"
    dub.parent.mkdir(parents=True)
    dub.write_bytes(b"d")
    lm["ps2-okami-usa"] = {"title": "Okami (USA)", "console": "ps2", "rom": str(dub)}
    (paths.data / "launch-map.json").write_text(json.dumps(lm))
    assert dedup.library_dups(remove.effective_map(paths))  # duplicata enquanto os dois estão no Steam
    # você apagou o atalho pelo Steam: o plugin anota "removed"
    (paths.data / "plugin-done.json").write_text(json.dumps({"ps2-okami-usa": {"appid": 0, "error": "", "removed": True}}))
    assert dedup.library_dups(remove.effective_map(paths)) == []
    b = bot.Bot(paths, "T")
    b.cfg["allowed"] = [1]
    b.qbt = Q([])
    assert "Okami (USA)" in b.handle(1, 1, "/devolver")
    assert "Achei mais de um" not in b.handle(1, 1, "/devolver okami usa")
    assert "ps2-okami-usa" not in json.loads((paths.data / "plugin-done.json").read_text())
    assert "Nenhum jogo removido" in b.handle(1, 1, "/devolver")


def test_third_copy_never_nests_into_existing_folder(tmp_path):
    roms = tmp_path / "roms"
    for d in ("Rez", "Rez (novo)"):
        (roms / "ps2" / d).mkdir(parents=True)
        (roms / "ps2" / d / "keep.txt").write_text("x")
    src = tmp_path / "dl/Rez"
    src.mkdir(parents=True)
    (src / "Rez.iso").write_bytes(b"c" * 2048)
    it = content.ingest(src, "ps2", roms, tmp_path / "q", tmp_path / "w")
    assert it.status == "added" and it.files == [str(roms / "ps2/Rez (novo 2)/Rez.iso")]
    assert sorted(p.name for p in (roms / "ps2/Rez (novo)").iterdir()) == ["keep.txt"]
