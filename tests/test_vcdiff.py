"""XDelta (VCDIFF) sem programa de fora (pedido 14/11/2026: tradução da OAleex do God of War PSP vem em .xdelta)."""
import zlib
from pathlib import Path

import pytest

from dc import vcdiff as V


def _n(x: int) -> bytes:
    out = [x & 0x7F]
    x >>= 7
    while x:
        out.append(0x80 | (x & 0x7F))
        x >>= 7
    return bytes(reversed(out))


def _janela(seg: tuple[int, int] | None, alvo: bytes, dados: bytes, inst: bytes, ends: bytes, soma=True) -> bytes:
    wi = (V.VCD_SOURCE if seg else 0) | (V.VCD_ADLER32 if soma else 0)
    cab = bytes([wi]) + (_n(seg[0]) + _n(seg[1]) if seg else b"")
    corpo = _n(len(alvo)) + b"\0" + _n(len(dados)) + _n(len(inst)) + _n(len(ends))
    corpo += zlib.adler32(alvo).to_bytes(4, "big") if soma else b""
    corpo += dados + inst + ends
    return cab + _n(len(corpo)) + corpo


def _cop(modo: int) -> int:
    return 19 + 16 * modo  # COPY tamanho-no-fluxo, modo m


def _patch(*janelas: bytes, app: bytes = b"") -> bytes:
    return b"\xd6\xc3\xc4\x00" + (b"\x04" + _n(len(app)) + app if app else b"\x00") + b"".join(janelas)


def test_tabela_padrao_da_rfc():
    t = V.TABELA
    assert t[0] == (V.RUN, 0, 0, V.NOOP, 0, 0) and t[1] == (V.ADD, 0, 0, V.NOOP, 0, 0)
    assert t[18] == (V.ADD, 17, 0, V.NOOP, 0, 0) and t[19] == (V.COPY, 0, 0, V.NOOP, 0, 0)
    assert t[20] == (V.COPY, 4, 0, V.NOOP, 0, 0) and t[162] == (V.COPY, 18, 8, V.NOOP, 0, 0)
    assert t[163] == (V.ADD, 1, 0, V.COPY, 4, 0) and t[235] == (V.ADD, 1, 0, V.COPY, 4, 6)
    assert t[247] == (V.COPY, 4, 0, V.ADD, 1, 0) and t[255] == (V.COPY, 4, 8, V.ADD, 1, 0)


def _exemplo():
    jogo = b"ABCDEFGHIJ" * 10 + b"texto em russo!!" + b"0123456789" * 5
    # resultado: "XY" + jogo[10:30] (modo SELF) + jogo[20:30] (modo "perto": 10 depois do anterior) + "zz"x6 (RUN)
    #   + mais 6 "z" copiados de 2 bytes atrás, sobrepondo o que está sendo escrito (modo HERE)
    alvo = b"XY" + jogo[10:30] + jogo[20:30] + b"z" * 12
    dados = b"XY" + b"z"
    inst = (bytes([1]) + _n(2) + bytes([_cop(0)]) + _n(20) + bytes([_cop(2)]) + _n(10) + bytes([0]) + _n(6)
            + bytes([_cop(1)]) + _n(6))
    ends = _n(10) + _n(10) + _n(2)  # HERE: endereço = aqui - 2
    return jogo, alvo, dados, inst, ends


def test_aplica_add_copy_run_e_copia_sobreposta(tmp_path):
    jogo, alvo, dados, inst, ends = _exemplo()
    (tmp_path / "j").write_bytes(jogo)
    (tmp_path / "p").write_bytes(_patch(_janela((len(jogo), 0), alvo, dados, inst, ends), app=b"nome.iso"))
    rel = V.aplicar(tmp_path / "j", tmp_path / "p", tmp_path / "o")
    assert (tmp_path / "o").read_bytes() == alvo
    assert rel["errados"] == [] and rel["tamanho"] == len(alvo) and rel["janelas"] == 1


def test_jogo_modificado_mostra_so_os_pedacos_errados(tmp_path):
    """ISO que já veio com outra tradução: o patch aplica, e a soma de cada pedaço diz o que saiu diferente."""
    jogo, alvo, dados, inst, ends = _exemplo()
    so_add = _janela(None, b"pedaco novo", b"pedaco novo", bytes([1]) + _n(11), b"")
    (tmp_path / "p").write_bytes(_patch(so_add, _janela((len(jogo), 0), alvo, dados, inst, ends)))
    modificado = bytearray(jogo)
    modificado[15] = ord("!")  # o trecho copiado do jogo mudou
    (tmp_path / "j").write_bytes(bytes(modificado))
    rel = V.aplicar(tmp_path / "j", tmp_path / "p", tmp_path / "o")
    assert rel["errados"] == [(11, len(alvo))] and rel["bytes_errados"] == len(alvo)
    assert (tmp_path / "o").read_bytes()[:11] == b"pedaco novo"  # o pedaço que não depende do jogo saiu certo


