"""Comandos do bot para as adições A1/A2/A3 (/traduzir e /converter) e o aviso de fim de tarefa."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from .. import ops
from . import ia, run

HELP = """/traduzir <jogo> — traduz para pt-BR com IA (Switch: vira mod; GBA Pokémon: ROM nova "(PT-BR)")
/traduzir biblioteca — todos os jogos que ainda não estão em português (pergunta antes)
/traduzir lista · status · config · revisar <op> · aplicar <op> · aprovar <op> · parar <op> · retomar <op> · desfazer <jogo>
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
        return "\n".join(_status_line(P, j) for j in reversed(js))
    if sub == "parar" and len(args) == 2:
        job = run.load_job(P, args[1])
        return _stop(bot, job) if job else "Não achei essa tarefa (veja /traduzir status)."
    if sub in ("revisar", "aplicar", "aprovar", "retomar") and len(args) == 2:
        job = run.load_job(P, args[1])
        if not job:
            return "Não achei essa tarefa (veja /traduzir status)."
        return {"revisar": _review, "aplicar": _apply, "aprovar": _approve, "retomar": _resume}[sub](bot, job)
    if sub == "desfazer" and len(args) > 1:
        return _undo(bot, " ".join(args[1:]))
    if sub == "lista":
        return _lista(bot)
    if sub == "biblioteca":
        return _biblioteca(bot, args[1].lower() if len(args) > 1 else "")
    if sub == "fora" and len(args) == 3 and args[2].lower() in ("sim", "nao", "não"):
        # resposta pelo botão da própria pergunta: vale para ESTA tarefa, mesmo com outras perguntas abertas
        if bot.cfg.get("pergunta_op") == args[1]:
            bot.cfg.pop("pergunta_op", None); bot.save_cfg()
        return run.answer_generic(P, args[1], args[2].lower() == "sim")
    if sub == "motor" and len(args) == 3 and args[2].lower() in ("sim", "nao", "não"):
        if bot.cfg.get("pergunta_op") == args[1]:
            bot.cfg.pop("pergunta_op", None); bot.save_cfg()
        return run.answer_motor(P, args[1], args[2].lower() == "sim")
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
        from pathlib import Path as _P
        from .rts import supported
        okc, why = supported(g["console"], _P(g["rom"]))
        if not okc:
            return f"{g['title']}: não dá para traduzir automaticamente — {why}."
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


def _biblioteca(bot, resp: str) -> str:
    """Traduzir a biblioteca inteira: mostra quantos entram e pergunta (Sim/Não) antes de começar."""
    P, S = bot.paths, bot.store
    if ops.in_safe_mode(P):
        return "Safe-mode ativo."
    if resp in ("nao", "não", "n"):
        return "Ok, nada foi enfileirado."
    plan = run.library_plan(P, S)
    lm = bot._map()
    if resp in ("sim", "s"):
        cfg = ia.load_cfg(P)
        if not ia.build_chain(P, cfg):
            return "Nenhuma IA disponível: instale o Ollama no Deck (./setup-deck.sh --modules A1) ou configure uma chave."
        lines = run.auto_queue(P, S, plan["ok"], lote=True)
        if not lines:
            return "Nada novo para traduzir: tudo já está em português, traduzido ou na fila."
        extra = "" if not run._power_paused(P, cfg) else "\n🔌 Começa quando o Deck for para a tomada."
        more = f"\n… e mais {len(lines) - 40}" if len(lines) > 40 else ""
        return (f"🈯 {len(lines)} jogo(s) na fila de tradução ({run.MAX_JOBS} de cada vez; aviso cada um que "
                f"terminar):\n" + "\n".join(lines[:40]) + more + "\nAcompanhe com /traduzir status." + extra)
    n = len(plan["ok"])
    sem = len(plan["sem"]) + len(plan["generico"])
    out = [f"📚 Biblioteca: {sum(len(v) for v in plan.values())} jogos",
           f"🇧🇷 já em português: {len(plan['pt'])}",
           f"🈯 vão entrar na fila: {n}"]
    out += [f"   • {lm[g]['title']} ({lm[g]['console']})" for g in plan["ok"][:25]]
    if n > 25:
        out.append(f"   … e mais {n - 25}")
    if plan["fila"] or plan["feito"]:
        out.append(f"⏳ já traduzindo ou na fila: {len(plan['fila'])} · ✅ já traduzidos: {len(plan['feito'])}")
    if plan["falhou"]:
        out.append(f"⚠️ já tentei e não deu (não entram de novo): {len(plan['falhou'])} — "
                   + ", ".join(lm[g]["title"] for g in plan["falhou"][:5]))
    gen = (f" (destes, {len(plan['generico'])} só teriam a tradução fora do padrão, que pergunta jogo a jogo"
           ")") if plan["generico"] else ""
    out.append(f"🚫 sem tradutor automático: {sem}{gen}")
    if not n:
        return "\n".join(out + ["", "Nada novo para traduzir."])
    bot.next_buttons = [("Sim", "/traduzir biblioteca sim"), ("Não", "/traduzir biblioteca nao")]
    return "\n".join(out + ["", f"Começar a traduzir os {n}? Vai de {run.MAX_JOBS} em {run.MAX_JOBS}, "
                                "pode levar dias; nada do jogo original é alterado."])


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
        elif idi.get(gid, {}).get("formato") == "fechado":
            m = idi[gid].get("motor")
            cant.append(f"• {label} — formato próprio do jogo" + (f" (motor: {m})" if m else "")
                        + " — tenta de novo sozinho quando eu aprender o formato")
        elif idi.get(gid, {}).get("pouco_texto"):
            cant.append(f"• {label} — quase não tem texto comum (voz/imagem)")
        elif g["console"] == "switch":
            can.append(f"• {label}")
        else:
            from pathlib import Path as _P
            from .rts import supported
            okc, why = supported(g["console"], _P(g.get("rom", "")))
            (can if okc else cant).append(f"• {label}" + ("" if okc else f" — {why}"))
    out = [f"🇧🇷 Em português ({len(pt)}) — aba \"Em português\":", *pt]
    if can:
        out += ["", f"Pode tentar /traduzir ({len(can)}):", *can]
    if cant:
        out += ["", f"Sem tradução automática ({len(cant)}):", *cant]
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


