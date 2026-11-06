"""Serviços de fundo: monitor de energia (M4.4), worker da fila (M18), testes (M10.4),
check-updates (M11) e dashboard local 127.0.0.1:8765 (M10.1, desligado por padrão)."""
from __future__ import annotations

import html
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from . import health, inventory, ops, worker
from .paths import Paths, get_paths
from .power import PowerPolicy, read_power
from .qbt import Qbt, QbtError
from .store import Store

H = Path.home()


def _log(paths: Paths, name: str, msg: str) -> None:
    paths.logs.mkdir(parents=True, exist_ok=True)
    with open(paths.logs / f"{name}.log", "a", encoding="utf-8") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat()} {msg}\n")


def power_loop(paths: Paths, interval: float = 30) -> None:
    """Pausa SÓ os torrents que ele mesmo pausou (não retoma o que o usuário pausou)."""
    cfgp = paths.config / "power.json"
    cfg = json.loads(cfgp.read_text("utf-8")) if cfgp.exists() else {}
    pol = PowerPolicy(min_battery_pct=cfg.get("min_battery_pct", 30), allow_on_battery=cfg.get("allow_on_battery", False),
                      debounce_s=cfg.get("debounce_s", 60), state="RUN")
    q, mine_p = Qbt(), paths.state / "paused-by-dc.json"
    store = Store(paths.db)
    while True:
        state, why, changed = pol.update(read_power())
        if changed:
            try:
                if state == "PAUSE":
                    act = [t["hash"] for t in q.torrents() if t["state"] in ("downloading", "stalledDL", "metaDL", "queuedDL")]
                    q.pause(act); mine_p.write_text(json.dumps(act))
                    _log(paths, "power", f"PAUSE {len(act)} torrent(s): {why}")
                else:
                    mine = json.loads(mine_p.read_text()) if mine_p.exists() else []
                    q.resume(mine); mine_p.unlink(missing_ok=True)
                    _log(paths, "power", f"RUN retomados {len(mine)}: {why}")
            except QbtError as e:
                _log(paths, "power", f"qBittorrent indisponível: {e}")
        # plugin do Decky: registra AppIDs criados ao vivo e atualiza as abas
        try:
            from . import plugin_bridge, syncer, tabs, vdf
            done_p = plugin_bridge.done_path(paths)
            if done_p.exists() and done_p.stat().st_mtime > getattr(power_loop, "_seen", 0):
                power_loop._seen = done_p.stat().st_mtime
                plugin_bridge.collect(paths, store)
                if tabs.SETTINGS.exists():
                    sc = syncer.shortcuts_path()
                    tabs.apply(vdf.read_shortcuts(sc), json.loads((paths.data / "launch-map.json").read_text("utf-8")),
                               sc.parents[1].name)
        except Exception as e:  # noqa: BLE001
            _log(paths, "worker", f"plugin: {e}")
        # fila: roda operações pendentes (ex.: /sync enfileirado durante jogo) quando o jogo fecha
        if not ops.game_running() and not ops.in_safe_mode(paths):
            from . import syncer
            for op in store.list(("pending",)):
                if op.type == "sync":
                    store.cancel(op.id)
                    _log(paths, "worker", "sync da fila: " + syncer.run_sync(paths, store, q).splitlines()[0])
        time.sleep(interval)


