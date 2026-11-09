#!/bin/bash
# Roda o teste de /traduzir em série (um jogo por vez), como serviço próprio do systemd, para não depender
# da sessão SSH. Uso: tools/testar_traducoes.sh "firered version (english" hercules ...
# Entra na pasta a cada jogo (por caminho absoluto): uma atualização do Deck Commander no meio troca a pasta.
REPO="${DC_REPO:-$HOME/deck-commander}"
for jogo in "$@"; do
    echo "===== $jogo"
    cd "$REPO" && python3 "$REPO/tools/traduzir_todos.py" "$jogo"
done
