#!/bin/bash
# ════════════════════════════════════════════════════════════════════════════════════════════
#  Deck Commander — instalador completo (um arquivo só, funciona sem GitHub)
#
#  Como usar no Steam Deck (modo Desktop):
#    dois cliques neste arquivo → "Executar" (ou: botão direito → Executar no Konsole)
#  Ou no Konsole:  bash Instalar-Deck-Commander.sh
#
#  O que ele faz (tudo dentro da pasta pessoal; o SteamOS não é alterado):
#    1. confere o aparelho (SteamOS, Python, internet, espaço livre)
#    2. instala o Decky Loader se faltar (pede para criar a senha do Deck, se não houver)
#    3. copia o Deck Commander para ~/deck-commander (a versão antiga fica em ~/deck-commander.anterior)
#    4. instala emuladores e serviços
#    5. instala os plugins do Decky: Deck Commander e TabMaster (abas por console)
#    6. procura jogos soltos (Downloads, cartão SD, pendrive…) e põe cada um na pasta do console
#    7. assistente do Telegram (QR code) e chave das capas — ambos opcionais
#  Pode rodar de novo quando quiser: atualiza sem apagar configurações, jogos ou saves.
# ════════════════════════════════════════════════════════════════════════════════════════════
set -uo pipefail

VERSAO_PACOTE="__VERSAO__"
DEST="$HOME/deck-commander"
LOG="$HOME/deck-commander-instalacao.log"
EU="$(readlink -f "$0")"

# ── 0. Dois cliques abrem sem terminal: reabre dentro do Konsole para dar para ver e responder ──
if [ ! -t 0 ] || [ ! -t 1 ]; then
  if [ -z "${DC_JA_NO_TERMINAL:-}" ]; then
    export DC_JA_NO_TERMINAL=1
    for t in konsole xterm; do
      if command -v "$t" >/dev/null 2>&1; then
        exec "$t" -e bash "$EU" "$@"
      fi
    done
    command -v zenity >/dev/null && zenity --error --text="Não achei o Konsole. Abra o Konsole e rode:\nbash \"$EU\""
    exit 1
  fi
fi

exec > >(tee -a "$LOG") 2>&1
echo "──── $(date '+%d/%m/%Y %H:%M') — instalador Deck Commander $VERSAO_PACOTE ────" >> "$LOG"

AZ=$'\033[1;36m'; VD=$'\033[1;32m'; AM=$'\033[1;33m'; VM=$'\033[1;31m'; NG=$'\033[1m'; NC=$'\033[0m'
passo() { printf '\n%s━━ %s ━━%s\n' "$AZ" "$*" "$NC"; }
ok()    { printf '%s  ✔ %s%s\n' "$VD" "$*" "$NC"; }
aviso() { printf '%s  ! %s%s\n' "$AM" "$*" "$NC"; }
erro()  { printf '%s  ✘ %s%s\n' "$VM" "$*" "$NC"; }
pergunta_sn() {  # pergunta_sn "texto" [padrão s|n]
  local r padrao="${2:-s}" dica="[S/n]"; [ "$padrao" = n ] && dica="[s/N]"
  read -r -p "  $1 $dica " r </dev/tty || r=""
  r="${r:-$padrao}"; [[ "$r" =~ ^[sSyY] ]]
}
fim() {
  echo
  echo "  Registro completo da instalação: $LOG"
  read -r -p "  Aperte Enter para fechar esta janela… " _ </dev/tty || true
  exit "${1:-0}"
}
trap 'erro "Algo deu errado (linha $LINENO). Nada foi apagado."; fim 1' ERR

clear 2>/dev/null || true
cat <<EOF
${AZ}
   ╔══════════════════════════════════════════════╗
   ║          DECK COMMANDER — INSTALADOR         ║
   ║                  versão $(printf '%-21s' "$VERSAO_PACOTE")║
   ╚══════════════════════════════════════════════╝${NC}

  Vai instalar: emuladores que faltarem, o plugin do Decky, os serviços do Deck
  Commander e (se você quiser) o bot do Telegram. Leva de 5 a 20 minutos,
  dependendo da internet. Deixe o Deck na tomada.

EOF
pergunta_sn "Começar?" s || fim 0

# ── 1. Conferências ──────────────────────────────────────────────────────────────────────────
passo "1/8  Conferindo o aparelho"
if grep -qi steamos /etc/os-release 2>/dev/null; then ok "SteamOS"; else aviso "Isto não parece um SteamOS — seguindo mesmo assim"; fi
[ "$(id -u)" -ne 0 ] || { erro "Não rode como administrador (sudo). Dê dois cliques normalmente."; fim 1; }
if ! /usr/bin/python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
  erro "Precisa do Python 3.11 ou mais novo (atualize o SteamOS: Configurações → Sistema → Atualizar)"; fim 1
