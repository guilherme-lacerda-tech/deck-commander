"""Jogos do PC no Steam Deck (aba "Computador"): acorda o PC, espera o Sunshine e transmite pelo Moonlight.

Fluxo de um atalho do console "pc" (game_id "pc-<slug>", criado por `sincronizar()`):
  dc-launch pc-<slug> -> jogar(app):
    1. acordar(): porteiro (Fire TV) pela Tailscale -> porteiro na rede de casa -> magic packet direto;
    2. esperar_pronto(): porta 47989 do Sunshine (Tailscale ou rede de casa) por até ~90 s;
    3. `flatpak run com.moonlight_stream.Moonlight stream <host> "<app>" --quit-after ...`
       (o Steam Input entrega os botões do Deck ao Moonlight, que os passa ao PC como controle Xbox);
    4. ao sair, `moonlight quit <host>` garante que o jogo fecha no PC; o Sunshine roda o "undo" do jogo
       (fecha os processos da pasta dele) e o agente da casa põe o PC para dormir 2 min depois
       (só se o PC foi acordado pela rede e ninguém o usa).

Config (segredo: o código do porteiro) em ~/.local/share/deck-commander/pc-remoto.json (permissão 600).
A lista de jogos vem do PC (`moonlight list --csv`), que é gerada lá por tools/pc/biblioteca-pc.ps1.
Só biblioteca padrão.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import signal
import socket
import subprocess
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

from .arquivo_json import gravar as _save
from .arquivo_json import ler as _load
from .paths import Paths, get_paths

CONSOLE = "pc"
LABEL = "Computador"
MOONLIGHT = "com.moonlight_stream.Moonlight"
FLATPAK = "/usr/bin/flatpak"
PORTA_SUNSHINE = 47989
TEMPLATE_CONTROLE = "controller_neptune_gamepad+mouse.vdf"  # "Gamepad com trackpad como mouse"

DEFAULT = {
    # Nada da rede de ninguém fica no código: cada Deck configura o próprio PC (python3 -m dc x pc config ...).
    "host_tailscale": "",          # IP do PC na Tailscale (para jogar fora de casa)
    "host_casa": "",               # IP do PC no WiFi de casa
    "rede_casa": "",               # começo do IP da rede de casa (ex.: "192.168.0.")
    "mac": "",                     # MAC da placa de rede do PC (para acordar direto, em casa)
    "broadcast": "255.255.255.255",
    "porteiro": [],                # opcional: aparelho sempre ligado em casa que acorda o PC (URL ...?t=código)
    "codigo": "",
    "espera_pronto_s": 90,
    "moonlight_args": ["--resolution", "1280x800", "--fps", "60", "--display-mode", "fullscreen",
                       "--frame-pacing", "--no-audio-on-host", "--video-codec", "HEVC", "--quit-after"],
    "bitrate_casa": 30000,
    "bitrate_fora": 15000,
    "fechar_no_pc": True,
    "nomes": {"Desktop": "Área de trabalho do PC", "Steam Big Picture": "Steam do PC"},
}


# ------------------------------------------------------------------------------------------- config
def config_path(paths: Paths) -> Path:
    return paths.data / "pc-remoto.json"


def carregar_config(paths: Paths) -> dict:
    cfg = json.loads(json.dumps(DEFAULT))
    try:
        cfg.update(json.loads(config_path(paths).read_text("utf-8")))
    except (OSError, ValueError):
        pass
    return cfg


def salvar_config(paths: Paths, cfg: dict) -> Path:
    p = config_path(paths)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), "utf-8")
    if os.name == "posix":
        os.chmod(tmp, 0o600)  # tem o código do porteiro
    os.replace(tmp, p)
    return p


# ------------------------------------------------------------------------------------------- rede
def porta_aberta(host: str, porta: int = PORTA_SUNSHINE, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, porta), timeout=timeout):
            return True
    except OSError:
        return False


def online(cfg: dict, timeout: float = 2.0) -> str | None:
    """Host (Tailscale primeiro, depois rede de casa) em que o Sunshine responde; None = PC dormindo/fora."""
    for h in (cfg.get("host_tailscale"), cfg.get("host_casa")):
        if h and porta_aberta(h, PORTA_SUNSHINE, timeout):
            return h
    return None


def em_casa(cfg: dict) -> bool:
    """O Deck está no WiFi de casa? (IP local da rota até o PC; não manda nada pela rede.)"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            if not cfg.get("host_casa") or not cfg.get("rede_casa"):
                return False
            s.connect((cfg["host_casa"], 9))
            return s.getsockname()[0].startswith(cfg["rede_casa"])
    except OSError:
        return False


