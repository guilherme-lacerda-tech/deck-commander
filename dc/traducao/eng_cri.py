"""CRI Middleware: pacotes .cpk (CriWare). Traduz arquivos de TEXTO legível guardados dentro do CPK.

Formato (documentação aberta: CriPakTools, vgmstream cri_utf.c, YACpkTool):
- o CPK começa com o bloco "CPK " e tem outros blocos ("TOC ", "ETOC", "ITOC", "GTOC", "HTOC"...). Cada bloco =
  assinatura(4) + u32 flags + u64 tamanho (little-endian) + uma tabela @UTF desse tamanho;
- tabela @UTF (BIG-endian): "@UTF" + u32 tamanho + u16 versão + u16 início das linhas + u32 início das strings +
  u32 início dos dados + u32 nome + u16 colunas + u16 bytes por linha + u32 linhas; depois as colunas
  (u8 flags + u32 nome). Flags: 0x10 tem nome, 0x20 tem valor fixo (no esquema), 0x40 valor por linha;
  tipo no nibble baixo (0/1 u8/s8, 2/3 u16/s16, 4/5 u32/s32, 6/7 u64/s64, 8 float, 9 double, 0xA string, 0xB dados);
- algumas tabelas vêm "embaralhadas" (XOR com um gerador simples; mesma operação para cifrar e decifrar);
- o TOC tem uma linha por arquivo: DirName, FileName, FileSize (gravado), ExtractSize (real), FileOffset;
- CRILAYLA: compressão própria (descompressor abaixo). Gravamos os arquivos trocados SEM compressão
  (FileSize = ExtractSize), o que o leitor da CRI aceita.

Base do FileOffset — regra do CriPakTools (CPK.cs, ReadTOC):
    base = min(ContentOffset, min(TocOffset, 0x800))
Na prática dá TocOffset (0x800), que é o que o YACpkTool e o vgmstream também usam. Como não deu para conferir em
CPK de Switch de verdade, a leitura testa essa regra primeiro e, se os arquivos caírem fora do CPK ou um arquivo
comprimido não começar com "CRILAYLA", tenta TocOffset, ContentOffset e 0 (nessa ordem).

Regravação: tudo até o primeiro arquivo (cabeçalho, TOC e blocos antes do conteúdo) é copiado byte a byte; os
arquivos vão na mesma ordem, com o mesmo alinhamento (coluna Align do cabeçalho); blocos que ficavam DEPOIS do
conteúdo (ex.: ETOC) são copiados para depois dos arquivos e o ponteiro deles no cabeçalho é atualizado. As tabelas
são corrigidas NO LUGAR (só os números por linha mudam; strings e layout ficam idênticos).
"""
from __future__ import annotations

import copy
import re
import struct
from dataclasses import dataclass, field
from typing import Any

from .eng_gamemaker import ArqTexto, eh_frase, gravar_texto, ler_texto
from .motores import Coleta, MotorError, Texto

NAME = "CRI (CPK)"

TEXTO_EXTS = (".txt", ".csv", ".tsv", ".json", ".xml", ".ini", ".lua", ".cfg")
AVISO_SEM_TEXTO = "texto em formato próprio do jogo dentro do CPK (precisa de estudo por jogo)"


def detect(paths: list[str]) -> bool:
    return any(p.lower().endswith(".cpk") for p in paths)


# ================================================================== @UTF
_FMT = {0: ">B", 1: ">b", 2: ">H", 3: ">h", 4: ">I", 5: ">i", 6: ">Q", 7: ">q", 8: ">f", 9: ">d"}


def _embaralha(b: bytes) -> bytes:
    """XOR das tabelas @UTF "cifradas" (CriPakTools DecryptUTF). Aplicar duas vezes devolve o original."""
    m, t = 0x0000655F, 0x00004115
    out = bytearray(b)
    for i in range(len(out)):
        out[i] ^= m & 0xFF
        m = (m * t) & 0xFFFFFFFF
    return bytes(out)


@dataclass
class Coluna:
    nome: str
    flags: int
    tipo: int
    fixo: Any = None
    pos_linha: int = -1     # deslocamento dentro da linha (valor por linha) ou -1


