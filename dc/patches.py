"""M5 — Aplicação de traduções/patches. IPS, BPS e UPS em Python puro (sem Flips externo).

- Formato detectado pelo CONTEÚDO (assinatura), não pela extensão.
- A ROM original nunca é alterada: o resultado vai para um arquivo novo "<nome> (patch).ext".
- BPS/UPS conferem CRC32 de origem e destino; falha => nada é publicado e o patch vai para quarentena.
- XDelta (VCDIFF): aplicado pelo leitor próprio (dc/vcdiff.py, 14/11/2026), em pedaços, sem carregar o jogo na memória;
  a soma de cada pedaço confere o resultado. Disco de outra versão: só com receita (dc/traducao/transplante.py).
- PPF 1/2/3 (comum em tradução de PS1/PS2): aplicado em cópia do disco, sem carregar tudo na memória; o bloco de
  conferência do PPF 2/3 recusa disco de outra versão (14/11/2026, regra "tradução da comunidade primeiro").
- Instaladores .exe: detectados e recusados com motivo (precisam de execução no prefixo Proton).
"""
from __future__ import annotations

import os
import zlib
from pathlib import Path


class PatchError(ValueError):
    pass


ULTIMO_XDELTA: dict = {}  # relatório do último .xdelta aplicado (modo exato / sem_conferencia / transplante)


def detect(data: bytes) -> str:
    if data.startswith(b"PATCH"):
        return "ips"
    if data.startswith(b"BPS1"):
        return "bps"
    if data.startswith(b"UPS1"):
        return "ups"
    if data[:3] == b"\xd6\xc3\xc4":
        return "xdelta"
    if data[:3] == b"PPF" and data[3:5] in (b"10", b"20", b"30"):
        return "ppf"
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


def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        x, n = n & 0x7F, n >> 7
        if n == 0:
            out.append(0x80 | x)
            return bytes(out)
        out.append(x)
        n -= 1


def create_bps(src: bytes, tgt: bytes) -> bytes:
    """Gera um patch BPS (SourceRead onde é igual, TargetRead onde muda). Simples, sempre válido."""
    out = bytearray(b"BPS1" + _varint(len(src)) + _varint(len(tgt)) + _varint(0))
    o, n = 0, len(tgt)
    while o < n:
        same = o < len(src) and src[o] == tgt[o]
        e = o
        while e < n and ((e < len(src) and src[e] == tgt[e]) == same):
            e += 1
        if same:
            out += _varint(((e - o - 1) << 2) | 0)
        else:
            out += _varint(((e - o - 1) << 2) | 1) + tgt[o:e]
        o = e
    out += _crc(src).to_bytes(4, "little") + _crc(tgt).to_bytes(4, "little")
    out += _crc(bytes(out)).to_bytes(4, "little")
    return bytes(out)


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


def _ppf_registros(data: bytes) -> tuple[int, list[tuple[int, bytes]], bytes | None, int]:
    """(versão, [(posição, bytes)], bloco de conferência ou None, posição do bloco no disco)."""
    ver = int(data[3:4])
    fim = len(data)
    diz = data.rfind(b"@BEGIN_FILE_ID.DIZ")
    if diz > 0:
        fim = diz
    bloco, pos_bloco, desfazer, larg = None, 0x9320, False, 4
    if ver == 1:
        i = 56
    elif ver == 2:
        bloco, i = data[60:1084], 1084
    else:
        tipo, conf, desfazer = data[56], data[57], data[58]
        pos_bloco = 0x80A0 if tipo == 1 else 0x9320
        if conf:
            bloco, i = data[60:1084], 1084
        else:
            i = 60
        larg = 8
    regs = []
    while i < fim:
        if i + larg + 1 > fim:
            raise PatchError("PPF cortado no meio")
        pos = int.from_bytes(data[i:i + larg], "little")
        n = data[i + larg]
        i += larg + 1
        regs.append((pos, data[i:i + n]))
        i += n * (2 if desfazer else 1)
    return ver, regs, bloco, pos_bloco


def _apply_ppf(rom: Path, patch: Path, out: Path | None) -> Path:
    import shutil
    data = Path(patch).read_bytes()
    _ver, regs, bloco, pos_bloco = _ppf_registros(data)
    if bloco:
        with open(rom, "rb") as f:
            f.seek(pos_bloco)
            if f.read(1024) != bloco:
                raise PatchError("o patch PPF é para outra versão deste disco (o bloco de conferência não bate)")
    out = Path(out) if out else rom.with_name(f"{rom.stem} (patch){rom.suffix}")
    if out.exists():
        raise FileExistsError(out)
    tmp = out.with_name(out.name + ".tmp")
    shutil.copyfile(rom, tmp)
    with open(tmp, "r+b") as f:
        for pos, b in regs:
            f.seek(pos)
            f.write(b)
    os.replace(tmp, out)
    return out


