"""Tradução PT-BR do Castlevania: Symphony of the Night (PS1) — engenharia reversa de 11/11/2026.

O texto do jogo fica em DRA.BIN (itens, menus, descrições), BOSS/*/*.BIN e ST/*/*.BIN (diálogos de cada fase), em dois
formatos (dc.traducao.eng_sotn). Cada trecho traduzido ocupa EXATAMENTE os bytes do original (sem acento: a fonte
do jogo só tem ASCII), então nenhum ponteiro nem tamanho de arquivo muda e o disco novo é uma cópia "(PT-BR)" do
.bin/.cue ao lado do original (o original nunca é tocado).
"""
from __future__ import annotations

import re
from pathlib import Path

from ..paths import Paths
from . import eng_sotn as S
from . import ia
from .psx_disco import Disco, gravar_cue
from .rts import RtsReport

SERIAIS = ("SLES_005.24", "SLUS_000.67", "SLES_005.25", "SLES_005.26", "SLES_005.27")  # SOTN EUR/EUA
_PULA = re.compile(r"(^|/)(F_|SD_)|\.(STR|XA|VB|VH|TIM|CCS|DA)$", re.IGNORECASE)


def _bin_da_cue(cue: Path) -> Path:
    m = re.search(r'FILE\s+"([^"]+)"\s+BINARY', cue.read_text("utf-8", "replace"))
    if not m:
        raise ValueError("cue sem FILE … BINARY")
    return cue.with_name(m.group(1))


def reconhece(rom: Path) -> bool:
    """É o SOTN de PS1? (lê o SYSTEM.CNF do disco)"""
    try:
        b = _bin_da_cue(rom) if rom.suffix.lower() == ".cue" else rom
        cnf = Disco(b).ler("SYSTEM.CNF").decode("ascii", "replace").upper()
    except (OSError, ValueError, KeyError, StopIteration):
        return False
    return any(s in cnf for s in SERIAIS)


def coletar(disco: Disco) -> list[S.Trecho]:
    trechos = []
    for nome in sorted(disco.arquivos()):
        if not nome.upper().endswith(".BIN") or _PULA.search(nome) or not (
                nome.upper() == "DRA.BIN" or nome.upper().startswith(("ST/", "BOSS/"))):
            continue
        d = disco.ler(nome)
        trechos += sem_sobreposicao(S.achar_menos20(nome, d) + S.achar_ascii(nome, d))
    return trechos


def sem_sobreposicao(trechos: list[S.Trecho]) -> list[S.Trecho]:
    """Os dois leitores podem pegar o mesmo pedaço (falha real: DRA.BIN @260864): fica o primeiro da lista
    (nomes em -0x20 têm prioridade, porque terminam no 0xFF exato) e cai quem encostar nele."""
    ocupado: list[tuple[int, int]] = []
    out = []
    for t in trechos:
        if any(t.pos < fim and ini < t.pos + t.tam for ini, fim in ocupado):
            continue
        ocupado.append((t.pos, t.pos + t.tam))
        out.append(t)
    return sorted(out, key=lambda t: t.pos)


def agrupar(trechos: list[S.Trecho], dados: dict[str, bytes]) -> list[list[S.Trecho]]:
    """Junta as linhas de uma mesma fala (trechos ASCII separados só por códigos de controle curtos, sem 0x00),
    para a IA traduzir a frase inteira e não pedaços soltos ("Whatever we do," + "the castle…")."""
    grupos: list[list[S.Trecho]] = []
    for t in sorted(trechos, key=lambda x: (x.arquivo, x.pos)):
        g = grupos[-1] if grupos else None
        if g and t.tipo == "ascii" and g[-1].tipo == "ascii" and g[-1].arquivo == t.arquivo:
            vao = dados[t.arquivo][g[-1].pos + g[-1].tam:t.pos]
            # até 12 bytes só de códigos de controle (quebra de linha + recuo, pausa, cor…): mesma caixa de fala.
            # Juntas, as linhas somam o espaço de todas — a frase traduzida se espalha por elas.
            if 0 < len(vao) <= 12 and all(0 < b < 0x20 for b in vao):
                g.append(t)
                continue
        grupos.append([t])
    return grupos