@dataclass
class Tabela:
    raw: bytearray          # a tabela @UTF decifrada
    nome: str
    colunas: list
    linhas: list            # [{nome: valor}]
    ini_linhas: int
    tam_linha: int

    def coluna(self, nome: str) -> Coluna | None:
        return next((c for c in self.colunas if c.nome == nome), None)

    def por_linha(self, nome: str) -> bool:
        c = self.coluna(nome)
        return c is not None and c.pos_linha >= 0

    def setar(self, r: int, nome: str, valor) -> None:
        c = self.coluna(nome)
        if c is None or c.pos_linha < 0:
            raise MotorError(f"tabela {self.nome}: coluna {nome} não é por linha, não dá para mudar só um arquivo")
        if c.tipo not in _FMT:
            raise MotorError(f"tabela {self.nome}: coluna {nome} não é numérica")
        struct.pack_into(_FMT[c.tipo], self.raw, self.ini_linhas + r * self.tam_linha + c.pos_linha, valor)
        self.linhas[r][nome] = valor


def _valor(tb: bytes, p: int, tipo: int, ini_str: int, ini_dados: int):
    if tipo in _FMT:
        n = struct.calcsize(_FMT[tipo])
        return struct.unpack_from(_FMT[tipo], tb, p)[0], n
    if tipo == 0xA:
        o = struct.unpack_from(">I", tb, p)[0]
        return _cstr(tb, ini_str + o), 4
    if tipo == 0xB:
        o, n = struct.unpack_from(">II", tb, p)
        return bytes(tb[ini_dados + o:ini_dados + o + n]), 8
    if tipo == 0xC:
        return bytes(tb[p:p + 16]), 16
    raise MotorError(f"tipo de coluna @UTF desconhecido: {tipo:#x}")


def _cstr(tb: bytes, p: int) -> str:
    fim = tb.find(b"\0", p)
    if fim < 0:
        raise MotorError("string da tabela @UTF sem \\0")
    s = bytes(tb[p:fim])
    try:
        return s.decode("utf-8")
    except UnicodeDecodeError:
        return s.decode("cp932", "replace")  # CPKs antigos gravam nomes em Shift-JIS


def ler_utf(b: bytes) -> Tabela:
    if b[:4] != b"@UTF":
        raise MotorError("tabela @UTF esperada")
    tam = struct.unpack_from(">I", b, 4)[0]
    tb = bytearray(b[:8 + tam])
    if len(tb) < 32:
        raise MotorError("tabela @UTF cortada")
    _ver, ini_linhas, ini_str, ini_dados, nome_o, ncol, tam_linha, nlin = struct.unpack_from(">HHIIIHHI", tb, 8)
    ini_linhas += 8
    ini_str += 8
    ini_dados += 8
    nome = _cstr(tb, ini_str + nome_o)
    p, pos_linha, cols = 32, 0, []
    for _ in range(ncol):
        fl = tb[p]
        no = struct.unpack_from(">I", tb, p + 1)[0]
        p += 5
        c = Coluna(_cstr(tb, ini_str + no) if fl & 0x10 else "", fl & 0xF0, fl & 0x0F)
        if fl & 0x20:
            c.fixo, n = _valor(tb, p, c.tipo, ini_str, ini_dados)
            p += n
        if fl & 0x40:
            c.pos_linha = pos_linha
            pos_linha += {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 8, 7: 8, 8: 4, 9: 8, 0xA: 4, 0xB: 8, 0xC: 16}[c.tipo]
        cols.append(c)
    if pos_linha > tam_linha:
        raise MotorError("linha da tabela @UTF maior que o declarado")
    linhas = []
    for r in range(nlin):
        base = ini_linhas + r * tam_linha
        row = {}
        for c in cols:
            if c.pos_linha >= 0:
                row[c.nome] = _valor(tb, base + c.pos_linha, c.tipo, ini_str, ini_dados)[0]
            else:
                row[c.nome] = c.fixo
        linhas.append(row)
    return Tabela(tb, nome, cols, linhas, ini_linhas, tam_linha)


@dataclass
class Bloco:
    sig: str
    pos: int                # início do bloco no CPK (assinatura)
    tab: Tabela
    cifrado: bool

    @property
    def tam(self) -> int:
        return 16 + len(self.tab.raw)

    def bytes_utf(self) -> bytes:
        return _embaralha(bytes(self.tab.raw)) if self.cifrado else bytes(self.tab.raw)


def ler_bloco(b: bytes, pos: int, sig: str) -> Bloco:
    if b[pos:pos + 4] != sig.encode():
        raise MotorError(f"bloco {sig.strip()} não encontrado em {pos:#x}")
    n = struct.unpack_from("<Q", b, pos + 8)[0]
    utf = bytes(b[pos + 16:pos + 16 + n])
    cifrado = utf[:4] != b"@UTF"
    if cifrado:
        utf = _embaralha(utf)
    return Bloco(sig, pos, ler_utf(utf), cifrado)


