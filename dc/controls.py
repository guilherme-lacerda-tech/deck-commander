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