fi
ok "Python $(/usr/bin/python3 -c 'import platform; print(platform.python_version())')"
if curl -fsS --max-time 10 -o /dev/null https://dl.flathub.org 2>/dev/null; then ok "Internet"
else erro "Sem internet. Conecte no Wi-Fi e rode de novo."; fim 1; fi
livre_gb=$(( $(df --output=avail -k "$HOME" | tail -1) / 1024 / 1024 ))
if [ "$livre_gb" -lt 5 ]; then erro "Só ${livre_gb} GB livres; precisa de pelo menos 5 GB."; fim 1; fi
ok "${livre_gb} GB livres"

# ── 2. Senha + Decky Loader ──────────────────────────────────────────────────────────────────
passo "2/8  Decky Loader (loja de plugins do modo de jogo)"
TEM_SUDO=0
garantir_senha() {
  [ "$TEM_SUDO" = 1 ] && return 0
  if [ "$(passwd -S "$USER" 2>/dev/null | awk '{print $2}')" != "P" ]; then
    echo
    echo "  O Deck ainda não tem senha. Ela é necessária para instalar o Decky e o plugin."
    echo "  ${NG}Crie uma agora e ANOTE${NC} (ela não aparece enquanto você digita)."
    passwd || { erro "A senha não foi criada"; return 1; }
  fi
  echo "  Digite a senha do Deck (não aparece na tela):"
  if sudo -v; then
    TEM_SUDO=1
    ( while sleep 50; do sudo -n true 2>/dev/null || exit; kill -0 $$ 2>/dev/null || exit; done ) &
    return 0
  fi
  erro "Senha não aceita"; return 1
}
decky_instalado() { [ -d "$HOME/homebrew/services" ] && [ -d "$HOME/homebrew/plugins" ]; }

if decky_instalado; then
  ok "Decky Loader já instalado"
else
  aviso "O Decky Loader não está instalado (sem ele os jogos só aparecem depois de reiniciar o Steam)."
  if pergunta_sn "Instalar o Decky Loader agora?" s && garantir_senha; then
    tmp_decky="$(mktemp -d)"
    curl -fsSL -o "$tmp_decky/install_release.sh" \
      https://github.com/SteamDeckHomebrew/decky-installer/releases/latest/download/install_release.sh
    # o script do Decky se reabre com 'sudo "$0"' quando não é root: sem o bit de execução dava
    # "command not found" (falha real na simulação EmuDeck, 16/11/2026). Já roda como root.
    chmod +x "$tmp_decky/install_release.sh"
    sudo bash "$tmp_decky/install_release.sh" || aviso "O instalador do Decky reclamou de algo (veja acima)"
    rm -rf "$tmp_decky"
    if decky_instalado; then ok "Decky Loader instalado"; else aviso "Decky não ficou instalado — dá para fazer depois em https://decky.xyz"; fi
  else
    aviso "Pulando o Decky. Instale depois em https://decky.xyz e rode este instalador de novo."
  fi
fi

# ── 3. Copiar o Deck Commander ───────────────────────────────────────────────────────────────
passo "3/8  Copiando o Deck Commander para $DEST"
TMPX="$(mktemp -d)"
linha=$(awk '/^__PACOTE_ABAIXO__$/ {print NR + 1; exit 0}' "$EU")
tail -n +"$linha" "$EU" | base64 -d | tar -xz -C "$TMPX"
[ -f "$TMPX/deck-commander/setup-deck.sh" ] || { erro "Pacote corrompido (baixe o instalador de novo)"; fim 1; }
if [ -d "$DEST" ]; then
  systemctl --user stop deck-commander-bot deck-commander-power 2>/dev/null || true
  rm -rf "$DEST.anterior"
  mv "$DEST" "$DEST.anterior"
  ok "Versão que estava aqui guardada em $DEST.anterior (/voltar no bot desfaz)"
