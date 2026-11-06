## Relatório de Spikes — fase PC (2026-11-06)

Ambiente: Windows 11, Python 3.12.10, pytest 8.4.2 (WSL indisponível — virtualização desligada).
Resultado: `python -m pytest -q` → **43 passed**. Validação no Linux/Deck real: ver `deck/DECK-PROMPT.md`.

### S1 — Concorrência + reboot
Status: **PARCIAL** (lógica passou no PC; reboot físico e `fcntl` real pendentes no Deck)
Evidência (`tests/test_s1_concurrency.py`):
- 2 processos: o segundo espera e estoura timeout com mensagem dizendo quem segura (tipo/op/pid).
- `kill` do dono do lock → o SO libera; ninguém fica preso.
- Reentrância: script interno com `DC_OPERATION_ID` não trava (`REENTRANT`).
- **Correção F5:** `DC_OPERATION_ID` vazado de operação concluída **não** fura o lock (`BLOCKED`).
- `kill` no meio de uma transação de 2000 inserts → banco abre com `integrity_check ok`, transação
  não confirmada some, operação `running` vira `interrupted` e aceita `retry`.
- `recover` não marca como interrompida uma operação que ainda segura o lock.
- Worker FIFO: operação `awaiting_approval` não segura a fila (correção F9); log JSONL por operação.
Impacto: nenhum ajuste estrutural; pendente `deck/s1_reboot.py` no Deck.

### S2 — Backup corrompido → restore
Status: **PASSOU** (lógica de arquivos; repetir com caminhos reais no Deck)
Evidência (`tests/test_s2_backup.py`): corrupção durante a criação → quarentena, nenhum snapshot
publicado; snapshot mais novo corrompido → cai para o anterior, o corrompido vai para quarentena
(movido, não apagado) com motivo; todos corrompidos → `AllBackupsCorrupt` (/sos); retenção mantém 5;
restore que toca `shortcuts.vdf` é recusado sem guarda do Steam e, com guarda, fecha→restaura→reabre;
quarentena vencida (30 dias) só avisa; aviso de mesmo dispositivo físico via `st_dev`.
Impacto: o "guarda do Steam" real depende de S3 (F1). Até lá, `dc restore --apply` bloqueia snapshots
que tocam arquivos do Steam.

### S3 — SRM CLI / Gaming Mode
Status: **PENDENTE (Deck)**. Ver F1: fechar o Steam no Gaming Mode reinicia a sessão.

### S4 — Playtime
Status: **PENDENTE (Deck)**. Leitor de VDF binário/texto pronto (`dc/vdf.py`); teste prova que o AppID
muda ao renomear ou trocar `.cue`→`.m3u` (F2). Falta confirmar onde o Steam guarda o playtime de atalhos.

### S5 — Adaptadores
Status: **PENDENTE (Deck)**. Precisa dos arquivos reais; são **5** adaptadores (F8).

### S6 — Energia dinâmica
Status: **PARCIAL** (`tests/test_s6_power.py`): descoberta por `type` com nomes variados, carregador
USB-C, sysfs ausente = unknown (mantém estado, não chuta), debounce contra cabo com mau contato,
histerese de bateria, carga lenta tratada como bateria. Falta: sysfs real LCD e OLED.

### S10 — ZIP Slip / bomb
Status: **PASSOU** (`tests/test_s10_extract.py`): `..`, caminho absoluto, `C:`, barra invertida,
symlink, colisão (maiúsc./minúsc. e arquivo×pasta), profundidade, contagem, tamanho total, proporção
de compressão, bytes reais > declarado, cancelamento sem pasta parcial, arquivo não-ZIP.
RAR fora do spike (precisa `unrar`).

### Conclusão
- Liberados para implementação (após confirmar no Linux do Deck): M18+M19, M0 (exceto restore de
  arquivos do Steam), M4.6 extração ZIP.
- Bloqueados: M2 (S3/S4, F1/F2), M3 (S5), M4.4 aplicação real (S6 no hardware).
- Ajustes na v5.1: F1–F18 em `docs/ANALISE-v5.1.md`.
