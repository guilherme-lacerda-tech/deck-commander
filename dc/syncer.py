"""M4.1/M4.7/M4.8 — orquestra o /sync: torrents concluídos -> ROMs -> banco -> atalhos no Steam.

- Jogo aberto: bloqueia ou enfileira (config `sync_during_game` = "block" | "queue"); downloads continuam.
- Timeout de 5 min por execução; 3 timeouts seguidos => safe-mode (só desativa, F4).
- Atalhos novos são gravados com o Steam aberto (mesmo método já em uso pelo Unifideck neste Deck);
  aparecem após reiniciar o Steam (comando /reiniciar).
"""
from __future__ import annotations

import glob
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from . import backup, content, library, ops, vdf
from .lock import OperationLock
from .paths import Paths
from .qbt import DONE_STATES, Qbt
from .quarantine import quarantine
from .store import Store

TIMEOUT_S = 300
LAST_CONFLICTS: list[str] = []  # jogos não adicionados por já existir atalho manual com o mesmo nome


def _cfg(paths: Paths) -> dict:
    p = paths.config / "deck.json"
    base = {"sync_during_game": "block", "approval_required": True, "roms_root": str(Path.home() / "Emulation/roms"),
            "downloads_root": str(Path.home() / "Emulation/downloads")}
    try:
        base.update(json.loads(p.read_text("utf-8")))
    except (OSError, ValueError):
        pass
    return base


def _state(paths: Paths) -> dict:
    try:
        return json.loads((paths.state / "sync-state.json").read_text("utf-8"))
    except (OSError, ValueError):
        return {"ingested": {}, "timeouts": 0, "last_sync": None, "pending": {}}


def _save_state(paths: Paths, st: dict) -> None:
    paths.state.mkdir(parents=True, exist_ok=True)
    tmp = paths.state / "sync-state.json.tmp"
    tmp.write_text(json.dumps(st, indent=1, ensure_ascii=False), "utf-8")
    tmp.replace(paths.state / "sync-state.json")


def shortcuts_path() -> Path:
    from .steam import shortcuts_path as _sp
    return _sp()


def rom_roots() -> list[Path]:
    return [Path.home() / "Emulation/roms"] + [Path(p) for p in sorted(glob.glob("/run/media/*/*/Emulation/roms"))]


def add_to_steam(paths: Paths, store: Store, op: str) -> list[str]:
    """Acrescenta atalhos para jogos novos (idempotente). Retorna os nomes adicionados.
    Depois, confere quais jogos de Switch têm português oficial (só os novos/atualizados são lidos)."""
    names = _add_to_steam(paths, store, op)
    try:
        from .traducao import portugues
        lm = json.loads((paths.data / "launch-map.json").read_text("utf-8"))
        portugues.detect_switch(paths, lm, rom_roots())
    except Exception:  # noqa: BLE001 — a detecção de idioma nunca atrapalha o /sync
        pass
    return names


