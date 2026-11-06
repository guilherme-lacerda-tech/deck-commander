# Arquitetura (estado atual)

Núcleo Python 3.11+ stdlib (correção F6 — nada a instalar no SteamOS imutável).

| Camada v5.1 | Módulo | Arquivo |
|---|---|---|
| 0 Segurança | M0.1/M0.2 backup verificado, fallback, restore com guarda do Steam | `dc/backup.py` |
| 0 Segurança | M0.4 quarentena com `review_by` | `dc/quarantine.py` |
| 4 Orquestração | M18.1 lock + reentrância validada | `dc/lock.py` |
| 4 Orquestração | M18/M19 Operation Store SQLite (WAL, FULL, integrity, aprovação 1h) | `dc/store.py` |
| 4 Orquestração | worker FIFO + recover + operations.log | `dc/worker.py` |
| 2 Biblioteca | leitura de VDF (base de M2.6) | `dc/vdf.py` |
| 2 Biblioteca | M2 launcher fixo + mapa (AppID estável, sem SRM) | `dc/library.py`, `dc/launch.py` |
| 3 Conteúdo | M4.6 extração protegida | `dc/safe_extract.py` |
| 3/5 | M4.4 energia + M20 sensor de bateria | `dc/power.py` |
| — | caminhos XDG separados | `dc/paths.py` |
| — | CLI | `dc/cli.py` |

Regras de fluxo:
- Toda operação destrutiva: `store.enqueue` → (aprovação) → `worker.run_once` adquire o lock →
  handler recebe `env` com `DC_OPERATION_ID` para scripts internos.
- Reentrância só vale se o lock está preso pela mesma operação e ela está `running`.
- Só `dc library` grava `shortcuts.vdf`, e só ACRESCENTA (nunca altera/remove atalhos de outras origens).

M2 (decisão do usuário 2026-11-06): todos os atalhos de ROM apontam para
`~/.local/share/deck-commander/bin/dc-launch <game_id>`; o mapa fica em
`~/.local/share/deck-commander/launch-map.json` e os emuladores em `~/.config/deck-commander/emulators.json`.
Trocar ROM/emulador = editar o mapa, sem reiniciar o Steam. Adicionar jogos novos = `python3 -m dc library --apply`
+ reiniciar o Steam uma vez.

## M1 — Dono único por hardware/função (Deck do usuário, 2026-11-06)
| Hardware / função | Dono | Observação |
|---|---|---|
| TDP, curva de ventoinha, clock da GPU | Panel de Control | PowerTools não deve mexer nisso |
| CPU (SMT, boost, núcleos) | PowerTools | Panel não mexe |
| Launch options de compatibilidade | Proton Pulse (opcional) | **não instalado** → M8 bloqueado |
| Abas da biblioteca | TabMaster | **não instalado** (instalação manual pela loja do Decky) |
| Lojas Epic/GOG | Unifideck | 500 atalhos; o DC nunca toca neles |
| ROMs no Steam | Deck Commander (`dc-launch`) | 22 atalhos; só acrescenta |
| Geração de quadros | decky-lsfg-vk | ativado por jogo pela própria interface do plugin |
| Badges ProtonDB | protondb-decky | v5.1 sugeria remover; mantido (não conflita com nada instalado) |

Versões travadas em `~/.config/deck-commander/plugins.lock`; `x updates` e `x diagnose` avisam se mudarem.
Instalar/remover plugins do Decky não tem interface oficial por linha de comando (achado F7): é manual.

## Serviços (systemd --user)
| Unidade | Módulo | Padrão |
|---|---|---|
| deck-commander-qbittorrent | M4 | ligado (WebUI só em 127.0.0.1:8790; a 8080 é do steamwebhelper) |
| deck-commander-power | M4.4/M18 | ligado (pausa downloads fora do carregador, roda fila) |
| deck-commander-bot | M4 | liga sozinho quando existir o token |
| deck-commander-backup.timer | M0/M6 | diário (configs + saves) |
| deck-commander-tests.timer | M10.4 | semanal + 15 min após o boot; 2 falhas seguidas → safe-mode |
| deck-commander-updates.timer | M11 | semanal; só avisa |
| deck-commander-dashboard | M10.1 | desligado (127.0.0.1:8765) |
