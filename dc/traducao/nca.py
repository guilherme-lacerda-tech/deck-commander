"""Leitor de jogos de Switch (NSP -> NCA -> RomFS), em Python puro, para extrair SÓ os arquivos de texto.

Usa as chaves que o seu Ryujinx já tem (~/.config/Ryujinx/system/prod.keys); nada é baixado.
- AES-128 próprio (XTS para o cabeçalho, CTR para os dados, CTR-EX para atualizações), ECB para chaves.
- Atualização (BKTR): o RomFS virtual = jogo-base + atualização, como o Ryujinx monta. Assim o texto
  extraído é o da versão que você joga (a tradução não sobrescreve textos novos da atualização).
- Autoverificação: cabeçalhos com assinatura mágica conferida em cada etapa ("NCA3", "IVFC", "BKTR",
  tamanho do cabeçalho do RomFS). Se algo não bater, para com erro — nunca grava lixo.
Só leitura: os arquivos do jogo nunca são alterados.
"""
from __future__ import annotations

import bisect
import struct
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO


class NcaError(ValueError):
    pass


# ============================================================================ AES-128 (puro)
def _xt(a: int) -> int:
    return ((a << 1) ^ 0x1B) & 0xFF if a & 0x80 else a << 1


def _build():
    sbox = [0] * 256
    p = q = 1
    while True:
        p = p ^ (p << 1) ^ (0x1B if p & 0x80 else 0)
        p &= 0xFF
        q ^= q << 1; q ^= q << 2; q ^= q << 4; q &= 0xFF
        if q & 0x80:
            q ^= 0x09
        x = q ^ ((q << 1) | (q >> 7)) ^ ((q << 2) | (q >> 6)) ^ ((q << 3) | (q >> 5)) ^ ((q << 4) | (q >> 4))
        sbox[p] = (x ^ 0x63) & 0xFF
        if p == 1:
            break
    sbox[0] = 0x63
    inv = [0] * 256
    for i, v in enumerate(sbox):
        inv[v] = i

    def mul(a, b):
        r = 0
        while b:
            if b & 1:
                r ^= a
            a = _xt(a); b >>= 1
        return r
    te = [[0] * 256 for _ in range(4)]
    td = [[0] * 256 for _ in range(4)]
    for i in range(256):
        s = sbox[i]
        w = (mul(s, 2) << 24) | (s << 16) | (s << 8) | mul(s, 3)
        si = inv[i]
        v = (mul(si, 14) << 24) | (mul(si, 9) << 16) | (mul(si, 13) << 8) | mul(si, 11)
        for k in range(4):
            te[k][i] = ((w >> (8 * k)) | (w << (32 - 8 * k))) & 0xFFFFFFFF
            td[k][i] = ((v >> (8 * k)) | (v << (32 - 8 * k))) & 0xFFFFFFFF
    return sbox, inv, te, td, mul


SBOX, INV, TE, TD, _MUL = _build()
RCON = [1, 2, 4, 8, 16, 32, 64, 128, 27, 54]


