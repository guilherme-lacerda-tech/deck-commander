#!/bin/bash
# Gera o instalador de arquivo único: o cabeçalho + o projeto (tar.gz em base64) no fim.
#   bash tools/instalador/gerar.sh [saída]     (padrão: ~/Desktop/Instalar-Deck-Commander.sh)
#
# O pacote é EXATAMENTE o commit atual do Git (git archive): nada de arquivos soltos da pasta de trabalho, tokens,
# bancos ou ~/.config. Leva VERSAO.txt com o commit — é por ele que a atualização automática (dc/atualizar.py)
# sabe qual versão está instalada. Recusa gerar com mudanças não commitadas (o instalador seria diferente do GitHub).
set -euo pipefail
AQUI="$(cd "$(dirname "$0")" && pwd)"
RAIZ="$(cd "$AQUI/../.." && pwd)"
SAIDA="${1:-$HOME/Desktop/Instalar-Deck-Commander.sh}"
VERSAO="$(cat "$RAIZ/VERSION")"

if [ -n "$(git -C "$RAIZ" status --porcelain -- dc decky-plugin tools setup-deck.sh install.sh modules config 2>/dev/null)" ]; then
  echo "Há mudanças não commitadas no projeto: faça o commit antes de gerar o instalador." >&2
  exit 1
fi
COMMIT="$(git -C "$RAIZ" rev-parse --short=7 HEAD)"

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
git -C "$RAIZ" archive --format=tar --prefix=deck-commander/ HEAD > "$TMP/pacote.tar"
mkdir -p "$TMP/deck-commander"
echo "$COMMIT $(date '+%d/%m %H:%M')" > "$TMP/deck-commander/VERSAO.txt"
tar -C "$TMP" -rf "$TMP/pacote.tar" deck-commander/VERSAO.txt
gzip -9 "$TMP/pacote.tar"

sed "s/__VERSAO__/$VERSAO ($COMMIT)/" "$AQUI/cabecalho.sh" > "$TMP/saida.sh"
base64 -w 76 "$TMP/pacote.tar.gz" >> "$TMP/saida.sh"
mkdir -p "$(dirname "$SAIDA")"
mv "$TMP/saida.sh" "$SAIDA"
chmod +x "$SAIDA"
echo "Gerado: $SAIDA ($(du -h "$SAIDA" | cut -f1), versão $VERSAO, commit $COMMIT)"
