"""Voz .bwav da Nintendo com áudio "Opus da Nintendo" (codec 2), mono — Zelda Tears of the Kingdom (11/11/2026).

Estrutura conferida num arquivo real (Voice/Resource/USen/EventFlowMsg/…/*.bwav): cabeçalho BWAV (0x10) + 1 canal
(0x4C) + preenchimento até 0x80 + bloco info 0x80000001 + bloco dados 0x80000004 com pacotes
[u32 BE tamanho][u32 BE final range][pacote Opus]. Usado pela dublagem: a voz PT-BR (edge-tts -> ffmpeg libopus em
Ogg) vira pacotes e é gravada no mesmo formato. docs/specs/bwav.md (1ª versão da IA local, reescrita após testes).
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field


@dataclass
class Bwav:
    taxa: int
    amostras: int
    preskip: int
    pacotes: list[bytes]                                   # canal 0 (mono, ou esquerdo)
    outros: list[list[bytes]] = field(default_factory=list)  # demais canais (estéreo: o direito)


def _alinha(n: int, a: int = 0x40) -> int:
    return (n + a - 1) // a * a


def _fluxo(d: bytes, base: int) -> tuple[int, list[bytes]]:
    """(pré-salto, pacotes) do fluxo Opus da Nintendo que começa em `base`."""
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
    return preskip, pacotes


def ler(d: bytes) -> Bwav:
    if d[:4] != b"BWAV":
        raise ValueError("não é BWAV")
    canais = struct.unpack_from("<H", d, 0x0E)[0]
    fluxos = []
    for c in range(canais):
        codec, _pan, taxa, amostras = struct.unpack_from("<HHII", d, 0x10 + c * 0x4C)
        if codec != 2:
            raise ValueError(f"BWAV não suportado (codec {codec}): só Opus")
        fluxos.append(_fluxo(d, struct.unpack_from("<I", d, 0x10 + c * 0x4C + 0x30)[0]))
    _c, _p, taxa, amostras = struct.unpack_from("<HHII", d, 0x10)
    return Bwav(taxa, amostras, fluxos[0][0], fluxos[0][1], [f[1] for f in fluxos[1:]])


def gravar(b: Bwav) -> bytes:
    canais = [b.pacotes] + list(b.outros)
    pans = [2] if len(canais) == 1 else list(range(len(canais)))  # mono = centro; estéreo = 0 esq., 1 dir.
    fluxos = []
    for pac in canais:
        corpo = b"".join(struct.pack(">II", len(p), 0) + p for p in pac)
        info = struct.pack("<IIBBHIIIII", 0x80000001, 0x18, 0, 1, 0, b.taxa, 0x20, 0, 0, b.preskip)
        fluxos.append(info + struct.pack("<II", 0x80000004, len(corpo)) + corpo)
    inicio = _alinha(0x10 + 0x4C * len(canais))
    offs, pos = [], inicio
    for k, f in enumerate(fluxos):  # cada fluxo começa alinhado a 0x40 (conferido no arquivo estéreo real)
        offs.append(pos)
        pos = _alinha(pos + len(f)) if k < len(fluxos) - 1 else pos + len(f)
    infos = b"".join(struct.pack("<HHIII", 2, pans[k], b.taxa, b.amostras, b.amostras) + bytes(32)
                     + struct.pack("<IIIII", offs[k], offs[k], 1, 0xFFFFFFFF, 0) + bytes(8) for k in range(len(canais)))
    corpo = bytearray(pos - inicio)
    for k, f in enumerate(fluxos):
        corpo[offs[k] - inicio:offs[k] - inicio + len(f)] = f
    # CRC32 do início dos dados até o fim (conferido nos arquivos reais); "final range" dos pacotes vai 0
    cab = b"BWAV" + struct.pack("<HHIHH", 0xFEFF, 1, zlib.crc32(bytes(corpo)), 0, len(canais))
    topo = cab + infos
    return topo + bytes(inicio - len(topo)) + bytes(corpo)


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


def _crc_ogg(dados: bytes) -> int:
    """CRC do Ogg: polinômio 0x04C11DB7, sem reflexão, começa em 0."""
    crc = 0
    for b in dados:
        crc ^= b << 24
        for _ in range(8):
            crc = ((crc << 1) ^ 0x04C11DB7) if crc & 0x80000000 else (crc << 1)
            crc &= 0xFFFFFFFF
    return crc


def para_ogg(b: Bwav) -> bytes:
    """Ogg Opus com os pacotes do BWAV (para o ffmpeg tocar/conferir: o original e a voz gerada)."""
    def pagina(pacotes: list[bytes], granulo: int, seq: int, tipo: int) -> bytes:
        lacing, corpo = b"", b""
        for p in pacotes:
            lacing += b"\xff" * (len(p) // 255) + bytes([len(p) % 255])
            corpo += p
        cab = b"OggS" + bytes([0, tipo]) + struct.pack("<qII", granulo, 0x44434F50, seq) + b"\x00\x00\x00\x00" \
            + bytes([len(lacing)]) + lacing
        pag = cab + corpo
        return pag[:22] + struct.pack("<I", _crc_ogg(pag)) + pag[26:]
    head = b"OpusHead" + struct.pack("<BBHIhB", 1, 1, b.preskip, b.taxa, 0, 0)
    tags = b"OpusTags" + struct.pack("<I", 12) + b"deck-command" + struct.pack("<I", 0)
    out = pagina([head], 0, 0, 2) + pagina([tags], 0, 1, 0)
    pos, seq, lote = 0, 2, []
    for k, p in enumerate(b.pacotes):
        lote.append(p)
        pos += 960  # quadros de 20 ms (o que o jogo e o ffmpeg usam)
        if len(lote) == 50 or k == len(b.pacotes) - 1:
            fim = k == len(b.pacotes) - 1
            out += pagina(lote, b.amostras + b.preskip if fim else pos, seq, 4 if fim else 0)
            seq += 1
            lote = []
    return out


def de_ogg(ogg: bytes, amostras: int) -> Bwav:
    pacotes, preskip = pacotes_do_ogg(ogg)
    return Bwav(48000, amostras, preskip, pacotes)
