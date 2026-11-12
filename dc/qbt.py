"""Cliente mínimo da WebAPI do qBittorrent (stdlib). Detecta a versão: 5.x usa stop/start,
4.x usa pause/resume (achado F11). WebUI só em 127.0.0.1 com bypass de auth local."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

DEFAULT_URL = "http://127.0.0.1:8790"


class QbtError(RuntimeError):
    pass


class Qbt:
    def __init__(self, url: str = DEFAULT_URL, timeout: float = 15):
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
        self._v5: bool | None = None

    def _req(self, path: str, data: dict | None = None) -> bytes:
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

    def add(self, magnet: str, category: str, save_path: str, extra_tags: str = "") -> None:
        if not magnet.startswith("magnet:?"):
            raise QbtError("link inválido: envie um magnet:?")
        out = self._req("torrents/add", {"urls": magnet, "category": category, "savepath": save_path,
                                         "tags": ",".join(filter(None, ["deck-commander", extra_tags]))}).decode()
        if "Fails" in out:
            raise QbtError("o qBittorrent recusou o magnet")

    def add_file(self, data: bytes, filename: str, category: str, save_path: str, extra_tags: str = "") -> None:
        """Envia um arquivo .torrent (multipart/form-data)."""
        if not data.startswith(b"d"):
            raise QbtError("isso não parece um arquivo .torrent")
        boundary = "----deckcommander" + str(abs(hash(data)) % 10**12)
        parts = []
        for k, v in (("category", category), ("savepath", save_path), ("tags", ",".join(filter(None, ["deck-commander", extra_tags])))):
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

    def set_seeding_limits(self, ratio: float, minutes: int) -> None:
        """Ao atingir o limite o torrent é PARADO (continua na lista; o /sync usa normalmente).
        Também aplica QUEUE_PREFS (reaplicado 1x/h pelo serviço de energia)."""
        prefs = {"max_ratio_enabled": ratio >= 0, "max_ratio": ratio,
                 "max_seeding_time_enabled": minutes >= 0, "max_seeding_time": minutes, "max_ratio_act": 0,
                 **QUEUE_PREFS}
        self._req("app/setPreferences", {"json": json.dumps(prefs)})

    def preferences(self) -> dict:
        return json.loads(self._req("app/preferences"))

    def torrents(self, category: str | None = None, tag: str = "deck-commander") -> list[dict]:
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

    def delete(self, h: str, delete_files: bool = False) -> None:
        """Remove o torrent da lista. Arquivos só são apagados com delete_files=True (pedido explícito)."""
        self._req("torrents/delete", {"hashes": h, "deleteFiles": "true" if delete_files else "false"})


DUP_OK_TAG = "dc-dup-ok"  # baixado com /baixar: o usuário quer esta cópia mesmo sendo o mesmo jogo
# Torrent sem fontes (parado há 1 min, < 2 KiB/s) não ocupa vaga da fila: sem isso, 3 torrents mortos
# (max_active_downloads=3) travavam todos os downloads que viessem depois.
QUEUE_PREFS = {"dont_count_slow_torrents": True, "slow_torrent_dl_rate_threshold": 2,
               "slow_torrent_ul_rate_threshold": 2, "slow_torrent_inactive_timer": 60}

DONE_STATES = {"uploading", "stalledUP", "pausedUP", "stoppedUP", "queuedUP", "forcedUP", "checkingUP"}
