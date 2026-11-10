"""/traduzir e /converter pelo bot + executor em segundo plano (sem processo de verdade)."""
import json
from pathlib import Path

import pytest

from dc import bot
from dc.paths import get_paths
from dc.traducao import comandos, run, switch


@pytest.fixture
def b(tmp_path, monkeypatch):
    paths = get_paths(tmp_path).ensure()
    monkeypatch.setattr(bot.ops, "game_running", lambda: False)
    x = bot.Bot(paths, "T")
    x.cfg["allowed"] = [1]
    x.cfg["notify_chat"] = 9
    x.sent = []
    x.send = lambda chat, text, buttons=None: x.sent.append(text)
    rom = tmp_path / "roms/switch/Jogo/Jogo [0100ABCD12340000][v0].nsp"
    rom.parent.mkdir(parents=True)
    rom.write_bytes(b"PFS0" + b"\x00" * 60)
    (paths.data / "launch-map.json").write_text(json.dumps({
        "switch-jogo": {"title": "Jogo", "console": "switch", "rom": str(rom)},
        "psx-hercules": {"title": "Hercules", "console": "psx", "rom": str(tmp_path / "h.chd")}}))
    from dc import syncer
    monkeypatch.setattr(syncer, "rom_roots", lambda: [tmp_path / "roms"])
    spawned = []
    monkeypatch.setattr(run, "spawn", lambda paths, op: spawned.append(op))
    x.spawned = spawned
    return x


def test_traduzir_queues_job_and_unsupported_console(b):
    assert "CHD" in b.handle(1, 1, "/traduzir hercules")
    r = b.handle(1, 1, "/traduzir jogo")
    assert "na fila" in r and len(b.spawned) == 1
    job = run.load_job(b.paths, b.spawned[0])
    assert job["type"] == "translate_switch" and job["game_id"] == "switch-jogo"
    assert "Jogo · na fila" in b.handle(1, 1, "/traduzir status")
    assert "Cadeia de IA" in b.handle(1, 1, "/traduzir config")
    assert (b.paths.config / "traducao.toml").exists()


def _no_keys(monkeypatch, msg="o Ryujinx ainda não tem prod.keys (abra um jogo nele uma vez)"):
    from dc.traducao import extract, nca, portugues

    def boom(*a, **k):
        raise nca.NcaError(msg)
    monkeypatch.setattr(switch, "find_romfs", lambda tid: None)
    monkeypatch.setattr(switch, "extract_with_hactool", lambda rom, tid: None)
    monkeypatch.setattr(extract, "extract_texts", boom)
    monkeypatch.setattr(portugues, "detect_switch", lambda *a, **k: {})
    monkeypatch.setattr(run, "_gba_inside", lambda *a: None)


def test_runner_switch_without_keys_explains_extraction(b, monkeypatch):
    _no_keys(monkeypatch)
    b.handle(1, 1, "/traduzir jogo")
    job = run.run(b.paths, b.spawned[0])
    assert job["status"] == "falhou" and "Extrair dados" in job["report"]
    comandos.notify(b); comandos.notify(b)
    assert len(b.sent) == 1 and "não deu certo" in b.sent[0]  # avisa uma vez só


def test_runner_switch_unknown_format_is_refused(b, monkeypatch):
    _no_keys(monkeypatch, "nenhum arquivo de texto reconhecido no jogo")
    b.handle(1, 1, "/traduzir jogo")
    job = run.run(b.paths, b.spawned[0])
    assert job["status"] == "falhou" and "formato padrão da Nintendo" in job["report"]


def test_runner_switch_official_ptbr_needs_no_ai(b, monkeypatch):
    from dc.traducao import portugues
    monkeypatch.setattr(portugues, "detect_switch", lambda paths, lm, roots: {k: {"ptbr": "oficial"} for k in lm})
    b.handle(1, 1, "/traduzir jogo")
    job = run.run(b.paths, b.spawned[0])
    assert job["status"] == "concluido" and "OFICIAL" in job["report"] and job["result"]["provider"] == "oficial"


def test_runner_switch_success_registers_and_blocks_repeat(b, monkeypatch, tmp_path):
    romfs = tmp_path / "romfs"; romfs.mkdir()
    monkeypatch.setattr(switch, "find_romfs", lambda tid: romfs)

    def fake(paths, tid, rf, name="", force_font=False, chain=None, log=None, progress=None, should_pause=None):
        progress(5, 5)
        r = switch.Report(tid); r.msbt_count, r.strings, r.translated, r.applied, r.mod_dir = 1, 5, 5, True, "/mod"
        return r
    monkeypatch.setattr(switch, "translate_game", fake)
    b.handle(1, 1, "/traduzir jogo")
    job = run.run(b.paths, b.spawned[0])
    assert job["status"] == "concluido" and job["result"]["title_id"] == "0100ABCD12340000"
    assert b.store.get(job["op"]).state == "done"
    comandos.notify(b)
    assert "pronto" in b.sent[-1]
    assert "já foi traduzido" in b.handle(1, 1, "/traduzir jogo")
    assert "na fila" in b.handle(1, 1, "/traduzir jogo --forcar")


