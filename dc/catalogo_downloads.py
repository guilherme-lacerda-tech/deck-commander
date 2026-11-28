"""Catálogo de ROMs distribuíveis, download verificado e publicação persistente.

O catálogo do proprietário em config/download-catalog.json complementa o catálogo
incluído no programa. Cada entrada fixa plataforma, tamanho e SHA-256. Downloads
rodam num processo separado, recuperável pelo serviço de energia após reinícios.
"""
from __future__ import annotations

import hashlib
from http.client import IncompleteRead
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from . import ops, syncer
from .emulators import CONSOLES
from .lock import LockTimeout, OperationLock, lock_is_held
from .paths import get_paths
from .store import Store
from .worker import log_operation

TYPE = "catalog-download"
MAX_SIZE = 64 * 1024**3
DEFAULT_CATALOG = Path(__file__).resolve().parents[1] / "config/download-catalog.json"


def _key(text):
    text = unicodedata.normalize("NFKD", text).casefold()
    return " ".join(re.findall(r"[a-z0-9]+", text))


def _validate(item):
    item = dict(item)
    for key in ("id", "titulo", "filename", "console", "url", "sha256", "license", "source_url"):
        if not isinstance(item.get(key), str) or not item[key].strip():
            raise ValueError("catálogo incompleto")
    if not re.fullmatch(r"[a-z0-9-]{1,100}", item["id"]):
        raise ValueError("identificador de catálogo inválido")
    for key in ("titulo", "filename"):
        if any(c in item[key] for c in '<>:"/\\|?*') or any(ord(c) < 32 for c in item[key]) or item[key] in (".", "..") or item[key].rstrip(". ") != item[key]:
            raise ValueError("nome de arquivo inválido no catálogo")
    spec = CONSOLES.get(item["console"], {})
    ext = Path(item["filename"]).suffix.lower()
    if not spec or ext not in spec["exts"] or ext in (".zip", ".7z", ".rar"):
        raise ValueError("catálogo direto exige arquivo de jogo descompactado")
    u = urllib.parse.urlsplit(item["url"])
    if u.scheme != "https" or not u.hostname or u.username or u.password:
        raise ValueError("download exige HTTPS sem credenciais no endereço")
    if not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]):
        raise ValueError("SHA-256 inválido no catálogo")
    if type(item.get("size")) is not int or not 0 < item["size"] <= MAX_SIZE:
        raise ValueError("tamanho inválido no catálogo")
    if item.get("archive_member"):
        member = item["archive_member"]
        if not isinstance(member, str) or member.startswith("/") or "\\" in member or ":" in member or ".." in member.split("/"):
            raise ValueError("membro ZIP inválido no catálogo")
        if not re.fullmatch(r"[0-9a-f]{64}", item.get("file_sha256", "")):
            raise ValueError("SHA-256 do membro ZIP ausente")
        if type(item.get("file_size")) is not int or not 0 < item["file_size"] <= MAX_SIZE:
            raise ValueError("tamanho do membro ZIP inválido")
    aliases = item.get("aliases", [])
    if not isinstance(aliases, list) or not all(isinstance(a, str) for a in aliases):
        raise ValueError("aliases inválidos no catálogo")
    return item


def pesquisar(paths, titulo, console=None):
    entries = {}
    for file in (DEFAULT_CATALOG, paths.config / "download-catalog.json"):
        if not file.exists():
            continue
        data = json.loads(file.read_text("utf-8"))
        if data.get("version") != 1 or not isinstance(data.get("games"), list):
            raise ValueError("versão de catálogo incompatível")
        for entry in data["games"]:
            entry = _validate(entry)
            entries[entry["id"]] = entry
    key = _key(titulo)
    return [entry for entry in entries.values()
            if (not console or entry["console"] == console)
            and key in {_key(name) for name in [entry["titulo"], *entry.get("aliases", [])]}]


def _digest(file):
    with file.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _file_hash(item):
    return item.get("file_sha256", item["sha256"])