def magic_packet(mac: str) -> bytes:
    h = re.sub(r"[^0-9A-Fa-f]", "", mac)
    if len(h) != 12:
        raise ValueError(f"MAC inválido: {mac!r}")
    return b"\xff" * 6 + bytes.fromhex(h) * 16


def enviar_wol(mac: str, broadcast: str = "255.255.255.255") -> None:
    pkt = magic_packet(mac)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for porta in (9, 7):
            s.sendto(pkt, (broadcast, porta))


def _http_get(url: str, timeout: float) -> tuple[int, str]:
    with urllib.request.urlopen(url, timeout=timeout) as r:  # noqa: S310 — URLs da config do usuário
        return r.status, r.read(512).decode("utf-8", "replace")


def acordar(cfg: dict, http_get: Callable = _http_get, wol: Callable = enviar_wol) -> tuple[bool, str]:
    """Pede ao porteiro (Tailscale, depois rede de casa) e, se nenhum responder, manda o magic packet direto."""
    if online(cfg, timeout=1.5):
        return True, "o PC já está acordado"
    codigo = cfg.get("codigo") or ""
    erros = []
    if codigo:
        for base in cfg.get("porteiro") or []:
            url = f"{base}?{urllib.parse.urlencode({'t': codigo})}"
            try:
                st, corpo = http_get(url, 6)
                if st == 200:
                    return True, f"porteiro {urllib.parse.urlsplit(base).hostname}: {corpo.strip()[:60]}"
                erros.append(f"{urllib.parse.urlsplit(base).hostname}: HTTP {st}")
            except Exception as e:  # noqa: BLE001
                erros.append(f"{urllib.parse.urlsplit(base).hostname}: {type(e).__name__}")
    else:
        erros.append("sem código do porteiro na config")
    if not cfg.get("mac"):
        erros.append("sem o MAC do PC na config")
        return False, "não consegui pedir para acordar: " + "; ".join(erros)
    try:  # só chega ao PC se o Deck estiver na rede de casa
        wol(cfg["mac"], cfg.get("broadcast") or "255.255.255.255")
        return True, "magic packet direto enviado (" + "; ".join(erros) + ")"
    except Exception as e:  # noqa: BLE001
        erros.append(f"WoL: {e}")
    return False, "não consegui pedir para acordar: " + "; ".join(erros)


def esperar_pronto(cfg: dict, limite: float | None = None, intervalo: float = 3.0,
                   sleep: Callable = time.sleep, relogio: Callable = time.monotonic) -> str | None:
    """Testa a porta 47989 do Sunshine até `limite` segundos (padrão da config, ~90 s). Devolve o host."""
    limite = cfg.get("espera_pronto_s", 90) if limite is None else limite
    fim = relogio() + limite
    while True:
        h = online(cfg)
        if h:
            return h
        if relogio() >= fim:
            return None
        sleep(intervalo)


# ------------------------------------------------------------------------------------------- moonlight
def _moonlight(*args: str) -> list[str]:
    return [FLATPAK, "run", MOONLIGHT, *args]


