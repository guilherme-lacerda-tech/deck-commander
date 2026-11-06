"""M12/M15 — instalação idempotente por módulo (`setup-deck.sh --modules M0,M4 | --all [--dev]`).

Tudo no $HOME (nada em /usr): unidades systemd --user, venv, qbittorrent-nox estático em ~/.local/bin,
cores do RetroArch, overrides de Flatpak. `--production` (padrão) não instala ferramentas de dev.
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import urllib.request
import zipfile
from pathlib import Path

from . import contracts, emulators
from .paths import Paths

H = Path.home()
REPO = Path(__file__).resolve().parents[1]
UNITS = H / ".config/systemd/user"
QBT_BIN = H / ".local/bin/qbittorrent-nox"
QBT_URL = "https://github.com/userdocs/qbittorrent-nox-static/releases/latest/download/x86_64-qbittorrent-nox"
QBT_PROFILE = H / ".local/share/deck-commander/qbittorrent"
PY = "/usr/bin/python3"

UNIT_FILES = {
    "deck-commander-qbittorrent.service": f"""[Unit]
Description=Deck Commander — qBittorrent (WebUI só em 127.0.0.1:8790)
ConditionPathExists={QBT_BIN}
[Service]
ExecStart={QBT_BIN} --profile={QBT_PROFILE} --confirm-legal-notice
Restart=on-failure
RestartSec=30
[Install]
WantedBy=default.target
""",
    "deck-commander-bot.service": f"""[Unit]
Description=Deck Commander — bot do Telegram
After=network-online.target deck-commander-qbittorrent.service
ConditionPathExists=%h/.config/deck-commander/secrets/telegram
[Service]
WorkingDirectory={REPO}
ExecStart={PY} -c "from dc.bot import main; main()"
Restart=on-failure
RestartSec=30
[Install]
WantedBy=default.target
""",
    "deck-commander-power.service": f"""[Unit]
Description=Deck Commander — monitor de energia e fila
[Service]
WorkingDirectory={REPO}
ExecStart={PY} -m dc.services power
Restart=on-failure
RestartSec=30
[Install]
WantedBy=default.target
""",
    "deck-commander-dashboard.service": f"""[Unit]
Description=Deck Commander — painel local http://127.0.0.1:8765 (desligado por padrão)
[Service]
WorkingDirectory={REPO}
ExecStart={PY} -m dc.services dashboard
[Install]
WantedBy=default.target
""",
}
for _name, _what, _cal, _boot in (("tests", "testes automáticos", "weekly", "15min"),
                                  ("updates", "verificação de updates (não atualiza nada)", "weekly", "20min"),
                                  ("backup", "backup de configs e saves", "daily", "30min")):
    UNIT_FILES[f"deck-commander-{_name}.service"] = f"""[Unit]
Description=Deck Commander — {_what}
[Service]
Type=oneshot
WorkingDirectory={REPO}
ExecStart={PY} -m dc.services {_name}
"""
    UNIT_FILES[f"deck-commander-{_name}.timer"] = f"""[Unit]
