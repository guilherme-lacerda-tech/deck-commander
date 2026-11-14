"""Executor das tarefas longas de tradução/conversão, FORA do bot (o bot continua respondendo).

`python3 -m dc.traducao.run <op_id>` — lançado pelo bot com prioridade baixa (nice).
- Uma tarefa por vez (as outras esperam "na fila").
- Pausa sozinho na bateria (a não ser que traducao.toml permita) e, com IA local, enquanto um jogo
  estiver aberto (para não roubar desempenho).
- Provedor pago: estima tokens primeiro e espera /traduzir aprovar <op>.
- Estado em state/traducao/<op>.json (o bot lê e avisa no Telegram quando termina).
- Registro no banco (M19) como operação 'done' com os campos da tradução.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from .. import ops
from ..paths import Paths, get_paths
from ..store import Store
from . import ia

TYPES = ("translate_switch", "translate_retro", "convert_switch", "translate_n3ds", "translate_generic")


def jobs_dir(paths: Paths) -> Path:
    d = paths.state / "traducao"
    d.mkdir(parents=True, exist_ok=True)
    return d


def job_path(paths: Paths, op: str) -> Path:
    return jobs_dir(paths) / f"{op}.json"


def load_job(paths: Paths, op: str) -> dict:
    try:
        return json.loads(job_path(paths, op).read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def save_job(paths: Paths, job: dict) -> None:
    p = job_path(paths, job["op"])
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(job, ensure_ascii=False, indent=1), "utf-8")
    os.replace(tmp, p)


def all_jobs(paths: Paths) -> list[dict]:
    out = []
    for p in sorted(jobs_dir(paths).glob("*.json"), key=lambda x: x.stat().st_mtime):
        try:
            out.append(json.loads(p.read_text("utf-8")))
        except (OSError, ValueError):
            pass
    return out


def _alive(pid) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except (OSError, ValueError):
        return False
    # depois de reiniciar o Deck o número do processo pode ter sido reaproveitado por outro programa:
    # aí a tarefa "rodando" morta seguraria a fila para sempre
    cmdline = Path(f"/proc/{int(pid)}/cmdline")
    try:
        return b"dc.traducao.run" in cmdline.read_bytes() if cmdline.exists() else True
    except OSError:
        return True


MAX_JOBS = 2  # um jogo grande (ex.: Z-A, horas) não segura a fila: o próximo traduz junto


def active_job(paths: Paths, except_op: str = "") -> dict | None:
    """Devolve uma tarefa que impede esta de começar (já há MAX_JOBS rodando), ou None."""
    running = [j for j in all_jobs(paths)
               if j["op"] != except_op and j.get("status") in ("rodando", "aguardando tomada", "pausado (jogo aberto)")
               and _alive(j.get("pid"))]
    return running[0] if len(running) >= MAX_JOBS else None


class _queue_lock:
    """Trava de arquivo entre os processos de tradução (só no Linux; no Windows dos testes não faz nada)."""

    def __init__(self, paths: Paths):
        self.f = None
        self.path = jobs_dir(paths) / ".fila.lock"

    def __enter__(self):
        try:
            import fcntl
            self.f = open(self.path, "a")
            fcntl.flock(self.f, fcntl.LOCK_EX)
        except (ImportError, OSError):
            self.f = None
        return self

    def __exit__(self, *exc):
        if self.f:
            self.f.close()  # fechar solta a trava


def create(paths: Paths, store: Store, kind: str, game_id: str, title: str, args: dict) -> dict:
    op = store.enqueue(kind, {"game_id": game_id, **args})
    job = {"op": op, "type": kind, "game_id": game_id, "title": title, "args": args, "status": "na fila",
           "progress": [0, 0], "created": datetime.now(timezone.utc).isoformat(), "notified": False}
    from . import motor
    job["motor_versao"] = motor.VERSAO
    save_job(paths, job)
    return job


def spawn(paths: Paths, op: str) -> None:
    """Lança o executor desacoplado do bot (sobrevive a reinício do bot)."""
    repo = Path(__file__).resolve().parents[2]
    cmd = [sys.executable, "-m", "dc.traducao.run", op]
    sdr = shutil.which("systemd-run")
    if sdr:
        # serviço próprio do systemd: não morre se o bot reiniciar (atualização) nem se a sessão fechar
        r = subprocess.run([sdr, "--user", "--collect", "--quiet", f"--unit=deck-commander-traducao-{op}",
                            f"--working-directory={repo}", f"--setenv=PYTHONPATH={repo}",
                            "--property=Nice=15", f"--property=StandardOutput=append:{paths.logs / 'traducao.log'}",
                            f"--property=StandardError=append:{paths.logs / 'traducao.log'}", *cmd],
                           capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            return
    if os.name == "posix" and os.path.exists("/usr/bin/nice"):
        cmd = ["/usr/bin/nice", "-n", "15"] + cmd
    log = open(paths.logs / "traducao.log", "a", encoding="utf-8")
    subprocess.Popen(cmd, cwd=repo, stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                     start_new_session=True, env={**os.environ, "PYTHONPATH": str(repo)})


ATIVOS_FILA = ("na fila", "rodando", "aguardando tomada", "pausado (jogo aberto)", "aguardando sim", "aguardando ok")


def translator_for(paths: Paths, store: Store, gid: str, g: dict, idi: dict, jobs: list[dict]) -> tuple[str, str]:
    """Decide o que fazer com um jogo: (situação, tipo de tarefa). Situação: 'pt' (já em português),
    'ok' (tem tradutor), 'fila' (já traduzindo/na fila), 'feito', 'falhou' (já tentou e não deu),
    'generico' (só a tradução fora do padrão), 'sem' (sem tradutor)."""
    from . import portugues, rts
    if portugues.status(gid, g, idi):
        return "pt", ""
    console = g.get("console", "")
    if console == "switch":
        kind = "translate_switch"
    elif console == "n3ds":
        kind = "translate_n3ds"
    elif console in ("ps3", "wiiu"):
        return "generico", "translate_generic"
    else:
        okc, _why = rts.supported(console, Path(g.get("rom", "")))
        if not okc:
            return "sem", ""
        kind = "translate_retro"
    from . import motor
    mark = idi.get(gid, {})
    if mark.get("pouco_texto") or (mark.get("formato") == "fechado" and not motor.stale(mark)):
        return "sem", ""
    mine = [j for j in jobs if j.get("game_id") == gid]
    if any(j.get("status") in ATIVOS_FILA for j in mine):
        return "fila", kind
    if already_translated(store, gid, kind):
        return "feito", kind
    if any(j.get("type") == kind and j.get("status") in ("falhou", "aguardando análise")
           and not (kind == "translate_switch" and motor.stale(j)) for j in mine):  # falhou numa versão mais antiga: o sistema aprendeu coisa nova, tenta de novo
        return "falhou", kind
    return "ok", kind


def auto_queue(paths: Paths, store: Store, game_ids: list[str], lote: bool = False) -> list[str]:
    """Download novo que não está em português => tradução automática na fila (traducao.toml:
    auto_traduzir = true, padrão). Devolve linhas para a mensagem do bot.
    `lote=True` ("/traduzir biblioteca"): pedido explícito (ignora auto_traduzir), não pergunta a tradução fora
    do padrão de cada jogo e não lança um processo por jogo — kick_queue() lança o próximo quando abre vaga."""
    cfg = ia.load_cfg(paths)
    if (not cfg.get("auto_traduzir", True) and not lote) or not game_ids:
        return []
    from . import portugues
    try:
        lm = json.loads((paths.data / "launch-map.json").read_text("utf-8"))
    except (OSError, ValueError):
        return []
    idi = portugues.load_idiomas(paths.data)
    jobs = all_jobs(paths)
    out = []
    for gid in game_ids:
        g = lm.get(gid)
        if not g or g.get("removed"):
            continue
        sit, kind = translator_for(paths, store, gid, g, idi, jobs)
        if sit == "pt":
            if not lote:
                st = portugues.status(gid, g, idi)
                out.append(f"🇧🇷 {g['title']}: já está em português ({'oficial' if st == 'oficial' else 'traduzido'}).")
            continue
        if not lote and cfg.get("comunidade_primeiro", True) and sit in ("ok", "falhou", "generico", "sem"):
            from . import comunidade  # regra do usuário 14/11/2026: tradução de fã primeiro, IA só se não existir
            if comunidade.registrar(paths, gid, g) or comunidade.esperando(paths, gid):
                out.append(f"🔎 {g['title']}: primeiro procuro uma tradução feita por fãs (o PC procura quando "
                           "estiver ligado); se não existir, a IA traduz.")
                continue
        if sit == "generico" and not lote:
            if offer_generic(paths, store, gid, g["title"], "não há tradutor padrão para este console"):
                out.append(f"❓ {g['title']}: vou perguntar se quer a tradução fora do padrão.")
            continue
        if sit != "ok" and not (sit == "falhou" and not lote):
            continue
        job = create(paths, store, kind, gid, g["title"], {"auto": True, **({"lote": True} if lote else {})})
        jobs.append(job)
        if lote:
            out.append(f"• {g['title']}")
            continue
        spawn(paths, job["op"])
        out.append(f"🈯 {g['title']}: não está em português — traduzindo sozinho; aviso quando ficar pronto.")
    if lote:
        kick_queue(paths)
    return out


def _age_min(iso: str) -> float:
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds() / 60
    except (TypeError, ValueError):
        return 1e9


def library_plan(paths: Paths, store: Store) -> dict:
    """Resumo para "/traduzir biblioteca": quantos entram na fila e por que os outros não."""
    from . import portugues
    try:
        lm = json.loads((paths.data / "launch-map.json").read_text("utf-8"))
    except (OSError, ValueError):  # Deck novo, nenhum jogo ainda
        lm = {}
    idi = portugues.load_idiomas(paths.data)
    jobs = all_jobs(paths)
    out: dict[str, list[str]] = {k: [] for k in ("ok", "pt", "fila", "feito", "falhou", "generico", "sem")}
    for gid, g in sorted(lm.items(), key=lambda kv: kv[1].get("title", "")):
        if g.get("removed"):
            continue
        sit, _kind = translator_for(paths, store, gid, g, idi, jobs)
        out[sit].append(gid)
    return out


def kick_queue(paths: Paths) -> list[str]:
    """Lança as tarefas do lote que ainda não têm processo, até MAX_JOBS ao mesmo tempo (chamado pelo bot a
    cada ciclo: sobrevive a reinício do Deck)."""
    jobs = all_jobs(paths)
    busy = sum(1 for j in jobs if j.get("status") in ("rodando", "aguardando tomada", "pausado (jogo aberto)", "na fila")
               and _alive(j.get("pid")))
    started = []
    for j in jobs:
        if busy >= MAX_JOBS:
            break
        if j.get("status") == "na fila" and (j.get("args") or {}).get("lote") and not _alive(j.get("pid"))                 and (not j.get("lancado") or _age_min(j["lancado"]) > 10):  # >10 min sem processo: Deck reiniciou
            j["lancado"] = datetime.now(timezone.utc).isoformat()
            save_job(paths, j)
            spawn(paths, j["op"])
            started.append(j["op"])
            busy += 1
    return started


def already_translated(store: Store, game_id: str, kind: str) -> bool:
    for o in store.list(("done",), limit=500):
        if o.type == kind and (o.params or {}).get("game_id") == game_id:
            return True
    return False


# ----------------------------------------------------------------------------- execução
def _power_paused(paths: Paths, cfg: dict) -> bool:
    if cfg.get("permitir_bateria"):
        return False
    try:
        st = json.loads((paths.state / "power-state.json").read_text("utf-8"))
    except (OSError, ValueError):
        return False
    return st.get("state") == "PAUSE"


def _uses_local_ai(cfg: dict) -> bool:
    spec = cfg["providers"].get(cfg["provider"], {})
    url = spec.get("url", "")
    return spec.get("tipo") == "ollama" and ("127.0.0.1" in url or "localhost" in url)


def run(paths: Paths, op: str) -> dict:
    store = Store(paths.db)
    job = load_job(paths, op)
    if not job:
        raise SystemExit(f"tarefa {op} não existe")
    cfg = ia.load_cfg(paths)
    job["pid"] = os.getpid()
    while True:  # checar a vaga e ocupar é uma coisa só (senão duas tarefas esperando começam juntas)
        with _queue_lock(paths):
            if not active_job(paths, op):
                job.update(status="rodando", started=datetime.now(timezone.utc).isoformat())
                save_job(paths, job)
                break
            job["status"] = "na fila"; save_job(paths, job)
        time.sleep(30)
    store.claim(op)  # 'pending' -> 'running' (ou já estava, se for retomada)
    last = [0.0]

    def progress(done: int, total: int) -> None:
        job["progress"] = [done, total]
        if time.time() - last[0] > 10 or done == total:
            last[0] = time.time(); save_job(paths, job)

    def should_pause() -> bool:
        why = None
        if _power_paused(paths, cfg):
            why = "aguardando tomada"
        elif _uses_local_ai(cfg) and ops.game_running():
            why = "pausado (jogo aberto)"
        new = why or "rodando"
        if job["status"] != new:
            job["status"] = new; save_job(paths, job)
        return why is not None

    try:
        result, text, ok = _dispatch(paths, store, job, cfg, progress, should_pause)
        if job["status"] in ("aguardando aprovação", "aguardando ok"):  # espera /traduzir aprovar ou o Sim no bot
            job.update(report=text, result=result)
            store.finish(op, False, error=job["status"])
        else:
            job.update(status="concluido" if ok else "falhou", report=text, result=result)
            store.finish(op, ok, result=result, error=None if ok else text[:300])
    except Exception as e:  # noqa: BLE001 — qualquer falha vira relatório; nada do original foi tocado
        job.update(status="falhou", report=f"{type(e).__name__}: {e}")
        store.finish(op, False, error=f"{type(e).__name__}: {e}")
        with open(paths.logs / "traducao.log", "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.now().isoformat(timespec='seconds')}] tarefa {op} ({job.get('type')}) — "
                    f"{job.get('title', job.get('game_id'))}\n" + traceback.format_exc())
    job["finished"] = datetime.now(timezone.utc).isoformat()
    job.pop("pid", None)
    save_job(paths, job)
    return job


def _game(paths: Paths, game_id: str) -> dict:
    lm = json.loads((paths.data / "launch-map.json").read_text("utf-8"))
    if game_id not in lm:
        raise LookupError(f"jogo {game_id} não está na biblioteca")
    return lm[game_id]


def _refresh_tabs(paths: Paths) -> None:
    try:
        from .. import syncer, tabs, vdf
        if tabs.SETTINGS.exists():
            sc = syncer.shortcuts_path()
            tabs.apply(vdf.read_shortcuts(sc), json.loads((paths.data / "launch-map.json").read_text("utf-8")),
                       sc.parents[1].name, data_dir=paths.data)
    except Exception:  # noqa: BLE001 — aba é conforto
        pass


def _gba_inside(rom: Path, tid: str, roots) -> str | None:
    """Jogos de GBA vendidos no Switch (ex.: FireRed/LeafGreen) trazem a ROM .gba dentro do RomFS."""
    from . import converter, extract, nca, switch
    try:
        keys = nca.load_keys(switch.keys_path())
        rfs, hs = nca.open_romfs(rom, keys, extract.latest_update(converter.collect(roots, tid)))
    except (nca.NcaError, OSError, TypeError):
        return None
    try:
        gbas = [p for p in rfs.files() if p.lower().endswith(".gba")]
        return gbas[0] if len(gbas) == 1 else None
    finally:
        for h in hs:
            h.close()


def _translate_gba_inside(paths, job, g, tid, inner, progress, should_pause):
    """ROM de GBA dentro de um jogo de Switch: tradução retrô (Meowth) e a ROM traduzida vira mod."""
    from .. import syncer
    from . import converter, extract, nca, retro, switch
    keys = nca.load_keys(switch.keys_path())
    rom = Path(g["rom"])
    rfs, hs = nca.open_romfs(rom, keys, extract.latest_update(converter.collect(syncer.rom_roots(), tid)))
    try:
        off, size = rfs.files()[inner]
        work = paths.data / "traducao" / "gba" / tid
        work.mkdir(parents=True, exist_ok=True)
        src = work / Path(inner).name
        src.write_bytes(rfs.read_at(off, size))
    finally:
        for h in hs:
            h.close()
    if not src.read_bytes()[0xAC:0xB0].isalnum():  # código do jogo no cabeçalho do GBA (ex.: BPRE)
        return {"title_id": tid}, "o arquivo .gba dentro do jogo não parece uma ROM de GBA", False
    from . import portugues
    langs = portugues.load_idiomas(paths.data).get(job["game_id"], {}).get("langs", [])
    english = any("English" in l for l in langs)
    source = None if english or not langs else ("es" if any("Spanish" in l for l in langs) else None)
    rep = retro.translate_rom(paths, src, g.get("title", ""), progress=progress, should_pause=should_pause,
                              source=source)
    if not rep.output or Path(rep.output).parent != src.parent:
        return {"title_id": tid}, rep.text(), False
    dst = switch.mod_target(tid) / "romfs" / inner
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(Path(rep.output).read_bytes())
    _refresh_tabs(paths)
    return ({"title_id": tid, "traducao_pt_br": True, "provider": rep.provider, "translated": rep.translated,
             "mod": str(switch.mod_target(tid))},
            rep.text() + f"\n✅ mod ativo: a ROM de GBA dentro do jogo foi trocada pela traduzida ({inner}).", True)


def _translate_trinity(paths, job, g, tid, rom, cfg, progress, should_pause):
    """Engine Trinity (Pokémon Legends Z-A): mensagens .dat + data.trpfd alterado, como mod."""
    from .. import syncer
    from . import portugues, trinity_game
    if not job["args"].get("aprovado"):
        src_dir, info = trinity_game.extract(paths, rom, tid, syncer.rom_roots(), cfg["idioma_origem"])
        from . import trinity_msg
        texts = [t for rel in info["mensagens"]
                 for t, _ in trinity_msg.read_dat((src_dir / "romfs" / rel).read_bytes()).texts() if t.strip()]
        est = ia.estimate_tokens(texts)
        need = _approval_needed(paths, cfg, est, job)
        if need:
            job["status"] = "aguardando aprovação"
            return {"estimate": est}, need, False
    job["extracao"] = "trinity (data.trpfs)"
    rep = trinity_game.translate_game(paths, tid, rom, syncer.rom_roots(), g.get("title", ""),
                                      force_font=job["args"].get("forcar", False),
                                      progress=progress, should_pause=should_pause)
    portugues.unmark(paths.data, job["game_id"], "formato")
    if rep.applied:
        _refresh_tabs(paths)
    result = {"traducao_pt_br": rep.applied, "provider": rep.provider, "modelo": cfg["providers"].get(
        rep.provider, {}).get("modelo", ""), "msbt_count": rep.msbt_count, "strings": rep.strings,
        "translated": rep.translated, "flagged": rep.flagged, "formato": "trinity", "mod": rep.mod_dir,
        "title_id": tid, "data": datetime.now(timezone.utc).isoformat()}
    return result, rep.text(), rep.translated > 0 and not (rep.errors and not rep.applied)


def _translate_lm3(paths, job, g, tid, rom, cfg, progress, should_pause):
    """Luigi's Mansion 3: copia o init.patch (base + atualização), traduz as tabelas em inglês e grava o mod."""
    from .. import syncer
    from . import lm3, nca, nlg, portugues
    try:
        patch = lm3.fetch_patch(rom, tid, syncer.rom_roots())
    except (nca.NcaError, OSError) as e:
        return {"title_id": tid}, f"Não consegui abrir o Luigi's Mansion 3: {e}", False
    job["extracao"] = str(patch)
    portugues.mark(paths.data, job["game_id"], formato=None)  # formato próprio do LM3 agora é suportado
    if not job["args"].get("aprovado"):
        try:
            est = ia.estimate_tokens(nlg.get_table(nlg.read_patch(patch.read_bytes()), lm3.LOCALES[0]).strings)
        except (nlg.PatchError, nlg.TableError, IndexError):
            est = 0
        need = _approval_needed(paths, cfg, est, job)
        if need:
            job["status"] = "aguardando aprovação"
            return {"estimate": est}, need, False
    rep = lm3.translate_game(paths, tid, patch, g.get("title", ""), progress=progress, should_pause=should_pause)
    if rep.applied:
        _refresh_tabs(paths)
    result = {"traducao_pt_br": rep.applied, "provider": rep.provider, "strings": rep.strings,
              "translated": rep.translated, "flagged": rep.flagged, "sem_espaco": rep.reverted_space,
              "linha_extra": rep.extra_line, "mod": rep.mod_dir, "title_id": tid, "formato": "nlg init.patch",
              "data": datetime.now(timezone.utc).isoformat()}
    return result, rep.text(), rep.translated > 0 and not (rep.errors and not rep.applied)