# ================================================================== CRILAYLA
def crilayla_descomprimir(d: bytes) -> bytes:
    """Descompressor CRILAYLA (mesmo algoritmo do CriPakTools/vgmstream).

    Layout: "CRILAYLA" + u32 tamanho descomprimido (sem o prefixo) + u32 tamanho dos dados comprimidos (LE),
    dados comprimidos, e por fim 0x100 bytes que são o COMEÇO do arquivo original, guardados sem compressão.
    Os bits são lidos de TRÁS para frente (do fim dos dados comprimidos para o começo, bit mais alto primeiro) e a
    saída também é escrita de trás para frente: 1 bit "0" = byte literal (8 bits); "1" = cópia de 13 bits de
    distância (+3) e tamanho 3 + campos de 2, 3, 5, 8 bits (cada um cheio continua no próximo; depois de 8 cheio,
    blocos de 8 bits até um diferente de 255).
    """
    if d[:8] != b"CRILAYLA":
        raise MotorError("não é CRILAYLA")
    usize, hoff = struct.unpack_from("<II", d, 8)
    if 0x10 + hoff + 0x100 > len(d):
        raise MotorError("CRILAYLA cortado")
    out = bytearray(usize + 0x100)
    out[:0x100] = d[0x10 + hoff:0x10 + hoff + 0x100]
    pos = 0x10 + hoff - 1              # último byte dos dados comprimidos
    fim_saida = 0x100 + usize - 1
    pool = 0
    sobra = 0

    def bits(n: int) -> int:
        nonlocal pos, pool, sobra
        v = 0
        feitos = 0
        while feitos < n:
            if sobra == 0:
                if pos < 0x10:
                    raise MotorError("CRILAYLA: dados comprimidos acabaram")
                pool = d[pos]
                pos -= 1
                sobra = 8
            k = min(sobra, n - feitos)
            v = (v << k) | ((pool >> (sobra - k)) & ((1 << k) - 1))
            sobra -= k
            feitos += k
        return v

    feitos = 0
    lens = (2, 3, 5, 8)
    while feitos < usize:
        if bits(1):
            src = fim_saida - feitos + bits(13) + 3
            n = 3
            nivel = 0
            while nivel < 4:
                x = bits(lens[nivel])
                n += x
                if x != (1 << lens[nivel]) - 1:
                    break
                nivel += 1
            if nivel == 4:
                while True:
                    x = bits(8)
                    n += x
                    if x != 255:
                        break
            if feitos + n > usize or src > fim_saida:
                raise MotorError("CRILAYLA: cópia fora do arquivo")
            for _ in range(n):
                out[fim_saida - feitos] = out[src]
                src -= 1
                feitos += 1
        else:
            out[fim_saida - feitos] = bits(8)
            feitos += 1
    return bytes(out)


# ================================================================== CPK
@dataclass
class Interno:
    linha: int              # linha no TOC
    caminho: str
    pos: int                # absoluto no CPK
    tam: int                # gravado
    real: int               # descomprimido


@dataclass
class Cpk:
    b: bytes
    cab: Bloco
    toc: Bloco
    base: int
    alinha: int
    internos: list = field(default_factory=list)

    def bruto(self, it: Interno) -> bytes:
        return self.b[it.pos:it.pos + it.tam]

    def conteudo(self, it: Interno) -> bytes:
        d = self.bruto(it)
        if it.tam < it.real or d[:8] == b"CRILAYLA":
            d = crilayla_descomprimir(d)
        if len(d) != it.real:
            raise MotorError(f"{it.caminho}: tamanho {len(d)} ≠ ExtractSize {it.real}")
        return d


def _base_cripaktools(toc_off: int, cont_off: int | None) -> int:
    f = min(toc_off, 0x800)
    if cont_off is None:
        return f
    return min(cont_off, f)


