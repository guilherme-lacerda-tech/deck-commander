"""M0.3/M15/M19 — safe-mode, uninstall com confirmação, índice e verify do banco."""
import pytest

from dc import ops
from dc.library import Game
from dc.paths import get_paths
from dc.store import Store


@pytest.fixture
def env(tmp_path, monkeypatch):
    units = tmp_path / "units"; units.mkdir()
    for u in ("deck-commander-bot.service", "deck-commander-power.service", "deck-commander-qbittorrent.service",
              "deck-commander-backup.service", "deck-commander-backup.timer", "deck-commander-dashboard.service",
              "outro.service"):
        (units / u).write_text("x")
    monkeypatch.setattr(ops, "unit_dir", lambda: units)
    calls = []
    enabled = {"deck-commander-bot.service", "deck-commander-power.service", "deck-commander-qbittorrent.service",
               "deck-commander-backup.timer"}  # backup.service é "static" e o painel está desligado

    class R:
        def __init__(self, out):
            self.stdout = out

    def fake(*a):
        calls.append(a)
        if a[0] == "is-enabled":
            return R("enabled\n" if a[1] in enabled else "disabled\n")
        return R("")
    monkeypatch.setattr(ops, "_systemctl", fake)
    paths = get_paths(tmp_path / "root").ensure()
    return paths, units, calls


def test_safe_mode_keeps_bot_and_off_restores_exactly(env):
    paths, units, calls = env
    s = Store(paths.db)
    out = ops.safe_mode_on(paths, "teste", s)
    off = [c[2] for c in calls if c[0] == "disable"]
    assert off == ["deck-commander-backup.timer", "deck-commander-qbittorrent.service", "deck-commander-power.service"]
    assert "bot continua ligado" in out[-1]  # o controle remoto nunca cai
    assert all("outro" not in c[-1] for c in calls)  # só serviços do DC
    assert ops.in_safe_mode(paths)
    assert s.list(("awaiting_approval",))[0].type == "safe-mode-restore"  # F4
    calls.clear()
    ops.safe_mode_off(paths)
    assert sorted(c[2] for c in calls if c[0] == "enable") == sorted(off)  # qBittorrent volta junto
    assert not ops.in_safe_mode(paths) and not (paths.state / "safe-mode-units.json").exists()


def test_safe_mode_off_without_record_restores_essentials(env):
    paths, units, calls = env
    ops.safe_mode_flag(paths).write_text("antigo")
    ops.safe_mode_off(paths)
    on = sorted(c[2] for c in calls if c[0] == "enable")
    assert on == ["deck-commander-backup.timer", "deck-commander-power.service", "deck-commander-qbittorrent.service"]


def test_uninstall_requires_confirmation_and_keeps_backups(env, tmp_path):
    paths, units, calls = env
    code = tmp_path / "code"; code.mkdir()
    (paths.backups / "snap").mkdir(parents=True)
    with pytest.raises(PermissionError):
        ops.uninstall(paths, code, purge=True, purge_backups=False)
    with pytest.raises(PermissionError):
        ops.uninstall(paths, code, purge=False, purge_backups=True, confirm="APAGAR")
    log = ops.uninstall(paths, code, purge=True, purge_backups=False, confirm="APAGAR", home=tmp_path / "h",
                        steam=lambda js: "ok")
    assert (paths.backups / "snap").exists() and not paths.config.exists() and not code.exists()
    assert not (units / "deck-commander-bot.service").exists() and (units / "outro.service").exists()
    assert any("preservados" in l for l in log)


