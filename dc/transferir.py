"""Transferência segura de um jogo do Deck para o PC Windows (jogo + emulador + TODA a configuração).

`preparar(game_id)` monta um MANIFESTO do que pertence ao jogo: cada arquivo com caminho no Deck,
tamanho, sha256 (streaming, com cache por tamanho/mtime), categoria e destino lógico no Windows:

  {JOGOS}/<console>/...  arquivos do jogo (base, updates, DLC)
  {EMU}/...              pasta de dados do emulador no PC (saves, config, mods, keys/firmware)
  {LINUX}/...            o emulador do Deck (binário Linux; vai só como arquivo de referência)

Categorias: jogo, update, dlc, save, config-global, config-jogo, mods, keys, emulador-linux.
Arquivos de texto com caminhos do Deck (/home/deck/...) vão com `reescrever=True` e a lista de
trocas fica em `manifesto["reescrever"]` (o script do PC troca pelos caminhos do Windows).
Cache de shader NÃO vai: depende da GPU, do driver e do sistema — o emulador do PC recompila.

Nunca altera nada no Deck: só lê (o único arquivo escrito é o cache de hashes, desligável).
Só stdlib e sem import relativo no topo: roda instalado (`python3 -m dc.transferir`) ou mandado
por ssh pela entrada padrão (`python3 - manifesto <jogo>`), sem instalar nada no Deck.

Saves do Ryujinx: a pasta do save NÃO tem o title id no nome. O índice fica em
bis/system/save/8000000000000000/0/imkvdb.arc (formato IMKV/IMEN):
  cabeçalho 12 bytes: "IMKV", u32 reservado, u32 quantidade
  cada entrada: "IMEN", u32 tamanho da chave (0x40), u32 tamanho do valor (0x40), chave, valor
  chave (SaveDataAttribute): u64 program_id @0, user_id 16 bytes @8, u64 system_save_id @0x18,
                             u8 tipo @0x20 (0 sistema, 1 conta, 2 bcat, 3 aparelho, 4 temporário, 5 cache)
  valor: u64 save_data_id @0 -> pasta bis/user/save/<save_data_id em 16 dígitos hex minúsculos>
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import struct
import sys
import time
from pathlib import Path

VERSAO = 1
CATEGORIAS = ("jogo", "update", "dlc", "save", "config-global", "config-jogo", "mods", "keys", "emulador-linux")
TEXTO_EXTS = {".ini", ".json", ".cfg", ".opt", ".rmp", ".txt", ".pnach", ".cht", ".m3u"}
CUE_LIKE = {".cue", ".m3u", ".gdi", ".ccd", ".mds"}
COMANDO_PC = r"tools\pc\transferir-do-deck.bat -Jogo {gid}"

# Emulador de cada console + o que o script do PC procura no Windows
EMU_DO_CONSOLE = {"switch2": "lichii", "switch": "ryujinx", "psx": "duckstation", "ps2": "pcsx2", "psp": "ppsspp",
                  "x360": "xenia"}
RA_CONSOLES = {"snes", "n64", "gba", "nes", "gb", "gbc", "genesis", "sms", "gg", "segacd", "saturn", "pce", "arcade"}
# Versão Windows oficial de cada emulador (só a indicação: o Deck Commander NÃO baixa nada)
EMU_WINDOWS = {
    "lichii": {"projeto": "Lichii (Switch 2; mesma build do Deck, ex.: build-83)",
               "releases": "https://github.com/zortos293/Lichii/releases",
               "dados": "pasta 'user' ao lado do lichii.exe (portátil) ou %APPDATA%\\eden"},
    "ryujinx": {"projeto": "Ryujinx (Ryubing), mesma versão do Deck",
                "releases": "https://git.ryujinx.app/projects/Ryubing/releases",
                "dados": "pasta 'portable' ao lado do Ryujinx.exe ou %APPDATA%\\Ryujinx"},
    "duckstation": {"projeto": "DuckStation (stenzek)", "releases": "https://github.com/stenzek/duckstation/releases",
                    "dados": "pasta do .exe com portable.txt ou Documentos\\DuckStation"},
    "pcsx2": {"projeto": "PCSX2", "releases": "https://github.com/PCSX2/pcsx2/releases",
              "dados": "pasta do .exe com portable.ini ou Documentos\\PCSX2"},
    "retroarch": {"projeto": "RetroArch (libretro)", "releases": "https://www.retroarch.com/?page=platforms",
                  "dados": "pasta do retroarch.exe ou %APPDATA%\\RetroArch"},
    "ppsspp": {"projeto": "PPSSPP", "releases": "https://github.com/hrydgard/ppsspp/releases",
               "dados": "pasta do PPSSPPWindows64.exe (memstick)"},
    "xenia": {"projeto": "Xenia Canary", "releases": "https://github.com/xenia-canary/xenia-canary-releases/releases",
              "dados": "pasta do xenia_canary.exe com portable.txt"},
}


# ------------------------------------------------------------------ caminhos -----------
def _home(home=None) -> Path:
    return Path(home) if home else Path(os.environ.get("DC_ROOT") or Path.home())


def _data_dir(home: Path) -> Path:
    if os.environ.get("XDG_DATA_HOME") and not os.environ.get("DC_ROOT"):
        return Path(os.environ["XDG_DATA_HOME"]) / "deck-commander"
    return home / ".local/share/deck-commander"


def carregar_mapa(home=None) -> dict:
    p = _data_dir(_home(home)) / "launch-map.json"
    try:
        lm = json.loads(p.read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    return {g: e for g, e in lm.items() if not e.get("removed")}


# ------------------------------------------------------------------ hash ---------------
class HashCache:
    """sha256 por (caminho, tamanho, mtime_ns). Não recalcula 19 GB à toa."""

    def __init__(self, path: Path | None):
        self.path, self.d, self.mudou = path, {}, False
        if path:
            try:
                self.d = json.loads(path.read_text("utf-8"))
            except (OSError, ValueError):
                self.d = {}

    def sha256(self, p: Path, st: os.stat_result) -> str:
        k = str(p)
        c = self.d.get(k)
        if c and c[0] == st.st_size and c[1] == st.st_mtime_ns:
            return c[2]
        h = hashlib.sha256()
        with open(p, "rb") as f:
            while True:
                b = f.read(1 << 20)
                if not b:
                    break
                h.update(b)
        sha = h.hexdigest()
        self.d[k] = [st.st_size, st.st_mtime_ns, sha]
        self.mudou = True
        return sha

    def salvar(self) -> None:
        if not (self.path and self.mudou):
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(self.d), "utf-8")
        os.replace(tmp, self.path)


# ------------------------------------------------------------------ manifesto ----------
class Manifesto:
    def __init__(self, gid: str, entrada: dict, emu: str):
        self.gid, self.e, self.emu = gid, entrada, emu
        self.arquivos: dict[str, dict] = {}
        self.excluidos: list[dict] = []
        self.avisos: list[str] = []
        self.notas: list[str] = []
        self.trocas: dict[str, str] = {}
        self.info: dict = {}

    def add(self, p: Path, categoria: str, destino: str, reescrever: bool | None = None) -> None:
        p = Path(p)
        if "\t" in str(p) or "\n" in str(p) or "\t" in destino or "\n" in destino:
            self.excluidos.append({"caminho": str(p), "motivo": "nome com TAB/quebra de linha (o manifesto é TSV)"})
            return
        if not p.is_file() or str(p) in self.arquivos:
            return
        # reescrever=None: decidido no fim, quando todas as trocas de caminho já são conhecidas
        self.arquivos[str(p)] = {"origem": str(p), "categoria": categoria, "destino": destino,
                                 "reescrever": reescrever}

    def add_arvore(self, raiz: Path, categoria: str, destino: str, pular=()) -> None:
        raiz = Path(raiz)
        if not raiz.is_dir():
            return
        for dp, dns, fns in os.walk(raiz):
            rel_dir = Path(dp).relative_to(raiz)
            dns[:] = sorted(d for d in dns if (rel_dir / d).as_posix() not in pular)
            for fn in sorted(fns):
                rel = (rel_dir / fn).as_posix()
                self.add(Path(dp) / fn, categoria, f"{destino}/{rel}")

    def excluir(self, p: Path, motivo: str) -> None:
        if Path(p).exists():
            self.excluidos.append({"caminho": str(p), "motivo": motivo})

    def troca(self, de: Path | str, para: str) -> None:
        self.trocas[str(de).rstrip("/")] = para


def _tem_caminho_do_deck(p: Path, prefixos) -> bool:
    try:
        with open(p, "rb") as f:
            b = f.read(4 << 20)
    except OSError:
        return False
    return any(x.encode() in b for x in ("/home/deck", "/run/media/deck", *prefixos))


# ------------------------------------------------------------------ arquivos do jogo ---
def _dir_console(p: Path, console: str) -> Path | None:
    """…/roms/<console> do caminho (para o destino {JOGOS}/<console>/<resto>)."""
    parts = p.parts
    for i in range(len(parts) - 1, 0, -1):
        if parts[i - 1].lower() == "roms" and i < len(parts) - 1:
            return Path(*parts[: i + 1])
    return None


def _destino_jogo(m: Manifesto, p: Path, console: str, base: Path) -> str:
    dc = _dir_console(p, console)
    if dc is not None:
        m.troca(dc, f"{{JOGOS}}/{console}")
        rel = p.relative_to(dc)
        if len(rel.parts) == 1:  # arquivo solto em roms/<console>: ganha pasta própria {JOGOS}/<console>/<jogo>/
            destino = f"{{JOGOS}}/{console}/{_pasta_jogo(m, base, p)}/{rel.as_posix()}"
            m.troca(p, destino)
            return destino
        return f"{{JOGOS}}/{console}/{rel.as_posix()}"
    m.troca(base, f"{{JOGOS}}/{console}/{base.name}")
    return f"{{JOGOS}}/{console}/{base.name}/{p.relative_to(base).as_posix()}"


def _pasta_jogo(m: "Manifesto", base: Path, p: Path) -> str:
    nome = re.sub(r'[<>:"/\\|?*\t\n]', "_", m.e.get("title") or Path(m.e.get("rom", p)).stem).strip(" .")
    return nome or p.stem


def _refs_disco(rom: Path) -> list[Path]:
    """Arquivos que um .cue/.m3u/.gdi/.ccd/.mds referencia (recursivo para m3u -> cue)."""
    out, ext = [], rom.suffix.lower()
    try:
        txt = rom.read_text("utf-8", errors="replace") if ext != ".mds" else ""
    except OSError:
        return out
    if ext == ".cue":
        for mm in re.finditer(r'^\s*FILE\s+"?(.+?)"?\s+\S+\s*$', txt, re.M | re.I):
            out.append(rom.parent / mm.group(1))
    elif ext == ".m3u":
        for ln in txt.splitlines():
            ln = ln.strip()
            if ln and not ln.startswith("#"):
                q = rom.parent / ln
                out.append(q)
                if q.suffix.lower() in CUE_LIKE:
                    out += _refs_disco(q)
    elif ext == ".gdi":
        for ln in txt.splitlines()[1:]:
            mm = re.match(r'\s*\d+\s+\d+\s+\d+\s+\d+\s+("([^"]+)"|(\S+))', ln)
            if mm:
                out.append(rom.parent / (mm.group(2) or mm.group(3)))
    elif ext in (".mds", ".ccd"):
        out += [q for q in rom.parent.iterdir() if q.stem == rom.stem and q != rom]
    return out


TID_RE = re.compile(r"\[(0100[0-9A-Fa-f]{12})\]")


def _tid_npdm(npdm: Path) -> str | None:
    """Program id do main.npdm (META -> ACI0 + 0x10)."""
    try:
        b = npdm.read_bytes()
        if b[:4] != b"META":
            return None
        off, = struct.unpack_from("<I", b, 0x70)
        if b[off:off + 4] != b"ACI0":
            return None
        pid, = struct.unpack_from("<Q", b, off + 0x10)
        return f"{pid:016X}"
    except (OSError, struct.error):
        return None


def _jogo_switch2(m: Manifesto, rom: Path) -> Path:
    raiz = rom.parents[2] if rom.name == "main" and rom.parent.name == "exefs" else rom.parent
    for dp, dns, fns in os.walk(raiz):
        dns.sort()
        for fn in sorted(fns):
            p = Path(dp) / fn
            top = p.relative_to(raiz).parts[0].lower()
            cat = {"updates": "update", "update": "update", "dlc": "dlc"}.get(top, "jogo")
            m.add(p, cat, _destino_jogo(m, p, "switch2", raiz))
    tid = _tid_npdm(raiz / "base/exefs/main.npdm") or _tid_npdm(rom.with_name("main.npdm"))
    if not tid:
        hx = [d.name for d in raiz.iterdir() if re.fullmatch(r"0[0-9a-fA-F]{15}", d.name)]
        tid = hx[0].upper() if hx else None
    m.info["title_id"] = tid
    return raiz


def _cat_switch(tid_base: str, tid_arq: str) -> str:
    b, a = int(tid_base, 16), int(tid_arq, 16)
    if a == b:
        return "jogo"
    if a == b | 0x800:
        return "update"
    return "dlc"


def _jogo_switch(m: Manifesto, rom: Path, home: Path, ryu: Path | None) -> Path:
    mm = TID_RE.search(rom.name)
    tid = mm.group(1).upper() if mm else None
    m.info["title_id"] = tid
    dc = _dir_console(rom, "switch")
    base = rom.parent
    extras: list[Path] = []
    if tid:
        prefixo = tid[:12]
        rec = dc is None or rom.parent != dc
        it = os.walk(rom.parent) if rec else [(str(rom.parent), [], os.listdir(rom.parent))]
        for dp, _dns, fns in it:
            for fn in fns:
                t = TID_RE.search(fn)
                if t and t.group(1).upper().startswith(prefixo) and Path(fn).suffix.lower() in (".nsp", ".nsz", ".xci", ".xcz"):
                    extras.append(Path(dp) / fn)
        if ryu:
            g = ryu / "games" / tid.lower()
            for js in ("updates.json", "dlc.json"):
                try:
                    d = json.loads((g / js).read_text("utf-8"))
                except (OSError, ValueError):
                    continue
                paths = d.get("paths", []) if isinstance(d, dict) else [x.get("path") for x in d if isinstance(x, dict)]
                extras += [Path(x) for x in paths if x]
    m.add(rom, "jogo", _destino_jogo(m, rom, "switch", base))
    for p in sorted(set(extras)):
        if not p.is_file():
            m.avisos.append(f"update/DLC citado mas não encontrado: {p}")
            continue
        t = TID_RE.search(p.name)
        cat = _cat_switch(tid, t.group(1)) if (t and tid) else "dlc"
        m.add(p, cat, _destino_jogo(m, p, "switch", base))
    return base


def _jogo_generico(m: Manifesto, rom: Path, console: str) -> Path:
    base = rom.parent
    if rom.is_dir():
        for dp, dns, fns in os.walk(rom):
            dns.sort()
            for fn in sorted(fns):
                p = Path(dp) / fn
                m.add(p, "jogo", _destino_jogo(m, p, console, rom.parent))
        return rom
    m.add(rom, "jogo", _destino_jogo(m, rom, console, base))
    refs = _refs_disco(rom) if rom.suffix.lower() in CUE_LIKE else []
    if console == "x360" and rom.parent.name == "00007000":  # Games on Demand: <TID>/00007000/<arq> + <arq>.data/
        base = rom.parents[1]
        for dp, dns, fns in os.walk(base):
            for fn in fns:
                p = Path(dp) / fn
                m.add(p, "jogo", _destino_jogo(m, p, console, base.parent))
    for p in refs + [q for q in base.iterdir() if q.is_file() and q.stem == rom.stem and q != rom]:
        if p.is_file():
            m.add(p, "jogo", _destino_jogo(m, p, console, base))
        else:
            m.avisos.append(f"arquivo citado pelo {rom.suffix} não existe: {p}")
    return base


# ------------------------------------------------------------------ serial PS1/PS2 -----
SERIAL_RE = re.compile(r"([A-Z]{4})[_-]?(\d{3})\.?(\d{2})")


def serial_disco(rom: Path, arquivos: list[Path]) -> str | None:
    """SLUS-00529: do nome ([SLUS-00529] Hercules) ou do SYSTEM.CNF lido no começo da imagem."""
    for nome in [rom.name, rom.parent.name]:
        mm = re.search(r"\b(S[CL][EUP][SMD]|SL[A-Z]{2}|SC[A-Z]{2})[_-](\d{3})\.?(\d{2})\b", nome)
        if mm:
            return f"{mm.group(1)}-{mm.group(2)}{mm.group(3)}"
    for p in arquivos:
        if p.suffix.lower() in (".bin", ".iso", ".img", ".mdf"):
            try:
                with open(p, "rb") as f:
                    b = f.read(16 << 20)
            except OSError:
                continue
            mm = re.search(rb"BOOT2?\s*=\s*cdrom0?:\\?([A-Z]{4})_(\d{3})\.(\d{2})", b)
            if mm:
                return f"{mm.group(1).decode()}-{mm.group(2).decode()}{mm.group(3).decode()}"
    return None


# ------------------------------------------------------------------ emuladores ---------
def _primeiro(*ps: Path) -> Path | None:
    return next((p for p in ps if p.exists()), None)


def _binario(home: Path, console: str, emu: str) -> Path | None:
    globs = {"lichii": ["Emulation/Lichii/lichii-linux-x86_64-pgo.AppImage", "Emulation/Lichii/*.AppImage"],
             "ryujinx": ["Downloads/publish/Ryujinx", "Applications/publish/Ryujinx", "Applications/Ryujinx*.AppImage"],
             "duckstation": ["Applications/DuckStation*.AppImage", "Applications/duckstation*.AppImage"]}.get(emu, [])
    import glob
    for g in globs:
        hits = sorted(glob.glob(str(home / g)))
        if hits:
            return Path(hits[0])
    return None


def _nomes_tid(pasta: Path, tid: str) -> list[str]:
    """Pastas com o title id em qualquer caixa (nome real do disco; sem duplicar em sistema sem caixa)."""
    try:
        return sorted(n for n in os.listdir(pasta) if n.upper() == tid.upper())
    except OSError:
        return []


def _emu_lichii(m: Manifesto, home: Path) -> None:
    C, D = home / ".config/eden", home / ".local/share/eden"
    tid = (m.info.get("title_id") or "").upper()
    m.info["dados_emulador"] = {"config": str(C), "dados": str(D)}
    m.troca(D, "{EMU}")
    m.troca(C, "{EMU}/config")
    m.add(C / "qt-config.ini", "config-global", "{EMU}/config/qt-config.ini")
    if tid:
        for p in (C / "custom").glob("*.ini") if (C / "custom").is_dir() else []:
            if p.stem.upper() == tid:
                m.add(p, "config-jogo", f"{{EMU}}/config/custom/{p.name}")
        saves = sorted(d for d in (D / "nand/user/save").glob("*/*/*") if d.is_dir() and d.name.upper() == tid)
        for s in saves:
            rel = s.relative_to(D).as_posix()
            m.add_arvore(s, "save", f"{{EMU}}/{rel}")
        m.info["saves"] = [str(s) for s in saves]
        for d in ("load", "sdmc/atmosphere/contents"):
            for nome in _nomes_tid(D / d, tid):
                m.add_arvore(D / d / nome, "mods", f"{{EMU}}/{d}/{nome}")
    else:
        m.avisos.append("não achei o title id do jogo (main.npdm) — saves/mods do Lichii não entraram")
    m.add_arvore(D / "keys", "keys", "{EMU}/keys")
    m.add_arvore(D / "nand/system/Contents", "keys", "{EMU}/nand/system/Contents")  # firmware instalada
    m.add_arvore(D / "nand/system/save", "config-global", "{EMU}/nand/system/save")  # perfis de usuário (UUID dos saves)
    m.add_arvore(D / "play_time", "config-global", "{EMU}/play_time")
    m.add_arvore(D / "amiibo", "config-global", "{EMU}/amiibo")
    m.excluir(home / ".cache/eden/shader", "cache de shader: depende da GPU/driver/sistema; o PC recompila")
    m.excluir(D / "log", "logs")
    m.excluir(D / "crash_dumps", "logs")
    m.notas.append("Saves do Lichii: ~/.local/share/eden/nand/user/save/0000000000000000/<UUID do perfil>/<TITLE ID>/ "
                   "— o perfil (UUID) vem junto em nand/system/save/8000000000000010.")


def ryujinx_saves(ryu: Path, tid: str) -> list[dict]:
    """Entradas do imkvdb.arc do título -> pasta bis/user/save/<save_data_id>."""
    arc = ryu / "bis/system/save/8000000000000000/0/imkvdb.arc"
    return [e for e in ler_imkvdb(arc) if e["program_id"] == int(tid, 16)]


def ler_imkvdb(arc: Path) -> list[dict]:
    try:
        b = arc.read_bytes()
    except OSError:
        return []
    if b[:4] != b"IMKV":
        return []
    n, = struct.unpack_from("<I", b, 8)
    o, out = 12, []
    for _ in range(n):
        if b[o:o + 4] != b"IMEN":
            break
        ks, vs = struct.unpack_from("<II", b, o + 4)
        k, v = b[o + 12:o + 12 + ks], b[o + 12 + ks:o + 12 + ks + vs]
        o += 12 + ks + vs
        pid, = struct.unpack_from("<Q", k, 0)
        said, = struct.unpack_from("<Q", v, 0)
        out.append({"program_id": pid, "user_id": k[8:24].hex(), "tipo": k[0x20],
                    "save_data_id": f"{said:016x}"})
    return out


def _emu_ryujinx(m: Manifesto, home: Path, ryu: Path | None) -> None:
    if not ryu:
        m.avisos.append("pasta do Ryujinx não encontrada (~/.config/Ryujinx)")
        return
    tid = (m.info.get("title_id") or "").lower()
    m.info["dados_emulador"] = {"dados": str(ryu)}
    m.troca(ryu, "{EMU}")
    m.add(ryu / "Config.json", "config-global", "{EMU}/Config.json")
    m.add_arvore(ryu / "profiles", "config-global", "{EMU}/profiles")
    m.add(ryu / "system/Profiles.json", "config-global", "{EMU}/system/Profiles.json")
    for k in sorted((ryu / "system").glob("*.keys")) if (ryu / "system").is_dir() else []:
        m.add(k, "keys", f"{{EMU}}/system/{k.name}")
    m.add_arvore(ryu / "bis/system/Contents", "keys", "{EMU}/bis/system/Contents")  # firmware instalada
    m.add_arvore(ryu / "bis/system/save", "config-global", "{EMU}/bis/system/save")  # inclui o índice imkvdb.arc
    if not tid:
        m.avisos.append("sem title id no nome do arquivo ([0100…]) — saves/mods do Ryujinx não entraram")
        return
    saves = ryujinx_saves(ryu, tid)
    for s in saves:
        d = ryu / "bis/user/save" / s["save_data_id"]
        m.add_arvore(d, "save", f"{{EMU}}/bis/user/save/{s['save_data_id']}")
    m.info["saves"] = [str(ryu / "bis/user/save" / s["save_data_id"]) for s in saves]
    m.info["saves_ryujinx"] = saves
    if not saves:
        m.avisos.append("o jogo ainda não tem save no Ryujinx (nada no imkvdb.arc)")
    m.add_arvore(ryu / "mods/contents" / tid, "mods", f"{{EMU}}/mods/contents/{tid}")
    m.add_arvore(ryu / "sdcard/atmosphere/contents" / tid.upper(), "mods", f"{{EMU}}/sdcard/atmosphere/contents/{tid.upper()}")
    m.add_arvore(ryu / "games" / tid, "config-jogo", f"{{EMU}}/games/{tid}", pular={"cache"})
    m.excluir(ryu / "games" / tid / "cache", "cache de shader/PPTC: depende da GPU/sistema; o PC recompila")
    m.notas.append("Saves do Ryujinx: a pasta é bis/user/save/<save_data_id>, achada pelo índice "
                   "bis/system/save/8000000000000000/0/imkvdb.arc (que vem junto).")


def _emu_duckstation(m: Manifesto, home: Path, serial: str | None, titulo: str) -> None:
    D = _primeiro(home / ".local/share/duckstation", home / ".config/duckstation",
                  home / ".var/app/org.duckstation.DuckStation/data/duckstation")
    if not D:
        m.avisos.append("pasta do DuckStation não encontrada")
        return
    m.info["dados_emulador"] = {"dados": str(D)}
    m.troca(D, "{EMU}")
    m.add(D / "settings.ini", "config-global", "{EMU}/settings.ini")
    m.add(D / "playtime.dat", "config-global", "{EMU}/playtime.dat")
    m.add_arvore(D / "inputprofiles", "config-global", "{EMU}/inputprofiles")
    bios = _ini_valor(D / "settings.ini", "SearchDirectory") or str(D / "bios")
    m.troca(bios, "{EMU}/bios")
    for p in sorted(Path(bios).glob("*")) if Path(bios).is_dir() else []:
        if p.is_file() and p.suffix.lower() == ".bin" and p.stat().st_size == 512 * 1024:  # BIOS do PS1 = .bin de 512 KB
            m.add(p, "keys", f"{{EMU}}/bios/{p.name}")
    nomes = {n for n in (serial, titulo) if n}
    saves = []
    for sub, cat in (("gamesettings", "config-jogo"), ("savestates", "save"), ("memcards", "save"),
                     ("cheats", "mods"), ("patches", "mods")):
        for p in sorted((D / sub).glob("*")) if (D / sub).is_dir() else []:
            if p.is_file() and any(p.name.lower().startswith(n.lower()) for n in nomes) \
                    or (sub == "memcards" and p.name.startswith("shared_card")):
                m.add(p, cat, f"{{EMU}}/{sub}/{p.name}")
                if cat == "save":
                    saves.append(str(p))
    m.info["saves"] = saves
    m.excluir(D / "cache", "cache (shaders/lista de jogos): o PC recria")
    m.notas.append("Saves do DuckStation: memcards/<título do jogo>_1.mcd (cartão por jogo) e savestates/<serial>_*.sav.")


def _emu_pcsx2(m: Manifesto, home: Path, serial: str | None) -> None:
    P = _primeiro(home / ".var/app/net.pcsx2.PCSX2/config/PCSX2", home / ".config/PCSX2")
    if not P:
        m.avisos.append("pasta do PCSX2 não encontrada")
        return
    m.info["dados_emulador"] = {"dados": str(P)}
    m.troca(P, "{EMU}")
    m.add(P / "inis/PCSX2.ini", "config-global", "{EMU}/inis/PCSX2.ini")
    m.add_arvore(P / "inputprofiles", "config-global", "{EMU}/inputprofiles")
    m.add_arvore(P / "memcards", "save", "{EMU}/memcards")
    m.info["saves"] = [str(P / "memcards")]
    m.notas.append("Saves do PCSX2: memcards/Mcd001.ps2 e Mcd002.ps2 são cartões COMPARTILHADOS (têm saves de todos os "
                   "jogos de PS2); vão inteiros.")
    bios = _ini_valor(P / "inis/PCSX2.ini", "Bios") or str(P / "bios")
    m.troca(bios, "{EMU}/bios")
    for p in sorted(Path(bios).glob("*")) if Path(bios).is_dir() else []:
        if p.is_file() and not (p.suffix.lower() == ".bin" and p.stat().st_size == 512 * 1024):  # o resto é do PS2
            m.add(p, "keys", f"{{EMU}}/bios/{p.name}")
    crcs = set()
    if serial:
        for sub, cat in (("gamesettings", "config-jogo"), ("sstates", "save")):
            for p in sorted((P / sub).glob(f"{serial}*")) if (P / sub).is_dir() else []:
                m.add(p, cat, f"{{EMU}}/{sub}/{p.name}")
                crcs |= set(re.findall(r"[0-9A-Fa-f]{8}", p.stem.replace(serial, "")))
    for crc in crcs:
        for sub in ("cheats", "patches", "cheats_ws"):
            for p in sorted((P / sub).glob(f"{crc}*.pnach")) if (P / sub).is_dir() else []:
                m.add(p, "mods", f"{{EMU}}/{sub}/{p.name}")
    m.excluir(P / "cache", "cache de shader/lista de jogos: o PC recria")


def _emu_retroarch(m: Manifesto, home: Path, stem: str) -> None:
    R = _primeiro(home / ".var/app/org.libretro.RetroArch/config/retroarch", home / ".config/retroarch")
    if not R:
        m.avisos.append("pasta do RetroArch não encontrada")
        return
    m.info["dados_emulador"] = {"dados": str(R)}
    m.troca(R, "{EMU}")
    m.add(R / "retroarch.cfg", "config-global", "{EMU}/retroarch.cfg")
    m.notas.append("RetroArch: o retroarch.cfg do Linux NÃO substitui o do PC (caminhos e drivers diferentes); vai como "
                   "referência. Saves, estados e ajustes do jogo são instalados.")
    for sub in ("config", "remaps"):
        for p in sorted((R / sub).glob(f"*/{stem}.*")) if (R / sub).is_dir() else []:
            m.add(p, "config-jogo", f"{{EMU}}/{sub}/{p.parent.name}/{p.name}")
    saves = []
    for chave, padrao, destino in (("savefile_directory", "saves", "saves"), ("savestate_directory", "states", "states")):
        d = _cfg_valor(R / "retroarch.cfg", chave)
        d = Path(d.replace("~", str(home), 1)) if d and d != "default" else R / padrao
        m.troca(d, f"{{EMU}}/{destino}")
        for p in sorted(d.rglob(f"{stem}.*")) if d.is_dir() else []:
            if p.is_file():
                m.add(p, "save", f"{{EMU}}/{destino}/{p.relative_to(d).as_posix()}")
                saves.append(str(p))
    m.info["saves"] = saves
    m.notas.append("Núcleos do RetroArch (.so) são do Linux: no Windows baixe os mesmos núcleos (.dll) pelo próprio RetroArch.")


def _ini_valor(p: Path, chave: str) -> str | None:
    try:
        for ln in p.read_text("utf-8", errors="replace").splitlines():
            k, _, v = ln.partition("=")
            if k.strip() == chave and v.strip():
                return v.strip()
    except OSError:
        pass
    return None


def _cfg_valor(p: Path, chave: str) -> str | None:
    v = _ini_valor(p, chave)
    return v.strip('"') if v else None


# ------------------------------------------------------------------ preparar -----------
def preparar(game_id: str, home=None, launch_map: dict | None = None, com_hash: bool = True,
             cache: Path | str | None | bool = True) -> dict:
    """Manifesto do jogo. Só lê o Deck. `cache`: True = cache padrão, None/False = sem cache, ou um caminho."""
    home = _home(home)
    lm = launch_map if launch_map is not None else carregar_mapa(home)
    if game_id not in lm:
        raise KeyError(f"jogo não está na biblioteca: {game_id}")
    e = lm[game_id]
    console, rom = e.get("console", ""), Path(e["rom"])
    if not rom.exists():
        raise FileNotFoundError(f"arquivo do jogo não existe: {rom} (SD fora?)")
    emu = EMU_DO_CONSOLE.get(console) or ("retroarch" if console in RA_CONSOLES else console)
    m = Manifesto(game_id, e, emu)
    ryu = _primeiro(home / ".config/Ryujinx", home / ".var/app/io.github.ryubing.Ryujinx/config/Ryujinx")

    if console == "switch2":
        _jogo_switch2(m, rom)
        _emu_lichii(m, home)
    elif console == "switch":
        _jogo_switch(m, rom, home, ryu)
        _emu_ryujinx(m, home, ryu)
    else:
        _jogo_generico(m, rom, console)
        if console in ("psx", "ps2"):
            jogos = [Path(a["origem"]) for a in m.arquivos.values() if a["categoria"] == "jogo"]
            serial = serial_disco(rom, jogos)
            m.info["serial"] = serial
            if console == "psx":
                _emu_duckstation(m, home, serial, rom.stem)
            else:
                _emu_pcsx2(m, home, serial)
        elif emu == "retroarch":
            _emu_retroarch(m, home, rom.stem)
        else:
            m.avisos.append(f"config do emulador de {console} ainda não entra na transferência (só o jogo)")

    b = _binario(home, console, emu)
    if b:
        if b.is_file() and b.parent.name == "publish":  # Ryujinx sem AppImage: a pasta inteira
            m.add_arvore(b.parent, "emulador-linux", f"{{LINUX}}/{emu}/publish")
        else:
            m.add(b, "emulador-linux", f"{{LINUX}}/{emu}/{b.name}")

    for a in m.arquivos.values():
        if a["reescrever"] is None:
            p = Path(a["origem"])
            a["reescrever"] = (p.suffix.lower() in TEXTO_EXTS and a["categoria"].startswith("config")
                               and _tem_caminho_do_deck(p, m.trocas))

    # stat + hash
    hc = None
    if com_hash:
        cpath = (_data_dir(home) / "transferir-hash-cache.json") if cache is True else (Path(cache) if cache else None)
        cpath = Path(os.environ["DC_TRANSFER_CACHE"]) if os.environ.get("DC_TRANSFER_CACHE") and cache is True else cpath
        hc = HashCache(cpath)
    arquivos = []
    for a in m.arquivos.values():
        p = Path(a["origem"])
        try:
            st = p.stat()
            a["tamanho"], a["mtime"] = st.st_size, int(st.st_mtime)
            a["sha256"] = hc.sha256(p, st) if hc else None
        except OSError as ex:
            m.excluidos.append({"caminho": str(p), "motivo": f"não deu para ler: {ex}"})
            continue
        arquivos.append(a)
    if hc:
        hc.salvar()

    resumo: dict[str, dict] = {}
    for a in arquivos:
        r = resumo.setdefault(a["categoria"], {"arquivos": 0, "bytes": 0})
        r["arquivos"] += 1
        r["bytes"] += a["tamanho"]
    m.notas.append("Cache de shader não vai: é compilado para a GPU/driver/sistema do Deck e não serve no PC; "
                   "o emulador do PC recompila (os primeiros minutos podem engasgar).")
    m.notas.append("Keys/firmware/BIOS vão junto (categoria keys): são do próprio usuário, tiradas do console dele, "
                   "e o emulador do PC precisa delas.")
    m.notas.append("Controles: o mapeamento vai, mas o controle do Deck tem outro ID no PC; se não responder, escolha o "
                   "controle do PC em Configurar > Controles (os botões já vêm mapeados).")
    return {
        "versao": VERSAO, "game_id": game_id, "titulo": e.get("title", game_id), "console": console,
        "emulador": emu, "emulador_windows": EMU_WINDOWS.get(emu, {}), "gerado_em": int(time.time()),
        "title_id": m.info.get("title_id"), "serial": m.info.get("serial"),
        "dados_emulador": m.info.get("dados_emulador", {}), "saves": m.info.get("saves", []),
        "saves_ryujinx": m.info.get("saves_ryujinx", []),
        "total_bytes": sum(a["tamanho"] for a in arquivos), "resumo": resumo,
        "reescrever": [{"de": k, "para": v} for k, v in sorted(m.trocas.items(), key=lambda kv: -len(kv[0]))],
        "avisos": m.avisos, "notas": m.notas, "excluidos": m.excluidos, "arquivos": arquivos,
    }


# ------------------------------------------------------------------ saída --------------
def gb(n: int) -> str:
    return f"{n / 1e9:.2f} GB" if n >= 1e8 else f"{n / 1e6:.1f} MB"


def texto_resumo(man: dict) -> str:
    linhas = [f"{man['titulo']} ({man['console']}, emulador {man['emulador']}) — {gb(man['total_bytes'])} "
              f"em {len(man['arquivos'])} arquivos"]
    for c in CATEGORIAS:
        r = man["resumo"].get(c)
        if r:
            linhas.append(f"• {c}: {r['arquivos']} arquivos, {gb(r['bytes'])}")
    if man.get("title_id"):
        linhas.append(f"title id: {man['title_id']}")
    if man.get("saves"):
        linhas.append("saves: " + "; ".join(man["saves"][:3]) + (" …" if len(man["saves"]) > 3 else ""))
    for d, v in (man.get("dados_emulador") or {}).items():
        linhas.append(f"{d} do emulador: {v}")
    ew = man.get("emulador_windows") or {}
    if ew:
        linhas.append(f"no PC instale: {ew['projeto']} — {ew['releases']}")
    if man["excluidos"]:
        linhas.append("não vai: " + "; ".join(f"{x['caminho']} ({x['motivo']})" for x in man["excluidos"][:4]))
    linhas += [f"⚠️ {a}" for a in man["avisos"][:6]]
    return "\n".join(linhas)


def tsv(man: dict) -> str:
    """Formato do script do PC: 1ª linha DCMANIFESTO<TAB>versão<TAB>json(meta); depois uma linha por arquivo:
    F<TAB>sha256<TAB>tamanho<TAB>categoria<TAB>reescrever(0/1)<TAB>destino<TAB>origem"""
    meta = {k: v for k, v in man.items() if k != "arquivos"}
    out = [f"DCMANIFESTO\t{VERSAO}\t{json.dumps(meta, ensure_ascii=True)}"]
    for a in man["arquivos"]:
        out.append("\t".join(["F", a["sha256"] or "-", str(a["tamanho"]), a["categoria"],
                              "1" if a["reescrever"] else "0", a["destino"], a["origem"]]))
    return "\n".join(out) + "\n"


def comando_transferir(bot, args: list[str]) -> str:
    """/transferir <jogo> no bot: o que vai, tamanho, e o comando para rodar no PC (sem calcular hash)."""
    if not args:
        return ("Uso: /transferir <jogo> — prepara a cópia do jogo + emulador + config + saves para o PC.\n"
                "No PC rode: " + COMANDO_PC.format(gid="<jogo>"))
    from .remove import find
    lm = bot._map()
    hits = find(lm, " ".join(args))
    if not hits:
        return "Não achei esse jogo na biblioteca."
    if len(hits) > 1:
        return "Achei mais de um:\n" + "\n".join(f"• {lm[g]['title']} ({lm[g]['console']}) → {g}" for g in hits[:10])
    gid = hits[0]
    try:
        man = preparar(gid, launch_map=lm, com_hash=False)
    except (KeyError, OSError) as ex:
        return f"Não deu para preparar: {ex}"
    return (texto_resumo(man) + "\n\nNo PC (Windows), na pasta do Deck Commander, rode:\n"
            + COMANDO_PC.format(gid=gid)
            + "\n(copia com conferência sha256, retoma se cair, faz backup da config do PC antes de sobrescrever; "
              "nada é apagado no Deck)")


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not argv or argv[0] not in ("manifesto", "resumo", "lista"):
        print("uso: python3 -m dc.transferir manifesto <jogo> [--tsv] [--sem-hash] [--sem-cache] | resumo <jogo> | lista",
              file=sys.stderr)
        return 2
    if argv[0] == "lista":
        for g, e in sorted(carregar_mapa().items(), key=lambda kv: kv[1].get("title", "")):
            print(f"{g}\t{e.get('title', g)}\t{e.get('console', '')}")
        return 0
    if len(argv) < 2:
        print("falta o id do jogo", file=sys.stderr)
        return 2
    flags = set(argv[2:])
    try:
        man = preparar(argv[1], com_hash=argv[0] == "manifesto" and "--sem-hash" not in flags,
                       cache=None if "--sem-cache" in flags else True)
    except (KeyError, FileNotFoundError) as ex:
        print(f"ERRO: {ex}", file=sys.stderr)
        return 1
    if argv[0] == "resumo":
        print(texto_resumo(man))
    elif "--tsv" in flags:
        sys.stdout.write(tsv(man))
    else:
        print(json.dumps(man, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
