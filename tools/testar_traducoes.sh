#!/bin/bash
# Roda o teste de /traduzir em série (um jogo por vez), como serviço próprio do systemd, para não depender
# da sessão SSH. Uso: tools/testar_traducoes.sh "firered version (english" hercules ...
cd "$(dirname "$0")/.." || exit 1
for jogo in "$@"; do
    echo "===== $jogo"
    python3 tools/traduzir_todos.py "$jogo"
done
