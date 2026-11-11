"""Protetor de tela com a arte dos jogos (o do Steam ficou preto com atalhos de emulador)."""
import json
import random
from pathlib import Path

from dc import protetor, vdf


def _deck(tmp_path, n=25):
    grid = tmp_path / ".local/share/Steam/userdata/123/config/grid"
    grid.mkdir(parents=True)
    sc = {}
    for k in range(n):
        aid = 3000000000 + k
        sc[str(k)] = {"appid": aid - (1 << 32), "AppName": f"Jogo {k}", "LastPlayTime": 1000 + k, "LaunchOptions": f"g{k}"}
        (grid / f"{aid}_hero.jpg").write_bytes(b"jpg")
        if k % 2:
            (grid / f"{aid}_logo.png").write_bytes(b"png")
    sc["99"] = {"appid": 5, "AppName": "Spotify", "LastPlayTime": 99999, "LaunchOptions": "app-spotify"}
    (grid / "5_hero.png").write_bytes(b"png")
    sc["98"] = {"appid": 6, "AppName": "Sem arte", "LastPlayTime": 99998}
    (grid.parent / "shortcuts.vdf").write_bytes(vdf.dump_binary({"shortcuts": sc}))
    return grid


def test_recentes_primeiro_sem_apps_nem_sem_arte(tmp_path):
    _deck(tmp_path)
    j = protetor.escolher(tmp_path, rnd=random.Random(1))
    assert [x["titulo"] for x in j[:3]] == ["Jogo 24", "Jogo 23", "Jogo 22"]
    assert len(j) == 25 and not {"Spotify", "Sem arte"} & {x["titulo"] for x in j}


def test_monta_pasta_do_steam(tmp_path):
    _deck(tmp_path, 3)
    assert "3 jogo" in protetor.montar(tmp_path)
    pasta = tmp_path / ".steam/root/config/uioverrides/screensavers/deckcommander"
    html = (pasta / "index.html").read_text("utf-8")
    lista = json.loads(html.split("const JOGOS = ")[1].split(";\n")[0])
    assert lista[0]["titulo"] == "Jogo 2" and (pasta / lista[0]["fundo"]).read_bytes() == b"jpg"
    assert lista[1]["logo"] and (pasta / lista[1]["logo"]).exists()
    protetor.montar(tmp_path)  # refazer não deixa sobra
    assert sorted(p.name for p in pasta.parent.iterdir()) == ["deckcommander"]


def test_nome_vale_como_endereco():
    """Falha real: o Steam abre uioverride-<pasta>.steamscreensavers.host; "Deck Commander" (com espaço) deu erro -105."""
    import re
    assert re.fullmatch(r"[a-z0-9-]+", protetor.NOME)
