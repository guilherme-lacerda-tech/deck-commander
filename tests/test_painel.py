"""Painel do Deck (dc/painel.py): ações em JSON que reaproveitam os comandos do bot."""
import base64
import json
import tomllib

import pytest

from dc import painel, qr
from dc.paths import get_paths
from dc.qbt import QbtError

TOKEN = "123456789:" + "A" * 35


class FakeQbt:
    def __init__(self, torrents=None, down=False):
        self.ts = torrents or []
        self.down = down
        self.paused, self.resumed, self.deleted = [], [], []

    def torrents(self, *a, **k):
        if self.down:
            raise QbtError("qBittorrent indisponível")
        return self.ts

    def pause(self, hs):
        self.paused += hs

    def resume(self, hs):
        self.resumed += hs

    def delete(self, h, delete_files=False):
        self.deleted.append((h, delete_files))


@pytest.fixture
def P(tmp_path, monkeypatch):
    monkeypatch.setenv("DC_ROOT", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    return get_paths(tmp_path).ensure()


def _lm(P, lm):
    (P.data / "launch-map.json").write_text(json.dumps(lm), "utf-8")


def run(P, acao, args=None, qbt=None):
    return painel.executar(acao, args, ponte=painel.Ponte(P, qbt=qbt or FakeQbt()))


def test_qr_svg_valid_and_square():
    s = qr.svg("https://t.me/BotFather")
    assert s.startswith("<svg") and 'fill="#fff"' in s and s.count("h1v1h-1z") > 100


def test_status_lists_downloads_space_and_safe_mode(P):
    q = FakeQbt([{"hash": "h1", "name": "Jogo A", "progress": 0.5, "state": "downloading", "eta": 600, "dlspeed": 2048},
                 {"hash": "h2", "name": "Jogo B", "progress": 1, "state": "stalledUP"}])
    (P.state / "SAFE_MODE").write_text("2026-11-10T00:00 testes falharam\n")
    r = run(P, "status", qbt=q)
    assert r["ok"] and r["safe_mode"] and r["safe_motivo"] == "testes falharam"
    a, b = r["downloads"]
    assert (a["pct"], a["estado"], a["eta_min"], a["velocidade_kb"]) == (50, "baixando", 10, 2)
    assert b["concluido"] and b["estado"] == "concluído"
    assert r["espaco"][0]["onde"] == "memória interna"


def test_status_with_qbittorrent_down_is_friendly(P):
    r = run(P, "status", qbt=FakeQbt(down=True))
    assert r["ok"] and r["downloads"] == [] and "não está respondendo" in r["erro_downloads"]


def test_pause_and_resume(P):
    q = FakeQbt([{"hash": "h1", "name": "x", "state": "downloading"}, {"hash": "h2", "name": "y", "state": "queuedDL"}])
    assert "2 download(s) pausado" in run(P, "downloads_pausar", qbt=q)["texto"]
    run(P, "downloads_retomar", {"hash": "h2"}, qbt=q)
    assert q.paused == ["h1", "h2"] and q.resumed == ["h2"]
    r = run(P, "downloads_pausar", qbt=FakeQbt(down=True))
    assert not r["ok"] and "qBittorrent" in r["erro"]


def test_battery_toggle_uses_bot_logic(P):
    assert "também na bateria" in run(P, "bateria", {"permitir": True})["texto"]
    assert json.loads((P.config / "power.json").read_text())["allow_on_battery"] is True
    r = run(P, "downloads")
    assert r["bateria_permitida"] is True and "Fora da tomada: baixa" in r["texto_bateria"]
    run(P, "bateria", {"permitir": False})
    assert json.loads((P.config / "power.json").read_text())["allow_on_battery"] is False


def test_painel_never_writes_telegram_json(P):
    cfg = {"allowed": [1], "notify_chat": 9}
    (P.config / "telegram.json").write_text(json.dumps(cfg))
    run(P, "duplicados")
    assert json.loads((P.config / "telegram.json").read_text()) == cfg


def test_duplicate_download_removal_needs_confirmation(P):
    q = FakeQbt([{"hash": "hh", "name": "Copia", "state": "stalledUP", "size": 10**9}])
    r = run(P, "remover", {"hash": "hh", "nome": "Copia"}, qbt=q)
    assert r["ok"] and not r["feito"] and "Apagar o download repetido" in r["texto"] and "/remover" not in r["texto"]
    assert q.deleted == []
    r = run(P, "remover", {"hash": "hh", "nome": "Copia", "confirmar": True}, qbt=q)
    assert r["feito"] and q.deleted == [("hh", True)]


def test_remove_game_shows_plan_first(P, tmp_path, monkeypatch):
    monkeypatch.setattr("dc.ops.game_running", lambda: False)
    rom = tmp_path / "Emulation/roms/gba/Jogo.gba"
    rom.parent.mkdir(parents=True)
    rom.write_bytes(b"x" * 10)
    _lm(P, {"gba-jogo": {"title": "Jogo", "console": "gba", "rom": str(rom)}})
    r = run(P, "remover", {"gid": "gba-jogo"})
    assert r["ok"] and "Remover «Jogo»" in r["texto"] and "Confirme" not in r["texto"]
    assert rom.exists()


def test_telegram_token_rejects_bad_format_without_echo(P, monkeypatch):
    r = run(P, "telegram_token", {"token": "abc"})
    assert not r["ok"] and "não parece um token" in r["erro"]
    monkeypatch.setattr("dc.telegram_setup.bot_username", lambda t: None)
    r = run(P, "telegram_token", {"token": TOKEN})
    assert not r["ok"] and TOKEN not in json.dumps(r)
    assert not (P.secrets / "telegram").exists()


def test_telegram_token_saves_and_returns_pairing_qr(P, monkeypatch):
    monkeypatch.setattr("dc.telegram_setup.bot_username", lambda t: "meu_bot" if t == TOKEN else None)
    started = []
    monkeypatch.setattr("dc.telegram_setup._start_bot_service", lambda: started.append(1))
    r = run(P, "telegram_token", {"token": TOKEN + TOKEN})  # colado duas vezes
    assert r["ok"] and r["usuario"] == "meu_bot" and started
    assert (P.secrets / "telegram").read_text().strip() == TOKEN
    assert TOKEN not in json.dumps(r)
    code = (P.state / "telegram-pairing").read_text()
    assert r["link"] == f"https://t.me/meu_bot?start={code}"
    assert base64.b64decode(r["qr"].split(",", 1)[1]).startswith(b"<svg")
    assert TOKEN not in (P.logs / "painel.log").read_text()
    st = run(P, "telegram")
    assert st["configurado"] and st["usuario"] == "meu_bot" and not st["pareado"] and st["codigo_aberto"]


def test_botfather_qr(P):
    r = run(P, "telegram_botfather")
    assert r["ok"] and r["link"] == "https://t.me/BotFather" and r["qr"].startswith("data:image/svg+xml;base64,")


def test_unexpected_error_is_friendly_and_token_scrubbed(P, monkeypatch):
    def boom(p, a):
        raise RuntimeError("falhou com " + TOKEN)
    monkeypatch.setitem(painel.ACOES, "status", boom)
    r = run(P, "status")
    assert not r["ok"] and "RuntimeError" in r["erro"] and TOKEN not in r["erro"]
    log = (P.logs / "painel.log").read_text()
    assert "falhou com ***" in log and TOKEN not in log
    assert run(P, "nada")["erro"].startswith("Ação desconhecida")


def test_auto_translation_toggle_keeps_toml_valid(P):
    from dc.traducao import ia
    run(P, "traducao_automatica", {"ligar": False})
    assert ia.load_cfg(P)["auto_traduzir"] is False
    run(P, "traducao_automatica", {"ligar": True})
    txt = (P.config / "traducao.toml").read_text()
    assert txt.count("auto_traduzir") == 1 and tomllib.loads(txt)["auto_traduzir"] is True
    assert tomllib.loads(txt)["providers"]["ollama"]["modelo"]  # seções intactas


def _job(P, **kw):
    from dc.traducao import run as trun
    job = {"op": "op1", "type": "translate_generic", "game_id": "g", "title": "Jogo X", "args": {}, **kw}
    trun.save_job(P, job)
    return job


def test_translation_questions_answered_in_panel(P, monkeypatch):
    from dc.traducao import run as trun
    spawned = []
    monkeypatch.setattr(trun, "spawn", lambda paths, op: spawned.append(op))
    _job(P, status="aguardando sim")
    r = run(P, "traducao")
    assert r["perguntas"][0]["tipo"] == "fora" and "Traduzir?" in r["perguntas"][0]["texto"]
    assert run(P, "status")["perguntas"] == 1
    r = run(P, "traducao_responder", {"op": "op1", "sim": True})
    assert "começou" in r["texto"] and spawned == ["op1"]
    assert run(P, "traducao_responder", {"op": "op1", "sim": False})["texto"] == "Essa pergunta já foi respondida."


def test_motor_question_no(P):
    _job(P, status="aguardando ok", type="translate_switch", oferta={"motor": "Unity", "frases": 100, "minutos": 5})
    q = run(P, "traducao")["perguntas"][0]
    assert q["tipo"] == "motor" and "Unity" in q["texto"]
    assert "fica como está" in run(P, "traducao_responder", {"op": "op1", "sim": False})["texto"]


def test_translation_tasks_progress_and_stop(P, monkeypatch):
    from dc.traducao import run as trun
    _job(P, status="interrompida", progress=[50, 200])
    r = run(P, "traducao")
    t = r["tarefas"][0]
    assert t["pode_retomar"] and not t["pode_parar"] and "25%" in t["linha"]
    assert "não está rodando" in run(P, "traducao_parar", {"op": "op1"})["texto"]
    assert "Não achei" in run(P, "traducao_retomar", {"op": "zzz"})["texto"]


def test_pc_config_validation_and_secret_hidden(P):
    assert not run(P, "pc_salvar", {"host_casa": "abc"})["ok"]
    assert "MAC inválido" in run(P, "pc_salvar", {"mac": "12"})["erro"]
    r = run(P, "pc_salvar", {"host_casa": "192.168.0.10", "rede_casa": "192.168.0", "mac": "aa:bb:cc:dd:ee:ff",
                             "porteiro": "http://10.0.0.2:8080/acordar", "codigo": "segredo"})
    assert r["ok"]
    r = run(P, "pc")
    assert r["rede_casa"] == "192.168.0." and r["mac"] == "AA:BB:CC:DD:EE:FF" and r["codigo_definido"]
    assert "segredo" not in json.dumps(r)
    run(P, "pc_salvar", {"host_casa": "192.168.0.11"})  # sem "codigo": mantém o que existe
    assert run(P, "pc")["codigo_definido"]


def test_pc_test_requires_ip_and_reports(P, monkeypatch):
    assert "Preencha antes" in run(P, "pc_testar")["erro"]
    run(P, "pc_salvar", {"host_casa": "192.168.0.10"})
    monkeypatch.setattr("dc.pc_remoto.online", lambda cfg, timeout=2.0: "192.168.0.10")
    monkeypatch.setattr("dc.pc_remoto.em_casa", lambda cfg: True)
    r = run(P, "pc_testar")
    assert r["acordado"] and r["em_casa"] and "acordado" in r["texto"]


def test_pc_wake_failure_is_error(P, monkeypatch):
    monkeypatch.setattr("dc.pc_remoto.acordar", lambda cfg: (False, "sem o MAC do PC na config"))
    r = run(P, "pc_acordar")
    assert not r["ok"] and "MAC" in r["erro"]


def test_transfer_list_prepare_and_send(P, tmp_path, monkeypatch):
    rom = tmp_path / "Emulation/roms/gba/Jogo.gba"
    rom.parent.mkdir(parents=True)
    rom.write_bytes(b"x" * 1000)
    _lm(P, {"gba-jogo": {"title": "Jogo", "console": "gba", "rom": str(rom)},
            "pc-fortnite": {"title": "Fortnite", "console": "pc", "rom": "pc:Fortnite"}})
    r = run(P, "transferir")
    assert [j["gid"] for j in r["jogos"]] == ["gba-jogo"] and r["fila"] == []
    r = run(P, "transferir_preparar", {"gid": "gba-jogo"})
    assert r["ok"] and r["titulo"] == "Jogo" and r["arquivos"] >= 1
    monkeypatch.setattr("dc.transferir._acordar_pc", lambda bot: " Acordei o PC.")
    r = run(P, "transferir_enviar", {"gid": "gba-jogo"})
    assert "na fila para o PC" in r["texto"] and "/transferir" not in r["texto"]
    assert run(P, "transferir")["fila"][0]["status"] == "na fila"


def test_trazer_do_pc_list_prepare_and_send(P, monkeypatch):
    lista = {"em": "agora", "emuladores_pc": {"duckstation": {}},
             "jogos": [{"id": "psx-hercules", "titulo": "Hercules", "console": "psx", "emulador": "duckstation",
                        "tamanho": 391_000_000, "arquivos": 3, "resumo": {"jogo": {"arquivos": 2, "bytes": 390_000_000}}}]}
    (P.data / "pc-jogos-transferiveis.json").write_text(json.dumps(lista), "utf-8")
    monkeypatch.setattr("dc.receber.flatpak_info", lambda i: None)
    r = run(P, "transferir")
    assert r["jogos_pc"] == [{"gid": "psx-hercules", "titulo": "Hercules", "console": "psx", "tamanho": "0.39 GB"}]
    r = run(P, "trazer_preparar", {"gid": "psx-hercules"})
    assert r["ok"] and r["tamanho"] == "0.39 GB" and "vai ser instalado no Deck" in r["resumo"]
    assert not run(P, "trazer_preparar", {"gid": "nao-existe"})["ok"]
    monkeypatch.setattr("dc.transferir._acordar_pc", lambda bot: "")
    r = run(P, "trazer_enviar", {"gid": "psx-hercules"})
    assert "na fila para vir do PC" in r["texto"] and "/trazer" not in r["texto"]
    f = run(P, "transferir")["fila"]
    assert f[0]["direcao"] == "pc->deck" and f[0]["status"] == "na fila"


def test_quality_list_and_set(P):
    _lm(P, {"ps2-a": {"title": "A", "console": "ps2", "rom": "/x"}, "gba-b": {"title": "B", "console": "gba", "rom": "/y"}})
    r = run(P, "qualidade")
    assert [j["gid"] for j in r["jogos"]] == ["ps2-a"] and r["jogos"][0]["niveis"][:3] == ["padrão", "nativo", "2x"]
    assert "2x só para este jogo" in run(P, "qualidade_definir", {"gid": "ps2-a", "nivel": "2x"})["texto"]
    assert run(P, "qualidade")["jogos"][0]["atual"] == "2x"
    run(P, "qualidade_definir", {"gid": "ps2-a", "nivel": "padrão"})
    assert run(P, "qualidade")["jogos"][0]["atual"] == "padrão"


def test_cli_reads_json_from_stdin(P, monkeypatch, capsys):
    import io
    real = painel.Ponte
    monkeypatch.setattr("dc.painel.Ponte", lambda paths: real(paths, qbt=FakeQbt()))
    monkeypatch.setattr("sys.stdin", io.StringIO('{"permitir": true}'))
    assert painel.main(["bateria"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] and "bateria" in out["texto"]
    assert painel.main(["bateria", "{nao-json"]) == 1


def test_traducao_mostra_so_a_tarefa_mais_nova_de_cada_jogo(tmp_path):
    import json
    from dc import painel
    from dc.paths import get_paths
    from dc.traducao import run
    paths = get_paths(tmp_path / "dc").ensure()
    d = run.jobs_dir(paths)
    velhas = [("a1", "falhou", "2026-11-08T10:00:00+00:00"), ("a2", "falhou", "2026-11-09T10:00:00+00:00"),
              ("a3", "concluido", "2026-11-10T10:00:00+00:00")]
    for op, st, cr in velhas:
        (d / f"{op}.json").write_text(json.dumps({"op": op, "type": "translate_switch", "game_id": "switch-ff",
                                                  "title": "Final Fantasy", "status": st, "created": cr}), "utf-8")
    # a falha mais velha foi gravada por último (bot marcou "avisado"): não pode passar na frente
    (d / "a1.json").write_text((d / "a1.json").read_text("utf-8"), "utf-8")

    class P:
        pass
    p = P(); p.paths = paths; p.store = None; p._map = lambda: {}
    import dc.traducao.run as r
    orig = r.library_plan
    r.library_plan = lambda *a, **k: {"ok": []}
    try:
        out = painel.traducao(p, {})
    finally:
        r.library_plan = orig
    assert [t["op"] for t in out["tarefas"]] == ["a3"]
    assert not out["tarefas"][0]["pode_retomar"]


def test_falha_de_formato_nao_oferece_retomar(tmp_path):
    import json
    from dc import painel
    from dc.paths import get_paths
    from dc.traducao import run
    paths = get_paths(tmp_path / "dc").ensure()
    (run.jobs_dir(paths) / "h1.json").write_text(json.dumps({
        "op": "h1", "type": "translate_retro", "game_id": "psx-hercules", "title": "Hercules", "status": "falhou",
        "created": "2026-11-09T18:27:00+00:00",
        "report": "⚠️ não traduzi para não estragar o jogo: texto misturado/ilegível — precisa de engenharia reversa"}))

    class P:
        pass
    p = P(); p.paths = paths; p.store = None; p._map = lambda: {}
    import dc.traducao.run as r
    orig = r.library_plan
    r.library_plan = lambda *a, **k: {"ok": []}
    try:
        t = painel.traducao(p, {})["tarefas"][0]
    finally:
        r.library_plan = orig
    assert not t["pode_retomar"] and "formato" in t["linha"]


def test_limpar_historicos(tmp_path):
    import json
    from dc import painel
    from dc.paths import get_paths
    from dc.traducao import run
    paths = get_paths(tmp_path / "dc").ensure()
    d = run.jobs_dir(paths)
    for op, st in (("c1", "concluido"), ("f1", "falhou"), ("r1", "rodando"), ("q1", "aguardando ok")):
        (d / f"{op}.json").write_text(json.dumps({"op": op, "status": st, "game_id": op}), "utf-8")

    class Q:
        apagados = []

        def torrents(self):
            return [{"hash": "h1", "state": "stalledUP"}, {"hash": "h2", "state": "downloading"},
                    {"hash": "h3", "state": "pausedUP"}]

        def delete(self, h, delete_files=False):
            assert delete_files is False
            self.apagados.append(h)
    (paths.state / "sync-state.json").write_text(json.dumps({"ingested": {"h1": {}, "h2": {}}}), "utf-8")

    class P:
        pass
    p = P(); p.paths = paths; p.qbt = Q()
    out = painel.traducao_limpar(p, {})
    assert "2 tarefa" in out["texto"]
    assert sorted(x.stem for x in d.glob("*.json")) == ["q1", "r1"]
    assert sorted(x.stem for x in (d / "arquivo").glob("*.json")) == ["c1", "f1"]
    out = painel.downloads_limpar(p, {})
    assert p.qbt.apagados == ["h1"] and "1 download" in out["texto"]  # h3 concluído mas não está na biblioteca


def test_desinstalar_lista_e_aviso_do_steam(tmp_path, monkeypatch):
    import json
    from dc import bot, painel, plugin_bridge
    from dc.paths import get_paths
    paths = get_paths(tmp_path / "dc").ensure()
    rom = tmp_path / "Jogo.iso"; rom.write_bytes(b"x")
    orig = tmp_path / "Orig.gba"; orig.write_bytes(b"x")
    (paths.data / "launch-map.json").write_text(json.dumps({
        "ps2-jogo": {"title": "Jogo", "console": "ps2", "rom": str(rom)},
        "gba-orig": {"title": "Original", "console": "gba", "rom": str(orig), "removed": True},
        "pc-fortnite": {"title": "Fortnite", "console": "pc", "rom": "Fortnite"}}), "utf-8")
    plugin_bridge.done_path(paths).write_text(json.dumps({"gba-orig": {"removed": True, "motivo": "traduzido"}}), "utf-8")

    class P:
        pass
    p = P(); p.paths = paths
    d = painel.desinstalar_lista(p, {})
    assert [j["gid"] for j in d["jogos"]] == ["ps2-jogo"]  # PC não entra
    assert d["tirados"] == [{"gid": "gba-orig", "titulo": "Original", "console": "gba", "substituido": True}]

    x = bot.Bot(paths, "T"); x.cfg["allowed"] = [1]; x.cfg["notify_chat"] = 9
    sent = []
    x.send = lambda chat, text, buttons=None: sent.append((text, buttons))
    x.notify_removidos()  # 1ª vez: só memoriza
    assert sent == []
    plugin_bridge.done_path(paths).write_text(json.dumps({"gba-orig": {"removed": True, "motivo": "traduzido"},
                                                          "ps2-jogo": {"appid": 0, "removed": True}}), "utf-8")
    x.notify_removidos(); x.notify_removidos()
    assert len(sent) == 1 and "Jogo" in sent[0][0]
    assert sent[0][1] == [("Apagar os arquivos", "/remover ps2-jogo confirmar"), ("Trazer de volta", "/devolver ps2-jogo")]


def test_perguntado_na_tela_nao_pergunta_no_telegram(tmp_path):
    import json
    from dc import bot, painel, plugin_bridge
    from dc.paths import get_paths
    paths = get_paths(tmp_path / "dc").ensure()
    rom = tmp_path / "J.iso"; rom.write_bytes(b"x")
    (paths.data / "launch-map.json").write_text(json.dumps({"ps2-j": {"title": "J", "console": "ps2", "rom": str(rom)}}))
    x = bot.Bot(paths, "T"); x.cfg["allowed"] = [1]; x.cfg["notify_chat"] = 9
    sent = []
    x.send = lambda chat, text, buttons=None: sent.append(text)
    x.notify_removidos()
    plugin_bridge.done_path(paths).write_text(json.dumps({"ps2-j": {"appid": 0, "removed": True}}))

    class P:
        pass
    p = P(); p.paths = paths
    painel.removido_perguntado(p, {"gid": "ps2-j"})
    x.notify_removidos()
    assert sent == []
