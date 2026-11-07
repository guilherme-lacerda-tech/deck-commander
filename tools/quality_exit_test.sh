#!/bin/bash
# Diagnóstico no Deck: qualidade por jogo + "Sair do jogo" do Steam (SIGTERM no dc-launch).
# Usa uma raiz isolada (DC_ROOT) e um emulador falso; mexe só no valor de resolução do PPSSPP e devolve.
set -u
R=/tmp/dcq
INI=~/.var/app/org.ppsspp.PPSSPP/config/ppsspp/PSP/SYSTEM/ppsspp.ini
if pgrep -x PPSSPPSDL >/dev/null || pgrep -x PPSSPPQt >/dev/null; then echo "PPSSPP aberto: abortado"; exit 1; fi
rm -rf "$R"; C=$R/.config/deck-commander; D=$R/.local/share/deck-commander; S=$R/.local/state/deck-commander
mkdir -p "$C" "$D"
cat > "$R/fake-emu.sh" <<EOF
#!/bin/bash
trap 'echo recebeu-TERM >> $R/emu.log; exit 0' TERM
echo iniciou >> $R/emu.log
while true; do sleep 1; done
EOF
chmod +x "$R/fake-emu.sh"; touch "$R/jogo.iso"
echo "{\"psp\": [\"$R/fake-emu.sh\", \"{rom}\"]}" > "$C/emulators.json"
echo "{\"psp-teste\": {\"title\": \"Teste\", \"console\": \"psp\", \"rom\": \"$R/jogo.iso\"}}" > "$D/launch-map.json"
echo '{"psp-teste": {"res": 1}}' > "$C/per-game.json"
before=$(sha256sum "$INI" | cut -c1-16); echo "antes:   $(grep '^InternalResolution' "$INI")"
DC_ROOT=$R ~/.local/share/deck-commander/bin/dc-launch psp-teste & PID=$!
sleep 3; echo "durante: $(grep '^InternalResolution' "$INI")"
kill -TERM $PID; wait $PID; echo "dc-launch saiu com $?"; sleep 1
after=$(sha256sum "$INI" | cut -c1-16); echo "depois:  $(grep '^InternalResolution' "$INI")"
echo "emulador: $(tr '\n' ' ' < "$R/emu.log")"
pgrep -f "$R/fake-emu.sh" >/dev/null && echo "FALHA: emulador continua aberto" || echo "emulador fechado"
[ -e "$S/quality-restore.json" ] && echo "FALHA: devolução pendente" || echo "nada pendente"
[ "$before" = "$after" ] && echo "RESULTADO: TUDO OK (arquivo idêntico)" || echo "RESULTADO: FALHOU (arquivo mudou)"
echo "--- launch.log:"; find "$R" -name launch.log -exec cat {} +
rm -rf "$R"
