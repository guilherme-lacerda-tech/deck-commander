"""M4 — /sync: downloads concluídos -> biblioteca.

Classificação (M4.2): categoria explícita do /add > extensão + nome > pergunta.
Integridade (M4.5): sem referência => 'unverified' (nunca 'corrupted' sem evidência).
ZIP (M4.6): extração protegida; suspeito => quarentena. >3 jogáveis => pede confirmação.
ROM hack (M4.10): detecta [BR]/(Translated)/(T x.y) e mantém a versão original separada.
Multidisco (M4.11): CD1/CD2/(Disc 1) de PS1 => gera .m3u e vira UM jogo.
"""
from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import safe_extract
from .emulators import CONSOLES
from .quarantine import quarantine

ARCHIVES = {".zip", ".7z", ".rar"}
AMBIGUOUS = {".iso", ".chd", ".zip", ".7z", ".bin", ".cue", ".pbp"}  # existe em vários consoles
_DISC = re.compile(r"\s*[\(\[]?\s*(disc|disco|cd)\s*([0-9]+)\s*[\)\]]?", re.IGNORECASE)
_HACK = re.compile(r"\[(br|pt-?br|t[-+]?por?)\]|\((br|pt-?br|translated|traduzido)\)|\(t\s?\d", re.IGNORECASE)
# A ordem importa: o mais específico vem antes ("Wii U" antes de "Wii", "Switch 2" antes de "Switch",
# "PlayStation Portable" antes de "PlayStation"). GoD só entre parênteses/colchetes: "God of War" não é Xbox 360.
NAME_HINTS = [(re.compile(p, re.IGNORECASE), c) for p, c in (
    (r"\bps2\b|playstation 2", "ps2"), (r"\bpsp\b|playstation portable", "psp"),
    (r"\bps3\b|playstation 3", "ps3"), (r"\bpsx\b|\bps1\b|playstation(?! [2-9])", "psx"),
    (r"gamecube|\bngc\b", "gc"), (r"\bwii ?u\b", "wiiu"), (r"\bwii\b", "wii"),
    (r"switch ?2\b|\bns2\b", "switch2"), (r"\bswitch\b|\bnsw\b", "switch"),
    (r"\bsnes\b|super nintendo", "snes"), (r"\bn64\b|nintendo 64", "n64"), (r"\bgba\b|game boy advance", "gba"),
    (r"\bnds\b|nintendo ds\b|\(ds\)|\[ds\]", "nds"), (r"\b3ds\b|nintendo 3ds", "n3ds"),
    (r"xbox ?360|\bx360\b|freeboot|[\(\[]god[\)\]]|games on demand", "x360"), (r"\bxbox\b", "xbox"), (r"dreamcast", "dc"),
    (r"\bsaturn\b", "saturn"), (r"sega ?cd|mega ?cd", "segacd"), (r"mega ?drive|genesis", "genesis"))]


def _link_or_copy(src: Path, dst: Path) -> None:
    """Hardlink no mesmo disco (instantâneo, 0 bytes extras); cópia entre discos."""
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def classify(name: str, explicit: str | None = None) -> str | None:
    if explicit and explicit != "auto":  # "auto" = /add sem console: decide pelo nome
        return explicit if explicit in CONSOLES and not CONSOLES[explicit].get("remoto") else None
    for rx, c in NAME_HINTS:
        if rx.search(name):
            return c
    ext = Path(name).suffix.lower()
    owners = [c for c, spec in CONSOLES.items() if ext in spec["exts"]]
    if len(owners) == 1 and ext not in AMBIGUOUS:
        return owners[0]
    return None  # ambíguo -> bot pergunta


def _setor(f, n: int, tam: int, desloc: int) -> bytes:
    f.seek(n * tam + desloc)
    return f.read(2048)


