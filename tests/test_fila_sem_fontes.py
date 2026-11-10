"""Torrent sem fontes não pode travar a fila: o qBittorrent é configurado para não contar torrent parado
como vaga ativa (no Deck estava max_active_downloads=3 e dont_count_slow_torrents=False)."""
import json

from dc import qbt


def test_seeding_limits_also_free_queue_slots_from_dead_torrents():
    q = qbt.Qbt()
    sent = []
    q._req = lambda path, data=None: sent.append((path, data)) or b"Ok."
    q.set_seeding_limits(2.0, 120)
    prefs = json.loads(sent[-1][1]["json"])
    assert sent[-1][0] == "app/setPreferences"
    assert prefs["dont_count_slow_torrents"] is True
    assert prefs["slow_torrent_inactive_timer"] <= 120
    assert prefs["max_ratio"] == 2.0 and prefs["max_seeding_time"] == 120