def test_paid_provider_waits_for_approval(b, monkeypatch, tmp_path):
    romfs = tmp_path / "romfs"; romfs.mkdir()
    monkeypatch.setattr(switch, "find_romfs", lambda tid: romfs)
    (b.paths.config / "traducao.toml").write_text('provider = "openai"\nfallback = []\n')
    (b.paths.secrets / "ia_api.key").write_text("sk-xyz")
    b.handle(1, 1, "/traduzir jogo")
    job = run.run(b.paths, b.spawned[0])
    assert job["status"] == "aguardando aprovação" and "/traduzir aprovar" in job["report"]
    comandos.notify(b)
    assert "💰" in b.sent[-1]
    assert "começando" in b.handle(1, 1, f"/traduzir aprovar {job['op']}")
    assert run.load_job(b.paths, job["op"])["args"]["aprovado"] is True and len(b.spawned) == 2


def test_interrupted_job_is_reported_and_resumable(b):
    b.handle(1, 1, "/traduzir jogo")
    job = run.load_job(b.paths, b.spawned[0])
    job.update(status="rodando", pid=999999999)  # processo que não existe mais
    run.save_job(b.paths, job)
    comandos.notify(b)
    assert "parou" in b.sent[-1] and "retomar" in b.sent[-1]
    assert "Retomando" in b.handle(1, 1, f"/traduzir retomar {job['op']}")


def test_converter_diagnose_and_undo(b):
    assert "nada a fazer" in b.handle(1, 1, "/converter jogo")
    assert "não tem mod" in b.handle(1, 1, "/traduzir desfazer jogo")
    assert "só para jogos de Switch" in b.handle(1, 1, "/converter hercules")


def test_auto_queue_translates_new_downloads_not_in_portuguese(b, monkeypatch, tmp_path):
    lm = json.loads((b.paths.data / "launch-map.json").read_text())
    iso = tmp_path / "roms/ps2/Okami/Okami.iso"
    iso.parent.mkdir(parents=True); iso.write_bytes(b"x")
    lm["ps2-okami"] = {"title": "Okami", "console": "ps2", "rom": str(iso)}
    lm["ps2-gow"] = {"title": "God of War (Dublado)", "console": "ps2", "rom": str(iso.with_name("gow.iso"))}
    (b.paths.data / "launch-map.json").write_text(json.dumps(lm))
    lines = run.auto_queue(b.paths, b.store, ["ps2-okami", "ps2-gow", "psx-hercules"])
    assert any("Okami" in l and "traduzindo sozinho" in l for l in lines)
    assert any("God of War" in l and "já está em português" in l for l in lines)
    assert not any("Hercules" in l for l in lines)  # .chd: não dá, não incomoda
    assert len(b.spawned) == 1
    assert run.auto_queue(b.paths, b.store, ["ps2-okami"]) == [] and len(b.spawned) == 1  # sem fila dupla
    (b.paths.config / "traducao.toml").write_text("auto_traduzir = false\n")
    assert run.auto_queue(b.paths, b.store, ["ps2-okami"]) == []


def test_out_of_standard_offer_asks_yes_no_and_runs_on_yes(b):
    asked = []
    b.send = lambda chat, text, buttons=None: asked.append((text, buttons))
    job = run.offer_generic(b.paths, b.store, "switch-jogo", "Jogo", "tradução padrão falhou")
    assert job["status"] == "aguardando sim"
    assert run.offer_generic(b.paths, b.store, "switch-jogo", "Jogo", "de novo") is None  # não pergunta 2x
    comandos.notify(b)
    text, buttons = asked[-1]
    assert "fora do padrão" in text and buttons == ["Sim", "Não"]
    r = b.handle(1, 1, "Sim")
    assert "começou" in r and b.spawned == [job["op"]]
    assert run.load_job(b.paths, job["op"])["status"] == "na fila"
    assert "pergunta_op" not in b.cfg


def test_out_of_standard_no_keeps_game(b):
    b.send = lambda chat, text, buttons=None: None
    job = run.offer_generic(b.paths, b.store, "switch-jogo", "Jogo", "x")
    comandos.notify(b)
    assert "fica como está" in b.handle(1, 1, "não")
    assert run.load_job(b.paths, job["op"])["status"] == "recusado" and b.spawned == []


