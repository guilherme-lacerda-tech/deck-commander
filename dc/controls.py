"""Controles: verificação por emulador + layout de botões do Switch.

Como funciona no Deck: no modo jogo o Steam Input entrega aos emuladores um controle padrão
(layout Xbox: A embaixo, B direita, X esquerda, Y em cima). Cada emulador mapeia esse controle
uma vez, de forma GLOBAL (vale para todos os jogos daquele console):
- DuckStation / PCSX2: mapeamento automático por índice (SDL-0) — independe do nome do controle;
- RetroArch / PPSSPP: autoconfiguração própria;
- Dolphin (GameCube/Wii): precisa de um dispositivo escolhido no GCPadNew.ini/WiimoteNew.ini;
- Ryujinx (Switch): por padrão usa POSIÇÃO (o "A" do Switch fica no botão da direita, que no Deck
  é o B). `switch_layout()` troca para RÓTULO: apertar A no Deck = A no jogo.
Ajuste por jogo (raro) é feito no próprio Steam: Controle → layout por jogo (fica salvo por atalho).
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

H = Path.home()
def _ryu(home: Path) -> list[Path]:
    return [home / ".config/Ryujinx/Config.json", home / ".var/app/io.github.ryubing.Ryujinx/config/Ryujinx/Config.json"]


RYU = _ryu(H)
LABELS = {"button_a": "A", "button_b": "B", "button_x": "X", "button_y": "Y"}
POSITIONAL = {"button_a": "B", "button_b": "A", "button_x": "Y", "button_y": "X"}


@dataclass
class Check:
    emulator: str
    ok: bool
    detail: str


# ---------------------------------------------------------------- layout dos botões, em palavras simples
# "xbox":   apertar A no Deck = A no jogo (o A fica EMBAIXO, como no controle de Xbox e no próprio Deck)
# "switch": botões na mesma POSIÇÃO do controle do Switch (o A fica na DIREITA: no Deck, é o botão B)
MODOS = {"xbox": "Controle de Xbox (A embaixo — apertar A no Deck = A no jogo)",
         "switch": "Controle de Switch (A na direita, igual ao Switch)"}
# Lichii (Switch 2, base yuzu/eden): botões SDL 0=embaixo, 1=direita, 2=esquerda, 3=em cima
_LICHII_BOTOES = {"xbox": {"a": 0, "b": 1, "x": 2, "y": 3}, "switch": {"a": 1, "b": 0, "x": 3, "y": 2}}
_LICHII_RX = re.compile(r'^(player_0_button_([abxy]))="(engine:sdl,[^"]*?button:)(\d+)(.*)"$', re.MULTILINE)


def _lichii(home: Path) -> list[Path]:
    return [home / ".config/eden/qt-config.ini", home / "Emulation/Lichii/user/config/qt-config.ini"]


def _ryu_modo(home: Path) -> str | None:
    p = next((x for x in _ryu(home) if x.exists()), None)
    if p is None:
        return None
    pads = [i for i in json.loads(p.read_text("utf-8")).get("input_config") or [] if "Gamepad" in str(i.get("backend", ""))]
    if not pads:
        return None
    return "xbox" if (pads[0].get("right_joycon") or {}).get("button_a") == "A" else "switch"


def _lichii_modo(home: Path) -> str | None:
    p = next((x for x in _lichii(home) if x.exists()), None)
    if p is None:
        return None
    botoes = {m.group(2): int(m.group(4)) for m in _LICHII_RX.finditer(p.read_text("utf-8", "replace"))}
    for modo, want in _LICHII_BOTOES.items():
        if botoes and all(botoes.get(k) == v for k, v in want.items()):
            return modo
    return None


def lichii_layout(mode: str, home: Path = H) -> list[str]:
    """Lichii: troca só os 4 botões de face do Jogador 1 (mantém o controle escolhido)."""
    want = _LICHII_BOTOES[mode]
    log = []
    for p in (x for x in _lichii(home) if x.exists()):
        txt = p.read_text("utf-8", "replace")
        novo = _LICHII_RX.sub(lambda m: f'{m.group(1)}="{m.group(3)}{want[m.group(2)]}{m.group(5)}"', txt)
        if novo != txt:
            bak = p.with_name(p.name + ".antes-deck-commander")
            if not bak.exists():
                bak.write_text(txt, "utf-8")
            tmp = p.with_name(p.name + ".dc-tmp")
            tmp.write_text(novo, "utf-8")
            os.replace(tmp, p)
            log.append(f"{p}: botões do Switch 2 como {MODOS[mode].split(' (')[0]}")
    return log


def layouts(home: Path = H) -> list[dict]:
    """Emuladores em que dá para escolher o layout dos botões: [{id, emulador, atual, opcoes}]."""
    out = []
    for ident, nome, modo in (("ryujinx", "Nintendo Switch (Ryujinx)", _ryu_modo(home)),
                              ("lichii", "Nintendo Switch 2 (Lichii)", _lichii_modo(home))):
        if modo is not None:
            out.append({"id": ident, "emulador": nome, "atual": modo, "opcoes": MODOS})
    return out


def definir_layout(ident: str, modo: str, home: Path = H) -> list[str]:
    if modo not in MODOS:
        raise ValueError("modo inválido")
    if ident == "ryujinx":
        return switch_layout("labels" if modo == "xbox" else "positional", home)
    if ident == "lichii":
        return lichii_layout(modo, home)
    raise ValueError("emulador sem escolha de layout")


def _ini_has(path: Path, section_rx: str, value_rx: str) -> bool | None:
    if not path.exists():
        return None
    cur, sec, val = None, re.compile(section_rx), re.compile(value_rx)
    for ln in path.read_text("utf-8", "replace").splitlines():
        m = re.match(r"\s*\[(.+?)\]", ln)
        if m:
            cur = m.group(1)
        elif cur and sec.fullmatch(cur) and val.search(ln):
            return True
    return False


def check(home: Path = H) -> list[Check]:
    out = []
    for name, paths, sec, rx in (
        ("DuckStation (PS1)", [home / ".local/share/duckstation/settings.ini",
                               home / ".var/app/org.duckstation.DuckStation/config/duckstation/settings.ini"], r"Pad1", r"=\s*SDL-\d"),
        ("PCSX2 (PS2)", [home / ".var/app/net.pcsx2.PCSX2/config/PCSX2/inis/PCSX2.ini"], r"Pad1", r"=\s*SDL-\d"),
        ("Dolphin GameCube", [home / ".var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu/GCPadNew.ini"],
         r"GCPad1", r"Device\s*=\s*(SDL|evdev)/"),
        ("Dolphin Wii", [home / ".var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu/WiimoteNew.ini"],
         r"Wiimote1", r"Device\s*=\s*(SDL|evdev)/"),
    ):
        p = next((x for x in paths if x.exists()), None)
        if p is None:
            out.append(Check(name, True, "ainda não aberto (o emulador cria o padrão na 1ª vez)"))
            continue
        has = _ini_has(p, sec, rx)
        out.append(Check(name, bool(has), "controle mapeado" if has else
                         "sem controle mapeado — abra o emulador no modo desktop e configure o Controle 1 uma vez"))
    ryu = next((p for p in _ryu(home) if p.exists()), None)
    if ryu is None:
        out.append(Check("Ryujinx (Switch)", True, "ainda não aberto"))
    else:
        cfg = json.loads(ryu.read_text("utf-8"))
        pads = [i for i in cfg.get("input_config") or [] if "Gamepad" in str(i.get("backend", ""))]
        if not pads:
            out.append(Check("Ryujinx (Switch)", False, "sem controle mapeado"))
        else:
            rj = pads[0].get("right_joycon") or {}
            lay = "rótulo (A=A)" if rj.get("button_a") == "A" else "posição (A do Switch = B do Deck)"
            out.append(Check("Ryujinx (Switch)", True, f"controle mapeado, layout por {lay}"))
    for name, d in (("RetroArch", home / ".var/app/org.libretro.RetroArch"), ("PPSSPP", home / ".var/app/org.ppsspp.PPSSPP")):
        if d.exists():
            out.append(Check(name, True, "autoconfiguração do emulador"))
    if (home / ".var/app/net.kuribo64.melonDS").exists():
        t = melonds_path(home)
        ok = t.exists() and "[Instance0.Joystick]" in t.read_text("utf-8", "replace")
        out.append(Check("melonDS (DS)", ok, "controle mapeado (A=A)" if ok else "sem controle mapeado"))
    for name, app, auto in (("xemu (Xbox)", "app.xemu.xemu", True), ("Flycast (Dreamcast)", "org.flycast.Flycast", True)):
        if (home / ".var/app" / app).exists():
            out.append(Check(name, True, "reconhece o controle sozinho"))
    # Estes gravam o controle pelo identificador do aparelho: precisa ser feito UMA vez com o controle ligado
    once = {"Azahar (3DS)": ("org.azahar_emu.Azahar", "config/azahar-emu/qt-config.ini", "engine:sdl"),
            "Cemu (Wii U)": ("info.cemu.Cemu", "config/Cemu/controllerProfiles/controller0.xml", "SDLController"),
            "RPCS3 (PS3)": ("net.rpcs3.RPCS3", "config/rpcs3/input_configs/global/Default.yml", "Handler: SDL")}
    for name, (app, rel, marker) in once.items():
        base = home / ".var/app" / app
        if not base.exists():
            continue
        f = base / rel
        ok = f.exists() and marker in f.read_text("utf-8", "replace")
        out.append(Check(name, ok, "controle configurado" if ok else
                         "configurar o controle UMA vez: modo desktop → abrir o emulador → Controles → escolher o controle"))
    return out


def switch_layout(mode: str = "labels", home: Path = H) -> list[str]:
    """Ryujinx: 'labels' (A=A, como no Deck) ou 'positional' (padrão do Ryujinx). Só mexe nos 4 botões
    de face dos controles (não toca no teclado nem em outras teclas)."""
    want = LABELS if mode == "labels" else POSITIONAL
    log = []
    for p in (x for x in _ryu(home) if x.exists()):
        cfg = json.loads(p.read_text("utf-8"))
        changed = False
        for pad in cfg.get("input_config") or []:
            if "Gamepad" not in str(pad.get("backend", "")):
                continue
            rj = pad.setdefault("right_joycon", {})
            for k, v in want.items():
                if rj.get(k) != v:
                    rj[k] = v
                    changed = True
        if changed:
            tmp = p.with_name(p.name + ".dc-tmp")
            tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", "utf-8")
            os.replace(tmp, p)
            log.append(f"{p}: botões do Switch por {'rótulo (A=A)' if mode == 'labels' else 'posição'}")
    return log


# Dolphin: nomes de entrada SDL conferidos no binário do Dolphin 2609 (Button S/E/W/N, Pad N…, Left X+…,
# Trigger L+…). No modo jogo o Steam Input entrega o "Steam Virtual Gamepad" (nome visto pelo SDL,
# confirmado no Ryujinx do Deck de teste).
DOLPHIN_DEVICE = "SDL/0/Steam Virtual Gamepad"
_GC = {
    "Buttons/A": "`Button S`", "Buttons/B": "`Button W`", "Buttons/X": "`Button E`", "Buttons/Y": "`Button N`",
    "Buttons/Z": "`Shoulder R`", "Buttons/Start": "Start",
    "Main Stick/Up": "`Left Y-`", "Main Stick/Down": "`Left Y+`", "Main Stick/Left": "`Left X-`", "Main Stick/Right": "`Left X+`",
    "C-Stick/Up": "`Right Y-`", "C-Stick/Down": "`Right Y+`", "C-Stick/Left": "`Right X-`", "C-Stick/Right": "`Right X+`",
    "Triggers/L": "`Trigger L+`", "Triggers/R": "`Trigger R+`", "Triggers/L-Analog": "`Trigger L+`", "Triggers/R-Analog": "`Trigger R+`",
    "D-Pad/Up": "`Pad N`", "D-Pad/Down": "`Pad S`", "D-Pad/Left": "`Pad W`", "D-Pad/Right": "`Pad E`",
}
_WII = {  # Wii Remote + Nunchuk (o formato da maioria dos jogos); apontar = analógico direito
    "Buttons/A": "`Button S`", "Buttons/B": "`Trigger R+`", "Buttons/1": "`Button W`", "Buttons/2": "`Button N`",
    "Buttons/-": "Back", "Buttons/+": "Start", "Buttons/Home": "`Thumb R`",
    "D-Pad/Up": "`Pad N`", "D-Pad/Down": "`Pad S`", "D-Pad/Left": "`Pad W`", "D-Pad/Right": "`Pad E`",
    "IR/Up": "`Right Y-`", "IR/Down": "`Right Y+`", "IR/Left": "`Right X-`", "IR/Right": "`Right X+`",
    "Shake/X": "`Button E`", "Shake/Y": "`Button E`", "Shake/Z": "`Button E`",
    "Extension": "Nunchuk",
    "Nunchuk/Buttons/C": "`Shoulder L`", "Nunchuk/Buttons/Z": "`Trigger L+`",
    "Nunchuk/Stick/Up": "`Left Y-`", "Nunchuk/Stick/Down": "`Left Y+`",
    "Nunchuk/Stick/Left": "`Left X-`", "Nunchuk/Stick/Right": "`Left X+`",
    "Source": "1",
}


def _dolphin_dir(home: Path) -> Path:
    return home / ".var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu"


def dolphin_defaults(home: Path = H) -> list[str]:
    """Mapeia o controle do Deck no Dolphin (GameCube porta 1 e Wii Remote 1) SÓ se ainda estiver no
    padrão de fábrica (teclado/mouse). Mapeamento feito por você nunca é tocado. Guarda .dc-orig."""
    log = []
    d = _dolphin_dir(home)
    if not d.exists():
        return log
    for fname, section, keys in (("GCPadNew.ini", "GCPad1", _GC), ("WiimoteNew.ini", "Wiimote1", _WII)):
        p = d / fname
        text = p.read_text("utf-8", "replace") if p.exists() else ""
        if _ini_has(p, section, r"Device\s*=\s*(SDL|evdev)/"):
            continue  # já tem controle: respeita
        # remove só a seção do jogador 1 e reescreve; as outras seções ficam como estavam
        out, skip = [], False
        for ln in text.splitlines():
            m = re.match(r"\s*\[(.+?)\]", ln)
            if m:
                skip = m.group(1) == section
            if not skip:
                out.append(ln)
        block = [f"[{section}]", f"Device = {DOLPHIN_DEVICE}"] + [f"{k} = {v}" for k, v in keys.items()]
        if p.exists():
            orig = p.with_name(p.name + ".dc-orig")
            if not orig.exists():
                orig.write_bytes(p.read_bytes())
        tmp = p.with_name(p.name + ".dc-tmp")
        tmp.write_text("\n".join(block + out) + "\n", "utf-8")
        os.replace(tmp, p)
        log.append(f"{fname}: controle do Deck mapeado no jogador 1 (original em {fname}.dc-orig)")
    return log


def _trocar(p: Path, novo: str, velho: str) -> None:
    if novo == velho:
        return
    orig = p.with_name(p.name + ".dc-orig")
    if not orig.exists():
        orig.write_text(velho, "utf-8")
    tmp = p.with_name(p.name + ".dc-tmp")
    tmp.write_text(novo, "utf-8")
    os.replace(tmp, p)


def _secao_com(text: str, section: str, linha: str) -> str:
    """Põe `linha` (chave = valor) dentro de [section], trocando a chave se já existir."""
    chave = linha.split("=")[0].strip()
    out, dentro, feito = [], False, False
    for ln in text.splitlines():
        m = re.match(r"\s*\[(.+?)\]", ln)
        if m:
            if dentro and not feito:
                out.append(linha); feito = True
            dentro = m.group(1) == section
        elif dentro and ln.split("=")[0].strip() == chave:
            if not feito:
                out.append(linha); feito = True
            continue
        out.append(ln)
    if dentro and not feito:
        out.append(linha)
    return "\n".join(out) + "\n"


def vibracao(home: Path = H) -> list[str]:
    """Liga a vibração do controle nos emuladores que vinham com ela desligada (pedido 13/11/2026: "nunca senti o Deck
    vibrar"). Medido no Deck: Ryujinx com "enable_rumble": false; Dolphin sem o motor ligado ao controle. DuckStation e
    PCSX2 já vinham com os motores (SDL-0/LargeMotor). O resto do mapeamento não é tocado; o original fica em .dc-orig."""
    log = []
    for p in (x for x in _ryu(home) if x.exists()):  # Switch
        velho = p.read_text("utf-8")
        cfg = json.loads(velho)
        mudou = False
        for pad in cfg.get("input_config") or []:
            if "Gamepad" in str(pad.get("backend", "")):
                r = pad.setdefault("rumble", {"strong_rumble": 1.0, "weak_rumble": 1.0})
                if r.get("enable_rumble") is not True:
                    r["enable_rumble"] = True; mudou = True
        if mudou:
            _trocar(p, json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", velho)
            log.append("Ryujinx (Switch): vibração ligada")
    d = _dolphin_dir(home)  # GameCube e Wii: o motor só vibra se estiver ligado ao controle
    for fname, section in (("GCPadNew.ini", "GCPad1"), ("WiimoteNew.ini", "Wiimote1")):
        p = d / fname
        if not _ini_has(p, section, r"Device\s*=\s*SDL/") or _ini_has(p, section, r"^\s*Rumble/Motor\s*="):
            continue  # sem controle SDL (ainda) ou o motor já tem dono: respeita
        velho = p.read_text("utf-8", "replace")
        _trocar(p, _secao_com(velho, section, "Rumble/Motor = Motor"), velho)
        log.append(f"Dolphin ({'GameCube' if section == 'GCPad1' else 'Wii'}): vibração ligada")
    for p in (x for x in _lichii(home) if x.exists()):  # Switch 2 (base yuzu/eden)
        velho = p.read_text("utf-8", "replace")
        novo = re.sub(r'^((?:player_0_)?vibration_enabled)=false$', r"\1=true", velho, flags=re.MULTILINE)
        novo = re.sub(r'^((?:player_0_)?vibration_enabled)\\default=false$', r"\1\\default=true", novo, flags=re.MULTILINE)
        if novo != velho:
            _trocar(p, novo, velho)
            log.append("Lichii (Switch 2): vibração ligada")
    return log


# melonDS (Nintendo DS): valores conferidos no código do melonDS (EmuInstance::joystickButtonDown):
# botão = número; direcional = 0x100 | (chapéu << 4) | direção (1 cima, 2 direita, 4 baixo, 8 esquerda);
# analógico = 0x10000 | (eixo << 24) | (sentido << 20) (0 positivo, 1 negativo). Um valor pode ter os dois.
# O Steam Input entrega o controle no padrão Xbox: A=0 B=1 X=2 Y=3 LB=4 RB=5 Back=6 Start=7; direcional = chapéu 0.
MELONDS_JOY = {
    "A": 0, "B": 1, "X": 2, "Y": 3, "L": 4, "R": 5, "Select": 6, "Start": 7,  # por rótulo (A=A), como no Switch
    "Up": 0x101 | 0x10000 | (1 << 24) | (1 << 20), "Down": 0x104 | 0x10000 | (1 << 24),
    "Left": 0x108 | 0x10000 | (1 << 20), "Right": 0x102 | 0x10000,
}


def melonds_path(home: Path = H) -> Path:
    return home / ".var/app/net.kuribo64.melonDS/config/melonDS/melonDS.toml"


def melonds_defaults(home: Path = H) -> list[str]:
    """Mapeia o controle do Deck no melonDS se ele ainda não tiver mapeamento de controle (não mexe no resto)."""
    if not (home / ".var/app/net.kuribo64.melonDS").exists():
        return []
    p = melonds_path(home)
    text = p.read_text("utf-8", "replace") if p.exists() else ""
    if "[Instance0.Joystick]" in text:
        return []
    block = ["", "[Instance0.Joystick]"] + [f"{k} = {v}" for k, v in MELONDS_JOY.items()]
    if "JoystickID" not in text:
        block = (["", "[Instance0]", "JoystickID = 0"] if "[Instance0]" not in text else []) + block
    if p.exists():
        orig = p.with_name(p.name + ".dc-orig")
        if not orig.exists():
            orig.write_bytes(p.read_bytes())
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".dc-tmp")
    tmp.write_text(text.rstrip("\n") + "\n".join(block) + "\n", "utf-8")
    os.replace(tmp, p)
    return [f"{p.name}: controle do Deck mapeado no melonDS (A=A, direcional e analógico)"]