def comando_stream(cfg: dict, host: str, app: str, casa: bool) -> list[str]:
    args = list(cfg.get("moonlight_args") or [])
    if "--bitrate" not in args:
        args += ["--bitrate", str(cfg["bitrate_casa"] if casa else cfg["bitrate_fora"])]
    return _moonlight("stream", host, app, *args)


def parse_lista(saida: str) -> list[str]:
    """Saída real do `moonlight list --csv` (Moonlight 6.2.0 no Deck, 2026-11-10):
        Name, ID, HDR Support, App Collection Game, Hidden, Direct Launch, Boxart URL
        "Desktop",881448767,true,false,false,false,"file:///…/881448767.png"
    Sem --csv: um nome por linha. Linhas de log do Qt (stderr misturado) são ignoradas."""
    linhas = [ln for ln in saida.splitlines() if ln.strip()]
    cab = next((i for i, ln in enumerate(linhas) if ln.startswith("Name,") and "ID" in ln), None)
    if cab is None:
        ruido = re.compile(r"^(\d\d:\d\d:\d\d - |_amdgpu|Qt |If this|for more|Failed to)")
        return [ln.strip() for ln in linhas if not ruido.search(ln) and not ln.startswith(" ")]
    out = []
    head = [c.strip().lower() for c in next(csv.reader([linhas[cab]]))]
    i_hidden = head.index("hidden") if "hidden" in head else None
    for row in csv.reader(io.StringIO("\n".join(linhas[cab + 1:]))):
        if not row or not row[0].strip():
            continue
        if len(row) < 2 or not row[1].strip().lstrip("-").isdigit():
            continue  # linha de log que escapou
        if i_hidden is not None and len(row) > i_hidden and row[i_hidden].strip().lower() == "true":
            continue
        out.append(row[0])
    return out


def _run_grupo(cmd: list[str], capture_output=True, text=True, timeout: float = 40):
    """subprocess.run que, no tempo-limite, mata o grupo inteiro (o flatpak deixa o bwrap/moonlight órfãos)."""
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=text, start_new_session=True)
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except (OSError, AttributeError):
            p.kill()
        p.communicate()
        raise
    return subprocess.CompletedProcess(cmd, p.returncode, out, err)


def lista_do_pc_path(paths: Paths) -> Path:
    """Lista de jogos que o próprio PC manda para o Deck (tools/pc/transferir-fila.ps1, a cada 5 min)."""
    return paths.data / "pc-apps.json"


def lista_do_pc(paths: Paths) -> list[str]:
    try:
        d = json.loads(lista_do_pc_path(paths).read_text("utf-8-sig"))
    except (OSError, ValueError):
        return []
    return [a for a in (d.get("apps") or []) if isinstance(a, str) and a.strip()]


def listar_apps(cfg: dict, host: str, run: Callable | None = None) -> list[str]:
    # Obs.: sem tela (bot/ssh), o "moonlight list" TRAVA quando precisa baixar a capa de um app novo (defeito do
    # Moonlight: QEventLoop sem QCoreApplication). Por isso a fonte principal é a lista que o PC manda.
    r = (run or _run_grupo)(_moonlight("list", "--csv", host), capture_output=True, text=True, timeout=40)
    txt = (r.stdout or "") + "\n" + (r.stderr or "")
    if r.returncode != 0 or "Failed to connect" in txt:
        raise RuntimeError(f"o Moonlight não conseguiu listar os jogos de {host}")
    apps = parse_lista(r.stdout or "")
    if not apps:
        raise RuntimeError(f"o Moonlight não devolveu nenhum app de {host}")
    return apps


