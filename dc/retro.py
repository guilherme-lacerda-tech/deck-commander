"""Aplica no disco a 0.8 "retrô" (dc.retro_hacks faz as contas; aqui só lê, guarda cópia e grava):

- emuladores: RetroArch (teclas, rewind, turbo, comandos pela rede local, cheats, exceções por núcleo + filtros),
  DuckStation, PCSX2 e Dolphin com as mesmas teclas reservadas (F9–F12);
- Steam Input: em cada atalho de jogo desses emuladores, os botões de trás viram essas teclas
  (L4 salvar, R4 carregar, L5 voltar no tempo, R5 turbo). O resto do layout do jogo não muda.
Antes da 1ª mudança de cada arquivo fica uma cópia "<arquivo>.antes-dc" (desfazer = /retro desfazer).
"""
from __future__ import annotations

import glob
import json
import shutil
import socket
from pathlib import Path

from . import retro_hacks as R
from . import vdf

RA = ".var/app/org.libretro.RetroArch/config/retroarch"
ARQUIVOS = {
    "RetroArch": RA + "/retroarch.cfg",
    "DuckStation": ".local/share/duckstation/settings.ini",
    "PCSX2": ".var/app/net.pcsx2.PCSX2/config/PCSX2/inis/PCSX2.ini",
    "Dolphin": ".var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu/Hotkeys.ini",
}
# console → emulador (o Deck Commander abre esses consoles nesses emuladores)
EMULADOR_DO_CONSOLE = {"psx": "DuckStation", "ps2": "PCSX2", "gc": "Dolphin", "wii": "Dolphin"}
for _c in ("nes", "snes", "n64", "gb", "gbc", "gba", "genesis", "sms", "gg", "segacd", "saturn", "pce", "arcade"):
    EMULADOR_DO_CONSOLE[_c] = "RetroArch"
CONFIG_DIR = "config"  # pasta "config/<núcleo>" do RetroArch (exceções por núcleo)


def _gravar(p: Path, novo: str) -> bool:
    """Grava só se mudou; guarda a cópia original uma vez."""
    velho = p.read_text("utf-8", "replace") if p.exists() else None
    if velho == novo:
        return False
    if velho is not None and not p.with_name(p.name + ".antes-dc").exists():
        shutil.copy2(p, p.with_name(p.name + ".antes-dc"))
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".dc-tmp")
    tmp.write_text(novo, "utf-8")
    tmp.replace(p)
    return True


def emuladores(home: Path, turbo: float = 2.0, filtros: bool = True) -> list[str]:
    """Configura os 4 emuladores (só os que existem no Deck). Devolve o que mudou."""
    feitos = []
    ra = home / ARQUIVOS["RetroArch"]
    if ra.exists():
        txt = R.cfg_retroarch(ra.read_text("utf-8", "replace"), turbo)
        cheats = home / RA / "cheats"
        cheats.mkdir(parents=True, exist_ok=True)
        txt = R.definir(txt, {"cheat_database_path": str(cheats), "video_shader_enable": "true" if filtros else "false",
                              "auto_shaders_enable": "true"})
        if _gravar(ra, txt):
            feitos.append("RetroArch")
        for nucleo, op in R.NUCLEOS.items():
            pasta = home / RA / CONFIG_DIR / nucleo
            cfg = pasta / f"{nucleo}.cfg"
            _gravar(cfg, R.override_nucleo(cfg.read_text("utf-8") if cfg.exists() else None,
                                           op["runahead"], op["rewind"], op["shader"]))
            if op["shader"]:
                _gravar(pasta / f"{nucleo}.slangp", R.preset_shader(op["shader"]))
    for nome, func in (("DuckStation", R.ini_duckstation), ("PCSX2", R.ini_pcsx2)):
        p = home / ARQUIVOS[nome]
        if p.exists() and _gravar(p, func(p.read_text("utf-8", "replace"), turbo)):
            feitos.append(nome)
    d = home / ARQUIVOS["Dolphin"]
    if d.parent.exists() and _gravar(d, R.hotkeys_dolphin(d.read_text("utf-8") if d.exists() else None)):
        feitos.append("Dolphin")
    return feitos


# ------------------------------------------------------------------------------------------- Steam Input
def _contas(home: Path) -> list[str]:
    return [Path(p).name for p in glob.glob(str(home / ".local/share/Steam/userdata/*")) if Path(p).name.isdigit()]


def _modelo(home: Path) -> str:
    return (home / ".local/share/Steam/controller_base/templates/controller_neptune_gamepad+mouse.vdf").read_text(
        "utf-8-sig")


def _configset_com(texto: str, nome: str) -> str:
    """configset_controller_neptune.vdf com o jogo usando o layout salvo dele ("autosave")."""
    d = vdf.load_text(texto) if texto.strip() else {"controller_config": {}}
    cc = d.setdefault("controller_config", {})
    if cc.get(nome) == {"autosave": "1"}:
        return texto
    cc[nome] = {"autosave": "1"}
    return vdf.dump_text(d)