def console_do_disco(arq: Path) -> str | None:
    """PS1 ou PS2 pelo próprio disco: o SYSTEM.CNF do PS2 tem "BOOT2", o do PS1 tem "BOOT".
    Lê imagem de 2048 bytes por setor (.iso) e de 2352 (.bin/.img de CD, modo 1 ou 2). None = não sei."""
    try:
        with open(arq, "rb") as f:
            for tam, desloc in ((2048, 0), (2352, 24), (2352, 16)):
                pvd = _setor(f, 16, tam, desloc)
                if pvd[:6] != b"\x01CD001":
                    continue
                raiz_lba = int.from_bytes(pvd[156 + 2:156 + 6], "little")
                raiz_tam = int.from_bytes(pvd[156 + 10:156 + 14], "little")
                pos = 0
                dados = b"".join(_setor(f, raiz_lba + i, tam, desloc) for i in range(min(8, (raiz_tam + 2047) // 2048)))
                while pos < len(dados):
                    n = dados[pos]
                    if n == 0:  # fim do setor: pula para o próximo
                        pos = (pos // 2048 + 1) * 2048
                        continue
                    nome = dados[pos + 33:pos + 33 + dados[pos + 32]].split(b";")[0].upper()
                    if nome == b"SYSTEM.CNF":
                        lba = int.from_bytes(dados[pos + 2:pos + 6], "little")
                        cnf = _setor(f, lba, tam, desloc).upper()
                        return "ps2" if b"BOOT2" in cnf else "psx" if b"BOOT" in cnf else None
                    pos += n
                return None
    except (OSError, IndexError):
        return None
    return None


def _console_pelos_discos(arquivos: list[Path]) -> str | None:
    vistos = {console_do_disco(f) for f in arquivos if f.suffix.lower() in (".iso", ".bin", ".img")}
    vistos.discard(None)
    return vistos.pop() if len(vistos) == 1 else None


GAME_EXTS = {e for spec in CONSOLES.values() for e in spec["exts"]} | ARCHIVES | {".bin", ".mdf"}


def _structure(files: list[Path]) -> str | None:
    """Pastas que só se reconhecem pela estrutura: PS3 (PS3_GAME/USRDIR/EBOOT.BIN), Xbox 360 GoD
    (<TitleID>/00007000/<cabeçalho>) e dump de Switch 2 (base/exefs/main)."""
    for f in files:
        up = [x.upper() for x in f.parts[-3:-1]]
        if f.name.upper() == "EBOOT.BIN" and up == ["PS3_GAME", "USRDIR"]:
            return "ps3"
        if not f.suffix and f.parent.name == "00007000":
            return "x360"
        if f.name == "main" and up == ["BASE", "EXEFS"]:
            return "switch2"
    return None


def _inner_names(archive: Path) -> list[str]:
    """Nomes dos arquivos dentro de um .zip/.7z/.rar (só lê o índice; nunca extrai)."""
    try:
        if archive.suffix.lower() == ".zip":
            import zipfile
            with zipfile.ZipFile(archive) as z:
                return [n for n in z.namelist() if not n.endswith("/")]
        return [f["path"] for f in safe_extract.inspect_external(archive)]
    except Exception:  # noqa: BLE001 — arquivo estranho: segue a pergunta normal
        return []


def _files(content: Path) -> list[Path]:
    return [content] if content.is_file() else sorted(f for f in content.rglob("*") if f.is_file())


def guess_console(content: Path) -> str | None:
    """/add sem console: nome do download > estrutura da pasta > nomes dos arquivos (inclusive os de dentro
    de .zip/.7z/.rar, só pelo índice). None = continua ambíguo (o bot pergunta)."""
    c = classify(content.name)
    if c:
        return c
    files = _files(content)
    c = _structure(files)
    if c:
        return c
    names = [f.name for f in files]
    for f in files:
        if f.suffix.lower() in ARCHIVES and not _extra_volume(f, files):
            names += [Path(n).name for n in _inner_names(f)]
    guesses = {classify(n) for n in names} - {None}
    return guesses.pop() if len(guesses) == 1 else None


def has_game_files(content: Path) -> bool:
    files = _files(content)
    return bool(_structure(files)) or any(f.suffix.lower() in GAME_EXTS or _VOLUME.search(f.name) for f in files)


def is_translation(name: str) -> bool:
    return bool(_HACK.search(name))


def playable(files: list[Path], console: str) -> list[Path]:
    exts = CONSOLES[console]["exts"]
    out = [f for f in files if f.suffix.lower() in exts and f.suffix.lower() != ".zip"]
    if CONSOLES[console].get("god"):  # Xbox 360 Games on Demand: o cabeçalho sem extensão em 00007000/
        out += [f for f in files if not f.suffix and f.parent.name == "00007000"]
    if CONSOLES[console].get("eboot"):  # PS3 em pasta
        out += [f for f in files if f.name == "EBOOT.BIN" and f.parent.name == "USRDIR" and f.parent.parent.name == "PS3_GAME"]
    if CONSOLES[console].get("dump"):  # Switch 2: <jogo>/base/exefs/main
        out += [f for f in files if f.name == "main" and [x.lower() for x in f.parts[-3:-1]] == ["base", "exefs"]]
    if console == "switch":
        from .library import switch_kind
        out = [f for f in out if switch_kind(f.name) in ("base", "unknown")]
    return out


def switch_extras(files: list[Path]) -> list[Path]:
    """Atualização/DLC de Switch (pelo Title ID no nome)."""
    from .library import switch_kind
    return [f for f in files if f.suffix.lower() in CONSOLES["switch"]["exts"] and switch_kind(f.name) in ("update", "dlc")]


def make_m3u(discs: list[Path], folder: Path, titulo: str = "") -> Path | None:
    """PS1 multidisco: (Disc 1)/(Disc 2) -> '<jogo>.m3u' com caminhos relativos a `folder`, preservando nomes.
    Falha real 14/11/2026 (Metal Gear Solid): os discos estavam numa subpasta e o .m3u listava só o nome do arquivo
    (caminho errado) -> o jogo virou 3 atalhos ("mgs", "mgs_cd1", "mgs_cd2"). Nome curto do disco ("mgs_") cede
    lugar ao nome do download."""
    numbered = [(int(m.group(2)), d) for d in discs if (m := _DISC.search(d.stem))]
    if len(numbered) < 2:
        return None
    numbered.sort()
    base = _DISC.sub("", numbered[0][1].stem).strip(" _-.")
    # "mgs" (nome de arquivo: minúsculo, sem espaço) cede ao nome do download; "FF7" (sigla de verdade) fica
    if titulo.strip() and (len(base) < 3 or (base == base.lower() and " " not in base and len(base) < 8)):
        base = titulo.strip()
    m3u = folder / f"{base or 'jogo'}.m3u"
    linhas = []
    for _, d in numbered:
        try:
            linhas.append(d.relative_to(folder).as_posix())
        except ValueError:
            linhas.append(d.name)
    m3u.write_text("\n".join(linhas) + "\n", "utf-8")
    return m3u


@dataclass
class SyncItem:
    name: str
    console: str | None
    status: str                    # added / ask_console / ask_many / quarantined / skipped
    files: list[str] = field(default_factory=list)
    note: str = ""
    integrity: str = "unverified"


_VOLUME = re.compile(r"\.(r\d{2,3}|s\d{2})$|\.part(?!0*1\.rar$)\d+\.rar$", re.IGNORECASE)


def _extra_volume(f: Path, files: list[Path]) -> bool:
    """Volume de continuação de RAR dividido (só pula se o primeiro volume estiver junto)."""
    if not _VOLUME.search(f.name):
        return False
    if f.suffix.lower() == ".rar":  # nome.part2.rar -> precisa do nome.part1.rar
        base = re.sub(r"\.part\d+\.rar$", "", f.name, flags=re.IGNORECASE)
        return any(re.fullmatch(re.escape(base) + r"\.part0*1\.rar", g.name, re.IGNORECASE) for g in files)
    return any(g.name.lower() == f.stem.lower() + ".rar" and g.parent == f.parent for g in files)


def mds_tracks(mds: Path) -> list[dict]:
    """Faixas de uma imagem do Alcohol 120% (.mds): tipo, tamanho do setor, setor inicial e posição no .mdf.
    Lista vazia = não deu para ler (formato desconhecido)."""
    try:
        b = mds.read_bytes()
        if not b.startswith(b"MEDIA DESCRIPTOR"):
            return []
        u16 = lambda o: int.from_bytes(b[o:o + 2], "little")
        u32 = lambda o: int.from_bytes(b[o:o + 4], "little")
        sess = u32(0x50)
        total, blocks = b[sess + 10], u32(sess + 20)
        out = []
        for i in range(total):
            o = blocks + 80 * i
            point = b[o + 4]
            if not 1 <= point <= 99:
                continue  # A0/A1/A2 = blocos de controle, não faixas
            low = b[o] & 0x0F
            kind = "AUDIO" if low == 9 else "MODE1/2352" if low == 0xA else "MODE2/2352"
            out.append({"track": point, "kind": kind, "sector": u16(o + 16), "start": u32(o + 36),
                        "offset": int.from_bytes(b[o + 40:o + 48], "little")})
        return sorted(out, key=lambda x: x["track"])
    except (OSError, IndexError):
        return []


def _msf(sector: int) -> str:
    return f"{sector // 4500:02d}:{sector // 75 % 60:02d}:{sector % 75:02d}"


_SERIAL = re.compile(r"^[A-Z]{4}[_-]?\d{3}\.?\d{2}$", re.IGNORECASE)  # SLES_005.24, SLUS-00067…


def mdf_to_cue(mdf: Path, title: str = "") -> Path | None:
    """CD de PS1 em .mdf/.mds (Alcohol 120%) vira .bin + .cue, que o DuckStation e o tradutor abrem. Lê as faixas
    do .mds (dados + áudio); setores de 2448 bytes (2352 + 96 de subcanal) perdem o subcanal."""
    mds = mdf.with_suffix(".mds")
    tracks = mds_tracks(mds) if mds.exists() else []
    size = mdf.stat().st_size
    if tracks:
        sizes = {t["sector"] for t in tracks}
        if len(sizes) != 1 or sizes.pop() not in (2352, 2448):
            return None
        sector = tracks[0]["sector"]
    else:
        sector = 2352 if size % 2352 == 0 else 2448 if size % 2448 == 0 else 0
        tracks = [{"track": 1, "kind": "MODE2/2352", "sector": sector, "start": 0, "offset": 0}]
    if not sector or size % sector:
        return None
    stem = mdf.stem
    if title and _SERIAL.match(stem):  # nome do arquivo é o código do disco: usa o nome do download
        stem = re.sub(r'[<>:"/|?*\\]', "", title).strip() or stem
    bin_ = mdf.with_name(stem + ".bin")
    if sector == 2352:
        mdf.rename(bin_)
    else:
        tmp = bin_.with_name(bin_.name + ".tmp")
        with open(mdf, "rb") as src, open(tmp, "wb") as dst:
            while True:
                chunk = src.read(2448 * 4096)
                if not chunk:
                    break
                dst.write(b"".join(chunk[i:i + 2352] for i in range(0, len(chunk), 2448)))
        os.replace(tmp, bin_)
        mdf.unlink()
    lines = [f'FILE "{bin_.name}" BINARY']
    for tr in tracks:
        lines.append(f"  TRACK {tr['track']:02d} {tr['kind']}")
        in_file = tr["offset"] // sector  # o pregap (2 s) costuma estar gravado antes do início da faixa
        if tr["track"] > 1 and in_file < tr["start"]:
            lines.append(f"    INDEX 00 {_msf(in_file)}")
        lines.append(f"    INDEX 01 {_msf(tr['start'])}")
    cue = bin_.with_suffix(".cue")
    cue.write_text(chr(10).join(lines) + chr(10), "utf-8")
    if mds.exists():
        mds.unlink()
    return cue


def ingest(content: Path, console: str | None, roms_root: Path, quarantine_root: Path,
           work: Path, confirm_many: bool = False) -> SyncItem:
    """Leva um download concluído (arquivo ou pasta) para roms_root/<console>/<pasta>/."""
    content = Path(content)
    name = content.name
    console = classify(name, console) if console and console != "auto" else guess_console(content)
    if console is None:
        if not has_game_files(content):
            return SyncItem(name, None, "skipped", note="não achei arquivo de jogo nesse download (só texto/imagem?)")
        return SyncItem(name, None, "ask_console", note="não consegui identificar o console")
    staging = work / f"stage-{abs(hash(str(content))) % 10**8}"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        src_files = [content] if content.is_file() else sorted(f for f in content.rglob("*") if f.is_file())
        collected: list[Path] = []
        for f in src_files:
            if _extra_volume(f, src_files):
                continue  # .r00/.r01…/.partN.rar: o 7-Zip lê junto com o primeiro volume (.rar)
            if f.suffix.lower() in ARCHIVES:
                try:
                    out = safe_extract.extract_any(f, staging / f.stem)
                except safe_extract.NoSpace as e:
                    return SyncItem(name, console, "no_space", note=f"{e} — libere espaço (/disk); tento de novo sozinho")
                except safe_extract.UnsafeArchive as e:
                    q = quarantine(f, quarantine_root, f"arquivo suspeito no /sync: {e}")
                    return SyncItem(name, console, "quarantined", note=f"{e} (em {q.name})")
                collected += out
            else:
                dst = staging / f.relative_to(content.parent if content.is_file() else content)
                dst.parent.mkdir(parents=True, exist_ok=True)
                _link_or_copy(f, dst)
                collected.append(dst)
        empty = [f for f in collected if f.stat().st_size == 0]
        if empty:
            q = quarantine(staging, quarantine_root, f"arquivos vazios: {[e.name for e in empty][:3]}")
            return SyncItem(name, console, "quarantined", note=f"arquivo vazio (em {q.name})", integrity="corrupted")
        nota_disco = ""
        if console in ("psx", "ps2"):  # falha real 14/11/2026: jogo de PS2 marcado como PS1 na hora de mandar
            disco = _console_pelos_discos(collected)
            if disco and disco != console:
                rot = {"psx": "PS1", "ps2": "PS2"}
                nota_disco = f"o disco é de {rot[disco]}, não de {rot[console]} — fui pelo disco"
                console = disco
        if console == "ps2":  # imagem .mdf de DVD = setores de 2048 bytes = .iso (o PCSX2 abre .iso)
            for i, f in enumerate(collected):
                if f.suffix.lower() == ".mdf" and f.stat().st_size % 2048 == 0:
                    iso = f.with_suffix(".iso")
                    f.rename(iso)
                    collected[i] = iso
        if console == "psx":  # imagem .mdf/.mds de CD: vira .bin + .cue (o DuckStation e o tradutor abrem)
            for i, f in enumerate(collected):
                if f.suffix.lower() == ".mdf":
                    cue = mdf_to_cue(f, re.sub(r"\.(zip|7z|rar)$", "", name, flags=re.IGNORECASE))
                    if cue:
                        collected[i] = cue
        games = playable(collected, console)
        title = re.sub(r"\.(zip|7z|rar)$", "", name, flags=re.IGNORECASE)
        if not games and console == "switch" and switch_extras(collected):
            # atualização/DLC baixada sozinha: vai para a pasta do Switch, que o Ryujinx lê sozinho (sem atalho)
            dest, n = roms_root / "switch" / title, 1
            while dest.exists():
                dest = roms_root / "switch" / f"{title} ({n})"
                n += 1
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(staging), str(dest))
            return SyncItem(name, console, "added", files=[],
                            note="atualização/DLC: o Ryujinx carrega sozinho junto do jogo (sem atalho novo)")
        if not games:
            return SyncItem(name, console, "skipped",
                            note="nenhum arquivo jogável para " + CONSOLES[console].get("label", console))
        if console == "psx":
            m3u = make_m3u([g for g in games if g.suffix.lower() in (".cue", ".chd", ".pbp")], staging, title)
            if m3u:
                games = [m3u]
        if len(games) > 3 and not confirm_many:
            return SyncItem(name, console, "ask_many", files=[g.name for g in games],
                            note=f"{len(games)} jogos no mesmo download — confirme com /sync tudo")
        dest, n = roms_root / console / title, 1
        while dest.exists():  # nunca mistura com uma pasta que já existe
            dest = roms_root / console / (f"{title} (novo)" if n == 1 else f"{title} (novo {n})")
            n += 1
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staging), str(dest))
        moved = [str(dest / g.relative_to(staging)) for g in games]
        note = "parece tradução/ROM hack — adicionado separado, original intacto" if is_translation(name) else ""
        note = "; ".join(filter(None, [nota_disco, note]))
        return SyncItem(name, console, "added", files=moved, note=note)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
