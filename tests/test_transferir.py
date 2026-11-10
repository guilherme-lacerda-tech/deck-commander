"""Transferência Deck -> PC: manifesto (categorias, destinos, saves, hash/cache) sem rede."""
import hashlib
import json
import os
import struct
from pathlib import Path

import pytest

from dc import transferir as T

TID = "040074A01BF12000"
UUID = "75C5F741961DE77744A52A398EE8F58A"


def _w(p: Path, data=b"x") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data if isinstance(data, bytes) else data.encode())
    return p


def _npdm(tid: str) -> bytes:
    b = bytearray(0x200)
    b[:4] = b"META"
    struct.pack_into("<I", b, 0x70, 0x100)
    b[0x100:0x104] = b"ACI0"
    struct.pack_into("<Q", b, 0x110, int(tid, 16))
    return bytes(b)


def _imkvdb(entradas) -> bytes:
    out = bytearray(b"IMKV" + struct.pack("<II", 0, len(entradas)))
    for pid, said, tipo in entradas:
        k = bytearray(0x40)
        struct.pack_into("<Q", k, 0, pid)
        k[8] = 1
        k[0x20] = tipo
        v = bytearray(0x40)
        struct.pack_into("<Q", v, 0, said)
        out += b"IMEN" + struct.pack("<II", 0x40, 0x40) + k + v
    return bytes(out)


def _por_cat(man):
    d = {}
    for a in man["arquivos"]:
        d.setdefault(a["categoria"], []).append(a)
    return d


def _destinos(man):
    return {a["destino"]: a for a in man["arquivos"]}


# ------------------------------------------------------------------ formatos ------------
def test_le_imkvdb_e_acha_save_do_titulo(tmp_path):
    arc = _w(tmp_path / "bis/system/save/8000000000000000/0/imkvdb.arc",
             _imkvdb([(0x0100DCA0064A6000, 3, 1), (0x0100F43008C44000, 4, 1), (0x0100F43008C44000, 5, 2)]))
    todas = T.ler_imkvdb(arc)
    assert [e["save_data_id"] for e in todas] == ["0000000000000003", "0000000000000004", "0000000000000005"]
    assert todas[0]["user_id"].startswith("01") and todas[2]["tipo"] == 2
    assert [e["save_data_id"] for e in T.ryujinx_saves(tmp_path, "0100f43008c44000")] == ["0000000000000004",
                                                                                         "0000000000000005"]
    assert T.ler_imkvdb(_w(tmp_path / "lixo.arc", b"nada")) == []


def test_title_id_do_npdm(tmp_path):
    assert T._tid_npdm(_w(tmp_path / "main.npdm", _npdm(TID))) == TID
    assert T._tid_npdm(_w(tmp_path / "ruim.npdm", b"XXXX" * 100)) is None


def test_serial_pelo_nome_e_pelo_system_cnf(tmp_path):
    assert T.serial_disco(Path("/r/[SLUS-00529] Hercules.cue"), []) == "SLUS-00529"
    iso = _w(tmp_path / "jogo.iso", b"\0" * 5000 + b"BOOT2 = cdrom0:\\SLES_524.12;1\r\n")
    assert T.serial_disco(tmp_path / "jogo.iso", [iso]) == "SLES-52412"


def test_refs_de_cue_e_m3u(tmp_path):
    _w(tmp_path / "a (Track 1).bin"), _w(tmp_path / "a (Track 2).bin")
    cue = _w(tmp_path / "a.cue", 'FILE "a (Track 1).bin" BINARY\n  TRACK 01\nFILE "a (Track 2).bin" BINARY\n')
    m3u = _w(tmp_path / "a.m3u", "a.cue\n#comentario\n")
    assert {p.name for p in T._refs_disco(cue)} == {"a (Track 1).bin", "a (Track 2).bin"}
    assert {p.name for p in T._refs_disco(m3u)} == {"a.cue", "a (Track 1).bin", "a (Track 2).bin"}


