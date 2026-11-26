import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from dc.romm_client import RommClient, RommError


def test_scan_e_consulta_por_http_local():
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            requests.append((self.path, self.headers.get("Authorization")))
            self.send_response(202)
            self.end_headers()
            self.wfile.write(json.dumps({"id": "123"}).encode())

        def do_GET(self):
            requests.append((self.path, self.headers.get("Authorization")))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({"id": "123", "status": "queued"}).encode())

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = RommClient(f"http://127.0.0.1:{server.server_port}", "chave-de-teste")
        task = client.iniciar_scan()
        assert client.consultar_tarefa(task["id"])["status"] == "queued"
        assert requests == [("/api/tasks/scan", "Bearer chave-de-teste"),
                            ("/api/tasks/123", "Bearer chave-de-teste")]
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_url_sem_credenciais_e_validacao_de_id():
    with pytest.raises(ValueError):
        RommClient("https://usuario:senha@example.com", "token")
    with pytest.raises(ValueError):
        RommClient("http://127.0.0.1", "token").consultar_tarefa("")
