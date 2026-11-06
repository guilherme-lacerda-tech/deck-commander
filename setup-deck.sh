#!/bin/bash
# Deck Commander — instalação/atualização idempotente. Tudo no $HOME.
#   ./setup-deck.sh --all            instala o projeto inteiro (produção)
#   ./setup-deck.sh --modules M0,M4  só esses módulos (+ dependências)
#   ./setup-deck.sh --all --dev      inclui ferramentas de desenvolvimento (pytest)
set -euo pipefail
cd "$(dirname "$0")"
MODS="" ; DEV=0
while [ $# -gt 0 ]; do
  case "$1" in
    --all) MODS="ALL";; --modules) MODS="$2"; shift;; --dev) DEV=1;; --production) DEV=0;;
    *) echo "opção desconhecida: $1"; exit 2;;
  esac; shift
done
[ -z "$MODS" ] && { echo "use --all ou --modules M0,M4"; exit 2; }
exec /usr/bin/python3 -c "
import sys; from dc.paths import get_paths; from dc import setup
mods = setup.ALL_MODULES if '$MODS' == 'ALL' else '$MODS'.split(',')
for l in setup.setup(get_paths(), mods, dev=$DEV == 1): print(l)
"