fi
mv "$TMPX/deck-commander" "$DEST"
rm -rf "$TMPX"
chmod +x "$DEST"/*.sh
ok "Código copiado (versão $(cat "$DEST/VERSION"))"

# ── 4. Instalação principal ──────────────────────────────────────────────────────────────────
passo "4/8  Instalando emuladores e serviços (a parte demorada)"
cd "$DEST"
EXTRA=(); [ "${DC_SEM_DOWNLOADS:-0}" = 1 ] && EXTRA=(--no-downloads)   # só para testes
if ./setup-deck.sh --all "${EXTRA[@]}"; then ok "Instalação principal concluída"
else erro "A instalação principal falhou (veja as mensagens acima)"; fim 1; fi

# ── 5. Plugins do Decky ──────────────────────────────────────────────────────────────────────
passo "5/8  Plugins do Decky (Deck Commander + TabMaster)"
# Com a senha, instala direto (sem precisar do Modo Desenvolvedor + ZIP)
PLUGIN_OK=0; TABMASTER=0; REINICIAR_DECKY=0
if ! decky_instalado; then
  aviso "Sem Decky Loader: plugins ficam para depois"
else
  # compara a pasta inteira (antes era só o main.py: uma tela nova do painel nunca era instalada)
  if [ -f "$HOME/homebrew/plugins/deck-commander/plugin.json" ] && \
     diff -rq --exclude=__pycache__ "$DEST/decky-plugin" "$HOME/homebrew/plugins/deck-commander" >/dev/null 2>&1; then
    ok "Plugin do Deck Commander já instalado e em dia"; PLUGIN_OK=1
    if [ ! -w "$HOME/homebrew/plugins/deck-commander/dist/index.js" ] && garantir_senha; then
      sudo chown -R "$(id -u):$(id -g)" "$HOME/homebrew/plugins/deck-commander"
      ok "Plugin liberado para a atualização automática"
    fi
  elif garantir_senha; then
    sudo rm -rf "$HOME/homebrew/plugins/deck-commander"
    sudo mkdir -p "$HOME/homebrew/plugins/deck-commander"
    sudo cp -r "$DEST/decky-plugin/." "$HOME/homebrew/plugins/deck-commander/"
    sudo rm -rf "$HOME/homebrew/plugins/deck-commander/__pycache__"
    # a pasta fica no nome do usuário: a atualização automática do Deck Commander troca o plugin sem pedir senha
    sudo chown -R "$(id -u):$(id -g)" "$HOME/homebrew/plugins/deck-commander"
    ok "Plugin do Deck Commander instalado no Decky"; PLUGIN_OK=1; REINICIAR_DECKY=1
  fi
  # TabMaster: baixado da loja oficial do Decky, conferindo o hash publicado pela própria loja
  if [ -f "$HOME/homebrew/plugins/TabMaster/plugin.json" ]; then
    ok "TabMaster já instalado"; TABMASTER=1
  elif garantir_senha; then
    tmp_tm="$(mktemp -d)"
    tm_hash=$(curl -fsS --max-time 30 https://plugins.deckbrew.xyz/plugins | /usr/bin/python3 -c '
import json, sys
for p in json.load(sys.stdin):
    if p["name"] == "TabMaster" and p.get("versions"):
        print(p["versions"][0]["hash"]); break' 2>/dev/null || true)
    if [ -n "$tm_hash" ] && curl -fsSL --max-time 120 -o "$tmp_tm/tm.zip" \
         "https://cdn.tzatzikiweeb.moe/file/steam-deck-homebrew/versions/$tm_hash.zip" && \
       [ "$(sha256sum "$tmp_tm/tm.zip" | cut -d' ' -f1)" = "$tm_hash" ] && \
       /usr/bin/python3 -c 'import sys, zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])' "$tmp_tm/tm.zip" "$tmp_tm/x" && \
       [ -f "$tmp_tm/x/TabMaster/plugin.json" ]; then
      sudo cp -r "$tmp_tm/x/TabMaster" "$HOME/homebrew/plugins/TabMaster"
      ok "TabMaster instalado (loja do Decky, arquivo conferido)"; TABMASTER=1; REINICIAR_DECKY=1
    else
      aviso "Não consegui baixar o TabMaster agora — instale pela loja do Decky depois"
    fi
    rm -rf "$tmp_tm"
  fi
  if [ "$REINICIAR_DECKY" = 1 ]; then
    sudo systemctl restart plugin_loader 2>/dev/null || true
    ok "Decky reiniciado para carregar os plugins"
  fi
fi

# ── 6. Jogos soltos ──────────────────────────────────────────────────────────────────────────
passo "6/8  Procurando jogos (Downloads, Área de Trabalho, cartão SD, pendrive…)"
echo "  Procurando… (pode levar um minuto)"
varr="$(python3 -m dc.varredura 2>&1 || true)"
echo "$varr"
if grep -q "jogo(s)" <<<"$varr"; then
  echo
  echo "  No mesmo disco o arquivo é MOVIDO (não ocupa espaço a mais); do pendrive é COPIADO."
  echo "  Jogos do cartão SD continuam no cartão. Nada é apagado e dá para desfazer."
  if pergunta_sn "Colocar esses jogos nas pastas certas?" s; then
    python3 -m dc.varredura --aplicar | grep -E "✔|✘|!|=|organizados" || true
  else
    aviso "Pulado. Para fazer depois: cd ~/deck-commander && python3 -m dc.varredura --aplicar"
  fi
fi
echo "  Colocando os jogos na biblioteca do Steam…"; mkdir -p "$HOME/.cache"
mkdir -p "$HOME/.cache"
if python3 -m dc library --apply > "$HOME/.cache/dc-instalador-biblioteca.log" 2>&1; then
  ok "$(grep -m1 'jogos encontrados' "$HOME/.cache/dc-instalador-biblioteca.log" || echo 'Biblioteca atualizada')"
else
  aviso "Não deu para atualizar a biblioteca agora (mande /sync no Telegram depois do reinício)"
fi

# ── 5. Telegram e capas (opcionais) ──────────────────────────────────────────────────────────
passo "7/8  Bot do Telegram (opcional, mas é o jeito mais fácil de usar)"
if [ -f "$HOME/.config/deck-commander/secrets/telegram" ]; then
  ok "Bot do Telegram já configurado"
elif pergunta_sn "Configurar o bot do Telegram agora? (precisa do celular com Telegram)" s; then
  echo "  Vai aparecer um QR code: aponte o celular, mande /newbot para o @BotFather,"
  echo "  copie o token e cole aqui (Ctrl+Shift+V no Konsole). Ele não aparece na tela."
  python3 -m dc x telegram-setup </dev/tty || aviso "Telegram não terminou — faça depois (veja o final)"
else
  aviso "Pulado. Para fazer depois: cd ~/deck-commander && python3 -m dc x telegram-setup"
fi

if [ ! -f "$HOME/.config/deck-commander/secrets/steamgriddb" ]; then
  echo
  echo "  Capas dos jogos: precisa de uma chave grátis em"
  echo "  https://www.steamgriddb.com/profile/preferences/api (entrar com a conta Steam → Generate API Key)"
  if pergunta_sn "Já tem a chave e quer colar agora?" n; then
    python3 -m dc secret steamgriddb </dev/tty || aviso "Chave não salva — faça depois"
  fi
fi

# ── 6. Resumo ────────────────────────────────────────────────────────────────────────────────
passo "8/8  Conferência final"
for s in deck-commander-power deck-commander-bot deck-commander-qbittorrent; do
  if systemctl --user is-active --quiet "$s"; then ok "$s rodando"
  elif [ "$s" = deck-commander-bot ] && [ ! -f "$HOME/.config/deck-commander/secrets/telegram" ]; then
    aviso "$s parado (liga sozinho quando o Telegram for configurado)"
  else aviso "$s não está rodando (veja: systemctl --user status $s)"; fi
done

cat <<EOF

${VD}══════════════════════════════════════════════════════════
   Deck Commander instalado!
══════════════════════════════════════════════════════════${NC}
  O que falta (no modo de jogo):
EOF
n=1
if ! decky_instalado; then
  echo "   $n. Instale o Decky Loader (https://decky.xyz) e rode este instalador de novo."; n=$((n+1))
fi
if [ "$TABMASTER" = 0 ]; then
  echo "   $n. Botão … → Decky (tomada) → loja (sacola) → instale o ${NG}TabMaster${NC} (abas por console)."; n=$((n+1))
fi
if decky_instalado && [ "$PLUGIN_OK" = 0 ]; then
  echo "   $n. Decky → ⚙️ → ligue Modo Desenvolvedor → Desenvolvedor → Instalar plugin de ZIP →"
  echo "      Downloads/deck-commander-plugin.zip"; n=$((n+1))
fi
echo "   $n. Reinicie o Deck uma vez."; n=$((n+1))
echo "   $n. Jogos novos: mande pelo Telegram, ou jogue em Downloads e rode de novo este instalador"
echo "      (ele acha e organiza). BIOS vão em ~/Emulation/bios/ (o /diagnostico do bot avisa se faltar)."
echo
echo "  Manual: ~/deck-commander/docs/MANUAL.md   ·   Problemas: ~/deck-commander/TROUBLESHOOTING.md"
trap - ERR
fim 0
exit 0
__PACOTE_ABAIXO__