# ------------------------------------------------------------------ Switch 2 / Lichii --
@pytest.fixture
def deck_switch2(tmp_path):
    h = tmp_path
    g = h / "Emulation/roms/switch2/Donkey Kong Bananza"
    _w(g / "base/exefs/main", b"main")
    _w(g / "base/exefs/main.npdm", _npdm(TID))
    _w(g / "base/romfs/Level.alsarc.zs", b"nivel")
    _w(g / "updates/romfs/Level.alsarc.zs", b"nivel2")
    _w(g / "dlc/romfs/Extra.zs", b"dlc")
    C, D = h / ".config/eden", h / ".local/share/eden"
    _w(C / "qt-config.ini", f"nand_directory={D}/nand\nPaths\\recentFiles=\"{g}/base/exefs/main\"\n")
    _w(C / f"custom/{TID}.ini", "[Renderer]\nresolution_setup=3\n")
    _w(C / "custom/0100000000000001.ini", "outro jogo")
    _w(D / f"nand/user/save/0000000000000000/{UUID}/{TID}/0/progress.sav", b"save")
    _w(D / f"nand/user/save/0000000000000000/{UUID}/0100000000000001/x.sav", b"outro")
    _w(D / "nand/system/save/8000000000000010/su/avators/profiles.dat", b"perfil")
    _w(D / "nand/system/Contents/registered/abc.nca", b"firmware")
    _w(D / "keys/prod.keys", "header_key = 00\n")
    _w(D / f"load/{TID}/meumod/romfs/a.bin", b"mod")
    _w(D / f"sdmc/atmosphere/contents/{TID}/cheats/abcd.txt", "[60fps]\n")
    _w(D / "log/eden_log.txt", "log")
    _w(h / ".cache/eden/shader/vulkan.bin", b"shader")
    _w(h / "Emulation/Lichii/lichii-linux-x86_64-pgo.AppImage", b"ELF")
    lm = {"switch2-dkb": {"title": "Donkey Kong Bananza", "console": "switch2", "rom": str(g / "base/exefs/main")}}
    return h, lm


def test_manifesto_switch2_lichii(deck_switch2):
    h, lm = deck_switch2
    man = T.preparar("switch2-dkb", home=h, launch_map=lm, cache=None)
    cat, dst = _por_cat(man), _destinos(man)
    assert man["title_id"] == TID and man["emulador"] == "lichii"
    assert {a["destino"] for a in cat["jogo"]} >= {"{JOGOS}/switch2/Donkey Kong Bananza/base/exefs/main",
                                                    "{JOGOS}/switch2/Donkey Kong Bananza/base/romfs/Level.alsarc.zs"}
    assert [a["destino"] for a in cat["update"]] == ["{JOGOS}/switch2/Donkey Kong Bananza/updates/romfs/Level.alsarc.zs"]
    assert len(cat["dlc"]) == 1
    assert [a["destino"] for a in cat["save"]] == [f"{{EMU}}/nand/user/save/0000000000000000/{UUID}/{TID}/0/progress.sav"]
    assert "{EMU}/config/qt-config.ini" in dst and dst["{EMU}/config/qt-config.ini"]["reescrever"]
    assert f"{{EMU}}/config/custom/{TID}.ini" in dst and "{EMU}/config/custom/0100000000000001.ini" not in dst
    assert {a["destino"] for a in cat["mods"]} == {f"{{EMU}}/load/{TID}/meumod/romfs/a.bin",
                                                    f"{{EMU}}/sdmc/atmosphere/contents/{TID}/cheats/abcd.txt"}
    assert {"{EMU}/keys/prod.keys", "{EMU}/nand/system/Contents/registered/abc.nca"} <= {a["destino"] for a in cat["keys"]}
    assert "{EMU}/nand/system/save/8000000000000010/su/avators/profiles.dat" in dst  # perfil (UUID do save)
    assert cat["emulador-linux"][0]["destino"] == "{LINUX}/lichii/lichii-linux-x86_64-pgo.AppImage"
    tudo = " ".join(a["origem"] for a in man["arquivos"])
    assert "shader" not in tudo and "eden_log" not in tudo and "0100000000000001" not in tudo
    assert any("shader" in x["caminho"] and "GPU" in x["motivo"] for x in man["excluidos"])
    trocas = {r["de"]: r["para"] for r in man["reescrever"]}
    assert trocas[str(h / ".local/share/eden")] == "{EMU}" and trocas[str(h / ".config/eden")] == "{EMU}/config"
    assert trocas[str(h / "Emulation/roms/switch2")] == "{JOGOS}/switch2"
    assert [len(r["de"]) for r in man["reescrever"]] == sorted((len(r["de"]) for r in man["reescrever"]), reverse=True)
    a = dst["{JOGOS}/switch2/Donkey Kong Bananza/base/romfs/Level.alsarc.zs"]
    assert a["sha256"] == hashlib.sha256(b"nivel").hexdigest() and a["tamanho"] == 5
    assert man["total_bytes"] == sum(x["tamanho"] for x in man["arquivos"])
    assert man["resumo"]["save"] == {"arquivos": 1, "bytes": 4}
    assert man["saves"][0].endswith(TID)
    assert "github.com/zortos293/Lichii/releases" in man["emulador_windows"]["releases"]


