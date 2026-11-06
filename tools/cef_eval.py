#!/usr/bin/env python3
"""Diagnóstico: avalia uma expressão JS no contexto do Steam (SharedJSContext) via CEF DevTools
em 127.0.0.1:8080 (porta que o Decky já abre). Só leitura/diagnóstico.
Uso: python3 tools/cef_eval.py 'expressão JS'"""
import base64
import json
import os
import socket
import struct
import sys
import urllib.parse
import urllib.request


def ws_url(target="SharedJSContext"):
    tabs = json.load(urllib.request.urlopen("http://127.0.0.1:8080/json", timeout=5))
    return next(t["webSocketDebuggerUrl"] for t in tabs if t["title"] == target)


def ws_eval(expr, target="SharedJSContext"):
    u = urllib.parse.urlparse(ws_url(target))
    s = socket.create_connection((u.hostname, u.port), timeout=15)
    key = base64.b64encode(os.urandom(16)).decode()
    s.sendall((f"GET {u.path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\nUpgrade: websocket\r\n"
               f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
    resp = b""
    while b"\r\n\r\n" not in resp:
        resp += s.recv(4096)
    msg = json.dumps({"id": 1, "method": "Runtime.evaluate",
                      "params": {"expression": expr, "awaitPromise": True, "returnByValue": True}}).encode()
    mask = os.urandom(4)
    hdr = bytes([0x81])
    n = len(msg)
    hdr += bytes([0x80 | n]) if n < 126 else (bytes([0x80 | 126]) + struct.pack(">H", n) if n < 65536
                                                 else bytes([0x80 | 127]) + struct.pack(">Q", n))
    s.sendall(hdr + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(msg)))

    def recv_exact(k):
        buf = b""
        while len(buf) < k:
            chunk = s.recv(k - len(buf))
            if not chunk:
                raise ConnectionError("fechado")
            buf += chunk
        return buf
    while True:
        b1, b2 = recv_exact(2)
        ln = b2 & 0x7F
        if ln == 126:
            ln = struct.unpack(">H", recv_exact(2))[0]
        elif ln == 127:
            ln = struct.unpack(">Q", recv_exact(8))[0]
        data = json.loads(recv_exact(ln))
        if data.get("id") == 1:
            s.close()
            r = data.get("result", {})
            return r.get("result", {}).get("value", r)


if __name__ == "__main__":
    print(json.dumps(ws_eval(sys.argv[1]), ensure_ascii=False, indent=1))
