"""Leitura (somente leitura) de VDF do Steam — base para S3/S4 e M2.6.

- shortcuts.vdf: VDF binário (0x00 mapa, 0x01 string, 0x02 int32, 0x07 uint64, 0x08 fim).
- localconfig.vdf: VDF texto ("chave" "valor" / "chave" { ... }).
- shortcut_appid(): fórmula usada pelo SRM para o AppID de atalho (crc32(exe+nome) | 0x80000000).
  Correção F2: o ID depende do NOME e do ALVO — renomear ou trocar .cue por .m3u muda o ID.
  O spike S4 confirma no Deck se o playtime de atalhos é indexado por esse ID.
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path


class VdfError(ValueError):
    pass


def load_binary(data: bytes) -> dict:
    pos = 0

    def cstr() -> str:
        nonlocal pos
        end = data.index(b"\x00", pos)
        s = data[pos:end].decode("utf-8", "replace")
        pos = end + 1
        return s

    def parse_map() -> dict:
        nonlocal pos
        out: dict = {}
        while True:
            if pos >= len(data):
                raise VdfError("fim inesperado")
            t = data[pos]; pos += 1
            if t == 0x08:
                return out
            key = cstr()
            if t == 0x00:
                out[key] = parse_map()
            elif t == 0x01:
                out[key] = cstr()
            elif t == 0x02:
                out[key] = struct.unpack_from("<i", data, pos)[0]; pos += 4
            elif t == 0x03:
                out[key] = struct.unpack_from("<f", data, pos)[0]; pos += 4
            elif t == 0x07:
                out[key] = struct.unpack_from("<Q", data, pos)[0]; pos += 8
            else:
                raise VdfError(f"tipo desconhecido 0x{t:02x} em {pos - 1}")

    try:
        return parse_map()
    except (IndexError, ValueError, struct.error) as e:
        raise VdfError(str(e)) from e


def dump_binary(obj: dict) -> bytes:
    """Usado só em testes/fixtures (o projeto não escreve shortcuts.vdf — SRM é o dono)."""
    out = bytearray()
    for k, v in obj.items():
        kb = k.encode() + b"\x00"
        if isinstance(v, dict):
            out += b"\x00" + kb + dump_binary(v)
        elif isinstance(v, str):
            out += b"\x01" + kb + v.encode() + b"\x00"
        elif isinstance(v, int):
            out += b"\x02" + kb + struct.pack("<i", v)
        else:
            raise TypeError(type(v))
    return bytes(out) + b"\x08"


def load_text(text: str) -> dict:
    tokens: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
        elif text.startswith("//", i):
            i = text.find("\n", i) if "\n" in text[i:] else n
        elif c in "{}":
            tokens.append(c); i += 1
        elif c == '"':
            j, buf = i + 1, []
            while j < n and text[j] != '"':
                if text[j] == "\\" and j + 1 < n:
                    buf.append({"n": "\n", "t": "\t"}.get(text[j + 1], text[j + 1])); j += 2
                else:
                    buf.append(text[j]); j += 1
            tokens.append("\x00" + "".join(buf)); i = j + 1
        else:
            j = i
            while j < n and text[j] not in ' \t\r\n{}"':
                j += 1
            tokens.append("\x00" + text[i:j]); i = j
    pos = 0

    def parse() -> dict:
        nonlocal pos
        out: dict = {}
        while pos < len(tokens):
            t = tokens[pos]
            if t == "}":
                pos += 1
                return out
            key = t[1:]; pos += 1
            if pos >= len(tokens):
                raise VdfError("valor ausente")
            if tokens[pos] == "{":
                pos += 1
                out[key] = parse()
            else:
                out[key] = tokens[pos][1:]; pos += 1
        return out

    return parse()


def shortcut_appid(exe: str, name: str) -> int:
    return (zlib.crc32((exe + name).encode("utf-8")) & 0xFFFFFFFF) | 0x80000000


def shortcut_gameid64(appid32: int) -> int:
    return (appid32 << 32) | 0x02000000


def read_shortcuts(path: Path) -> list[dict]:
    root = load_binary(Path(path).read_bytes())
    sc = root.get("shortcuts", {})
    return [sc[k] for k in sorted(sc, key=lambda x: int(x) if x.isdigit() else 0)]
