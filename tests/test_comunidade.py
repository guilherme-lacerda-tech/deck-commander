"""Regra do usuário (14/11/2026): todo jogo novo procura PRIMEIRO uma tradução feita por fãs (a tarefa do PC busca);
a IA só traduz quando não existe, ou quando o PC ficou 72 h sem procurar."""
import json

import pytest

from dc import remove, syncer
from dc.paths import get_paths
from dc.traducao import comunidade as C
from dc.traducao import run
from tests.test_console_errado import _bin_2352
from tests.test_transplante import iso


@pytest.fixture
def P(tmp_path):
    return get_paths(tmp_path).ensure()


def test_fila_espera_e_libera(P):
    assert C.registrar(P, "ps2-x", {"title": "X", "console": "ps2", "rom": "/nao/existe.iso"})
    assert not C.registrar(P, "ps2-x", {"title": "X"})  # entra uma vez só
    assert C.esperando(P, "ps2-x") and list(C.pendentes(P)) == ["ps2-x"]
    assert not C.esperando(P, "ps2-outro")  # fora da fila: não segura nada
    C.marcar(P, "ps2-x", "precisa_voce", "o site só baixa no navegador", store=object())
    assert C.esperando(P, "ps2-x")  # precisa de você: a IA não passa na frente
    assert C.avisos(P) == ["🔎 X: achei a tradução da comunidade, mas preciso de você: o site só baixa no navegador"]
    assert C.avisos(P) == []  # aviso sai uma vez
    with pytest.raises(ValueError):
        C.marcar(P, "ps2-x", "talvez")
    with pytest.raises(KeyError):
        C.marcar(P, "ps2-nada", "aplicado")


def test_nao_existe_e_72h_liberam_a_ia(P, monkeypatch):
    chamados = []
    monkeypatch.setattr(run, "auto_queue", lambda paths, store, gids: chamados.append(gids) or ["🈯 IA"])
    C.registrar(P, "psx-a", {"title": "A"})
    C.registrar(P, "psx-b", {"title": "B"})
    assert "A IA vai traduzir" in C.marcar(P, "psx-a", "nao_existe", store=object())
    assert chamados == [["psx-a"]] and not C.esperando(P, "psx-a")
    agora = C.carregar(P)["psx-b"]["desde"] + C.ESPERA_MAX_H * 3600 + 1
    assert not C.esperando(P, "psx-b", agora=agora)
    linhas = C.vencidos(P, store=object(), agora=agora)
    assert len(linhas) == 1 and "72 h" in linhas[0] and chamados[-1] == ["psx-b"]
    assert C.carregar(P)["psx-b"]["situacao"] == "sem_resposta"


def test_codigo_do_disco_vai_para_a_busca(tmp_path, P):
    d = tmp_path / "mgs"
    d.mkdir()
    (d / "mgs_cd1.bin").write_bytes(_bin_2352(iso({"/SYSTEM.CNF": b"BOOT = cdrom:\\SLUS_005.94;1\r\n"})))
    (d / "mgs_cd1.cue").write_text('FILE "mgs_cd1.bin" BINARY\n  TRACK 01 MODE2/2352\n')
    (d / "MGS.m3u").write_text("mgs_cd1.cue\n")
    assert C.serial(str(d / "MGS.m3u")) == "SLUS_005.94"
    ps2 = tmp_path / "dw.iso"
    ps2.write_bytes(iso({"/SYSTEM.CNF": b"BOOT2 = cdrom0:\\SLES_535.64;1\r\n"}))
    assert C.serial(str(ps2)) == "SLES_535.64"
    assert C.serial(str(tmp_path / "nada.iso")) == ""


def _ips(pos: int, novo: bytes) -> bytes:
    return b"PATCH" + pos.to_bytes(3, "big") + len(novo).to_bytes(2, "big") + novo + b"EOF"


def _publicacao_falsa(monkeypatch):
    escondidos = []
    monkeypatch.setattr(syncer, "add_to_steam", lambda paths, store, op: [])
    monkeypatch.setattr(remove, "hide", lambda paths, gid, motivo: escondidos.append(gid))
    monkeypatch.setattr(run, "_herdar_detonado", lambda *a: None)

    class Store:
        def enqueue(self, *a, **k): return "op"
        def claim(self, op): pass
        def finish(self, *a, **k): pass
    return escondidos, Store()


def test_aplicar_patch_em_jogo_de_cartucho(P, tmp_path, monkeypatch):
    rom = tmp_path / "roms/gba/Jogo/Jogo.gba"
    rom.parent.mkdir(parents=True)
    rom.write_bytes(b"\0" * 64)
    (P.data / "launch-map.json").write_text(json.dumps({"gba-jogo": {"title": "Jogo", "console": "gba",
                                                                      "rom": str(rom)}}))
    C.registrar(P, "gba-jogo", {"title": "Jogo", "console": "gba", "rom": str(rom)})
    patch = tmp_path / "trad.ips"
    patch.write_bytes(_ips(4, b"PT"))
    escondidos, store = _publicacao_falsa(monkeypatch)
    r = C.aplicar(P, "gba-jogo", patch, store=store)
    novo = rom.with_name("Jogo (PT-BR).gba")
    assert novo.read_bytes()[4:6] == b"PT" and rom.read_bytes() == b"\0" * 64  # original intacto
    assert "achei a tradução da comunidade e apliquei" in r and escondidos == ["gba-jogo"]
    assert C.carregar(P)["gba-jogo"]["situacao"] == "aplicado"


