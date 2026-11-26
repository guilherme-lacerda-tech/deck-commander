import json
import urllib.error

import pytest

from dc import prowlarr
from dc.paths import get_paths


def test_busca_usa_cabecalho_de_chave_e_filtra_respostas(tmp_path):
    p = get_paths(tmp_path).ensure()
    (p.config / "prowlarr.json").write_text(json.dumps({"url": "http://127.0.0.1:9696", "api_key": "segredo"}))
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, n):
            return json.dumps([{"title": "Jogo PS2", "magnetUrl": "magnet:?xt=urn:btih:abc"},
                               {"title": "Sem magnet"}]).encode()
    def abrir(req, timeout):
        assert req.get_header("X-api-key") == "segredo"
        assert "segredo" not in req.full_url
        assert "query=Jogo" in req.full_url
        return Response()
    assert prowlarr.pesquisar(p, "Jogo", abrir)[0]["titulo"] == "Jogo PS2"
    assert len(prowlarr.pesquisar(p, "Jogo", abrir)) == 1


def test_falha_de_rede_nao_expoe_detalhes(tmp_path):
    p = get_paths(tmp_path).ensure()
    (p.config / "prowlarr.json").write_text(json.dumps({"url": "http://localhost:9696", "api_key": "segredo"}))
    def falha(req, timeout):
        raise urllib.error.URLError("segredo")
    with pytest.raises(prowlarr.BuscaErro, match="não consegui consultar") as erro:
        prowlarr.pesquisar(p, "Jogo", falha)
    assert "segredo" not in str(erro.value)


def test_fonte_nao_configurada(tmp_path):
    assert prowlarr.pesquisar(get_paths(tmp_path).ensure(), "Jogo") is None
