"""Spotify sem abrir o app: o go-librespot (código aberto, github.com/devgianlu/go-librespot) roda como serviço do
usuário no Deck e aparece como "Steam Deck" na lista de aparelhos do Spotify.

Entrar na conta (uma vez): pareamento por código — o Deck pede um código ao Spotify, o painel mostra um QR (e o bot
manda o link no Telegram); você abre no celular, confirma, e o Deck guarda o acesso (não vemos nem guardamos senha).
Depois disso, o painel e o /musica tocam as SUAS playlists direto, com o jogo aberto, sem o app do Spotify.
Precisa de Spotify Premium. API local só no 127.0.0.1:3678 (não aparece na rede).
"""
from __future__ import annotations

import hashlib
import io
import json
import subprocess
import tarfile
import urllib.error
import urllib.request
from pathlib import Path

from .paths import Paths

VERSAO = "v0.10.5"
URL = f"https://github.com/devgianlu/go-librespot/releases/download/{VERSAO}/go-librespot_linux_x86_64.tar.gz"
SHA256 = "f08647217d1dced339375680d731bb5fc2410a9d693f2e1235303511c35a051c"  # publicado no release oficial
PORTA = 3678
UNIDADE = "dc-spotify.service"

CONFIG = f"""# gerado pelo Deck Commander (dc/spotify.py)
device_name: Steam Deck
device_type: computer
zeroconf_enabled: true    # o Deck também aparece no app do celular (Spotify Connect) na mesma rede
credentials:
  type: device_auth       # entrar pelo celular com um código (spotify.com/pair); o acesso fica guardado
audio_backend: pulseaudio
bitrate: 320
server:
  enabled: true
  address: 127.0.0.1
  port: {PORTA}
"""


def _bin(paths: Paths) -> Path:
    return paths.data / "bin" / "go-librespot"


def _conf_dir(paths: Paths) -> Path:
    return paths.config / "go-librespot"


def _unit_path() -> Path:
    return Path.home() / ".config/systemd/user" / UNIDADE


def instalado(paths: Paths) -> bool:
    return _bin(paths).exists() and _unit_path().exists()


