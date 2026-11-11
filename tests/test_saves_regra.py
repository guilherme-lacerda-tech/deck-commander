from dc import saves_regra as R

D = lambda sha, mt=1000: {"sha256": sha, "mtime": mt}  # noqa: E731


def acoes(a):
    return {x["destino"]: x["acao"] for x in a}


def test_regras():
    ult = {"s1": "a", "s2": "a", "s3": "a", "s4": "a"}
    deck = {"s1": D("b"), "s2": D("a"), "s3": D("b"), "s4": D("a"), "s5": D("n")}
    pc = {"s1": D("a"), "s2": D("c"), "s3": D("c"), "s4": D("a"), "s6": D("m")}
    a = acoes(R.decidir(deck, pc, ult))
    assert a == {"s1": "deck->pc", "s2": "pc->deck", "s3": "conflito", "s5": "deck->pc", "s6": "pc->deck"}


def test_primeira_vez_e_resumo():
    a = acoes(R.decidir({"x": D("a", 5000), "y": D("a", 1000), "z": D("b", 1000)},
                        {"x": D("b", 1000), "y": D("c", 9000), "z": D("c", 1060)}, {}))
    assert a == {"x": "deck->pc", "y": "pc->deck", "z": "conflito"}
    assert R.resumo([]) .startswith("Saves iguais")
    assert R.novo_ultimo({"x": D("a"), "y": D("b")}, {"x": D("a"), "y": D("c")}) == {"x": "a"}


def test_sumiu_de_um_lado_nao_apaga():
    a = R.decidir({}, {"s": D("a")}, {"s": "a"})
    assert acoes(a) == {"s": "pc->deck"}


def test_bot_saves_enfileira(tmp_path, monkeypatch):
    from dc import bot, transferir
    from dc.paths import get_paths
    paths = get_paths(tmp_path / "dc").ensure()
    monkeypatch.setattr(transferir, "_home", lambda home=None: tmp_path)
    x = bot.Bot(paths, "T"); x.cfg["allowed"] = [1]
    monkeypatch.setattr(x, "_map", lambda: {"switch2-dk": {"title": "Donkey Kong", "console": "switch2", "rom": "/x"}})
    r = x.handle(1, 1, "/saves donkey pc")
    assert "PC" in r and "na fila" in r
    f = transferir.ler_fila()
    assert f[-1]["direcao"] == "saves" and f[-1]["game_id"] == "switch2-dk"