def distribuir(texto: str, grupo: list[S.Trecho]) -> list[str]:
    """Reparte a frase traduzida pelas linhas originais (cada linha cabe no espaço dela; palavra inteira)."""
    palavras = texto.split()  # (os acentos ficam: codificar() decide o que cada fonte consegue mostrar)
    saida = []
    for k, t in enumerate(grupo):
        linha = ""
        while palavras:
            cand = (linha + " " + palavras[0]).strip()
            if len(S.codificar(cand, 10 ** 4, t.tipo, t.sjis).rstrip()) > t.tam and linha:
                break
            linha = cand
            palavras.pop(0)
            if k == len(grupo) - 1:
                continue
        saida.append(linha)
    if palavras and saida:  # sobrou: vai para a última linha (codificar corta no espaço que couber)
        saida[-1] = (saida[-1] + " " + " ".join(palavras)).strip()
    return saida


def _bios() -> bytes | None:
    """BIOS do PS1 do próprio usuário (DuckStation): as letras acentuadas das falas nascem das letras dele."""
    for pasta in (Path.home() / "Emulation/bios", Path.home() / ".local/share/duckstation/bios"):
        for nome in ("SCPH1001.BIN", "scph1001.bin", "SCPH7502.BIN", "scph7502.bin", "SCPH5501.BIN", "scph5501.bin"):
            p = pasta / nome
            if p.exists() and p.stat().st_size == 512 * 1024:
                return p.read_bytes()
    return None


def cabe(texto: str, grupo: list[S.Trecho]) -> bool:
    """A frase inteira cabe nas linhas do grupo, sem cortar palavra?"""
    linhas = distribuir(texto, grupo)
    return len(linhas) == len(grupo) and all(
        len(S.codificar(l, 10 ** 4, t.tipo, t.sjis).rstrip(b" \x00")) <= t.tam for l, t in zip(linhas, grupo))


def _completar(paths, cfg, chain, faltam: dict[str, str], por_texto, ids, res, progress) -> dict[str, str]:
    """2ª e 3ª chance para o que ficou em inglês: tradução sem limite + encurtar (até 3 vezes) até caber de
    verdade. Devolve {id: tradução que cabe}."""
    if not faltam:
        return {}
    grupo_de = {iid: min(por_texto[ids[iid]], key=lambda g: sum(t.tam for t in g)) for iid in faltam}
    # já veio uma tradução (que não coube)? começa por ela; senão traduz de novo sem limite
    longa = {iid: txt for iid, txt in faltam.items() if txt.strip() and txt != ids[iid]}
    sem = [ia.Item(iid, ids[iid]) for iid in faltam if iid not in longa]
    if sem:
        longa.update(ia.translate(paths, cfg, sem, "sotn-2a-chance", chain=chain, progress=progress).translated)
    ok: dict[str, str] = {}
    guardados = _encurtados(paths)
    for iid, txt in longa.items():
        g = grupo_de[iid]
        # ordem: glossário à mão (inteiro ou linha a linha) > encurtado de antes > a tradução que veio
        for cand in (GLOSSARIO.get(ids[iid]), " ".join(GLOSSARIO.get(t.texto, "\0") for t in g),
                     guardados.get(ids[iid]), txt):
            a = ajustar(cand, g) if cand and cand.strip() and "\0" not in cand else None
            if a:
                ok[iid] = a
                break
    pendentes = {iid: longa[iid] for iid in longa if iid not in ok and longa[iid].strip()}
    for _ in range(5):  # encurtar com o limite real (bytes de todas as linhas), conferindo com ajustar()
        if not pendentes:
            break
        pedidos = [(iid, txt, 1, max(4, int(sum(t.tam for t in grupo_de[iid]) * 0.85)))
                   for iid, txt in pendentes.items()]
        curtos = ia.shorten(paths, cfg, pedidos, lambda i, s: ajustar(s, grupo_de[i]) is not None, chain=chain)
        for iid, txt in curtos.items():
            ok[iid] = ajustar(txt, grupo_de[iid]) or txt
            guardados[ids[iid]] = ok[iid]
            pendentes.pop(iid, None)
    _guardar_encurtados(paths, guardados)
    # último recurso (nunca deixa em inglês): sem acento e cortada em palavra inteira — contada no relatório
    for iid, txt in pendentes.items():
        ok[iid] = S.sem_acento(txt)
        CORTADAS.append(ids[iid])
    return ok


def _arq_encurtados(paths) -> Path | None:
    return Path(paths.data) / "traducao" / "cache" / "sotn-encurtados.json" if paths is not None else None


