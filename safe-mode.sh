#!/bin/bash
# Desativa as automações do Deck Commander (não apaga nada). "./safe-mode.sh off" religa.
cd "$(dirname "$0")" && exec /usr/bin/python3 -m dc x safe-mode "$@"
