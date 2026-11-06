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
    a = ap.parse_args(argv)
    paths = get_paths()

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
            if backup.touches_steam(snap):
                raise SystemExit("este snapshot toca arquivos do Steam; o fechamento coordenado do Steam "
                                 "depende do spike S3 — restore aplicado bloqueado por enquanto")
            backup.restore_snapshot(snap, dry_run=False)
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
