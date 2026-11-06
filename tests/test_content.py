"""M4 — classificação, ingest com ZIP/multidisco/tradução/vazio/muitos arquivos."""
import zipfile

from dc import content


def test_classify():
    assert content.classify("x.iso", "ps2") == "ps2"
    assert content.classify("Mario (USA).sfc") == "snes"
    assert content.classify("God of War (PS2).iso") == "ps2"
    assert content.classify("jogo.iso") is None          # ambíguo -> pergunta
    assert content.classify("Zelda.nsp") == "switch"
    assert content.classify("x.iso", "dreamcast") is None


def test_translation_detection():
    assert content.is_translation("Donkey Kong Country [BR].sfc")
    assert content.is_translation("Final Fantasy Tactics (BR) (T1.6.4).cue")
    assert not content.is_translation("Donkey Kong Country (USA).sfc")


def test_ingest_zip_and_translation(tmp_path):
    dl = tmp_path / "dl"; dl.mkdir()
    z = dl / "Chrono Trigger [BR].zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("Chrono Trigger [BR].sfc", b"\x01" * 2048)
    it = content.ingest(z, "snes", tmp_path / "roms", tmp_path / "q", tmp_path / "work")
    assert it.status == "added" and it.files[0].endswith(".sfc") and "tradução" in it.note
    assert it.integrity == "unverified"
    assert z.exists()  # download original fica (seeding)


def test_ingest_multidisc_makes_m3u(tmp_path):
    d = tmp_path / "dl" / "Final Fantasy VII"; d.mkdir(parents=True)
    for n in (1, 2, 3):
        (d / f"Final Fantasy VII (Disc {n}).chd").write_bytes(b"x" * 10)
    it = content.ingest(d, "psx", tmp_path / "roms", tmp_path / "q", tmp_path / "work")
    assert it.status == "added" and len(it.files) == 1 and it.files[0].endswith("Final Fantasy VII.m3u")
    m3u = (tmp_path / "roms/psx/Final Fantasy VII/Final Fantasy VII.m3u").read_text()
    assert m3u.splitlines() == [f"Final Fantasy VII (Disc {n}).chd" for n in (1, 2, 3)]


def test_ingest_empty_goes_to_quarantine(tmp_path):
    d = tmp_path / "dl"; d.mkdir()
    f = d / "Vazio.gba"; f.write_bytes(b"")
    it = content.ingest(f, None, tmp_path / "roms", tmp_path / "q", tmp_path / "work")
    assert it.status == "quarantined" and it.integrity == "corrupted"


def test_ingest_many_asks_and_ambiguous_asks(tmp_path):
    d = tmp_path / "dl" / "Pack GBA"; d.mkdir(parents=True)
    for i in range(5):
        (d / f"Jogo {i}.gba").write_bytes(b"x")
    it = content.ingest(d, "gba", tmp_path / "roms", tmp_path / "q", tmp_path / "work")
    assert it.status == "ask_many" and len(it.files) == 5
    assert content.ingest(d, "gba", tmp_path / "roms", tmp_path / "q", tmp_path / "work", confirm_many=True).status == "added"
    iso = tmp_path / "dl" / "coisa.iso"; iso.write_bytes(b"x")
    assert content.ingest(iso, None, tmp_path / "roms", tmp_path / "q", tmp_path / "work").status == "ask_console"


def test_zip_slip_quarantined(tmp_path):
    z = tmp_path / "mal.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("../../evil.gba", b"x")
    it = content.ingest(z, "gba", tmp_path / "roms", tmp_path / "q", tmp_path / "work")
    assert it.status == "quarantined" and not (tmp_path / "evil.gba").exists()


import shutil as _sh
import subprocess as _sp

import pytest as _pt

needs_7z = _pt.mark.skipif(not _sh.which("7z"), reason="7-Zip não instalado (no Deck ele existe)")


@needs_7z
def test_ingest_7z_like_hercules(tmp_path):
    src = tmp_path / "src" / "[SLUS-00529] Hercules"; src.mkdir(parents=True)
    (src / "[SLUS-00529] Hercules.bin").write_bytes(b"\x01" * 4096)
    (src / "[SLUS-00529] Hercules.cue").write_text('FILE "[SLUS-00529] Hercules.bin" BINARY\n')
    arc = tmp_path / "dl" / "[SLUS-00529] Hercules.7z"; arc.parent.mkdir()
    _sp.run(["7z", "a", "-bd", str(arc), str(src)], check=True, capture_output=True)
    it = content.ingest(arc, "psx", tmp_path / "roms", tmp_path / "q", tmp_path / "work")
    assert it.status == "added" and it.files[0].endswith("Hercules.cue")


@needs_7z
def test_7z_slip_never_escapes(tmp_path):
    """Se o 7z guardou '../', a inspeção recusa; se ele mesmo saneou o nome, nada sai da pasta."""
    from dc import safe_extract
    work = tmp_path / "w" / "a" / "b"; work.mkdir(parents=True)
    (tmp_path / "w" / "evil.gba").write_bytes(b"x")
    arc = tmp_path / "mal.7z"
    _sp.run(["7z", "a", "-bd", "-spf2", str(arc), "../../evil.gba"], cwd=work, capture_output=True)
    if not arc.exists():
        _pt.skip("7z não criou o arquivo de teste")
    names = [e["Path"] for e in safe_extract.list_external(arc)]
    out = tmp_path / "x" / "out"
    if any(".." in n.replace("\\", "/").split("/") for n in names):
        with _pt.raises(safe_extract.UnsafeArchive):
            safe_extract.extract_any(arc, out)
    else:
        files = safe_extract.extract_any(arc, out)
        assert all(str(f.resolve()).startswith(str(out.resolve())) for f in files)
    assert not (tmp_path / "x" / "evil.gba").exists()


def test_ps2_mdf_becomes_iso(tmp_path):
    d = tmp_path / "dl" / "Shadow of the Colossus"; d.mkdir(parents=True)
    (d / "Shadow of the Colossus.mdf").write_bytes(b"\x00" * 2048 * 3)
    (d / "Shadow of the Colossus.mds").write_bytes(b"x")
    it = content.ingest(d, "ps2", tmp_path / "roms", tmp_path / "q", tmp_path / "work")
    assert it.status == "added" and it.files[0].endswith("Shadow of the Colossus.iso")