def agendar(paths, store, item, chat=None):
    if ops.in_safe_mode(paths):
        raise RuntimeError("Safe-mode ativo")
    item = _validate(item)
    # Serializa a verificação e inclusão para pedidos simultâneos do mesmo jogo.
    with OperationLock(paths.state / "catalog-enqueue.lock", "enqueue", TYPE, timeout=10):
        rows = store.conn.execute("SELECT id, params, state, result FROM operations WHERE type=? ORDER BY seq DESC", (TYPE,))
        for row in rows:
            previous = json.loads(row["params"])["item"]
            if (previous["console"], _file_hash(previous)) != (item["console"], _file_hash(item)):
                continue
            if row["state"] in ("pending", "running"):
                iniciar(paths)
                return row["id"]
            if row["state"] in ("failed", "interrupted"):
                store.retry(row["id"])
                iniciar(paths)
                return row["id"]
            result = json.loads(row["result"] or "{}")
            files = result.get("files", [])
            if row["state"] == "done" and files and all(Path(f).is_file() and _digest(Path(f)) == _file_hash(item) for f in files):
                return row["id"]
        op_id = store.enqueue(TYPE, {"item": item, "chat": chat})
    iniciar(paths)
    return op_id


def iniciar(paths):
    """Desacopla rede do bot e do monitor de energia. O filho abre seu SQLite."""
    if lock_is_held(paths.state / "catalog-worker.lock"):
        return
    env = dict(os.environ)
    # DC_ROOT explícito mantém filho e pai no mesmo perfil de teste ou instalação.
    if not os.environ.get("DC_ROOT") and paths != get_paths():
        env["DC_ROOT"] = str(paths.config.parent.parent)
    with (paths.logs / "catalog-worker.log").open("ab") as output:
        options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
        subprocess.Popen([sys.executable, "-m", "dc.catalogo_downloads", "--run"],
                         cwd=Path(__file__).resolve().parents[1], env=env,
                         stdin=subprocess.DEVNULL, stdout=output, stderr=output, **options)


def _download(paths, item):
    directory = paths.data / "catalog-downloads" / item["sha256"]
    directory.mkdir(parents=True, exist_ok=True)
    if directory.is_symlink() or directory.parent.is_symlink():
        raise ValueError("diretório de download contém link simbólico")
    target = directory / (item["filename"] + ".zip" if item.get("archive_member") else item["filename"])
    if target.is_symlink():
        raise ValueError("destino de download contém link simbólico")
    if target.exists():
        if target.stat().st_size == item["size"] and _digest(target) == item["sha256"]:
            return target
        raise ValueError("cache existente diverge do hash esperado")
    partial = target.with_name(target.name + ".part")
    if partial.is_symlink():
        raise ValueError("arquivo de retomada contém link simbólico")
    offset = partial.stat().st_size if partial.exists() else 0
    if offset > item["size"]:
        raise ValueError("arquivo de retomada excede o tamanho esperado")
    if offset == item["size"]:
        if _digest(partial) == item["sha256"]:
            partial.replace(target)
            return target
        partial.unlink()
        offset = 0
    if shutil.disk_usage(directory).free < item["size"] - offset + 16 * 1024**2:
        raise OSError("espaço insuficiente para download")
    headers = {"User-Agent": "DeckCommander/1", "Accept-Encoding": "identity"}
    if offset:
        headers["Range"] = f"bytes={offset}-"
    request = urllib.request.Request(item["url"], headers=headers)
    # O worker mantém catalog-worker.lock durante a transferência e a publicação.
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(partial, flags, 0o600)
    try:
        with os.fdopen(fd, "r+b") as output, urllib.request.urlopen(request, timeout=30) as response:
            if urllib.parse.urlsplit(response.geturl()).scheme != "https":
                raise ValueError("download redirecionado para conexão insegura")
            status = getattr(response, "status", 200)
            metadata = getattr(response, "headers", {})
            if metadata.get("Content-Encoding", "identity") != "identity":
                raise ValueError("codificação inesperada no download")
            if status == 206:
                expected = f"bytes {offset}-{item['size'] - 1}/{item['size']}"
                if metadata.get("Content-Range") != expected:
                    raise ValueError("resposta de retomada não corresponde ao intervalo solicitado")
            elif status == 200:
                # Servidor sem Range devolve o arquivo completo, recomeça nesse caso.
                offset = 0
                output.truncate(0)
            else:
                raise ValueError("resposta inesperada no download")
            output.seek(offset)
            total = offset
            while block := response.read(1024 * 1024):
                total += len(block)
                if total > item["size"]:
                    raise ValueError("download excede tamanho do catálogo")
                output.write(block)
                output.flush()
            os.fsync(output.fileno())
        if total < item["size"]:
            raise ConnectionError("download interrompido, bytes recebidos preservados")
        if _digest(partial) != item["sha256"]:
            raise ValueError("download não corresponde ao SHA-256 do catálogo")
        partial.replace(target)
        return target
    except IncompleteRead as exc:
        raise ConnectionError("download interrompido, bytes recebidos preservados") from exc
    except ValueError:
        # Bytes incompatíveis nunca participam da próxima tentativa.
        partial.unlink(missing_ok=True)
        raise


