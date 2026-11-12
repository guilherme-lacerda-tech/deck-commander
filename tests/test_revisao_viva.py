"""Revisão ao vivo (pedido do usuário 11/11/2026) e o cliente da porta de depuração da Steam."""
import json
import struct

from dc import revisao_viva as RV
from dc import steam_cdp as C


def test_checagem_quebrada_vira_falha_e_nao_para_as_outras(monkeypatch):
    def quebra():
        raise OSError("sem arquivo")
    monkeypatch.setattr(RV, "CHECAGENS", [("a", quebra), ("b", lambda: (True, "ok"))])
    res = RV.rodar()
    assert res[0][1] is False and "quebrou" in res[0][2] and res[1] == ("b", True, "ok")


def test_cobre_o_que_ja_falhou():
    nomes = " ".join(n for n, _f in RV.CHECAGENS)
    for chave in ("botões de trás", "F9", "60%", "Zelda", "Castlevania", "painel do Decky", "serviços"):
        assert chave in nomes, chave


class _Sock:
    def __init__(self, dados):
        self.dados = dados

    def recv(self, n):
        out, self.dados = self.dados[:n], self.dados[n:]
        return out


def _quadro_servidor(texto: bytes, fim=True, op=1) -> bytes:
    n = len(texto)
    cab = bytes([(0x80 if fim else 0) | op])
    cab += bytes([n]) if n < 126 else bytes([126]) + struct.pack("!H", n)
    return cab + texto


def test_quadro_mascarado_e_leitura_em_pedacos():
    q = C._quadro(b"x" * 300)
    assert q[0] == 0x81 and q[1] == 0x80 | 126 and struct.unpack("!H", q[2:4])[0] == 300  # bit de máscara ligado
    msg = json.dumps({"id": 1, "result": {"result": {"value": 2}}}).encode()
    dados = _quadro_servidor(msg[:10], fim=False) + _quadro_servidor(msg[10:], op=0)  # mensagem em 2 quadros
    assert json.loads(next(C._mensagens(_Sock(dados), bytearray()))) == json.loads(msg)
