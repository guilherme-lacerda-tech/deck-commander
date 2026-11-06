# Problemas comuns

**Antes de tudo:** `python3 -m dc x diagnose` e `python3 -m dc inventory` mostram o estado real.

| Sintoma | O que fazer |
|---|---|
| Jogo novo não aparece | Abra o Decky → **Deck Commander** → "Verificar agora". O painel mostra a fila e erros. Sem o plugin instalado, reinicie o Steam. |
| Jogo aparece em "All Games" mas não na aba | Confirme que o TabMaster está instalado. As abas seguem coleções do Steam; a primeira vez depois de instalar o TabMaster exige um reinício. |
| Jogo não abre | `~/.local/state/deck-commander/launch.log` tem o comando exato. "ROM não encontrada" = cartão SD fora. Emulador ausente: `./setup-deck.sh --all` (detecta de novo) ou ajuste `~/.config/deck-commander/emulators.json`. |
| Bot não responde | `systemctl --user status deck-commander-bot`. Token: `python3 -m dc secret telegram`. |
| Downloads parados | Fora do carregador eles pausam sozinhos. `/resume` força; ajuste em `~/.config/deck-commander/power.json`. |
| Aviso de atualização ao abrir emulador | Rode `./setup-deck.sh --all` de novo (idempotente). |
| Algo deu muito errado | `./safe-mode.sh` (desliga automações, não apaga nada). Ver [recovery/README.md](recovery/README.md). |

Plugin, para quem desenvolve: erros de carregamento aparecem em `~/.local/share/Steam/logs/webhelper_js.txt`
(procure por "Deck Commander"); `python3 tools/cef_eval.py '<expressão JS>'` avalia no contexto do Steam.
