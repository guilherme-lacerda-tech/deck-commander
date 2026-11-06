#!/bin/bash
# Remove o Deck Commander. Sem flags: só serviços e código.
#   --purge --confirm APAGAR                     apaga também configs/banco/logs
#   --purge --purge-backups --confirm APAGAR     apaga também ~/Backups/DeckCommander
cd "$(dirname "$0")" && exec /usr/bin/python3 -m dc x uninstall "$@"
