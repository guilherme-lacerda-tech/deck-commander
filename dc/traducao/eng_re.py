"""RE Engine (Capcom): textos dos arquivos .msg.<versão> ("GMSG"), soltos no RomFS ou dentro dos .pak ("KPKA").

Formato do .msg (reconstruído das ferramentas públicas REMSG_Converter e mhrice; NÃO conferido com arquivo real):
    0   versão u32 | "GMSG" | offset do cabeçalho u64 (=16)
    16  qtd de entradas u32 | qtd de atributos u32 | qtd de idiomas u32 | enchimento até 8
    32  offset do bloco de dados u64
        [offset de um u64 desconhecido — só nas versões cifradas (> 12)]
        offset da lista de idiomas u64 | offset dos tipos de atributo u64 | offset dos nomes de atributo u64
        offset de cada entrada u64 × qtd
    entrada: GUID (16) | u32 (crc/índice) | u32 (hash do nome) | ponteiro do nome u64 | ponteiro dos atributos u64
             | ponteiro do texto u64 × qtd de idiomas
    bloco de dados: do offset até o fim do arquivo; strings UTF-16LE terminadas em 0. Os ponteiros são
    ABSOLUTOS no arquivo e caem dentro desse bloco.
Como a disposição do cabeçalho varia entre versões e eu não tenho um arquivo real para conferir, a leitura
testa as disposições possíveis (com/sem o u64 desconhecido, com/sem nomes de atributo) e só aceita a que fecha
(cada tabela começa exatamente onde a anterior termina). Se nenhuma fecha → MotorError, nada é gravado.

Cifra do bloco de dados (versões > 12), chave fixa de 16 bytes, XOR encadeado com o byte CIFRADO anterior:
    dec[i] = enc[i] ^ enc[i-1] ^ KEY[i & 15]      (enc[-1] = 0, i contado a partir do início do bloco)
    enc[i] = dec[i] ^ enc[i-1] ^ KEY[i & 15]
É a direção usada pelas duas ferramentas (o "prev" guarda o byte lido, ainda cifrado). Conferência extra: depois
de decifrar, todo ponteiro precisa cair no início de uma string (byte anterior = fim de string), senão erro.

Regravação: em vez de remontar o bloco inteiro, as frases novas vão ANEXADAS no fim do bloco e só os ponteiros
do inglês mudam. Assim nomes, atributos e os outros idiomas ficam byte a byte iguais (não preciso saber onde
estão todos os ponteiros de cada versão — o que eu não conseguiria provar sem arquivo real).

.pak ("KPKA"): leio o índice (v4: 48 bytes por entrada; v2: 24 bytes) e entradas sem compressão ou deflate.
zstd não existe no Deck → se só houver texto em zstd, MotorError pedindo o descompressor (como o Oodle no PC).
Para GRAVAR, gero um pak de patch novo "re_chunk_000.pak.patch_<n>.pak" sem compressão, com o mesmo hash de
caminho da entrada original. Por que não o .msg solto em natives/...: (1) os nomes dentro do pak são só hashes,
não sei o caminho; (2) o RE Engine só lê arquivo solto com mod loader (REFramework/Fluffy no PC), coisa que o
Switch não tem. O motor abre os patch_001, 002... em sequência, então o nosso usa o próximo número livre.
"""
from __future__ import annotations

import re
import struct
import zlib
from collections.abc import Callable
from dataclasses import dataclass, field

from .motores import Coleta, MotorError, Texto

NAME = "RE Engine"

MSG_MAGIC = b"GMSG"
PAK_MAGIC = b"KPKA"
KEY = bytes.fromhex("CFCEFBF8EC0A336693A91D9350395F09")
VERSOES = (12, 14, 15, 17, 20, 22, 23)
INGLES = 1      # ordem dos idiomas do RE Engine: 0 japonês, 1 inglês, 2 francês...

CODES = re.compile(r"<[^>]*>|\{[^}]*\}|\r?\n|\\[nrt]|%[-+0-9.]*[sdif]")

