#!/bin/bash
# Checkpoint ANTES de mexer no Deck físico (política de 28/11/2026): guarda o que a implantação pode tocar e tira
# hash dos saves/atalhos (que ela NÃO deve tocar) para conferir depois.
#   bash checkpoint_deck.sh antes <nome>     -> cria ~/.local/state/deck-commander/code-checkpoints/<nome>/
#   bash checkpoint_deck.sh depois <nome>    -> compara saves/atalhos com o "antes" (sai 1 se algo mudou)
set -u
modo=$1; nome=$2
D="$HOME/.local/state/deck-commander/code-checkpoints/$nome"
hashes() {
  {
    find "$HOME/.config/PCSX2/sstates" "$HOME/.config/PCSX2/memcards" \
         "$HOME/.var/app/net.pcsx2.PCSX2/config/PCSX2/sstates" "$HOME/.var/app/net.pcsx2.PCSX2/config/PCSX2/memcards" \
         "$HOME/.local/share/eden/nand/user/save" "$HOME/.local/share/Ryujinx/bis/user/save" \
         "$HOME/.local/share/duckstation/savestates" "$HOME/.local/share/duckstation/memcards" \
         "$HOME/Emulation/saves" "$HOME/.var/app/org.ppsspp.PPSSPP/config/ppsspp/PSP/SAVEDATA" \
         "$HOME/.var/app/org.DolphinEmu.dolphin-emu/data/dolphin-emu/GC" \
         -type f 2>/dev/null | sort | xargs -r -d '\n' sha256sum
    for f in "$HOME"/.local/share/Steam/userdata/*/config/shortcuts.vdf; do [ -f "$f" ] && sha256sum "$f"; done
  } 2>/dev/null
}
if [ "$modo" = antes ]; then
  mkdir -p "$D"
  tar -czf "$D/codigo-e-config.tgz" -C "$HOME" deck-commander .config/deck-commander \
      .local/share/deck-commander/bin .local/share/deck-commander/data \
      $(cd "$HOME" && ls -d .config/systemd/user/deck-commander-* 2>/dev/null) \
      homebrew/plugins/deck-commander 2>/dev/null
  hashes > "$D/saves-e-atalhos.sha256"
  pgrep -af "pcsx2|duckstation|retroarch|dolphin|ppsspp|ryujinx|eden|cemu|rpcs3" | grep -v pgrep > "$D/processos.txt"
  cat "$HOME/deck-commander/VERSAO.txt" > "$D/versao.txt" 2>/dev/null
  echo "checkpoint $D: $(wc -l < "$D/saves-e-atalhos.sha256") arquivos de save/atalho; $(du -h "$D/codigo-e-config.tgz" | cut -f1) de código/config"
else
  hashes > "$D/depois.sha256"
  # shortcuts.vdf pode mudar só pelo horário da última execução gravado pelo Steam: mostrado à parte
  if diff <(grep -v shortcuts.vdf "$D/saves-e-atalhos.sha256") <(grep -v shortcuts.vdf "$D/depois.sha256") >/dev/null; then
    echo "saves: $(grep -vc shortcuts.vdf "$D/depois.sha256") arquivos, todos idênticos"
  else
    echo "SAVES MUDARAM:"; diff <(grep -v shortcuts.vdf "$D/saves-e-atalhos.sha256") <(grep -v shortcuts.vdf "$D/depois.sha256"); exit 1
  fi
  diff <(grep shortcuts.vdf "$D/saves-e-atalhos.sha256") <(grep shortcuts.vdf "$D/depois.sha256") >/dev/null \
    && echo "atalhos do Steam: idênticos" || echo "atalhos do Steam: mudaram (conferir)"
fi