TRAVADA_MIN = 45  # "rodando" sem nenhum progresso por tanto tempo = provavelmente travada


def _stop(bot, job: dict) -> str:
    """Para uma tarefa (ex.: travada). O que já foi traduzido fica no cache: /traduzir retomar continua dali."""
    import signal
    import subprocess
    if job.get("status") in ("concluido", "falhou", "interrompida", "recusado"):
        return f"{job['title']} não está rodando ({job.get('status')})."
    pid = job.get("pid")
    if run._alive(pid):
        subprocess.run(["systemctl", "--user", "stop", f"deck-commander-traducao-{job['op']}"], capture_output=True)
        if run._alive(pid):
            try:
                os.kill(int(pid), signal.SIGTERM)
            except OSError:
                pass
    job = run.load_job(bot.paths, job["op"]) or job
    job.update(status="interrompida", notified=True)
    job.pop("pid", None)
    run.save_job(bot.paths, job)
    try:
        bot.store.finish(job["op"], False, error="interrompida pelo usuário")
    except (ValueError, KeyError):
        pass
    return (f"⏹ Parei {job['title']}. O que já foi traduzido está guardado; para continuar de onde parou: "
            f"/traduzir retomar {job['op']}")


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


ATIVOS = ("rodando", "aguardando tomada", "pausado (jogo aberto)", "na fila")


def _avisos_path(P):
    return P.state / "traducao-avisos.json"