def _encurtados(paths) -> dict[str, str]:
    """Encurtamentos que já deram certo (inglês -> PT que cabe): refazer o disco não pede tudo de novo à IA."""
    import json
    p = _arq_encurtados(paths)
    try:
        return json.loads(p.read_text("utf-8")) if p and p.exists() else {}
    except (OSError, ValueError):
        return {}


def _guardar_encurtados(paths, d: dict[str, str]) -> None:
    import json
    p = _arq_encurtados(paths)
    if p:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(d, ensure_ascii=False), "utf-8")


CORTADAS: list[str] = []  # frases que nem encurtando couberam (relatório: devem ser zero ou quase)


def ajustar(texto: str, grupo: list[S.Trecho]) -> str | None:
    """Pedido do usuário 11/11/2026: frase cortada no meio não serve. Cabe como está? Senão, sem acento (nas falas
    cada acento ocupa 2 bytes)? Devolve o texto que cabe inteiro, ou None (aí precisa encurtar)."""
    if cabe(texto, grupo):
        return texto
    s = S.sem_acento(texto)
    return s if cabe(s, grupo) else None


NOMES = {"alucard", "dracula", "maria", "richter", "trevor", "grant", "sypha", "shaft", "death", "lisa", "slogra",
         "gaibon", "akmodan", "galamoth", "beelzebub", "olrox", "granfaloon", "doppleganger", "karasuman", "succubus",
         "scylla", "minotaur", "werewolf", "hippogryph", "lesser", "medusa", "cerberus", "orlox"}


