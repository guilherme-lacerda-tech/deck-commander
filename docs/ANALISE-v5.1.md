# Análise da v5.1 — falhas e melhorias

Data: 2026-11-06. Fonte analisada: `deck-commander-v5.txt` (v5.1) + histórico v3/v4/v5.

Severidade: **P0** = quebra o projeto ou perde dados · **P1** = trava a implementação ou gera retrabalho · **P2** = inconsistência/ajuste.

---

## P0 — falhas estruturais

### F1. "Fechar o Steam" não existe no Gaming Mode
M2.1, M2.4, M2.6 e M0.2 exigem Steam fechado para mexer em `shortcuts.vdf`/`localconfig.vdf`.
No Gaming Mode o Steam **é** a sessão (gamescope-session): se ele fecha, a sessão reinicia o Steam
ou cai para a tela de login. Não dá para "fechar, rodar SRM, reabrir" de dentro do Gaming Mode
como o documento descreve — e isso contradiz o princípio "Gaming Mode primeiro".

**Correção proposta:**
- Plano A: adicionar/remover atalhos pela API do cliente (`SteamClient.Apps.AddShortcut` etc.),
  via um plugin Decky mínimo — é como Unifideck e similares fazem, sem reiniciar o Steam.
- Plano B: janela de escrita offline — um serviço systemd de usuário que roda **entre** o
  `steam -shutdown` e o relançamento da sessão (ou ao trocar para Desktop).
- O spike S3 precisa testar **especificamente isto** em Gaming Mode, não só "Steam aberto/fechado".

### F2. AppID de atalho não-Steam é derivado de (executável + nome)
O AppID de atalho é calculado a partir do alvo + título. Logo:
- M4.10 (sufixo "(BR)" no nome) e M4.11 (trocar alvo de `.cue` para `.m3u`) **mudam o AppID**;
- o playtime em `localconfig.vdf` fica órfão — exatamente o que M2.6 diz proteger.

**Correção:** toda mudança de título/alvo de um atalho existente vira operação de **migração de
AppID** (copiar estatísticas do ID antigo para o novo + registrar em `provenance`). S4 deve testar renomear.

### F3. Aprovação depende do bot, mas o bot só chega na Fase D
`approval_required = true` (M12.2) é o padrão e dedup/configure-emulators (Fase C) exigem
aprovação "no Telegram", mas o M4 (bot) só existe depois. No Gaming Mode também não há terminal.

**Correção:** canal de aprovação abstrato: CLI (`dc approve <op_id>`) já na Fase B; Telegram
plugado depois; opcionalmente o plugin Decky de F1 mostra o botão "Aprovar" no Gaming Mode.

### F4. Safe-mode automático restaura configs sem aprovação
M0.3: os gatilhos automáticos (2 falhas em testes, 3 timeouts de `/sync`) executam o passo 2
(restaurar snapshot), que é destrutivo — contradiz a Regra #8 e o modo aprovação.

**Correção:** gatilho automático executa só o passo 1 (desativar serviços/agendamentos) e
**enfileira** o passo 2 como `awaiting_approval`. `/sos` manual pode fazer tudo.

### F5. Reentrância por variável de ambiente vaza
M18.1: "scripts internos recebem `OPERATION_ID` e não re-adquirem o lock". Qualquer processo
filho herda a variável — inclusive um serviço/processo de longa duração disparado pelo worker,
que passaria a ignorar o lock para sempre.

**Correção (implementada):** a reentrância só vale se o `OPERATION_ID` estiver `running` no
SQLite **e** o lock estiver de fato preso por essa mesma operação (registro do holder). Senão, é
tratado como operação independente e adquire normalmente.

## P1 — bloqueiam ou causam retrabalho

### F6. Dependências num SO imutável não foram definidas
`jq`, `sqlite3` (CLI), `bats`, `qbittorrent-nox`, `python-telegram-bot`, `unrar`, `xdelta3`:
o SteamOS tem `/usr` somente-leitura e o `pacman` some a cada update. O documento proíbe tocar
nos imutáveis mas não diz de onde as dependências vêm.