def jogar(app: str, paths: Paths | None = None, cfg: dict | None = None, say: Callable = print,
          popen: Callable = subprocess.Popen, run: Callable = subprocess.run,
          acordar_fn: Callable = None, esperar_fn: Callable = None) -> tuple[int, str]:
    """Acorda o PC, espera o Sunshine e transmite `app`. Devolve (código, mensagem para a tela se falhou)."""
    paths = paths or get_paths()
    cfg = cfg or carregar_config(paths)
    ok, como = (acordar_fn or acordar)(cfg)
    say(f"pc: acordar -> {como}")
    if not ok:
        return 1, f"{app}: não consegui acordar o PC ({como})."
    host = (esperar_fn or esperar_pronto)(cfg)
    if not host:
        return 1, (f"{app}: o PC não respondeu em {cfg.get('espera_pronto_s', 90)} s. "
                   "Fora de casa: a Tailscale do Deck está ligada? Tente de novo em 1 min.")
    casa = em_casa(cfg)
    cmd = comando_stream(cfg, host, app, casa)
    say(f"pc: transmitindo de {host} ({'casa' if casa else 'fora'}): {cmd}")
    paths.logs.mkdir(parents=True, exist_ok=True)
    log = open(paths.logs / "moonlight.log", "a", encoding="utf-8")
    log.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} {app} @ {host}\n"); log.flush()
    child = popen(cmd, stdout=log, stderr=subprocess.STDOUT)

    def fechar_no_pc() -> None:
        if cfg.get("fechar_no_pc", True):
            try:
                run(_moonlight("quit", host), capture_output=True, timeout=25)
                say("pc: pedido para fechar o jogo no PC enviado")
            except Exception as e:  # noqa: BLE001
                say(f"pc: quit falhou ({e})")

    def _parar(signum, _frame):  # "Sair do jogo" do Steam
        try:
            child.send_signal(signum)
            run([FLATPAK, "kill", MOONLIGHT], capture_output=True, timeout=10)
            child.wait(timeout=8)
        except Exception:  # noqa: BLE001
            try:
                child.kill()
            except Exception:  # noqa: BLE001
                pass
        fechar_no_pc()
        raise SystemExit(128 + signum)

    antigos = {}
    for s in (signal.SIGTERM, getattr(signal, "SIGHUP", None)):
        if s is not None:
            try:
                antigos[s] = signal.signal(s, _parar)
            except (ValueError, OSError):  # fora da thread principal (testes)
                pass
    try:
        code = child.wait()
    finally:
        for s, h in antigos.items():
            signal.signal(s, h)
        log.close()
    fechar_no_pc()
    agendar_sincronizar(paths, run=run)
    if code:
        return code, f"{app}: o Moonlight saiu com erro {code} (detalhes em moonlight.log)."
    return 0, ""


def agendar_sincronizar(paths: Paths, run: Callable = subprocess.run) -> None:
    """Depois de jogar o PC ainda está acordado ~2 min: atualiza a lista de jogos fora do processo do Steam."""
    repo = str(Path(__file__).resolve().parents[1])
    try:
        run(["systemd-run", "--user", "--collect", "--unit=dc-pc-sincronizar", f"--working-directory={repo}",
             "python3", "-m", "dc", "x", "pc", "sincronizar"], capture_output=True, timeout=10)
    except Exception:  # noqa: BLE001 — conforto; o /pc sincronizar faz o mesmo
        pass


# ------------------------------------------------------------------------------------------- biblioteca
def game_id(app: str) -> str:
    from .library import slug
    return f"{CONSOLE}-{slug(app) or 'app'}"



def entradas(apps: list[str], cfg: dict) -> dict:
    nomes = cfg.get("nomes") or {}
    out = {}
    for a in apps:
        gid = game_id(a)
        if gid not in out:
            out[gid] = {"title": nomes.get(a, a), "console": CONSOLE, "rom": f"pc:{a}", "app": a}
    return out