def _approval_needed(paths: Paths, cfg: dict, texts_estimate: int, job: dict) -> str | None:
    chain = ia.build_chain(paths, cfg)
    if not chain or chain[0].free or job["args"].get("aprovado") or not cfg.get("estimativa_antes_de_iniciar", True):
        return None
    return (f"Estimativa: ~{texts_estimate:,} tokens no {chain[0].name} ({chain[0].model}). "
            f"Usados hoje: {ia.tokens_today(paths):,} de {cfg.get('limite_diario_tokens'):,}. "
            f"Para seguir: /traduzir aprovar {job['op']}").replace(",", ".")


N3DS_TEXT = (".msbt", ".sarc", ".szs", ".arc", ".bcfnt", ".msbt.lz", ".zs")


def _engine_of(rom: Path, tid: str) -> dict:
    """Motor do jogo pela lista de arquivos (sem extrair nada)."""
    from .. import syncer
    from . import converter, extract, motor, nca, switch
    try:
        upd = extract.latest_update(converter.collect(syncer.rom_roots(), tid))
        rfs, handles = nca.open_romfs(rom, nca.load_keys(switch.keys_path()), upd)
        try:
            return motor.identify(list(rfs.files()))
        finally:
            for h in handles:
                h.close()
    except Exception:  # noqa: BLE001 - só diagnóstico
        return {"motor": "não identificado (jogo comprimido ou sem chaves)", "traduzo": False,
                "caminho": "descompactar (/converter <jogo> descompactar) e tentar de novo"}