def _add_to_steam(paths: Paths, store: Store, op: str) -> list[str]:
    games, _ = library.scan(rom_roots())
    ops.index_files(store, games)
    sc = shortcuts_path()
    launcher = library.launcher_path(Path.home())
    pl = library.plan(vdf.read_shortcuts(sc), games, launcher)
    LAST_CONFLICTS[:] = pl.name_conflicts
    if not pl.add:
        library.write_map(paths.data / "launch-map.json", games)
        return []
    from . import plugin_bridge
    if plugin_bridge.active():  # ao vivo: o plugin cria o atalho e aplica as capas (sem reiniciar)
        library.write_launcher(Path.home(), Path(__file__).resolve().parents[1])
        library.write_map(paths.data / "launch-map.json", games)
        # na fila, já criado (ainda não gravado em disco pelo Steam) ou removido pelo usuário: não reenvia
        busy = set(plugin_bridge.pending(paths)) | set(plugin_bridge.known(paths))
        rows = [r for r in pl.add if r["LaunchOptions"] not in busy]
        plugin_bridge.enqueue(paths, rows)
        return [r["AppName"] for r in rows]
    res = backup.create_snapshot({"shortcuts": sc}, paths.backups, paths.quarantine, kind="steam")
    if not res.ok:
        raise RuntimeError(f"backup falhou: {res.error}")
    library.write_launcher(Path.home(), Path(__file__).resolve().parents[1])
    library.write_map(paths.data / "launch-map.json", games)
    library.write_shortcuts(sc, pl.add)
    now = datetime.now(timezone.utc).isoformat()
    with store.tx(critical=True) as c:
        for row in pl.add:
            c.execute("INSERT OR IGNORE INTO provenance VALUES(?,?,?,?)",
                      (str(row["appid"] & 0xFFFFFFFF), "dc", now, op))
    try:  # abas do TabMaster (se instalado) acompanham os jogos novos
        from . import tabs
        if tabs.SETTINGS.exists():
            tabs.apply(vdf.read_shortcuts(sc), json.loads((paths.data / "launch-map.json").read_text("utf-8")),
                       sc.parents[1].name, data_dir=paths.data)
    except Exception:  # noqa: BLE001 — aba é conforto, nunca bloqueia o /sync
        pass
    return [r["AppName"] for r in pl.add]


def _duplicate_of(paths: Paths, item) -> str | None:
    """O jogo recém-chegado já existe na biblioteca (mesma identidade)? Devolve o título existente."""
    from . import dedup
    lm_p = paths.data / "launch-map.json"
    try:
        lm = json.loads(lm_p.read_text("utf-8"))
    except (OSError, ValueError):
        return None
    for f in item.files:
        k = dedup.match_key(library.clean_title(Path(f).stem), item.console, f)
        for gid, e in lm.items():
            if e.get("removed") or e.get("rom") in item.files:
                continue
            if dedup.same_game(k, dedup.match_key(e.get("title", gid), e.get("console"), e.get("rom", ""))) \
                    and Path(e.get("rom", "")).exists():
                return e.get("title", gid)
    return None


