"""Remover um jogo da biblioteca (ex.: duplicata), sempre com confirmação explícita.

O que acontece em `apply`:
1. atalho no Steam: o plugin remove ao vivo (sem o plugin: avisa para remover pelo Steam);
2. o jogo sai do mapa (dc-launch) e do registro do plugin — a autocorreção NÃO o recria;
3. os arquivos do jogo vão para a QUARENTENA (30 dias, nada é apagado; `/quarantine clear` apaga);
   no cartão SD a quarentena fica no próprio cartão (não copia GBs para a memória interna);
4. o download no qBittorrent é removido junto com o arquivo baixado (se ele veio do bot).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from . import plugin_bridge
from .arquivo_json import gravar as _save
from .arquivo_json import ler as _load
from .paths import Paths
from .quarantine import quarantine
from .store import Store


@dataclass
class RemovePlan:
    game_id: str
    title: str
    console: str
    move: Path | None           # arquivo/pasta que vai para a quarentena
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



def _size(p: Path) -> int:
    if p.is_file():
        return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def _what_to_move(rom: Path, roots: list[Path], launch_map: dict, game_id: str) -> Path | None:
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
    appids = [int(done[game_id]["appid"]) & 0xFFFFFFFF] if done.get(game_id, {}).get("appid") else []
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
    if plugin_bridge.marcar_removido(paths, rp.game_id, rp.appids):
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


def hide(paths: Paths, game_id: str, reason: str) -> str:
    """Tira SÓ o atalho da biblioteca (os arquivos ficam). Usado quando a versão traduzida substitui a
    original, para a biblioteca não ficar duplicada. Volta com /devolver."""
    appid = int(_load(plugin_bridge.done_path(paths), {}).get(game_id, {}).get("appid") or 0)
    plugin_bridge.marcar_removido(paths, game_id, [appid], motivo=reason)
    try:  # o atalho sai do Steam: o registro "criado pelo DC" sai junto (senão o diagnóstico acusa atalho sumido)
        with Store(paths.db).tx() as c:
            c.execute("DELETE FROM provenance WHERE operation_id=?", (f"plugin:{game_id}",))
    except Exception:  # noqa: BLE001 - banco ainda não criado (Deck novo): nada a limpar
        pass
    lm_p = paths.data / "launch-map.json"
    lm = _load(lm_p, {})
    if game_id in lm:
        lm[game_id]["removed"] = True
        _save(lm_p, lm)
    return lm.get(game_id, {}).get("title", game_id)


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
    plugin_bridge.atualizar(plugin_bridge.done_path(paths), {}, lambda d: d.pop(game_id, None))
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