# Glossário escrito à mão (11/11/2026) para nomes curtos de itens/menus onde a IA não acerta a abreviação: cada
# tradução foi contada para caber no espaço do original (nomes: acento = 1 byte; falas/descrições: acento = 2 bytes).
GLOSSARIO = {
    "Alucard mail": "Cota Alucard", "Alucard sword": "Esp. Alucard", "Axe": "Mch", "Axe Knight": "Cav. Mach.",
    "Bone Ark": "Ossuário", "Cancel": "Voltar", "Castle map": "Mapa", "Curse Zone": "Zona Mald.", "CURSE": "MALD.",
    "Dark shield": "Esc. Sombra", "Defeat Akmodan II": "Vença Akmodan II", "Defeat Galamoth": "Vença Galamoth",
    "Defeat Medusa": "Vença Medusa", "Defeat Trevor, Grant & Sypha": "Vença Trevor, Grant & Sypha",
    "Discus Lord": "Lorde Disco", "Dracula tunic": "Túnica Drác.", "Equip": "Armar", "Flail Guard": "Mangualeiro",
    "Flea Man": "Pulgão", "Heart Refresh": "Cura Corações", "Hide cuirass": "Couraça Pele", "Holy mail": "Cota Sta.",
    "Holy rod": "Cetro S.", "Holy sword": "Esp. Santa", "Ice mail": "CotaGelo", "Opal circlet": "Tiara Opala",
    "Phantom Skull": "Caveira Fant.", "Puppet Sword": "Esp. Boneco", "Resist dark": "Res. Trevas",
    "Resist holy": "Res. Santo", "STATUS": "ESTADO", "Spear Guard": "Lanceiro", "Stereo": "Estér.",
    "Stone mask": "Másc.Pedra", "Topaz circlet": "Tiara Topázio",
    "Magic scroll 1": "Pergaminho 1", "Magic scroll 2": "Pergaminho 2", "Magic scroll 3": "Pergaminho 3",
    "Magic scroll 4": "Pergaminho 4", "Magic scroll 5": "Pergaminho 5",
    "-Special Thanks-": "-Agradecimentos-", "Bat Card": "Morcego", "Buy item": "Comprar",
    "Dark Metamorphosis": "Metamorfose Negra", "Demon Card": "C.Demônio", "Ghost Card": "C.Fantasma",
    "Hard iron shield": "Escudo de ferro", "Holy Symbol": "Símbolo S.", "Immune to curses": "Imune a feitiço",
    "Merman Statue": "Est. Tritão", "No game": "Vazio", "Skill of Wolf": "Técnica Lobo", "Soul of Bat": "Alma Morc.",
    "Summon Spirit": "Invocar Alma", "Tetra Spirit": "Tetra Alma", "Unholy dark shield": "Escudo profano",
    "Zwei hander": "Montante", "no data": "Vazio", "not yet": "Espere",
    # pedaços de fala que ficam sozinhos (o resto da caixa vem depois de um código de pausa/cor) — à mão, no contexto
    "Open Hell's gate!": "Abram o Inferno!", "So he": "Ele", "sure he's here.": "ele está aqui.",
    "true feelings then": "seu sentimento,", "meet again": "nos vemos", "I'll feast on": "devorarei",
    "Well met,": "Salve,", "human side": "humanidade", "but my goal is": "mas meu fim é",
    "This world must be": "Este mundo será", "How is": "Como", "learn what caused": "saber a causa da",
    "Richter's madness.": "loucura de Richter", "I'm glad your": "Que bom que", "I can't let him": "Não o deixarei",
    # 11/11/2026: o que saiu cortado na 1ª regeração (nem a IA encurtando coube) — à mão, linha a linha
    "If those are your": "Se esse é", "so be it.": "Que seja.", "perhaps we'll": "talvez", "and join me": "e venha!",
    "Then for the Master,": "Então, pelo Mestre,", "Alucard!": "Alucard!", "not until I": "não até eu",
    "would not see each other again.": "não nos veríamos mais.", "but I found a Belmont...": "mas achei um Belmont...",
    "Count Dracula rises but once every": "Drácula só renasce uma vez a cada",
    "No Alucard! Don't come here!": "Não, Alucard! Não venha!", "remaking this world!": "refazendo o mundo!",
    "Heart broach": "Broche Cor.", "Beryl circlet": "Tiara Berilo", "Platinum mail": "Cota Platina",
    "Iron cuirass": "Couraça Fer.", "Final Save point": "Salvar Final", "Defeat Succubus": "Vença Succubus",
    "Defeat Beelzebub": "Vença Beelzebub", "Defeat Scylla": "Vença Scylla", "Defeat Olrox": "Vença Olrox",
    "Killer Fish": "Peixe Mat.", "Fake Grant": "Grant Fal.", "Medusa Head": "Cab.Medusa",
    "Blade Soldier": "Sold.Lâmina", "Enemy list": "Inimigos", "Custom cloak settings": "Ajustar a capa",
    "Select file": "Escolha", "Copying data.": "Copiando...", "File erased.": "Apagado.",
    # 2ª regeração (11/11/2026): as 21 que ainda saíam cortadas — medidas linha a linha no disco
    "Come forth my": "Venham, meus", "I'm certain that was": "Tenho certeza: era", "a Belmont.": "Belmont.",
    "and I'm": "e acho", "if you": "se", "live that long.": "viver até lá.", "How?": "Como",
    "data found.": "dados.", "Overwrite data?": "Sobrescrever?", "Library card": "Cartão Bibl.",
    "Castlevania pot roast [use]": "Assado do castelo [usar]", "Summons Dawn Warriors [1]": "Invoca Guerreiros [1]",
    "Defeat Granfaloon": "Vença Granfaloon", "Fake Sypha": "Sypha Fal.", "Fake Trevor": "Trevor Fal.",
    "but I": "mas", "found a Belmont...": "vi um Belmont...", "No Alucard!": "Alucard!",
    "Don't come here!": "Não venha aqui!", "Dark Priest of Dracula.": "Sacerdote de Drácula.",
    "Flame demon.": "Demônio.", "Giant vampire bat.": "Morcego gigante.",
    "Well armored axe knight.": "Cavaleiro de machado.", "Save error.": "Não salvou", "to copy to?": "copiar?",
}
IGUAIS = {"CON", "INT", "EXP", "Exp", "STR", "LCK", "DEF", "ATT", "HP", "MP", "Def HP", "Mono", "Long"}  # iguais em PT


def _so_nome(texto: str) -> bool:
    """Nome próprio / créditos / texto interno: fica igual em português (não é 'resto em inglês')."""
    palavras = [w.lower() for w in re.findall(r"[A-Za-z]+", texto)]
    if texto.strip() in IGUAIS:
        return True
    if not S.parece_texto(texto) or re.search(r"[0-9].*[A-Z].*[0-9]|[a-z][A-Z][a-z]", texto):  # dado, não texto
        return True
    if palavras and all(w in NOMES for w in palavras):
        return True
    if texto.isupper() and len(palavras) >= 2:  # nomes da equipe nos créditos (SHIGERU FUKUTAKE…)
        return True
    return bool(re.search(r"\b(load|set ok|dummy|debug|test)\b", texto, re.IGNORECASE) and len(palavras) <= 3)