def abrir_cpk(b: bytes) -> Cpk:
    cab = ler_bloco(b, 0, "CPK ")
    h = cab.tab.linhas[0]
    toc_off = h.get("TocOffset")
    if not toc_off:
        raise MotorError("CPK sem TOC de nomes (só ITOC por número): não sei o nome dos arquivos")
    cont_off = h.get("ContentOffset")
    alinha = int(h.get("Align") or 1) or 1
    toc = ler_bloco(b, toc_off, "TOC ")
    linhas = toc.tab.linhas
    for base in dict.fromkeys([_base_cripaktools(toc_off, cont_off), toc_off, cont_off or 0, 0]):
        ok = True
        ints = []
        for r, row in enumerate(linhas):
            pos = int(row.get("FileOffset") or 0) + base
            tam = int(row.get("FileSize") or 0)
            real = int(row.get("ExtractSize") if row.get("ExtractSize") is not None else tam)
            if pos + tam > len(b) or (tam < real and b[pos:pos + 8] != b"CRILAYLA"):
                ok = False
                break
            d, f = row.get("DirName") or "", row.get("FileName") or f"#{r}"
            ints.append(Interno(r, f"{d}/{f}" if d else f, pos, tam, real))
        if ok:
            return Cpk(b, cab, toc, base, alinha, ints)
    raise MotorError("não consegui achar a base do FileOffset do TOC (arquivos caem fora do CPK)")


def _blocos_cab(cpk: Cpk) -> list[tuple[str, int, int]]:
    """[(prefixo, offset, tamanho)] dos blocos que o cabeçalho cita (XxxOffset + XxxSize), menos o conteúdo."""
    h = cpk.cab.tab.linhas[0]
    out = []
    for nome, v in h.items():
        m = re.fullmatch(r"(\w+)Offset", nome or "")
        if not m or m.group(1) == "Content" or not v:
            continue
        pre = m.group(1)
        tam = int(h.get(pre + "Size") or 0)
        b = cpk.b
        if v + 16 <= len(b):
            tam = max(tam, 16 + struct.unpack_from("<Q", b, v + 8)[0])
        out.append((pre, int(v), tam))
    return out


def _alinhar(n: int, a: int, base: int = 0) -> int:
    return n + (-(n - base)) % a


def regravar_cpk(cpk: Cpk, novos: dict[int, bytes]) -> bytes:
    """CPK inteiro de novo com os arquivos de `novos` (linha do TOC -> bytes) gravados sem compressão."""
    b = cpk.b
    ints = sorted(cpk.internos, key=lambda x: (x.pos, x.linha))
    if not ints:
        raise MotorError("CPK sem arquivos")
    primeiro = ints[0].pos
    fim_antigo = max(x.pos + x.tam for x in ints)
    # alinhamento igual ao original: absoluto, ou relativo à base do FileOffset se era assim
    rel = 0
    if any(x.pos % cpk.alinha for x in ints) and all((x.pos - cpk.base) % cpk.alinha == 0 for x in ints):
        rel = cpk.base
    out = bytearray(b[:primeiro])
    nova_pos: dict[int, tuple[int, int]] = {}
    feito: dict[int, int] = {}  # arquivos que dividiam o mesmo lugar no original continuam dividindo
    for x in ints:
        dados = novos.get(x.linha)
        if dados is None and x.pos in feito:
            nova_pos[x.linha] = (feito[x.pos], x.tam)
            continue
        if dados is None:
            dados = cpk.bruto(x)
        p = _alinhar(len(out), cpk.alinha, rel)
        out += b"\0" * (p - len(out))
        out += dados
        nova_pos[x.linha] = (p, len(dados))
        if x.linha not in novos:
            feito[x.pos] = p
    fim_novo = len(out)
    # blocos depois do conteúdo (ETOC etc.): vão para depois dos arquivos
    reloc: dict[str, int] = {}
    blocos = _blocos_cab(cpk)
    for pre, off, tam in sorted(blocos, key=lambda x: x[1]):
        if off < primeiro:
            continue
        if off < fim_antigo:
            raise MotorError(f"bloco {pre} fica no meio dos arquivos: não sei regravar esse CPK")
        p = _alinhar(len(out), cpk.alinha)
        out += b"\0" * (p - len(out))
        out += b[off:off + tam]
        reloc[pre] = p
    resto = len(b) - max([fim_antigo] + [o + t for _, o, t in blocos])
    if resto > 0:  # preenchimento do fim do arquivo original
        out += b"\0" * ((-len(out)) % cpk.alinha)
    # TOC: tamanhos e offsets novos, corrigidos no lugar
    toc = copy.deepcopy(cpk.toc)
    for x in cpk.internos:
        p, n = nova_pos[x.linha]
        if x.linha in novos:
            toc.tab.setar(x.linha, "FileSize", n)
            if toc.tab.coluna("ExtractSize") is not None:
                toc.tab.setar(x.linha, "ExtractSize", n)
            if toc.tab.por_linha("CRC") and toc.tab.linhas[x.linha].get("CRC"):
                toc.tab.setar(x.linha, "CRC", 0)  # algoritmo do CRC da CRI não confirmado: zero = "sem CRC"
        if p - cpk.base != toc.tab.linhas[x.linha].get("FileOffset"):
            toc.tab.setar(x.linha, "FileOffset", p - cpk.base)
    cab = copy.deepcopy(cpk.cab)
    h = cab.tab.linhas[0]
    for pre, p in reloc.items():
        cab.tab.setar(0, pre + "Offset", p)
    if h.get("ContentSize") is not None and cab.tab.por_linha("ContentSize"):
        cab.tab.setar(0, "ContentSize", h["ContentSize"] + (fim_novo - fim_antigo))
    soma_t = sum(len(d) - x.tam for x in cpk.internos if (d := novos.get(x.linha)) is not None)
    soma_r = sum(len(d) - x.real for x in cpk.internos if (d := novos.get(x.linha)) is not None)
    for nome, delta in (("EnabledPackedSize", soma_t), ("EnabledDataSize", soma_r)):
        if h.get(nome) is not None and cab.tab.por_linha(nome) and delta:
            cab.tab.setar(0, nome, h[nome] + delta)
    toc_pos = reloc.get("Toc", cpk.toc.pos)
    for blk, pos in ((cab, 0), (toc, toc_pos)):
        utf = blk.bytes_utf()
        out[pos + 16:pos + 16 + len(utf)] = utf
    novo = bytes(out)
    # conferência: reabre e compara cada arquivo interno
    back = abrir_cpk(novo)
    if back.base != cpk.base or len(back.internos) != len(cpk.internos):
        raise MotorError("CPK regravado não reabre igual")
    for x, y in zip(sorted(cpk.internos, key=lambda i: i.linha), sorted(back.internos, key=lambda i: i.linha)):
        if x.caminho != y.caminho:
            raise MotorError("nomes do CPK mudaram")
        esperado = novos.get(x.linha)
        if esperado is None:
            if back.bruto(y) != cpk.bruto(x):
                raise MotorError(f"{x.caminho}: mudou sem querer")
        elif back.conteudo(y) != esperado:
            raise MotorError(f"{x.caminho}: conteúdo novo não confere")
    return novo


