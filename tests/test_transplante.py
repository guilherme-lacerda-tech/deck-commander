"""Tradução feita para outra versão do disco (pedido 14/11/2026, God of War: Chains of Olympus da OAleex na ISO
russa): leva só os arquivos traduzidos do resultado do patch para o disco do usuário."""
import random
import struct
import zlib

import pytest

from dc.traducao import transplante as T

S = 2048


def _rec(nome: bytes, lba: int, tam: int, pasta: bool) -> bytes:
    n = len(nome)
    corpo = (struct.pack("<I", lba) + struct.pack(">I", lba) + struct.pack("<I", tam) + struct.pack(">I", tam)
             + bytes(7) + bytes([2 if pasta else 0]) + b"\0\0" + b"\1\0\0\1" + bytes([n]) + nome)
    r = bytes([0, 0]) + corpo
    if len(r) % 2:
        r += b"\0"
    return bytes([len(r)]) + r[1:]


def iso(arquivos: dict[str, bytes], ordem=None) -> bytes:
    """ISO 9660 mínima: pastas a partir do setor 18, arquivos depois (na `ordem` pedida)."""
    pastas = {""}
    for c in arquivos:
        partes = c.strip("/").split("/")
        for i in range(1, len(partes)):
            pastas.add("/" + "/".join(partes[:i]))
    pastas = sorted(pastas, key=lambda p: (p.count("/"), p))
    lba_pasta = {p: 18 + i for i, p in enumerate(pastas)}
    prox = 18 + len(pastas)
    lba_arq = {}
    for c in ordem or sorted(arquivos):
        lba_arq[c] = prox
        prox += max(1, (len(arquivos[c]) + S - 1) // S)
    img = bytearray(prox * S)
    for p in pastas:
        d = _rec(b"\0", lba_pasta[p], S, True) + _rec(b"\1", lba_pasta[p], S, True)
        filhos = sorted({c[len(p) + 1:].split("/")[0] for c in list(arquivos) + pastas if c.startswith(p + "/")
                         and c != p})
        for f in filhos:
            cam = p + "/" + f
            if cam in lba_pasta:
                d += _rec(f.encode(), lba_pasta[cam], S, True)
            else:
                d += _rec(f.encode() + b";1", lba_arq[cam], len(arquivos[cam]), False)
        img[lba_pasta[p] * S:lba_pasta[p] * S + len(d)] = d
    for c, b in arquivos.items():
        img[lba_arq[c] * S:lba_arq[c] * S + len(b)] = b
    pvd = bytearray(S)
    pvd[0:6] = b"\x01CD001"
    pvd[80:88] = struct.pack("<I", prox) + struct.pack(">I", prox)
    pvd[156:190] = _rec(b"\0", 18, S, True)
    img[16 * S:17 * S] = pvd
    return bytes(img)


def _sfo(disc: str) -> bytes:
    chave = b"DISC_ID\0"
    valor = disc.encode() + b"\0" * (16 - len(disc))
    cab = b"\0PSF" + struct.pack("<I", 0x101) + struct.pack("<III", 20 + 16, 20 + 16 + len(chave), 1)
    return cab + struct.pack("<HHIII", 0, 0x0204, len(disc) + 1, 16, 0) + chave + valor


def _pack(texto: bytes) -> bytes:
    corpo = bytearray(0x28) + texto
    corpo[0:4] = b"Pack"
    corpo[4:16] = b"\x04\0\x18\0\xff\xff\xff\xff\x02\0\0\0"
    corpo[0x24:0x28] = struct.pack("<I", len(corpo) - 4)
    return bytes(corpo)


FONTE_US = random.Random(7).randbytes(10240)  # fonte: pixels, sem repetição
TEXTO_US = _pack(b"Continue. Load Game " * 20)


def _discos():
    base = {"/PSP_GAME/PARAM.SFO": _sfo("UCUS98653"), "/PSP_GAME/USRDIR/data/level.bin": b"\x07LEVEL" * 3000}
    us = iso({**base, "/PSP_GAME/USRDIR/data/English/game.bin": TEXTO_US,
              "/PSP_GAME/USRDIR/data/font.fnt": FONTE_US})
    fonte_ru = bytearray(FONTE_US); fonte_ru[100:140] = b"\xd0" * 40  # letras russas
    ru = iso({**base, "/PSP_GAME/USRDIR/data/English/game.bin": _pack("Продолжить ".encode() * 30),
              "/PSP_GAME/USRDIR/data/font.fnt": bytes(fonte_ru)},
             ordem=["/PSP_GAME/USRDIR/data/level.bin", "/PSP_GAME/PARAM.SFO", "/PSP_GAME/USRDIR/data/font.fnt",
                    "/PSP_GAME/USRDIR/data/English/game.bin"])  # outra arrumação, como a ISO russa
    fonte_pt = bytearray(FONTE_US); fonte_pt[2000:2016] = b"\xaa" * 16  # "ã" desenhado no lugar do "û"
    fonte_pt[4:12] = b"\x99" * 8  # cabeçalho diferente: não dá para achar pelo começo (como no Deck)
    texto_pt = _pack("Continuar. Carregar Jogo Nûo hà ".encode("latin1") * 25)  # maior que o original
    pt = iso({**base, "/PSP_GAME/USRDIR/data/English/game.bin": texto_pt,
              "/PSP_GAME/USRDIR/data/font.fnt": bytes(fonte_pt)})
    return us, ru, pt, texto_pt, bytes(fonte_pt)


def _n(x):
    out = [x & 0x7F]
    x >>= 7
    while x:
        out.append(0x80 | (x & 0x7F))
        x >>= 7
    return bytes(reversed(out))


def _patch_xdelta(us: bytes, pt: bytes, copiar: tuple[int, int]) -> bytes:
    """Patch como o do tradutor: quase tudo dentro do patch; o trecho `copiar` (início, fim) vem do disco US."""
    a, b = copiar
    jan = []
    for alvo, src in ((pt[:a], None), (pt[a:b], (len(us), 0)), (pt[b:], None)):
        if src:
            inst, dados, ends = bytes([19]) + _n(len(alvo)), b"", _n(a)
        else:
            inst, dados, ends = bytes([1]) + _n(len(alvo)), alvo, b""
        wi = (1 if src else 0) | 4
        corpo = (_n(len(alvo)) + b"\0" + _n(len(dados)) + _n(len(inst)) + _n(len(ends))
                 + zlib.adler32(alvo).to_bytes(4, "big") + dados + inst + ends)
        jan.append(bytes([wi]) + (_n(src[0]) + _n(src[1]) if src else b"") + _n(len(corpo)) + corpo)
    return b"\xd6\xc3\xc4\x00\x00" + b"".join(jan)


def test_le_a_iso_e_o_codigo_do_disco(tmp_path):
    _us, ru, *_ = _discos()
    (tmp_path / "ru.iso").write_bytes(ru)
    with open(tmp_path / "ru.iso", "rb") as f:
        r = T.registros(f)
    assert set(r) == {"/PSP_GAME/PARAM.SFO", "/PSP_GAME/USRDIR/data/level.bin",
                      "/PSP_GAME/USRDIR/data/English/game.bin", "/PSP_GAME/USRDIR/data/font.fnt"}
    assert T.codigo_disco(tmp_path / "ru.iso") == "UCUS98653"


def test_disco_original_aplica_exato(tmp_path):
    us, _ru, pt, *_ = _discos()
    (tmp_path / "us.iso").write_bytes(us)
    (tmp_path / "p.xdelta").write_bytes(_patch_xdelta(us, pt, (0, 16 * S)))  # copia o começo (igual nos dois)
    r = T.aplicar(tmp_path / "us.iso", tmp_path / "p.xdelta", tmp_path / "pt.iso", tmp_path / "w", log=lambda s: 0)
    assert r["modo"] == "exato" and (tmp_path / "pt.iso").read_bytes() == pt


def test_disco_de_outra_versao_recebe_so_os_arquivos_traduzidos(tmp_path):
    us, ru, pt, texto_pt, fonte_pt = _discos()
    (tmp_path / "ru.iso").write_bytes(ru)
    # o patch copia do disco US um pedaço que cai dentro da fonte (lá o russo é igual ao US)
    with open(tmp_path / "pt-ref.iso", "wb") as f:
        f.write(pt)
    with open(tmp_path / "pt-ref.iso", "rb") as f:
        _p, lba_fonte, _t = T.registros(f)["/PSP_GAME/USRDIR/data/font.fnt"]
    (tmp_path / "p.xdelta").write_bytes(_patch_xdelta(us, pt, (lba_fonte * S + 4000, lba_fonte * S + 4100)))
    log = []
    r = T.aplicar(tmp_path / "ru.iso", tmp_path / "p.xdelta", tmp_path / "saida.iso", tmp_path / "w", log=log.append)
    assert r["modo"] == "transplante" and r["arquivos"] == 2
    with open(tmp_path / "saida.iso", "rb") as f:
        reg = T.registros(f)

        def ler(n):
            _p, lba, tam = reg[n]
            f.seek(lba * S)
            return f.read(tam)
        assert ler("/PSP_GAME/USRDIR/data/English/game.bin") == texto_pt  # maior: foi para o fim do disco
        assert ler("/PSP_GAME/USRDIR/data/font.fnt") == fonte_pt  # o pedaço copiado veio da fonte do usuário
        assert ler("/PSP_GAME/USRDIR/data/level.bin") == b"\x07LEVEL" * 3000  # o resto é o disco do usuário
    assert not (tmp_path / "w" / "resultado-do-patch.iso").exists()  # 1,6 GB de rascunho não fica para trás
    assert any("não conferem" in s for s in log)


def test_sem_receita_explica_e_nao_gera_nada(tmp_path):
    us, ru, pt, *_ = _discos()
    ru = ru.replace(b"UCUS98653", b"ULUS99999")
    (tmp_path / "ru.iso").write_bytes(ru)
    with open(tmp_path / "pt-ref.iso", "wb") as f:
        f.write(pt)
    (tmp_path / "p.xdelta").write_bytes(_patch_xdelta(us, pt, (24 * S, len(us) - S)))  # copia arquivos do US
    with pytest.raises(T.ErroTransplante, match="outra versão"):
        T.aplicar(tmp_path / "ru.iso", tmp_path / "p.xdelta", tmp_path / "saida.iso", tmp_path / "w",
                  log=lambda s: 0)
    assert not (tmp_path / "saida.iso").exists()
