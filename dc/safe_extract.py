"""M4.6 / S10 — Extração protegida de ZIP (ZIP Slip + archive bomb).

Valida ANTES de extrair (nomes, symlinks, profundidade, colisões, contagem, tamanho,
proporção) e DURANTE (bytes reais — o cabeçalho pode mentir). Extrai numa pasta
temporária ao lado do destino; só no fim faz rename atômico. Cancelável sem deixar
biblioteca parcial. Suspeita -> UnsafeArchive (o chamador manda para quarentena).
RAR fica fora deste spike (exige unrar; mesma política deve ser aplicada à listagem).
"""
from __future__ import annotations

import os
import shutil
import stat
import threading
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


class UnsafeArchive(ValueError):
    pass


class NoSpace(OSError):
    """Falta espaço em disco. NÃO é arquivo suspeito: nada vai para a quarentena; tenta de novo depois."""


class ExtractionCancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class Limits:
    max_total_bytes: int = 64 * 1024**3   # 64 GiB expandido
    max_files: int = 5000
    max_depth: int = 12
    max_ratio: float = 200.0              # descomprimido / comprimido por entrada
    min_ratio_check_bytes: int = 1 << 20  # só checa proporção acima de 1 MiB
    free_space_margin: float = 1.05


def _check_name(name: str, limits: Limits) -> PurePosixPath:
    if "\x00" in name:
        raise UnsafeArchive(f"nome com byte nulo: {name!r}")
    n = name.replace("\\", "/")
    if n.startswith("/") or (len(n) > 1 and n[1] == ":"):
        raise UnsafeArchive(f"caminho absoluto: {name}")
    p = PurePosixPath(n)
    if any(part == ".." for part in p.parts):
        raise UnsafeArchive(f"ZIP Slip (..): {name}")
    if len(p.parts) > limits.max_depth:
        raise UnsafeArchive(f"profundidade {len(p.parts)} > {limits.max_depth}: {name}")
    return p


def inspect(archive: Path, limits: Limits = Limits()) -> list[zipfile.ZipInfo]:
    """Valida o índice do ZIP. Retorna as entradas de arquivo (sem diretórios)."""
    try:
        zf = zipfile.ZipFile(archive)
    except zipfile.BadZipFile as e:
        raise UnsafeArchive(f"ZIP inválido: {e}") from e
    with zf:
        infos = zf.infolist()
    if len(infos) > limits.max_files:
        raise UnsafeArchive(f"{len(infos)} entradas > limite {limits.max_files}")
    seen: set[str] = set()
    total = 0
    files = []
    for i in infos:
        p = _check_name(i.filename, limits)
        mode = i.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise UnsafeArchive(f"link simbólico no arquivo: {i.filename}")
        if stat.S_IFMT(mode) and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
            raise UnsafeArchive(f"tipo de arquivo especial: {i.filename}")
        key = str(p).casefold().rstrip("/")
        if key in seen:
            raise UnsafeArchive(f"colisão de nomes: {i.filename}")
        seen.add(key)
        if i.is_dir():
            continue
        total += i.file_size
        if total > limits.max_total_bytes:
            raise UnsafeArchive(f"expansão total > {limits.max_total_bytes} B")
        if i.file_size >= limits.min_ratio_check_bytes:
            ratio = i.file_size / max(i.compress_size, 1)
            if ratio > limits.max_ratio:
                raise UnsafeArchive(f"proporção de compressão {ratio:.0f}:1 > {limits.max_ratio:.0f}:1 "
                                    f"(possível bomb): {i.filename}")
        files.append(i)
    # um arquivo não pode ser também prefixo-diretório de outro (a/b e a/b/c)
    names = {str(_check_name(f.filename, limits)).casefold() for f in files}
    for n in names:
        parts = n.split("/")
        for k in range(1, len(parts)):
            if "/".join(parts[:k]) in names:
                raise UnsafeArchive(f"colisão arquivo/diretório: {n}")
    return files


def extract(archive: Path, dest: Path, limits: Limits = Limits(),
            cancel: threading.Event | None = None, chunk: int = 1 << 20) -> list[Path]:
    archive, dest = Path(archive), Path(dest)
    if dest.exists():
        raise FileExistsError(f"destino já existe: {dest}")
    files = inspect(archive, limits)
    declared = sum(i.file_size for i in files)
    dest.parent.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(dest.parent).free
    if free < declared * limits.free_space_margin:
        raise NoSpace(f"espaço insuficiente: precisa {declared / 1e9:.1f} GB, livre {free / 1e9:.1f} GB")

    tmp = dest.parent / f".dc-extract-{uuid.uuid4().hex[:8]}"
    tmp.mkdir()
    written = 0
    try:
        with zipfile.ZipFile(archive) as zf:
            for i in files:
                rel = _check_name(i.filename, limits)
                out = tmp.joinpath(*rel.parts)
                if os.path.commonpath([tmp.resolve(), out.resolve()]) != str(tmp.resolve()):
                    raise UnsafeArchive(f"ZIP Slip após resolução: {i.filename}")
                out.parent.mkdir(parents=True, exist_ok=True)
                entry_written = 0
                with zf.open(i) as src, open(out, "xb") as dst:
                    while True:
                        if cancel is not None and cancel.is_set():
                            raise ExtractionCancelled("extração cancelada")
                        buf = src.read(chunk)
                        if not buf:
                            break
                        entry_written += len(buf)
                        written += len(buf)
                        if entry_written > i.file_size or written > limits.max_total_bytes:
                            raise UnsafeArchive(f"bytes reais excedem o declarado: {i.filename}")
                        dst.write(buf)
        os.replace(tmp, dest)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return [dest.joinpath(*_check_name(i.filename, limits).parts) for i in files]