def _translate_unreal(paths, job, g, tid, rom, cfg, progress, should_pause):
    """Jogo de Switch feito na Unreal Engine: traduz o .locres e instala um pak de mod "_P" por cima.
    Devolve None se o jogo não for Unreal (aí segue o fluxo normal)."""
    from .. import syncer
    from . import converter, extract, nca, switch, unreal
    kp = switch.keys_path()
    if not kp:
        return None
    upd = extract.latest_update(converter.collect(syncer.rom_roots(), tid))
    try:
        rfs, handles = nca.open_romfs(rom, nca.load_keys(kp), upd)
    except (nca.NcaError, OSError):
        return None
    try:
        files = rfs.files()
        paks = unreal.main_paks(files)
        if not paks:
            return None
        found = {}
        for pk in paks:
            o, s = files[pk]
            rd = (lambda base: lambda a, n: rfs.read_at(base + a, n))(o)
            try:
                pak = unreal.read_pak(rd, s)
            except unreal.UnrealError as e:
                return {"title_id": tid}, f"Jogo feito na Unreal Engine, mas não consegui abrir {pk}: {e}", False
            for lp in unreal.game_locres(pak, cfg.get("idioma_origem", "en")):
                ent = pak.entries[lp]
                data = unreal.cached_plain(paths.data, tid, lp)
                if data is None:
                    try:
                        data = unreal.read_entry(rd, ent)
                    except unreal.UnrealError as e:
                        job["status"] = "aguardando análise"
                        return {"title_id": tid, "unreal": True}, (
                            f"Jogo feito na Unreal Engine: achei os textos ({lp}), mas {e}. O PC descompacta "
                            f"com o Oodle de um jogo seu (tools/pc/oodle_locres.py); depois mande /traduzir de novo."), False
                found[lp] = data
    finally:
        for h in handles:
            h.close()
    if not found:
        return None
    from . import portugues
    portugues.unmark(paths.data, job["game_id"], "formato")
    project = next(iter(found)).split("/", 1)[0]
    out, total, res_all = {}, 0, []
    for lp, data in found.items():
        new, res, changed = unreal.translate_locres(paths, cfg, data, f"unreal-{tid}", g.get("title", ""),
                                                    progress=progress, should_pause=should_pause)
        res_all.append(res)
        total += changed
        if changed:
            out[lp] = new
    if not out:
        errs = "; ".join(e for r in res_all for e in r.errors[:2]) or "nenhuma frase traduzida"
        return {"title_id": tid}, f"Não consegui traduzir: {errs}", False
    mod_root = switch.mod_target(tid)
    pak_path = unreal.build_mod(out, mod_root / "romfs", project)
    unreal.save_version(mod_root, {"base": rom.name, "update": upd.name if upd else None, "arquivos": sorted(out)})
    _refresh_tabs(paths)
    prov = next((r.provider_used for r in res_all if r.provider_used), "")
    msg = (f"Tradução pronta: {total} frases em português (jogo Unreal Engine). O mod substitui o texto em INGLÊS, "
           f"então o jogo precisa estar em inglês (padrão do Ryujinx). Se aparecer quadradinho no lugar de ã/õ, "
           f"me avise que eu troco esses acentos.")
    return ({"traducao_pt_br": True, "translated": total, "provider": prov, "title_id": tid, "mod": str(pak_path),
             "data": datetime.now(timezone.utc).isoformat()}, msg, True)


