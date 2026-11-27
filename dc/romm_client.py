"""Cliente HTTP para enfileirar e consultar varreduras do RomM.

Requer uma versão do RomM com POST /api/tasks/scan e GET /api/tasks/{id}.
O servidor deve enxergar a mesma biblioteca em que os arquivos foram publicados.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request


class RommError(RuntimeError):
    """Falha de comunicação ou resposta não reconhecida."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class RommClient:
    def __init__(self, base_url: str, token: str, timeout: float = 15):
        url = urllib.parse.urlsplit(base_url.rstrip("/"))
        if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("URL RomM inválida")
        if not token or "\n" in token or "\r" in token:
            raise ValueError("Token RomM inválido")
        if timeout <= 0:
            raise ValueError("Timeout inválido")
        self.base_url = base_url.rstrip("/")
        self._token = token
        self.timeout = timeout

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.base_url + path, data=data, method=method, headers={
            "Authorization": "Bearer " + self._token, "Accept": "application/json",
            **({"Content-Type": "application/json"} if data is not None else {}),
        })

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        try:
            with urllib.request.build_opener(NoRedirect()).open(req, timeout=self.timeout) as response:
                raw = response.read(1024 * 1024 + 1)
                if len(raw) > 1024 * 1024:
                    raise RommError("Resposta RomM excede o limite")
                result = json.loads(raw)
        except urllib.error.HTTPError as exc:
            raise RommError(f"RomM respondeu HTTP {exc.code}", exc.code) from exc
        except (OSError, ValueError) as exc:
            raise RommError("Falha ao consultar o RomM") from exc
        if not isinstance(result, dict):
            raise RommError("Resposta RomM não é um objeto")
        return result

    def iniciar_scan(self, opcoes: dict | None = None) -> dict:
        """Enfileira uma varredura; retorno não implica que ela terminou."""
        if opcoes is not None and not isinstance(opcoes, dict):
            raise TypeError("opções devem ser um objeto")
        return self._request("POST", "/api/tasks/scan", opcoes)

    def consultar_tarefa(self, task_id: str) -> dict:
        """Lê o estado de uma tarefa retornada pela API."""
        if not isinstance(task_id, str) or not task_id or len(task_id) > 200:
            raise ValueError("Identificador de tarefa inválido")
        return self._request("GET", "/api/tasks/" + urllib.parse.quote(task_id, safe=""))
