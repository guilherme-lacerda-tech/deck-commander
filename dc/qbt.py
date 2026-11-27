"""Cliente mínimo da WebAPI do qBittorrent (stdlib). Detecta a versão: 5.x usa stop/start,
4.x usa pause/resume (achado F11). WebUI só em 127.0.0.1 com bypass de auth local."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path, PurePosixPath

DEFAULT_URL = "http://127.0.0.1:8790"


class QbtError(RuntimeError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Qbt:
    def __init__(self, url: str = DEFAULT_URL, timeout: float = 15):
        self.url = url.rstrip("/")
        self.timeout = timeout
        self._cookies = CookieJar()
        self.opener = urllib.request.build_opener(_NoRedirect(), urllib.request.HTTPCookieProcessor(self._cookies))
        self._v5: bool | None = None
        self._credentials = None
        self._mount = None

    @classmethod
    def from_paths(cls, paths, timeout=15):
        config = paths.config / "qbittorrent.json"
        if not config.exists():
            return cls(timeout=timeout)
        try:
            cfg = json.loads(config.read_text("utf-8"))
            url = urllib.parse.urlsplit(cfg["url"])
            if not url.hostname or url.username is not None or url.password is not None or url.query or url.fragment:
                raise ValueError
            if url.scheme != "https" and not (url.scheme == "http" and url.hostname in ("127.0.0.1", "localhost", "::1")):
                raise ValueError
            client = cls(cfg["url"], timeout)
            client._credentials = (cfg["username"], paths.secrets / "qbittorrent-password")
            local = Path(cfg["local_downloads"]).expanduser()
            remote = PurePosixPath(cfg["remote_downloads"])
            if not local.is_absolute() or not remote.is_absolute() or ".." in remote.parts:
                raise ValueError
            client._mount = (local.resolve(), remote)
            return client
        except (ValueError, TypeError, KeyError, OSError) as exc:
            raise QbtError("Configuração do HomeLab qBittorrent inválida") from exc

    def _open(self, req):
        try:
            return self.opener.open(req, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            if exc.code not in (401, 403) or not self._credentials:
                raise
            exc.close()
        user, secret = self._credentials
        body = urllib.parse.urlencode({"username": user, "password": secret.read_text("utf-8").rstrip("\r\n")}).encode()
        login = urllib.request.Request(self.url + "/api/v2/auth/login", data=body, headers={"Referer": self.url})
        with self.opener.open(login, timeout=self.timeout) as response:
            if response.read(64).strip() not in (b"", b"Ok.") or not self._cookies:
                raise QbtError("Login do qBittorrent recusado")
        return self.opener.open(req, timeout=self.timeout)

    def _save_path(self, local):
        if not self._mount:
            return local
        root, remote = self._mount
        try:
            return str(remote / Path(local).resolve().relative_to(root).as_posix())
        except ValueError as exc:
            raise QbtError("Destino fora da pasta compartilhada de downloads") from exc

    def _req(self, path: str, data: dict | None = None) -> bytes:
        body = urllib.parse.urlencode(data).encode() if data is not None else None
        req = urllib.request.Request(f"{self.url}/api/v2/{path}", data=body,
                                     headers={"Referer": self.url, "User-Agent": "deck-commander"})
        try:
            with self._open(req) as r:
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
        out = self._req("torrents/add", {"urls": magnet, "category": category, "savepath": self._save_path(save_path),
                                         "tags": ",".join(filter(None, ["deck-commander", extra_tags]))}).decode()
        if "Fails" in out:
            raise QbtError("o qBittorrent recusou o magnet")

    def add_file(self, data: bytes, filename: str, category: str, save_path: str, extra_tags: str = "") -> None:
        """Envia um arquivo .torrent (multipart/form-data)."""
        if not data.startswith(b"d"):
            raise QbtError("isso não parece um arquivo .torrent")
        boundary = "----deckcommander" + str(abs(hash(data)) % 10**12)
        parts = []
        for k, v in (("category", category), ("savepath", self._save_path(save_path)), ("tags", ",".join(filter(None, ["deck-commander", extra_tags])))):
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        # O nome multipart é decorativo. O nome do conteúdo é lido da metainformação.
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="torrents"; filename="download.torrent"\r\n'
                     f"Content-Type: application/x-bittorrent\r\n\r\n".encode() + data + b"\r\n")
        body = b"".join(parts) + f"--{boundary}--\r\n".encode()
        req = urllib.request.Request(f"{self.url}/api/v2/torrents/add", data=body, headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}", "Referer": self.url})
        try:
            with self._open(req) as r:
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
        torrents = json.loads(self._req("torrents/info?" + urllib.parse.urlencode(q)))
        if self._mount:
            local, remote = self._mount
            for item in torrents:
                path = item.get("content_path")
                if not path:
                    continue
                try:
                    rel = PurePosixPath(path).relative_to(remote)
                    if ".." in rel.parts:
                        raise ValueError
                    actual = (local / rel).resolve()
                    actual.relative_to(local)
                    item["content_path"] = str(actual)
                except ValueError as exc:
                    raise QbtError("Torrent gerenciado fora da pasta compartilhada") from exc
        return torrents

    def files(self, h: str) -> list[dict]:
        return json.loads(self._req("torrents/files?" + urllib.parse.urlencode({"hash": h})))

    def pause(self, hashes: list[str]) -> None:
        if hashes:
            self._req("torrents/stop" if self.v5 else "torrents/pause", {"hashes": "|".join(hashes)})

    def resume(self, hashes: list[str]) -> None:
        if hashes:
            self._req("torrents/start" if self.v5 else "torrents/resume", {"hashes": "|".join(hashes)})

    def set_category(self, h: str, category: str) -> None:
        """Troca a categoria (= console) de um download. O lugar dos arquivos não muda (o /sync lê de onde estiver)."""
        self._req("torrents/setCategory", {"hashes": h, "category": category})

    def delete(self, h: str, delete_files: bool = False) -> None:
        """Remove o torrent da lista. Arquivos só são apagados com delete_files=True (pedido explícito)."""
        self._req("torrents/delete", {"hashes": h, "deleteFiles": "true" if delete_files else "false"})


DUP_OK_TAG = "dc-dup-ok"  # baixado com /baixar: o usuário quer esta cópia mesmo sendo o mesmo jogo
# Torrent sem fontes (parado há 1 min, < 2 KiB/s) não ocupa vaga da fila: sem isso, 3 torrents mortos
# (max_active_downloads=3) travavam todos os downloads que viessem depois.
QUEUE_PREFS = {"dont_count_slow_torrents": True, "slow_torrent_dl_rate_threshold": 2,
               "slow_torrent_ul_rate_threshold": 2, "slow_torrent_inactive_timer": 60}

DONE_STATES = {"uploading", "stalledUP", "pausedUP", "stoppedUP", "queuedUP", "forcedUP"}
