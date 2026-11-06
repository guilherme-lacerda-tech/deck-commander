# Privacidade (M17)

**Telemetria: nenhuma.** O Deck Commander não envia estatísticas para ninguém. Logs ficam só em
`~/.local/state/deck-commander/`.

**Mas "sem telemetria" não é "sem transmissão de dados".** Estes recursos conversam com a internet:

| Recurso | Para onde vai | O que é enviado |
|---|---|---|
| Bot do Telegram (M4) | servidores do Telegram (api.telegram.org) | seus comandos e as respostas do bot (nomes de jogos, status) |
| Downloads por torrent (M4) | trackers e outros participantes (peers) | seu **IP público** e o que você está baixando/compartilhando |
| Capas (M2.5) | SteamGridDB (steamgriddb.com) | nomes dos jogos pesquisados + sua chave de API |
| Cores do RetroArch / qbittorrent-nox (instalação) | buildbot.libretro.com · github.com | requisição de download comum |

**Segredos** (token do Telegram, chave do SteamGridDB) ficam em `~/.config/deck-commander/secrets/`
(permissão 600), nunca aparecem nos logs e **nunca** entram no `export`.

**Apagar tudo:** `./uninstall-module.sh M4 --purge` apaga o histórico do bot;
`./uninstall-deck-commander.sh --purge --confirm APAGAR` apaga configs, banco e logs
(backups só com `--purge-backups`).