def _apply_xdelta(rom: Path, patch: Path, out: Path | None) -> Path:
    """Disco original: resultado exato. Outra versão do disco (ex.: ISO já modificada por outra tradução) com receita
    em dc/traducao/transplante.py: leva só os arquivos traduzidos para o disco do usuário. Senão: falha, nada gravado."""
    from . import vcdiff
    from .traducao import transplante
    out = Path(out) if out else rom.with_name(f"{rom.stem} (patch){rom.suffix}")
    if out.exists():
        raise FileExistsError(out)
    trabalho = out.parent / ".dc-patch"
    recodificado = None
    try:
        if vcdiff.compressao_secundaria(Path(patch)):  # DJW/LZMA do xdelta3: desempacota antes (vcdiff.recodificar)
            trabalho.mkdir(exist_ok=True)
            recodificado = vcdiff.recodificar(Path(patch), trabalho / "patch-sem-compressao.xdelta")
            patch = recodificado
        ULTIMO_XDELTA.clear()
        ULTIMO_XDELTA.update(transplante.aplicar(rom, patch, out, trabalho, log=lambda s: None))
    except (vcdiff.ErroVcdiff, transplante.ErroTransplante) as e:
        raise PatchError(f"xdelta: {e}") from e
    finally:
        if recodificado:
            recodificado.unlink(missing_ok=True)
        try:
            trabalho.rmdir()
        except OSError:
            pass
    return out


def apply_file(rom: Path, patch: Path, out: Path | None = None) -> Path:
    rom, patch = Path(rom), Path(patch)
    with open(patch, "rb") as f:
        data = f.read(8)
    if detect(data) == "xdelta":
        return _apply_xdelta(rom, patch, out)
    if detect(data) == "ppf":
        return _apply_ppf(rom, patch, out)
    data = patch.read_bytes()
    kind = detect(data)
    if kind == "exe":
        raise PatchError("formato exe detectado: ainda não suportado (precisa de execução no prefixo Proton)")
    if kind == "xdelta":
        return _apply_xdelta(rom, patch, out)
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


def create_bps_arquivos(src_path: Path, tgt_path: Path, out_path: Path, bloco: int = 1 << 16) -> Path:
    """BPS de arquivos grandes (imagem de disco de ~700 MB) sem carregar tudo na memória. Pedaços iguais viram
    "copia do original" de uma vez; só os pedaços que mudaram são comparados byte a byte. Revisão retrô 12/11/2026:
    a tradução de disco (Castlevania) só gerava a cópia inteira do jogo; o patch é o que dá para compartilhar."""
    n_src, n_tgt = os.path.getsize(src_path), os.path.getsize(tgt_path)
    if n_src != n_tgt:  # disco traduzido sempre tem o mesmo tamanho; outro caso usa o gerador comum
        out = create_bps(Path(src_path).read_bytes(), Path(tgt_path).read_bytes())
        Path(out_path).write_bytes(out)
        return Path(out_path)
    out = bytearray(b"BPS1" + _varint(n_src) + _varint(n_tgt) + _varint(0))
    crc_s = crc_t = 0
    tipo, tam, dados = None, 0, bytearray()  # trecho em andamento: 0 = igual ao original, 1 = dados novos

    def fecha():
        nonlocal tipo, tam, dados
        if tipo == 0:
            out.extend(_varint(((tam - 1) << 2) | 0))
        elif tipo == 1:
            out.extend(_varint(((tam - 1) << 2) | 1)); out.extend(dados)
        tipo, tam, dados = None, 0, bytearray()

    def soma(t, n, pedaco=b""):
        nonlocal tipo, tam
        if t != tipo:
            fecha(); tipo = t
        tam += n
        if t == 1:
            dados.extend(pedaco)

    with open(src_path, "rb") as fs, open(tgt_path, "rb") as ft:
        while True:
            a, b = fs.read(bloco), ft.read(bloco)
            if not b:
                break
            crc_s, crc_t = zlib.crc32(a, crc_s), zlib.crc32(b, crc_t)
            if a == b:
                soma(0, len(b))
                continue
            i = 0
            while i < len(b):
                igual = a[i] == b[i]
                j = i
                while j < len(b) and (a[j] == b[j]) == igual:
                    j += 1
                soma(0 if igual else 1, j - i, b"" if igual else b[i:j])
                i = j
    fecha()
    out += (crc_s & 0xFFFFFFFF).to_bytes(4, "little") + (crc_t & 0xFFFFFFFF).to_bytes(4, "little")
    out += _crc(bytes(out)).to_bytes(4, "little")
    Path(out_path).write_bytes(bytes(out))
    return Path(out_path)
