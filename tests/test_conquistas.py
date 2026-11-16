"""RetroAchievements no painel e no bot (pedido 15/11/2026: "ele gosta de platinar jogos")."""
import json
import os

import pytest

from dc import conquistas as C
from dc.paths import get_paths

CHAVE = "AbCdEf0123456789AbCdEf0123456789"


@pytest.fixture
def P(tmp_path):
    return get_paths(tmp_path / "dc").ensure()


def _api(url):
    if "API_GetUserProfile" in url:
        assert CHAVE in url
        return {"User": "Irmao", "TotalPoints": 1234}
    if "API_GetUserSummary" in url:
        return {"User": "Irmao", "TotalPoints": 1234, "TotalTruePoints": 3000, "Rank": 5000,
                "RecentlyPlayed": [{"GameID": 1, "Title": "Castlevania SOTN", "ConsoleName": "PlayStation",
                                    "LastPlayed": "2026-11-15 20:00:00"},
                                   {"GameID": 2, "Title": "Mario", "ConsoleName": "NES"},
                                   {"GameID": 3, "Title": "Sem conquistas", "ConsoleName": "SNES"}],
                "Awarded": {"1": {"NumPossibleAchievements": 10, "NumAchieved": 10, "NumAchievedHardcore": 10},
                            "2": {"NumPossibleAchievements": 20, "NumAchieved": 5, "NumAchievedHardcore": 0}}}
    raise AssertionError(url)


def test_salvar_confere_no_site_e_guarda_so_para_o_usuario(P):
    assert "Irmao ligada" in C.salvar(P, " Irmao ", CHAVE + "\n", _api)
    assert C.credenciais(P) == ("Irmao", CHAVE)
    if os.name == "posix":
        assert oct((P.secrets / C.SEGREDO).stat().st_mode)[-3:] == "600"


@pytest.mark.parametrize("usuario,chave,erro", [("", CHAVE, "usuário"), ("Irmão!", CHAVE, "usuário"),
                                                ("Irmao", "curta", "Web API Key")])
def test_salvar_recusa_dados_errados_com_explicacao(P, usuario, chave, erro):
    with pytest.raises(ValueError, match=erro):
        C.salvar(P, usuario, chave, _api)


def test_site_recusa_a_chave(P):
    def nega(url):
        raise OSError("401")
    with pytest.raises(ValueError, match="não aceitou"):
        C.salvar(P, "Irmao", CHAVE, nega)


def test_resumo_mostra_progresso_e_masterizados(P):
    C.salvar(P, "Irmao", CHAVE, _api)
    r = C.resumo(P, _api)
    assert r["pontos"] == 1234 and r["masterizados"] == 1
    sotn, mario, sem = r["jogos"]
    assert sotn["masterizado"] and sotn["pct"] == 100 and sotn["ultimo"] == "2026-11-15"
    assert not mario["completo"] and mario["pct"] == 25 and mario["feitos"] == 5
    assert sem["total"] == 0 and sem["pct"] == 0
    t = C.texto(r)
    assert "👑 Castlevania SOTN" in t and "5/20 (25%)" in t


def test_sem_internet_mostra_o_ultimo_resumo(P):
    C.salvar(P, "Irmao", CHAVE, _api)
    C.resumo(P, _api)
    def falha(url):
        raise OSError("sem rede")
    r = C.resumo(P, falha)
    assert r["masterizados"] == 1 and "sem conexão" in r["aviso"]


def test_sem_conta_explica_como_ligar(P):
    assert C.resumo(P, _api) == {"ligado": False}
    assert "Web API Key" in C.texto({"ligado": False})


def test_painel_liga_e_desliga(P):
    from dc import painel
    pt = painel.Ponte(P, qbt=object())
    assert painel.conquistas(pt, {}) == {"ligado": False}
    with pytest.raises(painel.Erro, match="usuário"):
        painel.conquistas_salvar(pt, {"usuario": "", "chave": CHAVE})
    (P.secrets / C.SEGREDO).write_text(json.dumps({"usuario": "Irmao", "chave": CHAVE}))
    assert "apagada" in painel.conquistas_sair(pt, {})["texto"] and C.credenciais(P) is None
