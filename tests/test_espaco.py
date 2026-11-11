"""Sugestões de limpeza de disco (dc/espaco.py)."""
from datetime import datetime, timedelta, timezone

from dc import espaco

AGORA = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
GB = 1024 ** 3


def test_ultimas_e_sugestoes(tmp_path):
    log = tmp_path / "launch.log"
    log.write_text(
        "2026-07-01T10:00:00+00:00 lançando switch-zelda: ['x']\n"
        "lixo sem data\n"
        "2026-08-01T10:00:00+00:00 lançando switch-zelda: ['x']\n"
        "2026-11-09T10:00:00+00:00 lançando ps2-sotc: ['x']\n"
        "2026-11-09T10:00:01+00:00 qualidade: algo\n", "utf-8")
    ult = espaco.ultimas_jogadas(log)
    assert ult["switch-zelda"] == datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc) and set(ult) == {"switch-zelda", "ps2-sotc"}
    lm = {"switch-zelda": {"title": "Zelda", "console": "switch", "rom": "/z"},
          "ps2-sotc": {"title": "SotC", "console": "ps2", "rom": "/s"},
          "psx-velho": {"title": "Velho", "console": "psx", "rom": "/v"},
          "gba-mini": {"title": "Mini", "console": "gba", "rom": "/m"},
          "pc-x": {"title": "PC", "console": "pc", "rom": "x"},
          "wii-tirado": {"title": "Tirado", "console": "wii", "rom": "/t", "removed": True}}
    tam = {"switch-zelda": 20 * GB, "ps2-sotc": 4 * GB, "psx-velho": 3 * GB, "gba-mini": 1024}
    chamados = []

    def tamanho(g):
        chamados.append(g)
        return tam.get(g, 50 * GB)
    inst = {"psx-velho": AGORA - timedelta(days=120), "gba-mini": AGORA - timedelta(days=200)}
    s = espaco.sugestoes(lm, ult, tamanho, AGORA, data_instalacao=lambda g: inst.get(g))
    assert [x["gid"] for x in s] == ["switch-zelda", "psx-velho"]
    assert s[0]["dias_parado"] == 101 and s[0]["gb"] == 20.0 and not s[0]["nunca_jogado"]
    assert s[1]["nunca_jogado"]
    assert "ps2-sotc" not in chamados  # jogado ontem: nem calcula tamanho
    assert espaco.texto(s[0]) == "Você não joga Zelda há 101 dias e ele ocupa 20.0 GB."
    assert espaco.texto(s[1]).startswith("Você instalou Velho há 120 dias, nunca jogou")
