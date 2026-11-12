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
# tempo-limite por ação do painel (s); as que usam rede ou varrem a biblioteca demoram mais
PAINEL_TEMPO = {"diagnostico": 150, "pc_sincronizar": 150, "transferir_preparar": 150, "pc_acordar": 40, "pc_tv": 150, "espaco_sugestoes": 150, "familia": 40, "familia_atualizar": 60, "familia_puxar": 600, "musica_midia": 40, "musica_playlist": 40, "musica_conectar": 120,
                "telegram_token": 60, "telegram": 30, "telegram_parear": 30, "traducao": 90, "safe_mode": 90}


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _save(path, data):
    tmp = path + ".%d.tmp" % os.getpid()
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _atualizar(path, default, fn):
    """Lê, muda e grava sob a trava `<arquivo>.lock` — a mesma do Deck Commander (dc/plugin_bridge.trava).
    Sem ela, o plugin e o /pc sincronizar ou o /remover gravavam juntos e um apagava a mudança do outro."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".lock", "a") as lk:
        try:
            import fcntl
            fcntl.flock(lk, fcntl.LOCK_EX)
        except ImportError:  # Windows (testes no PC)
            pass
        data = _load(path, default)
        r = fn(data)
        _save(path, data)
        return r


def _versao_codigo(repo):
    """Marca da versão do código em disco: a data mais nova dos .py de dc/ (muda a cada implantação)."""
    mais_novo = 0.0
    for raiz, _pastas, arquivos in os.walk(os.path.join(repo, "dc")):
        for a in arquivos:
            if a.endswith(".py"):
                try:
                    mais_novo = max(mais_novo, os.stat(os.path.join(raiz, a)).st_mtime)
                except OSError:
                    pass
    return mais_novo


class Plugin:
    async def get_pending(self):
        done = _load(DONE, {})
        return [q for q in _load(QUEUE, []) if q.get("game_id") not in done]

    async def get_done(self):
        items = _load(ITEMS, {})
        return {k: {**v, "item": items.get(k)} for k, v in _load(DONE, {}).items() if not v.get("removed")}

    async def remember_item(self, game_id, item):
        """Guarda o item para a autocorreção poder recriar o atalho se ele sumir."""
        _atualizar(ITEMS, {}, lambda items: items.__setitem__(game_id, item))
        return True

    async def report(self, game_id, appid, error):
        # AppID sempre sem sinal (o JS do Steam às vezes entrega com sinal; a remoção compara pelo valor)
        marca = {"appid": int(appid or 0) & 0xFFFFFFFF, "error": error or ""}
        _atualizar(DONE, {}, lambda done: done.__setitem__(game_id, marca))
        if not error:
            _atualizar(QUEUE, [], lambda q: q.__setitem__(slice(None), [x for x in q if x.get("game_id") != game_id]))
        return True

    async def get_removals(self):
        return _load(REMOVE, [])

    async def removal_done(self, game_id, appid):
        want = int(appid or 0) & 0xFFFFFFFF
        _atualizar(REMOVE, [], lambda rq: rq.__setitem__(slice(None), [
            r for r in rq if not (r.get("game_id") == game_id and int(r.get("appid") or 0) & 0xFFFFFFFF == want)]))
        return await self.mark_removed(game_id)

    async def mark_removed(self, game_id):
        """Atalho removido (pelo /remover ou pelo usuário no Steam): a autocorreção não recria."""
        _atualizar(DONE, {}, lambda done: done.__setitem__(game_id, {"appid": 0, "error": "", "removed": True}))
        _atualizar(ITEMS, {}, lambda items: items.pop(game_id, None))
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
        if err.get("title"):  # aviso (ex.: emulador atualizado), não erro: o painel mostra com este título
            return {"title": err["title"], "message": err.get("message")}
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
        # Código atualizado (implantação/git pull) vale na hora: sem isto o painel seguia com a versão carregada
        # quando o Decky ligou até o próximo reinício (revisão de lançamento 12/11/2026).
        versao = _versao_codigo(repo)
        if versao != getattr(self, "_versao_dc", None):
            for nome in [m for m in sys.modules if m == "dc" or m.startswith("dc.")]:
                del sys.modules[nome]
            self._versao_dc = versao
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

    # ---- Interface completa (dc/painel.py) ------------------------------------------------------------
    async def painel(self, acao, args=None):
        """Roda `python3 -m dc.painel <acao>` como o usuário, fora do processo do Decky, com tempo-limite.
        Os parâmetros vão pela entrada padrão (o token do Telegram não aparece na lista de processos)."""
        import asyncio
        import signal
        if not isinstance(acao, str) or not acao.replace("_", "").isalnum():
            return {"ok": False, "erro": "ação inválida"}
        repo = os.environ.get("DC_PAINEL_REPO") or os.path.join(HOME, "deck-commander")  # outro só em teste
        uid = os.getuid()
        env = {k: v for k, v in os.environ.items() if k not in ("LD_LIBRARY_PATH", "PYTHONHOME", "PYTHONPATH")}
        if os.environ.get("LD_LIBRARY_PATH_ORIG"):  # o Decky é empacotado (PyInstaller): devolve o original
            env["LD_LIBRARY_PATH"] = os.environ["LD_LIBRARY_PATH_ORIG"]
        env.update(HOME=HOME, PYTHONPATH=repo, PYTHONIOENCODING="utf-8")
        env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{uid}")  # systemctl --user (modo seguro, bot, traduções)
        env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path=/run/user/{uid}/bus")
        limite = PAINEL_TEMPO.get(acao, 45)
        try:
            proc = await asyncio.create_subprocess_exec(
                "/usr/bin/python3", "-m", "dc.painel", acao, cwd=repo, env=env, start_new_session=True,
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        except OSError:
            return {"ok": False, "erro": "Não achei o Deck Commander em ~/deck-commander."}
        try:
            out, _err = await asyncio.wait_for(proc.communicate(json.dumps(args or {}).encode()), limite)
        except asyncio.TimeoutError:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
            await proc.wait()
            return {"ok": False, "erro": f"Demorou mais de {limite} s e eu parei. Tente de novo daqui a pouco."}
        for linha in reversed(out.decode("utf-8", "replace").splitlines()):
            if linha.startswith("{"):
                try:
                    return json.loads(linha)
                except ValueError:
                    break
        return {"ok": False, "erro": "O Deck Commander não respondeu direito (atualizado?). Veja o Diagnóstico."}

    async def _main(self):
        os.makedirs(BASE, exist_ok=True)

    async def _unload(self):
        pass