def sincronizar(paths: Paths, cfg: dict | None = None, apps: list[str] | None = None,
                run: Callable = subprocess.run, shortcuts: list[dict] | None = None,
                plugin_ativo: bool | None = None) -> dict:
    """Lista do PC -> launch-map (console "pc") -> atalhos (plugin ao vivo) -> abas/coleção "Computador".
    Jogos que sumiram do PC saem do mapa e o atalho é removido. Retorna o resumo."""
    from . import library, plugin_bridge
    cfg = cfg or carregar_config(paths)
    if apps is None:
        apps = lista_do_pc(paths) or None  # o PC manda a lista dele (não depende do PC acordado nem do Moonlight)
    if apps is None:
        host = online(cfg)
        if not host:
            raise RuntimeError("o PC está dormindo ou fora de alcance (mande /pc acordar e tente em ~1 min)")
        apps = listar_apps(cfg, host, run=None if run is subprocess.run else run)
    lm_p = paths.data / "launch-map.json"
    lm = _load(lm_p, {})
    novos = entradas(apps, cfg)
    atuais = {g: e for g, e in lm.items() if e.get("console") == CONSOLE}
    estado_p = paths.state / "pc-remoto.json"
    estado = _load(estado_p, {"tirados": []})
    tirados = set(estado.get("tirados") or [])
    done = _load(plugin_bridge.done_path(paths), {})

    saem = sorted(set(atuais) - set(novos))
    for gid in saem:
        lm.pop(gid, None)
        if done.get(gid, {}).get("appid") or gid in plugin_bridge.pending(paths):
            _tirar_atalho(paths, gid, done.get(gid, {}).get("appid"))
        tirados.add(gid)
    entram = []
    for gid, e in novos.items():
        keep = {k: v for k, v in atuais.get(gid, {}).items() if k == "removed"}  # removido por você fica removido
        lm[gid] = {**e, **keep}
        if gid not in atuais:
            entram.append(gid)
        if gid in tirados:  # voltou ao PC: libera o atalho que nós (não você) tiramos
            if done.get(gid, {}).get("removed"):
                # antes: gravava a cópia de `done` lida no começo, apagando o que _tirar_atalho tinha acabado de
                # marcar para outros jogos (revisão de lançamento 12/11/2026)
                plugin_bridge.atualizar(plugin_bridge.done_path(paths), {}, lambda d, g=gid: d.pop(g, None))
            tirados.discard(gid)
    _save(lm_p, lm)
    _save(estado_p, {"tirados": sorted(tirados)})

    # atalhos: mesmo lançador fixo (dc-launch <game_id>) dos outros consoles
    launcher = library.launcher_path(Path.home())
    if shortcuts is None:
        try:
            from . import syncer, vdf
            shortcuts = vdf.read_shortcuts(syncer.shortcuts_path())
        except Exception:  # noqa: BLE001
            shortcuts = []
    nomes_existentes = {(r.get("AppName") or r.get("appname") or "").casefold() for r in shortcuts
                        if "dc-launch" not in (r.get("exe") or r.get("Exe") or "")}
    jogos = []
    for gid, e in novos.items():
        if lm[gid].get("removed"):
            continue
        t = e["title"] if e["title"].casefold() not in nomes_existentes else f"{e['title']} (PC)"
        jogos.append(library.Game(gid, t, CONSOLE, e["rom"]))
    pl = library.plan(shortcuts, jogos, launcher)
    ativo = plugin_bridge.active() if plugin_ativo is None else plugin_ativo
    criados: list[str] = []
    aviso = ""
    if pl.add:
        library.write_launcher(Path.home(), Path(__file__).resolve().parents[1])
        if ativo:
            busy = set(plugin_bridge.pending(paths)) | set(plugin_bridge.known(paths))
            rows = [r for r in pl.add if r["LaunchOptions"] not in busy]
            plugin_bridge.enqueue(paths, rows)
            criados = [r["AppName"] for r in rows]
        else:
            aviso = "plugin do Decky desligado: os atalhos do PC entram quando ele voltar (mande /pc sincronizar)"
    controle = garantir_controle([j.title for j in jogos])
    try:
        from . import syncer, tabs, vdf
        sc = syncer.shortcuts_path()
        tabs.write_collections(paths.data, vdf.read_shortcuts(sc), lm)
        if tabs.SETTINGS.exists():
            tabs.apply(vdf.read_shortcuts(sc), lm, sc.parents[1].name, data_dir=paths.data)
    except Exception:  # noqa: BLE001 — aba é conforto
        pass
    return {"apps": apps, "entram": [lm[g]["title"] for g in entram], "saem": [atuais[g]["title"] for g in saem],
            "atalhos": criados, "controle": controle, "aviso": aviso}


