"""Varredura de jogos soltos: acha ROMs fora de Emulation/roms (Downloads, Área de Trabalho, cartão SD, pendrive…)
e leva cada uma para Emulation/roms/<console>/<jogo>/.

    python3 -m dc.varredura              só mostra o que achou (não mexe em nada)
    python3 -m dc.varredura --aplicar    move/copia para as pastas certas e grava um registro para desfazer
    python3 -m dc.varredura --desfazer   devolve os arquivos da última varredura para onde estavam

Regras de segurança (as mesmas do resto do projeto: nada é apagado):
- No mesmo disco o arquivo é MOVIDO (instantâneo, não ocupa espaço a mais). Do pendrive para o Deck é COPIADO e o
  original fica no pendrive. Jogos do cartão SD ficam no cartão (SD/Emulation/roms), não enchem o disco interno.
- Nunca sobrescreve: arquivo igual já na pasta do console = repetido (fica onde está); nome igual = pasta "(2)".
- .cue/.bin, .gdi, .m3u e .mds/.mdf andam juntos. Pasta de PS3 (PS3_GAME) anda inteira.
- .zip/.7z/.rar só entram se o nome do jogo dentro deixar claro o console; são extraídos e o compactado fica onde está.
- Console decidido por: extensão exclusiva > leitura do próprio disco (PS1/PS2/PSP/GameCube/Wii) > nome do arquivo
  ou da pasta ("PS2", "GBA"…). Sem certeza = não mexe (aparece na lista "não identificados").
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import content
from .emulators import CONSOLES
from .paths import get_paths

PULAR = {"emulation", "steamapps", "steam", "homebrew", "compatdata", "shadercache", "applications", "node_modules",
         "lost+found", "$recycle.bin", "system volume information", "windows", "program files", "program files (x86)",
         "appdata", "backups", "nsz-env", "src", "projects", "retrodeck", "heroic", "lutris", "drive_c", "pfx",
         "prefix", "bottles"}
PROFUNDIDADE = 6
MINIMO = 8 * 1024  # ROM menor que isso é lixo/cabeçalho
MULTI = {".cue", ".gdi", ".m3u", ".mds"}
SOLTOS_IGNORADOS = {".bin", ".img", ".mdf", ".iso", ".chd", ".cso", ".pbp", ".rvz", ".gcz", ".ciso", ".xiso",
                    ".zar", ".xex", ".rpx"}  # precisam de leitura/nome para decidir
PASTAS_CONSOLE = {**{c: c for c in CONSOLES if not CONSOLES[c].get("remoto")},
                  "ps1": "psx", "playstation": "psx", "ps2": "ps2", "gamecube": "gc", "ngc": "gc", "3ds": "n3ds",
                  "megadrive": "genesis", "mega drive": "genesis", "dreamcast": "dc", "xbox360": "x360", "xbox 360": "x360"}
REGISTRO = "varredura-ultima.json"
NUNCA = {".xex", ".zar", ".rpx", ".smd"}       # executável solto de jogo extraído / formato raro: não mexe
CABECALHO_SEGA = {".md", ".gen"}                # .md também é texto (README.md): só com "SEGA" no cabeçalho
DISCO = {".iso", ".chd", ".cso", ".rvz", ".gcz", ".ciso", ".wbfs", ".pbp", ".cue", ".gdi", ".m3u", ".xiso"}
INOFENSIVOS = {".txt", ".nfo", ".jpg", ".jpeg", ".png", ".sav", ".srm", ".url", ".diz", ".cue", ".m3u", ".bin"}


@dataclass
class Unidade:
    principal: Path                  # arquivo que dá nome ao jogo (ou a pasta, no caso do PS3)
    arquivos: list[Path] = field(default_factory=list)
    base: Path | None = None         # pasta de referência para manter caminhos relativos (m3u/cue em subpasta)
    console: str | None = None
    como: str = ""                   # como o console foi decidido
    compactado: bool = False


# ── onde procurar e para onde mandar ────────────────────────────────────────────────────────────────────────────
def _montagens() -> list[tuple[Path, str]]:
    out = []
    try:
        for linha in Path("/proc/mounts").read_text().splitlines():
            dev, ponto = linha.split()[:2]
            ponto = ponto.replace("\\040", " ")
            if ponto.startswith("/run/media/"):
                out.append((Path(ponto), dev))
    except OSError:
        pass
    return out


def raizes_de_busca(home: Path) -> list[Path]:
    return [home] + [p for p, _ in _montagens()]


def destino_para(arq: Path, home: Path) -> tuple[Path, bool]:
    """(Emulation/roms de destino, mover?). Mover só no mesmo disco; senão copia para o Deck."""
    roms_home = home / "Emulation/roms"
    try:
        dev = arq.stat().st_dev
    except OSError:
        return roms_home, False
    for ponto, disp in _montagens():
        try:
            if ponto.stat().st_dev != dev:
                continue
        except OSError:
            continue
        # o Deck Commander só enxerga /run/media/*/*/Emulation/roms (cartão SD do SteamOS 3.5+)
        if disp.startswith("/dev/mmcblk") and len(ponto.relative_to("/run/media").parts) == 2:
            return ponto / "Emulation/roms", True
        return roms_home, False  # pendrive/HD externo (ou SD em formato antigo): copia, original fica lá
    home_dev = home.stat().st_dev
    return roms_home, dev == home_dev


# ── identificação ───────────────────────────────────────────────────────────────────────────────────────────────
def _ler(arq: Path, pos: int, n: int) -> bytes:
    try:
        with open(arq, "rb") as f:
            f.seek(pos)
            return f.read(n)
    except OSError:
        return b""


def console_pelo_disco(arq: Path) -> str | None:
    ext = arq.suffix.lower()
    if ext in (".iso", ".bin", ".img"):
        c = content.console_do_disco(arq)
        if c:
            return c
    if ext in (".iso", ".gcz", ".ciso"):
        cab = _ler(arq, 0, 0x20)
        if cab[0x18:0x1C] == b"\x5d\x1c\x9e\xa3":
            return "wii"
        if cab[0x1C:0x20] == b"\xc2\x33\x9f\x3d":
            return "gc"
    if ext == ".rvz":  # o cabeçalho do disco vem copiado nos primeiros bytes do RVZ
        cab = _ler(arq, 0, 0x400)
        if b"\x5d\x1c\x9e\xa3" in cab:
            return "wii"
        if b"\xc2\x33\x9f\x3d" in cab:
            return "gc"
    if ext == ".iso":
        pvd = _ler(arq, 16 * 2048, 2048)
        if pvd[1:6] == b"CD001" and b"PSP GAME" in pvd[8:40]:
            return "psp"
    if ext == ".cso":
        return "psp" if _ler(arq, 0, 4) == b"CISO" else None
    return None


def _dica_de_nome(texto: str) -> str | None:
    for rx, c in content.NAME_HINTS:
        if rx.search(texto):
            return c
    return None


def _dica_de_pasta(arq: Path, raiz: Path) -> str | None:
    try:
        partes = arq.parent.relative_to(raiz).parts
    except ValueError:
        partes = arq.parent.parts[-3:]
    for p in reversed(partes):
        c = PASTAS_CONSOLE.get(p.lower()) or _dica_de_nome(p)
        if c:
            return c
    return None


def identificar(u: Unidade, raiz: Path) -> None:
    p = u.principal
    if u.console:  # já decidido pela estrutura
        return
    ext = p.suffix.lower()
    if ext in CABECALHO_SEGA:
        if b"SEGA" in _ler(p, 0x100, 0x10):
            u.console, u.como = "genesis", "cabeçalho SEGA"
        return
    if u.compactado:
        c = _console_do_compactado(p)
        if c:
            u.console, u.como = c, "conteúdo do compactado"
        return
    donos = [c for c, s in CONSOLES.items() if ext in s["exts"] and not s.get("remoto")]
    if len(donos) == 1 and ext not in content.AMBIGUOUS:
        u.console, u.como = donos[0], "extensão"
        return
    alvo = p
    if ext == ".cue":
        alvo = next((a for a in u.arquivos if a.suffix.lower() in (".bin", ".img", ".iso")), p)
    if ext == ".m3u":
        alvo = next((a for a in u.arquivos if a.suffix.lower() in (".bin", ".img", ".iso", ".chd")), p)
    c = console_pelo_disco(alvo)
    if c:
        u.console, u.como = c, "leitura do disco"
        return
    c = _dica_de_nome(p.name) or _dica_de_pasta(p, raiz)
    if c and (ext in CONSOLES[c]["exts"] or (ext in MULTI and c in ("psx", "segacd", "saturn", "pce", "dc"))):
        u.console, u.como = c, "nome do arquivo/pasta"
        return


def _console_do_compactado(p: Path) -> str | None:
    """Só aceita compactado "limpo": até 10 arquivos, todos de jogo de UM console (ou readme/capa/cue/bin).
    Zip de mod, de plugin ou de programa (com .dll, .esp, .py, README.md…) nunca passa."""
    nomes = [Path(n) for n in content._inner_names(p)]
    if not nomes or len(nomes) > 10:
        return None
    candidatos: set[str] = set()
    for n in nomes:
        ext = n.suffix.lower()
        if ext in INOFENSIVOS:
            continue
        donos = {c for c, s in CONSOLES.items() if ext in s["exts"] and not s.get("remoto") and c != "arcade"}
        if not donos or ext in NUNCA or ext in CABECALHO_SEGA or ext in content.ARCHIVES:
            return None  # tem arquivo que não é de jogo
        if len(donos) == 1 and ext not in content.AMBIGUOUS:
            candidatos |= donos
        else:  # .iso/.chd dentro: decide pelo nome do compactado ("God Hand (PS2).zip")
            dica = _dica_de_nome(p.name)
            if dica not in donos:
                return None
            candidatos.add(dica)
    return candidatos.pop() if len(candidatos) == 1 else None


def _ajustar_compactado(u: Unidade) -> None:
    """.zip de cartucho (GBA, SNES…) e de arcade o emulador abre direto: anda como está, sem extrair."""
    if u.compactado and u.console and u.principal.suffix.lower() in CONSOLES[u.console]["exts"]:
        u.compactado = False


# ── montagem das unidades (um jogo = um ou mais arquivos que andam juntos) ──────────────────────────────────────
def _referencias(arq: Path) -> list[Path]:
    """Arquivos citados por .cue/.gdi/.m3u/.mds (na mesma pasta ou em subpasta)."""
    try:
        texto = arq.read_text("utf-8", "replace")
    except OSError:
        return []
    ext = arq.suffix.lower()
    nomes: list[str] = []
    if ext == ".cue":
        nomes = re.findall(r'^\s*FILE\s+"?(.+?)"?\s+\w+\s*$', texto, re.IGNORECASE | re.MULTILINE)
    elif ext == ".gdi":
        for linha in texto.splitlines()[1:]:
            m = re.match(r'\s*\d+\s+\d+\s+\d+\s+\d+\s+"?(.+?)"?\s+\d+\s*$', linha)
            if m:
                nomes.append(m.group(1))
    elif ext == ".m3u":
        nomes = [l.strip() for l in texto.splitlines() if l.strip() and not l.startswith("#")]
    elif ext == ".mds":
        nomes = [arq.with_suffix(".mdf").name]
    out = []
    for n in nomes:
        f = (arq.parent / n.replace("\\", "/")).resolve()
        if f.is_file():
            out.append(f)
            if f.suffix.lower() == ".cue":  # m3u -> cue -> bin
                out += _referencias(f)
    return out


def _pular_pasta(nome: str) -> bool:
    n = nome.lower()
    return nome.startswith(".") or n in PULAR or n.startswith("deck-commander")


def _jogo_ps3(pasta: Path) -> bool:
    return (pasta / "PS3_GAME/USRDIR/EBOOT.BIN").is_file()


def encontrar(home: Path, raizes: list[Path] | None = None) -> tuple[list[Unidade], list[Path]]:
    """(jogos identificados, não identificados). Pastas de outros programas (EmuDeck, RetroDECK…) não são tocadas."""
    unidades: list[Unidade] = []
    sem_console: list[Path] = []
    vistos: set[Path] = set()
    raizes = raizes if raizes is not None else raizes_de_busca(home)
    # também olha arquivos soltos direto em Emulation/roms (fora de qualquer pasta de console)
    extras = []
    for r in [home / "Emulation/roms"] + [p / "Emulation/roms" for p in raizes[1:]]:
        if r.is_dir():
            extras += [c for c in r.iterdir() if c.is_file() and not c.name.startswith(".")]
    for raiz in raizes:
        for topo, pastas, arquivos in os.walk(raiz):
            t = Path(topo)
            nivel = len(t.relative_to(raiz).parts)
            if _jogo_ps3(t):
                unidades.append(Unidade(t, sorted(x for x in t.rglob("*") if x.is_file()), t, "ps3", "pasta PS3_GAME"))
                pastas[:] = []
                continue
            pastas[:] = [] if nivel >= PROFUNDIDADE else [p for p in pastas if not _pular_pasta(p)
                                                           and not (t == raiz and raiz != home and p.lower() == "emulation")]
            _da_pasta(t, arquivos, raiz, unidades, sem_console, vistos)
    for e in extras:
        _da_pasta(e.parent, [e.name], e.parent, unidades, sem_console, vistos)
    for u in unidades:
        _ajustar_compactado(u)
    return unidades, sem_console


def _da_pasta(t: Path, nomes: list[str], raiz: Path, unidades: list[Unidade], sem_console: list[Path],
              vistos: set[Path]) -> None:
    t = t.resolve()
    arqs = [t / n for n in sorted(nomes)]
    arqs = [a for a in arqs if a.is_file() and not a.is_symlink()]
    # 1º os que juntam vários arquivos
    for a in sorted(arqs, key=lambda x: x.suffix.lower() != ".m3u"):
        if a.suffix.lower() in MULTI and a.resolve() not in vistos:
            refs = _referencias(a)
            if a.suffix.lower() != ".mds" and not refs:
                continue
            grupo = list(dict.fromkeys([a.resolve()] + [r for r in refs if r not in vistos]))
            vistos.update(grupo)
            u = Unidade(a, grupo, t)
            identificar(u, raiz)
            (unidades.append(u) if u.console else sem_console.append(a))
    for a in arqs:
        r = a.resolve()
        if r in vistos:
            continue
        ext = a.suffix.lower()
        if ext not in content.GAME_EXTS or ext in MULTI or ext in NUNCA or "bios" in a.name.lower():
            continue
        try:
            if a.stat().st_size < MINIMO:
                continue
        except OSError:
            continue
        vistos.add(r)
        u = Unidade(a, [r], t, compactado=ext in content.ARCHIVES)
        identificar(u, raiz)
        if u.console:
            unidades.append(u)
        elif ext in DISCO or (ext in (".bin", ".img") and a.stat().st_size > 50 * 1024 * 1024):
            sem_console.append(a)  # compactado sem jogo claro (mod, programa…) nem entra na lista


# ── aplicar / desfazer ──────────────────────────────────────────────────────────────────────────────────────────
def _titulo(u: Unidade) -> str:
    t = u.principal.stem if u.principal.is_file() else u.principal.name
    if u.principal.suffix.lower() in (".m3u",):
        return t
    return content._DISC.sub("", t).strip(" _-.") or t


def _ja_existe(roms: Path, console: str, arq: Path) -> bool:
    pasta = roms / console
    if not pasta.is_dir():
        return False
    tam = arq.stat().st_size
    return any(x.is_file() and x.stat().st_size == tam for x in pasta.rglob(arq.name))


def _espaco_livre(p: Path) -> int:
    while not p.exists():
        p = p.parent
    return shutil.disk_usage(p).free


def aplicar(unidades: list[Unidade], home: Path, log=print) -> list[dict]:
    feitos: list[dict] = []
    paths = get_paths()
    for u in unidades:
        roms, mover = destino_para(u.principal, home)
        if all(_ja_existe(roms, u.console, a) for a in u.arquivos if a.is_file()) and not u.compactado:
            log(f"  = repetido (já está em {u.console}): {u.principal.name}")
            continue
        if u.compactado:
            trab = roms.parent / ".dc-varredura-tmp"
            trab.mkdir(parents=True, exist_ok=True)
            item = content.ingest(u.principal, u.console, roms, paths.quarantine, trab, confirm_many=True)
            shutil.rmtree(trab, ignore_errors=True)
            if item.status == "added":
                log(f"  ✔ {CONSOLES[u.console]['label']}: {u.principal.name} (extraído; o compactado ficou onde estava)")
                feitos.append({"tipo": "extraido", "de": str(u.principal), "para": [str(Path(f).parent) for f in item.files][:1]})
            else:
                log(f"  ! {u.principal.name}: {item.note or item.status}")
            continue
        tamanho = sum(a.stat().st_size for a in u.arquivos)
        if not mover and _espaco_livre(roms) < tamanho + 2 * 1024**3:
            log(f"  ! sem espaço para copiar {u.principal.name} ({tamanho // 1024**2} MB) — ficou onde está")
            continue
        destino, n = roms / u.console / _titulo(u), 2
        while destino.exists():
            destino = roms / u.console / f"{_titulo(u)} ({n})"; n += 1
        movidos = []
        try:
            for a in u.arquivos:
                rel = a.relative_to(u.base) if u.base and a.is_relative_to(u.base) else Path(a.name)
                alvo = destino / rel
                alvo.parent.mkdir(parents=True, exist_ok=True)
                if mover:
                    os.rename(a, alvo)
                else:
                    shutil.copy2(a, alvo)
                    if alvo.stat().st_size != a.stat().st_size:
                        raise OSError(f"cópia incompleta de {a.name}")
                movidos.append({"de": str(a), "para": str(alvo)})
        except OSError as e:
            log(f"  ✘ {u.principal.name}: {e} — desfazendo este jogo")
            for m in reversed(movidos):
                if mover:
                    os.rename(m["para"], m["de"])
                else:
                    Path(m["para"]).unlink(missing_ok=True)
            shutil.rmtree(destino, ignore_errors=True)
            continue
        verbo = "movido" if mover else "copiado (original ficou no pendrive/HD)"
        log(f"  ✔ {CONSOLES[u.console]['label']}: {_titulo(u)}  [{verbo}]")
        feitos.append({"tipo": "movido" if mover else "copiado", "arquivos": movidos, "pasta": str(destino)})
    reg = paths.state / REGISTRO
    reg.parent.mkdir(parents=True, exist_ok=True)
    reg.write_text(json.dumps({"quando": time.strftime("%Y-%m-%d %H:%M"), "feitos": feitos}, indent=1,
                              ensure_ascii=False), "utf-8")
    return feitos


def desfazer(log=print) -> int:
    reg = get_paths().state / REGISTRO
    if not reg.exists():
        log("Nenhuma varredura para desfazer."); return 0
    dados = json.loads(reg.read_text("utf-8"))
    n = 0
    for f in reversed(dados["feitos"]):
        if f["tipo"] == "movido":
            for m in reversed(f["arquivos"]):
                if Path(m["para"]).exists() and not Path(m["de"]).exists():
                    Path(m["de"]).parent.mkdir(parents=True, exist_ok=True)
                    os.rename(m["para"], m["de"]); n += 1
        elif f["tipo"] == "copiado":
            for m in f["arquivos"]:
                if Path(m["de"]).exists():
                    Path(m["para"]).unlink(missing_ok=True); n += 1
        else:
            continue  # extraído: o compactado original nunca saiu do lugar
        p = Path(f["pasta"])
        for d in sorted((x for x in p.rglob("*") if x.is_dir()), reverse=True) + [p]:
            try:
                d.rmdir()
            except OSError:
                pass
    reg.rename(reg.with_suffix(".desfeita.json"))
    log(f"Desfeito: {n} arquivos voltaram para onde estavam. (Rode 'python3 -m dc library --apply' para atualizar o Steam.)")
    return n


def resumo(unidades: list[Unidade], sem: list[Path], home: Path) -> str:
    por: dict[str, list[Unidade]] = {}
    for u in unidades:
        por.setdefault(u.console, []).append(u)
    linhas = []
    for c in sorted(por, key=lambda c: CONSOLES[c]["label"]):
        gb = sum(a.stat().st_size for u in por[c] for a in u.arquivos) / 1024**3
        linhas.append(f"  {CONSOLES[c]['label']:<20} {len(por[c]):>4} jogo(s)  {gb:6.1f} GB")
        for u in por[c][:8]:
            onde = str(u.principal.parent).replace(str(home), "~")
            linhas.append(f"      · {u.principal.name}   ({onde})")
        if len(por[c]) > 8:
            linhas.append(f"      · … e mais {len(por[c]) - 8}")
    if not unidades:
        linhas.append("  Nenhum jogo solto encontrado fora de Emulation/roms.")
    if sem:
        linhas.append(f"\n  Não identificados ({len(sem)}) — ficam onde estão (mande pelo Telegram com o nome do console):")
        for s in sem[:10]:
            linhas.append("      ? " + str(s).replace(str(home), "~"))
        if len(sem) > 10:
            linhas.append(f"      ? … e mais {len(sem) - 10}")
    return "\n".join(linhas)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    home = Path.home()
    if "--desfazer" in argv:
        desfazer(); return 0
    unidades, sem = encontrar(home)
    print(resumo(unidades, sem, home))
    if "--json" in argv:
        print(json.dumps({"jogos": len(unidades), "nao_identificados": len(sem)}))
    if "--aplicar" in argv and unidades:
        print()
        feitos = aplicar(unidades, home)
        print(f"\n{len(feitos)} jogo(s) organizados. Para desfazer: python3 -m dc.varredura --desfazer")
    elif unidades:
        print("\n(só mostrei; para organizar: python3 -m dc.varredura --aplicar)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