def test_cache_de_hash_nao_recalcula(deck_switch2, tmp_path):
    h, lm = deck_switch2
    cache = tmp_path / "cache.json"
    m1 = T.preparar("switch2-dkb", home=h, launch_map=lm, cache=cache)
    assert cache.exists()
    p = h / "Emulation/roms/switch2/Donkey Kong Bananza/base/romfs/Level.alsarc.zs"
    st = p.stat()
    p.write_bytes(b"NIVEL")  # mesmo tamanho; volta a data: o cache vale (prova que não leu de novo)
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns))
    m2 = T.preparar("switch2-dkb", home=h, launch_map=lm, cache=cache)
    assert _destinos(m2)["{JOGOS}/switch2/Donkey Kong Bananza/base/romfs/Level.alsarc.zs"]["sha256"] == \
        hashlib.sha256(b"nivel").hexdigest()
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))  # data mudou: recalcula
    m3 = T.preparar("switch2-dkb", home=h, launch_map=lm, cache=cache)
    assert _destinos(m3)["{JOGOS}/switch2/Donkey Kong Bananza/base/romfs/Level.alsarc.zs"]["sha256"] == \
        hashlib.sha256(b"NIVEL").hexdigest()
    assert m1["total_bytes"] == m3["total_bytes"]


def test_sem_hash_e_jogo_inexistente(deck_switch2):
    h, lm = deck_switch2
    man = T.preparar("switch2-dkb", home=h, launch_map=lm, com_hash=False)
    assert all(a["sha256"] is None for a in man["arquivos"])
    with pytest.raises(KeyError):
        T.preparar("nao-existe", home=h, launch_map=lm)