def retoque(paths: Paths, rom_original: Path, rom_pt: Path, chain=None, progress=lambda d, t: None) -> dict:
    """Passa de novo na cópia PT-BR: tudo que ainda está igual ao inglês (menos nomes) é traduzido SOZINHO, com o
    limite exato de letras e até 3 encurtamentos. Regrava a cópia (o original nunca é tocado)."""
    cfg = ia.load_cfg(paths)
    b_orig = _bin_da_cue(rom_original) if rom_original.suffix.lower() == ".cue" else rom_original
    b_pt = _bin_da_cue(rom_pt) if rom_pt.suffix.lower() == ".cue" else rom_pt
    originais = {t.texto for t in coletar(Disco(b_orig))}
    disco_pt = Disco(b_pt)
    resto = [t for t in coletar(disco_pt) if t.texto in originais and not _so_nome(t.texto)]
    if not resto:
        return {"restavam": 0, "traduzidos": 0}
    trocas: dict[str, list[tuple[S.Trecho, str]]] = {}
    feitos: dict[str, str] = {}
    # 1) glossário feito à mão (nomes curtos de itens/menus), só se couber de verdade
    sobra = []
    for t in resto:
        pt = GLOSSARIO.get(t.texto)
        if pt and len(S.codificar(pt, 10 ** 4, t.tipo, t.sjis).rstrip(b" \x00")) <= t.tam:
            trocas.setdefault(t.arquivo, []).append((t, pt))
            feitos[t.texto] = pt
        else:
            sobra.append(t)
    # 2) pedaços de fala: a caixa de fala INTEIRA (do disco original) é traduzida de novo, com contexto
    dados_orig = {}
    disco_orig = Disco(b_orig)
    todos_orig = coletar(disco_orig)
    for nome in {t.arquivo for t in sobra if t.tipo == "ascii"}:
        dados_orig[nome] = disco_orig.ler(nome)
    grupo_de: dict[tuple[str, int], list[S.Trecho]] = {}
    for g in agrupar([t for t in todos_orig if t.arquivo in dados_orig], dados_orig):
        for t in g:
            grupo_de[(t.arquivo, t.pos)] = g
    grupos_fala, avulsos = {}, []
    for t in sobra:
        g = grupo_de.get((t.arquivo, t.pos))
        if t.tipo == "ascii" and g and len(g) > 1:
            grupos_fala[" ".join(x.texto for x in g)] = g
        else:
            avulsos.append(t)
    # 3) o resto (e as caixas de fala) passam pela 2ª chance + encurtar, conferindo que cabe
    por_texto: dict[str, list[list[S.Trecho]]] = {}
    for txt, g in grupos_fala.items():
        por_texto.setdefault(txt, []).append(g)
    for t in avulsos:
        por_texto.setdefault(t.texto, []).append([t])
    ids = {f"r{n}": txt for n, txt in enumerate(por_texto)}
    novos_txt = _completar(paths, cfg, chain, dict(ids), por_texto, ids, None, progress)
    for iid, novo in novos_txt.items():
        if novo.strip() and S.sem_acento(novo).strip().lower() != ids[iid].strip().lower():
            feitos[ids[iid]] = novo
            for g in por_texto[ids[iid]]:
                for t, linha in zip(g, distribuir(novo, g)):
                    trocas.setdefault(t.arquivo, []).append((t, linha))
    if trocas:
        novos = {nome: S.aplicar(disco_pt.ler(nome), ts) for nome, ts in trocas.items()}
        tmp = b_pt.with_name(b_pt.name + ".retoque")
        disco_pt.gravar_copia(tmp, novos)
        tmp.replace(b_pt)
    return {"restavam": len(resto), "traduzidos": len(feitos)}


