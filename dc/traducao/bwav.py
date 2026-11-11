"""Voz .bwav da Nintendo com áudio "Opus da Nintendo" (codec 2), mono — Zelda Tears of the Kingdom (11/11/2026).

Estrutura conferida num arquivo real (Voice/Resource/USen/EventFlowMsg/…/*.bwav): cabeçalho BWAV (0x10) + 1 canal
(0x4C) + preenchimento até 0x80 + bloco info 0x80000001 + bloco dados 0x80000004 com pacotes
[u32 BE tamanho][u32 BE final range][pacote Opus]. Usado pela dublagem: a voz PT-BR (edge-tts -> ffmpeg libopus em
Ogg) vira pacotes e é gravada no mesmo formato. docs/specs/bwav.md (1ª versão da IA local, reescrita após testes).
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass


@dataclass
class Bwav:
    taxa: int
    amostras: int
    preskip: int
    pacotes: list[bytes]


def ler(d: bytes) -> Bwav:
    if d[:4] != b"BWAV":
        raise ValueError("não é BWAV")
    canais = struct.unpack_from("<H", d, 0x0E)[0]
    codec, _pan, taxa, amostras = struct.unpack_from("<HHII", d, 0x10)
    if canais != 1 or codec != 2:
        raise ValueError(f"BWAV não suportado (canais {canais}, codec {codec}): só mono Opus")
    base = struct.unpack_from("<I", d, 0x10 + 0x30)[0]
    ident, _tam = struct.unpack_from("<II", d, base)
    if ident != 0x80000001:
        raise ValueError("bloco info do Opus ausente")
    rel_dados = struct.unpack_from("<I", d, base + 0x10)[0]
    preskip = struct.unpack_from("<I", d, base + 0x1C)[0]
    ident, tam = struct.unpack_from("<II", d, base + rel_dados)
    if ident != 0x80000004:
        raise ValueError("bloco de dados do Opus ausente")
    i, fim, pacotes = base + rel_dados + 8, base + rel_dados + 8 + tam, []
    while i + 8 <= fim:
        n = struct.unpack_from(">I", d, i)[0]
        pacotes.append(d[i + 8:i + 8 + n])
        i += 8 + n
    return Bwav(taxa, amostras, preskip, pacotes)


def gravar(b: Bwav) -> bytes:
    corpo = b"".join(struct.pack(">II", len(p), 0) + p for p in b.pacotes)
    dados = struct.pack("<II", 0x80000004, len(corpo)) + corpo
    info = struct.pack("<IIBBHIIIII", 0x80000001, 0x18, 0, 1, 0, b.taxa, 0x20, 0, 0, b.preskip)
    canal = struct.pack("<HHIII", 2, 2, b.taxa, b.amostras, b.amostras) + bytes(32) + \
        struct.pack("<IIIII", 0x80, 0x80, 1, 0xFFFFFFFF, 0) + bytes(8)
    # CRC32 de 0x80 até o fim (conferido no arquivo real); o "final range" de cada pacote vai 0 (só depuração)
    cab = b"BWAV" + struct.pack("<HHIHH", 0xFEFF, 1, zlib.crc32(info + dados), 0, 1)
    topo = cab + canal
    return topo + bytes(0x80 - len(topo)) + info + dados


def pacotes_do_ogg(ogg: bytes) -> tuple[list[bytes], int]:
    """Pacotes de áudio de um Ogg Opus (sem OpusHead/OpusTags) e o pre-skip."""
    pacotes, atual, i = [], b"", 0
    while i + 27 <= len(ogg):
        if ogg[i:i + 4] != b"OggS":
            raise ValueError("Ogg corrompido")
        nseg = ogg[i + 26]
        lacing = ogg[i + 27:i + 27 + nseg]
        j = i + 27 + nseg
        for tam in lacing:
            atual += ogg[j:j + tam]
            j += tam
            if tam < 255:  # pacote terminou (255 = continua no próximo segmento, mesmo em outra página)
                pacotes.append(atual)
                atual = b""
        i = j
    if not pacotes or not pacotes[0].startswith(b"OpusHead"):
        raise ValueError("Ogg sem OpusHead")
    preskip = struct.unpack_from("<H", pacotes[0], 10)[0]
    return [p for p in pacotes[1:] if not p.startswith(b"OpusTags")], preskip


def de_ogg(ogg: bytes, amostras: int) -> Bwav:
    pacotes, preskip = pacotes_do_ogg(ogg)
    return Bwav(48000, amostras, preskip, pacotes)