# ------------------------------------------------------------------ Switch / Ryujinx ---
def test_manifesto_switch_ryujinx(tmp_path):
    h = tmp_path
    pasta = h / "Emulation/roms/switch/Luigis Mansion 3 [NSZ]"
    base = _w(pasta / "Luigis Mansion 3 [0100DCA0064A6000][v0].nsp", b"base")
    _w(pasta / "Luigis Mansion 3 [0100DCA0064A6800][v327680].nsp", b"upd")
    _w(pasta / "2 DLC/Luigis Mansion 3 [DLC 1] [0100DCA0064A7001][v1].nsp", b"dlc1")
    _w(pasta / "Outro Jogo [0100F43008C44000][v0].nsp", b"outro")
    R = h / ".config/Ryujinx"
    _w(R / "Config.json", '{"game_dirs": ["' + str(h / "Emulation/roms/switch") + '"]}')  # caminho cru (no Deck é /home/deck/...)
    _w(R / "profiles/controller/deck.json", "{}")
    _w(R / "system/Profiles.json", "{}")
    _w(R / "system/prod.keys", "k")
    _w(R / "bis/system/Contents/registered/fw.nca", b"fw")
    _w(R / "bis/system/save/8000000000000000/0/imkvdb.arc",
       _imkvdb([(0x0100DCA0064A6000, 3, 1), (0x0100F43008C44000, 4, 1)]))
    _w(R / "bis/user/save/0000000000000003/0/save.bin", b"meu save")
    _w(R / "bis/user/save/0000000000000004/0/save.bin", b"save de outro")
    _w(R / "mods/contents/0100dca0064a6000/PT-BR/romfs/t.msbt", b"mod")
    _w(R / "games/0100dca0064a6000/updates.json", json.dumps({"selected": "", "paths": [str(pasta / "nao-existe.nsp")]}))
    _w(R / "games/0100dca0064a6000/cache/shader/x.cache", b"cache")
    lm = {"switch-lm3": {"title": "Luigis Mansion 3", "console": "switch", "rom": str(base)}}
    man = T.preparar("switch-lm3", home=h, launch_map=lm, cache=None)
    cat, dst = _por_cat(man), _destinos(man)
    assert man["title_id"] == "0100DCA0064A6000" and man["emulador"] == "ryujinx"
    assert [a["origem"] for a in cat["jogo"]] == [str(base)]
    assert len(cat["update"]) == 1 and len(cat["dlc"]) == 1
    assert "{JOGOS}/switch/Luigis Mansion 3 [NSZ]/2 DLC/Luigis Mansion 3 [DLC 1] [0100DCA0064A7001][v1].nsp" in dst
    assert [a["destino"] for a in cat["save"]] == ["{EMU}/bis/user/save/0000000000000003/0/save.bin"]
    assert man["saves_ryujinx"][0]["save_data_id"] == "0000000000000003"
    assert "{EMU}/bis/system/save/8000000000000000/0/imkvdb.arc" in dst
    assert dst["{EMU}/Config.json"]["reescrever"] and "{EMU}/games/0100dca0064a6000/updates.json" in dst
    assert "{EMU}/mods/contents/0100dca0064a6000/PT-BR/romfs/t.msbt" in dst
    assert {"{EMU}/system/prod.keys", "{EMU}/bis/system/Contents/registered/fw.nca"} <= {a["destino"] for a in cat["keys"]}
    assert not any("cache" in d for d in dst) and not any("Outro Jogo" in d for d in dst)
    assert any("não encontrado" in a for a in man["avisos"])


# ------------------------------------------------------------------ PS1 / DuckStation --
def test_manifesto_psx_duckstation(tmp_path):
    h = tmp_path
    g = h / "Emulation/roms/psx/[SLUS-00529] Hercules"
    _w(g / "[SLUS-00529] Hercules.bin", b"\0" * 100)
    cue = _w(g / "[SLUS-00529] Hercules.cue", 'FILE "[SLUS-00529] Hercules.bin" BINARY\n')
    D = h / ".local/share/duckstation"
    bios = h / "Emulation/bios"
    _w(D / "settings.ini", f"[BIOS]\nSearchDirectory = {bios}\n[GameList]\nRecursivePaths = {h}/Downloads\n")
    _w(D / "memcards/[SLUS-00529] Hercules_1.mcd", b"card")
    _w(D / "memcards/Outro Jogo_1.mcd", b"card")
    _w(D / "savestates/SLUS-00529_1.sav", b"st")
    _w(D / "gamesettings/SLUS-00529.ini", "[Main]\n")
    _w(D / "cache/gamelist.cache", b"c")
    _w(bios / "SCPH1001.BIN", b"\0" * 512 * 1024)
    _w(bios / "SCPH-70004.ROM1", b"\0" * 512 * 1024)  # do PS2: não entra no PS1
    _w(h / "Applications/DuckStation-x64.AppImage", b"ELF")
    lm = {"psx-hercules": {"title": "Hercules", "console": "psx", "rom": str(cue)}}
    man = T.preparar("psx-hercules", home=h, launch_map=lm, cache=None)
    cat, dst = _por_cat(man), _destinos(man)
    assert man["serial"] == "SLUS-00529" and man["emulador"] == "duckstation"
    assert len(cat["jogo"]) == 2
    assert {a["destino"] for a in cat["save"]} == {"{EMU}/memcards/[SLUS-00529] Hercules_1.mcd",
                                                    "{EMU}/savestates/SLUS-00529_1.sav"}
    assert [a["destino"] for a in cat["keys"]] == ["{EMU}/bios/SCPH1001.BIN"]
    assert "{EMU}/gamesettings/SLUS-00529.ini" in dst and dst["{EMU}/settings.ini"]["reescrever"]
    assert {r["de"]: r["para"] for r in man["reescrever"]}[str(bios)] == "{EMU}/bios"
    assert not any("cache" in d for d in dst)


