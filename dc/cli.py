"""CLI mínima: `python3 -m dc <comando>`. Saída em português, sem efeitos sem --apply."""
from __future__ import annotations

import argparse
import glob
import json
import sys
import tomllib
from pathlib import Path

from . import backup, quarantine, safe_extract, worker
from .paths import get_paths
from .power import PowerPolicy, read_power
from .store import ApprovalError, Store


def _store(paths):
    paths.ensure()
    return Store(paths.db)


def backup_sources(paths) -> dict[str, Path]:
    cfg = paths.config / "backup.toml"
    if not cfg.exists():
        raise SystemExit(f"crie {cfg} (modelo em config/backup.example.toml)")
    data = tomllib.loads(cfg.read_text("utf-8"))
    out: dict[str, Path] = {}
    for name, pattern in data.get("sources", {}).items():
        hits = sorted(glob.glob(str(Path(pattern).expanduser())))
        if len(hits) == 1:
            out[name] = Path(hits[0])
        else:
            for i, h in enumerate(hits):
                out[f"{name}-{i}"] = Path(h)
    return out


def _library(paths, apply: bool) -> int:
    """Coloca jogos novos no Steam. Com o plugin do Decky: ao vivo; sem ele: grava shortcuts.vdf (+ reiniciar Steam)."""
    from . import library, plugin_bridge, syncer, vdf
    games, notes = library.scan(syncer.rom_roots())
    pl = library.plan(vdf.read_shortcuts(syncer.shortcuts_path()), games, library.launcher_path(Path.home()))
    for n in notes:
        print("nota:", n)
    print(f"jogos encontrados: {len(games)} | novos atalhos: {len(pl.add)} | já existem: {len(pl.already)}"
          f" | conflito de nome (não tocados): {pl.name_conflicts or 'nenhum'}")
    for row in pl.add:
        print(f"  + [{row['tags']['0']}] {row['AppName']}  ->  {row['LaunchOptions']}")
    if not apply:
        print("(dry-run; use --apply)"); return 0
    s = _store(paths)
    op = s.enqueue("library-add", {"count": len(pl.add)})
    s.claim_next()
    try:
        from .lock import OperationLock
        with OperationLock(paths.lock, op, "library-add", is_running=s.is_running):
            new = syncer.add_to_steam(paths, s, op)
        s.finish(op, True, result={"added": len(new)})
    except Exception as e:  # noqa: BLE001
        s.finish(op, False, error=str(e)); print(f"FALHOU: {e}"); return 1
    if plugin_bridge.installed():
        print(f"ok: {len(new)} jogo(s) na fila do plugin — aparecem na biblioteca em ~10 s, sem reiniciar.")
    else:
        print(f"ok: {len(new)} atalho(s) gravados. Reinicie o Steam para ver (ou instale o plugin do Decky).")
    return 0