def _offer(job: dict, tid: str, oferta: dict, text: str) -> tuple[dict, str, bool]:
    """Deixa a tarefa esperando o Sim do usuário no Telegram (o bot manda a pergunta com o tempo estimado)."""
    job["status"] = "aguardando ok"
    job["oferta"] = oferta
    job["notified"] = False
    return {"title_id": tid, "motor": oferta.get("motor", "")}, text, False


def _not_yet(paths, job, tid: str, motor_name: str, why: str) -> tuple[dict, str, bool]:
    """Não deu desta vez: marca com a versão do motor (tenta de novo sozinho quando o sistema aprender mais)."""
    from . import motor, portugues
    portugues.mark(paths.data, job["game_id"], formato="fechado", motor_versao=motor.VERSAO, motor=motor_name)
    return {"title_id": tid, "motor": motor_name}, (
        f"Jogo feito em {motor_name}: {why}\nNão é \"impossível\": quando o Deck Commander aprender mais sobre "
        "esse formato, ele tenta de novo sozinho."), False


def _translate_engine(paths, job, g, tid, rom, cfg, progress, should_pause):
    """Jogo feito em Unity, GameMaker, Godot, RE Engine, RPG Maker ou com pacotes CRI: acha as frases com o
    adaptador do motor, PERGUNTA no Telegram (quantas frases, tempo estimado) e, com o Sim, traduz e instala
    os arquivos novos no mod do Ryujinx. Devolve None se nenhum adaptador reconhece o jogo."""
    from .. import syncer
    from . import converter, extract, motores, nca, portugues, switch
    kp = switch.keys_path()
    if not kp:
        return None
    upd = extract.latest_update(converter.collect(syncer.rom_roots(), tid))
    try:
        rfs, handles = nca.open_romfs(rom, nca.load_keys(kp), upd)
    except (nca.NcaError, OSError):
        return None
    try:
        files = rfs.files()
        ad = motores.adapter_for(list(files))
        if not ad:
            return None
        if getattr(ad, "ptbr_oficial", None) and ad.ptbr_oficial(list(files)):
            # o próprio jogo já tem português do Brasil (só não aparece na lista de idiomas do console)
            from .. import quality
            portugues.mark(paths.data, job["game_id"], ptbr="oficial", ptbr_menu=True)
            quality.set_language(paths, job["game_id"], portugues.OFFICIAL, "português do Brasil do próprio jogo")
            _refresh_tabs(paths)
            return ({"title_id": tid, "traducao_pt_br": True, "provider": "oficial", "motor": ad.NAME},
                    "Esse jogo já tem português do Brasil OFICIAL (vem dentro do jogo). Configurei para ele abrir "
                    "em português; se abrir em inglês, escolha Português (Brasil) no menu de idioma do jogo. "
                    "Está na aba \"Em português\".", True)

        def read(path: str) -> bytes:
            o, n = files[path]
            return rfs.read_at(o, n)
        try:
            col = ad.collect(files, read)
        except motores.MotorError as e:
            return _not_yet(paths, job, tid, ad.NAME, f"{e}. Nada do jogo foi alterado.")
        n = len(motores.unique_texts(col))
        if not n:
            return _not_yet(paths, job, tid, ad.NAME, (col.aviso or "não achei frases num formato que eu já leia")
                            + ". Nada do jogo foi alterado.")
        if not job["args"].get("motor_ok"):
            return _offer(job, tid, {"motor": ad.NAME, "frases": n, "minutos": motores.estimate_minutes(n, cfg),
                                     "aviso": col.aviso},
                          f"Jogo feito em {ad.NAME}: achei {n} frases. Esperando o seu Sim no Telegram.")
        portugues.unmark(paths.data, job["game_id"], "formato")
        new, res, changed = motores.translate(paths, cfg, col, f"motor-{tid}", g.get("title", ""),
                                              progress=progress, should_pause=should_pause)
    finally:
        for h in handles:
            h.close()
    if not new:
        errs = "; ".join(res.errors[:2]) or "nenhuma frase traduzida"
        return {"title_id": tid, "motor": ad.NAME}, f"Não consegui traduzir: {errs}", False
    mod_root = switch.mod_target(tid)
    motores.install(new, mod_root / "romfs")
    (mod_root / "deck-commander-motor.json").write_text(json.dumps(
        {"motor": ad.NAME, "base": rom.name, "update": upd.name if upd else None, "arquivos": sorted(new)},
        ensure_ascii=False, indent=1), "utf-8")
    _refresh_tabs(paths)
    msg = (f"Tradução pronta: {changed} frases em português (jogo {ad.NAME}). O mod troca o texto em INGLÊS, então "
           "o jogo precisa estar em inglês. Se aparecer quadradinho no lugar de ã/õ/ç, me avise que eu troco esses "
           "acentos." + (f"\nObs.: {col.aviso}" if col.aviso else ""))
    return ({"traducao_pt_br": True, "translated": changed, "provider": res.provider_used or "", "title_id": tid,
             "motor": ad.NAME, "data": datetime.now(timezone.utc).isoformat()}, msg, True)