def test_out_of_standard_not_offered_for_iso_consoles(b):
    assert run.offer_generic(b.paths, b.store, "psx-hercules", "Hercules", "x") is None


def test_progress_every_20_percent_with_eta(b, monkeypatch):
    import time as _t
    job = run.create(b.paths, b.store, "translate_switch", "switch-jogo", "Jogo", {})
    job.update(status="rodando", progress=[100, 1000]); run.save_job(b.paths, job)
    now = [1000.0]
    monkeypatch.setattr(_t, "time", lambda: now[0])
    comandos.progress_notify(b)
    assert "Acompanhando Jogo: 10%" in b.sent[-1]
    job["progress"] = [250, 1000]; run.save_job(b.paths, job); now[0] += 150
    comandos.progress_notify(b)
    assert "20% traduzido" in b.sent[-1] and "60 frases/min" in b.sent[-1] and "faltam" in b.sent[-1]
    n = len(b.sent)
    comandos.progress_notify(b)
    assert len(b.sent) == n  # mesma faixa: não repete
    assert "25% (250/1000)" in b.handle(1, 1, "/traduzir status")


def test_traduzir_biblioteca_asks_then_queues_two_at_a_time(b, monkeypatch, tmp_path):
    """/traduzir biblioteca: mostra quantos entram e quantos não têm tradutor, pergunta (Sim/Não), e só então
    enfileira; lança no máximo MAX_JOBS processos — o resto entra quando abre vaga (kick_queue)."""
    from dc.traducao import ia
    lm = json.loads((b.paths.data / "launch-map.json").read_text())
    roms = tmp_path / "roms/switch"
    for i in range(3):
        r = roms / f"J{i}/J{i} [0100ABCD1234{i}000][v0].nsp"
        r.parent.mkdir(parents=True); r.write_bytes(b"PFS0")
        lm[f"switch-j{i}"] = {"title": f"J{i}", "console": "switch", "rom": str(r)}
    lm["ps2-pt"] = {"title": "Jogo (PT-BR)", "console": "ps2", "rom": "/x/Jogo (PT-BR).iso"}
    (b.paths.data / "launch-map.json").write_text(json.dumps(lm))
    monkeypatch.setattr(ia, "build_chain", lambda *a: ["x"])
    r = b.handle(1, 1, "/traduzir biblioteca")
    assert "vão entrar na fila: 4" in r and "já em português: 1" in r and "sem tradutor automático: 1" in r
    assert b.next_buttons == [("Sim", "/traduzir biblioteca sim"), ("Não", "/traduzir biblioteca nao")]
    assert b.spawned == [] and run.all_jobs(b.paths) == []  # nada antes do Sim
    assert "nada foi enfileirado" in b.handle(1, 1, "/traduzir biblioteca nao")
    r = b.handle(1, 1, "/traduzir biblioteca sim")
    assert "4 jogo(s) na fila" in r
    jobs = run.all_jobs(b.paths)
    assert len(jobs) == 4 and all(j["args"].get("lote") for j in jobs)
    assert len(b.spawned) == run.MAX_JOBS  # não abre um processo por jogo
    # processos lançados "vivos": nada novo; um terminou: entra o próximo
    monkeypatch.setattr(run, "_alive", lambda pid: pid == 1)
    for j in jobs:
        if j["op"] in b.spawned:
            j["pid"] = 1; run.save_job(b.paths, j)
    assert run.kick_queue(b.paths) == []
    j0 = run.load_job(b.paths, b.spawned[0]); j0.update(status="concluido"); j0.pop("pid"); run.save_job(b.paths, j0)
    assert len(run.kick_queue(b.paths)) == 1
    # de novo: nada repetido
    assert "Nada novo" in b.handle(1, 1, "/traduzir biblioteca sim") or "vão entrar na fila: 0" in b.handle(
        1, 1, "/traduzir biblioteca")


def test_runner_crash_log_has_date_and_task(b, monkeypatch):
    """traducao.log: cada erro com data/hora, código da tarefa e jogo (antes só o traceback solto)."""
    def boom(*a, **k):
        raise RuntimeError("falha de teste")
    monkeypatch.setattr(run, "_dispatch", boom)
    job = run.create(b.paths, b.store, "translate_switch", "switch-jogo", "Jogo", {})
    run.run(b.paths, job["op"])
    log = (b.paths.logs / "traducao.log").read_text("utf-8")
    assert f"tarefa {job['op']} (translate_switch) — Jogo" in log and "falha de teste" in log
