# Arquitetura

Núcleo em **Python 3.11+ só com biblioteca padrão** (nada a instalar no SteamOS imutável) + um plugin
do Decky em **JavaScript puro** (sem build). Tudo em `$HOME`.

## Diretórios (separação física)
| O quê | Onde |
|---|---|
| Código | `~/deck-commander/` |
| Configurações | `~/.config/deck-commander/` (`emulators.json`, `deck.json`, `power.json`, `backup.toml`, `plugins.lock`) |
| Segredos (600) | `~/.config/deck-commander/secrets/` (token do Telegram, chave SteamGridDB) |
| Banco, mapa, fila do plugin | `~/.local/share/deck-commander/` (`deck.db`, `launch-map.json`, `plugin-*.json`, `collections.json`, `art/`) |
| Logs e estado | `~/.local/state/deck-commander/` |
| Backups e quarentena | `~/Backups/DeckCommander/` (`DC_BACKUP_DIR` redireciona para SD/HD externo) |
| ROMs | `~/Emulation/roms/<console>/` e `/run/media/*/*/Emulation/roms/<console>/` |

## Fluxo de um jogo novo
```
Telegram ("Switch" + .torrent) -> bot -> qBittorrent (127.0.0.1:8790)
download concluído -> /sync automático -> content.ingest (classifica, extrai ZIP com segurança,
   multidisco .m3u, hardlink no mesmo disco) -> ~/Emulation/roms/<console>/<jogo>/
   -> banco (files, origem=torrent) -> launch-map.json -> plugin-queue.json (+ capas em art/)
plugin do Decky (a cada 10 s, só com o Steam já carregado):
   SteamClient.Apps.AddShortcut -> capas (SetCustomArtworkForApp) -> coleção do console -> aviso na tela
   autocorreção: atalho criado por ele que sumiu é recriado
TabMaster: aba = coleção do Steam -> jogo aparece na aba na hora
```
Sem o plugin instalado, o Deck Commander grava `shortcuts.vdf` (com backup) e pede para reiniciar o Steam.

## Módulos
| Módulo v5.1 | Arquivo |
|---|---|
| M-1 inventário | `dc/inventory.py` |
| M0 backup/restore/quarentena/safe-mode | `dc/backup.py`, `dc/quarantine.py`, `dc/ops.py` |
| M18/M19 lock, Operation Store, índice | `dc/lock.py`, `dc/store.py`, `dc/worker.py`, `dc/ops.py` |
| M27 contratos | `dc/contracts.py`, `modules/*/contract.toml` |
| M2 biblioteca (lançador fixo + mapa), abas, plugin | `dc/library.py`, `dc/launch.py`, `dc/tabs.py`, `dc/plugin_bridge.py`, `dc/steam.py`, `decky-plugin/` |
| M2.5 capas | `dc/artwork.py` |
| M3 emuladores, perfis, detecção | `dc/emulators.py`, `dc/adapters/` |
| M4 Telegram, torrents, /sync, energia | `dc/bot.py`, `dc/qbt.py`, `dc/content.py`, `dc/syncer.py`, `dc/safe_extract.py`, `dc/power.py` |
| M5 traduções IPS/BPS/UPS | `dc/patches.py` |
| M6/M7/M20/M21/M10.1 | `dc/health.py` |
| M10/M11 serviços, testes, updates, painel | `dc/services.py` |
| M12/M15 instalação por módulo | `dc/setup.py`, `setup-deck.sh`, `uninstall-*.sh` |
| M17 export/import | `dc/export.py` |

## Regras que o código garante
- Operação destrutiva: fila (`store.enqueue`) -> lock universal (`OperationLock`; reentrância só para a
  mesma operação em execução) -> log JSONL.
- `shortcuts.vdf`: só o Deck Commander **acrescenta** (com backup e verificação de round-trip); nunca
  altera/remove atalhos de outras origens (Unifideck, manuais).
- AppID estável: nome e executável dos atalhos nunca mudam; ROM/emulador mudam só no mapa.
- Leitura ausente nunca vira "ok" (sensores = `unknown`, decisão adiada).
- Nada é apagado automaticamente (quarentena com prazo de revisão; `--purge` exige confirmação).

## Dono único por função (M1)
| Função | Dono |
|---|---|
| TDP, ventoinha, clock da GPU | Panel de Control |
| CPU (SMT, boost) | PowerTools |
| Abas | TabMaster (abas `dc-*` geradas pelo Deck Commander; as suas são preservadas) |
| Lojas Epic/GOG | Unifideck |
| ROMs no Steam | Deck Commander |
| Geração de quadros | decky-lsfg-vk |

## Serviços (systemd --user)
| Unidade | Padrão |
|---|---|
| `deck-commander-qbittorrent` | ligado (WebUI só local, porta 8790 — a 8080 é do steamwebhelper) |
| `deck-commander-power` | ligado (pausa downloads fora do carregador, fila, coleções/abas) |
| `deck-commander-bot` | liga quando existe token |
| `deck-commander-backup.timer` | diário (configs + saves) |
| `deck-commander-tests.timer` | semanal (2 falhas seguidas -> safe-mode) |
| `deck-commander-updates.timer` | semanal (só avisa, não atualiza) |
| `deck-commander-dashboard` | desligado (opcional, 127.0.0.1:8765) |