def _avisos(P) -> dict:
    try:
        return json.loads(_avisos_path(P).read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def _save_avisos(P, data: dict) -> None:
    f = _avisos_path(P)
    tmp = f.with_name(f.name + ".tmp")
    tmp.write_text(json.dumps(data), "utf-8")
    os.replace(tmp, f)


def _fmt_dur(sec: float) -> str:
    m = int(sec // 60)
    return f"{m // 60} h {m % 60:02d} min" if m >= 60 else f"{max(m, 1)} min"


def _eta(P, j: dict) -> str:
    """Previsão pelo ritmo medido desde que o bot começou a acompanhar a tarefa."""
    import time
    from datetime import datetime, timedelta
    d, tot = (j.get("progress") or [0, 0])[:2]
    a = _avisos(P).get(j["op"])
    if not a or not tot or d <= a["d0"]:
        return ""
    rate = (d - a["d0"]) / max(1.0, time.time() - a["t0"])  # frases por segundo
    left = (tot - d) / rate
    fim = (datetime.now() + timedelta(seconds=left)).strftime("%H:%M")
    return f" · {rate * 60:.0f} frases/min · faltam ~{_fmt_dur(left)} (termina ~{fim})"


def _status_line(P, j: dict) -> str:
    d, tot = (j.get("progress") or [0, 0])[:2]
    pct = f" {d * 100 // tot}% ({d}/{tot})" if tot else ""
    return f"{j['title']} · {j['status']}{pct}{_eta(P, j) if j.get('status') in ATIVOS else ''}"


def progress_notify(bot) -> None:
    """Aviso a cada 20% de cada tradução em andamento, com a previsão de término."""
    import time
    chat = bot.cfg.get("notify_chat")
    P = bot.paths
    av = _avisos(P)
    changed = False
    for j in run.all_jobs(P):
        d, tot = (j.get("progress") or [0, 0])[:2]
        if j.get("status") not in ATIVOS or not tot:
            continue
        a = av.get(j["op"])
        if a is not None and j.get("status") == "rodando":  # vigia: rodando sem progresso por muito tempo
            if a.get("ultimo_d") != d:
                a.update(ultimo_d=d, desde=time.time(), travada=False); changed = True
            elif not a.get("travada") and time.time() - a.get("desde", time.time()) > TRAVADA_MIN * 60:
                a["travada"] = True; changed = True
                if chat:
                    bot.send(chat, f"⚠️ {j['title']} está parada em {d}/{tot} há {TRAVADA_MIN} min (a IA pode ter "
                                   f"travado). Para destravar: /traduzir parar {j['op']} e depois "
                                   f"/traduzir retomar {j['op']} (nada traduzido se perde).")
        if a is None:  # começa a acompanhar: ponto de partida do ritmo (não avisa faixas já passadas)
            av[j["op"]] = {"t0": time.time(), "d0": d, "faixa": d * 5 // tot, "ultimo_d": d, "desde": time.time()}
            changed = True
            if chat:
                bot.send(chat, f"📊 Acompanhando {j['title']}: {d * 100 // tot}% ({d}/{tot}). "
                               "Aviso a cada 20%, com a previsão de término.")
            continue
        faixa = d * 5 // tot  # 0..5 (cada faixa = 20%)
        if a["faixa"] < faixa < 5:
            a["faixa"] = faixa
            changed = True
            if chat:
                bot.send(chat, f"⏳ {j['title']}: {faixa * 20}% traduzido ({d}/{tot}){_eta(P, j)}")
    if changed:
        _save_avisos(P, av)


def notify(bot) -> None:
    """Avisa no Telegram quando uma tarefa termina, falha, espera aprovação ou ficou interrompida."""
    chat = bot.cfg.get("notify_chat")
    run.kick_queue(bot.paths)  # "/traduzir biblioteca": abre vaga => próximo jogo começa
    if not chat:
        return
    for j in run.all_jobs(bot.paths):
        if j.get("notified"):
            continue
        st = j.get("status")
        if st == "na fila" and (j.get("args") or {}).get("lote") and not j.get("started"):
            continue  # lote ainda esperando a vez: kick_queue relança sozinho (mesmo depois de reiniciar)
        if st in ("rodando", "aguardando tomada", "pausado (jogo aberto)", "na fila") and j.get("pid") \
                and not run._alive(j["pid"]):
            msg = f"⏹ A tarefa de {j['title']} parou (o Deck reiniciou?). Para continuar: /traduzir retomar {j['op']}"
        elif st == "concluido":
            msg = f"✅ {j['title']}: pronto.\n{j.get('report', '')}"
        elif st == "falhou":
            msg = f"❌ {j['title']}: não deu certo (nada do original foi alterado).\n{j.get('report', '')}"
            rep = (j.get("report") or "").lower()
            formato = any(w in rep for w in ("formato", "não traduzi para não estragar", "msbt", "fora do padrão")) \
                and not any(w in rep for w in ("ncz", "nsz", "comprimido", "prod.keys", "espaço"))
            if j.get("type") != "translate_generic" and formato:  # só quando o problema é o formato do texto
                offer = run.offer_generic(bot.paths, bot.store, j["game_id"], j["title"], "tradução padrão falhou")
                if offer:
                    msg += "\n\nPosso tentar a tradução fora do padrão (próxima mensagem)."
        elif st == "aguardando sim":
            j["notified"] = True
            run.save_job(bot.paths, j)
            bot.cfg["pergunta_op"] = j["op"]
            bot.save_cfg()
            bot.send(chat, (f"🧩 {j['title']}: tradução fora do padrão — deseja traduzir?\n"
                            "O texto deste jogo não está num formato conhecido. Eu procuro as frases nos arquivos, "
                            "só troco o que cabe no mesmo espaço (sem risco de quebrar o jogo) e uso só as IAs "
                            "locais do PC/Deck. Se não achar nada seguro, aviso e não mexo em nada."),
                     buttons=[("Sim", f"/traduzir fora {j['op']} sim"), ("Não", f"/traduzir fora {j['op']} nao")])
            continue
        elif st == "aguardando ok":
            from .motores import fmt_minutes
            of = j.get("oferta") or {}
            j["notified"] = True
            run.save_job(bot.paths, j)
            bot.cfg["pergunta_op"] = j["op"]
            bot.save_cfg()
            txt = (f"🧩 {j['title']} é feito em {of.get('motor', '?')}. Agora eu sei traduzir esse tipo de jogo.\n"
                   f"Achei {of.get('frases', 0)} frases; tempo estimado: {fmt_minutes(int(of.get('minutos', 1)))} "
                   "(só com as IAs locais do PC/Deck; o jogo original não é alterado, vira um mod).")
            if of.get("aviso"):
                txt += f"\nObs.: {of['aviso']}"
            bot.send(chat, txt + "\nQuer que eu traduza?",
                     buttons=[("Sim", f"/traduzir motor {j['op']} sim"), ("Não", f"/traduzir motor {j['op']} nao")])
            continue
        elif st == "aguardando aprovação":
            msg = f"💰 {j['title']}: {j.get('report', '')}"
        else:
            continue
        j["notified"] = True
        run.save_job(bot.paths, j)
        bot.send(chat, msg.replace("<jogo>", j.get("game_id", "<jogo>")))
