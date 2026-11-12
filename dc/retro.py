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


def _registro_path(home: Path) -> Path:
    """Jogos em que o Deck Commander já pôs os botões de trás (uma vez só: depois o layout é do usuário)."""
    return home / ".local/share/deck-commander/retro-steam-input.json"


def registro(home: Path) -> dict:
    try:
        d = json.loads(_registro_path(home).read_text("utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _salvar_registro(home: Path, reg: dict) -> None:
    p = _registro_path(home)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(_json(reg), "utf-8")
    tmp.replace(p)


def _base_controle(home: Path, conta: str) -> Path:
    return home / ".local/share/Steam/steamapps/common/Steam Controller Configs" / conta / "config"


def steam_input(home: Path, jogos: list[str], forcar: bool = False) -> list[str]:
    """Põe os botões de trás no layout de cada jogo (nome do atalho, como o Steam guarda: minúsculas).
    Cada jogo é mexido UMA vez (registro): se depois o usuário trocar o layout, isso é respeitado. `forcar` só
    quando o próprio usuário pede (botão Ligar do painel / `/retro`)."""
    feitos = []
    reg = registro(home)
    for conta in _contas(home):
        base = _base_controle(home, conta)
        cs = base / "configset_controller_neptune.vdf"
        texto_cs = cs.read_text("utf-8") if cs.exists() else ""
        novo_cs = texto_cs
        for jogo in jogos:
            nome = jogo.lower()
            chave = f"{conta}/{nome}"
            if chave in reg and not forcar:
                continue
            arq = base / nome / "controller_neptune.vdf"
            existia = arq.exists()
            atual = arq.read_text("utf-8", "replace") if existia else _modelo(home)
            if not R.tem_botoes_de_tras(atual):
                _gravar(arq, R.layout_com_botoes_de_tras(atual))
                feitos.append(jogo)
            elif not existia:
                _gravar(arq, atual)
            novo_cs = _configset_com(novo_cs, nome)
            reg.setdefault(chave, {"criado": not existia})
        if novo_cs != texto_cs:
            _gravar(cs, novo_cs)
    _salvar_registro(home, reg)
    return feitos


def _desfazer_steam_input(home: Path) -> int:
    """Volta os layouts que o Deck Commander mexeu (cópia .antes-dc ou apaga o que ele criou) e tira o modelo."""
    reg = registro(home)
    n = 0
    for chave, info in reg.items():
        conta, _, nome = chave.partition("/")
        arq = _base_controle(home, conta) / nome / "controller_neptune.vdf"
        antes = arq.with_name(arq.name + ".antes-dc")
        if antes.exists():
            antes.replace(arq)
            n += 1
        elif (info or {}).get("criado") and arq.exists():
            arq.unlink()
            n += 1
    for conta in _contas(home):
        cs = _base_controle(home, conta) / "configset_controller_neptune.vdf"
        antes = cs.with_name(cs.name + ".antes-dc")
        if antes.exists():
            antes.replace(cs)
    (home / ".local/share/Steam/controller_base/templates" / MODELO).unlink(missing_ok=True)
    _registro_path(home).unlink(missing_ok=True)
    return n


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
    steam_input(home, [n for n, _ in jogos], forcar=True)  # o usuário pediu: vale para todos
    modelo = gravar_modelo(home) if (home / ".local/share/Steam/controller_base/templates").exists() else None
    texto = (f"🕹️ Botões de trás em {len(jogos)} jogo(s)"
             + (f"; emuladores ajustados: {', '.join(emus)}" if emus else "; emuladores já estavam prontos")
             + ". L4 salva · R4 carrega · L5 (segurar) volta no tempo · R5 liga/desliga o turbo.")
    return {"texto": texto, "appids": [a for _, a in jogos if a], "modelo": modelo}


def aplicar(home: Path | None = None, mapa: dict | None = None, turbo: float = 2.0) -> str:
    r = preparar(home, mapa, turbo)
    return r["texto"] + " Para valer já, abra o painel do Deck → Retrô → Ligar (ou reinicie o Steam)."


def desfazer(home: Path | None = None) -> str:
    """Volta os emuladores e os layouts do Steam para como estavam antes do Deck Commander."""
    home = home or Path.home()
    voltou = []
    for nome, rel in ARQUIVOS.items():
        p = home / rel
        orig = p.with_name(p.name + ".antes-dc")
        if orig.exists():
            shutil.copy2(orig, p)
            voltou.append(nome)
    n = _desfazer_steam_input(home)
    return ("Voltei a configuração de: " + (", ".join(voltou) or "nada (não havia cópia)")
            + (f"; layouts de controle devolvidos em {n} jogo(s)" if n else ""))


# --------------------------------------------------------------------------- configs feitas por versões antigas
def _retroarch_aberto() -> bool:
    import subprocess
    try:
        return subprocess.run(["pgrep", "-f", "retroarch"], capture_output=True).returncode == 0
    except OSError:
        return False


def corrigir_retroarch_antigo(home: Path) -> bool:
    """Quem ligou o Retrô antes da 0.8.1 ficou com a porta de comandos aberta e o "hardcore" marcado. Com o RetroArch
    aberto não mexe: ele regrava o arquivo ao fechar e desfaria a troca (tenta de novo na próxima volta do painel)."""
    ra = home / ARQUIVOS["RetroArch"]
    if not ra.exists() or _retroarch_aberto():
        return False
    return _gravar(ra, R.seguranca_retroarch(ra.read_text("utf-8", "replace")))


def jogos_para_o_painel(home: Path | None = None, mapa: dict | None = None) -> dict:
    """Depois de ligado uma vez, todo jogo retro que entrar depois (ex.: a copia PT-BR de uma traducao) tambem
    ganha os botoes de tras. Falha real 11/11/2026: a copia PT-BR do Castlevania virou atalho novo e ficou sem
    L4/R4/L5/R5. O painel chama isto de tempos em tempos e escolhe o modelo nos appids que ainda nao tinham."""
    home = home or Path.home()
    if not estado(home)["aplicado"] or not (home / ".local/share/Steam/controller_base/templates" / MODELO).exists():
        return {"appids": [], "modelo": None}
    if mapa is None:
        from . import transferir
        mapa = transferir.carregar_mapa()
    # Só jogo que ainda não passou por aqui. Antes: TODO reinício do Decky reaplicava o modelo em todos e apagava o
    # layout que o usuário tivesse escolhido (revisão de lançamento 12/11/2026).
    corrigir_retroarch_antigo(home)
    reg = registro(home)
    contas = _contas(home)
    novos = [(n, a) for n, a in jogos_dos_emuladores(home, mapa)
             if any(f"{c}/{n.lower()}" not in reg for c in contas)]
    if novos:
        steam_input(home, [n for n, _ in novos])  # layout salvo (vale quando o Steam reiniciar)
    return {"appids": [a for _, a in novos if a], "modelo": "template://" + MODELO}


def estado(home: Path | None = None) -> dict:
    home = home or Path.home()
    ra = home / ARQUIVOS["RetroArch"]
    txt = ra.read_text("utf-8", "replace") if ra.exists() else ""
    return {"aplicado": 'input_save_state = "f9"' in txt, "filtros": 'video_shader_enable = "true"' in txt,
            "turbo": next((float(l.split('"')[1]) for l in txt.splitlines() if l.startswith("fastforward_ratio")), 0.0),
            "emuladores": [n for n, r in ARQUIVOS.items() if (home / r).exists() or (n == "Dolphin" and (home / r).parent.exists())]}


def _json(x) -> str:
    return json.dumps(x, ensure_ascii=False)
