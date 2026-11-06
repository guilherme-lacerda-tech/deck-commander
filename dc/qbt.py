"""Cliente mínimo da WebAPI do qBittorrent (stdlib). Detecta a versão: 5.x usa stop/start,
4.x usa pause/resume (achado F11). WebUI só em 127.0.0.1 com bypass de auth local."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from typing import Optional

DEFAULT_URL = "http://127.0.0.1:8790"


class QbtError(RuntimeError):
    pass


class Qbt:
    def __init__(self, url: str = DEFAULT_URL, timeout: float = 15):
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
        self._v5: Optional[bool] = None

    def _req(self, path: str, data: Optional[dict] = None) -> bytes:
        body = urllib.parse.urlencode(data).encode() if data is not None else None
        req = urllib.request.Request(f"{self.url}/api/v2/{path}", data=body,
                                     headers={"Referer": self.url, "User-Agent": "deck-commander"})
        try:
            with self.opener.open(req, timeout=self.timeout) as r:
                return r.read()
        except OSError as e:
            raise QbtError(f"qBittorrent indisponível: {e}") from e

    def version(self) -> str:
        return self._req("app/version").decode().strip()

    @property
    def v5(self) -> bool:
        if self._v5 is None:
            self._v5 = int(self.version().lstrip("v").split(".")[0]) >= 5
        return self._v5

    def add(self, magnet: str, category: str, save_path: str) -> None:
        if not magnet.startswith("magnet:?"):
            raise QbtError("link inválido: envie um magnet:?")
        out = self._req("torrents/add", {"urls": magnet, "category": category, "savepath": save_path,
                                         "tags": "deck-commander"}).decode()
        if "Fails" in out:
            raise QbtError("o qBittorrent recusou o magnet")

    def add_file(self, data: bytes, filename: str, category: str, save_path: str) -> None:
        """Envia um arquivo .torrent (multipart/form-data)."""
        if not data.startswith(b"d"):
            raise QbtError("isso não parece um arquivo .torrent")
        boundary = "----deckcommander" + str(abs(hash(data)) % 10**12)
        parts = []
        for k, v in (("category", category), ("savepath", save_path), ("tags", "deck-commander")):
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="torrents"; filename="{filename}"\r\n'
                     f"Content-Type: application/x-bittorrent\r\n\r\n".encode() + data + b"\r\n")
        body = b"".join(parts) + f"--{boundary}--\r\n".encode()
        req = urllib.request.Request(f"{self.url}/api/v2/torrents/add", data=body, headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}", "Referer": self.url})
        try:
            with self.opener.open(req, timeout=self.timeout) as r:
                out = r.read().decode()
        except urllib.error.HTTPError as e:
            if e.code in (409, 415):  # qBittorrent 5: 415 = arquivo inválido, 409 = já existe
                raise QbtError("arquivo .torrent inválido" if e.code == 415 else "esse torrent já está na lista") from e
            raise QbtError(f"qBittorrent respondeu erro {e.code}") from e
        except OSError as e:
            raise QbtError(f"qBittorrent indisponível: {e}") from e
        if "Fails" in out:
            raise QbtError("o qBittorrent recusou o arquivo .torrent")

    def torrents(self, category: Optional[str] = None, tag: str = "deck-commander") -> list[dict]:
        q = {"tag": tag}
        if category:
            q["category"] = category
        return json.loads(self._req("torrents/info?" + urllib.parse.urlencode(q)))

    def files(self, h: str) -> list[dict]:
        return json.loads(self._req("torrents/files?" + urllib.parse.urlencode({"hash": h})))

    def pause(self, hashes: list[str]) -> None:
        if hashes:
            self._req("torrents/stop" if self.v5 else "torrents/pause", {"hashes": "|".join(hashes)})

    def resume(self, hashes: list[str]) -> None:
        if hashes:
            self._req("torrents/start" if self.v5 else "torrents/resume", {"hashes": "|".join(hashes)})

    def delete(self, h: str) -> None:
        """Remove só o torrent da lista (os arquivos ficam)."""
        self._req("torrents/delete", {"hashes": h, "deleteFiles": "false"})


DONE_STATES = {"uploading", "stalledUP", "pausedUP", "stoppedUP", "queuedUP", "forcedUP", "checkingUP"}
