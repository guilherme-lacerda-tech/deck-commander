import pytest


@pytest.fixture(autouse=True)
def _no_retry_wait(monkeypatch):
    """Nos testes, nova tentativa da IA é imediata (no Deck espera alguns segundos)."""
    from dc.traducao import ia
    monkeypatch.setattr(ia, "RETRY_WAIT", 0)
