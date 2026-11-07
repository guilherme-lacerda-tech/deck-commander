"""Remover um jogo da biblioteca (ex.: duplicata), sempre com confirmação explícita.

O que acontece em `apply`:
1. atalho no Steam: o plugin remove ao vivo (sem o plugin: avisa para remover pelo Steam);
2. o jogo sai do mapa (dc-launch) e do registro do plugin — a autocorreção NÃO o recria;
3. os arquivos do jogo vão para a QUARENTENA (30 dias, nada é apagado; `/quarantine clear` apaga);
   no cartão SD a quarentena fica no próprio cartão (não copia GBs para a memória interna);
4. o download no qBittorrent é removido junto com o arquivo baixado (se ele veio do bot).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import plugin_bridge
from .paths import Paths
from .quarantine import quarantine
from .store import Store


@dataclass
class RemovePlan:
    game_id: str
    title: str
    console: str
    move: Optional[Path]           # arquivo/pasta que vai para a quarentena
    size: int = 0
    torrents: list[str] = field(default_factory=list)
    appids: list[int] = field(default_factory=list)

    def describe(self) -> str:
        lines = [f"Remover «{self.title}» ({self.console}):",
                 "• atalho sai do Steam" + (" (ao vivo)" if self.appids else ""),
                 f"• arquivos ({self.size / 1e9:.1f} GB) vão para a quarentena por 30 dias — nada é apagado agora"
                 if self.move else "• arquivos já não existem"]
        if self.torrents:
            lines.append("• o download sai do qBittorrent")
        return "\n".join(lines)


def _load(p: Path, default):
    try:
        return json.loads(p.read_text("utf-8"))
    except (OSError, ValueError):
        return default


def _save(p: Path, data) -> None:
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    os.replace(tmp, p)


def _size(p: Path) -> int:
    if p.is_file():
        return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def _what_to_move(rom: Path, roots: list[Path], launch_map: dict, game_id: str) -> Optional[Path]:
    """A pasta do jogo dentro de roms/<console>/ (se só ele mora lá); senão só o arquivo."""
    if not rom.exists():
        return None
    for root in roots:
        try:
            rel = rom.relative_to(root)
        except ValueError:
            continue
        if len(rel.parts) <= 2:  # roms/<console>/<arquivo>: solto, sai só ele
            return rom
        folder = root / rel.parts[0] / rel.parts[1]
        others = [g for g, e in launch_map.items() if g != game_id and str(e.get("rom", "")).startswith(str(folder) + os.sep)]
        return rom if others else folder
    return rom


def plan(paths: Paths, game_id: str, roots: list[Path]) -> RemovePlan:
    lm = _load(paths.data / "launch-map.json", {})
    e = lm.get(game_id)
    if not e:
        raise KeyError(f"jogo '{game_id}' não está na biblioteca do Deck Commander")
    rom = Path(e["rom"])
    move = _what_to_move(rom, roots, lm, game_id)
    done = _load(plugin_bridge.done_path(paths), {})
    appids = [done[game_id]["appid"]] if done.get(game_id, {}).get("appid") else []
    st = _load(paths.state / "sync-state.json", {})
    hs = [h for h, v in st.get("ingested", {}).items()
          if any(f == str(rom) or (move and f.startswith(str(move))) for f in v.get("files", []))]
    return RemovePlan(game_id, e.get("title", game_id), e.get("console", "?"), move,
                      _size(move) if move else 0, hs, appids)


def _quarantine_root(item: Path, default: Path) -> Path:
    """Mesma partição do jogo: mover para a quarentena vira só uma renomeação."""
    try:
        default.mkdir(parents=True, exist_ok=True)
        if item.stat().st_dev == default.stat().st_dev:
            return default
    except OSError:
        return default
    p = item
    while p.parent != p and p.name != "Emulation":
        p = p.parent
    return (p.parent if p.name == "Emulation" else item.parent) / "deck-commander-quarentena"


def apply(paths: Paths, store: Store, rp: RemovePlan, qbt=None) -> list[str]:
    out = []
    # 1) registro do plugin: marcado como removido => a autocorreção não recria
    done = _load(plugin_bridge.done_path(paths), {})
    done[rp.game_id] = {"appid": 0, "error": "", "removed": True}
    _save(plugin_bridge.done_path(paths), done)
    items_p = paths.data / "plugin-items.json"
    items = _load(items_p, {})
    if items.pop(rp.game_id, None) is not None:
        _save(items_p, items)
    q = _load(plugin_bridge.queue_path(paths), [])
    if any(x.get("game_id") == rp.game_id for x in q):
        _save(plugin_bridge.queue_path(paths), [x for x in q if x.get("game_id") != rp.game_id])
    if rp.appids and plugin_bridge.installed():
        rq_p = paths.data / "plugin-remove.json"
        rq = _load(rq_p, [])
        rq += [{"game_id": rp.game_id, "appid": a} for a in rp.appids]
        _save(rq_p, rq)
        out.append("atalho: o plugin remove do Steam em ~10 s" if plugin_bridge.loader_running() else
                   "atalho: o Decky não está rodando; o plugin remove assim que ele voltar")
    else:
        out.append("atalho: remova no Steam (Gerenciar → Remover atalho não-Steam) — ele já não abre nada")
    # 2) mapa
    lm_p = paths.data / "launch-map.json"
    lm = _load(lm_p, {})
    lm.pop(rp.game_id, None)
    _save(lm_p, lm)
    with store.tx() as c:
        c.execute("DELETE FROM provenance WHERE operation_id=?", (f"plugin:{rp.game_id}",))
        if rp.move:  # registro dos arquivos sai junto (senão o diagnóstico acusa "arquivo sumido")
            prefix = str(rp.move) + os.sep
            c.execute("DELETE FROM files WHERE path=? OR substr(path, 1, ?)=?", (str(rp.move), len(prefix), prefix))
        c.execute("DELETE FROM files WHERE game_id=?", (rp.game_id,))
    # 3) arquivos -> quarentena
    if rp.move and rp.move.exists():
        qroot = _quarantine_root(rp.move, paths.quarantine)
        entry = quarantine(rp.move, qroot, f"removido pelo usuário: {rp.title} ({rp.game_id})")
        out.append(f"arquivos na quarentena: {entry}")
    # 4) download
    if rp.torrents and qbt is not None:
        st_p = paths.state / "sync-state.json"
        st = _load(st_p, {})
        for h in rp.torrents:
            try:
                qbt.delete(h, delete_files=True)
                out.append("download removido do qBittorrent")
            except Exception as e:  # noqa: BLE001
                out.append(f"download: não consegui remover ({e})")
            st.get("ingested", {}).get(h, {})["removed"] = True
        _save(st_p, st)
    return out


def effective_map(paths: Paths) -> dict:
    """launch-map com `removed: True` também nos jogos que você tirou pelo próprio Steam (o plugin anota)."""
    lm = _load(paths.data / "launch-map.json", {})
    for gid, v in _load(plugin_bridge.done_path(paths), {}).items():
        if v.get("removed") and gid in lm:
            lm[gid] = {**lm[gid], "removed": True}
    return lm


def removed_games(paths: Paths) -> dict:
    """Jogos removidos cujos arquivos ainda estão no lugar (podem voltar com /devolver)."""
    return {g: e for g, e in effective_map(paths).items() if e.get("removed") and Path(e.get("rom", "")).exists()}


def bring_back(paths: Paths, game_id: str) -> str:
    """Desfaz a remoção de um jogo cujos arquivos ainda existem: o próximo /sync cria o atalho de novo."""
    lm_p = paths.data / "launch-map.json"
    lm = _load(lm_p, {})
    if game_id not in lm or not Path(lm[game_id].get("rom", "")).exists():
        return "Os arquivos desse jogo não estão mais no lugar (se foi pelo /remover, estão na quarentena)."
    lm[game_id].pop("removed", None)
    _save(lm_p, lm)
    done = _load(plugin_bridge.done_path(paths), {})
    if done.pop(game_id, None) is not None:
        _save(plugin_bridge.done_path(paths), done)
    return lm[game_id].get("title", game_id)


def find(launch_map: dict, query: str, include_removed: bool = False) -> list[str]:
    """game_ids cujo título tem todas as palavras digitadas (sem acento/caixa, em qualquer ordem).
    Se o texto for exatamente o nome de um deles, só esse volta."""
    from .library import slug
    q = slug(query)
    if not q:
        return []
    if q in launch_map:
        return [q]
    words = q.split("-")
    hits = [g for g, e in launch_map.items() if (include_removed or not e.get("removed"))
            and all(w in slug(e.get("title", "")).split("-") or w in slug(e.get("title", "")) for w in words)]
    exact = [g for g in hits if slug(launch_map[g].get("title", "")) == q]
    return exact or hits
