# Problemas comuns

**Antes de tudo:** `python3 -m dc inventory` e `python3 -m dc x diagnose` — mostram o estado real do Deck.

- **Jogo não abre pelo Steam:** veja `~/.local/state/deck-commander/launch.log` (cada tentativa fica registrada,
  com o comando exato). Cartão SD fora = "ROM não encontrada".
- **Jogo novo não aparece:** depois do `/sync` ou `dc library --apply`, reinicie o Steam (`/reiniciar`).
- **Atualização/aviso ao abrir emulador:** os avisos de update estão desligados no DuckStation e Ryujinx;
  se voltar, rode `./setup-deck.sh --all` de novo (idempotente).
- **Bot não responde:** `systemctl --user status deck-commander-bot` · token: `python3 -m dc secret telegram`.
- **Downloads parados:** fora do carregador eles pausam sozinhos (monitor de energia). `/resume` força.
  Ajuste em `~/.config/deck-commander/power.json` (`allow_on_battery`, `min_battery_pct`).
- **Algo deu muito errado:** `./safe-mode.sh` (desliga tudo, não apaga nada) e me chame.
