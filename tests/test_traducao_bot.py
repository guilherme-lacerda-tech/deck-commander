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
    x.send = lambda chat, text: x.sent.append(text)
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