def answer_motor(paths: Paths, op: str, yes: bool) -> str:
    """Resposta ao botão Sim/Não da pergunta "traduzir este jogo <motor>? leva ~X"."""
    job = load_job(paths, op)
    if not job or job.get("status") != "aguardando ok":
        return "Essa pergunta já foi respondida."
    if not yes:
        job.update(status="recusado", notified=True)
        save_job(paths, job)
        return f"Ok, {job['title']} fica como está. (Para pedir depois: /traduzir {job['title']})"
    job["args"]["motor_ok"] = True
    job.update(status="na fila", notified=False, progress=[0, 0])
    save_job(paths, job)
    spawn(paths, op)
    of = job.get("oferta") or {}
    return f"🛠 Começou: {job['title']} ({of.get('motor', '')}). Aviso aqui quando terminar."


def _translate_n3ds(paths, job, g, rom: Path, cfg, progress, should_pause) -> tuple[dict, str, bool]:
    """3DS: mesmo tradutor de MSBT do Switch; o mod vai para o Azahar (load/mods/<TitleID>/romfs)."""
    import shutil

    from . import n3ds, switch
    try:
        game = n3ds.open_game(rom)
    except n3ds.Encrypted as e:
        return {}, f"Não dá para traduzir: {e}. (O Azahar também só roda dump descriptografado.)", False
    except (n3ds.FormatError, OSError) as e:
        return {}, f"Não consegui abrir o jogo de 3DS: {e}", False
    tid = game.title_id
    work = paths.data / "traducao" / "n3ds" / tid / "romfs"
    shutil.rmtree(work, ignore_errors=True)
    n = game.extract(work, lambda rel: rel.lower().endswith(N3DS_TEXT))
    if not n:
        return {"title_id": tid}, ("Este jogo de 3DS não tem textos no formato padrão da Nintendo (MSBT). "
                                   "Use a tradução fora do padrão."), False

    def install(title_id: str, staged: Path) -> Path:
        dst = n3ds.mod_dir(title_id)
        if (dst / "romfs").exists():
            shutil.rmtree(dst / "romfs")
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copytree(staged / "romfs", dst / "romfs")
        return dst

    rep = switch.translate_game(paths, tid, work, g.get("title", ""), force_font=job["args"].get("forcar", False),
                                progress=progress, should_pause=should_pause, install=install, tag="n3ds")
    if rep.applied:
        _refresh_tabs(paths)
    result = {"traducao_pt_br": rep.applied, "provider": rep.provider, "strings": rep.strings,
              "translated": rep.translated, "flagged": rep.flagged, "mod": rep.mod_dir, "title_id": tid,
              "data": datetime.now(timezone.utc).isoformat()}
    return result, rep.text(), rep.translated > 0 and not (rep.errors and not rep.applied)


