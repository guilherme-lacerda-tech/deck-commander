"""Teste destrutível apenas em stack dc-audit-* com biblioteca exclusiva. Execute no host Docker Linux."""
import argparse
import hashlib
import http.cookiejar
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from contextlib import closing, contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import libtorrent as lt
import yaml


def command(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT).strip()


def request(url, data=None, headers=None, opener=None, form=False):
    headers = dict(headers or {})
    if data is not None:
        body = urllib.parse.urlencode(data).encode() if form else json.dumps(data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded" if form else "application/json"
    else:
        body = None
    req = urllib.request.Request(url, data=body, headers=headers)
    with (opener or urllib.request.build_opener()).open(req, timeout=30) as response:
        return json.load(response)


def romm_token(url, root):
    jar = http.cookiejar.CookieJar()
    browser = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    heartbeat = wait_for(lambda: request(url + "/api/heartbeat", opener=browser), 150, "boot RomM")
    key = root / "audit-admin-password"
    if heartbeat["SYSTEM"]["SHOW_SETUP_WIZARD"]:
        if not key.is_file():
            key.write_text(secrets.token_urlsafe(32))
        csrf = next(c.value for c in jar if c.name == "romm_csrftoken")
        request(url + "/api/users", {"username": "audit", "password": key.read_text(),
                "email": "audit@example.invalid", "role": "admin"}, {"X-CSRFToken": csrf}, browser)
    return request(url + "/api/token", {"grant_type": "password", "username": "audit",
                   "password": key.read_text(), "scope": "tasks.run roms.read"}, form=True)["access_token"]


def wait_for(read, seconds, name):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            value = read()
        except OSError:
            value = None
        if value:
            return value
        time.sleep(1)
    raise TimeoutError(name)


@contextmanager
def catalog(gateway, game, torrent):
    # Único release deste catálogo Torznab privado: uma ROM autoral de teste.
    class Catalog(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            target = urllib.parse.urlsplit(self.path)
            if target.path == "/file.torrent":
                payload, mime = torrent, "application/x-bittorrent"
            elif urllib.parse.parse_qs(target.query).get("t") == ["caps"]:
                payload = (b'<caps><server title="DC Audit"/><limits max="100" default="50"/>'
                           b'<searching><search available="yes" supportedParams="q"/></searching>'
                           b'<categories><category id="4000" name="PC"/></categories></caps>')
                mime = "application/xml"
            else:
                link = f"http://{gateway}:{self.server.server_port}/file.torrent"
                payload = (f'<rss version="2.0" xmlns:torznab="http://torznab.com/schemas/2015/feed">'
                           f'<channel><title>DC Audit</title><item><title>{game}</title><guid>{link}</guid>'
                           f'<link>{link}</link><category>4000</category><size>24592</size>'
                           f'<pubDate>Mon, 23 Nov 2026 12:00:00 GMT</pubDate>'
                           f'<enclosure url="{link}" length="24592" type="application/x-bittorrent"/>'
                           f'<torznab:attr name="seeders" value="1"/></item></channel></rss>').encode()
                mime = "application/rss+xml"
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    with ThreadingHTTPServer((gateway, 0), Catalog) as srv:
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://{gateway}:{srv.server_port}"
        finally:
            srv.shutdown()
            thread.join()


def main(lab):
    os.umask(0o077)
    settings = yaml.safe_load((lab / "homelab/inventory/lab.yml").read_text())
    target = settings["all"]["children"]["homelab"]["hosts"]["descartavel"]
    project = target["media_stack_project_name"]
    media = Path(target["media_root"]).resolve(strict=True)
    if not project.startswith("dc-audit-") or media.parent != lab or not media.is_dir():
        raise ValueError("exige inventário e biblioteca dedicados ao laboratório")
    home = lab / "home-cliente"
    home.mkdir(exist_ok=True)
    os.environ.update(HOME=str(home), DC_ROOT=str(home))
    from dc import prowlarr, romm_queue, syncer, vdf
    from dc.paths import get_paths
    from dc.qbt import DONE_STATES, Qbt
    from dc.store import Store

    paths = get_paths().ensure()
    roms = media / "library/roms"
    roms.mkdir(parents=True, exist_ok=True)
    steam = home / ".steam/steam/userdata/1/config"
    steam.mkdir(parents=True, exist_ok=True)
    romm = f"http://127.0.0.1:{target['media_stack_romm_port']}"
    idx = f"http://127.0.0.1:{target['media_stack_prowlarr_port']}"
    qurl = f"http://127.0.0.1:{target['media_stack_qbt_port']}"
    token = romm_token(romm, lab)
    (paths.secrets / "romm-token").write_text(token)
    (paths.config / "romm.json").write_text(json.dumps({"url": romm, "roms_root": str(roms)}))
    (paths.config / "deck.json").write_text(json.dumps({"roms_root": str(roms), "downloads_root": str(media / "downloads")}))
    qb = project + "-qbittorrent-1"
    passwords = re.findall(r"temporary password is provided for this session:\s*(\S+)", command("docker", "logs", qb))
    if not passwords:
        raise ValueError("exige o qBittorrent descartável recém-provisionado")
    (paths.secrets / "qbittorrent-password").write_text(passwords[-1])
    (paths.config / "qbittorrent.json").write_text(json.dumps({"url": qurl, "username": "admin",
        "remote_downloads": "/downloads", "local_downloads": str(media / "downloads")}))
    client = Qbt.from_paths(paths)
    print("qBittorrent", client.version(), flush=True)
    net = json.loads(command("docker", "inspect", qb))[0]["NetworkSettings"]["Networks"][project + "_apps"]
    gateway = net["Gateway"]
    title = "Commander NES " + secrets.token_hex(4)
    seed = lab / "seed"
    seed.mkdir(exist_ok=True)
    rom = seed / (title + ".nes")
    # iNES mapper 0: PRG 16 KiB, vetor de reset em $8000 e loop estável, CHR 8 KiB.
    rom.write_bytes(b"NES\x1a\x01\x01" + bytes(10) + b"\x4c\x00\x80" + bytes(16375)
                    + b"\x00\x80" * 3 + bytes(8192))
    fs = lt.file_storage()
    lt.add_files(fs, str(rom))
    meta = lt.create_torrent(fs, 16384, lt.create_torrent.v1_only)
    meta.set_priv(True)
    lt.set_piece_hashes(meta, str(seed))
    torrent = lt.bencode(meta.generate())
    session = lt.session({"listen_interfaces": gateway + ":0", "enable_dht": False,
                          "enable_lsd": False, "enable_upnp": False, "enable_natpmp": False})
    handle = session.add_torrent({"ti": lt.torrent_info(torrent), "save_path": str(seed)})
    wait_for(lambda: handle.status().is_seeding, 25, "seed local")
    key = ET.parse(media / "prowlarr/config.xml").findtext("ApiKey")
    headers = {"X-Api-Key": key}
    with catalog(gateway, title, torrent) as feed:
        definition = next(i for i in request(idx + "/api/v1/indexer/schema", headers=headers)
                          if i["implementation"] == "Torznab")
        for field in definition["fields"]:
            if field["name"] == "baseUrl":
                field["value"] = feed
        profiles = request(idx + "/api/v1/appprofile", headers=headers)
        definition.update(name=title, enable=True, redirect=False, appProfileId=profiles[0]["id"])
        try:
            indexer = request(idx + "/api/v1/indexer", definition, headers)
        except urllib.error.HTTPError as exc:
            if exc.code == 400:
                errors = json.load(exc)
                raise ValueError([(e.get("propertyName"), e.get("errorCode")) for e in errors]) from None
            raise
        (paths.config / "prowlarr.json").write_text(json.dumps({"url": idx, "api_key": key, "indexer_ids": [indexer["id"]]}))
        results = prowlarr.pesquisar(paths, title)
        match = next(r for r in results if r["titulo"] == title)
        data = prowlarr.baixar_torrent(paths, match["download_url"])
        assert data == torrent
        client.add_file(data, "catalogo.torrent", "nes", str(media / "downloads"))
        found = wait_for(lambda: next((r for r in client.torrents() if r["name"] == rom.name), None), 20, "fila")
        client._req("torrents/addPeers", {"hashes": found["hash"], "peers": f"{gateway}:{session.listen_port()}"})
        ready = wait_for(lambda: next((r for r in client.torrents() if r["hash"] == found["hash"]
                         and r["state"] in DONE_STATES and r["progress"] == 1), None), 100, "download completo")
    digest = hashlib.sha256(rom.read_bytes()).digest()
    assert hashlib.sha256(Path(ready["content_path"]).read_bytes()).digest() == digest
    store = Store(paths.db)
    try:
        result = syncer.run_sync(paths, store, client)
        print("sync:", result.splitlines()[0], flush=True)
    finally:
        store.close()
    installed = [p for p in roms.rglob(rom.name) if p.is_file()]
    assert len(installed) == 1 and hashlib.sha256(installed[0].read_bytes()).digest() == digest
    assert any(r["AppName"] == title for r in vdf.read_shortcuts(steam / "shortcuts.vdf"))
    def completed():
        romm_queue.tick(paths)
        with closing(romm_queue._db(paths)) as db:
            row = db.execute("SELECT * FROM scan").fetchone()
            return row["completed"] > 0 and row["completed"] == row["requested"]
    wait_for(completed, 240, "varredura RomM")
    data = request(romm + "/api/roms?" + urllib.parse.urlencode({"search_term": title}),
                   headers={"Authorization": "Bearer " + token})
    assert any(item["fs_name"] == rom.name for item in data["items"])
    print("PASS Prowlarr → .torrent → qBittorrent → SHA-256 → /sync → shortcuts.vdf → RomM", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lab", type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    main(args.lab.resolve(strict=True))
