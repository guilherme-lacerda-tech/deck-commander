"""Torrent sem fontes e torrent com erro (disco cheio / SD removido): o bot avisa uma vez, em português,
e não trava nada."""
from dc import bot
from dc.paths import get_paths
from dc.qbt import QbtError

NOW = 1_000_000.0


def _bot(tmp_path, ts):
    b = bot.Bot(get_paths(tmp_path).ensure(), "TOK")
    b.cfg.update(allowed=[1], notify_chat=9)
    b.sent = []
    b.call = lambda method, **kw: b.sent.append(kw.get("text")) or []

    class Q:
        def torrents(self, *a, **k):
            if ts is None:
                raise QbtError("qBittorrent indisponível")
            return ts
    b.qbt = Q()
    return b


def t(h, state, added_ago, seeds=0, progress=0.0):
    return {"hash": h, "name": f"Jogo {h}", "state": state, "added_on": NOW - added_ago,
            "num_seeds": seeds, "progress": progress}


def test_dead_torrent_warned_once_after_30_min(tmp_path):
    ts = [t("a", "stalledDL", 31 * 60), t("b", "metaDL", 5 * 60), t("c", "stalledDL", 40 * 60, seeds=2),
          t("d", "downloading", 99 * 60)]
    b = _bot(tmp_path, ts)
    b.notify_stalled(NOW)
    assert len(b.sent) == 1 and "Jogo a" in b.sent[0] and "sem fontes" in b.sent[0]
    assert "Jogo b" not in b.sent[0] and "Jogo c" not in b.sent[0] and "Jogo d" not in b.sent[0]
    b.notify_stalled(NOW + 600)
    assert len(b.sent) == 1  # não repete


def test_error_state_mentions_disk_or_sd(tmp_path):
    b = _bot(tmp_path, [t("e", "error", 10), t("f", "missingFiles", 10)])
    b.notify_stalled(NOW)
    assert "disco cheio" in b.sent[0] and "cartão SD" in b.sent[0] and "Jogo f" in b.sent[0]


def test_qbittorrent_down_is_silent_and_does_not_raise(tmp_path):
    b = _bot(tmp_path, None)
    b.notify_stalled(NOW)
    assert b.sent == []


def test_forgets_deleted_downloads(tmp_path):
    ts = [t("a", "stalledDL", 31 * 60)]
    b = _bot(tmp_path, ts)
    b.notify_stalled(NOW)
    ts.clear()
    b.notify_stalled(NOW)
    assert b.cfg["stalled_notified"] == {}
