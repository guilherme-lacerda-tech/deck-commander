"""Jogos de OUTROS programas (EmuDeck, RetroDECK) não entram sozinhos na biblioteca.

Falha real 15/11/2026 (Deck do irmão do usuário, que já tinha o EmuDeck): o EmuDeck usa a mesma pasta
`Emulation/roms/<console>` que o Deck Commander, e a biblioteca transformou os ~400 jogos de Wii dele em atalhos na
Steam sem perguntar.

Regra:
- Sem outro gerenciador no Deck: tudo que estiver em `Emulation/roms` entra (como antes — quem joga a ROM na pasta
  quer o jogo na biblioteca).
- Com EmuDeck/RetroDECK: entram só os jogos que o Deck Commander trouxe (download pelo bot, varredura de jogos
  soltos, cópia "(PT-BR)") e os consoles que você liberar (`importar <console>`).
- Atualização num Deck que já tinha importado tudo: os jogos que não vieram do Deck Commander saem da biblioteca da
  Steam UMA vez (só o atalho; os arquivos ficam onde estão) e o aviso diz como trazer cada console de volta.

    python3 -m dc.biblioteca                     -> resumo: jogos de outros programas por console
    python3 -m dc.biblioteca importar wii        -> põe os jogos de Wii dos outros programas na biblioteca
    python3 -m dc.biblioteca tirar wii           -> tira os atalhos desses jogos (arquivos ficam)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

MARCAS = {  # pastas que indicam outro gerenciador de emuladores
    "EmuDeck": ["emudeck", ".config/EmuDeck", "Emulation/tools/launchers/pcsx2.sh"],
    "RetroDECK": ["retrodeck", ".var/app/net.retrodeck.retrodeck"],
}


def outro_gerenciador(home: Path | None = None) -> str | None:
    home = home or Path.home()
    for nome, marcas in MARCAS.items():
        if any((home / m).exists() for m in marcas):
            return nome
    return None


def _cfg_path(paths) -> Path:
    return paths.config / "biblioteca.json"


def carregar(paths) -> dict:
    try:
        return json.loads(_cfg_path(paths).read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def salvar(paths, cfg: dict) -> None:
    _cfg_path(paths).parent.mkdir(parents=True, exist_ok=True)
    _cfg_path(paths).write_text(json.dumps(cfg, indent=1, ensure_ascii=False), "utf-8")


def origem_dc(paths, store=None) -> set[str]:
    """Arquivos e pastas que o Deck Commander trouxe: download (/sync), varredura de jogos soltos."""
    out: set[str] = set()
    try:
        st = json.loads((paths.state / "sync-state.json").read_text("utf-8"))
        for e in st.get("ingested", {}).values():
            out.update(e.get("files") or [])
    except (OSError, ValueError):
        pass
    try:
        reg = json.loads((paths.state / "varredura-ultima.json").read_text("utf-8"))
        out.update(f["pasta"] for f in reg.get("feitos", []) if f.get("pasta"))
    except (OSError, ValueError):
        pass
    if store is not None:
        try:
            with store.tx() as c:
                out.update(r[0] for r in c.execute("SELECT path FROM files WHERE origin != 'unknown'"))
        except Exception:  # noqa: BLE001, S110 — banco ainda não criado: só as outras fontes contam
            pass
    return out


def do_deck_commander(caminho: str, origem: set[str]) -> bool:
    if "(PT-BR)" in Path(caminho).name or caminho in origem:
        return True
    alvo = Path(caminho)
    return any(alvo.is_relative_to(Path(p)) for p in origem if not Path(p).suffix)


def permitidos(paths, games: list, store=None, home: Path | None = None) -> tuple[list, list]:
    """(jogos que entram na biblioteca, jogos de outros programas que ficam de fora)."""
    if not outro_gerenciador(home):
        return list(games), []
    cfg = carregar(paths)
    liberados = {c for c, v in cfg.get("importar", {}).items() if v}
    origem = origem_dc(paths, store)
    dentro, fora = [], []
    for g in games:
        (dentro if g.console in liberados or do_deck_commander(g.path, origem) else fora).append(g)
    return dentro, fora


def migrar(paths, store=None, home: Path | None = None) -> str | None:
    """Uma vez, num Deck com outro gerenciador: tira da Steam os jogos importados que não vieram do Deck Commander."""
    cfg = carregar(paths)
    nome = outro_gerenciador(home)
    if cfg.get("migrado") or not nome:
        return None
    from . import remove
    try:
        lm = json.loads((paths.data / "launch-map.json").read_text("utf-8"))
    except (OSError, ValueError):
        lm = {}
    origem = origem_dc(paths, store)
    tirados: dict[str, int] = {}
    for gid, e in lm.items():
        if e.get("removed") or e.get("console") in ("pc", "steam") or not e.get("rom"):
            continue
        if not do_deck_commander(e["rom"], origem):
            remove.hide(paths, gid, f"jogo do {nome} (não importado pelo Deck Commander)")
            tirados[e["console"]] = tirados.get(e["console"], 0) + 1
    cfg["migrado"] = True
    cfg.setdefault("importar", {})
    salvar(paths, cfg)
    if not tirados:
        return None
    from .emulators import CONSOLES
    lista = ", ".join(f"{CONSOLES.get(c, {}).get('label', c)} ({n})" for c, n in sorted(tirados.items()))
    return (f"🧹 Tirei da biblioteca da Steam {sum(tirados.values())} jogo(s) que são do {nome}, não do Deck "
            f"Commander: {lista}. Os arquivos continuam onde estavam e o {nome} segue funcionando. Para trazer um "
            "console de volta: python3 -m dc.biblioteca importar <console> (ex.: wii).")


def importar(paths, console: str, ligar: bool = True, store=None) -> str:
    from . import remove
    cfg = carregar(paths)
    cfg.setdefault("importar", {})[console] = ligar
    salvar(paths, cfg)
    lm = json.loads((paths.data / "launch-map.json").read_text("utf-8")) if (paths.data / "launch-map.json").exists() else {}
    origem = origem_dc(paths, store)
    n = 0
    for gid, e in lm.items():
        if e.get("console") != console or do_deck_commander(e.get("rom", ""), origem):
            continue
        if ligar and e.get("removed"):
            remove.bring_back(paths, gid); n += 1
        elif not ligar and not e.get("removed"):
            remove.hide(paths, gid, "jogo de outro programa (tirado pelo usuário)"); n += 1
    if ligar:
        return f"Ok: os jogos de {console} dos outros programas entram na biblioteca (rode /sync). {n} voltaram."
    return f"Ok: {n} jogo(s) de {console} de outros programas saíram da biblioteca (os arquivos ficam)."


def resumo(paths, store=None) -> dict:
    from . import library, syncer
    games, _ = library.scan(syncer.rom_roots())
    _dentro, fora = permitidos(paths, games, store)
    por: dict[str, int] = {}
    for g in fora:
        por[g.console] = por.get(g.console, 0) + 1
    return {"outro_gerenciador": outro_gerenciador(), "fora_por_console": por,
            "importar": carregar(paths).get("importar", {})}


def main(argv: list[str]) -> int:
    from .paths import get_paths
    from .store import Store
    paths = get_paths().ensure()
    store = Store(paths.db)
    if argv[:1] in (["importar"], ["tirar"]) and len(argv) == 2:
        print(importar(paths, argv[1], argv[0] == "importar", store))
    elif not argv:
        print(json.dumps(resumo(paths, store), ensure_ascii=False, indent=1))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
