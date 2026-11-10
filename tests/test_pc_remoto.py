"""Jogos do PC (aba Computador): tudo sem rede — Moonlight, porteiro, WoL e Sunshine simulados."""
import json

import pytest

from dc import pc_remoto, tabs
from dc.paths import get_paths

# saída REAL do `flatpak run com.moonlight_stream.Moonlight list --csv 100.118.222.56` no Deck (2026-11-10),
# com o log do Qt misturado (stderr) e um jogo oculto acrescentado
CSV_REAL = '''00:00:00 - Qt Info: Unable to detect Wayland or X11, so EGLFS will be used by default.
_amdgpu_device_initialize: amdgpu_query_info(ACCEL_WORKING) failed (-13)
Name, ID, HDR Support, App Collection Game, Hidden, Direct Launch, Boxart URL
"Desktop",881448767,true,false,false,false,"file:///home/deck/.var/app/x/881448767.png"
"Steam Big Picture",1093255277,true,false,false,false,"file:///home/deck/.var/app/x/1093255277.png"
"STAR WARS Jedi: Fallen Order",55,true,false,false,false,""
"Oculto",56,true,false,true,false,""
'''


@pytest.fixture
def paths(tmp_path, monkeypatch):
    monkeypatch.setattr(pc_remoto.Path, "home", lambda: tmp_path / "home")
    return get_paths(tmp_path / "dc").ensure()


@pytest.fixture
def cfg():
    c = json.loads(json.dumps(pc_remoto.DEFAULT))
    c["codigo"] = "SEGREDO"
    return c


