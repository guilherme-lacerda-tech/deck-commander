"""Valida o handler do bot, download HTTPS e instalação com dados reais na VM.

Execute com --root apontando para um perfil exclusivo de validação.
A autenticação e o transporte públicos do Telegram têm verificação própria.
"""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dc.bot import Bot
from dc.paths import get_paths
from dc import catalogo_downloads


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("titles", nargs="+")
    args = parser.parse_args()
    os.environ["DC_ROOT"] = str(args.root.resolve())
    paths = get_paths().ensure()
    bot = Bot(paths, "local-validation")
    bot.cfg["allowed"] = [1]
    report = []
    try:
        for title in args.titles:
            response = bot.handle_message({"from": {"id": 1}, "chat": {"id": 1}, "text": title})
            print(response, flush=True)
            matches = catalogo_downloads.pesquisar(paths, title)
            assert len(matches) == 1, f"catálogo ambíguo para {title}"
            item = matches[0]
            deadline = time.monotonic() + args.timeout
            while time.monotonic() < deadline:
                operations = [op for op in bot.store.list(limit=200)
                              if op.type == catalogo_downloads.TYPE
                              and op.params["item"]["id"] == item["id"]]
                if operations:
                    operation = operations[0]
                    if operation.state == "failed":
                        raise RuntimeError(operation.error)
                    result = json.loads(operation.result or "{}")
                    if result.get("phase") in ("installed", "waiting_steam", "waiting_game"):
                        break
                time.sleep(1)
            else:
                raise TimeoutError(f"aquisição de {title}")
            files = [Path(file) for file in result["files"]]
            expected = item.get("file_sha256", item["sha256"])
            assert files and all(file.is_file() for file in files)
            for file in files:
                with file.open("rb") as stream:
                    assert hashlib.file_digest(stream, "sha256").hexdigest() == expected
            launch_map = json.loads((paths.data / "launch-map.json").read_text("utf-8"))
            ids = [gid for gid, game in launch_map.items() if game.get("rom") in result["files"]]
            assert ids, "jogo baixado ausente no mapa de lançamento"
            repeated = bot.handle_message({"from": {"id": 1}, "chat": {"id": 1}, "text": title})
            after = [op.id for op in bot.store.list(limit=200)
                     if op.type == catalogo_downloads.TYPE and op.params["item"]["id"] == item["id"]]
            assert after == [operation.id], "pedido repetido duplicou a operação"
            report.append({"title": title, "operation": operation.id, "phase": result["phase"],
                           "files": result["files"], "sha256": expected, "game_ids": ids,
                           "repeat_response": repeated})
        output = args.root / "name-download-result.json"
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    finally:
        bot.search_pool.shutdown(wait=True)
        bot.store.close()


if __name__ == "__main__":
    main()
