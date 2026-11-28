"""Atualização automática (pedido 15/11/2026: "toda atualização precisa reinstalar")."""
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

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
    assert A.verificar(P, falha, tmp_path, git_sha=lambda: None) is None and A.estado(P)["erro"] == "OSError"


def test_fallback_git_quando_api_esta_limitada(P, tmp_path):
    _instalado(tmp_path, "1630b3f")
    def falha(_url):
        raise OSError("API bloqueada")
    nova = A.verificar(P, falha, tmp_path, git_sha=lambda: SHA)
    assert nova and nova["sha"] == SHA and "consulta Git" in A.estado(P)["erro"]
    (tmp_path / "deck-commander/VERSAO.txt").write_text(SHA[:7])
    assert A.verificar(P, falha, tmp_path, git_sha=lambda: SHA) is None


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
    # Não basta comparar texto: ../xevil começa com o texto de x, mas fica fora de x/.
    t_prefixo = tmp_path / "prefixo"; t_prefixo.mkdir()
    with pytest.raises(RuntimeError, match="estranho"):
        A.preparar(SHA, t_prefixo, _baixar(_tar({"../xevil/fora.txt": b"x"})))
    t2 = tmp_path / "b"; t2.mkdir()
    with pytest.raises(RuntimeError, match="não é o Deck Commander"):
        A.preparar(SHA, t2, _baixar(_tar({"outra/coisa.txt": b"x"})))
    t3 = tmp_path / "c"; t3.mkdir()
    assert (A.preparar(SHA, t3, _baixar(_tar(BOM))) / "setup-deck.sh").exists()


def test_atualizacao_recusa_trocar_sem_executor_de_testes(tmp_path, monkeypatch):
    """Atualização sem pytest não pode alegar que testou a versão nova."""
    monkeypatch.setattr(A.Path, "home", lambda: tmp_path)
    ok, resumo = A.testar(tmp_path)
    assert not ok and "ambiente de testes ausente" in resumo


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


def test_falha_de_consulta_nao_e_versao_atual(P, tmp_path, monkeypatch):
    _instalado(tmp_path)
    monkeypatch.setattr(A, "_sha_git", lambda: None)
    def falha(_url):
        raise OSError("sem rede")
    assert "Não consegui consultar" in A.aplicar(P, None, tmp_path, get_json=falha)
    assert A.estado(P)["consulta_ok"] is False


def test_falha_ao_agendar_nao_promete_atualizacao(P, tmp_path, monkeypatch):
    _instalado(tmp_path)
    monkeypatch.setattr(A, "testar", lambda pasta, rodar: (True, "ok"))
    res = A.aplicar(P, SHA, tmp_path, _baixar(_tar(BOM)), lambda *a, **k: _R(rc=1))
    assert "Não consegui iniciar" in res
    assert (tmp_path / "deck-commander/VERSAO.txt").read_text().startswith("1630b3f")


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


def test_after_update_repairs_launcher_after_staging_is_gone(tmp_path):
    """Regressão real de 27/11: pytest publicou um launcher que dependia de /tmp."""
    from dc import library
    home = tmp_path / "private-home"
    home.mkdir()
    staging = tmp_path / "dc-atualizar-extracted"
    staging.mkdir()
    shutil.copytree(Path(A.__file__).parent, staging / "dc", ignore=shutil.ignore_patterns("__pycache__"))
    launcher = library.write_launcher(home, staging)
    save = home / "Emulation/saves/progress.p2s"
    save.parent.mkdir(parents=True)
    save.write_bytes(b"latest gameplay must survive")
    installed = home / "deck-commander"
    staging.rename(installed)
    assert not staging.exists()
    env = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR", "COMSPEC") if key in os.environ}
    env.update(HOME=str(home), USERPROFILE=str(home), DC_ROOT=str(home), PATH=os.defpath,
               PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1",
               XDG_RUNTIME_DIR=str(home / "runtime"),
               DBUS_SESSION_BUS_ADDRESS="unix:path=/nonexistent-dc-test-bus",
               XDG_CONFIG_HOME=str(home / ".config"), XDG_DATA_HOME=str(home / ".local/share"),
               XDG_STATE_HOME=str(home / ".local/state"), XDG_CACHE_HOME=str(home / ".cache"))
    result = subprocess.run([sys.executable, "-m", "dc.atualizar", "depois"], cwd=installed,
                            env=env, capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert str(staging) not in launcher.read_text("utf-8")
    # Exatamente o launcher persistido, executado fora da árvore do programa.
    launched = subprocess.run([sys.executable, str(launcher)], cwd=home, env=env,
                              capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert launched.returncode == 2 and "ModuleNotFoundError" not in launched.stderr
    assert "sem game_id" in (get_paths(home).logs / "launch.log").read_text("utf-8")
    assert save.read_bytes() == b"latest gameplay must survive"
