"""M2 — Biblioteca via launcher fixo + mapa (decisão do usuário em 2026-11-06, no lugar do SRM).

Cada jogo vira UM atalho não-Steam cujo executável é sempre `dc-launch` e cujo nome nunca muda.
Como o AppID = crc32(exe + nome) | 0x80000000, ele fica estável para sempre; trocar ROM, formato
(.cue -> .m3u), emulador ou caminho muda só o mapa (launch-map.json), sem reiniciar o Steam e sem
perder coleções, arte ou Proton (correções F1/F2).

Regras v5.1 respeitadas: atalho manual/Unifideck nunca é tocado; nada é removido; dry-run por
padrão; `provenance` registra o que o DC criou; backup antes de gravar.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from . import vdf

LAUNCHER_NAME = "dc-launch"

from .emulators import CONSOLES  # fonte única dos consoles (M2.2)

DEFAULT_EMULATORS = {k: v["cmd"] for k, v in CONSOLES.items()}

_TITLE_ID = re.compile(r"\[([0-9A-Fa-f]{16})\]")
_NOISE = [re.compile(p, re.I) for p in (
    r"\(www\.[^)]*\)", r"\[[^\]]*\]", r"\(T\s?\d+(\.\d+)*\)", r"\(\d+(\.\d+)?\s*GB\)", r"\(v\d+(\.\d+)*\)", r"\((god|games on demand)\)")]


def clean_title(stem: str) -> str:
    t = stem
    for rx in _NOISE:
        t = rx.sub("", t)
    return re.sub(r"\s{2,}", " ", t).strip(" -_")


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def switch_kind(name: str) -> str:
    """base / update / dlc / unknown pelo Title ID entre colchetes."""
    m = _TITLE_ID.search(name)
    if not m:
        return "unknown"
    tid = m.group(1).upper()
    if tid.endswith("800"):
        return "update"
    if tid.endswith("000"):
        return "base"
    return "dlc"


@dataclass
class Game:
    game_id: str
    title: str
    console: str
    path: str
    skipped: list[str] = field(default_factory=list)


def scan(roots: Iterable[Path]) -> tuple[list[Game], list[str]]:
    """Encontra jogos jogáveis. Retorna (jogos, avisos). Só lê o disco."""
    games: dict[str, Game] = {}
    notes: list[str] = []
    for root in roots:
        root = Path(root)
        for console, spec in CONSOLES.items():
            d = root / console
            if not d.is_dir():
                continue
            if spec.get("dump"):  # Switch 2: <jogo>/base/exefs/main
                for main in sorted(d.rglob("main")):
                    if main.parent.name == "exefs" and main.parent.parent.name == "base":
                        title = clean_title(main.parent.parent.parent.name)
                        games.setdefault(f"{console}-{slug(title)}", Game(f"{console}-{slug(title)}", title, console, str(main)))
                continue
            if spec.get("eboot"):  # PS3 em pasta: <jogo>/PS3_GAME/USRDIR/EBOOT.BIN
                for eb in sorted(d.rglob("EBOOT.BIN")):
                    if eb.parent.name == "USRDIR" and eb.parent.parent.name == "PS3_GAME":
                        title = clean_title(eb.parent.parent.parent.name)
                        games.setdefault(f"{console}-{slug(title)}", Game(f"{console}-{slug(title)}", title, console, str(eb)))
            if spec.get("god"):  # Xbox 360 "Games on Demand": <TitleID>/00007000/<cabeçalho sem extensão>
                for hd in sorted(d.rglob("*")):
                    if hd.is_file() and not hd.suffix and hd.parent.name == "00007000":
                        title = clean_title(hd.parent.parent.parent.name)
                        games.setdefault(f"{console}-{slug(title)}", Game(f"{console}-{slug(title)}", title, console, str(hd)))
            files = sorted(f for f in d.rglob("*") if f.is_file() and f.suffix.lower() in spec["exts"])
            in_m3u = set()  # discos listados num .m3u (multidisco) não viram jogos separados
            for m in (f for f in files if f.suffix.lower() == ".m3u"):
                try:
                    in_m3u |= {(m.parent / ln.strip()).resolve() for ln in m.read_text("utf-8", "replace").splitlines()
                               if ln.strip() and not ln.startswith("#")}
                except OSError:
                    pass
            for f in files:
                if in_m3u and f.resolve() in in_m3u:
                    continue
                if console == "switch":
                    kind = switch_kind(f.name)
                    if kind != "base":
                        continue  # update/DLC entram pelo autoload do Ryujinx
                if console == "psx" and f.suffix.lower() == ".cue" and \
                        any((f.with_suffix(e)).exists() for e in (".m3u", ".chd")):
                    continue
                title = clean_title(f.stem)
                gid = f"{console}-{slug(title)}"
                if gid in games:
                    prev = games[gid]
                    rank = spec["exts"].index
                    if rank(f.suffix.lower()) < rank(Path(prev.path).suffix.lower()):
                        notes.append(f"{title}: usando {f.name} em vez de {Path(prev.path).name}")
                        games[gid] = Game(gid, title, console, str(f))
                    else:
                        notes.append(f"{title}: ignorado formato duplicado {f.name}")
                    continue
                games[gid] = Game(gid, title, console, str(f))
    return sorted(games.values(), key=lambda g: (g.console, g.title.lower())), notes


def launcher_path(home: Path) -> Path:
    return Path(home) / ".local/share/deck-commander/bin" / LAUNCHER_NAME


def shortcut_for(game: Game, launcher: Path) -> dict:
    exe = f'"{launcher}"'
    appid = vdf.shortcut_appid(exe, game.title)
    signed = appid - (1 << 32) if appid >= (1 << 31) else appid
    return {  # mesma ordem de chaves dos atalhos existentes no Deck
        "appid": signed, "AppName": game.title, "exe": exe, "StartDir": f'"{launcher.parent}/"',
        "icon": "", "ShortcutPath": "", "LaunchOptions": game.game_id, "IsHidden": 0,
        "AllowDesktopConfig": 1, "AllowOverlay": 1, "OpenVR": 0, "Devkit": 0, "DevkitGameID": "",
        "DevkitOverrideAppID": 0, "LastPlayTime": 0, "FlatpakAppID": "", "sortas": "",
        "tags": {"0": CONSOLES[game.console]["label"], "1": "Deck Commander"},
    }


@dataclass
class Plan:
    add: list[dict]
    already: list[str]
    name_conflicts: list[str]


def plan(existing: list[dict], games: list[Game], launcher: Path) -> Plan:
    ids = {(r.get("appid") or 0) & 0xFFFFFFFF for r in existing}
    names = {(r.get("AppName") or r.get("appname") or "").casefold(): r for r in existing}
    # atalhos criados pelo plugin têm AppID aleatório do Steam: reconhecidos pelo game_id nas opções
    dc_ids = {r.get("LaunchOptions") for r in existing if "dc-launch" in (r.get("exe") or r.get("Exe") or "")}
    add, already, conflicts = [], [], []
    for g in games:
        sc = shortcut_for(g, launcher)
        if sc["appid"] & 0xFFFFFFFF in ids or g.game_id in dc_ids:
            already.append(g.title)
        elif g.title.casefold() in names:
            other = names[g.title.casefold()]
            if "unifideck" in (other.get("exe") or other.get("Exe") or "").lower():
                # jogo de loja (Epic/GOG) com o mesmo nome: entra com o console no nome, sem tocar no outro
                from dataclasses import replace
                alt = shortcut_for(replace(g, title=f"{g.title} ({CONSOLES[g.console]['label']})"), launcher)
                if alt["appid"] & 0xFFFFFFFF not in ids and alt["AppName"].casefold() not in names:
                    add.append(alt)
                    continue
            conflicts.append(g.title)  # atalho manual com o mesmo nome: não duplica, não toca (avisado no /sync)
        else:
            add.append(sc)
    return Plan(add, already, conflicts)


def write_shortcuts(path: Path, new_rows: list[dict]) -> int:
    """Acrescenta atalhos sem alterar nenhum existente. Recusa se o arquivo não fizer round-trip
    byte-a-byte (formato que não entendemos => não gravamos)."""
    path = Path(path)
    raw = path.read_bytes()
    root = vdf.load_binary(raw)
    if vdf.dump_binary(root) != raw:
        raise RuntimeError("shortcuts.vdf não faz round-trip exato — gravação recusada")
    sc = root.setdefault("shortcuts", {})
    nxt = max((int(k) for k in sc if k.isdigit()), default=-1) + 1
    for i, row in enumerate(new_rows):
        sc[str(nxt + i)] = row
    tmp = path.with_name(path.name + ".dc-tmp")
    tmp.write_bytes(vdf.dump_binary(root))
    check = vdf.load_binary(tmp.read_bytes())["shortcuts"]
    if len(check) != len(sc):
        tmp.unlink()
        raise RuntimeError("verificação pós-escrita falhou")
    os.replace(tmp, path)
    return len(new_rows)


def write_map(map_path: Path, games: list[Game]) -> None:
    map_path = Path(map_path)
    data = {}
    if map_path.exists():
        data = json.loads(map_path.read_text("utf-8"))
    for g in games:
        keep = {k: v for k, v in data.get(g.game_id, {}).items() if k == "removed"}  # removido pelo usuário fica removido
        data[g.game_id] = {"title": g.title, "console": g.console, "rom": g.path, **keep}
    map_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = map_path.with_name(map_path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), "utf-8")
    os.replace(tmp, map_path)


def build_command(game_id: str, launch_map: dict, emulators: dict) -> list[str]:
    entry = launch_map.get(game_id)
    if entry is None:
        raise KeyError(f"jogo '{game_id}' não está no mapa")
    tmpl = emulators.get(entry["console"])
    if not tmpl:
        from .emulators import detect
        tmpl = detect().get(entry["console"]) or DEFAULT_EMULATORS[entry["console"]]
    return [entry["rom"] if a == "{rom}" else a for a in tmpl]


def write_launcher(home: Path, repo: Path) -> Path:
    """Script estável chamado pelos atalhos. Não muda nunca (o AppID depende do caminho dele)."""
    lp = launcher_path(home)
    lp.parent.mkdir(parents=True, exist_ok=True)
    lp.write_text(
        "#!/usr/bin/env python3\n"
        "# Gerado pelo Deck Commander. NÃO renomear/mover: o AppID dos atalhos depende deste caminho.\n"
        "import sys\n"
        f"sys.path.insert(0, {str(repo)!r})\n"
        "from dc.launch import main\n"
        "main(sys.argv[1:])\n", "utf-8")
    os.chmod(lp, 0o755)
    return lp
