"""Conferência da tradução retrô (romtranslate audit --json). Falha real 14/11/2026 no Nova the Squirrel:
"remaining" veio como lista de trechos e a conferência quebrava com int(lista)."""
from dc.traducao import rts


def test_restantes_conta_a_lista_de_trechos():
    au = {"notText": 547, "remaining": [{"id": "a", "text": "Game paused"}, {"id": "b", "text": "Credits"}]}
    assert rts.restantes(au) == 2


def test_restantes_aceita_numero_e_vazio():
    assert rts.restantes({"remaining": 7}) == 7
    assert rts.restantes({"untranslated": "3"}) == 3
    assert rts.restantes({}) == 0
    assert rts.restantes({"remaining": None, "sourceLanguage": 4}) == 4
