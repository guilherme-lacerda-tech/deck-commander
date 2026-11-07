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
