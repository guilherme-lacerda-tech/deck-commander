"""Pergunta coisas à Steam AO VIVO pela porta de depuração (127.0.0.1:8080, a mesma que o Decky usa), só com a
biblioteca padrão. Serve para a revisão ao vivo (dc.revisao_viva) conferir o que a Steam está usando de verdade —
ex.: qual layout de controle está escolhido em cada jogo — e não só o que está gravado em arquivo.

Rascunho da IA local (qwen2.5-coder:7b) corrigido: faltava o bit de máscara no tamanho, "desmascarava" as respostas
do servidor com bytes inventados, supunha resposta inteira em 1 KB e comparava o JSON pelo texto.
"""
from __future__ import annotations

import base64
import json
import os
import socket
import struct
import urllib.parse
import urllib.request

PORTA = 8080


def paginas(porta: int = PORTA) -> dict[str, str]:
    """título -> websocket de cada página da interface da Steam."""
    with urllib.request.urlopen(f"http://127.0.0.1:{porta}/json", timeout=5) as r:
        return {t["title"]: t["webSocketDebuggerUrl"] for t in json.load(r)}


def _quadro(dados: bytes) -> bytes:
    mascara = os.urandom(4)
    n = len(dados)
    cab = bytes([0x81])  # FIN + texto
    if n < 126:
        cab += bytes([0x80 | n])
    elif n < 65536:
        cab += bytes([0x80 | 126]) + struct.pack("!H", n)
    else:
        cab += bytes([0x80 | 127]) + struct.pack("!Q", n)
    return cab + mascara + bytes(b ^ mascara[i % 4] for i, b in enumerate(dados))


def _ler(sock: socket.socket, n: int, buf: bytearray) -> bytes:
    while len(buf) < n:
        parte = sock.recv(65536)
        if not parte:
            raise ConnectionError("a Steam fechou a conexão")
        buf += parte
    out = bytes(buf[:n])
    del buf[:n]
    return out


def _mensagens(sock: socket.socket, buf: bytearray):
    """Gera as mensagens de texto inteiras (junta quadros de continuação)."""
    partes = b""
    while True:
        b0, b1 = _ler(sock, 2, buf)
        n = b1 & 0x7F
        if n == 126:
            n = struct.unpack("!H", _ler(sock, 2, buf))[0]
        elif n == 127:
            n = struct.unpack("!Q", _ler(sock, 8, buf))[0]
        mascara = _ler(sock, 4, buf) if b1 & 0x80 else None
        dados = _ler(sock, n, buf)
        if mascara:
            dados = bytes(b ^ mascara[i % 4] for i, b in enumerate(dados))
        op = b0 & 0x0F
        if op == 8:
            raise ConnectionError("a Steam fechou a conexão")
        if op in (0, 1):
            partes += dados
            if b0 & 0x80:
                yield partes.decode("utf-8", "replace")
                partes = b""


def avaliar(ws_url: str, expressao: str, timeout: float = 10) -> object:
    """Roda `expressao` (JavaScript) naquela página e devolve o valor (objetos voltam como JSON)."""
    u = urllib.parse.urlparse(ws_url)
    sock = socket.create_connection((u.hostname, u.port or 80), timeout=timeout)
    try:
        chave = base64.b64encode(os.urandom(16)).decode()
        sock.sendall((f"GET {u.path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\nUpgrade: websocket\r\n"
                      f"Connection: Upgrade\r\nSec-WebSocket-Key: {chave}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        buf = bytearray()
        while b"\r\n\r\n" not in buf:
            parte = sock.recv(4096)
            if not parte:
                raise ConnectionError("sem resposta da Steam")
            buf += parte
        cab, _, resto = bytes(buf).partition(b"\r\n\r\n")
        if b" 101 " not in cab.split(b"\r\n")[0]:
            raise ConnectionError("a Steam recusou a conexão: " + cab.split(b"\r\n")[0].decode("latin-1"))
        buf = bytearray(resto)
        sock.sendall(_quadro(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {
            "expression": expressao, "returnByValue": True, "awaitPromise": True}}).encode()))
        for texto in _mensagens(sock, buf):
            msg = json.loads(texto)
            if msg.get("id") != 1:
                continue
            r = msg.get("result", {})
            if "exceptionDetails" in r:
                raise RuntimeError(r["exceptionDetails"].get("exception", {}).get("description")
                                   or r["exceptionDetails"].get("text", "erro no JavaScript"))
            return r.get("result", {}).get("value")
    finally:
        sock.close()
    return None


def steam(expressao: str, timeout: float = 10) -> object:
    """Avalia no SharedJSContext (onde ficam SteamClient, appStore… — o mesmo contexto do Decky)."""
    return avaliar(paginas()["SharedJSContext"], expressao, timeout)