def test_recusa_o_que_nao_e_xdelta_e_compressao(tmp_path):
    (tmp_path / "p").write_bytes(b"PATCHxxxxx")
    with pytest.raises(V.ErroVcdiff, match="não é"):
        V.aplicar(None, tmp_path / "p", tmp_path / "o")
    (tmp_path / "p").write_bytes(b"\xd6\xc3\xc4\x00\x01\x02")
    with pytest.raises(V.ErroVcdiff, match="compressão"):
        V.aplicar(None, tmp_path / "p", tmp_path / "o")


def test_patches_aceita_xdelta(tmp_path):
    """dc.patches recusava xdelta ("precisa de xdelta3"); agora aplica com o leitor próprio."""
    from dc import patches
    jogo, alvo, dados, inst, ends = _exemplo()
    (tmp_path / "jogo.iso").write_bytes(jogo)
    (tmp_path / "t.xdelta").write_bytes(_patch(_janela((len(jogo), 0), alvo, dados, inst, ends)))
    out = patches.apply_file(tmp_path / "jogo.iso", tmp_path / "t.xdelta", tmp_path / "saida.iso")
    assert out.read_bytes() == alvo


def test_patches_xdelta_em_outro_jogo_falha_sem_gravar(tmp_path):
    """Jogo que não é o que o patch pede (e sem receita): erro claro e nenhum arquivo pela metade."""
    from dc import patches
    jogo, alvo, dados, inst, ends = _exemplo()
    (tmp_path / "jogo.bin").write_bytes(jogo[:12] + b"outro jogo" + jogo[22:])
    (tmp_path / "t.xdelta").write_bytes(_patch(_janela((len(jogo), 0), alvo, dados, inst, ends)))
    with pytest.raises(patches.PatchError, match="outra versão"):
        patches.apply_file(tmp_path / "jogo.bin", tmp_path / "t.xdelta", tmp_path / "saida.bin")
    assert sorted(x.name for x in tmp_path.iterdir()) == ["jogo.bin", "t.xdelta"]


def test_patch_com_compressao_secundaria_e_desempacotado_pelo_xdelta3(tmp_path, monkeypatch):
    """Traduções do João13 para PS2 (KH Final Mix, NFS) vêm com DJW (xdelta3 -S): o xdelta3 oficial regrava o patch
    sem ela (`recode -S none`) e o leitor próprio aplica (14/11/2026)."""
    from dc import patches
    jogo, alvo, dados, inst, ends = _exemplo()
    (tmp_path / "jogo.iso").write_bytes(jogo)
    limpo = _patch(_janela((len(jogo), 0), alvo, dados, inst, ends))
    comprimido = limpo[:4] + b"\x01\x01" + limpo[5:]  # cabeçalho diz "DJW" (o conteúdo é o do fake abaixo)
    (tmp_path / "t.xdelta").write_bytes(comprimido)
    assert V.compressao_secundaria(tmp_path / "t.xdelta")
    chamadas = []

    def rodar(cmd, **k):
        chamadas.append(cmd)
        Path(cmd[-1]).write_bytes(limpo)
        return type("R", (), {"returncode": 0, "stderr": ""})()
    monkeypatch.setattr(V, "programa_xdelta3", lambda: "/bin/xdelta3")
    orig = V.recodificar
    monkeypatch.setattr(V, "recodificar", lambda p, d, programa=None, rodar_=None: orig(p, d, programa, rodar))
    out = patches.apply_file(tmp_path / "jogo.iso", tmp_path / "t.xdelta", tmp_path / "saida.iso")
    assert out.read_bytes() == alvo
    assert chamadas[0][:4] == ["/bin/xdelta3", "recode", "-S", "none"]
    assert not (tmp_path / ".dc-patch").exists()  # o patch temporário sai junto


def test_sem_xdelta3_explica_como_instalar(tmp_path, monkeypatch):
    (tmp_path / "p").write_bytes(b"\xd6\xc3\xc4\x00\x01\x01")
    monkeypatch.setattr(V, "programa_xdelta3", lambda: None)
    with pytest.raises(V.ErroVcdiff, match="pacman -S xdelta3"):
        V.recodificar(tmp_path / "p", tmp_path / "q")
