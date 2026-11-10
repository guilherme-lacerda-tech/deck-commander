"""Simulação 10/11: IA que cai no meio da resposta (túnel do PC) não pode travar nem derrubar a tradução."""
import http.client
import json
import threading

from dc.paths import get_paths
from dc.traducao import ia


def _prov(name, fail_from=None):
    calls = {"n": 0}

    def http(url, body, headers, timeout):
        calls["n"] += 1
        if fail_from and calls["n"] >= fail_from:
            raise http.client.IncompleteRead(b"")
        user = body["messages"][-1]["content"]
        try:
            txt = json.dumps({k: "PT " + v for k, v in json.loads(user).items()})
        except ValueError:
            txt = "PT " + user
        return {"message": {"content": txt}}
    return ia.Provider(name, {"tipo": "ollama", "url": "http://x", "gratis": True, "modelo": "m"}, "", http)


def _run(fn, limit=30):
    box = {}
    th = threading.Thread(target=lambda: box.update(r=fn()), daemon=True)
    th.start(); th.join(limit)
    assert not th.is_alive(), "a tradução travou"
    return box["r"]


def test_parallel_provider_dropping_mid_response_does_not_hang(tmp_path):
    P = get_paths(tmp_path).ensure()
    cfg = dict(ia.load_cfg(P), paralelo=True, lote=10)
    items = [ia.Item(f"t{i}", f"Hello {i}") for i in range(200)]
    r = _run(lambda: ia.translate(P, cfg, items, "j", chain=[_prov("ok"), _prov("cai", fail_from=2)]))
    assert len(r.translated) == 200
    assert any("cai" in e for e in r.errors)


def test_serial_provider_dropping_falls_back(tmp_path, monkeypatch):
    def drop(*a, **k):
        raise http.client.IncompleteRead(b"")  # a conexão do túnel caiu no meio da resposta
    monkeypatch.setattr(ia.urllib.request, "urlopen", drop)
    P = get_paths(tmp_path).ensure()
    cfg = dict(ia.load_cfg(P), paralelo=False, lote=10)
    items = [ia.Item(f"t{i}", f"Hello {i}") for i in range(30)]
    cai = ia.Provider("cai", {"tipo": "ollama", "url": "http://x", "gratis": True, "modelo": "m"})  # usa o _http real
    r = _run(lambda: ia.translate(P, cfg, items, "j2", chain=[cai, _prov("reserva")]))
    assert len(r.translated) == 30 and any("cai" in e for e in r.errors)


def test_ollama_unexpected_answer_is_provider_error():
    p = ia.Provider("x", {"tipo": "ollama", "url": "http://x"}, "", lambda *a: {"error": "model not found"})
    try:
        p.chat("s", "u")
    except ia.ProviderError as e:
        assert "inesperada" in str(e)
    else:
        raise AssertionError("devia virar ProviderError")
