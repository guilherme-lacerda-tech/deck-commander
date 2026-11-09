"""Backend do plugin Deck Commander (roda como o usuário, sem root).

Só lê/escreve dentro de ~/.local/share/deck-commander:
  plugin-queue.json  — jogos esperando virar atalho (gerado pelo /sync)
  plugin-done.json   — resultado (game_id -> appid ou erro), lido pelo Deck Commander
"""
import base64
import json
import os

try:
    import decky
    HOME = decky.DECKY_USER_HOME
except Exception:  # noqa: BLE001
    HOME = os.path.expanduser("~")

BASE = os.path.join(HOME, ".local/share/deck-commander")
QUEUE = os.path.join(BASE, "plugin-queue.json")
DONE = os.path.join(BASE, "plugin-done.json")
ITEMS = os.path.join(BASE, "plugin-items.json")  # escrito pelo Deck Commander e pelo plugin
REMOVE = os.path.join(BASE, "plugin-remove.json")  # pedidos de remoção (/remover no bot)


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


class Plugin:
    async def get_pending(self):
        done = _load(DONE, {})
        return [q for q in _load(QUEUE, []) if q.get("game_id") not in done]

    async def get_done(self):
        items = _load(ITEMS, {})
        return {k: {**v, "item": items.get(k)} for k, v in _load(DONE, {}).items() if not v.get("removed")}

    async def remember_item(self, game_id, item):
        """Guarda o item para a autocorreção poder recriar o atalho se ele sumir."""
        items = _load(ITEMS, {})
        items[game_id] = item
        _save(ITEMS, items)
        return True

    async def report(self, game_id, appid, error):
        done = _load(DONE, {})
        done[game_id] = {"appid": int(appid or 0), "error": error or ""}
        _save(DONE, done)
        if not error:
            _save(QUEUE, [q for q in _load(QUEUE, []) if q.get("game_id") != game_id])
        return True

    async def get_removals(self):
        return _load(REMOVE, [])

    async def removal_done(self, game_id, appid):
        _save(REMOVE, [r for r in _load(REMOVE, []) if not (r.get("game_id") == game_id and r.get("appid") == appid)])
        return await self.mark_removed(game_id)

    async def mark_removed(self, game_id):
        """Atalho removido (pelo /remover ou pelo usuário no Steam): a autocorreção não recria."""
        done = _load(DONE, {})
        done[game_id] = {"appid": 0, "error": "", "removed": True}
        _save(DONE, done)
        items = _load(ITEMS, {})
        if items.pop(game_id, None) is not None:
            _save(ITEMS, items)
        return True

    async def read_art(self, path):
        real = os.path.realpath(path)
        if not real.startswith(os.path.realpath(BASE) + os.sep) or not os.path.isfile(real):
            return None  # só imagens preparadas pelo Deck Commander
        with open(real, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        return {"data": data, "ext": os.path.splitext(real)[1].lstrip(".").lower() or "png"}

    async def get_collections(self):
        """{nome da coleção: [appids]} gerado pelo Deck Commander (consoles, Emuladores, lojas)."""
        return _load(os.path.join(BASE, "collections.json"), {})

    async def set_collection_ids(self, ids):
        path = os.path.join(BASE, "collection-ids.json")
        cur = _load(path, {})
        if cur != ids:
            _save(path, ids)
        return True

    async def get_launch_error(self):
        """Aviso deixado pelo dc-launch quando um jogo não abre (ex.: cartão SD fora). Lido uma vez."""
        path = os.path.join(BASE, "launch-error.json")
        err = _load(path, None)
        if err is None:
            return None
        try:
            os.remove(path)
        except OSError:
            pass
        return err.get("message")

    async def get_status(self):
        done = _load(DONE, {})
        return {"pending": len(await self.get_pending()),
                "added": sum(1 for v in done.values() if v.get("appid")),
                "removed": sum(1 for v in done.values() if v.get("removed")),
                "errors": [k for k, v in done.items() if v.get("error")][-5:]}

    # ---- Painel de desempenho e qualidade -------------------------------------------------------------
    def _dc(self):
        """Carrega o código do Deck Commander (mesmo usuário; ~/deck-commander)."""
        import sys
        os.environ["HOME"] = HOME  # o código do DC acha as configs dos emuladores a partir do HOME
        repo = os.path.join(HOME, "deck-commander")
        if repo not in sys.path:
            sys.path.insert(0, repo)
        from dc import autotune, perf, quality, tuning
        from dc.paths import get_paths
        self.autotune = autotune
        return perf, quality, tuning, get_paths()

    def _game(self, appid=None, game_id=None):
        lm = _load(os.path.join(BASE, "launch-map.json"), {})
        if game_id is None and appid:
            done = _load(DONE, {})
            want = int(appid) & 0xFFFFFFFF
            game_id = next((g for g, v in done.items() if (int(v.get("appid") or 0) & 0xFFFFFFFF) == want), None)
        if game_id is None:  # nenhum jogo aberto: o último medido
            game_id = _load(os.path.join(BASE, "perf-last.json"), {}).get("game_id")
        return game_id, lm.get(game_id or "", {})

    async def panel(self, appid=None):
        perf, quality, tuning, paths = self._dc()
        game_id, g = self._game(appid)
        console = g.get("console")
        out = {"game_id": game_id, "title": g.get("title"), "console": console, "measure": perf.enabled(paths),
               "presets": list(tuning.NAMES), "supported": bool(console and tuning.supported(console))}
        if not game_id:
            return out
        over = quality.get_override(paths, game_id)
        cl = tuning.console_level(console) if out["supported"] else None
        st = self.autotune.load(paths).get(game_id) or {}
        out.update(auto=st.get("fase") != "manual", auto_fase=st.get("fase"), trava_em=st.get("trava_em"),
                   override=over, game_preset=tuning.preset_of(console, over) if over else None,
                   console_level=cl, console_preset=tuning.preset_of(console, cl),
                   levels=[1, 2, 3, 4, 5][:quality.MAX.get(console, 4)],
                   history=[perf.describe(dict(h, title=g.get("title"))) for h in perf.history(paths.state, game_id)[-3:]][::-1])
        return out

    async def set_game_preset(self, game_id, preset=None):
        perf, quality, tuning, paths = self._dc()
        _, g = self._game(game_id=game_id)
        self.autotune.set_manual(paths, game_id, True, g.get("console"))
        return tuning.apply_game(paths, game_id, g.get("console"), preset)

    async def set_game_level(self, game_id, level=None):
        perf, quality, tuning, paths = self._dc()
        _, g = self._game(game_id=game_id)
        self.autotune.set_manual(paths, game_id, True, g.get("console"))
        return quality.set_override(paths, game_id, g.get("console"),
                                    None if level is None else quality.LABEL[int(level)])

    async def set_auto(self, game_id):
        perf, quality, tuning, paths = self._dc()
        _, g = self._game(game_id=game_id)
        self.autotune.set_manual(paths, game_id, False, g.get("console"))
        self.autotune.ensure(paths, game_id, g.get("console"))
        return "automático: a qualidade se ajusta sozinha"

    async def calibrate(self, game_id):
        import subprocess
        unit = "dc-calibra-" + "".join(c for c in game_id if c.isalnum())[:40]
        r = subprocess.run(["systemd-run", "--user", "--collect", f"--unit={unit}",
                            f"--working-directory={os.path.join(HOME, 'deck-commander')}",
                            "python3", "-m", "dc", "x", "calibrar", game_id, "90"], capture_output=True, text=True)
        if r.returncode:
            return "não deu para calibrar agora (já está calibrando?)"
        return "calibrando: o jogo abre e fecha sozinho algumas vezes (~2 min cada). Não mexa no Deck."

    async def set_console_preset(self, console, preset):
        perf, quality, tuning, paths = self._dc()
        return tuning.apply_console(console, preset)

    async def set_measure(self, on):
        perf, quality, tuning, paths = self._dc()
        f = paths.config / "desempenho.json"
        cfg = _load(str(f), {})
        cfg["medir"] = bool(on)
        f.parent.mkdir(parents=True, exist_ok=True)
        _save(str(f), cfg)
        return "medição ligada" if on else "medição desligada"

    async def _main(self):
        os.makedirs(BASE, exist_ok=True)

    async def _unload(self):
        pass