class R:
    def __init__(self, rc=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


# ---------------------------------------------------------------------------------------- moonlight list
def test_parse_lista_csv_real_ignora_log_e_ocultos():
    assert pc_remoto.parse_lista(CSV_REAL) == ["Desktop", "Steam Big Picture", "STAR WARS Jedi: Fallen Order"]


def test_parse_lista_sem_csv():
    txt = "00:00:00 - Qt Info: x\n_amdgpu_device_initialize: y\nDesktop\nSteam Big Picture\n"
    assert pc_remoto.parse_lista(txt) == ["Desktop", "Steam Big Picture"]


def test_listar_apps_erros(cfg):
    run = lambda cmd, **k: R(0, "", "Failed to connect to 100.118.222.56")
    with pytest.raises(RuntimeError):
        pc_remoto.listar_apps(cfg, "100.118.222.56", run=run)
    seen = []

    def ok(cmd, **k):
        seen.append(cmd)
        return R(0, CSV_REAL.split("\n", 2)[2])
    assert "Desktop" in pc_remoto.listar_apps(cfg, "h", run=ok)
    assert seen[0][-3:] == ["list", "--csv", "h"] and "com.moonlight_stream.Moonlight" in seen[0]


# ---------------------------------------------------------------------------------------- acordar
def test_magic_packet():
    p = pc_remoto.magic_packet("24-B2-B9-0B-61-71")
    assert len(p) == 102 and p[:6] == b"\xff" * 6 and p[6:12] == bytes.fromhex("24B2B90B6171")
    with pytest.raises(ValueError):
        pc_remoto.magic_packet("zz")


def test_acordar_ja_acordado_nao_chama_nada(cfg, monkeypatch):
    monkeypatch.setattr(pc_remoto, "online", lambda c, timeout=2: "100.118.222.56")
    ok, msg = pc_remoto.acordar(cfg, http_get=lambda *a: pytest.fail("não devia"), wol=lambda *a: pytest.fail("x"))
    assert ok and "acordado" in msg


def test_acordar_porteiro_tailscale_falha_lan_ok(cfg, monkeypatch):
    monkeypatch.setattr(pc_remoto, "online", lambda c, timeout=2: None)
    urls = []

    def get(url, timeout):
        urls.append(url)
        if "100.77.101.93" in url:
            raise OSError("sem rota")
        return 200, "ok, acordando o PC"
    ok, msg = pc_remoto.acordar(cfg, http_get=get, wol=lambda *a: pytest.fail("não devia mandar WoL"))
    assert ok and "192.168.100.23" in msg and len(urls) == 2
    assert urls[0] == "http://100.77.101.93:8766/acordar?t=SEGREDO"


def test_acordar_cai_no_wol(cfg, monkeypatch):
    monkeypatch.setattr(pc_remoto, "online", lambda c, timeout=2: None)
    wols = []
    ok, msg = pc_remoto.acordar(cfg, http_get=lambda u, t: (403, "token invalido"),
                                wol=lambda mac, bc: wols.append((mac, bc)))
    assert ok and wols == [("24-B2-B9-0B-61-71", "192.168.100.255")] and "HTTP 403" in msg
    cfg["codigo"] = ""
    ok, msg = pc_remoto.acordar(cfg, http_get=lambda *a: pytest.fail("sem código não chama"), wol=lambda *a: None)
    assert ok and "sem código" in msg


def test_esperar_pronto_relogio_falso(cfg, monkeypatch):
    t = [0.0]
    respostas = iter([None, None, "100.118.222.56"])
    monkeypatch.setattr(pc_remoto, "online", lambda c, timeout=2: next(respostas))
    h = pc_remoto.esperar_pronto(cfg, sleep=lambda s: t.__setitem__(0, t[0] + s), relogio=lambda: t[0])
    assert h == "100.118.222.56" and t[0] == 6
    monkeypatch.setattr(pc_remoto, "online", lambda c, timeout=2: None)
    t[0] = 0
    assert pc_remoto.esperar_pronto(cfg, limite=10, sleep=lambda s: t.__setitem__(0, t[0] + s), relogio=lambda: t[0]) is None


# ---------------------------------------------------------------------------------------- jogar
def test_comando_stream(cfg):
    c = pc_remoto.comando_stream(cfg, "100.118.222.56", "Fortnite", casa=True)
    assert c[:5] == ["/usr/bin/flatpak", "run", "com.moonlight_stream.Moonlight", "stream", "100.118.222.56"]
    assert c[5] == "Fortnite" and "--quit-after" in c and c[c.index("--bitrate") + 1] == "30000"
    assert pc_remoto.comando_stream(cfg, "h", "x", casa=False)[-1] == "15000"


class FakeChild:
    def __init__(self, code):
        self.code = code

    def wait(self, timeout=None):
        return self.code


def test_jogar_fluxo_completo(paths, cfg):
    runs, popens = [], []
    code, msg = pc_remoto.jogar("VALORANT", paths, cfg, say=lambda m: None,
                                popen=lambda cmd, **k: popens.append(cmd) or FakeChild(0),
                                run=lambda cmd, **k: runs.append(cmd) or R(),
                                acordar_fn=lambda c: (True, "ok"), esperar_fn=lambda c: "100.118.222.56")
    assert (code, msg) == (0, "")
    assert popens[0][3:6] == ["stream", "100.118.222.56", "VALORANT"]
    assert any(c[-2:] == ["quit", "100.118.222.56"] for c in runs)  # o jogo fecha no PC
    assert any(c[0] == "systemd-run" for c in runs)  # lista atualizada depois de jogar
    assert (paths.logs / "moonlight.log").exists()


def test_jogar_pc_nao_responde(paths, cfg):
    code, msg = pc_remoto.jogar("Fortnite", paths, cfg, say=lambda m: None,
                                popen=lambda *a, **k: pytest.fail("não transmite"),
                                acordar_fn=lambda c: (True, "ok"), esperar_fn=lambda c: None)
    assert code == 1 and "não respondeu" in msg
    code, msg = pc_remoto.jogar("Fortnite", paths, cfg, say=lambda m: None, acordar_fn=lambda c: (False, "x"))
    assert code == 1 and "acordar" in msg


def test_jogar_erro_do_moonlight(paths, cfg):
    code, msg = pc_remoto.jogar("X", paths, cfg, say=lambda m: None, popen=lambda *a, **k: FakeChild(3),
                                run=lambda *a, **k: R(), acordar_fn=lambda c: (True, ""), esperar_fn=lambda c: "h")
    assert code == 3 and "erro 3" in msg


# ---------------------------------------------------------------------------------------- sincronizar
def _lm(paths):
    return json.loads((paths.data / "launch-map.json").read_text("utf-8"))


def test_sincronizar_cria_atalhos_e_tira_os_que_sumiram(paths, cfg):
    (paths.data / "launch-map.json").write_text(json.dumps({"ps2-gow": {"title": "GoW", "console": "ps2", "rom": "/r"}}))
    r = pc_remoto.sincronizar(paths, cfg, apps=["Desktop", "Fortnite", "VALORANT"], shortcuts=[], plugin_ativo=True)
    lm = _lm(paths)
    assert lm["ps2-gow"]["console"] == "ps2"  # outros consoles intactos
    assert lm["pc-fortnite"] == {"title": "Fortnite", "console": "pc", "rom": "pc:Fortnite", "app": "Fortnite"}
    assert lm["pc-desktop"]["title"] == "Área de trabalho do PC" and lm["pc-desktop"]["app"] == "Desktop"
    q = json.loads((paths.data / "plugin-queue.json").read_text("utf-8"))
    assert {x["game_id"] for x in q} == {"pc-desktop", "pc-fortnite", "pc-valorant"}
    assert all(x["exe"].endswith('dc-launch"') and x["launch_options"] == x["game_id"] for x in q)
    assert sorted(r["atalhos"]) == ["Fortnite", "VALORANT", "Área de trabalho do PC"]
    # o plugin criou os atalhos
    done = {g: {"appid": 1000 + i, "error": ""} for i, g in enumerate(["pc-desktop", "pc-fortnite", "pc-valorant"])}
    (paths.data / "plugin-done.json").write_text(json.dumps(done))
    (paths.data / "plugin-queue.json").write_text("[]")
    # Fortnite desinstalado no PC
    r = pc_remoto.sincronizar(paths, cfg, apps=["Desktop", "VALORANT"], shortcuts=[], plugin_ativo=True)
    assert r["saem"] == ["Fortnite"] and "pc-fortnite" not in _lm(paths)
    rem = json.loads((paths.data / "plugin-remove.json").read_text("utf-8"))
    assert rem == [{"game_id": "pc-fortnite", "appid": 1001}]
    # reinstalado: volta (a remoção foi nossa, não do usuário)
    r = pc_remoto.sincronizar(paths, cfg, apps=["Desktop", "Fortnite", "VALORANT"], shortcuts=[], plugin_ativo=True)
    assert r["entram"] == ["Fortnite"] and r["atalhos"] == ["Fortnite"]


def test_sincronizar_respeita_removido_pelo_usuario_e_nome_igual(paths, cfg):
    (paths.data / "launch-map.json").write_text(json.dumps(
        {"pc-fortnite": {"title": "Fortnite", "console": "pc", "rom": "pc:Fortnite", "app": "Fortnite", "removed": True}}))
    manual = [{"appid": 77, "AppName": "Cyberpunk 2077", "exe": '"/home/deck/cp.sh"', "LaunchOptions": ""}]
    r = pc_remoto.sincronizar(paths, cfg, apps=["Fortnite", "Cyberpunk 2077"], shortcuts=manual, plugin_ativo=True)
    assert _lm(paths)["pc-fortnite"]["removed"] is True
    assert r["atalhos"] == ["Cyberpunk 2077 (PC)"]  # não colide com o atalho seu de mesmo nome


def test_sincronizar_sem_plugin_avisa(paths, cfg):
    r = pc_remoto.sincronizar(paths, cfg, apps=["Fortnite"], shortcuts=[], plugin_ativo=False)
    assert r["atalhos"] == [] and "plugin" in r["aviso"] and "pc-fortnite" in _lm(paths)


def test_sincronizar_pc_dormindo(paths, cfg, monkeypatch):
    monkeypatch.setattr(pc_remoto, "online", lambda c, timeout=2: None)
    with pytest.raises(RuntimeError, match="dormindo"):
        pc_remoto.sincronizar(paths, cfg)


# ---------------------------------------------------------------------------------------- integração
def test_aba_computador():
    sc = [{"appid": 11, "exe": '"/x/dc-launch"', "LaunchOptions": "pc-fortnite"},
          {"appid": 12, "exe": '"/x/dc-launch"', "LaunchOptions": "ps2-gow"}]
    lm = {"pc-fortnite": {"console": "pc"}, "ps2-gow": {"console": "ps2"}}
    out = tabs.build({}, sc, lm)
    assert out["dc-pc"]["title"] == "Computador" and out["dc-pc"]["filters"][0]["params"]["games"] == [11]
    assert tabs.groups(sc, lm)["Computador"] == [11]


def test_scan_ignora_pasta_pc(tmp_path):
    from dc import library
    (tmp_path / "pc").mkdir()
    (tmp_path / "pc" / "algo.iso").write_bytes(b"x")
    games, _ = library.scan([tmp_path])
    assert games == []


def test_dc_launch_despacha_para_o_pc(tmp_path, monkeypatch):
    from dc import launch
    monkeypatch.setenv("DC_ROOT", str(tmp_path))
    p = get_paths().ensure()
    (p.data / "launch-map.json").write_text(json.dumps(
        {"pc-valorant": {"title": "VALORANT", "console": "pc", "rom": "pc:VALORANT", "app": "VALORANT"}}))
    chamado = []
    monkeypatch.setattr(pc_remoto, "jogar", lambda app, paths, say=print: chamado.append(app) or (0, ""))
    with pytest.raises(SystemExit) as e:
        launch.main(["pc-valorant"])
    assert e.value.code == 0 and chamado == ["VALORANT"]
    monkeypatch.setattr(pc_remoto, "jogar", lambda app, paths, say=print: (1, "VALORANT: o PC não respondeu"))
    with pytest.raises(SystemExit) as e:
        launch.main(["pc-valorant"])
    assert e.value.code == 1
    assert "não respondeu" in json.loads((p.data / "launch-error.json").read_text("utf-8"))["message"]


def test_garantir_controle(tmp_path):
    f = tmp_path / "configset_controller_neptune.vdf"
    f.write_text('"controller_config"\n{\n\t"moonlight"\n\t{\n\t\t"template"\t\t"controller_neptune_wasd.vdf"\n\t}\n'
                 '\t"fortnite"\n\t{\n\t\t"template"\t\t"meu.vdf"\n\t}\n}\n', "utf-8")
    assert pc_remoto.garantir_controle(["Fortnite", "VALORANT"], f) == ["valorant"]
    txt = f.read_text("utf-8")
    assert '"meu.vdf"' in txt and txt.count("controller_neptune_gamepad+mouse.vdf") == 1
    assert txt.rstrip().endswith("}") and (tmp_path / "configset_controller_neptune.vdf.antes-deck-commander").exists()
    from dc import vdf
    assert vdf.load_text(txt)["controller_config"]["valorant"]["template"] == "controller_neptune_gamepad+mouse.vdf"
    assert pc_remoto.garantir_controle(["VALORANT"], f) == []  # idempotente


def test_comando_pc_bot(paths, cfg, monkeypatch):
    bot = type("B", (), {"paths": paths})()
    monkeypatch.setattr(pc_remoto, "online", lambda c, timeout=2: None)
    monkeypatch.setattr(pc_remoto, "em_casa", lambda c: False)
    assert "dormindo" in pc_remoto.comando_pc(bot, ["status"])
    assert "Nenhum jogo" in pc_remoto.comando_pc(bot, ["listar"])
    assert "❌" in pc_remoto.comando_pc(bot, ["sincronizar"])
    monkeypatch.setattr(pc_remoto, "acordar", lambda c: (True, "porteiro 100.77.101.93: ok"))
    assert pc_remoto.comando_pc(bot, ["acordar"]).startswith("⏰ porteiro")
    assert "Uso" in pc_remoto.comando_pc(bot, ["xyz"])


def test_config_secreta(paths):
    c = pc_remoto.carregar_config(paths)
    assert c["host_tailscale"] == "100.118.222.56" and c["codigo"] == ""
    c["codigo"] = "abc"
    p = pc_remoto.salvar_config(paths, c)
    assert pc_remoto.carregar_config(paths)["codigo"] == "abc" and p.name == "pc-remoto.json"


def test_bot_routes_pc_command(tmp_path, monkeypatch):
    from dc import bot, pc_remoto
    from dc.paths import get_paths
    paths = get_paths(tmp_path).ensure()
    x = bot.Bot(paths, "T")
    x.cfg["allowed"] = [1]
    seen = []
    monkeypatch.setattr(pc_remoto, "comando_pc", lambda b, args: seen.append(args) or "ok pc")
    assert x.handle(1, 1, "/pc status") == "ok pc" and seen == [["status"]]