def _tirar_atalho(paths: Paths, gid: str, appid) -> None:
    from . import plugin_bridge
    plugin_bridge.marcar_removido(paths, gid, [appid] if appid else [], so_com_plugin=False)  # atalho do PC: só via plugin


# ------------------------------------------------------------------------------------------- controle
def configset_path(home: Path | None = None) -> Path | None:
    """configset_controller_neptune.vdf do usuário Steam ativo (layout do controle por jogo)."""
    home = home or Path.home()
    try:
        from .steam import userdata_dir
        uid = userdata_dir(home / ".steam/steam").name
    except Exception:  # noqa: BLE001
        return None
    p = home / ".steam/steam/steamapps/common/Steam Controller Configs" / uid / "config/configset_controller_neptune.vdf"
    return p if p.exists() else None


def garantir_controle(titulos: list[str], path: Path | None = None) -> list[str]:
    """Atalhos do PC usam o layout "Gamepad com trackpad como mouse" (o Moonlight passa ao PC como controle Xbox).
    Só ACRESCENTA entradas que faltam (chave = nome do atalho em minúsculas; nunca muda o que você escolheu).
    Sem entrada o Steam já usa um layout de gamepad; isto só evita herdar outro por engano."""
    path = path or configset_path()
    if not path:
        return []
    try:
        txt = path.read_text("utf-8")
    except OSError:
        return []
    faltam = []
    for t in titulos:
        k = t.lower().replace('"', "")
        if not re.search(r'^\s*"' + re.escape(k) + r'"\s*$', txt, re.MULTILINE) and k not in faltam:
            faltam.append(k)
    fim = txt.rstrip().rfind("}")
    if not faltam or fim < 0:
        return []
    bak = path.with_name(path.name + ".antes-deck-commander")
    if not bak.exists():
        bak.write_text(txt, "utf-8")
    novo = "".join(f'\t"{k}"\n\t{{\n\t\t"template"\t\t"{TEMPLATE_CONTROLE}"\n\t}}\n' for k in faltam)
    tmp = path.with_name(path.name + ".dc-tmp")
    tmp.write_text(txt[:fim] + novo + txt[fim:], "utf-8")
    os.replace(tmp, path)
    return faltam


# ------------------------------------------------------------------------------------------- bot / cli
def status(paths: Paths, cfg: dict | None = None) -> str:
    cfg = cfg or carregar_config(paths)
    host = online(cfg)
    lm = _load(paths.data / "launch-map.json", {})
    n = sum(1 for e in lm.values() if e.get("console") == CONSOLE and not e.get("removed"))
    linhas = [f"🖥️ PC: {'acordado (' + host + ')' if host else 'dormindo ou fora de alcance'}",
              f"Deck {'em casa' if em_casa(cfg) else 'fora de casa'} · {n} jogo(s) do PC na aba {LABEL}"]
    if not cfg.get("codigo"):
        linhas.append(f"⚠️ falta o código do porteiro em {config_path(paths)} (sem ele só acorda em casa)")
    return "\n".join(linhas)


def listar(paths: Paths) -> str:
    lm = _load(paths.data / "launch-map.json", {})
    t = sorted(e["title"] for e in lm.values() if e.get("console") == CONSOLE and not e.get("removed"))
    return (f"Jogos do PC ({len(t)}):\n" + "\n".join(f"• {x}" for x in t)) if t else \
        "Nenhum jogo do PC ainda. Com o PC acordado: /pc sincronizar"


