"""Tradução de jogos de Switch por MOTOR (engine): Unity, GameMaker, Godot, RE Engine, RPG Maker, CRI.

Cada motor tem um adaptador `eng_<nome>.py` com o MESMO contrato:

    NAME = "Unity"
    def detect(paths: list[str]) -> bool
        True se a lista de arquivos do RomFS é desse motor (só olha nomes).
    def collect(files: dict[str, tuple[int, int]], read: Callable[[str], bytes]) -> Coleta
        Lê os arquivos que precisar (read(caminho) devolve os bytes do arquivo do RomFS) e devolve as frases
        e uma função `rebuild` que recebe {id: frase traduzida} e devolve {caminho no RomFS: bytes novos}.
        A própria `rebuild` relê o que gerou e levanta MotorError se não conferir (nada vai quebrado pro jogo).

Este módulo junta as frases repetidas, protege os códigos (⟦n⟧), manda para a IA, devolve para o adaptador
e grava os arquivos novos no mod LayeredFS do Ryujinx (o jogo original nunca é tocado).
O bot PERGUNTA antes (Sim/Não no Telegram) com o número de frases e o tempo estimado.
"""
from __future__ import annotations

import hashlib
import importlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional


class MotorError(ValueError):
    pass


@dataclass
class Texto:
    id: str                               # único dentro da coleta (o adaptador escolhe)
    text: str
    codes: Optional[re.Pattern] = None    # códigos que a IA não pode mexer; None = CODES_PADRAO


@dataclass
class Coleta:
    textos: list[Texto]
    rebuild: Callable[[dict[str, str]], dict[str, bytes]]
    aviso: str = ""                       # ressalva para o usuário (ex.: "parte do texto fica no executável")
    extra: dict = field(default_factory=dict)


# tags <..>, {..}, [..], códigos de escape estilo RPG Maker (\C[2], \N[1], \.), printf (%s, %d), quebras de linha
CODES_PADRAO = re.compile(r"<[^>]*>|\{[^}]*\}|\[[^\]]*\]|\\[A-Za-z]+\[[^\]]*\]|\\[^\s]|%[-+0-9.]*[sdif]|\r?\n")
_LETTERS = re.compile(r"[^\W\d_]{2,}")

ADAPTADORES = ("eng_rpgmaker", "eng_gamemaker", "eng_godot", "eng_re", "eng_unity", "eng_cri")

RITMO_PADRAO = 40    # frases/minuto com a IA do PC (medido no FF Resonance com o PC dividido)
RITMO_SO_DECK = 8    # frases/minuto só com a IA do Deck


def adapter_for(paths: list[str]):
    """Adaptador do motor desses arquivos, ou None."""
    for name in ADAPTADORES:
        try:
            mod = importlib.import_module(f".{name}", __package__)
        except ImportError:
            continue
        try:
            if mod.detect(paths):
                return mod
        except Exception:  # noqa: BLE001 - detector com defeito não pode derrubar a tradução
            continue
    return None


def unique_texts(col: Coleta) -> dict[str, list[Texto]]:
    """Frases com letras, agrupadas pelo texto (a IA traduz cada frase diferente uma vez só)."""
    out: dict[str, list[Texto]] = {}
    for t in col.textos:
        pat = t.codes or CODES_PADRAO
        if _LETTERS.search(pat.sub(" ", t.text)):
            out.setdefault(t.text, []).append(t)
    return out


def estimate_minutes(n_unique: int, cfg: dict) -> int:
    cfg = cfg or {}
    pc = "ollama_pc" in cfg.get("providers", {}) or "ollama_pc" in cfg.get("fallback", [])
    ritmo = cfg.get("ritmo_frases_min") or (RITMO_PADRAO if pc else RITMO_SO_DECK)
    return max(1, round(n_unique / ritmo))


def fmt_minutes(m: int) -> str:
    if m < 60:
        return f"~{m} min"
    h, r = divmod(m, 60)
    return f"~{h} h" + (f" {r:02d} min" if r else "")


def translate(paths, cfg: dict, col: Coleta, job: str, title: str, chain=None,
              progress=lambda d, t: None, should_pause=lambda: False):
    """Traduz a coleta e devolve ({caminho: bytes novos}, Result da IA, quantas frases trocaram)."""
    from . import ia
    uniq = unique_texts(col)
    prot: dict[str, tuple[str, list[str]]] = {}
    items = []
    for s, ts in uniq.items():
        p, codes = ia.protect(s, ts[0].codes or CODES_PADRAO)
        key = hashlib.sha1(s.encode("utf-8", "surrogatepass")).hexdigest()[:16]
        prot[key] = (s, codes)
        items.append(ia.Item(key, p))
    res = ia.translate(paths, cfg, items, job, ia.load_glossary(paths, title), chain=chain,
                       progress=progress, should_pause=should_pause)
    by_id: dict[str, str] = {}
    for key, (s, codes) in prot.items():
        t = res.translated.get(key)
        if t:
            new = ia.restore(t, codes)
            if new != s:
                for x in uniq[s]:
                    by_id[x.id] = new
    if not by_id:
        return {}, res, 0
    files = col.rebuild(by_id)
    return files, res, len(by_id)


def install(files: dict[str, bytes], mod_romfs: Path) -> list[Path]:
    """Grava os arquivos traduzidos no mod LayeredFS (mesmo caminho do RomFS)."""
    out = []
    for rel, data in files.items():
        dst = mod_romfs / rel.lstrip("/")
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(dst)
        out.append(dst)
    return out
