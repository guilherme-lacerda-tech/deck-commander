"""Atualização automática (pedido 15/11/2026: "toda atualização precisa reinstalar")."""
import io
import json
import tarfile

import pytest

from dc import atualizar as A
from dc.paths import get_paths

SHA = "abcdef1234567890abcdef1234567890abcdef12"


def _commit(sha=SHA, status="ahead"):
    def get(url):
        if "/compare/" in url:
            return {"status": status}
        return {"sha": sha, "commit": {"committer": {"date": "2026-11-16T03:00:00Z"},
                                       "message": "Biblioteca: jogos do EmuDeck fora\n\ndetalhes"}}
    return get


@pytest.fixture
def P(tmp_path):
    return get_paths(tmp_path / "dc").ensure()


def _instalado(home, versao="1630b3f"):
    (home / "deck-commander").mkdir(parents=True)
    (home / "deck-commander/VERSAO.txt").write_text(f"{versao} 14/11 13:09\n")


def test_verificar_ve_versao_nova_e_igual(P, tmp_path):
    _instalado(tmp_path)
    nova = A.verificar(P, _commit(), tmp_path)
    assert nova == {"sha": SHA, "data": "2026-11-16", "resumo": "Biblioteca: jogos do EmuDeck fora"}
    assert A.estado(P)["nova"]["sha"] == SHA  # o painel mostra
    (tmp_path / "deck-commander/VERSAO.txt").write_text("abcdef1 16/11 03:00\n")
    assert A.verificar(P, _commit(), tmp_path) is None


def test_sem_internet_nao_quebra(P, tmp_path):
    def falha(url):
        raise OSError("sem rede")
    assert A.verificar(P, falha, tmp_path) is None and A.estado(P)["erro"] == "OSError"


def test_aviso_uma_vez_por_dia_e_por_versao(P, tmp_path):
    _instalado(tmp_path)
    msg = A.avisar_se_nova(P, _commit(), tmp_path, agora=1000.0)
    assert "Atualização do Deck Commander disponível" in msg and "/atualizar" in msg
    assert A.avisar_se_nova(P, _commit(), tmp_path, agora=2000.0) is None  # mesmo dia
    assert A.avisar_se_nova(P, _commit(), tmp_path, agora=1000.0 + A.INTERVALO + 1) is None  # mesma versão


def _tar(arquivos: dict) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for nome, dados in arquivos.items():
            info = tarfile.TarInfo(nome)
            info.size = len(dados)
            t.addfile(info, io.BytesIO(dados))
    return buf.getvalue()


def _baixar(dados):
    def baixar(url, destino):
        assert SHA in url
        destino.write_bytes(dados)
    return baixar


BOM = {f"deck-commander-{SHA}/dc/__init__.py": b"", f"deck-commander-{SHA}/setup-deck.sh": b"#!/bin/bash\n"}


def test_preparar_recusa_pacote_estranho(tmp_path):
    with pytest.raises(RuntimeError, match="estranho"):
        A.preparar(SHA, tmp_path, _baixar(_tar({"../fora.txt": b"x"})))
    t2 = tmp_path / "b"; t2.mkdir()
    with pytest.raises(RuntimeError, match="não é o Deck Commander"):
        A.preparar(SHA, t2, _baixar(_tar({"outra/coisa.txt": b"x"})))
    t3 = tmp_path / "c"; t3.mkdir()
    assert (A.preparar(SHA, t3, _baixar(_tar(BOM))) / "setup-deck.sh").exists()


class _R:
    def __init__(self, rc=0, out="10 passed"):
        self.returncode, self.stdout = rc, out


def test_aplicar_testa_antes_e_troca_fora_do_servico(P, tmp_path, monkeypatch):
    _instalado(tmp_path)
    monkeypatch.setattr(A, "testar", lambda pasta, rodar: (True, "10 passed"))
    chamadas = []
    res = A.aplicar(P, SHA, tmp_path, _baixar(_tar(BOM)), lambda cmd, **k: chamadas.append(cmd) or _R())
    assert res.startswith("✅ Atualizando")
    nova = tmp_path / "deck-commander.nova"
    assert (nova / "VERSAO.txt").read_text().startswith(SHA[:7]) and (nova / "setup-deck.sh").exists()
    assert chamadas[-1][:3] == ["systemd-run", "--user", "--collect"]
    script = chamadas[-1][-1]
    assert "deck-commander.anterior" in script and "dc.atualizar depois" in script and "systemctl --user restart" in script
    assert (tmp_path / "deck-commander/VERSAO.txt").read_text().startswith("1630b3f")  # a troca é do systemd-run


def test_aplicar_nao_troca_se_os_testes_falham(P, tmp_path, monkeypatch):
    _instalado(tmp_path)
    monkeypatch.setattr(A, "testar", lambda pasta, rodar: (False, "1 failed, 9 passed"))
    chamadas = []
    res = A.aplicar(P, SHA, tmp_path, _baixar(_tar(BOM)), lambda cmd, **k: chamadas.append(cmd) or _R())
    assert "não passou nos testes" in res and chamadas == []
    assert not (tmp_path / "deck-commander.nova").exists()


def test_aplicar_sem_versao_nova(P, tmp_path):
    _instalado(tmp_path, SHA[:7])
    assert "mais nova" in A.aplicar(P, None, tmp_path, get_json=_commit())


def test_painel_mostra_atualizacao(P, tmp_path, monkeypatch):
    from dc import painel
    (P.state / "atualizacao.json").write_text(json.dumps({"nova": {"sha": SHA, "data": "2026-11-16", "resumo": "x"}}))
    pt = painel.Ponte(P, qbt=object())
    assert painel._atualizacao(pt)["sha"] == SHA


def test_versao_do_github_mais_velha_nao_e_oferecida(P, tmp_path):
    """Falha real 16/11/2026: logo depois do envio a API respondia o commit anterior e o Deck oferecia "atualizar"."""
    _instalado(tmp_path, "24760ac")
    assert A.verificar(P, _commit(status="behind"), tmp_path) is None
    assert A.verificar(P, _commit(status="diverged"), tmp_path) is None
    assert A.verificar(P, _commit(status="ahead"), tmp_path)["sha"] == SHA
