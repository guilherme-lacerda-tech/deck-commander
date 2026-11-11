"""Implanta a versão atual no Steam Deck com segurança (substitui os comandos soltos de antes).

    python tools/implantar.py [deck@IP]          (padrão: o endereço em %USERPROFILE%/.deck-commander/deck.txt)

Recusa se: há merge em conflito/sem terminar, há mudança não salva (commit) em dc/ ou decky-plugin/, ou algum teste
falha no PC. Depois testa A MESMA versão no Deck (numa pasta temporária) e só então copia, reinicia o bot e o serviço
de energia e atualiza o plugin do Decky. Nenhuma tradução em andamento é parada (elas rodam em serviços próprios).
Falhas antigas que isto impede: implantar no meio de um merge com conflito; implantar arquivo de teste quebrado.
"""
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CHAVE = str(Path.home() / ".ssh" / "deck_commander_ed25519")


def sh(cmd, **kw):
    return subprocess.run(cmd, cwd=RAIZ, text=True, capture_output=True, **kw)


def parar(msg):
    print("NÃO implantei:", msg)
    sys.exit(1)


def main():
    alvo = sys.argv[1] if len(sys.argv) > 1 else None
    if not alvo:
        f = Path.home() / ".deck-commander" / "deck.txt"
        alvo = f.read_text().strip() if f.exists() else "deck@steamdeck"
    if (RAIZ / ".git" / "MERGE_HEAD").exists() or sh(["git", "diff", "--name-only", "--diff-filter=U"]).stdout.strip():
        parar("há um merge sem terminar ou com conflito")
    sujos = [l for l in sh(["git", "status", "--porcelain", "dc", "decky-plugin", "config"]).stdout.splitlines() if l.strip()]
    if sujos:
        parar("há mudanças sem commit em dc/decky-plugin/config:\n  " + "\n  ".join(sujos))
    print("testes no PC…")
    r = sh([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], timeout=1800)
    if r.returncode != 0:
        parar("testes falharam no PC:\n" + "\n".join(r.stdout.splitlines()[-15:]))
    print(r.stdout.strip().splitlines()[-1])
    ssh = ["ssh", "-i", CHAVE, "-o", "BatchMode=yes", alvo]
    remoto = ("rm -rf /tmp/dc-new && mkdir /tmp/dc-new && tar -x -C /tmp/dc-new && cd /tmp/dc-new && "
              "nice ~/.local/share/deck-commander/venv/bin/python -m pytest -q -p no:cacheprovider tests 2>&1 | tail -1 && "
              "test ${PIPESTATUS[0]} -eq 0 && cp -a /tmp/dc-new/. ~/deck-commander/ && "
              "systemctl --user restart deck-commander-bot deck-commander-power && cd ~/deck-commander && "
              "python3 -c 'from dc import setup; l=[]; setup.setup_plugin(l); print(*l)' && echo IMPLANTADO")
    import shlex
    p = subprocess.run(ssh + ["bash -c " + shlex.quote(remoto)], input=subprocess.run(
        ["git", "archive", "--format=tar", "HEAD"], cwd=RAIZ, capture_output=True).stdout, capture_output=True, timeout=1800)
    saida = p.stdout.decode("utf-8", "replace") + p.stderr.decode("utf-8", "replace")
    print(saida.strip())
    if "IMPLANTADO" not in saida:
        parar("os testes no Deck falharam ou a cópia não terminou (o Deck continua com a versão anterior)")


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    main()