def _baixar(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as r:  # noqa: S310 — endereço fixo do release oficial
        return r.read()


def instalar(paths: Paths, baixar=_baixar, run=subprocess.run) -> str:
    """Baixa o go-librespot oficial (confere o sha256 publicado), configura e liga o serviço. Pode repetir à vontade."""
    b = _bin(paths)
    if not b.exists():
        dados = baixar(URL)
        if hashlib.sha256(dados).hexdigest() != SHA256:
            raise RuntimeError("o arquivo baixado do go-librespot não confere (sha256) — não instalei")
        with tarfile.open(fileobj=io.BytesIO(dados)) as tf:
            m = next((x for x in tf.getmembers() if x.isfile() and Path(x.name).name == "go-librespot"), None)
            if not m:
                raise RuntimeError("o pacote do go-librespot veio sem o programa")
            conteudo = tf.extractfile(m).read()
        b.parent.mkdir(parents=True, exist_ok=True)
        tmp = b.with_name(b.name + ".tmp")
        tmp.write_bytes(conteudo)
        tmp.chmod(0o755)
        tmp.replace(b)
    c = _conf_dir(paths)
    c.mkdir(parents=True, exist_ok=True)
    (c / "config.yml").write_text(CONFIG, "utf-8")
    u = _unit_path()
    u.parent.mkdir(parents=True, exist_ok=True)
    u.write_text("[Unit]\nDescription=Deck Commander - Spotify (go-librespot)\nAfter=pipewire-pulse.service\n\n"
                 f"[Service]\nExecStart={b} --config_dir {c}\nRestart=on-failure\nRestartSec=5\n\n"
                 "[Install]\nWantedBy=default.target\n", "utf-8")
    run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    r = run(["systemctl", "--user", "enable", "--now", UNIDADE], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("não consegui ligar o serviço do Spotify: " + (r.stderr or "").strip()[-200:])
    py = paths.data / "venv/bin/python"  # QR do login (biblioteca qrcode, só no ambiente do Deck Commander)
    if py.exists():
        run([str(py), "-m", "pip", "install", "-q", "qrcode"], capture_output=True, timeout=120)
    return "Spotify instalado."


def api(metodo: str, caminho: str, corpo: dict | None = None, timeout: float = 3) -> tuple[int, object]:
    """Chama a API local do go-librespot. (código HTTP, JSON ou None); 0 = serviço fora do ar."""
    req = urllib.request.Request(f"http://127.0.0.1:{PORTA}{caminho}", method=metodo,
                                 data=json.dumps(corpo).encode() if corpo is not None else None,
                                 headers={"Content-Type": "application/json"} if corpo is not None else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 — só localhost
            txt = r.read().decode("utf-8", "replace")
            return r.status, (json.loads(txt) if txt.strip() else None)
    except urllib.error.HTTPError as e:
        return e.code, None
    except (OSError, ValueError):
        return 0, None


def estado(paths: Paths, chamar=api) -> dict:
    """{instalado, rodando, conectado, usuario, login: {url, code} | None, tocando: {...} | None}"""
    out = {"instalado": instalado(paths), "rodando": False, "conectado": False, "usuario": None, "login": None,
           "tocando": None}
    if not out["instalado"]:
        return out
    cod, st = chamar("GET", "/status")
    if cod == 0:
        return out
    out["rodando"] = True
    if cod == 200 and isinstance(st, dict) and st.get("username"):
        out.update(conectado=True, usuario=st["username"])
        t = st.get("track") or None
        if t:
            out["tocando"] = {"titulo": t.get("name", ""), "artista": ", ".join(t.get("artist_names") or []),
                              "estado": "Paused" if st.get("paused") else "Playing", "capa": t.get("album_cover_url")}
        return out
    cod, ac = chamar("GET", "/auth/code")
    if cod == 200 and isinstance(ac, dict) and ac.get("url"):
        out["login"] = {"url": ac["url"], "code": ac.get("code", ""), "expira": ac.get("expires_at")}
    return out


def minhas_playlists(chamar=api) -> list[dict]:
    """As playlists da conta (nome, uri, imagem). Lista vazia se a versão/conta não permitir."""
    cod, d = chamar("GET", "/library/playlists?limit=50", timeout=8)
    if cod != 200 or not isinstance(d, dict):
        return []
    return [{"nome": x.get("name", ""), "uri": x["uri"], "imagem": x.get("image_url")}
            for x in d.get("items") or [] if x.get("uri")]


def tocar(uri: str, chamar=api) -> bool:
    return chamar("POST", "/player/play", {"uri": uri}, timeout=10)[0] in (200, 204)


MIDIA = {"tocar_pausar": "/player/playpause", "tocar": "/player/resume", "pausar": "/player/pause",
         "proxima": "/player/next", "anterior": "/player/prev"}


def midia(acao: str, chamar=api) -> bool:
    caminho = MIDIA.get(acao)
    return bool(caminho) and chamar("POST", caminho, {} if acao == "proxima" else None)[0] in (200, 204)


def qr_svg(paths: Paths, texto: str, run=subprocess.run) -> str | None:
    """QR do link de login como SVG (data URI) para o painel; None se a biblioteca não estiver instalada."""
    py = paths.data / "venv/bin/python"
    if not py.exists():
        return None
    cod = ("import sys,io,qrcode,qrcode.image.svg as s;i=qrcode.make(sys.argv[1],image_factory=s.SvgPathFillImage,"
           "box_size=10,border=2);b=io.BytesIO();i.save(b);sys.stdout.write(b.getvalue().decode())")
    try:
        r = run([str(py), "-c", cod, texto], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0 or "<svg" not in r.stdout:
        return None
    import base64
    return "data:image/svg+xml;base64," + base64.b64encode(r.stdout.encode()).decode()
