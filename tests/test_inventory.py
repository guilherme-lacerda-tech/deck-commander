"""M-1 — inventário: sem efeito colateral, procedência sem chute, avisos sem falhar."""
import hashlib

from dc import inventory, vdf
from dc.paths import get_paths
from dc.store import Store


def tree_hash(root):
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(root)).encode()); h.update(p.read_bytes())
    return h.hexdigest()


def make_home(tmp_path):
    home = tmp_path / "home"
    (home / "Emulation/roms/psx").mkdir(parents=True)
    (home / "Emulation/roms/psx/Game A.chd").write_bytes(b"a")
    (home / "Emulation/roms/psx/Game B.chd").write_bytes(b"b")
    (home / "Emulation/roms/psx/readme.txt").write_text("x")
    (home / "Emulation/bios").mkdir()
    (home / "Emulation/bios/scph5501.bin").write_bytes(b"x")
    sc = home / ".steam/steam/userdata/1/config"; sc.mkdir(parents=True)
    (sc / "shortcuts.vdf").write_bytes(vdf.dump_binary({"shortcuts": {
        "0": {"appid": 1, "AppName": "X", "exe": '"/x/unifideck-launcher"'}}}))
    return home


def test_inventory_no_side_effects_and_provenance(tmp_path):
    home = make_home(tmp_path)
    paths = get_paths(tmp_path / "dc").ensure()
    s = Store(paths.db)
    with s.tx() as c:
        c.execute("INSERT INTO files(path,size,mtime,origin,origin_ref) VALUES(?,?,?,?,?)",
                  (str(home / "Emulation/roms/psx/Game A.chd"), 1, 0, "torrent", "op123"))
    s.close()
    before_home, before_db = tree_hash(home), paths.db.read_bytes()
    j, m, inv = inventory.run(home, paths)
    assert tree_hash(home) == before_home and paths.db.read_bytes() == before_db
    roms = {r["path"].rsplit("/", 1)[-1].rsplit("\\", 1)[-1]: r for r in inv["roms"]}
    assert set(roms) == {"Game A.chd", "Game B.chd"}
    assert roms["Game A.chd"]["origin"] == "torrent" and roms["Game A.chd"]["origin_ref"] == "op123"
    assert roms["Game B.chd"]["origin"] == "unknown" and "não rastreável" in roms["Game B.chd"]["note"]
    assert inv["bios"]["required_ok"] == {"ps1": True, "ps2": False}
    assert any("PS2" in w for w in inv["warnings"])
    assert inv["steam"][0]["by_launcher"] == {"unifideck-launcher": 1}
    assert j.exists() and "Inventário" in m.read_text("utf-8")


def test_missing_decky_and_emudeck_warn_without_failing(tmp_path):
    home = tmp_path / "vazio"; home.mkdir()
    inv = inventory.collect(home, get_paths(tmp_path / "dc"))
    w = " ".join(inv["warnings"])
    assert "Decky" in w and "EmuDeck" in w and inv["roms"] == []
