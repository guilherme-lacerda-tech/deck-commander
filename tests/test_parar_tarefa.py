"""Tarefa de tradução travada "viva": o bot avisa e /traduzir parar libera para /traduzir retomar."""
import time

from dc.traducao import comandos, run
from tests.test_traducao_bot import b  # noqa: F401 — mesma fixture do bot de tradução


def test_stalled_job_warns_once_and_stop_then_resume(b, monkeypatch):
    sent = []
    b.send = lambda chat, text, buttons=None: sent.append(text)
    b.cfg["notify_chat"] = 1
    job = run.create(b.paths, b.store, "translate_switch", "switch-jogo", "Jogo", {})
    job.update(status="rodando", pid=4242, progress=[10, 100]); run.save_job(b.paths, job)
    monkeypatch.setattr(run, "_alive", lambda pid: bool(pid))
    comandos.progress_notify(b)                       # começa a acompanhar
    av = comandos._avisos(b.paths); av[job["op"]]["desde"] = time.time() - 46 * 60; comandos._save_avisos(b.paths, av)
    comandos.progress_notify(b); comandos.progress_notify(b)
    stalled = [t for t in sent if "parada em 10/100" in t]
    assert len(stalled) == 1 and f"/traduzir parar {job['op']}" in stalled[0]
    killed = []
    monkeypatch.setattr(comandos.os, "kill", lambda pid, sig: killed.append(pid))
    monkeypatch.setattr("subprocess.run", lambda *a, **k: None)
    r = b.handle(1, 1, f"/traduzir parar {job['op']}")
    assert "Parei Jogo" in r and killed == [4242]
    assert run.load_job(b.paths, job["op"])["status"] == "interrompida"
    monkeypatch.setattr(run, "_alive", lambda pid: False)
    assert "Retomando Jogo" in b.handle(1, 1, f"/traduzir retomar {job['op']}")


def test_stop_finished_job_is_explained(b):
    job = run.create(b.paths, b.store, "translate_switch", "switch-x", "X", {})
    job.update(status="concluido"); run.save_job(b.paths, job)
    assert "não está rodando" in b.handle(1, 1, f"/traduzir parar {job['op']}")
