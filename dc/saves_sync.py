"""Sincronização de saves Deck ↔ PC de um jogo (quem decide é o Deck; quem copia é o PC, com backup).

    python3 -m dc.saves_sync plano <game_id>       (entrada: JSON {destino: {sha256, mtime}} dos saves do PC)
    python3 -m dc.saves_sync confirmar <game_id>   (entrada: JSON igual, do PC DEPOIS das cópias)
    python3 -m dc.saves_sync escolher <game_id> deck|pc   (resolve conflito: qual lado vale)

A regra (dc.saves_regra, escrita pela IA local e revisada) nunca apaga e nunca sobrescreve quando os dois lados mudaram:
nesse caso é "conflito" e o usuário escolhe pelo bot (/saves <jogo> deck|pc).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from . import saves_regra
from .paths import Paths, get_paths


def _dir(paths: Paths) -> Path:
    d = paths.data / "saves-sync"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load(p: Path, default):
    try:
        return json.loads(p.read_text("utf-8"))
    except (OSError, ValueError):
        return default


def _save(p: Path, data) -> None:
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    tmp.replace(p)


def saves_do_deck(game_id: str) -> dict[str, dict]:
    """destino -> {sha256, mtime, caminho} dos saves deste jogo no Deck (mesma lista da transferência)."""
    import hashlib
    from . import transferir
    man = transferir.preparar(game_id, com_hash=False, so_dados=True)  # só saves: sem listar o jogo inteiro
    out = {}
    for a in man.get("arquivos", []):
        if a.get("categoria") == "save":
            h = hashlib.sha256()
            try:
                with open(a["origem"], "rb") as f:
                    for bloco in iter(lambda f=f: f.read(1 << 20), b""):
                        h.update(bloco)
            except OSError:
                continue  # o jogo apagou/trocou o arquivo entre a lista e a leitura: fica para a próxima vez
            out[a["destino"]] = {"sha256": h.hexdigest(), "mtime": int(a.get("mtime") or 0), "caminho": a["origem"]}
    return out


def plano(paths: Paths, game_id: str, pc: dict) -> dict:
    deck = saves_do_deck(game_id)
    ultimo = _load(_dir(paths) / f"{game_id}.json", {})
    forcar = _load(_dir(paths) / "escolhas.json", {}).get(game_id)  # conflito resolvido pelo usuário: lado que vale
    acoes = saves_regra.decidir(deck, pc, ultimo)
    for a in acoes:
        if a["acao"] == "conflito" and forcar in ("deck", "pc"):
            a["acao"], a["motivo"] = ("deck->pc" if forcar == "deck" else "pc->deck"), f"você escolheu o {forcar.upper()}"
        a["caminho_deck"] = (deck.get(a["destino"]) or {}).get("caminho")
    conflitos = [a["destino"] for a in acoes if a["acao"] == "conflito"]
    pend = _load(_dir(paths) / "conflitos.json", {})
    if conflitos:
        pend[game_id] = conflitos
    else:
        pend.pop(game_id, None)
    _save(_dir(paths) / "conflitos.json", pend)
    return {"acoes": acoes, "resumo": saves_regra.resumo(acoes),
            "base_deck": _base_emu(deck)}


def _base_emu(deck: dict) -> str | None:
    """Pasta real do {EMU} no Deck (para criar save novo que só existe no PC)."""
    for destino, d in deck.items():
        if destino.startswith("{EMU}/") and d.get("caminho", "").endswith(destino[len("{EMU}"):]):
            return d["caminho"][: -len(destino[len("{EMU}"):])]
    return None


def confirmar(paths: Paths, game_id: str, pc_final: dict) -> dict:
    deck = saves_do_deck(game_id)
    novo = saves_regra.novo_ultimo(deck, pc_final)
    _save(_dir(paths) / f"{game_id}.json", novo)
    esc = _load(_dir(paths) / "escolhas.json", {})
    if esc.pop(game_id, None):
        _save(_dir(paths) / "escolhas.json", esc)
    return {"sincronizados": len(novo)}


def escolher(paths: Paths, game_id: str, lado: str) -> str:
    if lado not in ("deck", "pc"):
        raise ValueError("diga deck ou pc")
    esc = _load(_dir(paths) / "escolhas.json", {})
    esc[game_id] = lado
    _save(_dir(paths) / "escolhas.json", esc)
    return f"Combinado: na próxima sincronização vale o save do {lado.upper()}."


def auto_ligado(paths: Paths, game_id: str) -> bool:
    """Sincronizar sozinho ao fechar o jogo: só jogos já sincronizados uma vez (existem nos dois lados) e se o usuário
    não desligou (/saves auto nao)."""
    return (_dir(paths) / f"{game_id}.json").exists() and not (paths.config / "saves-auto-desligado").exists()


def pedir_ao_fechar(paths: Paths, game_id: str, titulo: str, segundos: float) -> bool:
    """Chamado pelo launch quando o jogo fecha: põe a sincronização na fila (o PC faz quando estiver ligado)."""
    if segundos < 60 or not auto_ligado(paths, game_id):
        return False
    from . import transferir
    transferir.enfileirar(game_id, titulo, direcao="saves", auto=True)
    return True


def conflitos(paths: Paths) -> dict:
    return _load(_dir(paths) / "conflitos.json", {})


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if len(argv) < 2 or argv[0] not in ("plano", "confirmar", "escolher"):
        print(__doc__, file=sys.stderr)
        return 2
    paths = get_paths()
    try:
        if argv[0] == "escolher":
            print(escolher(paths, argv[1], argv[2] if len(argv) > 2 else ""))
            return 0
        entrada = json.loads(sys.stdin.read().lstrip("﻿") or "{}")
        out = plano(paths, argv[1], entrada) if argv[0] == "plano" else confirmar(paths, argv[1], entrada)
    except (ValueError, KeyError, FileNotFoundError) as e:  # entrada ruim / jogo fora da biblioteca: mensagem clara
        print(json.dumps({"erro": str(e), "acoes": [], "resumo": f"Não deu para sincronizar: {e}"}, ensure_ascii=False))
        return 1
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