def run_tests(paths: Paths, repo: Path) -> dict:
    venv_py = H / ".local/share/deck-commander/venv/bin/python"
    py = str(venv_py) if venv_py.exists() else sys.executable
    t0 = time.time()
    r = subprocess.run([py, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(repo / "tests")],
                       capture_output=True, text=True, cwd=repo)
    summary = (r.stdout.strip().splitlines() or ["?"])[-1]
    rep = {"at": datetime.now(timezone.utc).isoformat(), "ok": r.returncode == 0, "summary": summary,
           "seconds": round(time.time() - t0, 1)}
    hist_p = paths.state / "tests-history.json"
    hist = json.loads(hist_p.read_text("utf-8")) if hist_p.exists() else []
    hist = (hist + [rep])[-50:]
    hist_p.write_text(json.dumps(hist, indent=1), "utf-8")
    (paths.state / "tests-last.json").write_text(json.dumps(rep), "utf-8")
    rows = "".join(f"<tr><td>{h['at'][:16]}</td><td>{'✅' if h['ok'] else '❌'}</td><td>{html.escape(h['summary'])}</td></tr>"
                   for h in reversed(hist))
    (paths.logs / "tests-automated.html").write_text(
        f"<!doctype html><meta charset=utf-8><title>Testes automatizados</title><h1>Testes automatizados</h1>"
        f"<table border=1 cellpadding=4><tr><th>quando</th><th>ok</th><th>resultado</th></tr>{rows}</table>"
        f"<pre>{html.escape(r.stdout[-5000:])}</pre>", "utf-8")
    if len(hist) >= 2 and not hist[-1]["ok"] and not hist[-2]["ok"]:
        ops.safe_mode_on(paths, "testes críticos falharam 2x seguidas", Store(paths.db))
        rep["safe_mode"] = True
    return rep


def check_updates(paths: Paths) -> list[str]:
    """Compara SteamOS/Decky/plugins/flatpaks com a última verificação. NÃO atualiza nada."""
    inv = inventory.collect(H, paths)
    snap = {"steamos": inv["hardware"]["steamos"], "decky": inv["software"]["decky"],
            "plugins": health.installed_plugins(), "flatpaks": inv["software"]["flatpaks"]}
    p = paths.state / "versions.json"
    old = json.loads(p.read_text("utf-8")) if p.exists() else None
    p.write_text(json.dumps(snap, indent=1), "utf-8")
    if old is None:
        return ["primeira verificação registrada"]
    msgs = []
    if not snap["decky"] or not (H / "homebrew/services/PluginLoader").exists():
        msgs.append("⚠️ Decky Loader sumiu (provável update do SteamOS) — reinstale manualmente; o DC não reinstala sozinho")
    if old["steamos"] != snap["steamos"]:
        msgs.append(f"SteamOS mudou: {old['steamos']} -> {snap['steamos']} (rode /diagnostico)")
    for k in ("plugins", "flatpaks"):
        for name in set(old[k]) | set(snap[k]):
            if old[k].get(name) != snap[k].get(name):
                msgs.append(f"{k[:-1]} {name}: {old[k].get(name)} -> {snap[k].get(name)}")
    _log(paths, "updates", "; ".join(msgs) or "sem mudanças")
    return msgs or ["sem mudanças"]


class _Dash(BaseHTTPRequestHandler):
    paths: Paths

    def do_GET(self):  # noqa: N802
        body = health.status_text(self.paths, Store(self.paths.db), Qbt())
        page = (f"<!doctype html><meta charset=utf-8><meta http-equiv=refresh content=30><title>Deck Commander</title>"
                f"<body style='font-family:sans-serif;background:#111;color:#eee'><h1>Deck Commander</h1>"
                f"<pre style='font-size:16px'>{html.escape(body)}</pre>")
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
        self.wfile.write(page.encode())

    def log_message(self, *a):
        pass


def dashboard(paths: Paths, port: int = 8765) -> None:
    _Dash.paths = paths
    HTTPServer(("127.0.0.1", port), _Dash).serve_forever()  # só local, nunca na rede


def main(argv: list[str]) -> int:
    paths = get_paths().ensure()
    repo = Path(__file__).resolve().parents[1]
    what = argv[0] if argv else ""
    if what == "power":
        power_loop(paths)
    elif what == "tests":
        print(run_tests(paths, repo))
    elif what == "updates":
        print("\n".join(check_updates(paths)))
    elif what == "dashboard":
        dashboard(paths)
    elif what == "backup":
        from . import backup, cli
        res = backup.create_snapshot(cli.backup_sources(paths), paths.backups, paths.quarantine, kind="config")
        print(res.path if res.ok else res.error)
        print(health.backup_saves(paths))
    elif what == "worker":
        worker.recover(Store(paths.db), paths)
    else:
        print("uso: python3 -m dc.services power|tests|updates|dashboard|backup|worker"); return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
