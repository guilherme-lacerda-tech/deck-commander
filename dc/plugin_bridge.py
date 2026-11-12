"""Ponte com o plugin do Decky "Deck Commander": atalhos ao vivo, sem reiniciar o Steam.

O DC escreve plugin-queue.json (com as capas já baixadas em data/art/<game_id>/); o plugin cria o
atalho via SteamClient.Apps.AddShortcut, aplica as capas e grava plugin-done.json com o AppID que o
Steam gerou. `collect()` registra esses AppIDs em `provenance` (origem 'dc').
Sem o plugin instalado, o DC volta ao método antigo (gravar shortcuts.vdf + reiniciar o Steam).
"""
from __future__ import annotations

import glob
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .arquivo_json import gravar as _save
from .arquivo_json import ler as _load
from .paths import Paths
from .store import Store

H = Path.home()


def installed(home: Path = H) -> bool:
    for pj in glob.glob(str(home / "homebrew/plugins/*/plugin.json")):
        try:
            if json.loads(Path(pj).read_text("utf-8")).get("name") == "Deck Commander":
                return True
        except (OSError, ValueError):
            pass
    return False


def loader_running() -> bool:
    """O Decky Loader está rodando? (Um update do SteamOS pode removê-lo; aí o plugin não age.)"""
    import subprocess
    try:
        return subprocess.run(["pgrep", "-f", "homebrew/services/PluginLoader"], capture_output=True,
                              timeout=5).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def active(home: Path = H) -> bool:
    """Plugin instalado E Decky rodando: só assim os atalhos entram ao vivo."""
    return installed(home) and loader_running()



@contextmanager
def trava(p: Path):
    """Trava do arquivo (o mesmo `<arquivo>.lock` que o backend do plugin usa). Sem ela o plugin e o Deck Commander
    liam-mexiam-gravavam ao mesmo tempo e um apagava a mudança do outro (revisão de lançamento 12/11/2026)."""
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p.with_name(p.name + ".lock"), "a") as f:
        if os.name == "posix":
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "posix":
                fcntl.flock(f, fcntl.LOCK_UN)


def atualizar(p: Path, padrao, fn):
    """Lê, muda (fn mexe no objeto) e grava `p` sob a trava. Devolve o que fn devolver."""
    with trava(p):
        dados = _load(p, padrao)
        r = fn(dados)
        _save(p, dados)
        return r


def marcar_removido(paths: Paths, game_id: str, appids=(), motivo: str = "", so_com_plugin: bool = True) -> bool:
    """Atalho do Deck Commander sai: registro (a autocorreção não recria), item, fila e pedido de remoção ao
    plugin. Era copiado em remove.apply, remove.hide e pc_remoto (cada um um pouco diferente). Devolve se pediu
    a remoção do atalho ao plugin."""
    marca = {"appid": 0, "error": "", "removed": True, **({"motivo": motivo} if motivo else {})}
    atualizar(done_path(paths), {}, lambda d: d.__setitem__(game_id, marca))
    atualizar(paths.data / "plugin-items.json", {}, lambda d: d.pop(game_id, None))
    atualizar(queue_path(paths), [], lambda q: q.__setitem__(slice(None), [x for x in q if x.get("game_id") != game_id]))
    ids = [int(a) & 0xFFFFFFFF for a in appids if a]
    if ids and (installed() or not so_com_plugin):
        atualizar(paths.data / "plugin-remove.json", [],
                  lambda rq: rq.extend({"game_id": game_id, "appid": a} for a in ids))
        return True
    return False


def queue_path(paths: Paths) -> Path:
    return paths.data / "plugin-queue.json"


def done_path(paths: Paths) -> Path:
    return paths.data / "plugin-done.json"


def prepare_art(paths: Paths, game_id: str, title: str) -> dict:
    """Baixa as capas para data/art/<game_id>/ (se houver chave do SteamGridDB)."""
    from . import artwork
    key = artwork.read_key(paths.secrets)
    if not key:
        return {}
    d = paths.data / "art" / game_id
    try:
        artwork.fetch_for("img", title, d, artwork.make_fetch(key))
    except Exception:  # noqa: BLE001 — sem capa não impede o jogo de entrar
        return {}
    kinds = {"imgp": "p", "img": "wide", "img_hero": "hero", "img_logo": "logo"}
    return {kinds[f.stem]: str(f) for f in d.iterdir() if f.stem in kinds}


def enqueue(paths: Paths, rows: list[dict], with_art: bool = True) -> int:
    have = {x["game_id"] for x in _load(queue_path(paths), [])}
    novos = []
    for r in rows:  # capas baixadas FORA da trava (rede): o plugin não fica esperando
        gid = r["LaunchOptions"]
        if gid in have or any(x["game_id"] == gid for x in novos):
            continue
        novos.append({"game_id": gid, "name": r["AppName"], "exe": r["exe"], "start_dir": r["StartDir"],
                      "launch_options": gid, "art": prepare_art(paths, gid, r["AppName"]) if with_art else {}})

    def por(q):
        ja = {x["game_id"] for x in q}
        add = [x for x in novos if x["game_id"] not in ja]
        q.extend(add)
        return len(add)
    n = atualizar(queue_path(paths), [], por)
    # para a autocorreção do plugin
    atualizar(paths.data / "plugin-items.json", {}, lambda items: items.update({x["game_id"]: x for x in novos}))
    return n


def collect(paths: Paths, store: Store) -> list[str]:
    """Registra em provenance o que o plugin já criou. Retorna game_ids com erro."""
    done = _load(done_path(paths), {})
    errors = []
    now = datetime.now(timezone.utc).isoformat()
    with store.tx() as c:
        for gid, v in done.items():
            if v.get("appid"):
                # atalho recriado (autocorreção) ganha AppID novo: o antigo deixa de existir
                c.execute("DELETE FROM provenance WHERE operation_id=? AND appid<>?", (f"plugin:{gid}", str(v["appid"])))
                c.execute("INSERT OR IGNORE INTO provenance VALUES(?,?,?,?)", (str(v["appid"]), "dc", now, f"plugin:{gid}"))
            elif v.get("error"):
                errors.append(f"{gid}: {v['error']}")
    return errors


def known(paths: Paths) -> list[str]:
    """game_ids que o plugin já criou ou que foram removidos de propósito."""
    return [g for g, v in _load(done_path(paths), {}).items() if v.get("appid") or v.get("removed")]


def pending(paths: Paths) -> list[str]:
    done = _load(done_path(paths), {})
    return [x["game_id"] for x in _load(queue_path(paths), []) if x["game_id"] not in done]
