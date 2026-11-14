"""Monitor/TV ligado ou tirado COM O DECK RODANDO: reage na hora (o serviço de energia chama a cada 30 s).

- energia (TDP) do jogo aberto muda na hora: máximo na dock, o do console no portátil;
- aviso na tela do Deck (o plugin mostra o launch-error.json com título);
- a resolução os emuladores só leem ao abrir: entra ao reabrir o jogo (com "continuar de onde parou" ligado,
  reabrir volta no mesmo ponto).
Rascunho da IA local (qwen2.5-coder:7b), corrigido: avisava a cada 30 s, primeira leitura contava como troca,
variável sem valor quando não havia jogo, gravação não atômica.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .paths import Paths
from .tdp import TDP_POR_CONSOLE, Tdp, em_dock


def _gravar(f: Path, dados: dict) -> None:
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_name(f.name + ".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False), "utf-8")
    os.replace(tmp, f)


def _ler(f: Path):
    try:
        return json.loads(f.read_text("utf-8"))
    except (OSError, ValueError):
        return None


def verificar(paths: Paths, detectar=em_dock, tdp_factory=Tdp) -> str | None:
    try:
        estado_f = paths.state / "dock-estado.json"
        atual = bool(detectar())
        anterior = _ler(estado_f)
        if not isinstance(anterior, dict) or "dock" not in anterior:
            _gravar(estado_f, {"dock": atual})
            return None  # primeira leitura não é troca
        if bool(anterior["dock"]) == atual:
            return None
        _gravar(estado_f, {"dock": atual})

        jogo = _ler(paths.state / "jogo-aberto.json")
        jogo = jogo if isinstance(jogo, dict) and jogo.get("console") else None
        extra = ""
        if jogo and not (paths.config / "tdp-desligado").exists() and (paths.state / "tdp-anterior.json").exists():
            try:
                ctl = tdp_factory(paths.state / "tdp-anterior.json")
                watts = (ctl.maximo() or 15) if atual else TDP_POR_CONSOLE.get(jogo["console"], 15)
                ctl.definir(watts)
                extra = f" · energia {watts} W"
            except Exception as e:  # noqa: BLE001 — energia nunca derruba o serviço
                extra = f" · energia: não ajustei ({e})"

        nome = (jogo or {}).get("title") or "Jogo"
        if atual:
            titulo = "Deck Commander — monitor conectado"
            msg = (f"{nome}: energia no máximo agora. A resolução de TV entra quando você fechar e abrir o jogo."
                   if jogo else "Os próximos jogos abrem com resolução de TV e energia no máximo.")
        else:
            titulo = "Deck Commander — modo portátil"
            msg = (f"{nome}: energia de volta ao normal do console. A resolução volta ao normal quando você "
                   "fechar o jogo." if jogo else "Os próximos jogos abrem no modo portátil.")
        _gravar(paths.data / "launch-error.json", {"title": titulo, "message": msg})
        return f"dock: {'conectado' if atual else 'desconectado'}{extra}"
    except Exception as e:  # noqa: BLE001
        return f"dock: erro {e}"
