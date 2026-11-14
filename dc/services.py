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


def seeding_limits(paths: Paths) -> dict:
    """Depois de baixar, compartilha até a razão 1.0 ou 60 min (o que vier primeiro) e para.
    Ajustável em deck.json: seed_ratio, seed_minutes (-1 = sem limite)."""
    from . import syncer
    c = syncer._cfg(paths)
    return {"ratio": float(c.get("seed_ratio", 1.0)), "minutes": int(c.get("seed_minutes", 60))}


def power_loop(paths: Paths, interval: float = 30) -> None:
    """Pausa SÓ os torrents que ele mesmo pausou (não retoma o que o usuário pausou)."""
    cfgp = paths.config / "power.json"
    cfg = json.loads(cfgp.read_text("utf-8")) if cfgp.exists() else {}
    pol = PowerPolicy(min_battery_pct=cfg.get("min_battery_pct", 30), allow_on_battery=cfg.get("allow_on_battery", False),
                      debounce_s=cfg.get("debounce_s", 60), state="RUN")
    q, mine_p = Qbt(), paths.state / "paused-by-dc.json"
    state_p = paths.state / "power-state.json"
    store = Store(paths.db)
    cfg_mtime, seed_at, last_written = 0.0, 0.0, None
    ACTIVE = ("downloading", "stalledDL", "metaDL", "queuedDL", "forcedDL")
    while True:
        # power.json mudou (ex.: /bateria pelo bot): vale na hora, sem reiniciar o serviço
        try:
            mt = cfgp.stat().st_mtime if cfgp.exists() else 0.0
            if mt != cfg_mtime:
                cfg_mtime = mt
                cfg = json.loads(cfgp.read_text("utf-8")) if cfgp.exists() else {}
                pol.allow_on_battery = bool(cfg.get("allow_on_battery", False))
                pol.min_battery_pct = int(cfg.get("min_battery_pct", 30))
        except (OSError, ValueError) as e:
            _log(paths, "power", f"power.json ilegível: {e}")
        # limite de seeding (protege o pacote de dados do celular); reaplica 1x/h caso o qBittorrent reinicie
        if time.time() - seed_at > 3600:
            try:
                q.set_seeding_limits(**seeding_limits(paths))
                seed_at = time.time()
            except QbtError:
                pass
        reading = read_power()
        state, why, changed = pol.update(reading)
        try:  # modo repouso: na tomada, com download/tradução, o Deck não dorme até terminar (dc/repouso.py)
            from . import repouso
            if repouso.permitido():
                trava = getattr(power_loop, "_trava", None)
                if trava is None:  # serviço (re)começou: marca velha não pode apagar a tela sem trava de verdade
                    (paths.state / "repouso-ativo").unlink(missing_ok=True)
                    trava = repouso.Trava(marca=paths.state / "repouso-ativo")
                    import threading  # botão de ligar com a trava: apaga/acende a tela
                    threading.Thread(target=repouso.vigiar_botao, args=(paths,), daemon=True).start()
                power_loop._trava = trava
                try:
                    tors = q.torrents()
                except QbtError:
                    tors = []
                msg = trava.ajustar(repouso.motivo(paths, tors, bool(reading.ac_online)))
                if msg:
                    _log(paths, "power", msg)
                    if trava.proc is None:  # acabou: se a tela foi apagada pelo botão, o Deck vai dormir
                        fim = repouso.ao_terminar(paths)
                        if fim:
                            _log(paths, "power", fim)
        except Exception as e:  # noqa: BLE001 — repouso nunca derruba o serviço de energia
            _log(paths, "power", f"repouso: {e}")
        if (state, why) != last_written:
            last_written = (state, why)
            try:
                state_p.write_text(json.dumps({"state": state, "why": why, "battery": reading.battery_pct,
                                               "ac": reading.ac_online}, ensure_ascii=False), "utf-8")
            except OSError:
                pass
        try:
            if state == "RUN" and mine_p.exists():  # inclui pausa que sobrou de antes de um reinício
                mine = json.loads(mine_p.read_text()) if mine_p.exists() else []
                q.resume(mine); mine_p.unlink(missing_ok=True)
                _log(paths, "power", f"RUN retomados {len(mine)}: {why}")
            elif state == "PAUSE":
                # inclui downloads novos que chegaram durante a pausa (antes eles baixavam na bateria)
                mine = json.loads(mine_p.read_text()) if mine_p.exists() else []
                act = [t["hash"] for t in q.torrents() if t["state"] in ACTIVE and t["hash"] not in mine]
                if act or changed:
                    q.pause(act); mine_p.write_text(json.dumps(sorted(set(mine) | set(act))))
                    _log(paths, "power", f"PAUSE {len(act)} torrent(s): {why}")
        except (QbtError, OSError, ValueError) as e:
            _log(paths, "power", f"qBittorrent indisponível: {e}")
        # plugin do Decky: registra AppIDs criados ao vivo e atualiza as abas
        try:
            from . import plugin_bridge, syncer, tabs, vdf
            done_p = plugin_bridge.done_path(paths)
            sc = syncer.shortcuts_path()
            stamp = max(done_p.stat().st_mtime if done_p.exists() else 0, sc.stat().st_mtime)
            if stamp > getattr(power_loop, "_seen", 0):  # plugin criou atalho ou Unifideck/Steam mudou a lista
                power_loop._seen = stamp
                plugin_bridge.collect(paths, store)
                if tabs.SETTINGS.exists():
                    tabs.apply(vdf.read_shortcuts(sc), json.loads((paths.data / "launch-map.json").read_text("utf-8")),
                               sc.parents[1].name, data_dir=paths.data)
        except Exception as e:  # noqa: BLE001
            _log(paths, "worker", f"plugin: {e}")
        # fila: roda operações pendentes (ex.: /sync enfileirado durante jogo) quando o jogo fecha
        running = ops.game_running()
        # shaders à noite (opcional): na tomada, sem jogo, de madrugada abre 1 jogo novo por vez por ~60 s
        if not running and time.time() - getattr(power_loop, "_shaders", 0) > 600:
            power_loop._shaders = time.time()
            try:
                if json.loads((paths.config / "shaders-noite.json").read_text("utf-8")).get("ligado"):
                    from datetime import datetime as _dt

                    from . import bench, espaco, remove, shaders_noite
                    feitos = shaders_noite.rodada(
                        remove.effective_map(paths), shaders_noite.Estado(paths.state / "shaders-noite.json"),
                        espaco.ultimas_jogadas(paths.logs / "launch.log"),
                        lambda g, s: bool(bench.run(paths, g, s, log=lambda m: _log(paths, "worker", f"shaders: {m}"))),
                        _dt.now(), bool(reading.ac_online), ops.game_running, maximo=1,
                        log=lambda m: _log(paths, "worker", f"shaders: {m}"))
                    if feitos:
                        _log(paths, "worker", f"shaders: cache gerado para {feitos}")
            except (OSError, ValueError):
                pass  # desligado (arquivo não existe)
            except Exception as e:  # noqa: BLE001
                _log(paths, "worker", f"shaders: {e}")
        try:  # monitor/TV ligado ou tirado agora: energia na hora + aviso na tela
            from . import dock_watch
            if not running:
                (paths.state / "jogo-aberto.json").unlink(missing_ok=True)  # sobra de jogo fechado à força
            msg = dock_watch.verificar(paths)
            if msg:
                _log(paths, "worker", msg)
        except Exception as e:  # noqa: BLE001
            _log(paths, "worker", f"dock: {e}")
        if not running:  # qualidade por jogo: devolve o valor global se o jogo foi fechado à força
            try:
                from . import quality
                msg = quality.restore(paths)
                if msg:
                    _log(paths, "worker", f"qualidade: {msg}")
            except Exception as e:  # noqa: BLE001
                _log(paths, "worker", f"qualidade: {e}")
        try:  # busca da comunidade que o PC não fez em 72 h: libera a tradução por IA
            from .traducao import comunidade
            for linha in comunidade.vencidos(paths, store):
                _log(paths, "worker", "comunidade: " + linha.splitlines()[0])
        except Exception as e:  # noqa: BLE001
            _log(paths, "worker", f"comunidade: {e}")
        if not running and not ops.in_safe_mode(paths):
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
    # returncode 1 = algum teste falhou de verdade. 2-5 = problema para RODAR os testes (pytest ausente,
    # coleta interrompida...): é registrado, mas não conta para o safe-mode (não é defeito do DC).
    rep = {"at": datetime.now(timezone.utc).isoformat(), "ok": r.returncode == 0, "summary": summary,
           "seconds": round(time.time() - t0, 1), "infra": r.returncode not in (0, 1)}
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
    real = [h for h in hist if not h.get("infra")]
    if not rep["infra"] and len(real) >= 2 and not real[-1]["ok"] and not real[-2]["ok"]:
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
