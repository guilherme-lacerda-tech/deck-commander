import json

from dc import artwork


def fake_fetch(calls):
    def f(url, headers):
        calls.append(url)
        if "/search/autocomplete/" in url:
            return json.dumps({"success": True, "data": [{"id": 42, "name": "God of War"}]}).encode()
        if "/api/v2/" in url:
            kind = url.split("/api/v2/")[1].split("/")[0]
            return json.dumps({"success": True, "data": [{"url": f"https://cdn.example/{kind}.png"}]}).encode()
        return b"IMG"
    return f


def test_search_term_cleanup():
    assert artwork.search_term("God of War 2 VERSÃO I.A") == "God of War 2"
    assert artwork.search_term("Ghost Rider (BR) (DUB-IA)") == "Ghost Rider"
    assert artwork.search_term("Pokémon FireRed Version (English Ver.)") == "Pokémon FireRed Version"
    assert artwork.search_term("Devil May Cry 3") == "Devil May Cry 3"


def test_fetch_saves_steam_names_and_never_overwrites(tmp_path):
    grid = tmp_path / "grid"; grid.mkdir()
    (grid / "123_hero.jpg").write_bytes(b"ESCOLHIDA-PELO-USUARIO")
    calls = []
    res = artwork.fetch_for(123, "God of War 1 (Dublado)", grid, fake_fetch(calls))
    assert res["game"] == "God of War"
    assert sorted(res["saved"]) == ["123.png", "123_logo.png", "123p.png"]
    assert res["skipped"] == ["123_hero"]
    assert (grid / "123_hero.jpg").read_bytes() == b"ESCOLHIDA-PELO-USUARIO"
    assert any("dimensions=600x900" in c for c in calls)
    res2 = artwork.fetch_for(123, "God of War 1 (Dublado)", grid, fake_fetch([]))
    assert res2["saved"] == []  # idempotente


def test_key_file(tmp_path):
    assert artwork.read_key(tmp_path) is None
    (tmp_path / "steamgriddb").write_text(" abc \n")
    assert artwork.read_key(tmp_path) == "abc"


def test_god_of_war_1_does_not_match_ii():
    assert artwork.search_term("God of War 1 (Dublado)") == "God of War"
    res = [{"id": 2, "name": "God of War II"}, {"id": 1, "name": "God of War"}]
    assert artwork.best_match(res, "God of War")["id"] == 1
    assert artwork.best_match(res, "Algo Diferente")["id"] == 2
