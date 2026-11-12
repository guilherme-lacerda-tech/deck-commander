# Recuperação — 17 cenários (M16)

"Teste" = coberto por teste automatizado/simulação em `tests/`. "Deck" = validado no Deck real.

| # | Cenário | Comportamento | Como resolver | Validação |
|---|---|---|---|---|
| 1 | Backup corrompido | cai para o anterior; o ruim vai para quarentena | automático (`dc backup latest`) | teste S2 + Deck |
| 2 | Todos os backups corrompidos | `AllBackupsCorrupt` → /sos | `dc backup create` novo; revisar quarentena | teste S2 |
| 3 | Emulador faltando | /diagnostico aponta lançador quebrado | reinstalar o emulador; `dc x diagnose` | teste + Deck (DuckStation) |
| 4 | ROM corrompida | vazio/erro → quarentena (sem referência = "não verificado", não corrompido) | `/quarantine review <id>` | teste content |
| 5 | Torrent com nome obscuro | /sync pergunta o console | `/console <id> <console>` | teste content |
| 6 | ZIP/RAR no torrent | extração protegida; >3 jogos pergunta; suspeito → quarentena | `/sync tudo` | teste S10 + content |
| 7 | Jogo aberto durante /sync | bloqueia (ou enfileira, `sync_during_game=queue`); downloads seguem | fechar o jogo | teste unit |
| 8 | BIOS faltando | aviso no inventário e no /diagnostico | copiar para `~/Emulation/bios` | Deck |
| 9 | Save corrompido | backups diários em `~/Backups/DeckCommander/saves` | `dc x saves import <snap> --apply` (conflito não sobrescreve) | teste |
| 10 | Schema de emulador mudou | adaptador recusa ("schema mudou?"), nada é gravado | atualizar o adaptador | teste S5 |
| 11 | /sync trava | timeout 5 min; 3 seguidos → safe-mode | `/sync` de novo; `/sos off` após revisar | teste unit |
| 12 | Bot cai | systemd reinicia (30 s); /diagnostico reinicia até 3x | `systemctl --user status deck-commander-bot` | Deck |
| 13 | Migração quebra | banco testado com `integrity_check` na abertura; backup consistente via VACUUM INTO | restaurar `deck.db` do snapshot | teste store |
| 14 | Fork do Panel quebra | M9 não aplicado (ver docs/desenvolvimento/FORK-PANEL-DE-CONTROL.md) | — | n/a |
| 15 | Decky sumiu (update SteamOS) | `x updates`/diagnóstico avisam; **não** reinstala sozinho | reinstalar o Decky manualmente | teste unit |
| 16 | `localconfig.vdf`/`shortcuts.vdf` corrompido | snapshot "steam" antes de cada gravação | `dc restore <snap> --apply` (fecha/reabre o Steam) | teste S2 + Deck |
| 17 | Banco divergente | `x db verify` mostra relatório; usuário decide | `dc x db index` | teste ops |

Reboot no meio de uma operação: a operação vira `interrupted` e espera decisão (`dc op retry|cancel <id>`) —
validado no Deck (S1).
