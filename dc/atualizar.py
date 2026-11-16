"""Atualização automática (pedido 15/11/2026: "toda atualização precisa reinstalar, não tem busca de atualização").

Uma vez por dia o serviço confere no GitHub (repositório público, sem senha) se há versão nova. Se houver, avisa no
painel e no Telegram. Ao tocar em "Atualizar" (painel) ou mandar /atualizar:
1. baixa a versão nova (arquivo do próprio GitHub) para uma pasta temporária;
2. roda os testes do Deck Commander NO PRÓPRIO DECK — se algum falhar, não troca nada;
3. guarda a versão atual em ~/deck-commander.anterior (o /voltar desfaz) e copia a nova no lugar;
4. termina a instalação (plugin do Decky, serviços, emuladores prontos) e reinicia os serviços.
Configurações, jogos, saves e traduções ficam fora da pasta do programa: nada disso é tocado.

    python3 -m dc.atualizar            -> confere e diz se há versão nova
    python3 -m dc.atualizar aplicar    -> atualiza (o mesmo que o botão do painel)
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path

REPO = "guilherme-lacerda-tech/deck-commander"
API = f"https://api.github.com/repos/{REPO}/commits/main"
TARBALL = "https://codeload.github.com/" + REPO + "/tar.gz/{sha}"
INTERVALO = 24 * 3600


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "deck-commander", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def pasta_programa(home: Path | None = None) -> Path:
    return (home or Path.home()) / "deck-commander"


def versao_local(home: Path | None = None) -> str:
    """Commit instalado: VERSAO.txt (instalador e implantação gravam) ou o git da pasta."""
    pasta = pasta_programa(home)
    try:
        v = (pasta / "VERSAO.txt").read_text("utf-8").split()
        if v:
            return v[0]
    except OSError:
        pass
    r = subprocess.run(["git", "-C", str(pasta), "rev-parse", "HEAD"], capture_output=True, text=True, check=False)
    return r.stdout.strip() if r.returncode == 0 else ""


def _cache(paths) -> Path:
    return paths.state / "atualizacao.json"


def estado(paths) -> dict:
    try:
        return json.loads(_cache(paths).read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def verificar(paths, get_json=_get_json, home: Path | None = None, agora: float | None = None) -> dict | None:
    """Há versão nova? Devolve {"sha", "data", "resumo"} ou None. Guarda o resultado (o painel mostra)."""
    agora = agora or time.time()
    try:
        c = get_json(API)
        sha = c["sha"]
        data = c["commit"]["committer"]["date"][:10]
        resumo = c["commit"]["message"].splitlines()[0][:160]
    except Exception as e:  # noqa: BLE001 — sem internet: tenta amanhã
        st = estado(paths)
        st.update(conferido=agora, erro=f"{type(e).__name__}")
        _cache(paths).write_text(json.dumps(st, ensure_ascii=False), "utf-8")
        return None
    local = versao_local(home)
    nova = None if (local and sha.startswith(local)) or (local and local.startswith(sha[:7])) else \
        {"sha": sha, "data": data, "resumo": resumo}
    st = estado(paths)
    st.update(conferido=agora, erro=None, local=local, nova=nova)
    _cache(paths).write_text(json.dumps(st, ensure_ascii=False), "utf-8")
    return nova


def avisar_se_nova(paths, get_json=_get_json, home: Path | None = None, agora: float | None = None) -> str | None:
    """Chamado pelo serviço: confere 1×/dia e devolve o aviso (uma vez por versão)."""
    agora = agora or time.time()
    st = estado(paths)
    if st.get("conferido") and agora - st["conferido"] < INTERVALO:
        return None
    nova = verificar(paths, get_json, home, agora)
    if not nova or estado(paths).get("avisado") == nova["sha"]:
        return None
    st = estado(paths)
    st["avisado"] = nova["sha"]
    _cache(paths).write_text(json.dumps(st, ensure_ascii=False), "utf-8")
    return (f"🆕 Atualização do Deck Commander disponível ({nova['data']}): {nova['resumo']}\n"
            "Para atualizar: painel do Deck Commander → Atualizar, ou mande /atualizar aqui. "
            "Jogos, saves e configurações ficam como estão; /voltar desfaz.")


def _baixar(url: str, destino: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "deck-commander"})
    with urllib.request.urlopen(req, timeout=300) as r, open(destino, "wb") as f:
        shutil.copyfileobj(r, f)


def preparar(sha: str, trabalho: Path, baixar=_baixar) -> Path:
    """Baixa e extrai a versão; devolve a pasta com o programa novo."""
    arq = trabalho / "nova.tar.gz"
    baixar(TARBALL.format(sha=sha), arq)
    with tarfile.open(arq, "r:gz") as tar:
        for m in tar.getmembers():  # nada fora da pasta de trabalho (arquivo de fora é dado não confiável)
            alvo = (trabalho / "x" / m.name).resolve()
            if not str(alvo).startswith(str((trabalho / "x").resolve())) or m.issym() or m.islnk():
                raise RuntimeError(f"arquivo estranho no pacote: {m.name}")
        tar.extractall(trabalho / "x", filter="data")  # conferido acima
    pastas = [p for p in (trabalho / "x").iterdir() if p.is_dir()]
    if len(pastas) != 1 or not (pastas[0] / "dc/__init__.py").exists() or not (pastas[0] / "setup-deck.sh").exists():
        raise RuntimeError("o pacote baixado não é o Deck Commander")
    return pastas[0]


def testar(pasta: Path, rodar=subprocess.run) -> tuple[bool, str]:
    """Testes do Deck Commander no próprio Deck. Sem pytest instalado: segue (avisando)."""
    py = Path.home() / ".local/share/deck-commander/venv/bin/python"
    if not py.exists():
        return True, "testes não rodados (sem o ambiente de testes)"
    r = rodar([str(py), "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "tests"], cwd=str(pasta),
              capture_output=True, text=True, timeout=1800, check=False)
    ultima = (r.stdout.strip().splitlines() or ["?"])[-1]
    return r.returncode == 0, ultima


def aplicar(paths, sha: str | None = None, home: Path | None = None, baixar=_baixar, rodar=subprocess.run,
            get_json=_get_json) -> str:
    """Atualiza (ver o topo). A troca final roda fora dos serviços, porque eles serão reiniciados."""
    if sha is None:
        nova = verificar(paths, get_json, home)
        if not nova:
            return "O Deck Commander já está na versão mais nova."
        sha = nova["sha"]
    atual = pasta_programa(home)
    trabalho = Path(tempfile.mkdtemp(prefix="dc-atualizar-"))
    try:
        nova_pasta = preparar(sha, trabalho, baixar)
        ok, resumo = testar(nova_pasta, rodar)
        if not ok:
            return f"❌ A versão nova não passou nos testes deste Deck ({resumo}). Nada foi trocado."
        (nova_pasta / "VERSAO.txt").write_text(f"{sha[:7]} {time.strftime('%d/%m %H:%M')}\n", "utf-8")
        anterior = atual.with_name("deck-commander.anterior")
        staging = atual.with_name("deck-commander.nova")
        shutil.rmtree(staging, ignore_errors=True)
        shutil.copytree(nova_pasta, staging, symlinks=True)
        script = (f"set -e; sleep 2; rm -rf '{anterior}'; mv '{atual}' '{anterior}'; mv '{staging}' '{atual}'; "
                  f"cd '{atual}'; chmod +x ./*.sh; python3 -m dc.atualizar depois >> "
                  f"'{paths.logs / 'atualizacao.log'}' 2>&1; "
                  "systemctl --user restart deck-commander-bot deck-commander-power")
        rodar(["systemd-run", "--user", "--collect", "--unit", f"dc-atualizar-{int(time.time())}", "bash", "-c", script],
              capture_output=True, text=True, check=False)
        st = estado(paths)
        st.update(nova=None, local=sha[:7], atualizado=time.time())
        _cache(paths).write_text(json.dumps(st, ensure_ascii=False), "utf-8")
        return (f"✅ Atualizando para a versão de {time.strftime('%d/%m')} ({resumo}). Em ~1 minuto o painel e o bot "
                "voltam já na versão nova. Se algo ficar estranho: /voltar.")
    finally:
        shutil.rmtree(trabalho, ignore_errors=True)


def depois(log=print) -> None:
    """Roda NA VERSÃO NOVA, logo depois da troca: termina a instalação sem baixar emuladores de novo."""
    from . import setup
    from .paths import get_paths
    paths = get_paths().ensure()
    linhas: list[str] = []
    for passo in (lambda: setup.write_units(linhas), lambda: setup.preparar_primeira_vez(log=linhas),
                  lambda: setup.write_emulators_json(paths, linhas), lambda: setup.setup_plugin(linhas)):
        try:
            passo()
        except Exception as e:  # noqa: BLE001 — um passo que falha não impede os outros
            linhas.append(f"AVISO: {type(e).__name__}: {e}")
    for ln in linhas:
        log(ln)


def main(argv: list[str]) -> int:
    from .paths import get_paths
    paths = get_paths().ensure()
    if argv[:1] == ["aplicar"]:
        res = aplicar(paths)
        print(res)
        try:
            from .traducao import comunidade
            comunidade.avisar(paths, res)
        except Exception:  # noqa: BLE001, S110 — o aviso é conforto; o resultado já foi impresso
            pass
    elif argv[:1] == ["depois"]:
        depois()
    elif not argv:
        nova = verificar(paths)
        print(f"Versão nova ({nova['data']}): {nova['resumo']}" if nova else "Já está na versão mais nova.")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
