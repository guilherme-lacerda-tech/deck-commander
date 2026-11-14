"""Tradução da comunidade feita para OUTRA versão do disco (pedido 14/11/2026: God of War: Chains of Olympus).

O caso real: a tradução PT-BR da OAleex (patch xdelta de 1,1 GB) pede a ISO americana original (UCUS-98653); a ISO do
usuário é a americana já modificada por uma tradução russa ("Barik Rus 4.96"), remontada com outra arrumação de
arquivos. Medido no Deck: o patch aplica, mas 166 de 192 pedaços não conferem a soma — só 8% do resultado (125 MB)
vem do jogo original e esses trechos saem errados; o resto (92%) vem inteiro dentro do patch.

O que dá certo (testado no Deck 14/11/2026, jogo aberto no PPSSPP: menu, dificuldade e legendas em português com
acento): tirar do resultado SÓ os arquivos que a tradução trocou (textos e fonte — eles vêm inteiros no patch) e
colocá-los dentro da ISO do usuário, que continua sendo o jogo que já funciona. Os poucos bytes desses arquivos que
o patch copiaria do original vêm do mesmo lugar do arquivo correspondente na ISO do usuário.

Cada jogo tem uma RECEITA (quais arquivos levar), escolhida pelo código do disco (PARAM.SFO). Sem receita: nada é
feito e o motivo é dito.
"""
from __future__ import annotations

import bisect
import fnmatch
import mmap
import os
import shutil
import struct
from pathlib import Path

S = 2048

# Código do disco -> arquivos que a tradução troca (caminhos dentro da ISO; * vale)
RECEITAS = {
    "UCUS98653": {"nome": "God of War: Chains of Olympus (tradução OAleex e cia, v1.1)",
                  "arquivos": ["/PSP_GAME/USRDIR/data/English/*", "/PSP_GAME/USRDIR/data/font.fnt"]},
}


class ErroTransplante(RuntimeError):
    pass


