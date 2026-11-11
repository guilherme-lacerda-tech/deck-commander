"""Falha real 11/11/2026: o Zelda TotK nunca foi traduzido — o texto dele é zstd COM o dicionário do próprio jogo
(Pack/ZsDic.pack.zs) e o leitor desistia. Agora abre com o dicionário e regrava com o MESMO dicionário."""
import pytest

zstd = pytest.importorskip("compression.zstd")

from dc.traducao import extract, nx  # noqa: E402


def test_zstd_com_dicionario_do_jogo():
    amostras = [(b"MsgStdBn texto de exemplo %d " % i) * 20 for i in range(200)]
    dic = zstd.train_dict(amostras, 4096)
    pacote = zstd.compress(nx.write_sarc(nx.Sarc("<", {"zs.zsdic": dic.dict_content}, ["zs.zsdic"], {})))
    dado = b"SARC" + b"MsgStdBn texto de exemplo 7 " * 50
    comprimido = zstd.compress(dado, zstd_dict=dic)
    nx.DICIONARIOS_ZSTD.clear()
    with pytest.raises(nx.FormatError):
        nx.unpack_layer("Mals/USen.Product.sarc.zs", comprimido)
    assert nx.registrar_dicionarios(pacote) == ["zs.zsdic"]
    corpo, tipo = nx.unpack_layer("Mals/USen.Product.sarc.zs", comprimido)
    assert corpo == dado and tipo == "zstd:zs.zsdic"
    volta = nx.pack_layer(corpo, tipo)
    assert zstd.decompress(volta, zstd_dict=dic) == dado
    with pytest.raises(Exception):
        zstd.decompress(volta)  # sem o dicionário não abre: foi gravado com ele, como o jogo espera
    nx.DICIONARIOS_ZSTD.clear()


def test_extracao_leva_o_dicionario():
    arqs = {"Pack/ZsDic.pack.zs": (0, 100), "Mals/USen.Product.142.sarc.zs": (0, 100), "Model/x.bfres.zs": (0, 9)}
    assert "Pack/ZsDic.pack.zs" in extract.text_files(arqs) and "Mals/USen.Product.142.sarc.zs" in extract.text_files(arqs)