def offer_generic(paths: Paths, store: Store, game_id: str, title: str, motivo: str) -> dict | None:
    """Deixa a pergunta "tradução fora do padrão — deseja traduzir?" para o bot fazer (botões Sim/Não)."""
    from . import fora_padrao
    g = _game(paths, game_id)
    if g.get("console") not in fora_padrao.SUPPORTED:
        return None
    if any(j.get("game_id") == game_id and j.get("type") == "translate_generic" and
           j.get("status") in ("aguardando sim", "na fila", "rodando", "recusado") for j in all_jobs(paths)):
        return None
    job = create(paths, store, "translate_generic", game_id, title, {"motivo": motivo})
    job.update(status="aguardando sim", notified=False, report=motivo)
    save_job(paths, job)
    return job


def answer_generic(paths: Paths, op: str, yes: bool) -> str:
    job = load_job(paths, op)
    if not job or job.get("status") != "aguardando sim":
        return "Essa pergunta já foi respondida."
    if not yes:
        job.update(status="recusado", notified=True)
        save_job(paths, job)
        return f"Ok, {job['title']} fica como está."
    job.update(status="na fila", notified=False)
    save_job(paths, job)
    spawn(paths, op)
    return (f"🛠 Tradução fora do padrão de {job['title']} começou, só com as IAs locais do PC/Deck. "
            "Pode levar horas; aviso quando terminar.")


