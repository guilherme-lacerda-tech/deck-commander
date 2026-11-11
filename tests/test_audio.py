"""Mixer e controle de mídia (dc/audio.py)."""
import json
from types import SimpleNamespace

from dc import audio

SINKS = [{"index": 1, "mute": False, "volume": {"front-left": {"value_percent": "80%"}, "front-right": {"value_percent": "60%"}},
          "properties": {"application.name": "Spotify", "application.process.binary": "spotify"}},
         {"index": 2, "mute": False, "volume": {"mono": {"value_percent": "100%"}},
          "properties": {"application.name": "melonDS"}},
         {"index": 3, "mute": True, "volume": {}, "properties": {"application.name": "speech-dispatcher-dummy"}}]


def fake(cmds):
    def run(args, **kw):
        cmds.append(args)
        if args[:3] == ["pactl", "-f", "json"]:
            return SimpleNamespace(returncode=0, stdout=json.dumps(SINKS))
        if args[:3] == ["busctl", "--user", "list"]:
            return SimpleNamespace(returncode=0, stdout="org.mpris.MediaPlayer2.spotify 123 spotify deck\n")
        return SimpleNamespace(returncode=0, stdout="")
    return run


def test_fluxos_e_volume():
    cmds = []
    fl = audio.fluxos(run=fake(cmds))
    assert [(f["nome"], f["tipo"], f["volume"]) for f in fl] == [("Spotify", "musica", 70), ("melonDS", "jogo", 100),
                                                                ("speech-dispatcher-dummy", "sistema", 0)]
    assert audio.definir_volume("musica", 200, run=fake(cmds)) == 1
    assert ["pactl", "set-sink-input-volume", "1", "150%"] in cmds


def test_midia_e_playlist():
    cmds = []
    assert audio.midia("proxima", run=fake(cmds))
    assert cmds[-1][-1] == "Next" and "org.mpris.MediaPlayer2.spotify" in cmds[-1]
    assert audio.abrir("spotify:playlist:x", run=fake(cmds)) and cmds[-1][-3:] == ["OpenUri", "s", "spotify:playlist:x"]
    assert not audio.midia("explodir", run=fake(cmds))


def test_link_de_playlist_vira_uri_e_bot(tmp_path, monkeypatch):
    from dc import bot, painel
    from dc.paths import get_paths
    assert painel._uri_spotify("https://open.spotify.com/playlist/37i9dQ?si=abc") == "spotify:playlist:37i9dQ"
    paths = get_paths(tmp_path).ensure()
    x = bot.Bot(paths, "T"); x.cfg["allowed"] = [1]
    monkeypatch.setattr(audio, "fluxos", lambda run=None: [])
    monkeypatch.setattr(audio, "tocando", lambda run=None: None)
    p = painel.Ponte(paths)
    painel.musica_salvar(p, {"nome": "Foco", "uri": "https://open.spotify.com/playlist/AAA"})
    abertos = []
    monkeypatch.setattr(audio, "abrir", lambda uri, run=None: abertos.append(uri) or True)
    assert "Foco" in x.handle(1, 1, "/musica")
    assert "Tocando" in x.handle(1, 1, "/musica foco") and abertos == ["spotify:playlist:AAA"]


def test_link_colado_no_bot_vira_playlist(tmp_path):
    from dc import bot, painel
    from dc.paths import get_paths
    paths = get_paths(tmp_path).ensure()
    x = bot.Bot(paths, "T"); x.cfg["allowed"] = [1]
    msg = lambda t: {"from": {"id": 1}, "chat": {"id": 1}, "text": t}
    r = x.handle_message(msg("Foco https://open.spotify.com/intl-pt/playlist/37i9dQZF1DX8NTLI2TtZa6?si=abc"))
    assert 'guardada como "Foco"' in r
    pls = audio.playlists(painel._playlists_path(painel.Ponte(paths)))
    assert pls == [{"nome": "Foco", "uri": "spotify:playlist:37i9dQZF1DX8NTLI2TtZa6"}]
    assert "Playlist 2" in x.handle_message(msg("https://open.spotify.com/album/AAA"))
    assert 'como "Rock"' in x.handle(1, 1, "/playlist Rock https://open.spotify.com/playlist/BBB")
