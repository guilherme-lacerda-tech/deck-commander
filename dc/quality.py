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

from .adapters.ini import IniDoc
from .arquivo_json import gravar as _save
from .arquivo_json import ler as _load
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
    "n3ds": ("ini", [H / ".var/app/org.azahar_emu.Azahar/config/azahar-emu/qt-config.ini"], "Renderer", "resolution_factor"),
    "switch": ("json", [H / ".config/Ryujinx/Config.json",
                        H / ".var/app/io.github.ryubing.Ryujinx/config/Ryujinx/Config.json"], None, "res_scale"),
}
MAX = {"switch": 4, "psp": 5, "psx": 5}
# Monitor/TV ligado (dock): resolução mínima para a imagem ficar nítida numa tela grande (~1080p). Só SOBE;
# se o jogo já está acima disso, fica como está. Switch não entra: o Ryujinx já roda em modo dock (1080p).
# Desligar: criar ~/.config/deck-commander/dock-desligado.
DOCK_RES = {"psx": 4, "psp": 3, "n3ds": 3, "gc": 2, "wii": 2, "ps2": 2}


def supported(console: str) -> bool:
    return console in TARGETS


def _overrides_path(paths: Paths) -> Path:
    return paths.config / "per-game.json"


def _restore_path(paths: Paths) -> Path:
    return paths.state / "quality-restore.json"



def get_override(paths: Paths, game_id: str) -> int | None:
    return _load(_overrides_path(paths), {}).get(game_id, {}).get("res")


def set_override(paths: Paths, game_id: str, console: str, level: str | None) -> str:
    """level: nativo/2x/3x/4x ou None/'padrão' para voltar ao valor do console."""
    if not supported(console):
        return "Esse console não tem ajuste de resolução por jogo (roda sempre na resolução original)."
    ov = _load(_overrides_path(paths), {})
    if level in (None, "padrao", "padrão", "default"):
        e = ov.get(game_id, {})
        e.pop("res", None)  # o idioma por jogo (se houver) continua
        if not e:
            ov.pop(game_id, None)
        _save(_overrides_path(paths), ov)
        return "voltou ao padrão do console"
    n = LEVELS.get(level.lower())
    if n is None:
        raise ValueError("use: nativo, 2x, 3x, 4x ou padrão")
    if n > MAX.get(console, 4):
        raise ValueError(f"máximo para esse console: {MAX.get(console, 4)}x")
    ov.setdefault(game_id, {})["res"] = n
    _save(_overrides_path(paths), ov)
    return f"{LABEL[n]} só para este jogo (vale a partir do próximo lançamento)"


def _target(console: str) -> tuple | None:
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


