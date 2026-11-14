"""Aplica patch XDelta (VCDIFF, RFC 3284) sem programa de fora — pedido 14/11/2026 (tradução da OAleex do God of War
Chains of Olympus vem em .xdelta de 1,1 GB e o Deck não tem xdelta3).

Funciona em pedaços (janelas), lendo o jogo e o patch do disco: não carrega 1 GB na memória.

O xdelta3 grava uma soma (adler32) de cada pedaço do resultado. Isso permite aplicar o patch num jogo que NÃO é o
original que o patch pede (ex.: uma ISO que já veio modificada por outra tradução) e saber exatamente quais pedaços
saíram certos: `relatorio["errados"]` lista os pedaços cuja soma não bateu. Zero errados = resultado idêntico ao que o
tradutor gerou.

Compressão secundária (xdelta3 -S djw/lzma/fgk): o leitor não decodifica; `recodificar` usa o xdelta3 oficial (pacote
do Arch, em ~/.local/share/deck-commander/bin) só para regravar o patch SEM ela (`xdelta3 recode -S none`, ~40 s para
2 GB) e o resto segue por aqui — inclusive o transplante para disco de outra versão (14/11/2026: as traduções do
João13 para PS2 vêm com DJW). Tabela de códigos própria: recusada com motivo.
"""
from __future__ import annotations

import zlib
from pathlib import Path

NOOP, ADD, RUN, COPY = 0, 1, 2, 3
VCD_SOURCE, VCD_TARGET, VCD_ADLER32 = 0x01, 0x02, 0x04
S_NEAR, S_SAME = 4, 3


class ErroVcdiff(ValueError):
    pass


def compressao_secundaria(patch: Path) -> bool:
    with open(patch, "rb") as f:
        cab = f.read(5)
    return cab[:4] == b"\xd6\xc3\xc4\x00" and bool(cab[4] & 0x01)


def programa_xdelta3() -> str | None:
    import shutil
    p = Path.home() / ".local/share/deck-commander/bin/xdelta3"
    return shutil.which("xdelta3") or (str(p) if p.exists() else None)


def recodificar(patch: Path, destino: Path, programa: str | None = None, rodar=None) -> Path:
    """Regrava o patch sem compressão secundária (mesmo conteúdo, só desempacotado)."""
    import subprocess
    programa = programa or programa_xdelta3()
    if not programa:
        raise ErroVcdiff("patch com compressão secundária (xdelta3 -S) e o programa xdelta3 não está instalado "
                         "(no Deck: distrobox enter dcbuild -- sudo pacman -S xdelta3; depois copie /usr/bin/xdelta3 "
                         "para ~/.local/share/deck-commander/bin/)")
    rodar = rodar or subprocess.run
    r = rodar([programa, "recode", "-S", "none", "-f", str(patch), str(destino)], capture_output=True, text=True,
              timeout=3600, check=False)
    if r.returncode != 0 or not Path(destino).exists() or compressao_secundaria(Path(destino)):
        raise ErroVcdiff(f"não consegui regravar o patch sem a compressão secundária: {(r.stderr or '').strip()[:200]}")
    return Path(destino)


def tabela_padrao() -> list[tuple[int, int, int, int, int, int]]:
    """Tabela de instruções padrão (RFC 3284 seção 5.6): (tipo1, tam1, modo1, tipo2, tam2, modo2)."""
    t = [(RUN, 0, 0, NOOP, 0, 0)]
    t += [(ADD, s, 0, NOOP, 0, 0) for s in range(0, 18)]
    for modo in range(9):
        t.append((COPY, 0, modo, NOOP, 0, 0))
        t += [(COPY, s, modo, NOOP, 0, 0) for s in range(4, 19)]
    for modo in range(6):
        t += [(ADD, a, 0, COPY, c, modo) for a in range(1, 5) for c in range(4, 7)]
    for modo in range(6, 9):
        t += [(ADD, a, 0, COPY, 4, modo) for a in range(1, 5)]
    t += [(COPY, 4, modo, ADD, 1, 0) for modo in range(9)]
    assert len(t) == 256
    return t


TABELA = tabela_padrao()