def _extra(paths, args) -> int:
    """Subcomandos do projeto completo (M0, M3, M5, M6, M7, M10, M11, M17, M19, M20, M21)."""
    from . import emulators, export, health, ops, patches, services, syncer, library, vdf
    from .store import Store
    if not args:
        print(open(Path(__file__).resolve().parents[1] / "docs/COMANDOS.md", encoding="utf-8").read()); return 0
    c, r = args[0], args[1:]
    apply = "--apply" in r
    r = [x for x in r if x != "--apply"]
    if c == "configure":
        for l in emulators.configure(apply=apply) or ["nada a mudar"]:
            print(l)
        print("" if apply else "(dry-run; use --apply)")
    elif c == "patch":
        print("gerado:", patches.apply_file(Path(r[0]), Path(r[1])))
    elif c == "safe-mode":
        out = ops.safe_mode_off(paths) if r and r[0] == "off" else ops.safe_mode_on(paths, "manual", _store(paths))
        print("\n".join(out) or "ok")
    elif c == "uninstall":
        confirm = r[r.index("--confirm") + 1] if "--confirm" in r else ""
        for l in ops.uninstall(paths, Path(__file__).resolve().parents[1], "--purge" in r, "--purge-backups" in r, confirm):
            print(l)
    elif c == "db":
        s = _store(paths); games, _ = library.scan(syncer.rom_roots())
        if r and r[0] == "index":
            print("registrados:", ops.index_files(s, games))
        else:
            print(json.dumps(ops.db_verify(s, games, vdf.read_shortcuts(syncer.shortcuts_path())), indent=1, ensure_ascii=False))
    elif c == "saves":
        if r and r[0] == "import":
            print(json.dumps(health.import_saves(Path(r[1]), dry_run=not apply), indent=1, ensure_ascii=False))
        else:
            print(json.dumps(health.backup_saves(paths), indent=1, ensure_ascii=False))
    elif c == "disk":
        for i in health.disk_report(syncer.rom_roots(), vdf.read_shortcuts(syncer.shortcuts_path())):
            print(f"{i['size'] / 1e9:6.1f} GB  {i['last_played']:10}  {'candidato ' if i['suggest_remove'] else '          '}{i['path']}")
        for n in health.stale_downloads(paths):
            print("download já importado (pode apagar o original):", n)
    elif c == "sensors":
        for s in health.read_sensors().values():
            print(f"{s.name:10} {s.state:12} {'' if s.value is None else s.value}{s.unit}")
    elif c == "diagnose":
        for f in health.diagnose(paths, _store(paths), repair=apply):
            print(f"{'OK ' if f.ok else '!! '}[{f.mode}] {f.problem}: {f.detail} {('-> ' + f.action) if f.action else ''}")
    elif c == "status":
        print(health.status_text(paths, _store(paths)))
    elif c == "sync":
        from .qbt import Qbt
        print(syncer.run_sync(paths, _store(paths), Qbt(), confirm_many="tudo" in r))
    elif c == "steam-restart":
        print(ops.restart_steam())
    elif c == "export":
        out = Path(r[0] if r else Path.home() / "deck-commander-export.zip")
        print("\n".join(export.export_config(paths, out))); print("->", out)
    elif c == "import":
        print("\n".join(export.import_config(paths, Path(r[0]), dry_run=not apply)))
    elif c == "tabs":
        from . import tabs
        sc = syncer.shortcuts_path()
        res = tabs.apply(vdf.read_shortcuts(sc), json.loads((paths.data / "launch-map.json").read_text("utf-8")),
                         sc.parents[1].name, data_dir=paths.data)
        print(res or "abas já atualizadas"); print("reinicie o Deck para o TabMaster carregar")
    elif c == "profile":  # M3: perfil de qualidade em DuckStation (ps1) / PCSX2 (ps2)
        from .adapters import ManualOverride, SchemaChanged, get_adapter
        if len(r) < 2:
            print("uso: dc x profile <ps1|ps2> <economico|equilibrado|desempenho> [--apply] [--force]"); return 2
        console = {"ps1": "psx", "psx": "psx", "ps2": "ps2"}[r[0]]
        emu, cfg = (("duckstation", Path.home() / ".local/share/duckstation/settings.ini") if console == "psx" else
                    ("pcsx2", Path.home() / ".var/app/net.pcsx2.PCSX2/config/PCSX2/inis/PCSX2.ini"))
        try:
            ch = get_adapter(emu).apply(cfg, "ps1" if console == "psx" else "ps2", r[1],
                                        paths.state / "adapters-state.json", force="--force" in r, dry_run=not apply)
        except (ManualOverride, SchemaChanged) as e:
            print(f"recusado: {e}"); return 1
        for x in ch:
            print(f"[{x.section}] {x.key}: {x.old} -> {x.new}")
        print("nada a mudar" if not ch else ("aplicado (lido de volta e confirmado)" if apply else "(dry-run; use --apply)"))
    elif c == "dedup":  # M2.4: só relatório — nunca remove nada
        import hashlib
        from collections import defaultdict
        by_size = defaultdict(list)
        for root in syncer.rom_roots():
            for f in (root.rglob("*") if root.exists() else []):
                if f.is_file() and f.stat().st_size > 1024 * 1024:
                    by_size[f.stat().st_size].append(f)
        groups = defaultdict(list)
        for size, fs in by_size.items():
            if len(fs) > 1:
                for f in fs:
                    h = hashlib.sha256()
                    with open(f, "rb") as fh:
                        for chunk in iter(lambda: fh.read(1 << 22), b""):
                            h.update(chunk)
                    groups[h.hexdigest()].append(f)
        dups = [v for v in groups.values() if len(v) > 1]
        for v in dups:
            print("cópias idênticas (sugestão: manter só uma):")
            for f in v:
                print("   ", f)
        print(f"{len(dups)} grupo(s) de duplicatas. Nada foi apagado.")
    elif c == "duplicados":
        from . import dedup
        lm = json.loads((paths.data / "launch-map.json").read_text("utf-8"))
        for grp in dedup.library_dups(lm):
            print("mesmo jogo:")
            for g in grp:
                print(f"    {g}  ->  {lm[g]['rom']}")
        print("Para remover um:  python3 -m dc x remover <game_id>   (mostra o plano; --confirm executa)")
    elif c == "remover" and r:
        from . import remove
        from .qbt import Qbt
        lm = json.loads((paths.data / "launch-map.json").read_text("utf-8"))
        hits = [r[0]] if r[0] in lm else remove.find(lm, " ".join(x for x in r if x != "--confirm"))
        if len(hits) != 1:
            print("seja mais específico:" if hits else "não achei esse jogo", *hits, sep="\n  "); return 1
        rp = remove.plan(paths, hits[0], syncer.rom_roots())
        print(rp.describe())
        if "--confirm" not in r:
            print("(nada foi feito; repita com --confirm)"); return 0
        print("\n".join(remove.apply(paths, _store(paths), rp, Qbt())))
    elif c == "qualidade":
        from . import quality, remove
        lm = json.loads((paths.data / "launch-map.json").read_text("utf-8"))
        if not r:
            print("\n".join(quality.listing(paths, lm)) or "nenhum jogo com qualidade própria"); return 0
        hits = remove.find(lm, " ".join(r[:-1]))
        if len(hits) != 1:
            print("seja mais específico:" if hits else "não achei esse jogo", *hits, sep="\n  "); return 1
        print(lm[hits[0]]["title"] + ": " + quality.set_override(paths, hits[0], lm[hits[0]]["console"], r[-1]))
    elif c == "controles":
        from . import controls
        if r and r[0] in ("labels", "positional"):
            print("\n".join(controls.switch_layout(r[0])) or "já estava assim")
        for x in controls.check():
            print(("ok  " if x.ok else "!!  ") + f"{x.emulator}: {x.detail}")
    elif c == "telegram-pair":
        from .bot import pair_code
        print("Código de pareamento (mande  /start CODIGO  para o seu bot):", pair_code(paths))
    elif c in ("tests", "updates", "backup"):
        return services.main([c])
    else:
        print("comando desconhecido; veja: python3 -m dc x"); return 2
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="dc")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    sub.add_parser("status")
    o = sub.add_parser("op"); o.add_argument("action", choices=["list", "approve", "retry", "cancel"])
    o.add_argument("id", nargs="?")
    b = sub.add_parser("backup"); b.add_argument("action", choices=["create", "list", "verify", "latest"])
    b.add_argument("--kind", default="config")
    r = sub.add_parser("restore"); r.add_argument("snapshot"); r.add_argument("--apply", action="store_true")
    q = sub.add_parser("quarantine"); q.add_argument("action", choices=["list", "clear"]); q.add_argument("id", nargs="?")
    p = sub.add_parser("power"); p.add_argument("--sysfs", default="/sys/class/power_supply")
    e = sub.add_parser("extract"); e.add_argument("archive"); e.add_argument("dest")
    lb = sub.add_parser("library"); lb.add_argument("--apply", action="store_true")
    sk = sub.add_parser("secret"); sk.add_argument("name", choices=["steamgriddb", "telegram"])
    x = sub.add_parser("x", help="comandos do projeto: veja docs/COMANDOS.md"); x.add_argument("args", nargs="*")
    sub.add_parser("artwork")
    sub.add_parser("inventory")
    sub.add_parser("contracts")
    a = ap.parse_args(argv)
    paths = get_paths()

    if a.cmd == "inventory":
        from . import inventory
        j, m, inv = inventory.run(Path.home(), paths)
        print(m.read_text("utf-8"))
        print(f"(salvo em {j} e {m})")
        return 0
    if a.cmd == "x":
        return _extra(paths, a.args)
    if a.cmd == "secret":
        import getpass, os
        paths.ensure()
        val = getpass.getpass(f"Cole a chave {a.name} e aperte Enter (não aparece na tela): ").strip()
        if not val:
            print("nada gravado"); return 1
        if len(val) % 2 == 0 and val[:len(val) // 2] == val[len(val) // 2:]:
            val = val[:len(val) // 2]
            print("aviso: a chave foi colada duas vezes — guardei uma cópia só")
        p = paths.secrets / a.name
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(val + "\n")
        print(f"chave gravada em {p} (permissão 600)"); return 0
    if a.cmd == "artwork":
        from . import artwork, vdf
        key = artwork.read_key(paths.secrets)
        if not key:
            print("sem chave: rode  python3 -m dc secret steamgriddb"); return 1
        from .steam import shortcuts_path
        sc = shortcuts_path()
        grid = Path(sc).parent / "grid"
        fetch = artwork.make_fetch(key)
        ok = fail = 0
        for r in vdf.read_shortcuts(Path(sc)):
            if "dc-launch" not in (r.get("exe") or ""):
                continue
            try:
                res = artwork.fetch_for(r["appid"] & 0xFFFFFFFF, r["AppName"], grid, fetch)
                ok += bool(res["game"])
                print(f"{r['AppName'][:45]:45} -> {res['game']}  novos={len(res['saved'])} já_tinha={len(res['skipped'])}"
                      + (f"  {res.get('error')}" if res.get("error") else ""))
            except Exception as e:  # noqa: BLE001
                fail += 1
                print(f"{r['AppName'][:45]:45} -> ERRO {e}")
        print(f"pronto: {ok} com arte, {fail} erros. Reinicie o Steam se as capas não aparecerem.")
        return 0 if not fail else 1
    if a.cmd == "library":
        return _library(paths, a.apply)
    if a.cmd == "contracts":
        from . import contracts
        problems = contracts.validate(Path(__file__).resolve().parents[1] / "modules")
        print("\n".join(problems) if problems else "contratos OK")
        return 1 if problems else 0

    if a.cmd == "init":
        s = _store(paths)
        print(f"ok: banco v{s.schema_version()} em {paths.db}")
        print("interrompidas:", worker.recover(s, paths) or "nenhuma")
    elif a.cmd == "status":
        s = _store(paths)
        for st in ("running", "pending", "awaiting_approval", "interrupted", "failed"):
            ops = s.list((st,))
            print(f"{st}: {len(ops)}" + "".join(f"\n  {x.id} {x.type} {x.error or ''}" for x in ops))
        for qe in quarantine.list_entries(paths.quarantine):
            if qe.overdue:
                print(f"AVISO quarentena com revisão vencida: {qe.id} ({qe.reason})")
    elif a.cmd == "op":
        s = _store(paths)
        if a.action == "list":
            for x in s.list():
                print(f"{x.id} {x.state:18} {x.type} {x.error or ''}")
        else:
            if not a.id:
                raise SystemExit("informe o id")
            try:
                getattr(s, a.action)(a.id)
            except (ApprovalError, ValueError) as err:
                print(f"recusado: {err}"); return 1
            print("ok")
    elif a.cmd == "backup":
        paths.ensure()
        if a.action == "create":
            res = backup.create_snapshot(backup_sources(paths), paths.backups, paths.quarantine, kind=a.kind)
            for w in res.warnings:
                print("aviso:", w)
            print(f"ok: {res.path}" if res.ok else f"FALHOU: {res.error}")
            return 0 if res.ok else 1
        if a.action == "list":
            for sn in backup.list_snapshots(paths.backups, a.kind):
                print(sn.name)
        elif a.action == "verify":
            bad = 0
            for sn in backup.list_snapshots(paths.backups, a.kind):
                pr = backup.verify_snapshot(sn); bad += bool(pr)
                print(sn.name, "OK" if not pr else "INVÁLIDO: " + "; ".join(pr[:3]))
            return 1 if bad else 0
        elif a.action == "latest":
            try:
                sn, warns = backup.latest_valid(paths.backups, paths.quarantine, a.kind)
            except backup.AllBackupsCorrupt as err:
                print(f"SOS: {err}"); return 2
            for w in warns:
                print("aviso:", w)
            print(sn)
    elif a.cmd == "restore":
        snap = Path(a.snapshot)
        if not snap.is_absolute():
            snap = paths.backups / snap
        plan = backup.restore_snapshot(snap, dry_run=True)
        for src, dst in plan:
            print(f"{src} -> {dst}")
        if a.apply:
            from .ops import SteamGuard
            backup.restore_snapshot(snap, dry_run=False, steam_guard=SteamGuard() if backup.touches_steam(snap) else None)
            print("restaurado")
        else:
            print("(dry-run; use --apply)")
    elif a.cmd == "quarantine":
        if a.action == "list":
            for qe in quarantine.list_entries(paths.quarantine):
                print(f"{qe.id}  revisar até {qe.review_by[:10]}{'  [VENCIDO]' if qe.overdue else ''}  {qe.reason}")
        else:
            quarantine.clear(paths.quarantine, a.id); print("removido")
    elif a.cmd == "power":
        rd = read_power(Path(a.sysfs))
        print(json.dumps({"ac_online": rd.ac_online, "battery_pct": rd.battery_pct,
                          "battery_status": rd.battery_status,
                          "supplies": [s.__dict__ for s in rd.supplies]}, indent=1))
        print("decisão:", PowerPolicy().desired(rd))
    elif a.cmd == "extract":
        try:
            out = safe_extract.extract(Path(a.archive), Path(a.dest))
        except safe_extract.UnsafeArchive as err:
            paths.ensure()
            qd = quarantine.quarantine(Path(a.archive), paths.quarantine, f"arquivo suspeito: {err}")
            print(f"REJEITADO: {err}\nem quarentena: {qd}"); return 1
        print(f"ok: {len(out)} arquivos em {a.dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
