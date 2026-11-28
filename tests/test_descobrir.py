"""Descobrir jogos (pedido do dono, 28/11/2026): 'PS2' ou 'fps' trazem os mais bem avaliados."""
import json

import pytest

from dc import bot, descobrir, syncer
from dc.paths import get_paths


@pytest.mark.parametrize("texto,console,genero", [
    ("PS2", "ps2", None), ("melhores ps2", "ps2", None), ("fps", None, "Q185029"), ("fps ps2", "ps2", "Q185029"),
    ("top rpg psp", "psp", "Q744038"), ("jogos de corrida", None, "Q860750"), ("terror", None, "Q333967"),
])
def test_interpretar(texto, console, genero):
    r = descobrir.interpretar(texto)
    assert r["console"] == console and (r["genero"][1] if r["genero"] else None) == genero


@pytest.mark.parametrize("texto", ["god of war", "mario kart wii", "Resident Evil", "hades", "super tilt"])
def test_nome_de_jogo_continua_indo_para_a_busca(texto):
    assert descobrir.interpretar(texto) is None


def linha(jogo, nome, n, pq=None, ano=2001):
    b = {"jogo": {"value": f"http://www.wikidata.org/entity/{jogo}"}, "nome": {"value": nome},
         "n": {"value": str(n)}, "ano": {"value": str(ano)}}
    if pq:
        b["pq"] = {"value": f"http://www.wikidata.org/entity/{pq}"}
    return b


def test_nota_da_plataforma_vale_e_nota_so_de_outra_fica_de_fora(tmp_path, monkeypatch):
    """28/11/2026: Half-Life aparecia com 96 no PS2 (nota do PC)."""
    ps2, pc = descobrir.PLATAFORMA_WD["ps2"], descobrir.PLATAFORMA_WD["pc"]
    linhas = [linha("Q1", "Half-Life", 96, pc), linha("Q1", "Half-Life", 87, ps2), linha("Q2", "MGS2", 96, ps2),
              linha("Q3", "Só PC", 99, pc), linha("Q4", "Geral", 90)]
    consultas = []

    def baixar(consulta, abrir=None, timeout=60):
        consultas.append(consulta)
        return linhas if "p:P444" in consulta else []
    monkeypatch.setattr(descobrir, "_baixar", baixar)
    jogos = descobrir.melhores(get_paths(tmp_path).ensure(), "ps2", None)
    assert [(j["nome"], j["nota"], j["tipo_nota"]) for j in jogos[:3]] == [
        ("MGS2", 96, "plataforma"), ("Geral", 90, "geral"), ("Half-Life", 87, "plataforma")]
    assert "Só PC" not in [j["nome"] for j in jogos]
    n = len(consultas)
    descobrir.melhores(get_paths(tmp_path).ensure(), "ps2", None)
    assert len(consultas) == n  # 2ª vez: cache


def test_bot_ps2_lista_os_melhores_com_botao_de_busca(tmp_path, monkeypatch):
    b = bot.Bot(get_paths(tmp_path).ensure(), "TOK")
    b.cfg["allowed"] = [1]
    b.sent = []
    b.call = lambda method, **kw: b.sent.append(kw) or []
    b.limited = lambda uid: False
    monkeypatch.setattr(syncer, "_cfg", lambda p: {"downloads_root": str(tmp_path / "dl")})
    monkeypatch.setattr(descobrir, "melhores", lambda paths, c, g, **k: [
        {"nome": "Metal Gear Solid 2", "nota": 96, "tipo_nota": "plataforma", "ano": 2001},
        {"nome": "Resident Evil 4", "nota": None, "tipo_nota": None, "ano": 2005}])
    r = b.handle_message({"from": {"id": 1}, "chat": {"id": 9}, "text": "PS2"})
    assert "mais bem avaliados de PlayStation 2" in r or "mais bem avaliados" in r
    for d in b.descobertas.values():
        d["future"].result(timeout=5)
    b.notify_descobertas()
    txt = b.sent[-1]["text"]
    assert "1. Metal Gear Solid 2 (2001) — 96" in txt and "Resident Evil 4 (2005) — sem nota" in txt
    kb = json.loads(b.sent[-1]["reply_markup"])["inline_keyboard"]
    cmd = b.cfg["botoes"][kb[0][0]["callback_data"][2:]]
    assert cmd == "/busca Metal Gear Solid 2 ps2"


def test_wikidata_fora_do_ar_avisa(tmp_path, monkeypatch):
    b = bot.Bot(get_paths(tmp_path).ensure(), "TOK")
    b.cfg["allowed"] = [1]
    b.sent = []
    b.call = lambda method, **kw: b.sent.append(kw) or []
    b.limited = lambda uid: False

    def cai(*a, **k):
        raise OSError("timed out")
    monkeypatch.setattr(descobrir, "melhores", cai)
    b.handle_message({"from": {"id": 1}, "chat": {"id": 9}, "text": "fps"})
    for d in b.descobertas.values():
        try:
            d["future"].result(timeout=5)
        except OSError:
            pass
    b.notify_descobertas()
    assert "Não consegui consultar as notas" in b.sent[-1]["text"]
