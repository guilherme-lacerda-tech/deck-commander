"""Spotify no Deck: SUAS playlists no painel e no /musica, tocando com o jogo aberto, sem você abrir o app.

Como funciona (testado em 11/11/2026):
- Conta e lista de playlists: o go-librespot (código aberto, github.com/devgianlu/go-librespot). Entrar na conta é uma
  vez só, por código: o painel mostra um QR (o bot manda o link); você confirma no celular e o Deck guarda o acesso
  (ninguém vê senha). Ele é ligado só por alguns segundos para atualizar a lista e desligado em seguida, para não
  ficar como um aparelho "fantasma" no seu Spotify.
- Tocar: pelo app OFICIAL do Spotify, aberto escondido (dc.audio, MPRIS). O Spotify recusa a chave de áudio da maioria
  das faixas para players que não são o app oficial (go-librespot #279/#317, "lado do Spotify"); contornar isso seria
  quebrar a proteção dele, então não fazemos.
Precisa de Spotify Premium. A API local do go-librespot só escuta em 127.0.0.1:3678.
"""
from __future__ import annotations

import hashlib
import io
import json
import subprocess
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from .paths import Paths

VERSAO = "v0.10.5"
URL = f"https://github.com/devgianlu/go-librespot/releases/download/{VERSAO}/go-librespot_linux_x86_64.tar.gz"
SHA256 = "f08647217d1dced339375680d731bb5fc2410a9d693f2e1235303511c35a051c"  # publicado no release oficial
PORTA = 3678
UNIDADE = "dc-spotify.service"
VALIDADE_LISTA = 6 * 3600  # a lista de playlists é atualizada sozinha a cada 6 h (ou no botão)

CONFIG = f"""# gerado pelo Deck Commander (dc/spotify.py) — usado só para entrar na conta e listar playlists
device_name: Deck Commander (lista)
device_type: computer
zeroconf_enabled: false
credentials:
  type: device_auth       # entrar pelo celular com um código (spotify.com/pair); o acesso fica guardado
audio_backend: pulseaudio
server:
  enabled: true
  address: 127.0.0.1
  port: {PORTA}
"""


def _bin(paths: Paths) -> Path:
    return paths.data / "bin" / "go-librespot"


def _conf_dir(paths: Paths) -> Path:
    return paths.config / "go-librespot"


def _cache(paths: Paths) -> Path:
    return paths.state / "spotify-playlists.json"


def _unit_path() -> Path:
    return Path.home() / ".config/systemd/user" / UNIDADE


def instalado(paths: Paths) -> bool:
    return _bin(paths).exists() and _unit_path().exists()


def _baixar(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as r:  # noqa: S310 — endereço fixo do release oficial
        return r.read()


def instalar(paths: Paths, baixar=_baixar, run=subprocess.run) -> str:
    """Baixa o go-librespot oficial (confere o sha256 publicado) e configura. Pode repetir à vontade."""
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
    u.write_text("[Unit]\nDescription=Deck Commander - conta do Spotify (go-librespot, ligado sob demanda)\n\n"
                 f"[Service]\nExecStart={b} --config_dir {c}\nRestart=on-failure\nRestartSec=5\n", "utf-8")
    run(["systemctl", "--user", "disable", UNIDADE], capture_output=True)  # não liga no boot: só quando precisa
    run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    return "Spotify instalado."


def _servico(acao: str, run=subprocess.run) -> bool:
    return run(["systemctl", "--user", acao, UNIDADE], capture_output=True).returncode == 0


def api(metodo: str, caminho: str, corpo: dict | None = None, timeout: float = 3) -> tuple[int, object]:
    """Chama a API local do go-librespot. (código HTTP, JSON ou None); 0 = serviço fora do ar / sem resposta."""
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


def _ler_cache(paths: Paths) -> dict:
    try:
        return json.loads(_cache(paths).read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def _login_pendente(chamar) -> dict | None:
    cod, ac = chamar("GET", "/auth/code")
    if cod == 200 and isinstance(ac, dict) and ac.get("url"):
        return {"url": ac["url"], "code": ac.get("code", ""), "expira": ac.get("expires_at")}
    return None


def atualizar(paths: Paths, chamar=api, run=subprocess.run, espera: float = 1.0, tentativas: int = 12) -> dict:
    """Liga o go-librespot, e: se falta entrar na conta, devolve {"login": {...}} (o serviço fica ligado esperando);
    se já entrou, guarda a lista de playlists e DESLIGA o serviço. {"erro": ...} se não respondeu."""
    if not instalado(paths):
        instalar(paths, run=run)
    _servico("start", run)
    for _ in range(tentativas):
        login = _login_pendente(chamar)
        if login:
            return {"login": login}
        cod, st = chamar("GET", "/status")
        if cod == 200 and isinstance(st, dict) and st.get("username"):
            cod, d = chamar("GET", "/library/playlists?limit=50", timeout=10)
            lista = [{"nome": x.get("name", "").strip(), "uri": x["uri"], "imagem": x.get("image_url")}
                     for x in ((d or {}).get("items") or []) if x.get("uri")] if cod == 200 else None
            if lista is not None:
                tmp = _cache(paths).with_suffix(".tmp")
                tmp.write_text(json.dumps({"em": time.time(), "playlists": lista}, ensure_ascii=False), "utf-8")
                tmp.replace(_cache(paths))
            _servico("stop", run)
            return {"conectado": True, "playlists": lista or []}
        time.sleep(espera)
    _servico("stop", run)
    return {"erro": "a conta do Spotify não respondeu"}


def estado(paths: Paths, chamar=api, run=subprocess.run) -> dict:
    """{instalado, conectado, login: {url, code} | None, playlists: [...], em} — rápido: usa a lista guardada e só
    consulta o go-librespot se ele estiver ligado (esperando o login) ou se a lista passou de 6 h."""
    c = _ler_cache(paths)
    out = {"instalado": instalado(paths), "conectado": bool(c), "login": None, "playlists": c.get("playlists", []),
           "em": c.get("em")}
    if not out["instalado"]:
        return out
    ativo = run(["systemctl", "--user", "is-active", "--quiet", UNIDADE], capture_output=True).returncode == 0
    if ativo:  # entrando na conta agora
        login = _login_pendente(chamar)
        if login:
            out.update(conectado=False, login=login)
            return out
    if ativo or (c and time.time() - c.get("em", 0) > VALIDADE_LISTA):
        r = atualizar(paths, chamar, run, tentativas=4)
        if r.get("login"):
            out.update(conectado=False, login=r["login"])
        elif r.get("conectado"):
            c = _ler_cache(paths)
            out.update(conectado=True, playlists=c.get("playlists", []), em=c.get("em"))
    return out


def qr_svg(texto: str) -> str:
    """QR do link de login como SVG (data URI) — o mesmo gerador do QR do Telegram, que o painel já mostra."""
    import base64

    from . import qr
    return "data:image/svg+xml;base64," + base64.b64encode(qr.svg(texto).encode()).decode()