# ---------------------------------------------------------------- .7z / .rar (7-Zip do SteamOS)
SEVEN_ZIP = "7z"


def list_external(archive: Path) -> list[dict]:
    """Lista o arquivo com `7z l -slt` (lê .7z e .rar) sem extrair nada."""
    import subprocess
    try:
        r = subprocess.run([SEVEN_ZIP, "l", "-slt", "-ba", "-p", str(archive)], capture_output=True, text=True, timeout=120)
    except FileNotFoundError as e:
        raise UnsafeArchive("7-Zip não encontrado (o SteamOS normalmente traz /usr/bin/7z)") from e
    if r.returncode != 0:
        raise UnsafeArchive(f"arquivo inválido ou protegido por senha: {r.stderr.strip()[-200:]}")
    entries, cur = [], {}
    for line in r.stdout.splitlines() + [""]:
        if not line.strip():
            if cur.get("Path"):
                entries.append(cur)
            cur = {}
            continue
        k, sep, v = line.partition(" = ")
        if sep:
            cur[k.strip()] = v
    return entries


def inspect_external(archive: Path, limits: Limits = Limits()) -> list[dict]:
    import re as _re
    entries = list_external(archive)
    if len(entries) > limits.max_files:
        raise UnsafeArchive(f"{len(entries)} entradas > limite {limits.max_files}")
    seen, total, files = set(), 0, []
    for e in entries:
        name = e["Path"]
        p = _check_name(name, limits)
        attrs = e.get("Attributes", "")
        if e.get("Encrypted") == "+":
            raise UnsafeArchive("arquivo protegido por senha")
        if _re.search(r"(^|\s)l[r-][w-][x-]", attrs):
            raise UnsafeArchive(f"link simbólico no arquivo: {name}")
        key = str(p).casefold()
        if key in seen:
            raise UnsafeArchive(f"colisão de nomes: {name}")
        seen.add(key)
        is_dir = "D" in attrs.split(" ")[0] or e.get("Folder") == "+"
        if is_dir:
            continue
        size = int(e.get("Size") or 0)
        total += size
        if total > limits.max_total_bytes:
            raise UnsafeArchive(f"expansão total > {limits.max_total_bytes} B")
        packed = int(e.get("Packed Size") or 0)
        if packed and size >= limits.min_ratio_check_bytes and size / packed > limits.max_ratio:
            raise UnsafeArchive(f"proporção de compressão {size / packed:.0f}:1 (possível bomb): {name}")
        files.append({"path": str(p), "size": size})
    return files


def extract_external(archive: Path, dest: Path, limits: Limits = Limits()) -> list[Path]:
    import subprocess
    archive, dest = Path(archive), Path(dest)
    if dest.exists():
        raise FileExistsError(f"destino já existe: {dest}")
    files = inspect_external(archive, limits)
    declared = sum(f["size"] for f in files)
    dest.parent.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(dest.parent).free
    if free < declared * limits.free_space_margin:
        raise NoSpace(f"espaço insuficiente: precisa {declared / 1e9:.1f} GB, livre {free / 1e9:.1f} GB")
    tmp = dest.parent / f".dc-extract-{uuid.uuid4().hex[:8]}"
    tmp.mkdir()
    try:
        r = subprocess.run([SEVEN_ZIP, "x", "-y", "-bd", "-p", f"-o{tmp}", str(archive)],
                           capture_output=True, text=True, timeout=3600)
        if r.returncode != 0:
            raise UnsafeArchive(f"falha ao extrair: {r.stderr.strip()[-200:]}")
        real_total, out = 0, []
        root = tmp.resolve()
        for f in tmp.rglob("*"):  # confere de novo o que saiu de fato
            if f.is_symlink():
                raise UnsafeArchive(f"link simbólico extraído: {f.name}")
            if os.path.commonpath([root, f.resolve()]) != str(root):
                raise UnsafeArchive(f"arquivo fora da pasta: {f}")
            if f.is_file():
                real_total += f.stat().st_size
                out.append(f)
        if real_total > limits.max_total_bytes:
            raise UnsafeArchive("bytes reais excedem o limite")
        os.replace(tmp, dest)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return sorted(dest / f.relative_to(tmp) for f in out)


def extract_any(archive: Path, dest: Path, limits: Limits = Limits()) -> list[Path]:
    """.zip pelo extrator interno; .7z/.rar pelo 7-Zip do sistema — mesmas regras de segurança."""
    if Path(archive).suffix.lower() == ".zip":
        return extract(archive, dest, limits)
    return extract_external(archive, dest, limits)