Description=Deck Commander — {_what} (agendado)
[Timer]
OnBootSec={_boot}
OnCalendar={_cal}
Persistent=true
[Install]
WantedBy=timers.target
"""

MODULE_UNITS = {  # o que cada módulo liga
    "M0": ["deck-commander-backup.timer"],
    "M4": ["deck-commander-qbittorrent.service", "deck-commander-power.service", "deck-commander-bot.service"],
    "M10": ["deck-commander-tests.timer"],
    "M11": ["deck-commander-updates.timer"],
}
ALL_MODULES = ["M-1", "M0", "M18+M19", "M27", "M1", "M2", "M3", "M4", "M5", "M6", "M7", "M20", "M21",
               "M10", "M11", "M12", "M15", "M16", "M17"]


def _sc(*a) -> str:
    r = subprocess.run(["systemctl", "--user", *a], capture_output=True, text=True)
    return (r.stdout + r.stderr).strip()


def download(url: str, dest: Path) -> None:
    tmp = dest.with_name(dest.name + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "deck-commander"})
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)
    os.replace(tmp, dest)


def install_qbittorrent(log: list[str]) -> None:
    if not QBT_BIN.exists():
        QBT_BIN.parent.mkdir(parents=True, exist_ok=True)
        download(QBT_URL, QBT_BIN)
        QBT_BIN.chmod(QBT_BIN.stat().st_mode | stat.S_IXUSR)
        log.append(f"baixado qbittorrent-nox -> {QBT_BIN}")
    ver = subprocess.run([str(QBT_BIN), "--version"], capture_output=True, text=True).stdout.strip()
    log.append(f"qbittorrent-nox: {ver}")
    conf = QBT_PROFILE / "qBittorrent/config/qBittorrent.conf"
    if not conf.exists():
        conf.parent.mkdir(parents=True, exist_ok=True)
        dl = H / "Emulation/downloads"; dl.mkdir(parents=True, exist_ok=True)
        conf.write_text(
            "[LegalNotice]\nAccepted=true\n\n"
            f"[BitTorrent]\nSession\\DefaultSavePath={dl}\nSession\\TempPathEnabled=false\n\n"
            "[Preferences]\nWebUI\\Address=127.0.0.1\nWebUI\\Port=8790\nWebUI\\LocalHostAuth=false\n"
            "WebUI\\HostHeaderValidation=true\nWebUI\\CSRFProtection=true\nGeneral\\Locale=pt_BR\n", "utf-8")
        log.append("qBittorrent configurado: WebUI só local (127.0.0.1:8790)")


def install_cores(log: list[str]) -> None:
    emulators.RA_CORES.mkdir(parents=True, exist_ok=True)
    for core in emulators.RA_CORE_FILES:
        dst = emulators.RA_CORES / core
        if dst.exists():
            continue
        z = dst.with_suffix(".zip")
        download(emulators.RA_CORE_URL.format(core=core), z)
        with zipfile.ZipFile(z) as f:
            f.extract(core, emulators.RA_CORES)
        z.unlink()
        log.append(f"core RetroArch instalado: {core}")


def install_flatpaks(log: list[str]) -> None:
    """Instala (modo usuário, Flathub oficial) os emuladores Flatpak que faltarem."""
    have = subprocess.run(["flatpak", "list", "--app", "--columns=application"], capture_output=True, text=True).stdout.split()
    missing = [a for a in emulators.FLATPAK_IDS if a not in have]
    if not missing:
        return
    subprocess.run(["flatpak", "remote-add", "--user", "--if-not-exists", "flathub",
                    "https://dl.flathub.org/repo/flathub.flatpakrepo"], capture_output=True)
    r = subprocess.run(["flatpak", "install", "--user", "-y", "--noninteractive", "flathub", *missing],
                       capture_output=True, text=True)
    log.append(f"emuladores instalados (Flathub): {', '.join(missing)}" if r.returncode == 0
               else f"AVISO: falha ao instalar {missing}: {r.stderr.strip()[-200:]}")


def flatpak_overrides(log: list[str]) -> None:
    for app in emulators.FLATPAK_IDS:
        for fs in (str(H / "Emulation"), "/run/media/deck"):
            subprocess.run(["flatpak", "override", "--user", f"--filesystem={fs}", app], capture_output=True)
    log.append("Flatpaks dos emuladores com acesso a ~/Emulation e ao cartão SD")


def write_units(log: list[str]) -> None:
    UNITS.mkdir(parents=True, exist_ok=True)
    for name, body in UNIT_FILES.items():
        p = UNITS / name
        if not p.exists() or p.read_text() != body:
            p.write_text(body, "utf-8"); log.append(f"unidade {name}")
    _sc("daemon-reload")


PLUGIN_SRC = REPO / "decky-plugin"
PLUGIN_ZIP = H / "Downloads/deck-commander-plugin.zip"


def find_installed_plugin() -> Path | None:
    for pj in (H / "homebrew/plugins").glob("*/plugin.json"):
        try:
            if json.loads(pj.read_text("utf-8")).get("name") == "Deck Commander":
                return pj.parent
        except (OSError, ValueError):
            pass
    return None


def setup_plugin(log: list[str]) -> None:
    """Gera o .zip para instalar pelo Decky e, se já instalado, atualiza os arquivos no lugar."""
    PLUGIN_ZIP.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(PLUGIN_ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(PLUGIN_SRC.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts:
                z.write(f, Path("deck-commander") / f.relative_to(PLUGIN_SRC))
    inst = find_installed_plugin()
    if inst is None:
        log.append(f"PLUGIN: instale pelo Decky -> Configurações -> Desenvolvedor -> Instalar plugin de ZIP -> {PLUGIN_ZIP}")
        return
    changed = []
    for rel in ("dist/index.js", "main.py", "package.json"):
        src, dst = PLUGIN_SRC / rel, inst / rel
        if not dst.exists() or dst.read_bytes() != src.read_bytes():
            try:
                shutil.copyfile(src, dst); changed.append(rel)
            except PermissionError:
                log.append(f"PLUGIN: sem permissão para atualizar {dst} — reinstale pelo ZIP {PLUGIN_ZIP}")
                return
    log.append("plugin já instalado" + (f"; atualizado ({', '.join(changed)}) — vale no próximo reinício" if changed else ", em dia"))


def write_plugins_lock(paths: Paths, log: list[str]) -> None:
    from .health import installed_plugins
    lock = paths.config / "plugins.lock"
    if not lock.exists():
        lock.write_text(json.dumps(installed_plugins(), indent=1, ensure_ascii=False), "utf-8")
        log.append(f"plugins.lock gerado com as versões atuais ({lock})")


def write_emulators_json(paths: Paths, log: list[str]) -> None:
    """Grava os emuladores encontrados; mantém o que o usuário já configurou e ainda existe."""
    p = paths.config / "emulators.json"
    cur = json.loads(p.read_text("utf-8")) if p.exists() else {}
    found = emulators.detect()
    for console, cmd in found.items():
        if console not in cur or not Path(cur[console][0]).exists():
            cur[console] = cmd
            log.append(f"emulador de {console}: {cmd[0] if cmd[0] != emulators.FLATPAK else cmd[2]}")
    for console in emulators.SEARCH:
        if console not in cur:
            log.append(f"AVISO: emulador de {console} não encontrado (jogos desse console não abrem)")
    p.write_text(json.dumps(cur, indent=1, ensure_ascii=False), "utf-8")


def write_backup_toml(paths: Paths) -> None:
    p = paths.config / "backup.toml"
    if not p.exists():
        shutil.copy(REPO / "config/backup.example.toml", p)


def setup(paths: Paths, modules: list[str], dev: bool = False, downloads: bool = True) -> list[str]:
    log: list[str] = []
    paths.ensure()
    cs = contracts.load(REPO / "modules")
    probs = contracts.validate_contracts(cs)
    if probs:
        raise RuntimeError("contratos inválidos: " + "; ".join(probs))
    wanted = set(modules)
    for m in list(wanted):  # dependências obrigatórias entram junto
        frontier = [m]
        while frontier:
            x = frontier.pop()
            for d in cs.get(x, {}).get("depends_on", []):
                if d not in wanted:
                    wanted.add(d); frontier.append(d); log.append(f"{m} depende de {d}: incluído")
    write_units(log)
    write_backup_toml(paths)
    if "M2" in wanted or "M3" in wanted:
        write_emulators_json(paths, log)
    if "M1" in wanted:
        write_plugins_lock(paths, log)
    if "M3" in wanted:
        if downloads:
            install_flatpaks(log)
            install_cores(log)
        elif not all((emulators.RA_CORES / c).exists() for c in emulators.RA_CORE_FILES):
            log.append("PENDENTE: cores do RetroArch (rode ./setup-deck.sh --all para baixar)")
        flatpak_overrides(log)
        for l in emulators.configure(apply=True):
            log.append("config " + l)
    if "M2" in wanted:
        setup_plugin(log)
    if "M4" in wanted:
        if downloads:
            install_qbittorrent(log)
        elif not QBT_BIN.exists():
            log.append("PENDENTE: qbittorrent-nox (rode ./setup-deck.sh --all para baixar)")
    if dev:
        venv = H / ".local/share/deck-commander/venv"
        if not venv.exists():
            subprocess.run([PY, "-m", "venv", str(venv)], check=True)
        subprocess.run([str(venv / "bin/pip"), "install", "-q", "pytest"], check=True)
        log.append("--dev: venv com pytest")
    for m in sorted(wanted):
        for u in MODULE_UNITS.get(m, []):
            if u == "deck-commander-bot.service" and not (paths.secrets / "telegram").exists():
                _sc("enable", u); log.append(f"{u}: habilitado, inicia quando houver token (dc secret telegram)")
                continue
            if u == "deck-commander-qbittorrent.service" and not QBT_BIN.exists():
                _sc("enable", u); log.append(f"{u}: habilitado, inicia quando o qbittorrent-nox existir"); continue
            out = _sc("enable", "--now", u)
            log.append(f"ligado {u}" + (f" ({out})" if "Failed" in out else ""))
    (paths.state / "installed-modules.json").write_text(json.dumps(sorted(wanted)), "utf-8")
    (paths.state / "VERSION").write_text((REPO / "VERSION").read_text().strip(), "utf-8")
    return log


def uninstall_module(paths: Paths, module: str, purge: bool = False) -> list[str]:
    cs = contracts.load(REPO / "modules")
    deps = contracts.dependents(cs, module)
    inst = set(json.loads((paths.state / "installed-modules.json").read_text())) if (paths.state / "installed-modules.json").exists() else set()
    active = [d for d in deps if d in inst]
    log = [f"AVISO: {', '.join(active)} dependem de {module}"] if active else []
    for u in MODULE_UNITS.get(module, []):
        _sc("disable", "--now", u); log.append(f"desligado {u} (dados preservados)")
    if module == "M4" and purge:
        for f in ("bot.log", "sync-state.json"):
            (paths.logs / f).unlink(missing_ok=True)
        (paths.config / "telegram.json").unlink(missing_ok=True)
        log.append("histórico do bot apagado (--purge)")
    inst.discard(module)
    (paths.state / "installed-modules.json").write_text(json.dumps(sorted(inst)), "utf-8")
    return log