def _translate_generic(paths, job, g, rom: Path, cfg, progress, should_pause) -> tuple[dict, str, bool]:
    import shutil

    from .. import syncer
    from . import fora_padrao, n3ds, switch
    console = g["console"]
    work = paths.data / "traducao" / "fora-do-padrao" / job["game_id"]
    shutil.rmtree(work, ignore_errors=True)
    src, stage = work / "arquivos", work / "traduzidos"
    expected = idioma_from_name(rom.name)
    if console == "switch":
        from ..dedup import base_title_id
        tid = base_title_id(rom.name)
        if not tid:
            return {}, "não achei o Title ID no nome do arquivo", False
        fora_padrao.extract_switch(rom, tid, syncer.rom_roots(), src)
        rep = fora_padrao.translate_dir(paths, src, stage, g.get("title", ""), expected, progress=progress,
                                        should_pause=should_pause)
        if rep.changed:
            fora_padrao.install_layeredfs(stage, switch.mod_target(tid) / "romfs")
    elif console == "n3ds":
        game = n3ds.open_game(rom)
        game.extract(src, lambda rel: Path(rel).suffix.lower() not in fora_padrao.MEDIA)
        rep = fora_padrao.translate_dir(paths, src, stage, g.get("title", ""), expected, progress=progress,
                                        should_pause=should_pause)
        if rep.changed:
            fora_padrao.install_layeredfs(stage, n3ds.mod_dir(game.title_id) / "romfs")
    else:  # jogo em pasta (PS3, Wii U): cópia "(PT-BR)" com links + os arquivos traduzidos
        root = fora_padrao.folder_game_root(console, rom)
        if not root:
            return {}, "formato de arquivo deste jogo não é pasta; a tradução fora do padrão não se aplica", False
        rep = fora_padrao.translate_dir(paths, root, stage, g.get("title", ""), expected, progress=progress,
                                        should_pause=should_pause)
        if rep.changed:
            out = root.with_name(root.name + " (PT-BR)")
            shutil.rmtree(out, ignore_errors=True)
            fora_padrao.hardlink_copy(root, out)
            for rel in rep.changed:
                (out / rel).unlink(missing_ok=True)
                shutil.copy2(stage / rel, out / rel)
    shutil.rmtree(src, ignore_errors=True)
    if rep.changed:
        _refresh_tabs(paths)
    return ({"traducao_pt_br": bool(rep.changed), "translated": rep.translated, "provider": rep.provider},
            rep.text(), bool(rep.changed))


def idioma_from_name(name: str):
    from . import idioma
    return idioma.language_from_name(name)


