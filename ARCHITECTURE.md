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
| 3 Conteúdo | M4.6 extração protegida | `dc/safe_extract.py` |
| 3/5 | M4.4 energia + M20 sensor de bateria | `dc/power.py` |
| — | caminhos XDG separados | `dc/paths.py` |
| — | CLI | `dc/cli.py` |

Regras de fluxo:
- Toda operação destrutiva: `store.enqueue` → (aprovação) → `worker.run_once` adquire o lock →
  handler recebe `env` com `DC_OPERATION_ID` para scripts internos.
- Reentrância só vale se o lock está preso pela mesma operação e ela está `running`.
- O DB nunca escreve `shortcuts.vdf` (SRM é o dono).
