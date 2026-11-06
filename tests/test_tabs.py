import json

from dc import tabs

DEFAULT = {k: {"id": k, "title": k, "position": i} for i, k in enumerate(
    ["GreatOnDeck", "AllGames", "Installed", "Favorites", "Collections", "DesktopApps", "Soundtracks"])}


def test_build_tabs_per_console_and_emulators():
    sc = [{"appid": -10, "exe": '"/x/dc-launch"', "LaunchOptions": "ps2-gow"},
          {"appid": 20, "exe": '"/x/dc-launch"', "LaunchOptions": "switch-smg"},
          {"appid": 30, "exe": '"/usr/bin/flatpak"', "LaunchOptions": '"run" "net.pcsx2.PCSX2"'},
          {"appid": 40, "exe": '"/x/unifideck-launcher"', "LaunchOptions": "epic:1"},
          {"appid": 50, "exe": '"/x/Ryujinx"', "LaunchOptions": ""}]
    lm = {"ps2-gow": {"console": "ps2"}, "switch-smg": {"console": "switch"}}
    custom = {**DEFAULT, "meu-tab": {"id": "meu-tab", "title": "Meu", "position": 7, "filters": []}}
    out = tabs.build(custom, sc, lm)
    assert out["dc-ps2"]["filters"][0]["params"]["games"] == [(-10) & 0xFFFFFFFF]
    assert out["dc-switch"]["filters"][0]["params"]["games"] == [20]
    assert out["dc-emuladores"]["filters"][0]["params"]["games"] == [30, 50]
    assert out["dc-gc"]["autoHide"] is True and out["dc-gc"]["filters"][0]["params"]["games"] == []
    assert out["DesktopApps"]["position"] == -1 and "meu-tab" in out
    pos = sorted(t["position"] for t in out.values() if t["position"] > -1)
    assert pos == list(range(len(pos)))  # posições contínuas, sem colisão
    assert out["Favorites"]["position"] < out["dc-ps2"]["position"] < out["Collections"]["position"]


def test_apply_backs_up_and_is_idempotent(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"usersDict": {"1": {"tabs": DEFAULT}}, "tags": []}))
    sc = [{"appid": 5, "exe": "dc-launch", "LaunchOptions": "psx-fft"}]
    res = tabs.apply(sc, {"psx-fft": {"console": "psx"}}, "1", p)
    assert res["dc-psx"] == "whitelist" and (tmp_path / "settings.json.antes-deck-commander").exists()
    assert tabs.apply(sc, {"psx-fft": {"console": "psx"}}, "1", p) == {}


def test_store_tabs_from_unifideck_tags():
    sc = [{"appid": 1, "exe": '"/x/unifideck-launcher"', "tags": {"0": "Not Installed", "1": "Epic"}},
          {"appid": 2, "exe": '"/x/unifideck-launcher"', "tags": {"0": "Gog", "1": "Installed"}},
          {"appid": 3, "exe": '"/x/unifideck-launcher"', "tags": {"0": "Epic"}}]
    out = tabs.build(DEFAULT, sc, {})
    assert out["dc-loja-epic"]["title"] == "Epic Games" and out["dc-loja-epic"]["filters"][0]["params"]["games"] == [1, 3]
    assert out["dc-loja-gog"]["title"] == "GOG" and out["dc-loja-gog"]["filters"][0]["params"]["games"] == [2]
    assert out["Favorites"]["position"] < out["dc-loja-epic"]["position"] < out["dc-ps2"]["position"]
    assert "dc-emuladores" in out and all(1 not in t["filters"][0]["params"]["games"]
                                           for k, t in out.items() if k == "dc-emuladores")


def test_collections_spec_includes_plugin_created_and_switches_filter(tmp_path):
    sc = [{"appid": 7, "exe": '"/x/dc-launch"', "LaunchOptions": "ps2-gow"},
          {"appid": 8, "exe": '"/x/unifideck-launcher"', "tags": {"0": "Gog"}}]
    lm = {"ps2-gow": {"console": "ps2"}, "switch-cv": {"console": "switch"}}
    (tmp_path / "plugin-done.json").write_text(json.dumps({"switch-cv": {"appid": 3616886574, "error": ""}}))
    spec = tabs.write_collections(tmp_path, sc, lm)
    assert spec == {"PlayStation 2": [7], "Nintendo Switch": [3616886574], "GOG": [8]}
    (tmp_path / "collection-ids.json").write_text(json.dumps({"Nintendo Switch": "uc-abc"}))
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"usersDict": {"1": {"tabs": DEFAULT}}}))
    res = tabs.apply(sc, lm, "1", p, data_dir=tmp_path)
    assert res["dc-switch"] == "collection" and res["dc-ps2"] == "whitelist"
    t = json.loads(p.read_text())["usersDict"]["1"]["tabs"]["dc-switch"]
    assert t["filters"][0]["params"] == {"id": "uc-abc", "name": "Nintendo Switch"}
    tabs.COLLECTION_IDS.clear()
