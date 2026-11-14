"""Falha real 14/11/2026 (Telegram): o Metal Gear (PS1) foi mandado sem console; o usuário respondeu "Ps1" e o bot
entendeu "o PRÓXIMO download é PS1" — o Darkwatch, de PS2 ("(PS2)DARKWATCH.7z"), foi marcado como PS1.

Agora: (1) o console dito logo depois de um download sem console vale para ele; (2) o nome de dentro do torrent
vale mais que o console dito antes; (3) /console corrige um download ainda baixando; (4) no /sync, o próprio disco
diz se é PS1 ou PS2."""
import hashlib

import pytest

from dc import bot, content, dedup, syncer
from dc.paths import get_paths
from tests.test_transplante import iso

INFO_MGS = b"d4:name20:MetalGearSolidRus.7z12:piece lengthi16384ee"
INFO_DW = b"d4:name17:(PS2)DARKWATCH.7z12:piece lengthi16384ee"


def torrent(info: bytes) -> bytes:
    return b"d8:announce3:url4:info" + info + b"e"


class FakeQbt:
    def __init__(self):
        self.added, self.cats, self.lista = [], {}, []

    def torrents(self, *a, **k):
        return self.lista

    def add(self, magnet, cat, dest, extra_tags=""):
        self.added.append((magnet, cat))

    def add_file(self, data, name, cat, dest, extra_tags=""):
        self.added.append((name, cat))

    def set_category(self, h, c):
        self.cats[h] = c


@pytest.fixture
def x(tmp_path, monkeypatch):
    b = bot.Bot(get_paths(tmp_path).ensure(), "TOK")
    b.cfg["allowed"] = [1]
    b.qbt = FakeQbt()
    b.limited = lambda uid: False
    b.dados = {}
    b.call = lambda method, **kw: {"file_path": kw.get("file_id", "f")} if method == "getFile" else []

    class R:
        def __init__(self, url, *a, **k):
            self.url = url

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b.dados[self.url.rsplit("/", 1)[-1]]
    monkeypatch.setattr(bot.urllib.request, "urlopen", R)
    monkeypatch.setattr(syncer, "_cfg", lambda p: {"downloads_root": str(tmp_path / "dl")})
    return b


def msg(b, text=None, **extra):
    m = {"from": {"id": 1}, "chat": {"id": 9}, **extra}
    if text is not None:
        m["text"] = text
    return b.handle_message(m)


def doc(b, nome, dados):
    b.dados[nome] = dados
    return msg(b, document={"file_id": nome, "file_name": nome})


def test_codigo_do_torrent_e_do_magnet():
    assert dedup.info_hash(torrent(INFO_MGS)) == hashlib.sha1(INFO_MGS).hexdigest()
    assert dedup.info_hash(b"<html>") is None
    assert dedup.magnet_hash("magnet:?xt=urn:btih:" + "AB" * 20) == "ab" * 20
    assert dedup.magnet_hash("magnet:?xt=urn:btih:" + "A" * 32) == "00" * 20
    assert dedup.magnet_hash("magnet:?dn=x") is None


def test_o_caso_do_deck_ps1_responde_o_download_anterior_e_o_ps2_vai_para_ps2(x):
    r = doc(x, "Metal Gear Solid [SLUS-00594] [RUS].torrent", torrent(INFO_MGS))
    assert "Não sei o console" in r and "responda" in r and "/sync vai perguntar" not in r
    assert x.qbt.added[-1][1] == "auto"
    r = msg(x, "Ps1")
    assert r.startswith("Ok, Metal Gear Solid [SLUS-00594] [RUS] = PS1")
    h = hashlib.sha1(INFO_MGS).hexdigest()
    assert x.qbt.cats == {h: "psx"} and x.cfg["explicit"][h] == "psx"
    assert not x.cfg["pending_console"]  # não virou "o próximo é PS1"
    r = doc(x, "Darkwatch [ENG NTSC].torrent", torrent(INFO_DW))
    assert x.qbt.added[-1] == ("Darkwatch [ENG NTSC].torrent", "ps2") and "(PS2)" in r


def test_nome_de_dentro_do_torrent_vale_mais_que_o_console_dito_antes(x):
    assert "próximo" in msg(x, "PS1")
    r = doc(x, "Darkwatch [ENG NTSC].torrent", torrent(INFO_DW))
    assert x.qbt.added[-1][1] == "ps2"
    assert "Você tinha dito PS1" in r and "Baixei como PS2" in r
    assert "Console errado? /console " + hashlib.sha1(INFO_DW).hexdigest()[:8] in r


def test_console_dito_junto_vale_mas_avisa_se_o_nome_discorda(x):
    x.dados["dw"] = torrent(INFO_DW)
    r = msg(x, document={"file_id": "dw", "file_name": "Darkwatch.torrent"}, caption="ps1")
    assert x.qbt.added[-1][1] == "psx" and "parece PS2" in r