def test_desinstalar_nao_deixa_sujeira(env, tmp_path, monkeypatch):
    """Revisão de lançamento 12/11/2026: desinstalar só tirava serviços e código. Ficavam atalhos quebrados, teclas e
    layouts dos botões de trás, protetor de tela, o .zip, o qbittorrent baixado e o plugin rodando no Decky."""
    from dc import plugin_bridge, retro
    paths, _units, _calls = env
    h = tmp_path / "h"
    prot = h / ".steam/root/config/uioverrides/screensavers/deckcommander"
    prot.mkdir(parents=True)
    (h / "Downloads").mkdir()
    (h / "Downloads/deck-commander-plugin.zip").write_bytes(b"zip")
    (h / ".local/bin").mkdir(parents=True)
    (h / ".local/bin/qbittorrent-nox").write_bytes(b"elf")
    paths.ensure()
    plugin_bridge._save(plugin_bridge.done_path(paths), {"psx-a": {"appid": 7, "error": ""}, "x": {"appid": 0}})
    monkeypatch.setattr(plugin_bridge, "active", lambda *a: True)
    monkeypatch.setattr(plugin_bridge, "installed", lambda *a: True)
    desfeito = []
    monkeypatch.setattr(retro, "desfazer", lambda home: desfeito.append(home) or "ok")
    pediu = []
    log = ops.uninstall(paths, tmp_path / "code", purge=True, purge_backups=False, confirm="APAGAR", home=h,
                        esperar_plugin=0, steam=lambda js: pediu.append(js) or "ok")
    assert desfeito == [h] and not prot.exists() and not (h / "Downloads/deck-commander-plugin.zip").exists()
    assert not (h / ".local/bin/qbittorrent-nox").exists()
    assert pediu and "uninstallPlugin" in pediu[0] and any("confirme na tela" in l for l in log)
    assert any("atalhos:" in l and "1 ficaram" in l for l in log)  # o plugin não processou (espera 0)


def test_desinstalar_pede_ao_plugin_tirar_os_atalhos(env, tmp_path, monkeypatch):
    import json
    from dc import plugin_bridge
    paths, *_ = env
    paths.ensure()
    plugin_bridge._save(plugin_bridge.done_path(paths), {"psx-a": {"appid": 7, "error": ""}})
    monkeypatch.setattr(plugin_bridge, "active", lambda *a: True)
    monkeypatch.setattr(plugin_bridge, "installed", lambda *a: True)
    linhas = ops._tirar_atalhos(paths, 0)
    rq = json.loads((paths.data / "plugin-remove.json").read_text("utf-8"))
    assert rq == [{"game_id": "psx-a", "appid": 7}] and "1 ficaram" in linhas[0]
    assert ops._tirar_atalhos(paths, 0) == []  # já marcados: não pede de novo
    plugin_bridge._save(plugin_bridge.done_path(paths), {"psx-b": {"appid": 8, "error": ""}})
    monkeypatch.setattr(plugin_bridge, "active", lambda *a: False)
    assert "Decky não está rodando" in ops._tirar_atalhos(paths, 0)[0]


def test_index_and_verify(env, tmp_path):
    paths, *_ = env
    s = Store(paths.db)
    a = tmp_path / "a.iso"; a.write_bytes(b"a")
    b = tmp_path / "b.iso"; b.write_bytes(b"b")
    games = [Game("ps2-a", "A", "ps2", str(a)), Game("ps2-b", "B", "ps2", str(b))]
    assert ops.index_files(s, games) == 2
    assert ops.index_files(s, games) == 0  # idempotente
    assert [tuple(r) for r in s.conn.execute("SELECT DISTINCT origin FROM files")] == [("unknown",)]
    b.unlink()
    a.write_bytes(b"aa")
    c = tmp_path / "c.iso"; c.write_bytes(b"c")
    with s.tx() as cx:
        cx.execute("INSERT INTO provenance VALUES('111','dc','x','op')")
    rep = ops.db_verify(s, [Game("ps2-a", "A", "ps2", str(a)), Game("ps2-c", "C", "ps2", str(c))],
                        [{"appid": 222, "AppName": "Novo", "exe": '"/x/dc-launch"'}])
    assert rep["missing"] == [str(b)] and rep["modified"] == [str(a)] and rep["untracked"] == [str(c)]
    assert rep["shortcut_untracked"] == ["Novo"] and rep["shortcut_missing"] == ["111"]