def _resumo(r: dict) -> str:
    out = [f"🖥️ PC: {len(r['apps'])} app(s) no Sunshine"]
    if r["entram"]:
        out.append("Entraram: " + ", ".join(r["entram"]))
    if r["saem"]:
        out.append("Saíram (não estão mais no PC): " + ", ".join(r["saem"]))
    if r["atalhos"]:
        out.append(f"✨ {len(r['atalhos'])} atalho(s) aparecem na aba {LABEL} em ~10 s")
    if r["aviso"]:
        out.append("⚠️ " + r["aviso"])
    if not (r["entram"] or r["saem"] or r["atalhos"]):
        out.append("Nada mudou.")
    return "\n".join(out)


def na_tv(cfg: dict, http_get: Callable = _http_get, acordar_fn: Callable = None,
          esperar_fn: Callable = None) -> tuple[bool, str]:
    """"Jogar na TV": acorda o PC, espera ficar pronto e pede ao agente da casa (opcional, config "agente_url" e
    "agente_token") para pôr a imagem do PC na TV. Só funciona em casa (o agente escuta só a rede local)."""
    url, token = cfg.get("agente_url") or "", cfg.get("agente_token") or ""
    if not url or not token:
        return False, ("Este PC não tem o agente da casa configurado (agente_url e agente_token). "
                       "Sem ele, ligue a TV no PC pelo controle da TV.")
    ok, como = (acordar_fn or acordar)(cfg)
    if not ok:
        return False, f"não consegui acordar o PC ({como})"
    if not (esperar_fn or esperar_pronto)(cfg):
        return False, "o PC não respondeu a tempo; tente de novo em 1 min"
    try:
        st, corpo = http_get(f"{url.rstrip('/')}/tv?{urllib.parse.urlencode({'t': token})}", 20)
    except Exception as e:  # noqa: BLE001
        return False, f"o agente da casa não respondeu ({type(e).__name__}) — o Deck está no WiFi de casa?"
    return (st == 200), ("📺 PC na TV" if st == 200 else f"o agente respondeu {st}: {corpo.strip()[:80]}")


def comando_pc(bot, args: list[str]) -> str:
    """/pc listar | sincronizar | acordar | status — para ligar no bot (handle devolve o texto)."""
    paths = getattr(bot, "paths", None) or get_paths()
    sub = (args[0].lower() if args else "status")
    cfg = carregar_config(paths)
    try:
        if sub in ("listar", "lista", "jogos"):
            return listar(paths)
        if sub in ("sincronizar", "sync"):
            return _resumo(sincronizar(paths, cfg))
        if sub == "acordar":
            ok, como = acordar(cfg)
            return (f"⏰ {como}. O PC leva ~20–40 s; depois: /pc status" if ok else f"❌ {como}")
        if sub == "status":
            return status(paths, cfg)
        if sub == "tv":
            ok, como = na_tv(cfg)
            return (f"{como}. Jogue com um controle ligado no PC." if ok else f"❌ {como}")
    except Exception as e:  # noqa: BLE001
        return f"❌ /pc {sub}: {e}"
    return "Uso: /pc listar | /pc sincronizar | /pc acordar | /pc status | /pc tv"


def cli(paths: Paths, args: list[str]) -> str:
    """python3 -m dc x pc <listar|sincronizar|acordar|status|jogar <app>|config <chave> <valor>>"""
    if args and args[0] == "jogar" and len(args) > 1:
        code, msg = jogar(" ".join(args[1:]), paths)
        return msg or f"saiu com código {code}"
    if args and args[0] == "config":
        cfg = carregar_config(paths)
        if len(args) >= 3:
            cfg[args[1]] = args[2]
            salvar_config(paths, cfg)
            return f"{args[1]} gravado em {config_path(paths)}"
        if not config_path(paths).exists():
            salvar_config(paths, cfg)
        return f"config em {config_path(paths)} (código {'definido' if cfg.get('codigo') else 'FALTANDO'})"
    return comando_pc(type("B", (), {"paths": paths})(), args)
