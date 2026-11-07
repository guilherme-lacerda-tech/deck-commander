#!/usr/bin/env python3
"""Teste de ponta a ponta no Deck, sem internet e sem mandar mensagem no Telegram:
torrent local (jogo falso) -> qBittorrent -> /sync (extração .zip) -> plugin cria o atalho ao vivo ->
o mesmo jogo de novo é barrado como duplicata -> limpeza completa (atalho, arquivos, torrents).
Usa a etiqueta 'dc-e2e' (o bot de verdade só olha 'deck-commander'). Uso: python3 tools/e2e_local.py"""
import hashlib
import json
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dc import plugin_bridge, quarantine, remove, syncer  # noqa: E402
from dc.paths import get_paths  # noqa: E402
from dc.qbt import DONE_STATES, Qbt  # noqa: E402
from dc.store import Store  # noqa: E402

TAG = "dc-e2e"
ROOT = Path("/tmp/dc-e2e")
REPO = Path(__file__).resolve().parents[1]


def benc(x) -> bytes:
    if isinstance(x, int):
        return b"i%de" % x
    if isinstance(x, str):
        x = x.encode()
    if isinstance(x, bytes):
        return b"%d:%s" % (len(x), x)
    if isinstance(x, dict):
        return b"d" + b"".join(benc(k) + benc(v) for k, v in sorted(x.items())) + b"e"
    raise TypeError(x)


def make_torrent(f: Path) -> bytes:
    data, pl = f.read_bytes(), 16384
    pieces = b"".join(hashlib.sha1(data[i:i + pl]).digest() for i in range(0, len(data), pl))
    return benc({"announce": "http://127.0.0.1:9/announce",
                 "info": {"name": f.name, "length": len(data), "piece length": pl, "pieces": pieces, "private": 1}})


class Q(Qbt):
    def torrents(self, category=None, tag=TAG):
        return super().torrents(category, tag)

    def add_local(self, data: bytes, name: str, save: Path) -> None:
        b = "----dce2e"
        parts = [f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
                 for k, v in (("category", "ps2"), ("savepath", str(save)), ("tags", TAG), ("skip_checking", "false"))]
        parts.append(f'--{b}\r\nContent-Disposition: form-data; name="torrents"; filename="{name}"\r\n'
                     f"Content-Type: application/x-bittorrent\r\n\r\n".encode() + data + b"\r\n")
        req = urllib.request.Request(f"{self.url}/api/v2/torrents/add", data=b"".join(parts) + f"--{b}--\r\n".encode(),
                                     headers={"Content-Type": f"multipart/form-data; boundary={b}", "Referer": self.url})
        self.opener.open(req, timeout=15).read()


def cef(expr: str) -> str:
    return subprocess.run([sys.executable, str(REPO / "tools/cef_eval.py"), expr], capture_output=True, text=True).stdout.strip()


def wait_done(q: Q, name: str, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        for t in q.torrents():
            if t["name"] == name and t["state"] in DONE_STATES:
                return t
        time.sleep(2)
    raise SystemExit(f"FALHOU: torrent {name} não completou: {[ (t['name'], t['state']) for t in q.torrents()]}")


def check(ok, msg):
    print(("OK   " if ok else "FALHA ") + msg)
    if not ok:
        check.failed = True


check.failed = False


def main():
    paths = get_paths()
    q, store = Q(), Store(paths.db)
    shutil.rmtree(ROOT, ignore_errors=True)
    (ROOT / "dl").mkdir(parents=True)
    # 1) jogo falso compactado, já "baixado" (o qBittorrent confere e marca 100%)
    z = ROOT / "dl/DC Teste E2E (USA).zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("DC Teste E2E (USA).iso", b"\x01" * 40000)
    q.add_local(make_torrent(z), "e2e1.torrent", ROOT / "dl")
    t1 = wait_done(q, z.name)
    check(True, f"torrent concluído ({t1['state']})")
    out = syncer.run_sync(paths, store, q)
    print("   /sync:", out.replace("\n", " | "))
    check("DC Teste E2E" in out and "❌" not in out, "/sync extraiu o .zip e mandou para o Steam")
    lm = json.loads((paths.data / "launch-map.json").read_text())
    gid = next((g for g, e in lm.items() if e["title"].startswith("DC Teste E2E")), None)
    check(gid is not None, f"jogo no mapa do lançador ({gid})")
    appid = 0
    for _ in range(12):
        time.sleep(5)
        appid = json.loads(plugin_bridge.done_path(paths).read_text()).get(gid, {}).get("appid", 0)
        if appid:
            break
    check(bool(appid), f"plugin criou o atalho ao vivo (appid {appid})")
    check(cef(f"String(!!appStore.GetAppOverviewByAppID({appid}))") == '"true"', "atalho visível no Steam")
    # 2) o mesmo jogo de novo (outro arquivo/nome) => duplicata, sem segundo atalho
    z2 = ROOT / "dl2/DC Teste E2E.zip"
    z2.parent.mkdir()
    with zipfile.ZipFile(z2, "w") as zf:
        zf.writestr("DC Teste E2E.iso", b"\x02" * 40000)
    q.add_local(make_torrent(z2), "e2e2.torrent", z2.parent)
    wait_done(q, z2.name)
    out2 = syncer.run_sync(paths, store, q)
    print("   /sync 2:", out2.replace("\n", " | "))
    check("já tem" in out2 and out2.startswith("0 jogo"), "segunda cópia barrada como duplicata")
    out3 = syncer.run_sync(paths, store, q)
    check(out3.startswith("0 jogo") and "já tem" not in out3, "rodar /sync de novo não reprocessa nada")
    # 3) limpeza: remove o jogo (atalho ao vivo + arquivos + torrent), apaga quarentena e torrents do teste
    rp = remove.plan(paths, gid, syncer.rom_roots())
    for line in remove.apply(paths, store, rp, q):
        print("   remover:", line)
    gone = False
    for _ in range(8):
        time.sleep(5)
        if cef(f"String(!!appStore.GetAppOverviewByAppID({appid}))") == '"false"':
            gone = True
            break
    check(gone, "atalho removido do Steam ao vivo")
    for t in q.torrents():
        q.delete(t["hash"], delete_files=True)
    for e in quarantine.list_entries(paths.quarantine):
        if "E2E" in e.id:
            quarantine.clear(paths.quarantine, e.id)
    st = syncer._state(paths)
    st["ingested"] = {h: v for h, v in st["ingested"].items() if "E2E" not in v.get("name", "")}
    syncer._save_state(paths, st)
    done = json.loads(plugin_bridge.done_path(paths).read_text())
    done.pop(gid, None)
    plugin_bridge.done_path(paths).write_text(json.dumps(done, indent=1, ensure_ascii=False))
    shutil.rmtree(ROOT, ignore_errors=True)
    lm = json.loads((paths.data / "launch-map.json").read_text())
    check(not any("E2E" in e["title"] for e in lm.values()) and not q.torrents(), "limpeza completa")
    print("RESULTADO:", "FALHOU" if check.failed else "TUDO OK")
    sys.exit(1 if check.failed else 0)


if __name__ == "__main__":
    main()
