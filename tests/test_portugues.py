"""Aba "Em português", idioma por jogo (PT-BR oficial do Switch) e AES do leitor de NCA."""
import json

from dc import quality, tabs
from dc.paths import get_paths
from dc.traducao import nca, portugues


def test_pt_names_from_real_library():
    yes = ["Ben 10 - Protector of Earth (BR-USA) (DUB)", "Black (BR) (DUB IA)", "God of War 1 (Dublado)",
           "God of War 2 VERSÃO I.A", "Shadow of the Colossus (Dub-e-Leg)", "Final Fantasy Tactics (BR)",
           "Pokemon Fire Red (PT-BR)"]
    no = ["Shadow of the Colossus", "Hercules", "Super Mario Galaxy", "Brave Fencer", "Brotherhood", "Dubai Racer"]
    assert all(portugues.is_pt_name(t) for t in yes)
    assert not any(portugues.is_pt_name(t) for t in no)
    assert portugues.is_pt_name("Jogo", "/r/Jogo (www.romsportugues.com).iso")


def test_switch_official_ptbr_language_per_launch(tmp_path, monkeypatch):
    paths = get_paths(tmp_path / "dc").ensure()
    cfg = tmp_path / "Config.json"
    original = '{\n  "res_scale": 1,\n  "system_language": "AmericanEnglish",\n  "x": "y"\n}'
    cfg.write_text(original)
    monkeypatch.setitem(quality.TARGETS, "switch", ("json", [cfg], None, "res_scale"))
    monkeypatch.setitem(quality.LANG_TARGET, "switch", ("json", [cfg], None, "system_language"))
    quality.set_language(paths, "switch-galaxy", "BrazilianPortuguese", "oficial")
    quality.set_override(paths, "switch-galaxy", "switch", "2x")
    rec = quality.apply_for_launch(paths, "switch-galaxy", "switch")
    now = json.loads(cfg.read_text())
    assert now["system_language"] == "BrazilianPortuguese" and now["res_scale"] == 2 and len(rec["records"]) == 2
    assert quality.apply_for_launch(paths, "switch-outro", "switch") is None  # outro jogo: nada muda
    quality.restore(paths)
    assert cfg.read_text() == original  # byte a byte
    assert "padrão" in quality.set_override(paths, "switch-galaxy", "switch", "padrão")
    assert quality.get_language(paths, "switch-galaxy") == "BrazilianPortuguese"  # idioma continua


def test_pt_tab_and_collection(tmp_path, monkeypatch):
    lm = {"ps2-gow": {"title": "God of War 1 (Dublado)", "console": "ps2", "rom": "/r/gow.iso"},
          "ps2-sotc": {"title": "Shadow of the Colossus", "console": "ps2", "rom": "/r/sotc.iso"},
          "switch-gal": {"title": "Super Mario Galaxy", "console": "switch", "rom": "/r/Galaxy [010099C022B96000].nsp"}}
    (tmp_path / "traducao").mkdir()
    (tmp_path / "traducao/idiomas.json").write_text(json.dumps({"switch-gal": {"ptbr": "oficial"}}))
    sc = [{"appid": 1, "exe": '"/x/dc-launch"', "LaunchOptions": "ps2-gow"},
          {"appid": 2, "exe": '"/x/dc-launch"', "LaunchOptions": "ps2-sotc"},
          {"appid": 3, "exe": '"/x/dc-launch"', "LaunchOptions": "switch-gal"}]
    monkeypatch.setattr(portugues, "has_dc_mod", lambda rom: False)
    spec = tabs.write_collections(tmp_path, sc, lm)
    assert spec["Em português"] == [1, 3] and spec["__exato__"] == ["Em português"]
    t = tabs.build({}, sc, lm)
    assert t["dc-portugues"]["title"] == "Em português"


def test_aes_fips197_and_ctr_roundtrip():
    a = nca.AES(bytes(range(16)))
    ct = a.encrypt(bytes.fromhex("00112233445566778899aabbccddeeff"))
    assert ct.hex() == "69c4e0d86a7b0430d8cdb78070b4c55a"
    assert a.decrypt(ct).hex() == "00112233445566778899aabbccddeeff"
    data = bytes(range(256)) * 3
    enc = a.ctr(data, b"\x01" * 8, 0x40)
    assert enc != data and a.ctr(enc, b"\x01" * 8, 0x40) == data
