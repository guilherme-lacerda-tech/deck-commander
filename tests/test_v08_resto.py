"""0.8 — texturas HD, netplay e dublagem (docs/specs/texturas.md, netplay.md, dublagem.md)."""
import json
import struct
import zipfile
from pathlib import Path
from types import SimpleNamespace

from dc import dublagem, netplay, texturas


# ------------------------------------------------------------------------------------------- texturas
def _iso_ps2(p: Path, cnf: bytes) -> None:
    setores = [bytearray(2048) for _ in range(22)]
    raiz = bytearray(34)
    raiz[0] = 34
    struct.pack_into("<I", raiz, 2, 18)
    struct.pack_into("<I", raiz, 10, 2048)
    setores[16][156:190] = raiz
    nome = b"SYSTEM.CNF;1"
    reg = bytearray(33 + len(nome) + 1)
    reg[0] = len(reg)
    struct.pack_into("<I", reg, 2, 20)
    struct.pack_into("<I", reg, 10, len(cnf))
    reg[32] = len(nome)
    reg[33:33 + len(nome)] = nome
    setores[18][:len(reg)] = reg
    setores[20][:len(cnf)] = cnf
    p.write_bytes(b"".join(bytes(s) for s in setores))


def test_texturas_ps2(tmp_path):
    iso = tmp_path / "jogo.iso"
    _iso_ps2(iso, b"BOOT2 = cdrom0:\\SLUS_203.12;1\nVER = 1.00\n")
    assert texturas.serial_ps2(iso) == "SLUS-20312"
    home = tmp_path / "home"
    ini = home / ".var/app/net.pcsx2.PCSX2/config/PCSX2/inis/PCSX2.ini"
    ini.parent.mkdir(parents=True)
    ini.write_text("[EmuCore/GS]\nRenderer = -1\n\n[Pad]\nA = 1\n")

    def baixar(url, destino):
        destino.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(destino, "w") as z:
            z.writestr("pack/a.png", b"x")
            z.writestr("pack/b.dds", b"y")
            z.writestr("../fora.txt", b"mal")
    msg = texturas.instalar(home, "ps2", iso, "https://exemplo/pack.zip", baixar)
    pasta = home / ".var/app/net.pcsx2.PCSX2/config/PCSX2/textures/SLUS-20312/replacements"
    assert sorted(p.name for p in pasta.iterdir()) == ["a.png", "b.dds"] and "2 arquivos" in msg
    txt = ini.read_text()
    assert "LoadTextureReplacements = true" in txt and txt.index("LoadTextureReplacements") < txt.index("[Pad]")
    assert not (tmp_path / "fora.txt").exists()


def test_texturas_gc_e_console_errado(tmp_path):
    iso = tmp_path / "zelda.iso"
    iso.write_bytes(b"GALE01" + bytes(100))
    assert texturas.id_gc(iso) == "GALE01"
    import pytest
    with pytest.raises(ValueError):
        texturas.instalar(tmp_path, "switch", iso, "x", lambda u, d: None)


# ------------------------------------------------------------------------------------------- netplay
def test_netplay(tmp_path):
    netplay.pedir(tmp_path, "snes-mario", "host", agora=1000)
    assert netplay.argumentos(tmp_path, "snes-mario", agora=1100) == ["--host", "--port", "55435"]
    assert netplay.argumentos(tmp_path, "snes-mario", agora=1101) == []  # vale uma vez
    netplay.pedir(tmp_path, "snes-mario", "cliente", ip="100.64.0.2", agora=1000)
    assert netplay.argumentos(tmp_path, "snes-mario", agora=2000) == []  # vencido
    ra = ["/usr/bin/flatpak", "run", "org.libretro.RetroArch", "-L", "x.so", "/r.sfc"]
    assert netplay.aplicar_no_comando(ra, ["--host"])[-2:] == ["--host", "/r.sfc"]
    ds = ["/a/DuckStation-x64.AppImage", "/r.cue"]
    assert netplay.aplicar_no_comando(ds, ["--host"]) == ds
    import time
    netplay.convite(tmp_path, "Irmão", "snes-mario", "Mario", "100.64.0.9", agora=time.time())
    import time
    assert netplay.convite_pendente(tmp_path)["de"] == "Irmão"
    c = netplay.aceitar(tmp_path)
    assert c["ip"] == "100.64.0.9" and netplay.convite_pendente(tmp_path, agora=time.time()) is None
    cmd = netplay.comando_convidar_remoto("deck@x", "/k", "Gui", "snes-mario", "Mario", "100.64.0.1")
    assert cmd[:2] == ["ssh", "-i"] and "dc.netplay receber" in cmd[-1]
    run = lambda *a, **k: SimpleNamespace(returncode=0, stdout="100.64.0.1\n", stderr="")
    assert netplay.ip_tailscale(run) == "100.64.0.1"


# ------------------------------------------------------------------------------------------- dublagem
def test_srt_e_mix():
    assert dublagem.srt([dublagem.Fala(1.5, 3.25, "Olá")]) == "1\n00:00:01,500 --> 00:00:03,250\nOlá\n\n"
    cmd = dublagem.comando_mixar(Path("v.mp4"), [(1.0, Path("a.mp3")), (2.5, Path("b.mp3"))], Path("s.mp4"))
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "adelay=1000|1000" in fc and "adelay=2500|2500" in fc and "amix=inputs=3" in fc
    assert "-c:v" in cmd and cmd[cmd.index("-c:v") + 1] == "copy"
    assert dublagem.videos_do_jogo(["a/intro.MP4", "b/x.bin", "c/fim.webm"]) == ["a/intro.MP4", "c/fim.webm"]


def test_dublar(tmp_path):
    chamadas = []

    def run(args, **k):
        chamadas.append(args)
        if args[1:2] == ["-hide_banner"]:  # info(): duração e faixas pela saída do ffmpeg
            return SimpleNamespace(returncode=1, stdout="", stderr="  Duration: 00:00:01.00, start\n"
                                   "  Stream #0:0: Video: vp9\n  Stream #0:1: Audio: opus, 48000 Hz\n")
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    falou = []
    falas = [dublagem.Fala(0.5, 2.0, "Hello"), dublagem.Fala(3.0, 4.0, "Bye")]
    r = dublagem.dublar(tmp_path / "v.mp4", tmp_path / "s.mp4", tmp_path / "trab", lambda wav: falas,
                        lambda ts: ["Olá", "Tchau"], lambda t, p: falou.append((t, p)), run=run)
    assert r["falas"] == 2 and [t for t, _ in falou] == ["Olá", "Tchau"]
    assert "Tchau" in (tmp_path / "trab/legenda.srt").read_text("utf-8")
    assert any("-filter_complex" in c for c in chamadas)
    json.dumps(r)


def test_video_sem_audio_nao_dubla(tmp_path):
    """Falha real (Zelda TotK): os vídeos não têm som — a voz fica em arquivos .bwav separados."""
    run = lambda args, **k: SimpleNamespace(returncode=1, stdout="", stderr="  Duration: 00:01:48.17\n  Stream #0:0: Video: vp9\n")
    r = dublagem.dublar(tmp_path / "v.webm", tmp_path / "s.webm", tmp_path / "t", lambda w: 1 / 0, None, None, run=run)
    assert r["falas"] == 0 and r["sem_audio"]
    cmd = dublagem.comando_mixar(Path("v.webm"), [(1.0, Path("a.mp3"))], Path("s.webm"), tem_audio=False)
    assert "libopus" in cmd and "[bg]" not in cmd[cmd.index("-filter_complex") + 1]