def _payload(source, item):
    """Extrai somente o membro catalogado, sem confiar nos caminhos do ZIP."""
    if not item.get("archive_member"):
        return source
    target = source.parent / item["filename"]
    if target.is_symlink():
        raise ValueError("destino de extração contém link simbólico")
    if target.exists():
        if target.stat().st_size == item["file_size"] and _digest(target) == _file_hash(item):
            return target
        raise ValueError("membro extraído diverge do catálogo")
    if shutil.disk_usage(source.parent).free < item["file_size"] + 16 * 1024**2:
        raise OSError("espaço insuficiente para extrair jogo")
    fd, name = tempfile.mkstemp(prefix="extract-", suffix=".part", dir=source.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as output, zipfile.ZipFile(source) as archive:
            entry = archive.getinfo(item["archive_member"])
            if entry.is_dir() or entry.file_size != item["file_size"]:
                raise ValueError("tamanho do membro ZIP divergente")
            total = 0
            with archive.open(entry) as incoming:
                while block := incoming.read(1024 * 1024):
                    total += len(block)
                    if total > item["file_size"]:
                        raise ValueError("membro ZIP excede limite")
                    output.write(block)
            output.flush()
            os.fsync(output.fileno())
        if total != item["file_size"] or _digest(temporary) != _file_hash(item):
            raise ValueError("SHA-256 do membro ZIP divergente")
        temporary.replace(target)
        return target
    finally:
        temporary.unlink(missing_ok=True)


def _install(paths, store, op, source):
    item = op.params["item"]
    root = Path(syncer._cfg(paths)["roms_root"]).expanduser().resolve()
    destination = root / item["console"] / item["titulo"] / item["filename"]
    for part in (destination.parent.parent, destination.parent, destination):
        if part.is_symlink():
            raise ValueError("destino de instalação contém link simbólico")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if _digest(destination) != _file_hash(item):
            raise FileExistsError("arquivo existente diferente, preservado")
    else:
        # Publicação por link é atômica e falha se outra operação criou o destino.
        fd, name = tempfile.mkstemp(prefix=".dc-", suffix=".part", dir=destination.parent)
        temporary = Path(name)
        try:
            with os.fdopen(fd, "wb") as output, source.open("rb") as incoming:
                shutil.copyfileobj(incoming, output)
                output.flush()
                os.fsync(output.fileno())
            os.link(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
    stat = destination.stat()
    with store.tx(critical=True) as db:
        db.execute("INSERT OR IGNORE INTO content_hashes(sha256,size,first_seen_at) VALUES(?,?,?)",
                   (_file_hash(item), stat.st_size, datetime.now(timezone.utc).isoformat()))
        db.execute("INSERT INTO files(path,size,mtime,sha256,origin,origin_ref,origin_note,integrity) "
                   "VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET sha256=excluded.sha256,integrity=excluded.integrity",
                   (str(destination), stat.st_size, stat.st_mtime, _file_hash(item), "import", item["id"], item["source_url"], "verified"))
    return destination


def _defer(store, op_id, result):
    with store.tx(critical=True) as db:
        db.execute("UPDATE operations SET state='pending',result=?,finished_at=? WHERE id=? AND state='running'",
                   (json.dumps(result), datetime.now(timezone.utc).isoformat(), op_id))


def executar(paths, store, op):
    """Baixa e instala primeiro, publica no Steam quando o ambiente está pronto."""
    item = _validate(op.params["item"])
    source = _payload(_download(paths, item), item)
    if item["console"] == "doom":
        from .setup import install_doom_data
        install_doom_data([])
    with OperationLock(paths.lock, op.id, TYPE, is_running=store.is_running):
        destination = _install(paths, store, op, source)
        result = {"files": [str(destination)], "sha256": _file_hash(item), "shortcuts": []}
        if ops.game_running():
            result.update(phase="waiting_game", message=f"{item['titulo']} baixado e verificado. A biblioteca será atualizada ao fechar o jogo.")
            _defer(store, op.id, result)
            return result
        try:
            syncer.shortcuts_path()
        except FileNotFoundError:
            from . import biblioteca, library
            games, _ = library.scan(syncer.rom_roots())
            games, _ = biblioteca.permitidos(paths, games, store)
            library.write_launcher(Path.home(), Path(__file__).resolve().parents[1])
            library.write_map(paths.data / "launch-map.json", games)
            result.update(phase="waiting_steam", message=f"{item['titulo']} baixado e instalado. Aguardando o primeiro login da Steam para criar o atalho.")
            _defer(store, op.id, result)
            return result
        result["shortcuts"] = syncer.add_to_steam(paths, store, op.id)
        result.update(phase="installed", message=f"{item['titulo']} instalado e publicado na biblioteca.")
    from . import romm_queue
    romm_queue.published(paths, [str(destination)])
    from .traducao import run as translation
    launch_map = json.loads((paths.data / "launch-map.json").read_text("utf-8"))
    game_ids = [gid for gid, game in launch_map.items() if game.get("rom") == str(destination)]
    result["translation"] = translation.auto_queue(paths, store, game_ids)
    return result


def run_pending(paths, store):
    """Uma rodada exclusiva recupera tarefas próprias e processa a fila em ordem."""
    if ops.in_safe_mode(paths):
        return []
    completed = []
    try:
        with OperationLock(paths.state / "catalog-worker.lock", "catalog-worker", TYPE, timeout=0):
            with store.tx(critical=True) as db:
                db.execute("UPDATE operations SET state='pending' WHERE type=? AND state IN ('running','interrupted')", (TYPE,))
            rows = store.conn.execute("SELECT id FROM operations WHERE type=? AND state='pending' ORDER BY seq", (TYPE,)).fetchall()
            for row in rows:
                before = store.get(row[0])
                if before.finished_at and (datetime.now(timezone.utc) - datetime.fromisoformat(before.finished_at)).total_seconds() < 60:
                    continue
                op = store.claim(row[0])
                if op is None:
                    continue
                log_operation(paths, {"op": op.id, "type": TYPE, "event": "start"})
                try:
                    result = executar(paths, store, op)
                    store.finish(op.id, True, result=result)
                    log_operation(paths, {"op": op.id, "type": TYPE, "event": result["phase"]})
                except Exception as exc:
                    # URL e credenciais eventualmente contidas em erros de rede ficam fora do log.
                    error = f"Falha de download ou instalação ({type(exc).__name__})"
                    if isinstance(exc, OSError) and not isinstance(exc, FileExistsError) and op.attempts < 3:
                        _defer(store, op.id, {"phase": "retry", "message": error + ". Nova tentativa automática em um minuto."})
                    else:
                        store.finish(op.id, False, error=error)
                    log_operation(paths, {"op": op.id, "type": TYPE, "event": "failed", "error": error})
                completed.append(op.id)
    except LockTimeout:
        pass
    return completed


if __name__ == "__main__":
    if sys.argv[1:] != ["--run"]:
        raise SystemExit("Uso: python -m dc.catalogo_downloads --run")
    paths = get_paths().ensure()
    store = Store(paths.db)
    try:
        run_pending(paths, store)
    finally:
        store.close()
