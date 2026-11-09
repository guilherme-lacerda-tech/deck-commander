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

TYPES = ("translate_switch", "translate_retro", "convert_switch")


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
        return True
    except (OSError, ValueError):
        return False


def active_job(paths: Paths, except_op: str = "") -> dict | None:
    for j in all_jobs(paths):
        if j["op"] != except_op and j.get("status") in ("rodando", "aguardando tomada", "pausado (jogo aberto)") \
                and _alive(j.get("pid")):
            return j
    return None


def create(paths: Paths, store: Store, kind: str, game_id: str, title: str, args: dict) -> dict:
    op = store.enqueue(kind, {"game_id": game_id, **args})
    job = {"op": op, "type": kind, "game_id": game_id, "title": title, "args": args, "status": "na fila",
           "progress": [0, 0], "created": datetime.now(timezone.utc).isoformat(), "notified": False}
    save_job(paths, job)
    return job


def spawn(paths: Paths, op: str) -> None:
    """Lança o executor desacoplado do bot (sobrevive a reinício do bot)."""
    repo = Path(__file__).resolve().parents[2]
    cmd = [sys.executable, "-m", "dc.traducao.run", op]
    if os.name == "posix" and os.path.exists("/usr/bin/nice"):
        cmd = ["/usr/bin/nice", "-n", "15"] + cmd
    log = open(paths.logs / "traducao.log", "a", encoding="utf-8")
    subprocess.Popen(cmd, cwd=repo, stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                     start_new_session=True, env={**os.environ, "PYTHONPATH": str(repo)})


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
    while active_job(paths, op):
        job["status"] = "na fila"; save_job(paths, job); time.sleep(30)
    store.claim(op)  # 'pending' -> 'running' (ou já estava, se for retomada)
    job.update(status="rodando", started=datetime.now(timezone.utc).isoformat())
    save_job(paths, job)
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
        if job["status"] == "aguardando aprovação":  # provedor pago: espera /traduzir aprovar
            job.update(report=text, result=result)
            store.finish(op, False, error="aguardando aprovação")
        else:
            job.update(status="concluido" if ok else "falhou", report=text, result=result)
            store.finish(op, ok, result=result, error=None if ok else text[:300])
    except Exception as e:  # noqa: BLE001 — qualquer falha vira relatório; nada do original foi tocado
        job.update(status="falhou", report=f"{type(e).__name__}: {e}")
        store.finish(op, False, error=f"{type(e).__name__}: {e}")
        with open(paths.logs / "traducao.log", "a", encoding="utf-8") as f:
            f.write(traceback.format_exc())
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
    rep = retro.translate_rom(paths, src, g.get("title", ""), progress=progress, should_pause=should_pause)
    if not rep.output or Path(rep.output).parent != src.parent:
        return {"title_id": tid}, rep.text(), False
    dst = switch.mod_target(tid) / "romfs" / inner
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(Path(rep.output).read_bytes())
    _refresh_tabs(paths)
    return ({"title_id": tid, "traducao_pt_br": True, "provider": rep.provider, "translated": rep.translated,
             "mod": str(switch.mod_target(tid))},
            rep.text() + f"\n✅ mod ativo: a ROM de GBA dentro do jogo foi trocada pela traduzida ({inner}).", True)


def _approval_needed(paths: Paths, cfg: dict, texts_estimate: int, job: dict) -> str | None:
    chain = ia.build_chain(paths, cfg)
    if not chain or chain[0].free or job["args"].get("aprovado") or not cfg.get("estimativa_antes_de_iniciar", True):
        return None
    return (f"Estimativa: ~{texts_estimate:,} tokens no {chain[0].name} ({chain[0].model}). "
            f"Usados hoje: {ia.tokens_today(paths):,} de {cfg.get('limite_diario_tokens'):,}. "
            f"Para seguir: /traduzir aprovar {job['op']}").replace(",", ".")


def _dispatch(paths, store, job, cfg, progress, should_pause) -> tuple[dict, str, bool]:
    from .. import syncer
    g = _game(paths, job["game_id"])
    rom = Path(g["rom"])
    if job["type"] == "translate_switch":
        from . import switch
        from ..dedup import base_title_id
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
        romfs = switch.find_romfs(tid)
        how = "pasta extraída"
        if not romfs:
            try:  # 2) extrai sozinho só os textos (base + atualização) com as chaves do Ryujinx
                romfs, how = extract.extract_texts(rom, tid, syncer.rom_roots(), cfg["idioma_origem"])
            except nca.NcaError as e:
                gba = _gba_inside(rom, tid, syncer.rom_roots())
                if gba:
                    return _translate_gba_inside(paths, job, g, tid, gba, progress, should_pause)
                romfs = switch.extract_with_hactool(rom, tid)
                if not romfs and ("prod.keys" in str(e) or "ausente" in str(e)):
                    return {"title_id": tid}, (
                        f"Não consegui abrir o jogo: {e}. Abra qualquer jogo no Ryujinx uma vez (ele guarda as chaves), "
                        f"ou extraia os arquivos: Ryujinx → botão direito no jogo → Extrair dados → RomFS → "
                        f"~/Emulation/romfs/{tid}. Depois mande /traduzir de novo."), False
                if not romfs:
                    return {"title_id": tid}, (
                        f"Não dá para traduzir este jogo automaticamente: {e}. Os textos dele não estão no formato "
                        "padrão da Nintendo (MSBT), e mexer em formato desconhecido poderia quebrar o jogo."), False
        job["extracao"] = how
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
    if job["type"] == "translate_retro":
        from . import retro
        if not retro.supported(g["console"]):
            return {}, (f"Tradução automática de {g['console'].upper()} ainda não tem extrator confiável "
                        "(hoje: Pokémon de GBA via Meowth)."), False
        rep = retro.translate_rom(paths, rom, g.get("title", ""), progress=progress, should_pause=should_pause)
        ok = bool(rep.output) and Path(rep.output).parent == rom.parent
        if ok:  # ROM "(PT-BR)" entra na biblioteca como jogo novo (o original fica)
            op2 = store.enqueue("library-add", {"from": job["op"]})
            store.claim(op2)
            syncer.add_to_steam(paths, store, op2)
            store.finish(op2, True)
        from .. import backup
        result = {"traducao_pt_br": ok, "provider": rep.provider, "strings": rep.strings, "translated": rep.translated,
                  "flagged": rep.flagged, "patch": rep.patch, "patch_hash": backup.sha256_file(Path(rep.patch))
                  if rep.patch else "", "rom": rep.output, "data": datetime.now(timezone.utc).isoformat()}
        return result, rep.text(), bool(rep.output)
    if job["type"] == "convert_switch":
        from . import converter
        from ..dedup import base_title_id
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


def main() -> None:
    paths = get_paths().ensure()
    run(paths, sys.argv[1])


if __name__ == "__main__":
    main()
