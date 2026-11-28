"""Implanta a versão atual no Steam Deck com segurança.

    python tools/implantar.py [deck@IP] [--com-jogo-aberto]   (padrão: %USERPROFILE%/.deck-commander/deck.txt)

Ordem (cada passo só roda se o anterior deu certo; qualquer falha deixa o Deck com a versão que estava):
 1. no PC: recusa merge pendente, mudança sem commit em dc/decky-plugin/config e teste falhando;
 2. no Deck: recusa se há jogo aberto (não interrompe partida; --com-jogo-aberto ignora);
 3. no Deck: testa A MESMA versão numa pasta temporária DENTRO DO ISOLAMENTO (dc/test_runner: bubblewrap, HOME e
    XDG falsos, sem rede). Falha real 27/11/2026: teste rodado direto escreveu no HOME do Deck e quebrou o launcher
    do DMC3 — este script ainda rodava pytest sem isolamento (corrigido 28/11/2026);
 4. troca a pasta INTEIRA (a antiga vira ~/deck-commander.anterior; /voltar desfaz). Antes era cópia por cima, que
    deixava arquivo removido no lugar (ex.: dc/emulators.py ao lado do pacote dc/emulators/);
 5. `python3 -m dc.atualizar depois`: refaz launcher, serviços, emuladores.json e plugin do Decky na pasta nova;
 6. reinicia bot e energia e roda a revisão ao vivo.
"""
import os
import shlex
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CHAVE = str(Path.home() / ".ssh" / "deck_commander_ed25519")

# Roda NO DECK. Variáveis: VERSAO, COM_JOGO.
REMOTO = r"""
set -u
NOVA=/tmp/dc-new
rm -rf "$NOVA" && mkdir "$NOVA" && tar -x -C "$NOVA" || { echo "FALHA: pacote"; exit 1; }
cd "$NOVA"
if [ "$COM_JOGO" != 1 ] && PYTHONDONTWRITEBYTECODE=1 python3 -c 'import sys; from dc import ops; sys.exit(0 if ops.game_running() else 1)'; then
  echo "FALHA: há jogo aberto — não interrompo partida (feche o jogo ou use --com-jogo-aberto)"; exit 1
fi
PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY' || { echo "FALHA: testes isolados no Deck"; exit 1; }
import sys
from pathlib import Path
from dc import test_runner
r = test_runner.run(Path("."), Path.home() / ".local/share/deck-commander/venv/bin/python")
linhas = (r.stdout or "").strip().splitlines() or (r.stderr or "").strip().splitlines() or ["executor sem resultado"]
print("testes isolados no Deck:", linhas[-1])
sys.exit(r.returncode)
PY
rm -rf "$HOME/deck-commander.anterior"
mv "$HOME/deck-commander" "$HOME/deck-commander.anterior" || { echo "FALHA: guardar versão anterior"; exit 1; }
if ! cp -a "$NOVA" "$HOME/deck-commander"; then
  rm -rf "$HOME/deck-commander"; mv "$HOME/deck-commander.anterior" "$HOME/deck-commander"
  echo "FALHA: cópia (versão anterior restaurada)"; exit 1
fi
echo "$VERSAO" > "$HOME/deck-commander/VERSAO.txt"
chmod +x "$HOME"/deck-commander/*.sh
cd "$HOME/deck-commander" && python3 -m dc.atualizar depois || echo "AVISO: pós-instalação reclamou (veja acima)"
systemctl --user restart deck-commander-bot deck-commander-power
rm -rf "$NOVA"
echo IMPLANTADO
"""


def sh(cmd, **kw):
    return subprocess.run(cmd, cwd=RAIZ, text=True, capture_output=True, **kw)


def parar(msg):
    print("NÃO implantei:", msg)
    sys.exit(1)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    com_jogo = "--com-jogo-aberto" in sys.argv
    alvo = args[0] if args else None
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
    commit = sh(["git", "log", "-1", "--format=%h %cd", "--date=format:%d/%m %H:%M"]).stdout.strip()
    versao = commit or "desconhecida"  # guardada no Deck: /voltar e o atualizador usam
    ssh = ["ssh", "-i", CHAVE, "-o", "BatchMode=yes", alvo]
    if os.environ.get("DC_SSH_CONFIG"):  # ex.: a VM de teste (D:/vm-steamos), em outra porta
        ssh[1:1] = ["-F", os.environ["DC_SSH_CONFIG"]]
    remoto = f"VERSAO={shlex.quote(versao)} COM_JOGO={1 if com_jogo else 0} bash -c {shlex.quote(REMOTO)}"
    pacote = subprocess.run(["git", "archive", "--format=tar", "HEAD"], cwd=RAIZ, capture_output=True).stdout
    p = subprocess.run(ssh + [remoto], input=pacote, capture_output=True, timeout=3600)
    saida = p.stdout.decode("utf-8", "replace") + p.stderr.decode("utf-8", "replace")
    print(saida.strip())
    if "IMPLANTADO" not in saida:
        parar("um passo falhou no Deck (acima); o Deck continua com a versão anterior")
    # revisão AO VIVO (pedido do usuário 11/11/2026): confere no aparelho cada coisa que já funcionou.
    rv = subprocess.run(ssh + ["cd ~/deck-commander && XDG_RUNTIME_DIR=/run/user/$(id -u) timeout 600 python3 -m dc.revisao_viva"],
                        capture_output=True, timeout=700)
    print(rv.stdout.decode("utf-8", "replace").strip())
    if rv.returncode != 0:
        print("ATENÇÃO: a revisão ao vivo achou FALHA (acima). Corrigir antes de dizer que está pronto.")


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    main()