_MSG_NOME = re.compile(r"\.msg\.\d+$")
_PATCH = re.compile(r"^(.*\.pak)\.patch_(\d+)\.pak$")


def detect(paths: list[str]) -> bool:
    for p in paths:
        low = p.lower()
        nome = low.rsplit("/", 1)[-1]
        if _MSG_NOME.search(low) or (nome.startswith("re_chunk_") and ".pak" in nome):
            return True
    return False


# ================================================================== cifra
def _keystream(n: int) -> int:
    return int.from_bytes((KEY * (n // 16 + 1))[:n], "little")


def decifrar(enc: bytes) -> bytes:
    """dec[i] = enc[i] ^ enc[i-1] ^ KEY[i&15]. Feito com inteiro grande (rápido em Python puro)."""
    n = len(enc)
    if not n:
        return b""
    e = int.from_bytes(enc, "little")
    mask = (1 << (8 * n)) - 1
    return ((e ^ ((e << 8) & mask) ^ _keystream(n)).to_bytes(n, "little"))


def cifrar(dec: bytes) -> bytes:
    """enc[i] = dec[i] ^ KEY[i&15] ^ enc[i-1] = XOR acumulado de (dec ^ KEY); acumula dobrando o passo."""
    n = len(dec)
    if not n:
        return b""
    x = int.from_bytes(dec, "little") ^ _keystream(n)
    mask = (1 << (8 * n)) - 1
    s = 8
    while s < 8 * n:
        x ^= (x << s) & mask
        s *= 2
    return x.to_bytes(n, "little")


# ================================================================== .msg
@dataclass
class Msg:
    raw: bytes
    version: int
    langs: list
    data_offset: int
    cifrado: bool
    pool: bytes                       # bloco de dados decifrado
    entradas: list                    # offset do cabeçalho de cada entrada
    textos: list                      # [ [texto por idioma] por entrada ]
    nomes: list
    extra: dict = field(default_factory=dict)

    @property
    def idx_ingles(self) -> int:
        return self.langs.index(INGLES) if INGLES in self.langs else INGLES


def _u32(b, p): return struct.unpack_from("<I", b, p)[0]
def _u64(b, p): return struct.unpack_from("<Q", b, p)[0]
def _al8(n): return (n + 7) & ~7


def _wstr(pool: bytes, base: int, ptr: int) -> str:
    i = ptr - base
    if i < 0 or i >= len(pool) or i % 2:
        raise MotorError("ponteiro de texto fora do bloco de dados")
    j = i
    while j + 1 < len(pool):
        if pool[j] == 0 and pool[j + 1] == 0:
            return pool[i:j].decode("utf-16-le", "replace")
        j += 2
    raise MotorError("texto sem terminador no bloco de dados")


def _inicio_ok(pool: bytes, base: int, ptr: int) -> bool:
    i = ptr - base
    return 0 <= i < len(pool) and i % 2 == 0 and (i == 0 or pool[i - 2:i] == b"\0\0")


def _layout(b: bytes, n: int, n_attr: int, n_lang: int) -> tuple[int, int] | None:
    """Descobre quantos offsets vêm depois do data_offset (4, 3 ou 2) testando qual fecha certinho."""
    for k, tem_unk, tem_nomes in ((4, True, True), (3, False, True), (2, False, False)):
        fim_tab = 40 + 8 * k + 8 * n
        if fim_tab > len(b):
            continue
        offs = [_u64(b, 40 + 8 * j) for j in range(k)]
        p = fim_tab
        if tem_unk:
            if offs[0] != p:
                continue
            p += 8
            offs = offs[1:]
        if offs[0] != p:                                   # idiomas logo depois
            continue
        attr = _al8(p + 4 * n_lang)
        if offs[1] != attr:                                # tipos de atributo
            continue
        fim = _al8(attr + 4 * n_attr)
        if tem_nomes:
            if offs[2] != fim:
                continue
            fim += 8 * n_attr
        if n and _u64(b, 40 + 8 * k) < fim:               # entradas só depois das tabelas
            continue
        return k, offs[0]
    return None


def read_msg(b: bytes) -> Msg:
    if len(b) < 48 or b[4:8] != MSG_MAGIC:
        raise MotorError("não é um .msg do RE Engine (falta o 'GMSG')")
    ver = _u32(b, 0)
    if ver not in VERSOES:
        raise MotorError(f".msg versão {ver}: não conheço essa versão (sei {', '.join(map(str, VERSOES))})")
    n, n_attr, n_lang = struct.unpack_from("<3I", b, 16)
    data_off = _u64(b, 32)
    if not (0 < data_off <= len(b)) or n > 1_000_000 or n_lang > 64 or n_attr > 1024:
        raise MotorError(".msg com cabeçalho inválido")
    lay = _layout(b, n, n_attr, n_lang)
    if not lay:
        raise MotorError(f".msg versão {ver}: o cabeçalho não bate com nenhuma disposição que eu conheço")
    k, lang_off = lay
    langs = list(struct.unpack_from(f"<{n_lang}I", b, lang_off))
    entradas = [_u64(b, 40 + 8 * k + 8 * j) for j in range(n)]
    for e in entradas:
        if e + 32 + 8 * n_lang > data_off:
            raise MotorError(".msg com entrada fora do cabeçalho")
    bruto = b[data_off:]
    # versões > 12 têm o bloco cifrado; confere a escolha pelos ponteiros e tenta a outra se não fechar
    tentativas = (True, False) if ver > 12 else (False, True)
    for cif in tentativas:
        pool = decifrar(bruto) if cif else bruto
        ptrs = [_u64(b, e + 24) for e in entradas] + [_u64(b, e + 32 + 8 * j) for e in entradas
                                                      for j in range(n_lang)]
        if all(_inicio_ok(pool, data_off, p) for p in ptrs):
            break
    else:
        raise MotorError(".msg: o bloco de dados não decifrou direito (ponteiros não caem em início de texto)")
    textos = [[_wstr(pool, data_off, _u64(b, e + 32 + 8 * j)) for j in range(n_lang)] for e in entradas]
    nomes = [_wstr(pool, data_off, _u64(b, e + 24)) for e in entradas]
    return Msg(b, ver, langs, data_off, cif, pool, entradas, textos, nomes)


def write_msg(m: Msg, novos: dict[int, str]) -> bytes:
    """Anexa as frases novas no fim do bloco, aponta o inglês para elas, recifra e relê para conferir."""
    head = bytearray(m.raw[:m.data_offset])
    pool = bytearray(m.pool)
    if len(pool) % 2:
        pool += b"\0"
    li = m.idx_ingles
    if li >= len(m.langs) and m.entradas:
        raise MotorError(".msg sem o idioma inglês")
    ja: dict[str, int] = {}
    for idx, s in sorted(novos.items()):
        if s not in ja:
            ja[s] = m.data_offset + len(pool)
            pool += s.encode("utf-16-le", "surrogatepass") + b"\0\0"
        struct.pack_into("<Q", head, m.entradas[idx] + 32 + 8 * li, ja[s])
    blob = bytes(head) + (cifrar(bytes(pool)) if m.cifrado else bytes(pool))
    back = read_msg(blob)
    for i, (a, b2) in enumerate(zip(m.textos, back.textos)):
        esperado = list(a)
        if i in novos:
            esperado[li] = novos[i]
        if b2 != esperado:
            raise MotorError("o .msg regravado não confere na releitura")
    if back.nomes != m.nomes or len(back.textos) != len(m.textos):
        raise MotorError("o .msg regravado não confere na releitura")
    return blob


def montar_msg(version: int, langs: list[int], entradas: list[tuple[bytes, str, list[str]]],
               attrs: list[tuple[str, int]] = (), valores: list[list] = ()) -> bytes:
    """Monta um .msg na disposição descrita acima (para testes e como documentação executável do formato).
    entradas: (guid 16 bytes, nome, [texto por idioma]); attrs: (nome, tipo) com tipo 2 = texto, 0 = inteiro."""
    n, nl, na = len(entradas), len(langs), len(attrs)
    unk = version > 12
    k = 4 if unk else 3
    p = 40 + 8 * k + 8 * n
    unk_off = p
    if unk:
        p += 8
    lang_off = p
    attr_off = _al8(lang_off + 4 * nl)
    nome_attr_off = _al8(attr_off + 4 * na)
    p = nome_attr_off + 8 * na
    heads = []
    for _ in entradas:
        heads.append(p)
        p += 32 + 8 * nl
    vals_off = []
    for _ in entradas:
        vals_off.append(p)
        p += 8 * na
    data_off = p
    pool = bytearray()

    def ptr(s: str) -> int:
        o = data_off + len(pool)
        pool.extend(s.encode("utf-16-le") + b"\0\0")
        return o
    b = bytearray(data_off)
    struct.pack_into("<I4sQ3I", b, 0, version, MSG_MAGIC, 16, n, na, nl)
    offs = ([unk_off] if unk else []) + [lang_off, attr_off, nome_attr_off]
    struct.pack_into(f"<Q{k}Q", b, 32, data_off, *offs)
    for j, h in enumerate(heads):
        struct.pack_into("<Q", b, 40 + 8 * k + 8 * j, h)
    struct.pack_into(f"<{nl}I", b, lang_off, *langs)
    struct.pack_into(f"<{na}i", b, attr_off, *[t for _n, t in attrs])
    for j, (nm, _t) in enumerate(attrs):
        struct.pack_into("<Q", b, nome_attr_off + 8 * j, ptr(nm))
    for j, (guid, nome, txts) in enumerate(entradas):
        struct.pack_into("<16sIIQQ", b, heads[j], guid, j, zlib.crc32(nome.encode()), ptr(nome), vals_off[j])
        for li, s in enumerate(txts):
            struct.pack_into("<Q", b, heads[j] + 32 + 8 * li, ptr(s))
        for a, (_nm, t) in enumerate(attrs):
            v = valores[j][a] if valores else 0
            struct.pack_into("<Q", b, vals_off[j] + 8 * a, ptr(v) if t == 2 else int(v))
    return bytes(b) + (cifrar(bytes(pool)) if version > 12 else bytes(pool))


# ================================================================== .pak ("KPKA")
@dataclass
class PakEntry:
    hash_lower: int
    hash_upper: int
    offset: int
    csize: int
    usize: int
    attributes: int = 0
    checksum: int = 0

    @property
    def compressao(self) -> int:     # 0 nenhuma, 1 deflate, 2 zstd
        return self.attributes & 0xF

    @property
    def cifrada(self) -> bool:
        return bool((self.attributes >> 16) & 0xFF)


@dataclass
class Pak:
    major: int
    minor: int
    feature: int
    entries: list


def murmur3_32(data: bytes, seed: int = 0xFFFFFFFF) -> int:
    c1, c2, h = 0xCC9E2D51, 0x1B873593, seed
    n = len(data) & ~3
    for i in range(0, n, 4):
        k = int.from_bytes(data[i:i + 4], "little")
        k = (k * c1) & 0xFFFFFFFF
        k = ((k << 15) | (k >> 17)) & 0xFFFFFFFF
        k = (k * c2) & 0xFFFFFFFF
        h ^= k
        h = ((h << 13) | (h >> 19)) & 0xFFFFFFFF
        h = (h * 5 + 0xE6546B64) & 0xFFFFFFFF
    k = 0
    tail = data[n:]
    for j in range(len(tail) - 1, -1, -1):
        k = (k << 8) | tail[j]
    if tail:
        k = (k * c1) & 0xFFFFFFFF
        k = ((k << 15) | (k >> 17)) & 0xFFFFFFFF
        k = (k * c2) & 0xFFFFFFFF
        h ^= k
    h ^= len(data)
    h ^= h >> 16
    h = (h * 0x85EBCA6B) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 0xC2B2AE35) & 0xFFFFFFFF
    h ^= h >> 16
    return h


def hash_caminho(path: str) -> tuple[int, int]:
    """Hash que o pak guarda no lugar do nome: murmur3 (semente 0xFFFFFFFF) do caminho em UTF-16LE,
    em minúsculas e em maiúsculas. Ex.: "natives/NSW/message/ui.msg.17"."""
    return (murmur3_32(path.lower().encode("utf-16-le")), murmur3_32(path.upper().encode("utf-16-le")))


def read_pak(b: bytes) -> Pak:
    if b[:4] != PAK_MAGIC or len(b) < 16:
        raise MotorError("não é um .pak do RE Engine (falta o 'KPKA')")
    major, minor, feature, count = struct.unpack_from("<BBHI", b, 4)
    if feature & 8:
        raise MotorError("o índice deste .pak é criptografado (jogos RE Engine mais novos); não sei abrir")
    if major not in (2, 4):
        raise MotorError(f".pak versão {major}.{minor}: só leio 2 e 4")
    entries, p = [], 16
    for _ in range(count):
        if major == 4:
            if p + 48 > len(b):
                raise MotorError(".pak com índice truncado")
            lo, up, off, cs, us, at, ck = struct.unpack_from("<IIQQQQQ", b, p)
            p += 48
        else:
            if p + 24 > len(b):
                raise MotorError(".pak com índice truncado")
            off, us, lo, up = struct.unpack_from("<QQII", b, p)
            cs, at, ck = us, 0, 0
            p += 24
        entries.append(PakEntry(lo, up, off, cs, us, at, ck))
    return Pak(major, minor, feature, entries)


def read_entry(b: bytes, e: PakEntry) -> bytes:
    if e.cifrada:
        raise MotorError("entrada do .pak criptografada")
    raw = b[e.offset:e.offset + e.csize]
    if e.compressao == 0:
        return raw
    if e.compressao == 1:
        for wbits in (-15, 15):
            try:
                out = zlib.decompress(raw, wbits)
            except zlib.error:
                continue
            if len(out) == e.usize:
                return out
        raise MotorError("entrada deflate do .pak não descompactou")
    if e.compressao == 2:
        raise MotorError("o texto está comprimido com zstd, e o Deck não tem o descompressor zstd "
                         "(precisa descompactar no PC, como fizemos com o Oodle)")
    raise MotorError(f"compressão {e.compressao} desconhecida no .pak")


def _parece_msg(b: bytes, e: PakEntry) -> bool | None:
    """True/False olhando o começo da entrada; None = não dá para saber (zstd/cifrada)."""
    if e.cifrada or e.compressao not in (0, 1):
        return None
    if e.compressao == 0:
        cab = b[e.offset:e.offset + 8]
    else:
        try:
            cab = zlib.decompressobj(-15).decompress(b[e.offset:e.offset + min(e.csize, 512)], 8)
        except zlib.error:
            return False
    return len(cab) == 8 and cab[4:8] == MSG_MAGIC and _u32(cab, 0) in VERSOES


def write_pak(major: int, minor: int, arquivos: list[tuple[int, int, bytes]]) -> bytes:
    """Pak sem compressão: [(hash minúsculo, hash maiúsculo, bytes)]."""
    tam = 48 if major == 4 else 24
    p = 16 + tam * len(arquivos)
    idx, corpo = bytearray(), bytearray()
    for lo, up, data in arquivos:
        off = p + len(corpo)
        if major == 4:
            idx += struct.pack("<IIQQQQQ", lo, up, off, len(data), len(data), 0, 0)
        else:
            idx += struct.pack("<QQII", off, len(data), lo, up)
        corpo += data
    return PAK_MAGIC + struct.pack("<BBHII", major, minor, 0, len(arquivos), 0) + bytes(idx) + bytes(corpo)


def _ordem_paks(paths: list[str]) -> list[str]:
    """Base primeiro e depois patch_001, 002...: o que vem depois vence (mesma prioridade do jogo)."""
    def chave(p):
        m = _PATCH.match(p.lower())
        return (m.group(1), int(m.group(2))) if m else (p.lower(), 0)
    return sorted(paths, key=chave)


def _proximo_patch(base: str, todos: list[str]) -> str:
    n = 0
    for p in todos:
        m = _PATCH.match(p)
        if m and m.group(1).lower() == base.lower():
            n = max(n, int(m.group(2)))
    return f"{base}.patch_{n + 1:03d}.pak"


# ================================================================== contrato
def collect(files: dict, read: Callable[[str], bytes]) -> Coleta:
    textos: list[Texto] = []
    msgs: dict[str, tuple] = {}     # id da origem -> (Msg, destino)
    avisos = []
    for p in sorted(files):
        if _MSG_NOME.search(p.lower()):
            msgs[p] = (read_msg(read(p)), ("solto", p))
    zstd = 0
    vencedor: dict[tuple, tuple] = {}   # (hash) -> (pak, entrada)
    cache: dict[str, bytes] = {}
    for pk in _ordem_paks([p for p in files if p.lower().endswith(".pak")]):
        b = read(pk)
        if b[:4] != PAK_MAGIC:
            continue
        cache[pk] = b
        for e in read_pak(b).entries:
            vencedor[(e.hash_lower, e.hash_upper)] = (pk, e)
    for (lo, up), (pk, e) in vencedor.items():
        b = cache[pk]
        tipo = _parece_msg(b, e)
        if tipo is None:
            zstd += 1
            continue
        if tipo:
            base = _PATCH.match(pk).group(1) if _PATCH.match(pk) else pk
            msgs[f"{pk}#{lo:08x}{up:08x}"] = (read_msg(read_entry(b, e)), ("pak", base, lo, up))
    if not msgs:
        if zstd:
            raise MotorError(f"{zstd} arquivos dos .pak estão em zstd (ou cifrados) e o Deck não tem o "
                             "descompressor zstd; os textos devem estar entre eles")
        raise MotorError("não achei nenhum .msg do RE Engine (solto ou dentro dos .pak)")
    if zstd:
        avisos.append(f"{zstd} arquivos dos .pak em zstd/cifrados não foram lidos (pode faltar texto)")
    for oid, (m, _d) in msgs.items():
        li = m.idx_ingles
        if li >= len(m.langs):
            avisos.append(f"{oid}: sem inglês")
            continue
        for i, t in enumerate(m.textos):
            if t[li]:
                textos.append(Texto(f"{oid}|{i}", t[li], CODES))

    def rebuild(traduzidos: dict[str, str]) -> dict[str, bytes]:
        por_msg: dict[str, dict[int, str]] = {}
        for tid, s in traduzidos.items():
            oid, i = tid.rsplit("|", 1)
            if oid not in msgs:
                raise MotorError(f"origem desconhecida: {oid}")
            por_msg.setdefault(oid, {})[int(i)] = s
        out: dict[str, bytes] = {}
        por_patch: dict[str, list] = {}
        for oid, novos in por_msg.items():
            m, dest = msgs[oid]
            blob = write_msg(m, novos)
            if dest[0] == "solto":
                out[dest[1]] = blob
            else:
                por_patch.setdefault(dest[1], []).append((dest[2], dest[3], blob))
        for base, arqs in por_patch.items():
            major, minor = 4, 0
            if base in files:
                bp = read_pak(cache.get(base) or read(base))
                major, minor = bp.major, bp.minor
            nome = _proximo_patch(base, list(files))
            pak = write_pak(major, minor, arqs)
            back = read_pak(pak)
            if len(back.entries) != len(arqs) or any(
                    (e.hash_lower, e.hash_upper) != (lo, up) or read_entry(pak, e) != data
                    for e, (lo, up, data) in zip(back.entries, arqs)):
                raise MotorError("o pak de patch gravado não confere na releitura")
            out[nome] = pak
        return out

    return Coleta(textos, rebuild, "; ".join(avisos))