def run_sync(paths: Paths, store: Store, qbt: Qbt | None, confirm_many: bool = False,
             explicit: dict | None = None) -> str:
    cfg = _cfg(paths)
    if ops.in_safe_mode(paths):
        return "Safe-mode ativo: /sync desativado. Use /sos off depois de revisar."
    if ops.game_running():
        if cfg["sync_during_game"] == "queue":
            store.enqueue("sync", {"confirm_many": confirm_many})
            return "Jogo aberto: /sync ficou na fila e roda quando você sair. Downloads continuam."
        return "Feche o jogo primeiro (o /sync não roda durante o jogo). Downloads continuam."
    st = _state(paths)
    op = store.enqueue("sync", {"confirm_many": confirm_many})
    store.claim(op)
    t0 = time.monotonic()
    lines, added_files, arrived = [], 0, set()
    try:
        with OperationLock(paths.lock, op, "sync", is_running=store.is_running):
            torrents = qbt.torrents() if qbt else []
            todo = [t for t in torrents if t["hash"] not in st["ingested"] and t.get("state") in DONE_STATES]
            for n, t in enumerate(todo):
                if time.monotonic() - t0 > TIMEOUT_S:
                    if n == 0:  # nada andou em 5 min: aí sim é travamento
                        raise TimeoutError("/sync passou de 5 minutos")
                    lines.append(f"⏳ {len(todo) - n} download(s) ficam para a próxima rodada (extração demorada).")
                    break
                forced = (explicit or {}).get(t["hash"])
                item = content.ingest(Path(t["content_path"]), forced or t.get("category") or None,
                                      Path(cfg["roms_root"]), paths.quarantine, paths.state / "work",
                                      confirm_many=confirm_many)
                wanted = "dc-dup-ok" in (t.get("tags") or "")  # o usuário confirmou com /baixar
                dup = _duplicate_of(paths, item) if item.status == "added" and not wanted else None
                if dup:
                    folder = Path(item.files[0])
                    while folder.parent.name != item.console and folder.parent != folder:
                        folder = folder.parent
                    q = quarantine(folder if folder.parent.name == item.console else Path(item.files[0]),
                                   paths.quarantine, f"duplicata de «{dup}» (download {t['name']})")
                    st["ingested"][t["hash"]] = {"name": t["name"], "duplicate_of": dup, "quarantine": str(q)}
                    lines.append(f"♻️ {t['name']}: você já tem «{dup}» — não criei outro atalho. "
                                 f"A cópia nova ficou na quarentena ({q.name}); /duplicados mostra como limpar.")
                    _save_state(paths, st)
                    continue
                if item.status == "added":
                    st["ingested"][t["hash"]] = {"name": t["name"], "files": item.files}
                    with store.tx() as c:
                        for f in item.files:
                            p = Path(f); s = p.stat()
                            c.execute("INSERT OR REPLACE INTO files(path,size,mtime,origin,origin_ref,integrity)"
                                      " VALUES(?,?,?,?,?,?)", (f, s.st_size, s.st_mtime, "torrent", t["hash"], item.integrity))
                    added_files += len(item.files)
                    arrived |= {library.clean_title(Path(f).stem).casefold() for f in item.files}
                    lines.append(f"✅ {t['name']} → {item.console}" + (f" ({item.note})" if item.note else "")
                                 + " · não verificado (sem referência de hash)")
                elif item.status == "ask_console":
                    st["pending"][t["hash"]] = t["name"]
                    lines.append(f"❓ {t['name']}: qual console? responda /console {t['hash'][:8]} <ps2|psx|gc|wii|snes|n64|gba|psp|switch>")
                elif item.status == "ask_many":
                    lines.append(f"❓ {t['name']}: {item.note}")
                elif item.status == "quarantined":
                    st["ingested"][t["hash"]] = {"name": t["name"], "quarantined": True}
                    lines.append(f"⛔ {t['name']}: quarentena — {item.note}")
                else:
                    lines.append(f"⚠️ {t['name']}: {item.note}")
                _save_state(paths, st)  # cada download concluído fica registrado na hora (nunca entra 2x)
            new = add_to_steam(paths, store, op)
        st["timeouts"] = 0
        st["last_sync"] = datetime.now(timezone.utc).isoformat()
        _save_state(paths, st)
        store.finish(op, True, result={"files": added_files, "shortcuts": len(new)})
        head = f"{len(new)} jogo(s) novo(s) no Steam" + (": " + ", ".join(new[:10]) if new else "")
        fresh = [c for c in LAST_CONFLICTS if c.casefold() in arrived]
        for c in fresh:
            lines.append(f"⚠️ «{c}» não ganhou atalho: já existe um atalho seu com esse nome no Steam "
                         "(feito à mão?). Apague o antigo no Steam e mande /sync.")
        from . import plugin_bridge
        if new and plugin_bridge.active():
            tail = "\n✨ Aparecem na biblioteca em ~10 segundos, já com capa (sem reiniciar)."
        else:
            tail = "\n👉 Toque em /reiniciar para aparecer no Steam (fecha e abre o Steam, ~20 s)." if new else ""
        return "\n".join([head] + lines) + tail
    except TimeoutError as e:
        st["timeouts"] = st.get("timeouts", 0) + 1
        _save_state(paths, st)
        store.finish(op, False, error=str(e))
        if st["timeouts"] >= 3:
            ops.safe_mode_on(paths, "3 timeouts seguidos do /sync", store)
            return "⛔ 3 timeouts seguidos: safe-mode ativado (serviços desligados, nada apagado). Use /status."
        return f"⏱ {e}. Tentativa {st['timeouts']}/3 — tente /sync de novo."
    except Exception as e:  # noqa: BLE001
        store.finish(op, False, error=str(e))
        return f"❌ /sync falhou: {e}"