def _write(fmt: str, f: Path, sec, key, value: str | None) -> None:
    if fmt == "ini":
        doc = IniDoc.load(f)
        if value is None:
            doc.delete(sec, key)
        else:
            doc.ensure_section(sec, key, value)
        data = doc.dump()
    else:
        import re
        raw = f.read_text("utf-8")
        numeric = value is not None and re.fullmatch(r"-?\d+", value) is not None
        if numeric:
            rx = re.compile(r'("' + re.escape(key) + r'"\s*:\s*)(-?\d+(?:\.\d+)?)')
            new = str(int(value))
        else:
            rx = re.compile(r'("' + re.escape(key) + r'"\s*:\s*)("(?:[^"\\]|\\.)*")')
            new = json.dumps(value)
        if value is not None and len(rx.findall(raw)) == 1:
            # troca só o valor: o resto do arquivo fica byte a byte igual
            data = rx.sub(lambda m: m.group(1) + new, raw).encode("utf-8")
        else:
            cfg = json.loads(raw)
            if value is None:
                cfg.pop(key, None)
            else:
                cfg[key] = int(value) if numeric else value
            data = (json.dumps(cfg, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    tmp = f.with_name(f.name + ".dc-tmp")
    tmp.write_bytes(data)
    os.replace(tmp, f)


LANG_TARGET = {"switch": ("json", TARGETS["switch"][1], None, "system_language")}


def get_language(paths: Paths, game_id: str) -> str | None:
    return _load(_overrides_path(paths), {}).get(game_id, {}).get("idioma")


def set_language(paths: Paths, game_id: str, lang: str | None, why: str = "") -> None:
    """Idioma do console só para este jogo (ex.: BrazilianPortuguese para quem tem PT-BR oficial)."""
    ov = _load(_overrides_path(paths), {})
    e = ov.setdefault(game_id, {})
    if lang:
        e["idioma"] = lang
        if why:
            e["idioma_motivo"] = why
    else:
        e.pop("idioma", None); e.pop("idioma_motivo", None)
    if not e:
        ov.pop(game_id, None)
    _save(_overrides_path(paths), ov)


def dock_ligado(paths: Paths, dock: bool) -> bool:
    return dock and not (paths.config / "dock-desligado").exists()


def _plan(paths: Paths, game_id: str, console: str, dock: bool = False) -> list[tuple]:
    out = []
    n = get_override(paths, game_id)
    if dock_ligado(paths, dock) and console in DOCK_RES:
        n = min(max(n or 0, DOCK_RES[console]), MAX.get(console, 4))
    from . import perfil  # Beleza / Desempenho / Retrô (painel): a palavra final é do perfil escolhido
    n = perfil.nivel(paths, console, n, MAX.get(console, 4))
    if n and supported(console):
        t = _target(console)
        if t:
            out.append((*t, str(n)))
    lang = get_language(paths, game_id)
    if lang and console in LANG_TARGET:
        fmt, files, sec, key = LANG_TARGET[console]
        f = next((x for x in files if x.exists()), None)
        if f:
            out.append((fmt, f, sec, key, lang))
    return out


def _num(v) -> float | None:
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def apply_for_launch(paths: Paths, game_id: str, console: str, dock: bool = False) -> dict | None:
    """Aplica os ajustes do jogo (resolução, idioma). Devolve o registro de devolução (já em disco) ou None.
    dock=True (monitor/TV ligado): a resolução sobe até DOCK_RES, nunca desce."""
    recs = []
    own = get_override(paths, game_id)
    for fmt, f, sec, key, new in _plan(paths, game_id, console, dock):
        old = _read(fmt, f, sec, key)
        if old is not None and old.strip() in (new, f"{new}.0", f"{new}.000000"):
            continue
        if (dock_ligado(paths, dock) and key == TARGETS.get(console, (0, 0, 0, None))[3] and not own
                and _num(old) is not None and _num(old) >= float(new)):
            continue  # o padrão do console já é igual ou maior que o da dock
        recs.append({"game_id": game_id, "fmt": fmt, "file": str(f), "section": sec, "key": key, "old": old, "new": new})
    if not recs:
        return None
    _save(_restore_path(paths), recs)  # primeiro registra, depois muda
    for r in recs:
        _write(r["fmt"], Path(r["file"]), r["section"], r["key"], r["new"])
    return {"key": ", ".join(r["key"] for r in recs), "old": ", ".join(str(r["old"]) for r in recs),
            "new": ", ".join(r["new"] for r in recs), "records": recs}


def restore(paths: Paths) -> str | None:
    """Devolve os valores originais se houver devolução pendente. Seguro de chamar a qualquer momento
    em que nenhum jogo esteja aberto."""
    rp = _restore_path(paths)
    data = _load(rp, None)
    if not data:
        return None
    recs = data if isinstance(data, list) else [data]
    msgs = []
    for rec in reversed(recs):  # na ordem inversa (vários ajustes no mesmo arquivo)
        f = Path(rec["file"])
        if not f.exists():
            continue
        cur = _read(rec["fmt"], f, rec["section"], rec["key"])
        if cur is not None and cur.strip() == rec["new"]:
            _write(rec["fmt"], f, rec["section"], rec["key"], rec["old"])
            msgs.append(f"{rec['key']} devolvido para {rec['old']}")
        else:
            msgs.append(f"{rec['key']} mudou durante o jogo ({cur}); mantido como você deixou")
    rp.unlink(missing_ok=True)
    return "; ".join(msgs) or None


def listing(paths: Paths, launch_map: dict) -> list[str]:
    ov = _load(_overrides_path(paths), {})
    return [f"{launch_map.get(g, {}).get('title', g)}: {LABEL.get(v.get('res'), v.get('res'))}"
            for g, v in ov.items() if v.get("res")]