# ================================================================== contrato
def _eh_texto_ext(nome: str) -> bool:
    return nome.lower().endswith(TEXTO_EXTS)


def collect(files: dict, read) -> Coleta:
    textos: list[Texto] = []
    destino: dict[str, tuple[str, int, str]] = {}   # id -> (cpk, linha do TOC, id local)
    cpks: dict[str, Cpk] = {}
    arqs: dict[tuple[str, int], ArqTexto] = {}
    avisos: list[str] = []
    for p in files:
        if not p.lower().endswith(".cpk"):
            continue
        try:
            cpk = abrir_cpk(read(p))
        except (MotorError, struct.error, IndexError) as e:
            avisos.append(f"{p}: {e}")
            continue
        for it in cpk.internos:
            if it.real == 0 or it.real > (16 << 20):
                continue
            try:
                d = cpk.conteudo(it)
            except MotorError as e:
                avisos.append(f"{p}|{it.caminho}: {e}")
                continue
            arq = ler_texto(it.caminho, d, exigir_texto=not _eh_texto_ext(it.caminho))
            if arq is None:
                continue
            achou = False
            for x in arq.itens:
                if eh_frase(x.texto):
                    tid = f"{p}|{it.caminho}|{x.id}"
                    textos.append(Texto(tid, x.texto))
                    destino[tid] = (p, it.linha, x.id)
                    achou = True
            if achou:
                arqs[(p, it.linha)] = arq
                cpks[p] = cpk

    def rebuild(trads: dict[str, str]) -> dict[str, bytes]:
        por: dict[str, dict[int, dict[str, str]]] = {}
        for tid, s in trads.items():
            if tid in destino:
                p, linha, lid = destino[tid]
                por.setdefault(p, {}).setdefault(linha, {})[lid] = s
        out: dict[str, bytes] = {}
        for p, por_linha in por.items():
            novos = {linha: gravar_texto(arqs[(p, linha)], lids) for linha, lids in por_linha.items()}
            out[p] = regravar_cpk(cpks[p], novos)
        return out

    aviso = "; ".join(avisos)
    if not textos:
        aviso = AVISO_SEM_TEXTO + (f" ({aviso})" if aviso else "")
    return Coleta(textos, rebuild, aviso, {"cpks": sorted(cpks)})
