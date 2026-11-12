import shutil
import subprocess
import zipfile
from collections.abc import Callable
from pathlib import Path

PASTAS = {
    "ps2": ".var/app/net.pcsx2.PCSX2/config/PCSX2/textures/{id}/replacements",
    "gc":  ".var/app/org.DolphinEmu.dolphin-emu/data/dolphin-emu/Load/Textures/{id}",
    "wii": ".var/app/org.DolphinEmu.dolphin-emu/data/dolphin-emu/Load/Textures/{id}",
}

def serial_ps2(iso: Path) -> str | None:
    """Extrai o serial do PS2 a partir do arquivo ISO."""
    # (corrigido: a 1ª versão tratava o registro da RAIZ como se fosse o SYSTEM.CNF e nunca achava nada)
    import re
    try:
        with open(iso, "rb") as f:
            f.seek(16 * 2048)
            raiz = f.read(2048)[156:190]
            setor, tam = int.from_bytes(raiz[2:6], "little"), int.from_bytes(raiz[10:14], "little")
            f.seek(setor * 2048)
            d = f.read(min(tam, 1 << 20))
            i = 0
            while i < len(d):
                n = d[i]
                if n == 0:  # resto do setor vazio
                    i = (i // 2048 + 1) * 2048
                    continue
                nome = d[i + 33:i + 33 + d[i + 32]].decode("ascii", "replace")
                if nome.upper() == "SYSTEM.CNF;1":
                    f.seek(int.from_bytes(d[i + 2:i + 6], "little") * 2048)
                    cnf = f.read(int.from_bytes(d[i + 10:i + 14], "little")).decode("ascii", "replace")
                    m = re.search(r"BOOT2\s*=\s*cdrom0:\\+([A-Z]{4})_(\d{3})\.(\d{2})", cnf, re.IGNORECASE)
                    return f"{m.group(1).upper()}-{m.group(2)}{m.group(3)}" if m else None
                i += n
    except OSError:
        pass
    return None

def id_gc(iso: Path) -> str | None:
    """Extrai o ID do GameCube/Wii a partir do arquivo ISO."""
    try:
        with open(iso, "rb") as f:
            magic = f.read(6)
            if not magic.isalnum():
                return None
            return magic.decode('ascii')
    except Exception:
        pass
    return None

def pasta_destino(home: Path, console: str, jogo_id: str) -> Path:
    """Retorna o caminho da pasta de destino para texturas."""
    pasta = PASTAS[console].format(id=jogo_id)
    return home / pasta

def ligar_opcao(home: Path, console: str) -> None:
    """Ativa a opção de carregar texturas no emulador."""
    if console == "ps2":
        ini_path = home / ".var/app/net.pcsx2.PCSX2/config/PCSX2/inis/PCSX2.ini"
        section = "[EmuCore/GS]"
        key1, value1 = "LoadTextureReplacements", "true"
        key2, value2 = "LoadTextureReplacementsAsync", "true"
    elif console in ("gc", "wii"):
        ini_path = home / ".var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu/GFX.ini"
        section = "[Settings]"
        key1, value1 = "HiresTextures", "True"
        key2, value2 = "CacheHiresTextures", "False"
    else:
        raise ValueError("texturas HD só para PS2, GameCube e Wii por enquanto")

    # (corrigido: a 1ª versão RENOMEAVA o arquivo como cópia — sumia com a configuração do emulador)
    import shutil

    from .retro_hacks import ini_definir
    ini_path.parent.mkdir(parents=True, exist_ok=True)
    texto = ini_path.read_text(encoding="utf-8", errors="replace") if ini_path.exists() else ""
    backup = ini_path.with_name(ini_path.name + ".antes-texturas")
    if ini_path.exists() and not backup.exists():
        shutil.copy2(ini_path, backup)
    ini_path.write_text(ini_definir(texto, section.strip("[]"), {key1: value1, key2: value2}), encoding="utf-8")

def _nome_seguro(nome: str) -> bool:
    """Caminho relativo, sem subir pasta (".."), sem raiz nem letra de unidade."""
    n = nome.replace("\\", "/")
    return bool(n) and not n.startswith("/") and ":" not in n.split("/")[0] and ".." not in n.split("/")


def extrair(pacote: Path, destino: Path, run=subprocess.run) -> int:
    """Extrai o pacote para a pasta destino."""
    if pacote.suffix.lower() == ".zip":
        with zipfile.ZipFile(pacote, "r") as zf:
            for member in zf.infolist():
                name = member.filename.replace("\\", "/")
                if member.is_dir() or not _nome_seguro(name):  # revisão 11/11/2026: "pack/" (pasta) quebrava
                    continue
                target = destino / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, open(target, "wb") as f:
                    shutil.copyfileobj(src, f)
    elif pacote.suffix.lower() in (".7z", ".rar"):
        try:  # confere os nomes ANTES de extrair: pacote vindo de link não pode escrever fora da pasta
            lista = run(["7z", "l", "-slt", "-ba", str(pacote)], capture_output=True, text=True, check=True).stdout
            ruins = [l[7:] for l in lista.splitlines() if l.startswith("Path = ") and not _nome_seguro(l[7:])]
            if ruins:
                raise RuntimeError(f"pacote com caminho perigoso ({ruins[0]}) — não extraí")
            run(["7z", "x", "-y", f"-o{destino}", str(pacote)], capture_output=True, check=True)
        except FileNotFoundError:
            raise RuntimeError("7z não instalado no Deck") from None
    else:
        raise ValueError("Formato de pacote não suportado")

    # pacote com uma pasta só por fora ("pack/…"): o conteúdo sobe um nível
    topo = list(destino.iterdir())
    if len(topo) == 1 and topo[0].is_dir():
        sub = topo[0]
        for item in list(sub.iterdir()):
            item.rename(destino / item.name)
        sub.rmdir()
    return sum(1 for f in destino.rglob("*") if f.is_file())

def instalar(home: Path, console: str, rom: Path, url: str, baixar: Callable[[str, Path], None], run=subprocess.run, tmp: Path | None = None) -> str:
    """Instala texturas HD para o jogo especificado."""
    if console == "ps2":
        jogo_id = serial_ps2(rom)
    elif console in ("gc", "wii"):
        jogo_id = id_gc(rom)
    else:
        raise ValueError("texturas HD só para PS2, GameCube e Wii por enquanto")

    if not jogo_id:
        raise ValueError("não consegui ler o código do jogo")

    if tmp is None:
        filename = url.split("/")[-1]
        tmp = home / ".cache/deck-commander/texturas" / filename

    tmp.parent.mkdir(parents=True, exist_ok=True)
    baixar(url, tmp)

    destino = pasta_destino(home, console, jogo_id)
    destino.mkdir(parents=True, exist_ok=True)
    count = extrair(tmp, destino, run)
    ligar_opcao(home, console)
    tmp.unlink()

    return f"🖼️ Texturas HD instaladas: {count} arquivos em {jogo_id}. Vale na próxima vez que abrir o jogo."
