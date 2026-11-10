#!/bin/bash
# Deck Commander — instalação em 1 comando no Steam Deck (modo Desktop → Konsole):
#
#   curl -fsSL https://raw.githubusercontent.com/SEU-USUARIO/deck-commander/main/install.sh | bash
#
# Baixa (ou atualiza) o projeto em ~/deck-commander, instala tudo no $HOME (sem senha de administrador)
# e abre o assistente do Telegram (QR code → @BotFather → cola o token → QR do seu bot → pronto).
# Pode rodar de novo quando quiser: atualiza sem apagar nada.
set -euo pipefail
REPO="${DC_REPO:-https://github.com/SEU-USUARIO/deck-commander.git}"
BRANCH="${DC_BRANCH:-main}"
DEST="${DC_DEST:-$HOME/deck-commander}"

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
command -v git >/dev/null || { echo "git não encontrado (o SteamOS já traz; atualize o sistema)"; exit 1; }
command -v python3 >/dev/null || { echo "python3 não encontrado (o SteamOS já traz; atualize o sistema)"; exit 1; }

if [ -d "$DEST/.git" ]; then
  say "Atualizando $DEST"
  git -C "$DEST" pull --ff-only
else
  say "Baixando o Deck Commander para $DEST"
  git clone --depth 1 --branch "$BRANCH" "$REPO" "$DEST"
fi
cd "$DEST"

say "Instalando (emuladores, serviços, plugin) — pode levar alguns minutos"
./setup-deck.sh --all

if [ ! -d "$HOME/homebrew/plugins" ]; then
  say "Falta o Decky Loader (loja de plugins do Gaming Mode)"
  echo "Instale em https://decky.xyz (botão Download → abrir o arquivo) e rode este comando de novo."
fi

if [ -r /dev/tty ] && [ "${DC_SEM_TELEGRAM:-0}" != "1" ]; then
  say "Bot do Telegram (pode pular com Ctrl+C e fazer depois: python3 -m dc x telegram-setup)"
  python3 -m dc x telegram-setup < /dev/tty || true
fi

say "Pronto! Volte ao Gaming Mode. Ajuda: $DEST/README.md"
