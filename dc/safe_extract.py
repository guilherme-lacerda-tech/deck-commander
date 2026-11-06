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
from typing import Optional


class UnsafeArchive(ValueError):
    pass


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
            cancel: Optional[threading.Event] = None, chunk: int = 1 << 20) -> list[Path]:
    archive, dest = Path(archive), Path(dest)
    if dest.exists():
        raise FileExistsError(f"destino já existe: {dest}")
    files = inspect(archive, limits)
    declared = sum(i.file_size for i in files)
    dest.parent.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(dest.parent).free
    if free < declared * limits.free_space_margin:
        raise UnsafeArchive(f"espaço insuficiente: precisa {declared} B, livre {free} B")

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
