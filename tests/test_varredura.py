"""Varredura de jogos soltos (instalador): acha, separa por console, não confunde mod/README/BIOS com jogo, desfaz."""
import zipfile
from pathlib import Path

import pytest

from dc import varredura as V


@pytest.fixture
def casa(tmp_path, monkeypatch):
    monkeypatch.setenv("DC_ROOT", str(tmp_path / "dcroot"))
    monkeypatch.setattr(V, "_montagens", list)
    h = tmp_path / "home"
    h.mkdir()
    return h


def _f(h: Path, rel: str, data: bytes = b"x" * 20000) -> Path:
    p = h / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


def _consoles(h):
    unidades, sem = V.encontrar(h, [h])
    return {u.principal.name: u.console for u in unidades}, [s.name for s in sem]


def test_identifica_por_extensao_disco_e_pasta(casa):
    _f(casa, "Downloads/Emerald.gba")
    _f(casa, "Downloads/Zelda [0100000000010000].nsp")
    gc = bytearray(40000); gc[0x1C:0x20] = b"\xc2\x33\x9f\x3d"
    _f(casa, "Desktop/Melee.iso", bytes(gc))
    wii = bytearray(40000); wii[0x18:0x1C] = b"\x5d\x1c\x9e\xa3"
    _f(casa, "Downloads/MK.iso", bytes(wii))
    _f(casa, "Downloads/PS2/qualquer.chd")
    _f(casa, "Downloads/misterio.iso")
    achados, sem = _consoles(casa)
    assert achados == {"Emerald.gba": "gba", "Zelda [0100000000010000].nsp": "switch", "Melee.iso": "gc",
                       "MK.iso": "wii", "qualquer.chd": "ps2"}
    assert sem == ["misterio.iso"]


def test_nao_confunde_readme_mod_bios_e_xex(casa):
    _f(casa, "Downloads/README.md", b"# texto\n" * 3000)
    sonic = bytearray(40000); sonic[0x100:0x110] = b"SEGA MEGA DRIVE "
    _f(casa, "Downloads/Sonic.md", bytes(sonic))
    with zipfile.ZipFile(casa / "Downloads/Mod.zip", "w") as z:
        z.writestr("README.md", "x"); z.writestr("plugin.esp", "x" * 20000)
    with zipfile.ZipFile(casa / "Downloads/ps2-bios.zip", "w") as z:
        z.writestr("SCPH-39001.bin", "x" * 20000)
    with zipfile.ZipFile(casa / "Downloads/Golden Sun.zip", "w") as z:
        z.writestr("Golden Sun.gba", "g" * 20000)
    _f(casa, "trabalho/default.xex")
    _f(casa, "retrodeck/roms/gba/de-outro-programa.gba")
    achados, sem = _consoles(casa)
    assert achados == {"Sonic.md": "genesis", "Golden Sun.zip": "gba"}
    assert sem == []


def test_cue_bin_e_multidisco_andam_juntos_e_desfaz(casa):
    _f(casa, "Downloads/MGS/cd1.bin"); _f(casa, "Downloads/MGS/cd2.bin")
    (casa / "Downloads/MGS/cd1.cue").write_text('FILE "cd1.bin" BINARY\n')
    (casa / "Downloads/MGS/cd2.cue").write_text('FILE "cd2.bin" BINARY\n')
    (casa / "Downloads/MGS/Metal Gear Solid (PS1).m3u").write_text("cd1.cue\ncd2.cue\n")
    _f(casa, "Downloads/Emerald.gba")
    _f(casa, "Emulation/roms/gba/Ja tenho/Emerald.gba")  # repetido: não move
    unidades, _ = V.encontrar(casa, [casa])
    V.aplicar(unidades, casa, log=lambda *a: None)
    mgs = casa / "Emulation/roms/psx/Metal Gear Solid (PS1)"
    assert sorted(p.name for p in mgs.iterdir()) == ["Metal Gear Solid (PS1).m3u", "cd1.bin", "cd1.cue", "cd2.bin", "cd2.cue"]
    assert (casa / "Downloads/Emerald.gba").exists()
    V.desfazer(log=lambda *a: None)
    assert (casa / "Downloads/MGS/cd2.bin").exists() and not mgs.exists()