class _Leitor:
    """Lê um trecho de bytes com números no formato do VCDIFF (base 128, mais significativo primeiro)."""

    def __init__(self, data: bytes | memoryview, pos: int = 0):
        self.d, self.p = data, pos

    def byte(self) -> int:
        if self.p >= len(self.d):
            raise ErroVcdiff("patch terminou no meio (arquivo cortado?)")
        b = self.d[self.p]
        self.p += 1
        return b

    def num(self) -> int:
        n = 0
        for _ in range(10):
            b = self.byte()
            n = (n << 7) | (b & 0x7F)
            if not b & 0x80:
                return n
        raise ErroVcdiff("número inválido no patch")

    def pedaco(self, n: int) -> bytes:
        if self.p + n > len(self.d):
            raise ErroVcdiff("patch terminou no meio (arquivo cortado?)")
        b = bytes(self.d[self.p:self.p + n])
        self.p += n
        return b


def _num_arquivo(f) -> int:
    n = 0
    for _ in range(10):
        c = f.read(1)
        if not c:
            raise ErroVcdiff("patch terminou no meio (arquivo cortado?)")
        n = (n << 7) | (c[0] & 0x7F)
        if not c[0] & 0x80:
            return n
    raise ErroVcdiff("número inválido no patch")


def _decodificar_janela(origem: bytes, alvo_tam: int, dados: bytes, inst: bytes, ends: bytes,
                        copias=None) -> bytes:
    """Monta um pedaço do resultado. `origem` = trecho do jogo (ou do resultado, se VCD_TARGET).
    `copias(pos_no_pedaco, pos_na_origem, tamanho)`: avisa cada trecho copiado da origem."""
    s = len(origem)
    out = bytearray()
    di, ii, ai = _Leitor(dados), _Leitor(inst), _Leitor(ends)
    perto, mesmo, prox = [0] * S_NEAR, [0] * (S_SAME * 256), 0

    def endereco(modo: int) -> int:
        nonlocal prox
        aqui = s + len(out)
        if modo == 0:
            a = ai.num()
        elif modo == 1:
            a = aqui - ai.num()
        elif modo < 2 + S_NEAR:
            a = perto[modo - 2] + ai.num()
        else:
            a = mesmo[(modo - 2 - S_NEAR) * 256 + ai.byte()]
        perto[prox] = a
        prox = (prox + 1) % S_NEAR
        mesmo[a % (S_SAME * 256)] = a
        return a

    while ii.p < len(inst):
        cod = TABELA[ii.byte()]
        for tipo, tam, modo in ((cod[0], cod[1], cod[2]), (cod[3], cod[4], cod[5])):
            if tipo == NOOP:
                continue
            if tam == 0:
                tam = ii.num()
            if tipo == ADD:
                out += di.pedaco(tam)
            elif tipo == RUN:
                out += bytes([di.byte()]) * tam
            else:
                a = endereco(modo)
                if a < s:
                    if copias is not None:
                        copias(len(out), a, min(tam, s - a))
                    fim = a + tam
                    if fim <= s:
                        out += origem[a:fim]
                        continue
                    out += origem[a:s]  # cópia que atravessa da origem para o resultado
                    tam, a = fim - s, s
                a -= s
                if a < 0 or a > len(out):
                    raise ErroVcdiff("cópia aponta para fora do pedaço")
                if a + tam <= len(out):
                    out += out[a:a + tam]
                else:  # sobreposta: repete o padrão (é assim que o VCDIFF codifica sequências)
                    for k in range(tam):
                        out.append(out[a + k])
    if len(out) != alvo_tam:
        raise ErroVcdiff(f"pedaço com {len(out)} bytes, o patch dizia {alvo_tam}")
    return bytes(out)


