#!/bin/bash
# Teste de "usuário novo" (revisão de lançamento 11/11/2026): instala o Deck Commander numa pasta pessoal VAZIA e
# isolada e aperta todos os botões do painel e todos os comandos do bot, como alguém fazendo tudo pela 1ª vez.
# Nada do Deck de verdade é tocado: systemctl/flatpak/steam são falsos (só anotam o que seria feito) e não há
# downloads grandes. Uso (no Deck):  bash tools/usuario_novo.sh /caminho/do/codigo.tar
set -uo pipefail
TAR="$1"
RAIZ=/tmp/dc-usuario-novo
rm -rf "$RAIZ"; mkdir -p "$RAIZ/home/deck-commander" "$RAIZ/falsos"
tar -xf "$TAR" -C "$RAIZ/home/deck-commander"
for f in systemctl flatpak steam steamos-session-select gamescopectl qbittorrent-nox; do
  printf '#!/bin/bash\necho "$(basename "$0") $*" >> %s/chamadas.log\nexit 0\n' "$RAIZ" > "$RAIZ/falsos/$f"
  chmod +x "$RAIZ/falsos/$f"
done
export HOME="$RAIZ/home" PATH="$RAIZ/falsos:$PATH" XDG_CONFIG_HOME="$RAIZ/home/.config" \
       XDG_DATA_HOME="$RAIZ/home/.local/share" XDG_STATE_HOME="$RAIZ/home/.local/state" PYTHONPATH="$RAIZ/home/deck-commander"
cd "$HOME/deck-commander"
echo "=== instalação (--all --no-downloads)"
./setup-deck.sh --all --no-downloads > "$RAIZ/setup.log" 2>&1; echo "código de saída: $?"
grep -i -E "falh|erro|error|traceback|PENDENTE" "$RAIZ/setup.log" | head -20
echo "=== painel: todas as ações com o mínimo (sem nada configurado)"
python3 - <<'EOF'
import json, subprocess, sys
from dc import painel
lentas = {"pc_acordar", "pc_tv", "musica_conectar", "transferir_enviar", "trazer_enviar", "familia_puxar"}
for nome in sorted(painel.ACOES):
    if nome in lentas:
        continue
    r = subprocess.run([sys.executable, "-m", "dc.painel", nome], input="{}", capture_output=True, text=True, timeout=60)
    linha = next((l for l in reversed(r.stdout.splitlines()) if l.startswith("{")), "")
    try:
        d = json.loads(linha)
    except ValueError:
        print(f"QUEBROU  {nome}: sem resposta JSON (código {r.returncode}) {r.stderr.strip()[-200:]}")
        continue
    if not d.get("ok") and "Traceback" in (d.get("erro") or "") or "Exception" in (d.get("erro") or ""):
        print(f"QUEBROU  {nome}: {d.get('erro','')[:200]}")
    elif not d.get("ok"):
        print(f"recusou  {nome}: {str(d.get('erro'))[:120]}")
EOF
echo "=== bot: todos os comandos da ajuda (usuário pareado)"
python3 - <<'EOF'
import re, traceback
from dc import bot as B
from dc.paths import get_paths
p = get_paths(); p.ensure()
b = B.Bot(p, "123:fake")
b.cfg = {"allowed": [1]}
b.save_cfg = lambda: None
b.send = lambda *a, **k: None
b.call = lambda *a, **k: {}
cmds = sorted(set(re.findall(r"(/[a-z_]+)", B.HELP)))
for c in cmds:
    if c in ("/sync", "/update", "/reboot", "/desligar", "/sos"):
        continue
    try:
        r = b.handle(1, 1, c)
    except SystemExit:
        r = "(saiu)"
    except Exception as e:
        print(f"QUEBROU  {c}: {type(e).__name__}: {e}"[:220])
        continue
EOF
echo "=== chamadas que seriam feitas no sistema"
sort "$RAIZ/chamadas.log" 2>/dev/null | cut -c1-120 | uniq -c | sort -rn | head -15

echo "=== fuzz (entradas maliciosas)"
python3 tools/usuario_novo_fuzz.py
