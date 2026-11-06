#!/bin/bash
# Desliga um módulo preservando dados. --purge (só M4) apaga o histórico do bot.
set -euo pipefail
cd "$(dirname "$0")"
[ $# -ge 1 ] || { echo "uso: $0 M4 [--purge]"; exit 2; }
PURGE=False; [ "${2:-}" = "--purge" ] && PURGE=True
exec /usr/bin/python3 -c "
from dc.paths import get_paths; from dc import setup
for l in setup.uninstall_module(get_paths(), '$1', purge=$PURGE): print(l)
"