# ------------------------------------------------------------------ saída / bot --------
def test_tsv_e_resumo(deck_switch2):
    h, lm = deck_switch2
    man = T.preparar("switch2-dkb", home=h, launch_map=lm, cache=None)
    linhas = T.tsv(man).splitlines()
    assert linhas[0].startswith("DCMANIFESTO\t1\t")
    meta = json.loads(linhas[0].split("\t", 2)[2])
    assert meta["game_id"] == "switch2-dkb" and "arquivos" not in meta
    c = linhas[1].split("\t")
    assert c[0] == "F" and len(c[1]) == 64 and len(c) == 7 and c[5].startswith(("{JOGOS}", "{EMU}", "{LINUX}"))
    assert len(linhas) == 1 + len(man["arquivos"])
    txt = T.texto_resumo(man)
    assert "save: 1 arquivos" in txt and "no PC instale" in txt


def test_nome_com_tab_fica_de_fora(tmp_path):
    m = T.Manifesto("x", {}, "retroarch")  # no Windows nem dá para criar esse arquivo; no Deck dá
    m.add(tmp_path / "Jogo	.sav", "save", "{EMU}/saves/Jogo	.sav")
    assert not m.arquivos and m.excluidos


class _Bot:
    def __init__(self, lm):
        self.lm = lm

    def _map(self):
        return self.lm


def test_comando_transferir(deck_switch2, monkeypatch):
    h, lm = deck_switch2
    monkeypatch.setenv("DC_ROOT", str(h))
    bot = _Bot(lm)
    assert "Uso:" in T.comando_transferir(bot, [])
    assert "Não achei" in T.comando_transferir(bot, ["zelda"])
    r = T.comando_transferir(bot, ["donkey", "kong"])
    assert "Donkey Kong Bananza" in r and "transferir-do-deck.bat -Jogo switch2-dkb" in r and "save:" in r


def test_cli_lista_e_resumo(deck_switch2, monkeypatch, capsys):
    h, lm = deck_switch2
    monkeypatch.setenv("DC_ROOT", str(h))
    _w(h / ".local/share/deck-commander/launch-map.json", json.dumps(lm))
    assert T.main(["lista"]) == 0
    assert "switch2-dkb\tDonkey Kong Bananza\tswitch2" in capsys.readouterr().out
    assert T.main(["resumo", "switch2-dkb"]) == 0
    assert "Donkey Kong Bananza" in capsys.readouterr().out
    assert T.main(["manifesto", "nao-existe"]) == 1
    assert T.main([]) == 2


def test_rom_solta_ganha_pasta_do_jogo(tmp_path):
    iso = _w(tmp_path / "Emulation/roms/ps2/God of War 2.iso", b"\0" * 10)
    lm = {"ps2-gow2": {"title": "God of War 2: Versão", "console": "ps2", "rom": str(iso)}}
    man = T.preparar("ps2-gow2", home=tmp_path, launch_map=lm, cache=None)
    d = [a["destino"] for a in man["arquivos"] if a["categoria"] == "jogo"]
    assert d == ["{JOGOS}/ps2/God of War 2_ Versão/God of War 2.iso"]
    trocas = {r["de"]: r["para"] for r in man["reescrever"]}
    assert trocas[str(iso)] == d[0]  # config que cita o .iso aponta para o lugar novo
    assert man["emulador_windows"]["projeto"] == "PCSX2"