def steam_input(home: Path, jogos: list[str]) -> list[str]:
    """Põe os botões de trás no layout de cada jogo (nome do atalho, como o Steam guarda: minúsculas)."""
    feitos = []
    for conta in _contas(home):
        base = home / ".local/share/Steam/steamapps/common/Steam Controller Configs" / conta / "config"
        cs = base / "configset_controller_neptune.vdf"
        texto_cs = cs.read_text("utf-8") if cs.exists() else ""
        novo_cs = texto_cs
        for jogo in jogos:
            nome = jogo.lower()
            arq = base / nome / "controller_neptune.vdf"
            atual = arq.read_text("utf-8", "replace") if arq.exists() else _modelo(home)
            if not R.tem_botoes_de_tras(atual):
                _gravar(arq, R.layout_com_botoes_de_tras(atual))
                feitos.append(jogo)
            elif not arq.exists():
                _gravar(arq, atual)
            novo_cs = _configset_com(novo_cs, nome)
        if novo_cs != texto_cs:
            _gravar(cs, novo_cs)
    return feitos


MODELO = "controller_neptune_dc_retro.vdf"


def gravar_modelo(home: Path) -> str:
    """Modelo de layout "Deck Commander Retrô" na pasta de modelos do Steam (ele enxerga na hora, sem reiniciar).
    Devolve o endereço que o Steam usa para escolher o modelo num jogo."""
    texto = R.layout_com_botoes_de_tras(_modelo(home)).replace(
        "Gamepad with Mouse Trackpad", "Deck Commander Retro (L4 salva, R4 carrega, L5 volta, R5 turbo)", 1)
    _gravar(home / ".local/share/Steam/controller_base/templates" / MODELO, texto)
    return "template://" + MODELO


def jogos_dos_emuladores(home: Path, mapa: dict) -> list[tuple[str, int]]:
    """(nome, appid) dos atalhos do Steam cujos jogos abrem nos emuladores configurados aqui."""
    jogos = set()
    for sc in glob.glob(str(home / ".local/share/Steam/userdata/*/config/shortcuts.vdf")):
        try:
            for s in vdf.read_shortcuts(Path(sc)):
                e = mapa.get(s.get("LaunchOptions", "")) or {}
                if e.get("console") in EMULADOR_DO_CONSOLE and s.get("AppName"):
                    jogos.add((s["AppName"], int(s.get("appid", 0)) & 0xFFFFFFFF))
        except (OSError, ValueError, KeyError):
            continue
    return sorted(jogos)


def preparar(home: Path | None = None, mapa: dict | None = None, turbo: float = 2.0) -> dict:
    """Ajusta os emuladores e deixa o modelo pronto. O painel (que roda dentro do Steam) escolhe o modelo em cada
    jogo de `appids` na hora; o layout salvo de cada jogo também ganha os botões (vale quando o Steam reiniciar)."""
    home = home or Path.home()
    if mapa is None:
        from . import transferir
        mapa = transferir.carregar_mapa()
    emus = emuladores(home, turbo)
    jogos = jogos_dos_emuladores(home, mapa)
    steam_input(home, [n for n, _ in jogos])
    modelo = gravar_modelo(home) if (home / ".local/share/Steam/controller_base/templates").exists() else None
    texto = (f"🕹️ Botões de trás em {len(jogos)} jogo(s)"
             + (f"; emuladores ajustados: {', '.join(emus)}" if emus else "; emuladores já estavam prontos")
             + ". L4 salva · R4 carrega · L5 (segurar) volta no tempo · R5 (segurar) turbo.")
    return {"texto": texto, "appids": [a for _, a in jogos if a], "modelo": modelo}


def aplicar(home: Path | None = None, mapa: dict | None = None, turbo: float = 2.0) -> str:
    r = preparar(home, mapa, turbo)
    return r["texto"] + " Para valer já, abra o painel do Deck → Retrô → Ligar (ou reinicie o Steam)."


def desfazer(home: Path | None = None) -> str:
    """Volta os arquivos dos emuladores para a cópia de antes (os layouts do Steam ficam: são só os botões de trás)."""
    home = home or Path.home()
    voltou = []
    for nome, rel in ARQUIVOS.items():
        p = home / rel
        orig = p.with_name(p.name + ".antes-dc")
        if orig.exists():
            shutil.copy2(orig, p)
            voltou.append(nome)
    return "Voltei a configuração de: " + (", ".join(voltou) or "nada (não havia cópia)")


# ------------------------------------------------------------------------------------------- RetroArch ao vivo
def comando_retroarch(cmd: str, porta: int = 55355) -> bool:
    """Manda um comando para o RetroArch aberto (ex.: "SHADER_TOGGLE", "SAVE_STATE"). Só na própria máquina."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.sendto(cmd.encode(), ("127.0.0.1", porta))
        return True
    except OSError:
        return False


def estado(home: Path | None = None) -> dict:
    home = home or Path.home()
    ra = home / ARQUIVOS["RetroArch"]
    txt = ra.read_text("utf-8", "replace") if ra.exists() else ""
    return {"aplicado": 'input_save_state = "f9"' in txt, "filtros": 'video_shader_enable = "true"' in txt,
            "turbo": next((float(l.split('"')[1]) for l in txt.splitlines() if l.startswith("fastforward_ratio")), 0.0),
            "emuladores": [n for n, r in ARQUIVOS.items() if (home / r).exists() or (n == "Dolphin" and (home / r).parent.exists())]}


def _json(x) -> str:
    return json.dumps(x, ensure_ascii=False)
