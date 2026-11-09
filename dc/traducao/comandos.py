"""Comandos do bot para as adições A1/A2/A3 (/traduzir e /converter) e o aviso de fim de tarefa."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from .. import ops
from . import ia, run

HELP = """/traduzir <jogo> — traduz para pt-BR com IA (Switch: vira mod; GBA Pokémon: ROM nova "(PT-BR)")
/traduzir lista · status · config · revisar <op> · aplicar <op> · aprovar <op> · retomar <op> · desfazer <jogo>
/converter <jogo> [organizar|descompactar] — Switch: confere/organiza update e DLC, descompacta NSZ"""


def _find(bot, query: str):
    from ..remove import find
    lm = bot._map()
    hits = find(lm, query)
    if len(hits) == 1:
        return hits[0], lm[hits[0]], None
    if not hits:
        return None, None, "Não achei esse jogo na biblioteca."
    return None, None, "Achei mais de um:\n" + "\n".join(f"• {lm[g]['title']} ({lm[g]['console']})" for g in hits[:10])


def traduzir(bot, args: list[str]) -> str:
    P, S = bot.paths, bot.store
    if not args:
        return HELP
    sub = args[0].lower()
    if sub == "config":
        return _config(P)
    if sub == "status":
        js = run.all_jobs(P)[-8:]
        if not js:
            return "Nenhuma tradução/conversão ainda."
        return "\n".join(f"{j['op']} · {j['title']} · {j['status']}" + (
            f" ({j['progress'][0]}/{j['progress'][1]})" if j.get("progress", [0, 0])[1] else "") for j in reversed(js))
    if sub in ("revisar", "aplicar", "aprovar", "retomar") and len(args) == 2:
        job = run.load_job(P, args[1])
        if not job:
            return "Não achei essa tarefa (veja /traduzir status)."
        return {"revisar": _review, "aplicar": _apply, "aprovar": _approve, "retomar": _resume}[sub](bot, job)
    if sub == "desfazer" and len(args) > 1:
        return _undo(bot, " ".join(args[1:]))
    if sub == "lista":
        return _lista(bot)
    force = "--forcar" in args
    query = " ".join(a for a in args if not a.startswith("--"))
    gid, g, err = _find(bot, query)
    if err:
        return err
    if ops.in_safe_mode(P):
        return "Safe-mode ativo."
    from . import portugues
    st = portugues.status(gid, g, portugues.load_idiomas(P.data))
    if st and not force:
        why = {"oficial": "tem português do Brasil oficial (abre em português sozinho)",
               "mod": "já tem a tradução do Deck Commander instalada",
               "traduzido": "já é uma versão traduzida/dublada"}[st]
        return f"{g['title']} {why}. Está na aba \"Em português\". (Para traduzir mesmo assim: --forcar)"
    if g["console"] == "switch":
        kind = "translate_switch"
    elif g["console"] == "switch2":
        return "Switch 2 ainda não tem tradução (os jogos são dumps extraídos, sem MSBT padrão conferido)."
    else:
        from .retro import supported
        if not supported(g["console"]):
            return (f"{g['console'].upper()}: ainda não há extrator de texto confiável para traduzir sozinho. "
                    "Hoje funciona: jogos de Switch e Pokémon de GBA.")
        kind = "translate_retro"
    if run.already_translated(S, gid, kind) and not force:
        return f"{g['title']} já foi traduzido. Para traduzir de novo: /traduzir {query} --forcar"
    cfg = ia.load_cfg(P)
    if not ia.build_chain(P, cfg):
        return "Nenhuma IA disponível: instale o Ollama no Deck (./setup-deck.sh --modules A1) ou configure uma chave."
    job = run.create(P, S, kind, gid, g["title"], {"forcar": force})
    run.spawn(P, job["op"])
    extra = "" if not run._power_paused(P, cfg) else "\n🔌 Começa quando o Deck for para a tomada."
    return (f"🈯 Tradução de {g['title']} na fila ({job['op']}). Pode levar de minutos a horas; "
            f"aviso aqui quando terminar. Acompanhe com /traduzir status.{extra}")


def converter(bot, args: list[str]) -> str:
    from . import converter as cv
    from .. import syncer
    from ..dedup import base_title_id
    if not args:
        return HELP
    action = args[-1].lower() if args[-1].lower() in ("organizar", "descompactar") else None
    query = " ".join(args[:-1] if action else args)
    gid, g, err = _find(bot, query)
    if err:
        return err
    if g["console"] != "switch":
        return "O /converter é só para jogos de Switch."
    tid = base_title_id(Path(g["rom"]).name)
    if not tid:
        return "Não achei o Title ID ([0100…]) no nome do arquivo."
    tf = cv.collect(syncer.rom_roots(), tid)
    if not action:
        return "\n".join(cv.diagnose(tf, g["title"]))
    if ops.game_running():
        return "Feche o jogo antes."
    job = run.create(bot.paths, bot.store, "convert_switch", gid, g["title"], {"acao": action})
    run.spawn(bot.paths, job["op"])
    return f"🔧 {action.capitalize()} {g['title']} ({job['op']}). Aviso quando terminar."


def _lista(bot) -> str:
    from . import portugues
    lm = bot._map()
    idi = portugues.load_idiomas(bot.paths.data)
    pt, can, cant = [], [], []
    for gid, g in sorted(lm.items(), key=lambda kv: (kv[1].get("console", ""), kv[1].get("title", ""))):
        if g.get("removed"):
            continue
        st = portugues.status(gid, g, idi)
        label = f"{g['title']} ({g['console']})"
        if st:
            pt.append(f"• {label} — {dict(oficial='oficial', mod='tradução DC', traduzido='traduzido/dublado')[st]}")
        elif g["console"] == "switch" or g["console"] == "gba":
            can.append(f"• {label}")
        else:
            cant.append(f"• {label}")
    out = [f"🇧🇷 Em português ({len(pt)}) — aba \"Em português\":", *pt]
    if can:
        out += ["", f"Pode tentar /traduzir ({len(can)}):", *can]
    if cant:
        out += ["", f"Sem tradução automática ({len(cant)}) — PS1/PS2/etc. não têm extrator de texto confiável:", *cant]
    return "\n".join(out)


def _config(P) -> str:
    cfg = ia.load_cfg(P)
    chain = ia.build_chain(P, cfg)
    lines = [f"Idioma: {cfg['idioma_origem']} → {cfg['idioma']} · few-shot: {'sim' if cfg.get('few_shot') else 'não'}",
             "Cadeia de IA:"]
    for p in chain:
        lines.append(f"• {p.name}: {p.model} · {'grátis' if p.free else 'pago'} · chave {ia.mask(p.key)}")
    if not chain:
        lines.append("• (nenhuma disponível)")
    lines.append(f"Tokens hoje (pagos/limitados): {ia.tokens_today(P):,} de {cfg['limite_diario_tokens']:,}".replace(",", "."))
    lines.append(f"Na bateria: {'traduz' if cfg.get('permitir_bateria') else 'espera a tomada'} · "
                 f"bloqueia se > {cfg['flagged_threshold']}% das frases tiverem problema")
    lines.append(f"Arquivo: {ia.write_default_cfg(P)}")
    return "\n".join(lines)


def _review(bot, job: dict) -> str:
    r = job.get("result") or {}
    rep = Path(r.get("mod", "")) / "relatorio.json" if r.get("mod") else None
    samples = []
    if rep and rep.exists():
        samples = json.loads(rep.read_text("utf-8")).get("flagged_samples", [])
    return (job.get("report") or "(sem relatório)") + ("\n\nFrases com problema:\n" + "\n".join(f"• {s}" for s in samples[:15])
                                                       if samples else "")


def _apply(bot, job: dict) -> str:
    P = bot.paths
    r = job.get("result") or {}
    if job["type"] == "translate_switch":
        staged = P.data / "traducao" / "mods" / r.get("title_id", "")
        if not (staged / "romfs").is_dir():
            return "Não há mod guardado para essa tarefa."
        from .switch import install_mod
        dst = install_mod(r["title_id"], staged)
        return f"✅ Mod aplicado: {dst}\nAbra o jogo no Ryujinx. Para desfazer: /traduzir desfazer {job['title']}"
    if job["type"] == "translate_retro":
        pend = P.data / "traducao" / "pendente"
        g = bot._map().get(job["game_id"])
        if not g:
            return "O jogo original não está mais na biblioteca."
        from .retro import output_paths
        out_rom, out_patch = output_paths(Path(g["rom"]))
        src = pend / out_rom.name
        if not src.exists():
            return "Não há ROM traduzida guardada para essa tarefa."
        shutil.move(str(src), str(out_rom))
        if (pend / out_patch.name).exists():
            shutil.move(str(pend / out_patch.name), str(out_patch))
        from .. import syncer
        return "✅ ROM traduzida colocada na biblioteca.\n" + syncer.run_sync(P, bot.store, bot.qbt)
    return "Essa tarefa não tem o que aplicar."


def _approve(bot, job: dict) -> str:
    if job.get("status") != "aguardando aprovação":
        return "Essa tarefa não está esperando aprovação."
    job["args"]["aprovado"] = True
    job.update(status="na fila", notified=False)
    run.save_job(bot.paths, job)
    try:
        bot.store.retry(job["op"])
    except ValueError:
        pass
    run.spawn(bot.paths, job["op"])
    return f"Aprovado. Tradução de {job['title']} começando."


def _resume(bot, job: dict) -> str:
    if job.get("status") in ("concluido",):
        return "Essa tarefa já terminou."
    if run._alive(job.get("pid")):
        return "Ela ainda está rodando."
    op = bot.store.get(job["op"])
    if op and op.state == "running":  # processo morreu (Deck reiniciou): libera para recomeçar
        bot.store.finish(job["op"], False, error="interrompida")
    try:
        bot.store.retry(job["op"])
    except ValueError:
        pass
    job.update(status="na fila", notified=False)
    run.save_job(bot.paths, job)
    run.spawn(bot.paths, job["op"])
    return f"Retomando {job['title']} (o que já foi traduzido não é refeito)."


def _undo(bot, query: str) -> str:
    gid, g, err = _find(bot, query)
    if err:
        return err
    if g["console"] == "switch":
        from .switch import uninstall_mod
        from ..dedup import base_title_id
        tid = base_title_id(Path(g["rom"]).name) or ""
        return ("✅ Mod de tradução removido; o jogo volta ao idioma original." if uninstall_mod(tid)
                else "Esse jogo não tem mod de tradução do Deck Commander.")
    return f"Para tirar a ROM traduzida, use /remover {g['title']} (PT-BR)."


def notify(bot) -> None:
    """Avisa no Telegram quando uma tarefa termina, falha, espera aprovação ou ficou interrompida."""
    chat = bot.cfg.get("notify_chat")
    if not chat:
        return
    for j in run.all_jobs(bot.paths):
        if j.get("notified"):
            continue
        st = j.get("status")
        if st in ("rodando", "aguardando tomada", "pausado (jogo aberto)", "na fila") and j.get("pid") \
                and not run._alive(j["pid"]):
            msg = f"⏹ A tarefa de {j['title']} parou (o Deck reiniciou?). Para continuar: /traduzir retomar {j['op']}"
        elif st == "concluido":
            msg = f"✅ {j['title']}: pronto.\n{j.get('report', '')}"
        elif st == "falhou":
            msg = f"❌ {j['title']}: não deu certo (nada do original foi alterado).\n{j.get('report', '')}"
        elif st == "aguardando aprovação":
            msg = f"💰 {j['title']}: {j.get('report', '')}"
        else:
            continue
        j["notified"] = True
        run.save_job(bot.paths, j)
        bot.send(chat, msg)