**Correção (implementada):** núcleo em **Python 3.11+ só com biblioteca padrão** (`sqlite3`,
`fcntl`, `zipfile`, `tomllib`, `hashlib`) — zero dependência nova para M-1/M0/M18/M19.
O resto: venv em `~/.local/share/deck-commander/venv` (bot), Flatpak (qBittorrent, Flips) ou
binário estático em `~/.local/bin`. Tudo no `$HOME`, que sobrevive a updates.

### F7. Instalar/remover plugins Decky não tem CLI oficial
M1 automatiza "instalar TabMaster, desinstalar ProtonDB Badges". Não há interface oficial
estável para isso. Pelo princípio de honestidade: M1 deve **detectar e orientar**, com
instalação manual pela loja do Decky (passo único, documentado).

### F8. M3: são 5 adaptadores, não 4
PSP → PPSSPP está entre os 8 consoles oficiais, mas o DoD exige "4 adaptadores
(duckstation, pcsx2, dolphin, retroarch)". Falta `adapter-ppsspp` no DoD e no S5.

### F9. Fila FIFO + aprovação: quem fica na frente?
Uma operação `awaiting_approval` bloqueia a fila inteira até expirar (1h)? Não está definido.

**Correção (implementada):** `awaiting_approval` não ocupa a cabeça da fila; o worker pega a
próxima `pending`. Aprovação expirada → `cancelled` com motivo `approval_expired`.

### F10. Test-restore de backup de ROMs dobra o espaço
M0.1 exige test-restore em sandbox para todo snapshot. Para backups de ROMs (dezenas de GB) isso
exige o mesmo espaço livre de novo. **Correção:** sandbox completo para configs; para ROMs,
verificação por manifesto SHA-256 + restore amostral.

### F11. API do qBittorrent mudou na 5.x
`torrents/pause`/`resume` viraram `torrents/stop`/`start` no qBittorrent 5.0. O M4.4 precisa de
detecção de versão da WebAPI.

### F12. Reboot real só existe no Deck
S1 pede "reboot no meio". No PC dá para simular com `kill -9` durante transação (feito); o reboot
físico continua pendente no Deck.

## P2 — inconsistências menores

- **F13 (corrigida no Deck).** A 8080 está mesmo ocupada, mas pelo `steamwebhelper` (o Decky usa a 1337). Usar 8765 é
  inofensivo, mas a justificativa está errada — vale verificar `ss -ltn` no Deck.
- **F14.** M5: o DoD diz "5 formatos" e a tabela lista 6 (inclui substituição). Definir.
- **F15.** M0.1 "mesmo dispositivo via df": `df` engana com bind mounts. Usar `st_dev` /
  `findmnt -no SOURCE` (implementado com `st_dev`).
- **F16.** Quarentena em `~/Backups/` no SD: mover ROM grande entre dispositivos é cópia+remoção
  (lento e pode falhar no meio). Quarentena de ROM deve ficar no mesmo dispositivo da ROM.
- **F17.** "Sem watcher contínuo (economia de bateria)": o bot do Telegram em long-polling já é
  um processo contínuo. Documentar o intervalo e incluí-lo no power-monitor.
- **F18.** Regra #4 da Parte 2 (confirmar antes de cada módulo) conflita com o objetivo de
  interação mínima. Proposta: aprovação em lote por fase; confirmação só para ações destrutivas
  no Deck real.

---

## O que dá para fazer agora, sem o Deck

| Spike | No PC | Pendente no Deck |
|---|---|---|
| S1 concorrência + crash | lock, reentrância, kill -9, integrity_check | reboot físico, `fcntl` real em Linux |
| S2 backup corrompido | tudo (lógica pura de arquivos) | rodar com os caminhos reais |
| S3 SRM / Gaming Mode | — | tudo (ver F1) |
| S4 playtime | — | tudo (ver F2) |
| S5 adaptadores | — | precisa dos `.ini` reais dos emuladores instalados |
| S6 energia | descoberta + histerese com sysfs simulado | ler `/sys/class/power_supply` real (LCD/OLED) |
| S10 ZIP slip/bomb | tudo | — |