# ------------------------------------------------------------------------------------------------ ISO 9660
def registros(f) -> dict[str, tuple[int, int, int]]:
    """{"/PASTA/ARQ": (posição do registro no disco, setor, tamanho)} de todos os arquivos (não pastas)."""
    def ler(a, n):
        f.seek(a)
        return f.read(n)
    out: dict[str, tuple[int, int, int]] = {}
    vistos = set()

    def andar(lba: int, tam: int, pre: str) -> None:
        if lba in vistos:
            return
        vistos.add(lba)
        d = ler(lba * S, ((tam + S - 1) // S) * S)
        i = 0
        while i < len(d):
            n = d[i]
            if n == 0:
                i = (i // S + 1) * S
                continue
            r = d[i:i + n]
            if n < 34 or 33 + r[32] > n:
                raise ErroTransplante("diretório da ISO ilegível")
            nome = r[33:33 + r[32]]
            if nome not in (b"\0", b"\1"):
                caminho = pre + "/" + nome.decode("latin1").split(";")[0]
                elba, etam = struct.unpack("<I", r[2:6])[0], struct.unpack("<I", r[10:14])[0]
                if r[25] & 2:
                    andar(elba, etam, caminho)
                else:
                    out[caminho] = (lba * S + i, elba, etam)
            i += n
    pvd = ler(16 * S, S)
    if pvd[1:6] != b"CD001":
        raise ErroTransplante("não é uma ISO")
    raiz = pvd[156:190]
    andar(struct.unpack("<I", raiz[2:6])[0], struct.unpack("<I", raiz[10:14])[0], "")
    return out


def codigo_disco(iso: Path) -> str | None:
    """DISC_ID do PARAM.SFO (PSP)."""
    with open(iso, "rb") as f:
        try:
            r = registros(f)
        except (ErroTransplante, struct.error):
            return None
        e = r.get("/PSP_GAME/PARAM.SFO")
        if not e:
            return None
        f.seek(e[1] * S)
        sfo = f.read(e[2])
    if sfo[:4] != b"\0PSF":
        return None
    chaves, dados, n = struct.unpack("<III", sfo[8:20])
    for k in range(n):
        ko, _fmt, tam, _max, do = struct.unpack("<HHIII", sfo[20 + 16 * k:36 + 16 * k])
        nome = sfo[chaves + ko:sfo.index(b"\0", chaves + ko)].decode("latin1")
        if nome == "DISC_ID":
            return sfo[dados + do:dados + do + tam].split(b"\0")[0].decode("latin1")
    return None


def tamanho_real(dados_ru: bytes, inicio: bytes) -> int:
    """Tamanho do arquivo traduzido. Arquivo "Pack" (God of War) diz o próprio tamanho no cabeçalho (+4)."""
    if inicio[:4] == b"Pack" and len(inicio) >= 0x28:
        return struct.unpack("<I", inicio[0x24:0x28])[0] + 4
    return len(dados_ru)


def _parecido(a: bytes, b: bytes) -> float:
    n = min(len(a), len(b)) // 16
    if not n:
        return 0.0
    return sum(1 for i in range(0, n * 16, 16) if a[i:i + 16] == b[i:i + 16]) / n


def achar(m, dados_ru: bytes, perto: int | None = None) -> int | None:
    """Posição (alinhada ao setor) do arquivo traduzido dentro do resultado do patch.
    1º: mesmo cabeçalho (16 bytes) — se houver vários, o mais perto do anterior (os arquivos vêm em ordem);
    2º: mesma assinatura (4 bytes) e pelo menos metade igual (ex.: fonte com letras trocadas)."""
    def busca(chave: bytes, limite=5000):
        res, i = [], m.find(chave)
        while i != -1 and len(res) < limite:
            if i % S == 0:
                res.append(i)
            i = m.find(chave, i + 1)
        return res
    if len(set(dados_ru[:16])) > 2:
        cands = busca(dados_ru[:16])
        if cands:
            if perto is None:
                return max(cands, key=lambda c: _parecido(m[c:c + len(dados_ru)], dados_ru))
            depois = [c for c in cands if c >= perto]
            return min(depois or cands, key=lambda c: abs(c - perto))
    # pedaços do meio do arquivo votam onde ele começa (o cabeçalho pode ter vindo errado: no God of War a fonte
    # tinha 69 bytes do cabeçalho copiados do disco original, visto no Deck 14/11/2026)
    from collections import Counter
    votos: Counter = Counter()
    passo = max(16, len(dados_ru) // 64 // 16 * 16)
    for k in range(0, max(0, len(dados_ru) - 16), passo):
        bloco = dados_ru[k:k + 16]
        if len(set(bloco)) < 6:
            continue
        i, achados = m.find(bloco), 0
        while i != -1 and achados < 20:
            if (i - k) % S == 0 and i >= k:
                votos[i - k] += 1
            achados += 1
            i = m.find(bloco, i + 1)
    for c, n in votos.most_common(5):
        if n >= 3 and _parecido(m[c:c + len(dados_ru)], dados_ru) >= 0.5:
            return c
    return None


def conserta(dados: bytes, inicio: int, original: bytes, copias_ord: list, inicios: list) -> bytes:
    """Bytes que o patch copiaria do disco original (que o usuário não tem): usa o mesmo lugar do arquivo do usuário."""
    b = bytearray(dados)
    fim = inicio + len(b)
    i = max(0, bisect.bisect_right(inicios, inicio) - 1)
    while i < len(copias_ord) and copias_ord[i][0] < fim:
        t, _x, n = copias_ord[i]
        for k in range(max(t, inicio), min(t + n, fim)):
            o = k - inicio
            if o < len(original):
                b[o] = original[o]
        i += 1
    return bytes(b)


def montar(iso: Path, trocas: dict[str, bytes], saida: Path) -> Path:
    """Cópia da ISO com arquivos trocados. Cabe no lugar: grava lá; não cabe: vai para o fim do disco.
    Só os campos de setor e tamanho dos registros mudam (o nome é o mesmo, então o diretório não muda de tamanho)."""
    with open(iso, "rb") as f:
        reg = registros(f)
    falta = [n for n in trocas if n not in reg]
    if falta:
        raise ErroTransplante(f"arquivo(s) que não existem na ISO: {falta[:3]}")
    tmp = saida.with_name(saida.name + ".tmp")
    shutil.copyfile(iso, tmp)
    with open(tmp, "r+b") as fo:
        fim = (os.path.getsize(tmp) + S - 1) // S * S
        for nome, dados in trocas.items():
            pos, lba, tam = reg[nome]
            setores = (len(dados) + S - 1) // S
            if setores > (tam + S - 1) // S:
                lba, fim = fim // S, fim + setores * S
            fo.seek(lba * S)
            fo.write(dados.ljust(setores * S, b"\0"))
            fo.seek(pos + 2)
            fo.write(struct.pack("<I", lba) + struct.pack(">I", lba) + struct.pack("<I", len(dados))
                     + struct.pack(">I", len(dados)))
        fo.truncate(fim)
        fo.seek(16 * S + 80)  # tamanho do volume
        fo.write(struct.pack("<I", fim // S) + struct.pack(">I", fim // S))
    os.replace(tmp, saida)
    return saida


def _remendos_vizinhos(iso: Path, resultado: Path, copias: list, inicios: list, faixas: list[tuple[int, int]],
                       janela: int) -> list:
    """O resto do pedaço onde cada arquivo traduzido está também vem do disco original e é repetido dentro dele.
    Melhor palpite para esses trechos: o mesmo arquivo na ISO do usuário — achado comparando setores do resultado
    com setores da ISO (cada arquivo começa num setor). Medido no Deck: a fonte do God of War saiu com 907 bytes
    diferentes da russa (só as letras trocadas) contra 3150 sem este passo."""
    alvo = set()
    for onde, n in faixas:
        alvo.update(range(onde // janela, (onde + n - 1) // janela + 1))
    if not alvo:
        return []
    indice: dict[bytes, int] = {}
    repetidos = set()
    with open(iso, "rb") as f:
        k = 0
        while True:
            b = f.read(S)
            if not b:
                break
            chave = b[:48]
            if len(set(chave)) > 4:
                if chave in indice:
                    repetidos.add(chave)
                else:
                    indice[chave] = k
            k += 1
    for chave in repetidos:
        indice.pop(chave, None)
    out = []
    with open(resultado, "rb") as fp, open(iso, "rb") as fr:
        for w in sorted(alvo):
            fp.seek(w * janela)
            bloco = fp.read(janela)
            achados = []  # (setor no resultado, deslocamento até o setor da ISO)
            for s in range(0, len(bloco), S):
                r = indice.get(bloco[s:s + 48])
                if r is not None:
                    achados.append(((w * janela + s) // S, r - (w * janela + s) // S))
            if not achados:
                continue
            setores = [a[0] for a in achados]
            k = max(0, bisect.bisect_left(inicios, w * janela) - 1)
            while k < len(copias) and copias[k][0] < (w + 1) * janela:
                t, x, n = copias[k]
                k += 1
                i = bisect.bisect_right(setores, t // S) - 1
                if i < 0 or t < w * janela:
                    continue
                fr.seek(t + achados[i][1] * S)
                out.append((x, fr.read(n)))
    return out


# ------------------------------------------------------------------------------------------------ fluxo
def aplicar(iso: Path, patch: Path, saida: Path, trabalho: Path, receita: dict | None = None, log=print) -> dict:
    """Aplica o patch; se o disco não é o original que ele pede, leva só os arquivos da receita para a ISO do usuário.
    Devolve {"modo": "exato"|"transplante", "arquivos": n, "saida": caminho}."""
    from .. import vcdiff
    trabalho.mkdir(parents=True, exist_ok=True)
    resultado = trabalho / "resultado-do-patch.iso"
    copias: list = []
    log("aplicando o patch (pode levar 1 min)…")
    rel = vcdiff.aplicar(iso, patch, resultado, copias=copias)
    try:
        if not rel["bytes_errados"]:
            os.replace(resultado, saida)
            return {"modo": "exato", "arquivos": 0, "saida": str(saida)}
        cod = codigo_disco(iso)
        receita = receita or RECEITAS.get(cod or "")
        log(f"o disco não é o original que o patch pede ({len(rel['errados'])} de {rel['janelas']} pedaços não "
            f"conferem); disco {cod}")
        if not receita:
            raise ErroTransplante(f"o patch é para outra versão do disco e não há receita para {cod}: só dá com "
                                  "o disco que o patch pede")
        copias.sort()
        inicios = [c[0] for c in copias]
        with open(iso, "rb") as fr, open(resultado, "rb") as fp:
            reg = registros(fr)
            m = mmap.mmap(fp.fileno(), 0, access=mmap.ACCESS_READ)
            try:
                nomes = sorted(n for n in reg if any(fnmatch.fnmatch(n, p) for p in receita["arquivos"]))
                lugares, perto = {}, None
                for nome in nomes:
                    _pos, lba, tam = reg[nome]
                    fr.seek(lba * S)
                    original = fr.read(tam)
                    onde = achar(m, original, perto)
                    if onde is None:
                        raise ErroTransplante(f"não achei {nome} traduzido no resultado do patch")
                    n = tamanho_real(original, m[onde:onde + 0x28])
                    lugares[nome] = (onde, n, original)
                    perto = onde + n
            finally:
                m.close()
        # 2ª passada: o patch também repete trechos de dentro do próprio resultado; se o trecho veio errado do disco,
        # a repetição herda o erro (visto no Deck: 8% da fonte). Então o disco "lido" pelo patch já recebe, nesses
        # lugares, o byte do arquivo do usuário — e o erro não se espalha.
        remendos = _remendos_vizinhos(iso, resultado, copias, inicios, [(o, n) for o, n, _ in lugares.values()],
                                      rel.get("tamanho_janela", 8 << 20))
        for onde, n, original in lugares.values():
            k = max(0, bisect.bisect_right(inicios, onde) - 1)
            while k < len(copias) and copias[k][0] < onde + n:
                t, x, tam = copias[k]
                a, b = max(t, onde), min(t + tam, onde + n, onde + len(original))
                if a < b:
                    remendos.append((x + (a - t), original[a - onde:b - onde]))
                k += 1
        remendos = list(dict(remendos).items())  # mesmo lugar: vale o do arquivo traduzido (vem por último)
        log("aplicando de novo com os trechos conhecidos…")
        copias2: list = []
        vcdiff.aplicar(iso, patch, resultado, copias=copias2, remendos=remendos)
        copias2.sort()
        inicios2 = [c[0] for c in copias2]
        trocas = {}
        with open(resultado, "rb") as fp:
            for nome, (onde, n, original) in lugares.items():
                fp.seek(onde)
                trocas[nome] = conserta(fp.read(n), onde, original, copias2, inicios2)
        log(f"{len(trocas)} arquivo(s) traduzidos levados para o seu disco")
        montar(iso, trocas, saida)
        return {"modo": "transplante", "arquivos": len(trocas), "saida": str(saida)}
    finally:
        resultado.unlink(missing_ok=True)


def main(argv: list[str]) -> int:
    """python3 -m dc.traducao.transplante <iso> <patch.xdelta> <saida.iso>"""
    if len(argv) != 3:
        print(main.__doc__)
        return 2
    saida = Path(argv[2])
    r = aplicar(Path(argv[0]), Path(argv[1]), saida, saida.parent / ".dc-transplante")
    print(r)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
