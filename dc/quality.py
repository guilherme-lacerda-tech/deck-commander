"""Qualidade POR JOGO (resolução interna): nativo, 2x, 3x, 4x.

Cada emulador tem um valor global (perfil do console, M3). Para um jogo que precisa de outro valor
(pesado demais em 3x, ou com efeito que quebra fora do nativo), o `dc-launch` troca o valor só
enquanto aquele jogo está aberto e devolve o original ao fechar:

1. grava em state/quality-restore.json o que vai mudar (antes de mudar);
2. aplica e abre o emulador; 3. ao fechar, devolve o valor antigo — só se ninguém mexeu nele
   durante o jogo (ajuste manual no menu do emulador é respeitado).
Se o Steam matar o processo (botão "Sair do jogo"), a devolução acontece no próximo lançamento ou
pelo serviço de fundo, assim que nenhum jogo estiver aberto.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from .adapters.ini import IniDoc
from .paths import Paths

H = Path.home()
LEVELS = {"nativo": 1, "native": 1, "1x": 1, "2x": 2, "3x": 3, "4x": 4, "5x": 5}
LABEL = {1: "nativo", 2: "2x", 3: "3x", 4: "4x", 5: "5x"}

# console -> (formato, [arquivos candidatos], seção, chave). O primeiro arquivo que existir é usado.
TARGETS = {
    "psx": ("ini", [H / ".local/share/duckstation/settings.ini",
                    H / ".var/app/org.duckstation.DuckStation/config/duckstation/settings.ini"], "GPU", "ResolutionScale"),
    "ps2": ("ini", [H / ".var/app/net.pcsx2.PCSX2/config/PCSX2/inis/PCSX2.ini",
                    H / ".config/PCSX2/inis/PCSX2.ini"], "EmuCore/GS", "upscale_multiplier"),
    "gc": ("ini", [H / ".var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu/GFX.ini"], "Settings", "InternalResolution"),
    "wii": ("ini", [H / ".var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu/GFX.ini"], "Settings", "InternalResolution"),
    "psp": ("ini", [H / ".var/app/org.ppsspp.PPSSPP/config/ppsspp/PSP/SYSTEM/ppsspp.ini"], "Graphics", "InternalResolution"),
    "switch": ("json", [H / ".config/Ryujinx/Config.json",
                        H / ".var/app/io.github.ryubing.Ryujinx/config/Ryujinx/Config.json"], None, "res_scale"),
}
MAX = {"switch": 4, "psp": 5, "psx": 5}


def supported(console: str) -> bool:
    return console in TARGETS


def _overrides_path(paths: Paths) -> Path:
    return paths.config / "per-game.json"


def _restore_path(paths: Paths) -> Path:
    return paths.state / "quality-restore.json"


def _load(p: Path, default):
    try:
        return json.loads(p.read_text("utf-8"))
    except (OSError, ValueError):
        return default


def _save(p: Path, data) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    os.replace(tmp, p)


def get_override(paths: Paths, game_id: str) -> Optional[int]:
    return _load(_overrides_path(paths), {}).get(game_id, {}).get("res")


def set_override(paths: Paths, game_id: str, console: str, level: Optional[str]) -> str:
    """level: nativo/2x/3x/4x ou None/'padrão' para voltar ao valor do console."""
    if not supported(console):
        return "Esse console não tem ajuste de resolução por jogo (roda sempre na resolução original)."
    ov = _load(_overrides_path(paths), {})
    if level in (None, "padrao", "padrão", "default"):
        ov.pop(game_id, None)
        _save(_overrides_path(paths), ov)
        return "voltou ao padrão do console"
    n = LEVELS.get(level.lower())
    if n is None:
        raise ValueError("use: nativo, 2x, 3x, 4x ou padrão")
    if n > MAX.get(console, 4):
        raise ValueError(f"máximo para esse console: {MAX.get(console, 4)}x")
    ov[game_id] = {"res": n}
    _save(_overrides_path(paths), ov)
    return f"{LABEL[n]} só para este jogo (vale a partir do próximo lançamento)"


def _target(console: str) -> Optional[tuple]:
    fmt, files, sec, key = TARGETS[console]
    for f in files:
        if f.exists():
            return fmt, f, sec, key
    return None


def _read(fmt: str, f: Path, sec, key):
    if fmt == "ini":
        return IniDoc.load(f).get(sec, key)
    v = _load(f, {}).get(key)
    return None if v is None else str(v)


def _write(fmt: str, f: Path, sec, key, value: Optional[str]) -> None:
    if fmt == "ini":
        doc = IniDoc.load(f)
        if value is None:
            doc.delete(sec, key)
        else:
            doc.ensure_section(sec, key, value)
        data = doc.dump()
    else:
        cfg = _load(f, {})
        if value is None:
            cfg.pop(key, None)
        else:
            cfg[key] = int(value)
        data = (json.dumps(cfg, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    tmp = f.with_name(f.name + ".dc-tmp")
    tmp.write_bytes(data)
    os.replace(tmp, f)


def apply_for_launch(paths: Paths, game_id: str, console: str) -> Optional[dict]:
    """Aplica o valor do jogo. Devolve o registro de devolução (já gravado em disco) ou None."""
    n = get_override(paths, game_id)
    if not n or not supported(console):
        return None
    t = _target(console)
    if not t:
        return None
    fmt, f, sec, key = t
    old = _read(fmt, f, sec, key)
    new = str(n)
    if old is not None and old.strip() in (new, f"{n}.0", f"{n}.000000"):
        return None
    rec = {"game_id": game_id, "fmt": fmt, "file": str(f), "section": sec, "key": key, "old": old, "new": new}
    _save(_restore_path(paths), rec)  # primeiro registra, depois muda
    _write(fmt, f, sec, key, new)
    return rec


def restore(paths: Paths) -> Optional[str]:
    """Devolve o valor original se houver devolução pendente. Seguro de chamar a qualquer momento
    em que nenhum jogo esteja aberto."""
    rp = _restore_path(paths)
    rec = _load(rp, None)
    if not rec:
        return None
    f = Path(rec["file"])
    msg = None
    if f.exists():
        cur = _read(rec["fmt"], f, rec["section"], rec["key"])
        if cur is not None and cur.strip() == rec["new"]:
            _write(rec["fmt"], f, rec["section"], rec["key"], rec["old"])
            msg = f"{rec['key']} devolvido para {rec['old']}"
        else:
            msg = f"{rec['key']} mudou durante o jogo ({cur}); mantido como você deixou"
    rp.unlink(missing_ok=True)
    return msg


def listing(paths: Paths, launch_map: dict) -> list[str]:
    ov = _load(_overrides_path(paths), {})
    return [f"{launch_map.get(g, {}).get('title', g)}: {LABEL.get(v.get('res'), v.get('res'))}" for g, v in ov.items()]
