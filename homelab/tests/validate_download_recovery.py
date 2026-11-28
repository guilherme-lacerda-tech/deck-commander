"""Interrompe um worker real durante HTTPS e verifica sua retomada por Range.

Usa uma cópia do Doom Shareware já adquirido. O servidor TLS é exclusivo do
ensaio, aceita conexões em loopback e serve apenas esse arquivo.
"""
import argparse
import hashlib
import json
import os
import re
import signal
import ssl
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

def until(read, timeout=60):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = read()
        if value:
            return value
        time.sleep(0.03)
    raise TimeoutError("ensaio de retomada")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=False)
    # Alguns módulos calculam caminhos globais no import. Todo o ensaio,
    # inclusive o launcher gerado, deve permanecer no perfil descartável.
    profile = work / "profile"
    os.environ.update(HOME=str(profile), USERPROFILE=str(profile), DC_ROOT=str(profile),
                      DC_BACKUP_DIR=str(profile / "Backups/DeckCommander"),
                      XDG_CONFIG_HOME=str(profile / ".config"),
                      XDG_DATA_HOME=str(profile / ".local/share"),
                      XDG_STATE_HOME=str(profile / ".local/state"),
                      XDG_CACHE_HOME=str(profile / ".cache"),
                      XDG_RUNTIME_DIR=str(profile / "runtime"),
                      DBUS_SESSION_BUS_ADDRESS="unix:path=/nonexistent-dc-recovery-test-bus")
    from dc import catalogo_downloads
    from dc.bot import Bot
    from dc.lock import lock_is_held, read_holder
    from dc.paths import get_paths

    paths = get_paths().ensure()
    (paths.config / "deck.json").write_text(json.dumps({"roms_root": str(work / "roms")}))
    original = catalogo_downloads.pesquisar(paths, "Doom")[0]
    content = args.source.read_bytes()
    sha = hashlib.sha256(content).hexdigest()
    assert sha == original["file_sha256"], "o arquivo fonte diverge do catálogo"
    certificate, private_key = work / "server.crt", work / "server.key"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                    "-keyout", str(private_key), "-out", str(certificate), "-days", "1",
                    "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.chmod(private_key, 0o600)
    os.environ["SSL_CERT_FILE"] = str(certificate)
    requests = []

    class Source(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path != "/doom1.wad":
                self.send_error(404)
                return
            header = self.headers.get("Range")
            match = re.fullmatch(r"bytes=(\d+)-", header or "")
            offset = int(match[1]) if match else 0
            requests.append({"range": header, "offset": offset})
            self.send_response(206 if match else 200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(content) - offset))
            if match:
                self.send_header("Content-Range", f"bytes {offset}-{len(content)-1}/{len(content)}")
            self.end_headers()
            try:
                for start in range(offset, len(content), 65536):
                    self.wfile.write(content[start:start + 65536])
                    self.wfile.flush()
                    time.sleep(0.03)
            except (BrokenPipeError, ConnectionResetError, ssl.SSLError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Source)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certificate, private_key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    entry = {**original, "url": f"https://localhost:{server.server_port}/doom1.wad",
             "sha256": sha, "size": len(content)}
    for key in ("archive_member", "file_sha256", "file_size"):
        entry.pop(key)
    (paths.config / "download-catalog.json").write_text(json.dumps({"version": 1, "games": [entry]}))
    bot = Bot(paths, "local-validation")
    bot.cfg["allowed"] = [1]
    try:
        response = bot.handle_message({"from": {"id": 1}, "chat": {"id": 1}, "text": "Doom"})
        print(response, flush=True)
        partial = paths.data / "catalog-downloads" / sha / "doom1.wad.part"
        until(lambda: partial.exists() and 0 < partial.stat().st_size < len(content))
        holder = read_holder(paths.state / "catalog-worker.lock")
        assert holder["operation_id"] == "catalog-worker" and holder["type"] == catalogo_downloads.TYPE
        os.kill(holder["pid"], signal.SIGKILL)
        until(lambda: not lock_is_held(paths.state / "catalog-worker.lock"), timeout=10)
        preserved = partial.stat().st_size
        assert 0 < preserved < len(content)
        operations = [op for op in bot.store.list() if op.type == catalogo_downloads.TYPE]
        assert len(operations) == 1 and operations[0].state == "running"
        operation_id = operations[0].id
        catalogo_downloads.iniciar(paths)

        def installed():
            op = bot.store.get(operation_id)
            if op.state == "failed":
                raise RuntimeError(op.error)
            result = json.loads(op.result or "{}")
            return result if result.get("phase") in ("installed", "waiting_steam") else None

        result = until(installed)
        target = Path(result["files"][0])
        assert hashlib.sha256(target.read_bytes()).hexdigest() == sha
        assert any(request["offset"] == preserved for request in requests[1:])
        assert len([op for op in bot.store.list() if op.type == catalogo_downloads.TYPE]) == 1
        assert not partial.exists()
        report = {"operation": operation_id, "preserved_bytes": preserved,
                  "total_bytes": len(content), "requests": requests,
                  "sha256": sha, "phase": result["phase"], "file": str(target),
                  "attempts": bot.store.get(operation_id).attempts}
        (work / "result.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2), flush=True)
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=3)
        bot.search_pool.shutdown(wait=True)
        bot.store.close()


if __name__ == "__main__":
    main()
