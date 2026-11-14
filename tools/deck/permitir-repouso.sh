#!/bin/bash
# Deck Commander — modo repouso: deixa o usuário "deck" segurar o descanso do Deck enquanto baixa ou traduz na tomada.
# Rode UMA vez no Deck (Konsole no modo Desktop, ou pelo ssh), digitando a SUA senha:
#     sudo bash ~/deck-commander/tools/deck/permitir-repouso.sh
# Para tirar:  sudo rm /etc/polkit-1/rules.d/49-deck-commander-repouso.rules
set -eu
cat > /etc/polkit-1/rules.d/49-deck-commander-repouso.rules <<'REGRA'
// Deck Commander (dc/repouso.py): o usuário deck pode SEGURAR o descanso (nada além disso).
polkit.addRule(function(action, subject) {
    if ((action.id == "org.freedesktop.login1.inhibit-block-sleep" ||
         action.id == "org.freedesktop.login1.inhibit-block-idle") && subject.user == "deck") {
        return polkit.Result.YES;
    }
});
REGRA
chmod 644 /etc/polkit-1/rules.d/49-deck-commander-repouso.rules
echo "Pronto: modo repouso liberado. Na tomada, com download ou tradução, o Deck não dorme até terminar."