def _dispatch(paths, store, job, cfg, progress, should_pause) -> tuple[dict, str, bool]:
    from .. import syncer
    g = _game(paths, job["game_id"])
    rom = Path(g["rom"])
    if job["type"] == "translate_switch":
        from ..dedup import base_title_id
        from . import switch
        tid = base_title_id(rom.name)
        if not tid:
            return {}, "não achei o Title ID no nome do arquivo ([0100…])", False
        from . import extract, nca, portugues
        # 1) o jogo já tem português oficial? então é só abrir com o idioma certo (sem IA, sem cópia)
        idi = portugues.detect_switch(paths, {job["game_id"]: g}, syncer.rom_roots())
        if idi.get(job["game_id"], {}).get("ptbr") == "oficial":
            _refresh_tabs(paths)
            return ({"title_id": tid, "traducao_pt_br": True, "provider": "oficial"},
                    "Esse jogo já tem português do Brasil OFICIAL. Configurei para ele abrir em português "
                    "(só ele; os outros continuam como estavam). Está na aba \"Em português\".", True)
        from . import lm3
        if lm3.supported(tid):  # Luigi's Mansion 3: textos no init.patch da Next Level Games (não é MSBT)
            return _translate_lm3(paths, job, g, tid, rom, cfg, progress, should_pause)
        ue = _translate_unreal(paths, job, g, tid, rom, cfg, progress, should_pause)
        if ue:  # Unreal Engine (ex.: Final Fantasy Resonance): textos em .locres dentro do .pak
            return ue
        eng = _translate_engine(paths, job, g, tid, rom, cfg, progress, should_pause)
        if eng:  # Unity, GameMaker, Godot, RE Engine, RPG Maker, CRI: pergunta antes (Sim/Não + tempo)
            return eng
        romfs = switch.find_romfs(tid)
        how = "pasta extraída"
        if not romfs:
            try:  # 2) extrai sozinho só os textos (base + atualização) com as chaves do Ryujinx
                romfs, how = extract.extract_texts(rom, tid, syncer.rom_roots(), cfg["idioma_origem"])
            except nca.NcaError as e:
                gba = _gba_inside(rom, tid, syncer.rom_roots())
                if gba:
                    return _translate_gba_inside(paths, job, g, tid, gba, progress, should_pause)
                from . import trinity_game
                files = trinity_game.find_rom_files(rom, tid, syncer.rom_roots())
                if files and trinity_game.is_trinity(files):  # Pokémon Legends Z-A / Scarlet-Violet
                    return _translate_trinity(paths, job, g, tid, rom, cfg, progress, should_pause)
                romfs = switch.extract_with_hactool(rom, tid)
                if not romfs and ("prod.keys" in str(e) or "ausente" in str(e)):
                    return {"title_id": tid}, (
                        f"Não consegui abrir o jogo: {e}. Abra qualquer jogo no Ryujinx uma vez (ele guarda as chaves), "
                        f"ou extraia os arquivos: Ryujinx → botão direito no jogo → Extrair dados → RomFS → "
                        f"~/Emulation/romfs/{tid}. Depois mande /traduzir de novo."), False
                if not romfs:
                    from . import motor
                    info = _engine_of(rom, tid)
                    portugues.mark(paths.data, job["game_id"], formato="fechado", motor_versao=motor.VERSAO,
                                   motor=info["motor"])
                    return {"title_id": tid, "motor": info["motor"]}, (
                        f"Ainda não traduzo este jogo sozinho: {e}.\nMotor do jogo: {info['motor']}.\n"
                        f"Caminho para traduzir: {info['caminho']}.\nNão é \"impossível\": quando o Deck "
                        "Commander aprender esse formato, ele tenta de novo sozinho."), False
        job["extracao"] = how
        portugues.unmark(paths.data, job["game_id"], "formato")  # achou os textos: não é mais "formato fechado"
        if not job["args"].get("aprovado"):
            rep0 = switch.Report(tid)
            files, _ = switch.scan(romfs, rep0, cfg["idioma_origem"])
            est = ia.estimate_tokens([t for f in files for t, _ in f.msbt.texts()])
            need = _approval_needed(paths, cfg, est, job)
            if need:
                job["status"] = "aguardando aprovação"
                return {"estimate": est}, need, False
        rep = switch.translate_game(paths, tid, romfs, g.get("title", ""), force_font=job["args"].get("forcar", False),
                                    progress=progress, should_pause=should_pause)
        if rep.applied:
            _refresh_tabs(paths)
        result = {"traducao_pt_br": rep.applied, "provider": rep.provider, "modelo": cfg["providers"].get(
            rep.provider, {}).get("modelo", ""), "msbt_count": rep.msbt_count, "strings": rep.strings,
            "translated": rep.translated, "flagged": rep.flagged, "fontes_bitmap": rep.font,
            "compressao": sorted(rep.compression), "referencia_usada": rep.reference, "mod": rep.mod_dir,
            "title_id": tid, "data": datetime.now(timezone.utc).isoformat()}
        return result, rep.text(), rep.translated > 0 and not (rep.errors and not rep.applied)
    if job["type"] == "translate_n3ds":
        return _translate_n3ds(paths, job, g, rom, cfg, progress, should_pause)
    if job["type"] == "translate_generic":
        return _translate_generic(paths, job, g, rom, cfg, progress, should_pause)
    if job["type"] == "translate_retro":
        from . import retro, rts, sotn
        if g["console"] == "psx" and sotn.reconhece(rom):  # engenharia reversa própria (formato do SOTN)
            rep = sotn.translate_rom(paths, rom, g.get("title", ""), progress=progress, should_pause=should_pause)
        elif g["console"] == "gba" and retro.is_pokemon_gba(rom) and retro.meowth_bin():
            rep = retro.translate_rom(paths, rom, g.get("title", ""), progress=progress, should_pause=should_pause)
        else:  # todo o resto do retrô: RomTranslate Studio
            okc, why = rts.supported(g["console"], rom)
            if not okc:
                return {}, f"Não dá para traduzir: {why}.", False
            rep = rts.translate_rom(paths, rom, g["console"], g.get("title", ""), progress=progress,
                                    should_pause=should_pause)
            rep.strings = rep.candidates
            if rep.candidates < rts.MIN_SENTENCES:
                from . import portugues
                portugues.mark(paths.data, job["game_id"], pouco_texto=True)
        ok = bool(rep.output) and Path(rep.output).parent == rom.parent
        if ok:  # ROM "(PT-BR)" entra na biblioteca e SUBSTITUI o atalho do original (sem duplicar)
            op2 = store.enqueue("library-add", {"from": job["op"]})
            store.claim(op2)
            syncer.add_to_steam(paths, store, op2)
            store.finish(op2, True)
            from ..remove import hide
            hide(paths, job["game_id"], "substituído pela versão traduzida (PT-BR)")
            _herdar_detonado(paths, job["game_id"], rep.output)
            rep.errors.append("o original saiu da biblioteca (arquivo guardado); para ter os dois: "
                              f"/devolver {g.get('title', '')}")
            _refresh_tabs(paths)
        from .. import backup
        result = {"traducao_pt_br": ok, "provider": rep.provider, "strings": getattr(rep, "strings", getattr(rep, "found", 0)), "translated": rep.translated,
                  "flagged": rep.flagged, "patch": rep.patch, "patch_hash": backup.sha256_file(Path(rep.patch))
                  if rep.patch else "", "rom": rep.output, "data": datetime.now(timezone.utc).isoformat()}
        return result, rep.text(), bool(rep.output)
    if job["type"] == "convert_switch":
        from ..dedup import base_title_id
        from . import converter
        tid = base_title_id(rom.name)
        tf = converter.collect(syncer.rom_roots(), tid)
        action = job["args"].get("acao")
        lines = converter.organize(tf, g.get("title", tid)) if action == "organizar" else converter.decompress(paths, tf)
        op2 = store.enqueue("library-add", {"from": job["op"]})
        store.claim(op2)
        syncer.add_to_steam(paths, store, op2)  # caminhos novos no mapa do lançador
        store.finish(op2, True)
        return {"acao": action, "title_id": tid, "linhas": lines}, "\n".join(lines), not any("❌" in l for l in lines)
    raise ValueError(f"tipo desconhecido: {job['type']}")


def _herdar_detonado(paths, game_id: str, rom_nova) -> None:
    """O detonado (já traduzido) vai para o jogo "(PT-BR)" que substituiu o original."""
    try:
        from .. import detonado, library
        games, _ = library.scan([Path(rom_nova).parent.parent])  # raiz "roms" (o scan olha roms/<console>)
        novo = next((g.game_id for g in games if Path(g.path) == Path(rom_nova)), None)
        if novo:
            detonado.herdar(paths, game_id, novo)
    except Exception:  # noqa: BLE001 — o detonado nunca atrapalha a tradução
        pass


def main() -> None:
    paths = get_paths().ensure()
    run(paths, sys.argv[1])


if __name__ == "__main__":
    main()