def aplicar(jogo: Path | None, patch: Path, saida: Path, progresso=None, copias: list | None = None,
            remendos: list | None = None) -> dict:
    """Aplica `patch` em `jogo` e grava `saida`. Devolve relatorio:
    {"janelas", "tamanho", "errados": [(inicio, tamanho), ...], "bytes_errados", "sem_soma"}.
    `copias`: se for uma lista, recebe (pos_no_resultado, pos_no_jogo, tamanho) de cada trecho que veio do jogo —
    num jogo diferente do original, são exatamente os bytes que podem ter saído errados.
    `remendos`: [(pos_no_jogo, bytes), ...] lidos NO LUGAR do jogo (o que se sabe que o original tinha ali)."""
    import bisect
    remendos = sorted(remendos or [])
    rem_ini = [r[0] for r in remendos]
    rel = {"janelas": 0, "tamanho": 0, "errados": [], "bytes_errados": 0, "sem_soma": 0}
    tam_patch = patch.stat().st_size
    with open(patch, "rb") as fp, open(saida, "w+b") as fo, (open(jogo, "rb") if jogo else _Nada()) as fj:
        if fp.read(4) != b"\xd6\xc3\xc4\x00":
            raise ErroVcdiff("não é um patch xdelta/VCDIFF")
        ind = fp.read(1)[0]
        if ind & 0x01:
            raise ErroVcdiff("patch com compressão secundária (xdelta3 -S): ainda não suportado")
        if ind & 0x02:
            raise ErroVcdiff("patch com tabela de códigos própria: ainda não suportado")
        if ind & 0x04:
            fp.read(_num_arquivo(fp))  # cabeçalho do programa (nome dos arquivos), ignorado
        while True:
            c = fp.read(1)
            if not c:
                break
            wi = c[0]
            origem = b""
            if wi & (VCD_SOURCE | VCD_TARGET):
                seg_tam, seg_pos = _num_arquivo(fp), _num_arquivo(fp)
                if wi & VCD_SOURCE:
                    if jogo is None:
                        raise ErroVcdiff("este patch precisa do jogo original")
                    fj.seek(seg_pos)
                    origem = fj.read(seg_tam)
                    if len(origem) < seg_tam:  # jogo menor que o original: o que falta fica zerado (e a soma acusa)
                        origem += b"\0" * (seg_tam - len(origem))
                    if remendos:
                        k = max(0, bisect.bisect_right(rem_ini, seg_pos) - 64)
                        fim, buf = seg_pos + seg_tam, None
                        while k < len(remendos) and remendos[k][0] < fim:
                            rp, rb = remendos[k]
                            a, b = max(rp, seg_pos), min(rp + len(rb), fim)
                            if a < b:
                                buf = buf if buf is not None else bytearray(origem)
                                buf[a - seg_pos:b - seg_pos] = rb[a - rp:b - rp]
                            k += 1
                        if buf is not None:
                            origem = bytes(buf)
                else:
                    fo.flush()
                    fo.seek(seg_pos)
                    origem = fo.read(seg_tam)
                    fo.seek(0, 2)
            _ = _num_arquivo(fp)  # tamanho da codificação
            alvo_tam = _num_arquivo(fp)
            if fp.read(1)[0] != 0:
                raise ErroVcdiff("patch com compressão secundária (xdelta3 -S): ainda não suportado")
            nd, ni, na = _num_arquivo(fp), _num_arquivo(fp), _num_arquivo(fp)
            soma = int.from_bytes(fp.read(4), "big") if wi & VCD_ADLER32 else None
            dados, inst, ends = fp.read(nd), fp.read(ni), fp.read(na)
            if len(ends) < na:
                raise ErroVcdiff("patch terminou no meio (arquivo cortado?)")
            inicio = rel["tamanho"]
            avisa = None
            if copias is not None and wi & VCD_SOURCE:
                def avisa(pos, a, n, _i=inicio, _s=seg_pos):
                    copias.append((_i + pos, _s + a, n))
            try:
                pedaco = _decodificar_janela(origem, alvo_tam, dados, inst, ends, avisa)
            except ErroVcdiff:
                if soma is None:
                    raise
                pedaco = b"\0" * alvo_tam  # origem diferente pode gerar endereço impossível: marca como errado
                soma = -1
            fo.write(pedaco)
            rel["janelas"] += 1
            rel["tamanho"] += alvo_tam
            if soma is None:
                rel["sem_soma"] += 1
            elif zlib.adler32(pedaco) != soma:
                rel["errados"].append((inicio, alvo_tam))
                rel["bytes_errados"] += alvo_tam
            if progresso:
                progresso(fp.tell(), tam_patch)
    return rel


class _Nada:
    def __enter__(self):
        return None

    def __exit__(self, *a):
        return False


def main(argv: list[str]) -> int:
    """python3 -m dc.vcdiff <jogo> <patch.xdelta> <saida>"""
    import json
    import sys
    if len(argv) != 3:
        print(main.__doc__)
        return 2
    ultimo = [-1]

    def prog(feito, total):
        pc = feito * 100 // max(total, 1)
        if pc != ultimo[0] and pc % 5 == 0:
            ultimo[0] = pc
            print(f"{pc}%", flush=True)
    rel = aplicar(Path(argv[0]), Path(argv[1]), Path(argv[2]), prog)
    rel["errados"] = rel["errados"][:50]
    print(json.dumps(rel))
    sys.stdout.flush()
    return 0 if not rel["bytes_errados"] else 1


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