def translate_rom(paths: Paths, rom: Path, title: str = "", chain=None, progress=lambda d, t: None,
                  should_pause=lambda: False) -> RtsReport:
    cfg = ia.load_cfg(paths)
    rep = RtsReport(rom=str(rom), encoding="SOTN (ASCII e ASCII-0x20)")
    bin_ = _bin_da_cue(rom) if rom.suffix.lower() == ".cue" else rom
    disco = Disco(bin_)
    trechos = coletar(disco)
    rep.found = rep.candidates = len(trechos)
    rep.strings = rep.candidates  # o run.py lê .strings no relatório (falha real: AttributeError depois de gravar)
    dados = {nome: disco.ler(nome) for nome in {t.arquivo for t in trechos}}
    # cada fala (grupo de linhas) vira UMA frase para a IA; frases iguais em vários lugares traduzem uma vez só
    por_texto: dict[str, list[list[S.Trecho]]] = {}
    for g in agrupar(trechos, dados):
        txt = " ".join(t.texto for t in g)
        if _so_nome(txt):  # nomes, créditos da equipe e textos internos de depuração ficam como estão
            continue
        por_texto.setdefault(txt, []).append(g)
    itens = [ia.Item(f"t{n}", txt, max_len=min(sum(t.tam for t in g) for g in gs))
             for n, (txt, gs) in enumerate(por_texto.items())]
    ids = {f"t{n}": txt for n, txt in enumerate(por_texto)}
    res = ia.translate(paths, cfg, itens, f"sotn-{rom.stem}", ia.load_glossary_jogo(paths, cfg, itens, title),
                       chain=chain, progress=progress, should_pause=should_pause)
    rep.provider = res.provider_used
    traduzidos = dict(res.translated)
    faltam = {iid: txt for iid, txt in ids.items() if iid not in traduzidos or not traduzidos[iid].strip()}
    # falha real 11/11/2026 ("no diálogo tava tudo cortado"): tradução que não cabia era gravada cortada na última
    # palavra. Agora: cabe? sem acento cabe? senão vai para o encurtar (com a tradução que veio).
    for iid, novo in list(traduzidos.items()):
        if iid in faltam or not novo.strip():
            continue
        a = ajustar(novo, min(por_texto[ids[iid]], key=lambda g: sum(t.tam for t in g)))
        if a:
            traduzidos[iid] = a
        else:
            faltam[iid] = novo
            del traduzidos[iid]
    CORTADAS.clear()
    traduzidos.update(_completar(paths, cfg, chain, faltam, por_texto, ids, res, progress))
    rep.errors += [f"{len(CORTADAS)} frase(s) não couberam nem encurtando (cortadas): " + "; ".join(CORTADAS[:5])] \
        if CORTADAS else []
    trocas: dict[str, list[tuple[S.Trecho, str]]] = {}
    for iid, novo in traduzidos.items():
        orig = ids.get(iid)
        if not orig or not novo.strip() or S.sem_acento(novo).strip() == orig.strip():
            continue
        for g in por_texto[orig]:
            for t, linha in zip(g, distribuir(novo, g)):
                trocas.setdefault(t.arquivo, []).append((t, linha))
            rep.translated += 1
    rep.flagged = len(res.flagged)
    rep.errors += res.errors[:3]
    if not trocas:
        rep.errors.append("nenhuma frase traduzida")
        return rep
    novos = {nome: S.aplicar(dados[nome], ts) for nome, ts in trocas.items()}
    from . import sotn_fonte  # nomes e menus com acento: letras novas na fonte 8x8
    novos["BIN/F_GAME.BIN"] = sotn_fonte.com_acentos(disco.ler("BIN/F_GAME.BIN"))
    from . import (
        sotn_imagens,  # botões desenhados da tela de arquivos (File select…) remontados em português
    )
    novos["ST/SEL/F_SEL.BIN"] = sotn_imagens.botoes_em_portugues(disco.ler("ST/SEL/F_SEL.BIN"))
    from . import (
        sotn_falas_fonte,  # falas com acento: tabela de letras novas + rotina de letras com 25 voltas
    )
    bios = _bios()
    if bios:
        dra = novos.get("DRA.BIN") or disco.ler("DRA.BIN")
        exe_nome = next(n for n in disco.arquivos() if n.upper().startswith("SLES_") or n.upper().startswith("SLUS_"))
        novos["DRA.BIN"], novos[exe_nome] = sotn_falas_fonte.aplicar(dra, disco.ler(exe_nome), bios)
    else:
        rep.errors.append("BIOS do PS1 não achado: falas ficaram sem acento")
    rep.flagged = len([i for i in ids if i not in traduzidos])
    stem = rom.stem
    bin_pt = bin_.with_name(f"{stem} (PT-BR).bin")
    disco.gravar_copia(bin_pt, novos)
    if rom.suffix.lower() == ".cue":
        cue_pt = rom.with_name(f"{stem} (PT-BR).cue")
        gravar_cue(rom, cue_pt, bin_pt.name)
        rep.output = str(cue_pt)
    else:
        rep.output = str(bin_pt)
    originais = {t.texto for t in trechos}
    rep.audit_left = sum(1 for t in coletar(Disco(bin_pt)) if t.texto in originais)
    return rep