def test_aplicar_em_jogo_de_dois_cds_monta_cue_e_m3u(P, tmp_path, monkeypatch):
    pasta = tmp_path / "roms/psx/MGS"
    sub = pasta / "MGS"
    sub.mkdir(parents=True)
    for n in (1, 2):
        (sub / f"mgs_cd{n}.bin").write_bytes(b"\0" * 64)
        (sub / f"mgs_cd{n}.cue").write_text(f'FILE "mgs_cd{n}.bin" BINARY\n  TRACK 01 MODE2/2352\n')
    m3u = pasta / "Metal Gear Solid.m3u"
    m3u.write_text("MGS/mgs_cd1.cue\nMGS/mgs_cd2.cue\n")
    (P.data / "launch-map.json").write_text(json.dumps({"psx-mgs": {"title": "MGS", "console": "psx",
                                                                     "rom": str(m3u)}}))
    C.registrar(P, "psx-mgs", {"title": "MGS", "console": "psx", "rom": str(m3u)})
    patch = tmp_path / "cd1.ips"
    patch.write_bytes(_ips(0, b"BR"))
    _escondidos, store = _publicacao_falsa(monkeypatch)
    with pytest.raises(ValueError):
        C.aplicar(P, "psx-mgs", patch, store=store)  # .m3u: precisa dizer qual disco
    C.aplicar(P, "psx-mgs", patch, sub / "mgs_cd1.bin", store=store)
    pt = pasta / "Metal Gear Solid (PT-BR).m3u"
    assert pt.read_text().splitlines() == ["MGS/mgs_cd1 (PT-BR).cue", "MGS/mgs_cd2.cue"]  # CD 2 ainda o original
    assert '"mgs_cd1 (PT-BR).bin"' in (sub / "mgs_cd1 (PT-BR).cue").read_text()
    C.aplicar(P, "psx-mgs", tmp_path / "cd1.ips", sub / "mgs_cd2.bin", store=store)
    assert pt.read_text().splitlines() == ["MGS/mgs_cd1 (PT-BR).cue", "MGS/mgs_cd2 (PT-BR).cue"]


def test_cli_sem_argumentos_explica(capsys, monkeypatch, P):
    monkeypatch.setattr("dc.paths.get_paths", lambda: P)
    assert C.main([]) == 2 and "listar" in capsys.readouterr().out


# -- PPF (formato comum das traduções de PS1/PS2) -------------------------------------------------------------
def _ppf3(regs, bloco=None, desc=b"Traducao PT-BR"):
    cab = b"PPF30" + b"\x02" + desc.ljust(50, b" ") + bytes([0, 1 if bloco else 0, 0, 0])
    corpo = b"".join(pos.to_bytes(8, "little") + bytes([len(b)]) + b for pos, b in regs)
    return cab + (bloco or b"") + corpo + b"@BEGIN_FILE_ID.DIZ" + b"oi" + b"@END_FILE_ID.DIZ" + (2).to_bytes(2, "little")


def test_ppf3_aplica_e_confere_a_versao(tmp_path):
    from dc import patches
    disco = tmp_path / "d.bin"
    orig = bytes(range(256)) * 200
    disco.write_bytes(orig)
    bloco = orig[0x9320:0x9320 + 1024]
    p = tmp_path / "t.ppf"
    p.write_bytes(_ppf3([(10, b"PT"), (0x9000, b"BR!")], bloco))
    out = patches.apply_file(disco, p, tmp_path / "d (PT-BR).bin")
    novo = out.read_bytes()
    assert novo[10:12] == b"PT" and novo[0x9000:0x9003] == b"BR!" and len(novo) == len(orig)
    assert disco.read_bytes() == orig  # original intacto
    outro = tmp_path / "outro.bin"
    outro.write_bytes(b"\xff" * len(orig))
    with pytest.raises(patches.PatchError, match="outra versão"):
        patches.apply_file(outro, p, tmp_path / "x.bin")
    assert not (tmp_path / "x.bin").exists()


def test_ppf1_e_ppf2(tmp_path):
    from dc import patches
    disco = tmp_path / "d.bin"
    orig = b"\0" * 0xA000
    disco.write_bytes(orig)
    p1 = tmp_path / "a.ppf"
    p1.write_bytes(b"PPF10\0" + b" " * 50 + (5).to_bytes(4, "little") + b"\x02" + b"ok")
    assert patches.apply_file(disco, p1, tmp_path / "a.bin").read_bytes()[5:7] == b"ok"
    p2 = tmp_path / "b.ppf"
    p2.write_bytes(b"PPF20\1" + b" " * 50 + len(orig).to_bytes(4, "little") + orig[0x9320:0x9320 + 1024]
                   + (7).to_bytes(4, "little") + b"\x01" + b"Z")
    assert patches.apply_file(disco, p2, tmp_path / "b.bin").read_bytes()[7:8] == b"Z"