class AES:
    def __init__(self, key: bytes):
        if len(key) != 16:
            raise NcaError("chave AES precisa de 16 bytes")
        w = list(struct.unpack(">4I", key))
        for i in range(4, 44):
            t = w[i - 1]
            if i % 4 == 0:
                t = ((t << 8) | (t >> 24)) & 0xFFFFFFFF
                t = (SBOX[t >> 24] << 24) | (SBOX[(t >> 16) & 255] << 16) | (SBOX[(t >> 8) & 255] << 8) | SBOX[t & 255]
                t ^= RCON[i // 4 - 1] << 24
            w.append(w[i - 4] ^ t)
        self.ek = w
        dk = w[40:44]
        for r in range(9, 0, -1):
            for j in range(4):
                x = w[4 * r + j]
                dk.append(TD[0][SBOX[x >> 24]] ^ TD[1][SBOX[(x >> 16) & 255]] ^ TD[2][SBOX[(x >> 8) & 255]]
                          ^ TD[3][SBOX[x & 255]])
        dk += w[0:4]
        self.dk = dk

    def encrypt(self, block: bytes) -> bytes:
        k = self.ek
        s0, s1, s2, s3 = struct.unpack(">4I", block)
        s0 ^= k[0]; s1 ^= k[1]; s2 ^= k[2]; s3 ^= k[3]
        T0, T1, T2, T3 = TE
        for r in range(1, 10):
            o = 4 * r
            t0 = T0[s0 >> 24] ^ T1[(s1 >> 16) & 255] ^ T2[(s2 >> 8) & 255] ^ T3[s3 & 255] ^ k[o]
            t1 = T0[s1 >> 24] ^ T1[(s2 >> 16) & 255] ^ T2[(s3 >> 8) & 255] ^ T3[s0 & 255] ^ k[o + 1]
            t2 = T0[s2 >> 24] ^ T1[(s3 >> 16) & 255] ^ T2[(s0 >> 8) & 255] ^ T3[s1 & 255] ^ k[o + 2]
            t3 = T0[s3 >> 24] ^ T1[(s0 >> 16) & 255] ^ T2[(s1 >> 8) & 255] ^ T3[s2 & 255] ^ k[o + 3]
            s0, s1, s2, s3 = t0, t1, t2, t3
        S = SBOX
        out = [((S[a >> 24] << 24) | (S[(b >> 16) & 255] << 16) | (S[(c >> 8) & 255] << 8) | S[d & 255]) ^ k[40 + i]
               for i, (a, b, c, d) in enumerate(((s0, s1, s2, s3), (s1, s2, s3, s0), (s2, s3, s0, s1), (s3, s0, s1, s2)))]
        return struct.pack(">4I", *out)

    def decrypt(self, block: bytes) -> bytes:
        k = self.dk
        s0, s1, s2, s3 = struct.unpack(">4I", block)
        s0 ^= k[0]; s1 ^= k[1]; s2 ^= k[2]; s3 ^= k[3]
        T0, T1, T2, T3 = TD
        for r in range(1, 10):
            o = 4 * r
            t0 = T0[s0 >> 24] ^ T1[(s3 >> 16) & 255] ^ T2[(s2 >> 8) & 255] ^ T3[s1 & 255] ^ k[o]
            t1 = T0[s1 >> 24] ^ T1[(s0 >> 16) & 255] ^ T2[(s3 >> 8) & 255] ^ T3[s2 & 255] ^ k[o + 1]
            t2 = T0[s2 >> 24] ^ T1[(s1 >> 16) & 255] ^ T2[(s0 >> 8) & 255] ^ T3[s3 & 255] ^ k[o + 2]
            t3 = T0[s3 >> 24] ^ T1[(s2 >> 16) & 255] ^ T2[(s1 >> 8) & 255] ^ T3[s0 & 255] ^ k[o + 3]
            s0, s1, s2, s3 = t0, t1, t2, t3
        I = INV
        out = [((I[a >> 24] << 24) | (I[(b >> 16) & 255] << 16) | (I[(c >> 8) & 255] << 8) | I[d & 255]) ^ k[40 + i]
               for i, (a, b, c, d) in enumerate(((s0, s3, s2, s1), (s1, s0, s3, s2), (s2, s1, s0, s3), (s3, s2, s1, s0)))]
        return struct.pack(">4I", *out)

    def ecb_decrypt(self, data: bytes) -> bytes:
        return b"".join(self.decrypt(data[i:i + 16]) for i in range(0, len(data), 16))

    def ctr(self, data: bytes, upper: bytes, offset: int) -> bytes:
        """AES-CTR do Switch: contador = upper(8 bytes) || (offset/16 big-endian). offset alinhado a 16."""
        if not data:
            return b""
        blk = offset >> 4
        enc = self.encrypt
        ks = b"".join(enc(upper + struct.pack(">Q", blk + i)) for i in range((len(data) + 15) // 16))[:len(data)]
        return (int.from_bytes(data, "big") ^ int.from_bytes(ks, "big")).to_bytes(len(data), "big")


def xts_decrypt(k1: AES, k2: AES, data: bytes, sector: int, sector_size: int = 0x200) -> bytes:
    """AES-XTS da Nintendo (número do setor em big-endian no tweak)."""
    out = bytearray()
    for s in range(0, len(data), sector_size):
        tweak = int.from_bytes(k2.encrypt(sector.to_bytes(16, "big")), "little")
        for i in range(s, min(s + sector_size, len(data)), 16):
            t = tweak.to_bytes(16, "little")
            x = bytes(a ^ b for a, b in zip(data[i:i + 16], t))
            out += bytes(a ^ b for a, b in zip(k1.decrypt(x), t))
            tweak <<= 1
            if tweak >> 128:
                tweak = (tweak ^ 0x87) & ((1 << 128) - 1)
        sector += 1
    return bytes(out)


# ============================================================================ chaves
def load_keys(path: Path) -> dict[str, bytes]:
    keys = {}
    for line in Path(path).read_text("utf-8", "replace").splitlines():
        if "=" in line:
            k, v = (x.strip() for x in line.split("=", 1))
            try:
                keys[k] = bytes.fromhex(v)
            except ValueError:
                pass
    return keys


# ============================================================================ PFS0 (NSP)
@dataclass
class PfsEntry:
    name: str
    offset: int
    size: int


def read_pfs0(f: BinaryIO, base: int = 0) -> list[PfsEntry]:
    f.seek(base)
    h = f.read(16)
    if h[:4] != b"PFS0":
        raise NcaError("não é NSP/PFS0")
    n, st = struct.unpack_from("<II", h, 4)
    if n > 10000 or st > 1 << 20:
        raise NcaError("PFS0 inválido")
    ents = f.read(24 * n)
    names = f.read(st)
    data = base + 16 + 24 * n + st
    out = []
    for i in range(n):
        off, size, no, _ = struct.unpack_from("<QQII", ents, 24 * i)
        out.append(PfsEntry(names[no:names.index(b"\0", no)].decode("utf-8", "replace"), data + off, size))
    return out


# ============================================================================ NCA
@dataclass
class Section:
    index: int
    start: int          # deslocamento absoluto no arquivo NSP
    size: int
    fsh: bytes          # cabeçalho do sistema de arquivos (0x200, já decifrado)

    @property
    def fs_type(self) -> int:
        return self.fsh[2]

    @property
    def enc(self) -> int:
        return self.fsh[4]

    @property
    def upper(self) -> bytes:
        gen, secure = struct.unpack_from("<II", self.fsh, 0x140)
        return struct.pack(">II", secure, gen)

    def ivfc_romfs(self) -> tuple[int, int]:
        if self.fsh[8:12] != b"IVFC":
            raise NcaError("RomFS sem IVFC (formato não suportado)")
        off, size = struct.unpack_from("<QQ", self.fsh, 0x8 + 0x10 + 5 * 0x18)
        return off, size


class Nca:
    def __init__(self, f: BinaryIO, offset: int, size: int, keys: dict, title_key: bytes | None = None):
        self.f, self.offset, self.size = f, offset, size
        hk = keys.get("header_key")
        if not hk or len(hk) != 32:
            raise NcaError("header_key ausente no prod.keys")
        f.seek(offset)
        raw = f.read(0xC00)
        hdr = xts_decrypt(AES(hk[:16]), AES(hk[16:]), raw, 0)
        if hdr[0x200:0x204] != b"NCA3":
            raise NcaError("cabeçalho NCA não confere (chaves erradas?)")
        self.hdr = hdr
        self.content_type = hdr[0x205]
        gen = max(hdr[0x206], hdr[0x220])
        rev = gen - 1 if gen > 0 else 0
        self.title_id = struct.unpack_from("<Q", hdr, 0x210)[0]
        self.rights_id = hdr[0x230:0x240]
        if any(self.rights_id):
            if not title_key:
                raise NcaError("jogo com ticket: chave do título ausente")
            tk = keys.get(f"titlekek_{rev:02x}")
            if not tk:
                raise NcaError(f"titlekek_{rev:02x} ausente")
            self.key = AES(tk).decrypt(title_key)
        else:
            kak = keys.get(f"key_area_key_application_{rev:02x}")
            if not kak:
                raise NcaError(f"key_area_key_application_{rev:02x} ausente")
            self.key = AES(kak).ecb_decrypt(hdr[0x300:0x340])[0x20:0x30]
        self.aes = AES(self.key)
        self.sections = []
        self.sparse: dict[int, tuple] = {}
        for i in range(4):
            s, e = struct.unpack_from("<II", hdr, 0x240 + 0x10 * i)
            if e > s:
                sec = Section(i, offset + s * 0x200, (e - s) * 0x200, hdr[0x400 + 0x200 * i:0x600 + 0x200 * i])
                self.sections.append(sec)
                self._load_sparse(sec)

    def _load_sparse(self, sec: Section) -> None:
        """NCA "esparso" (jogo-base que só traz pedaços; o resto vem na atualização). A tabela diz onde
        cada trecho está no arquivo; os trechos são cifrados como no NCA completo."""
        sp = sec.fsh[0x148:0x178]
        t_off, t_size = struct.unpack_from("<QQ", sp, 0)
        if not t_size:
            return
        hdr = sp[0x10:0x20]
        phys, gen = struct.unpack_from("<QH", sp, 0x20)
        _g, secure = struct.unpack_from("<II", sec.fsh, 0x140)
        upper = struct.pack(">II", secure, gen << 16)
        self.f.seek(self.offset + phys + t_off)
        table = self.aes.ctr(self.f.read(t_size), upper, phys + t_off)
        ents = _bucket_entries(lambda o, n: table[o:o + n], 0, t_size, hdr, 0x14)
        virt = [struct.unpack_from("<q", e, 0)[0] for e in ents]
        if not virt or virt[0] != 0:
            raise NcaError("tabela esparsa inválida")
        self.sparse[sec.index] = (virt, [struct.unpack_from("<q", e, 8)[0] for e in ents],
                                  [struct.unpack_from("<i", e, 16)[0] for e in ents], self.offset + phys)

    def _raw(self, sec: Section, off: int, size: int) -> bytes:
        """Bytes cifrados da seção (resolvendo o mapa esparso, se houver)."""
        if sec.index not in self.sparse:
            self.f.seek(sec.start + off)
            return self.f.read(size)
        virt, phys, store, base = self.sparse[sec.index]
        out = bytearray()
        while size > 0:
            i = bisect.bisect_right(virt, off) - 1
            end = virt[i + 1] if i + 1 < len(virt) else off + size
            n = min(size, end - off)
            if store[i] == 0:
                self.f.seek(base + phys[i] + (off - virt[i]))
                chunk = self.f.read(n)
                if len(chunk) != n:
                    raise NcaError("trecho esparso fora do arquivo")
                out += chunk
            else:
                out += b"\0" * n  # trecho ausente no jogo-base (vem da atualização)
            off += n; size -= n
        return bytes(out)

    def romfs_section(self) -> Section:
        for s in self.sections:
            if s.fs_type == 0:
                return s
        raise NcaError("NCA sem RomFS")

    def read_plain(self, sec: Section, off: int, size: int, upper: bytes | None = None) -> bytes:
        """Lê `size` bytes do trecho (relativo à seção), decifrando com CTR."""
        a = off & ~0xF
        raw = self._raw(sec, a, (off + size - a + 15) & ~0xF)
        if sec.enc == 1:
            data = raw
        elif sec.enc in (3, 4):
            data = self.aes.ctr(raw, upper or sec.upper, sec.start - self.offset + a)
        else:
            raise NcaError(f"criptografia de seção não suportada ({sec.enc})")
        return data[off - a:off - a + size]


# ============================================================================ atualização (BKTR)
NODE = 0x4000


def _bucket_entries(read: Callable[[int, int], bytes], base: int, size: int, hdr: bytes, esize: int) -> list[bytes]:
    if hdr[:4] != b"BKTR":
        raise NcaError("tabela da atualização sem BKTR")
    count = struct.unpack_from("<i", hdr, 8)[0]
    l1 = read(base, NODE)
    _idx, nsets, _end = struct.unpack_from("<iiq", l1, 0)
    per = (NODE - 16) // esize
    if nsets <= 0 or nsets > (NODE - 16) // 8 or count > nsets * per:
        raise NcaError("tabela da atualização inconsistente")
    out = []
    for s in range(nsets):
        node = read(base + NODE * (1 + s), NODE)
        _i, cnt, _e = struct.unpack_from("<iiq", node, 0)
        if cnt < 0 or cnt > per:
            raise NcaError("nó da tabela inválido")
        out += [node[16 + esize * j:16 + esize * (j + 1)] for j in range(cnt)]
    if len(out) != count:
        raise NcaError("contagem da tabela da atualização não confere")
    return out


class PatchedRomFs:
    """Armazenamento virtual base+atualização (Indirect + AesCtrEx)."""

    def __init__(self, base: Nca | None, patch: Nca):
        self.base, self.patch = base, patch
        self.bsec = base.romfs_section() if base else None
        ps = patch.romfs_section()
        self.psec = ps
        if ps.enc != 4:  # atualização sem BKTR: o RomFS dela é completo
            self.ind = None
            return
        info = ps.fsh[0x100:0x140]
        ind_off, ind_size = struct.unpack_from("<QQ", info, 0)
        ind_hdr = info[0x10:0x20]
        ex_off, ex_size = struct.unpack_from("<QQ", info, 0x20)
        ex_hdr = info[0x30:0x40]
        self.ind = True
        plain = lambda o, n: patch.read_plain(ps, o, n)  # noqa: E731 — tabela de subseções: CTR normal
        ex = _bucket_entries(plain, ex_off, ex_size, ex_hdr, 0x10)
        self.ex_off = [struct.unpack_from("<q", e, 0)[0] for e in ex]
        self.ex_gen = [struct.unpack_from("<i", e, 12)[0] for e in ex]
        self.ex_enc = [e[8] for e in ex]
        self.ex_limit = ex_off
        ind = _bucket_entries(self._patch_read, ind_off, ind_size, ind_hdr, 0x14)
        self.virt = [struct.unpack_from("<q", e, 0)[0] for e in ind]
        self.phys = [struct.unpack_from("<q", e, 8)[0] for e in ind]
        self.store = [struct.unpack_from("<i", e, 16)[0] for e in ind]
        if not self.virt or self.virt[0] != 0 or any(s not in (0, 1) for s in self.store):
            raise NcaError("tabela de relocação inválida")
        if any(s == 0 for s in self.store) and not base:
            raise NcaError("atualização precisa do jogo-base")

    def _patch_read(self, off: int, size: int) -> bytes:
        out = bytearray()
        while size > 0:
            if off >= self.ex_limit:
                out += self.patch.read_plain(self.psec, off, size)
                break
            i = bisect.bisect_right(self.ex_off, off) - 1
            if i < 0:
                raise NcaError("trecho fora da tabela de subseções")
            end = self.ex_off[i + 1] if i + 1 < len(self.ex_off) else self.ex_limit
            n = min(size, end - off)
            gen, secure = struct.unpack_from("<II", self.psec.fsh, 0x140)
            upper = struct.pack(">II", secure, self.ex_gen[i])
            if self.ex_enc[i] == 1:  # trecho não cifrado
                self.patch.f.seek(self.psec.start + off)
                out += self.patch.f.read(n)
            else:
                out += self.patch.read_plain(self.psec, off, n, upper)
            off += n; size -= n
        return bytes(out)

    def read(self, off: int, size: int) -> bytes:
        if self.ind is None:  # atualização com RomFS completo
            return self.patch.read_plain(self.psec, off, size)
        out = bytearray()
        while size > 0:
            i = bisect.bisect_right(self.virt, off) - 1
            end = self.virt[i + 1] if i + 1 < len(self.virt) else off + size
            n = min(size, end - off)
            p = self.phys[i] + (off - self.virt[i])
            if self.store[i] == 0:
                out += self.base.read_plain(self.bsec, p, n)
            else:
                out += self._patch_read(p, n)
            off += n; size -= n
        return bytes(out)


# ============================================================================ RomFS
class RomFs:
    def __init__(self, read: Callable[[int, int], bytes], base: int):
        self.read_at = read
        self.base = base
        h = read(base, 0x50)
        vals = struct.unpack_from("<10Q", h, 0)
        if vals[0] != 0x50:
            raise NcaError("cabeçalho do RomFS não confere")
        (_hs, _dho, _dhs, dmo, dms, _fho, _fhs, fmo, fms, self.data_off) = vals
        if dms > 64 << 20 or fms > 256 << 20:
            raise NcaError("tabelas do RomFS grandes demais")
        self.dmeta = read(base + dmo, dms)
        self.fmeta = read(base + fmo, fms)

    def files(self) -> dict[str, tuple[int, int]]:
        """{caminho: (deslocamento absoluto, tamanho)}"""
        out = {}

        def walk_dir(off: int, path: str, depth: int = 0):
            if depth > 64:
                raise NcaError("RomFS com diretórios em laço")
            _par, _sib, child, fil, _h, nlen = struct.unpack_from("<IIIIII", self.dmeta, off)
            f = fil
            while f != 0xFFFFFFFF:
                _p, sib, doff, size, _hh, fl = struct.unpack_from("<IIQQII", self.fmeta, f)
                name = self.fmeta[f + 0x20:f + 0x20 + fl].decode("utf-8", "replace")
                out[f"{path}{name}"] = (self.base + self.data_off + doff, size)
                f = sib
            c = child
            while c != 0xFFFFFFFF:
                _p, sib, _c, _f, _h2, nl = struct.unpack_from("<IIIIII", self.dmeta, c)
                name = self.dmeta[c + 0x18:c + 0x18 + nl].decode("utf-8", "replace")
                walk_dir(c, f"{path}{name}/", depth + 1)
                c = sib
        walk_dir(0, "")
        return out


# ============================================================================ alto nível
def _ticket_key(f: BinaryIO, ents: list[PfsEntry]) -> bytes | None:
    for e in ents:
        if e.name.endswith(".tik"):
            f.seek(e.offset)
            t = f.read(min(e.size, 0x400))
            sig = struct.unpack_from("<I", t, 0)[0]
            body = {0x10000: 0x240, 0x10001: 0x140, 0x10002: 0x80, 0x10003: 0x240, 0x10004: 0x140, 0x10005: 0x80}.get(sig)
            if body is None:
                raise NcaError("ticket com assinatura desconhecida")
            return t[body + 0x40:body + 0x50]
    return None


def open_program(path: Path, keys: dict):
    """Abre o NSP e devolve (arquivo, NCA do programa)."""
    f = open(path, "rb")
    ents = read_pfs0(f)
    tk = _ticket_key(f, ents)
    best = None
    for e in sorted((e for e in ents if e.name.endswith(".nca") and not e.name.endswith(".cnmt.nca")),
                    key=lambda e: -e.size):
        try:
            n = Nca(f, e.offset, e.size, keys, tk)
        except NcaError:
            continue
        if n.content_type == 0 and any(s.fs_type == 0 for s in n.sections):
            best = n
            break
    if not best:
        f.close()
        if any(e.name.endswith(".ncz") for e in ents):
            raise NcaError("jogo comprimido (NCZ): descompacte com /converter <jogo> descompactar")
        raise NcaError("não achei o programa (NCA) com RomFS neste arquivo")
    return f, best


NACP_LANGS = ["AmericanEnglish", "BritishEnglish", "Japanese", "French", "German", "LatinAmericanSpanish", "Spanish",
              "Italian", "Dutch", "CanadianFrench", "Portuguese", "Russian", "Korean", "TraditionalChinese",
              "SimplifiedChinese", "BrazilianPortuguese"]


def _open_control(path: Path, keys: dict):
    f = open(path, "rb")
    ents = read_pfs0(f)
    tk = _ticket_key(f, ents)
    for e in ents:
        if e.name.endswith(".nca") and not e.name.endswith(".cnmt.nca") and e.size < 64 << 20:
            try:
                n = Nca(f, e.offset, e.size, keys, tk)
            except NcaError:
                continue
            if n.content_type == 2:
                return f, n
    f.close()
    return None, None


def game_languages(base_nsp: Path, keys: dict, update_nsp: Path | None = None) -> list[str]:
    """Idiomas que o jogo declara (control.nacp). A atualização pode acrescentar idiomas: ela tem prioridade."""
    for p in [x for x in (update_nsp, base_nsp) if x]:
        f, n = _open_control(p, keys)
        if not n:
            continue
        try:
            sec = n.romfs_section()
            if sec.enc == 4:
                continue  # controle com patch: usa o do jogo-base
            off, _ = sec.ivfc_romfs()
            r = RomFs(lambda o, k: n.read_plain(sec, o, k), off)
            files = r.files()
            if "control.nacp" not in files:
                continue
            o, size = files["control.nacp"]
            nacp = r.read_at(o, size)
            mask = struct.unpack_from("<I", nacp, 0x302C)[0]
            return [l for i, l in enumerate(NACP_LANGS) if mask >> i & 1]
        finally:
            f.close()
    raise NcaError("não achei o arquivo de controle (control.nacp)")


def open_romfs(base_nsp: Path, keys: dict, update_nsp: Path | None = None) -> tuple[RomFs, list]:
    """RomFS do jogo (com a atualização aplicada, se houver). Devolve (romfs, arquivos abertos)."""
    fb, base = open_program(base_nsp, keys)
    handles = [fb]
    if update_nsp:
        fu, patch = open_program(update_nsp, keys)
        handles.append(fu)
        storage = PatchedRomFs(base, patch)
        sec = patch.romfs_section()
        off, _size = sec.ivfc_romfs()
        return RomFs(storage.read, off), handles
    sec = base.romfs_section()
    off, _size = sec.ivfc_romfs()
    return RomFs(lambda o, n: base.read_plain(sec, o, n), off), handles
