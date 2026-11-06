"""M5 — Aplicação de traduções/patches. IPS, BPS e UPS em Python puro (sem Flips externo).

- Formato detectado pelo CONTEÚDO (assinatura), não pela extensão.
- A ROM original nunca é alterada: o resultado vai para um arquivo novo "<nome> (patch).ext".
- BPS/UPS conferem CRC32 de origem e destino; falha => nada é publicado e o patch vai para quarentena.
- XDelta (VCDIFF) e instaladores .exe: detectados e recusados com motivo (precisam de xdelta3 /
  execução no prefixo Proton — pendentes, ver relatório).
"""
from __future__ import annotations

import os
import zlib
from pathlib import Path


class PatchError(ValueError):
    pass


def detect(data: bytes) -> str:
    if data.startswith(b"PATCH"):
        return "ips"
    if data.startswith(b"BPS1"):
        return "bps"
    if data.startswith(b"UPS1"):
        return "ups"
    if data[:3] == b"\xd6\xc3\xc4":
        return "xdelta"
    if data.startswith(b"MZ"):
        return "exe"
    return "unknown"


def _crc(b: bytes) -> int:
    return zlib.crc32(b) & 0xFFFFFFFF


class _Reader:
    def __init__(self, data: bytes, pos: int = 4):
        self.d, self.p = data, pos

    def byte(self) -> int:
        if self.p >= len(self.d):
            raise PatchError("patch truncado")
        b = self.d[self.p]; self.p += 1
        return b

    def varint(self) -> int:
        data, shift = 0, 1
        while True:
            x = self.byte()
            data += (x & 0x7F) * shift
            if x & 0x80:
                return data
            shift <<= 7
            data += shift


def apply_ips(src: bytes, patch: bytes) -> bytes:
    out = bytearray(src)
    p = 5
    while True:
        if patch[p:p + 3] == b"EOF":
            p += 3
            if len(patch) - p == 3:  # extensão: truncar
                del out[int.from_bytes(patch[p:p + 3], "big"):]
            return bytes(out)
        if p + 5 > len(patch):
            raise PatchError("IPS sem EOF")
        off = int.from_bytes(patch[p:p + 3], "big"); size = int.from_bytes(patch[p + 3:p + 5], "big"); p += 5
        if size == 0:
            n = int.from_bytes(patch[p:p + 2], "big"); val = patch[p + 2]; p += 3
            chunk = bytes([val]) * n
        else:
            chunk = patch[p:p + size]; p += size
            if len(chunk) != size:
                raise PatchError("IPS truncado")
        if off + len(chunk) > len(out):
            out.extend(b"\0" * (off + len(chunk) - len(out)))
        out[off:off + len(chunk)] = chunk


def apply_bps(src: bytes, patch: bytes) -> bytes:
    if _crc(patch[:-4]) != int.from_bytes(patch[-4:], "little"):
        raise PatchError("BPS: CRC do patch inválido")
    if _crc(src) != int.from_bytes(patch[-12:-8], "little"):
        raise PatchError("BPS: a ROM não é a versão que este patch espera (CRC de origem diferente)")
    r = _Reader(patch)
    src_size, tgt_size, meta = r.varint(), r.varint(), r.varint()
    r.p += meta
    if src_size != len(src):
        raise PatchError("BPS: tamanho de origem diferente")
    out = bytearray(tgt_size)
    o = s_rel = t_rel = 0
    end = len(patch) - 12
    while r.p < end:
        d = r.varint(); cmd, n = d & 3, (d >> 2) + 1
        if cmd == 0:
            out[o:o + n] = src[o:o + n]; o += n
        elif cmd == 1:
            out[o:o + n] = patch[r.p:r.p + n]; r.p += n; o += n
        else:
            x = r.varint(); delta = -(x >> 1) if x & 1 else (x >> 1)
            if cmd == 2:
                s_rel += delta
                out[o:o + n] = src[s_rel:s_rel + n]; s_rel += n; o += n
            else:
                t_rel += delta
                for _ in range(n):
                    out[o] = out[t_rel]; o += 1; t_rel += 1
    if _crc(bytes(out)) != int.from_bytes(patch[-8:-4], "little"):
        raise PatchError("BPS: CRC do resultado não confere")
    return bytes(out)


def apply_ups(src: bytes, patch: bytes) -> bytes:
    if _crc(patch[:-4]) != int.from_bytes(patch[-4:], "little"):
        raise PatchError("UPS: CRC do patch inválido")
    if _crc(src) != int.from_bytes(patch[-12:-8], "little"):
        raise PatchError("UPS: a ROM não é a versão que este patch espera (CRC de origem diferente)")
    r = _Reader(patch)
    in_size, out_size = r.varint(), r.varint()
    if in_size != len(src):
        raise PatchError("UPS: tamanho de origem diferente")
    out = bytearray(src[:out_size].ljust(out_size, b"\0"))
    pos, end = 0, len(patch) - 12
    while r.p < end:
        pos += r.varint()
        while True:
            x = r.byte()
            if pos < out_size:
                out[pos] ^= x
            pos += 1
            if x == 0:
                break
    if _crc(bytes(out)) != int.from_bytes(patch[-8:-4], "little"):
        raise PatchError("UPS: CRC do resultado não confere")
    return bytes(out)


APPLY = {"ips": apply_ips, "bps": apply_bps, "ups": apply_ups}


def apply_file(rom: Path, patch: Path, out: Path | None = None) -> Path:
    rom, patch = Path(rom), Path(patch)
    data = patch.read_bytes()
    kind = detect(data)
    if kind in ("xdelta", "exe"):
        raise PatchError(f"formato {kind} detectado: ainda não suportado (precisa de "
                         f"{'xdelta3' if kind == 'xdelta' else 'execução no prefixo Proton'})")
    if kind not in APPLY:
        raise PatchError("arquivo não é um patch IPS/BPS/UPS")
    out = Path(out) if out else rom.with_name(f"{rom.stem} (patch){rom.suffix}")
    if out.exists():
        raise FileExistsError(out)
    result = APPLY[kind](rom.read_bytes(), data)
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_bytes(result)
    os.replace(tmp, out)
    return out