def test_sem_download_sem_console_o_console_continua_valendo_para_o_proximo(x):
    assert "próximo .torrent ou magnet = ps2" in msg(x, "PS2")
    doc(x, "Okami.torrent", torrent(b"d4:name9:Okami.iso12:piece lengthi1ee"))
    assert x.qbt.added[-1][1] == "ps2"


def test_magnet_sem_console_tambem_aceita_a_resposta(x):
    mag = "magnet:?xt=urn:btih:" + "c" * 40 + "&dn=Jogo"
    assert "responda só o nome do console" in msg(x, mag)
    assert msg(x, "PS2").startswith("Ok, Jogo = PS2")
    assert x.qbt.cats == {"c" * 40: "ps2"}


def test_magnet_com_nome_de_console_vence_o_dito_antes(x):
    msg(x, "PS1")
    r = msg(x, "magnet:?xt=urn:btih:" + "d" * 40 + "&dn=%28PS2%29Darkwatch.7z")
    assert x.qbt.added[-1][1] == "ps2" and "Baixei como PS2" in r


def test_resposta_depois_de_10_min_volta_a_ser_para_o_proximo(x, monkeypatch):
    doc(x, "MGS.torrent", torrent(INFO_MGS))
    x.cfg["sem_console"]["1"]["at"] -= bot.PENDING_TTL + 1
    assert "próximo" in msg(x, "PS1") and x.qbt.cats == {}


def test_console_corrige_download_ainda_baixando(x):
    h = "a2c054db" + "0" * 32
    x.qbt.lista = [{"hash": h, "name": "(PS2)DARKWATCH.7z", "category": "psx"}]
    r = msg(x, "/console a2c054db ps2")
    assert r == "Ok, (PS2)DARKWATCH.7z = PS2. Vale quando terminar de baixar."
    assert x.qbt.cats == {h: "ps2"} and x.cfg["explicit"][h] == "ps2"
    assert msg(x, "/console darkwatch ps2").startswith("Ok, (PS2)DARKWATCH.7z")  # pelo nome também
    assert "Não achei" in msg(x, "/console ffffffff ps2")


def test_console_nao_mexe_em_jogo_que_ja_foi_para_a_biblioteca(x):
    h = "b" * 40
    st = syncer._state(x.paths)
    st.setdefault("ingested", {})[h] = {"name": "X", "files": ["/r/x.iso"]}
    syncer._save_state(x.paths, st)
    x.qbt.lista = [{"hash": h, "name": "X", "category": "psx"}]
    assert "já foi para a biblioteca" in msg(x, f"/console {h[:8]} ps2") and x.qbt.cats == {}


# -- o disco diz o console -----------------------------------------------------------------------------------
def _bin_2352(img2048: bytes) -> bytes:
    """Converte uma imagem de 2048 em CD "cru" de 2352 (modo 2: 24 bytes antes dos dados)."""
    out = bytearray()
    for i in range(0, len(img2048), 2048):
        out += b"\0" * 24 + img2048[i:i + 2048] + b"\0" * 280
    return bytes(out)


def test_disco_ps2_e_ps1(tmp_path):
    ps2 = tmp_path / "dw.iso"
    ps2.write_bytes(iso({"/SYSTEM.CNF": b"BOOT2 = cdrom0:\\SLUS_212.52;1\r\nVER = 1.00\r\n"}))
    ps1 = tmp_path / "mgs.bin"
    ps1.write_bytes(_bin_2352(iso({"/SYSTEM.CNF": b"BOOT = cdrom:\\SLUS_005.94;1\r\n"})))
    nada = tmp_path / "x.iso"
    nada.write_bytes(b"\0" * 40000)
    assert content.console_do_disco(ps2) == "ps2"
    assert content.console_do_disco(ps1) == "psx"
    assert content.console_do_disco(nada) is None
    assert content.console_do_disco(tmp_path / "nao-existe.iso") is None


def test_sync_de_jogo_ps2_marcado_como_ps1_vai_para_ps2(tmp_path):
    d = tmp_path / "(PS2)DARKWATCH"
    d.mkdir()
    (d / "DARKWATCH.iso").write_bytes(iso({"/SYSTEM.CNF": b"BOOT2 = cdrom0:\\SLUS_212.52;1\r\n"}))
    it = content.ingest(d, "psx", tmp_path / "roms", tmp_path / "q", tmp_path / "work")
    assert it.status == "added" and it.console == "ps2"
    assert "o disco é de PS2, não de PS1" in it.note
    assert all("/roms/ps2/" in f.replace("\\", "/") for f in it.files)


def test_sync_de_jogo_ps1_marcado_como_ps2_vai_para_ps1(tmp_path):
    d = tmp_path / "MGS"
    d.mkdir()
    (d / "MGS.bin").write_bytes(_bin_2352(iso({"/SYSTEM.CNF": b"BOOT = cdrom:\\SLUS_005.94;1\r\n"})))
    (d / "MGS.cue").write_text('FILE "MGS.bin" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n')
    it = content.ingest(d, "ps2", tmp_path / "roms", tmp_path / "q", tmp_path / "work")
    assert it.status == "added" and it.console == "psx" and "o disco é de PS1" in it.note
