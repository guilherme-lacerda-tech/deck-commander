"""Tradução da COMUNIDADE primeiro (regra do usuário, 14/11/2026: "a cada jogo tem que fazer isso").

Todo jogo novo que não está em português entra nesta fila antes da tradução por IA. Quem procura é a tarefa agendada
do PC (o Claude, com busca na internet): ela lê a fila pelo SSH, procura uma tradução PT-BR feita por fãs (João13,
romhacking.net.br, PO.B.R.E…), baixa SÓ o patch (nunca jogo/ISO), confere se é para a mesma versão do disco, aplica
e marca o resultado aqui. Se o PC estiver desligado, a fila espera; quando ele liga, a tarefa roda.

Situações: procurar -> aplicado | nao_existe | precisa_voce (achou, mas o site só baixa com clique no navegador, ou o
patch é de outra versão do disco) | sem_resposta (passou ESPERA_MAX_H sem o PC procurar).
Com nao_existe ou sem_resposta, a tradução por IA começa sozinha (como antes desta regra).

    python3 -m dc.traducao.comunidade listar                       -> JSON com os jogos esperando busca
    python3 -m dc.traducao.comunidade marcar <jogo> <situação> [nota]
    python3 -m dc.traducao.comunidade aplicar <jogo> <patch> [<arquivo do disco>]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ESPERA_MAX_H = 72
SITUACOES = ("procurar", "aplicado", "nao_existe", "precisa_voce", "sem_resposta")
LIBERA_IA = ("nao_existe", "sem_resposta")


def _arq(paths) -> Path:
    return paths.state / "comunidade.json"


def carregar(paths) -> dict:
    try:
        return json.loads(_arq(paths).read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def salvar(paths, dados: dict) -> None:
    tmp = _arq(paths).with_suffix(".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=1), "utf-8")
    tmp.replace(_arq(paths))


def serial(rom: str) -> str:
    """Código do disco (ex.: SLUS_005.94) pelo SYSTEM.CNF — a tradução de fã é feita para UMA versão do disco."""
    try:
        from ..content import system_cnf
        p = Path(rom)
        if p.suffix.lower() in (".m3u", ".cue"):
            alvo = p.parent / p.read_text("utf-8", "replace").split()[0] if p.suffix.lower() == ".m3u" else p
            if alvo.suffix.lower() == ".cue":
                import re
                m = re.search(r'FILE\s+"([^"]+)"', alvo.read_text("utf-8", "replace"))
                alvo = alvo.parent / m.group(1) if m else alvo
            p = alvo
        cnf = system_cnf(p) or b""
        import re
        m = re.search(rb"(?i)(S[LC][A-Z]{2}[_-]\d{3}\.?\d{2})", cnf)  # o MGS russo grava "slus_005.94"
        return m.group(1).decode().upper() if m else ""
    except Exception:  # noqa: BLE001 — sem código: a busca usa só o nome
        return ""


def registrar(paths, gid: str, entrada: dict) -> bool:
    """Põe o jogo na fila de busca. False se ele já passou por ela."""
    dados = carregar(paths)
    if gid in dados:
        return False
    dados[gid] = {"titulo": entrada.get("title", gid), "console": entrada.get("console", ""),
                  "rom": entrada.get("rom", ""), "serial": serial(entrada.get("rom", "")),
                  "situacao": "procurar", "desde": time.time()}
    salvar(paths, dados)
    return True


def esperando(paths, gid: str, agora: float | None = None) -> bool:
    """A IA ainda espera a busca da comunidade para este jogo?"""
    e = carregar(paths).get(gid)
    if not e:
        return False
    if e["situacao"] == "procurar":
        return (agora or time.time()) - e.get("desde", 0) < ESPERA_MAX_H * 3600
    return e["situacao"] not in LIBERA_IA


def pendentes(paths) -> dict:
    return {g: e for g, e in carregar(paths).items() if e["situacao"] == "procurar"}


def marcar(paths, gid: str, situacao: str, nota: str = "", store=None) -> str:
    if situacao not in SITUACOES:
        raise ValueError(f"situação inválida: {situacao} (use {', '.join(SITUACOES)})")
    dados = carregar(paths)
    if gid not in dados:
        raise KeyError(f"{gid} não está na fila da comunidade")
    e = dados[gid]
    e.update(situacao=situacao, nota=nota, quando=time.time())
    titulo = e.get("titulo", gid)
    aviso = {
        "aplicado": f"🇧🇷 {titulo}: achei a tradução da comunidade e apliquei. {nota}".strip(),
        "nao_existe": f"🔎 {titulo}: não existe tradução da comunidade. A IA vai traduzir. {nota}".strip(),
        "precisa_voce": f"🔎 {titulo}: achei a tradução da comunidade, mas preciso de você: {nota}".strip(),
        "sem_resposta": f"🔎 {titulo}: o PC não procurou a tradução em {ESPERA_MAX_H} h. A IA vai traduzir.",
    }.get(situacao)
    if aviso:
        e["avisar"] = aviso
    salvar(paths, dados)
    linhas = [aviso or f"{titulo}: {situacao}"]
    if situacao in LIBERA_IA:
        linhas += _liberar_ia(paths, gid, store)
    return "\n".join(linhas)


def _liberar_ia(paths, gid: str, store=None) -> list[str]:
    from ..store import Store
    from . import run
    return run.auto_queue(paths, store or Store(paths.db), [gid])


def vencidos(paths, store=None, agora: float | None = None) -> list[str]:
    """Chamado de hora em hora pelo serviço: busca que o PC não fez em ESPERA_MAX_H libera a IA."""
    agora = agora or time.time()
    out = []
    for gid, e in pendentes(paths).items():
        if agora - e.get("desde", 0) >= ESPERA_MAX_H * 3600:
            out.append(marcar(paths, gid, "sem_resposta", store=store))
    return out


def avisos(paths) -> list[str]:
    """Mensagens novas para o Telegram (o bot manda e elas saem daqui)."""
    dados = carregar(paths)
    msgs = [e.pop("avisar") for e in dados.values() if e.get("avisar")]
    if msgs:
        salvar(paths, dados)
    return msgs


def aplicar(paths, gid: str, patch: Path, disco: Path | None = None, store=None) -> str:
    """Aplica o patch da comunidade e publica a cópia "(PT-BR)" no lugar do original (como a tradução por IA)."""
    from .. import patches, syncer
    from ..remove import hide
    from ..store import Store
    from . import run
    lm = json.loads((paths.data / "launch-map.json").read_text("utf-8"))
    g = lm[gid]
    rom_lib = Path(g["rom"])
    alvo = Path(disco) if disco else rom_lib
    if alvo.suffix.lower() in (".m3u", ".cue"):
        raise ValueError("jogo de disco em .m3u/.cue: diga qual arquivo do disco recebe o patch (.bin/.iso)")
    saida = alvo.with_name(f"{alvo.stem} (PT-BR){alvo.suffix}")
    feito = patches.apply_file(alvo, Path(patch), saida)
    publicado = _montar_discos(rom_lib, alvo, Path(feito))
    store = store or Store(paths.db)
    op = store.enqueue("library-add", {"from": f"comunidade:{gid}"})
    store.claim(op)
    syncer.add_to_steam(paths, store, op)
    store.finish(op, True)
    hide(paths, gid, "substituído pela tradução da comunidade (PT-BR)")
    run._herdar_detonado(paths, gid, publicado)
    return marcar(paths, gid, "aplicado", f"Jogo novo: {publicado.stem}", store=store)


def _montar_discos(rom_lib: Path, alvo: Path, feito: Path) -> Path:
    """Disco de CD (.cue/.m3u): cria o .cue "(PT-BR)" que aponta para o disco traduzido e, em jogo de vários CDs,
    um .m3u "(PT-BR)" com os CDs já traduzidos (os outros continuam os originais). Devolve o que vai para a
    biblioteca. Imagem solta (.iso/.chd...) é o próprio arquivo traduzido."""
    suf = rom_lib.suffix.lower()
    if suf not in (".cue", ".m3u"):
        return feito
    if suf == ".m3u":
        cues = [rom_lib.parent / ln.strip() for ln in rom_lib.read_text("utf-8", "replace").splitlines()
                if ln.strip() and not ln.startswith("#")]
    else:
        cues = [rom_lib]
    novos = []
    for c in cues:
        pt = c.with_name(f"{c.stem} (PT-BR).cue")
        texto = c.read_text("utf-8", "replace")
        if f'"{alvo.name}"' in texto and c.parent == alvo.parent:
            pt.write_text(texto.replace(f'"{alvo.name}"', f'"{feito.name}"'), "utf-8")
        novos.append(pt if pt.exists() else c)
    if suf == ".cue":
        return novos[0]
    m3u = rom_lib.with_name(f"{rom_lib.stem} (PT-BR).m3u")
    m3u.write_text("\n".join(n.relative_to(rom_lib.parent).as_posix() for n in novos) + "\n", "utf-8")
    return m3u


def main(argv: list[str]) -> int:
    from ..paths import get_paths
    paths = get_paths().ensure()
    if argv[:1] == ["listar"]:
        print(json.dumps(pendentes(paths), ensure_ascii=False, indent=1))
    elif argv[:1] == ["marcar"] and len(argv) >= 3:
        print(marcar(paths, argv[1], argv[2], " ".join(argv[3:])))
    elif argv[:1] == ["aplicar"] and len(argv) in (3, 4):
        print(aplicar(paths, argv[1], Path(argv[2]), Path(argv[3]) if len(argv) == 4 else None))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
