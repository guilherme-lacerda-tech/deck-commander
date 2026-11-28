# Relatório de reassunção — Deck Commander (Claude, 28/11/2026)

Reassunção autorizada pelo proprietário em 28/11/2026, após a paralisação pedida ao Codex.
Este relatório registra o que **verifiquei eu mesmo** hoje. Quando algo vem apenas do relatório do Codex
(`RELATORIO_PARALISACAO_2026-11-28.md`) sem conferência minha, isso está dito.

Legenda: **[verificado]** = conferido hoje por comando/arquivo; **[Codex]** = afirmado pelo Codex, não reconferido;
**[pendente]** = ainda não investigado.

## 1. O que mudou desde minha última participação

- Meu último commit foi `c66ef88` (16/11/2026), após a simulação SteamOS + EmuDeck na VM. **[verificado]**
- Depois dele, o `origin/main` recebeu 59 commits do Codex, até `61158ce` (27/11). **[verificado]**
- A branch local do Codex, `execucao/validacao-integral-20261126` (`4fd16bb`), tem 8 commits além do ancestral
  comum `4b265ce` e ainda não foi publicada. **[verificado]**
- O `61158ce` é 1 commit sobre o `4b265ce` que não está nessa branch. Os arquivos de segurança são idênticos nas duas
  (`dc/test_runner.py`, `dc/atualizar.py`, `dc/saves_*.py`, `dc/backup.py`), porque a branch trouxe a mesma
  correção em `5766990`. **[verificado]**
- A automação Codex `retomar-o-deck-commander` está `PAUSED` (`~/.codex/automations/.../automation.toml`).
  **[verificado]**
- Tarefas agendadas restantes no Windows: `DeckCommander Transferencias` e `DeckCommander-IA`. São serviços do
  produto, não agentes de desenvolvimento; foram mantidas. **[verificado]**

## 2–4. O que o Codex implementou, corrigiu e deixou parcial

Da leitura do código e do diff (detalhes de cada um no relatório do Codex):

| Item | Estado | Base |
|---|---|---|
| Executor de testes em `bubblewrap` (`dc/test_runner.py`), sem fallback para pytest direto | implementado; auditado abaixo (§13) | [verificado] |
| Launcher regenerado no pós-atualização (`atualizar.depois`) | implementado | [verificado] |
| Proteções de saves (conflito na 1ª sincronização, ancestral preservado, retenção ≥1) | implementado + testes | [verificado] código; [Codex] hardware |
| Catálogo HTTPS de downloads (`dc/catalogo_downloads.py`): SHA-256, retomada HTTP, worker separado, fila SQLite | implementado; **só 2 jogos** no catálogo | [verificado] |
| Busca Prowlarr em segundo plano (`dc/prowlarr.py`) | implementado; **lenta** (ver §16) | [verificado] |
| RomM (`dc/romm_client.py`, `dc/romm_queue.py`), HomeLab Ansible/Compose | implementado; laboratório | [verificado] código; [Codex] lab |
| Perfis de controle Azahar/Cemu/RPCS3 (`config/controller-profiles/`, `dc/emulators/setup_controls.py`) | implementado; sem aceite físico | [verificado] código |
| `dc/emulators.py` virou pacote `dc/emulators/` | refatoração | [verificado] |
| Busca multiplataforma ("god" → várias plataformas) | **não implementada**: o fluxo atual ainda pede a plataforma antes de buscar | [verificado] em `bot._iniciar_catalogo` |

## 5. O que está comprovadamente funcionando (hoje)

- Deck físico ligado e acessível; bot e serviço de energia `active`; Prowlarr `active`. **[verificado]**
- Suíte do commit consolidado `b91d3c8` no Windows: **1092 aprovados, 4 pulados** (unitários e de integração com
  serviços substituídos; não é E2E nem validação física). **[verificado]**
- Prowlarr no Deck responde, mas leva **92,5 s** para uma busca por "doom" (100 resultados). **[verificado]**

## 6. O que foi alterado no Steam Deck

Comparei os 323 arquivos de `~/deck-commander/{dc,decky-plugin,tests,config,tools}` com o git:

- Contra `76ab40c`: 11 arquivos diferentes. São exatamente os do reparo `61158ce`. **[verificado]**
- Contra `61158ce`: só `dc/test_runner.py` com fim de linha CRLF (conteúdo idêntico) e 3 arquivos de teste sem os
  testes novos. **O código de produção do Deck equivale ao `61158ce`.** **[verificado]**
- `VERSAO.txt` do Deck ainda diz `76ab40c`. O reparo foi aplicado arquivo a arquivo, sem atualizar o registro.
  **Risco:** o atualizador compara versões por esse arquivo. **[verificado]**
- Checkpoints no Deck (`code-checkpoints/save-sync-*`, `dmc-launch-repair-*`). **[Codex]** Ainda não listados.

## 7. O que foi alterado no RG505

O relatório do Codex de 28/11 **omite** o RG505. Encontrei trabalho real:

- **Sistema:** Android com acesso a `/data/user/0/*` pelo ADB, ou seja, com root. Front-end Daijishō. Emuladores
  com dados no backup: DraStic, DuckStation, Citra, Dolphin MMJR, Mupen64Plus FZ (+pro), PPSSPP Gold, AetherSX2 e
  RetroArch. **[verificado]** no backup.
- **Backup** de 19/11, em `Documents/Codex/2026-11-19/v/work/rg505-backup/`:
  `emulator-configs-and-saves-2026-11-19.tar.gz` (73 MB) e `unknown-app.apk`. **[verificado]**
- **Instalações** em `work/rg505-install/`: RetroArch aarch64 e Moonlight (APKs), com capturas de pareamento e de
  streaming do Moonlight. **[verificado]**
- **Bot próprio "RG505 Commander"**, um segundo bot do Telegram, separado do Deck:
  - Código em `Documents/Codex/2026-11-19/v/outputs/rg505-commander/`; não está em nenhum repositório git.
  - Estado em `%LOCALAPPDATA%\RG505Commander`.
  - Iniciado pelo atalho `Startup\RG505-Commander.cmd`, que também abre um qBittorrent próprio na porta 58180.
  - **Está rodando agora no PC**: processo "RG505 Commander", iniciado em 28/11 às 09:10. **[verificado]**
  - Funções:
    - Instala ROMs no cartão por ADB, via Tailscale `100.119.68.85` ou LAN `192.168.100.61`, na porta `39951`.
    - Sincroniza Deck → RG505 sem apagar nada, com manifesto de 37 arquivos.
    - Cuida de torrents e de traduções.
  - **Defeito visível:** o arquivo de configuração guarda a senha do qBittorrent em texto. **[verificado]**
- **Firetv-wake-relay:** um app Android também gerado em 19–20/11. **[verificado]** Existe; ainda não auditado.
- **Acesso agora:** o ADB não conecta em nenhum dos dois endereços (timeout). O RG505 está desligado ou com a
  depuração sem fio desativada. Na depuração sem fio do Android a porta também muda a cada ativação. **[verificado]**
- **A validar quando ele estiver acessível:**
  1. Versão do Android e do firmware (`getprop`).
  2. Root.
  3. Espaço livre.
  4. Integridade dos 37 arquivos do manifesto.
  5. Saves dos emuladores contra o backup.
  6. Pareamento do Moonlight.

## 8. PC

- Repositório do Codex: `Documents/Codex/2026-11-17/in/work/deck-commander`, com worktree do hotfix. Estava com
  `AGENTS.md` e `EXECUTION_STATE.json` modificados e o relatório sem commit. Os três foram **preservados**: copiados
  para a branch de consolidação. O original não foi tocado. **[verificado]**
- Repositório canônico: `C:/dev/deck-commander`, que estava 59 commits atrás do `origin/main`.
- Consolidação feita no worktree `C:/dev/dc-consolida`, branch `consolida/2026-11-28`. **[verificado]**

## 9. VM

- VM SteamOS 3.8.14 em `D:\vm-steamos`, criada por mim em 16/11.
- O Codex instalou nela a versão `d884e20` e cópias posteriores. **[Codex]**
- A Steam nunca teve o primeiro login. **[Codex]** Bate com o que deixei em 16/11.

## 10. HomeLab

- Existe stack Docker/WSL de laboratório com RomM, MariaDB, Prowlarr, qBittorrent e Ansible. **[Codex]**
- O servidor Debian pessoal **não foi inventariado nem provisionado** pelo Codex. Eu ainda não investiguei.
  **[pendente]**

## 11–12. Diferenças entre branches e o que não estava integrado

| Ambiente | Commit | Observação |
|---|---|---|
| GitHub `main` | `61158ce` | Isolamento de testes e reparo do launcher |
| Branch do Codex | `4fd16bb` | + aquisição por nome, retomada HTTP, RomM, HomeLab, perfis de controle |
| Deck físico | ≈ `61158ce` | `VERSAO.txt` diz `76ab40c`; sem a aquisição por nome |
| **Consolidação** | `b91d3c8` | `61158ce` + `4fd16bb` + relatório do Codex; 1 conflito (README, texto equivalente) |

Fora do git ficam:

- o RG505 Commander;
- o firetv-wake-relay;
- as branches `re/sc3`, `re/dq8` e `re/cod-x360` e as branches `pronto/*` dos worktrees em `C:/dev/dc-*`, que vêm
  de antes da ausência e não foram tocadas.

## 13. Riscos encontrados

1. **Auditoria do isolamento de testes (`61158ce`).**
   - O desenho está correto:
     - `/` montado somente leitura;
     - `/home`, `/run` e `/tmp` em tmpfs, o que esconde o HOME real, o cartão SD e os sockets do Steam;
     - `--unshare-all`, sem rede nem PID compartilhado;
     - `--clearenv`, HOME e XDG privados;
     - sem `bwrap` ou sem venv dedicado, retorna código 2 e **não roda pytest**.
   - Ponto aberto: num Deck sem o venv de testes, a atualização é **recusada**. O instalador cria esse venv
     (`setup._venv_pip(TEST_VENV, "pytest")`). Falta comprovar isso numa instalação nova.
2. `VERSAO.txt` desatualizado no Deck (§6).
3. Seleção de resultado por posição (`/resultado N`). Se a lista mudar, N aponta outro item. Há TTL, mas não há
   identidade estável. **Corrigir na busca nova.**
4. RG505 Commander:
   - senha do qBittorrent em texto no `config.json`;
   - fora de versionamento.
5. Dois bots do Telegram, Deck e RG505, para o mesmo dono: dois pontos de controle. Precisa consolidar (§20).

## 14. Regressões

- Nenhuma regressão nova reproduzida hoje.
- A regressão DMC3, com o launcher apontando para o staging apagado, foi corrigida. **[Codex]**: o jogo abriu no
  Deck. A causa e a proteção eu conferi no código.

## 15. Resultados dos testes (sem somar versões)

| Commit | Ambiente | Resultado | Tipo |
|---|---|---|---|
| `b91d3c8` | Windows (PC) | 1092 ok, 4 pulados | unitários + integração com substitutos |

Os números do Codex (1.050, 1.090…) são de outros commits e não se somam a este.

## 16. Estado da pesquisa pelo Telegram

**Causa real do timeout do Prowlarr, medida hoje no Deck:**

| Requisição à mesma URL `advancedsearch` do Internet Archive | Tempo |
|---|---|
| `curl` padrão | 2,8 s |
| `curl --http1.1` | 1,1 s |
| `curl` com `User-Agent: Prowlarr/3.1.0.5799` | **84,9 s** |
| Prowlarr `/api/v1/search?query=doom` | **92,5 s** |

- DNS é imediato (A em 0,02 s; não existe AAAA, então não é IPv6). Não há proxy configurado.
- **O Internet Archive atrasa de propósito as requisições identificadas como Prowlarr.** Não é rede.
- Como o cliente do Deck Commander desiste em 15 s, o resultado aparece como falha.
- O Prowlarr não permite trocar o User-Agent por indexador.

**Decisão:**

- Um adaptador direto para o Internet Archive, identificado honestamente como Deck Commander (sem se passar por
  navegador).
- O Prowlarr continua como provedor opcional, em paralelo, com estado de falha explícito.

Hoje a busca:

- pede a plataforma antes de pesquisar;
- não tem lista multiplataforma, paginação, filtros nem identidade estável dos resultados;
- não diferencia "nenhum resultado" de "fonte indisponível" na resposta ao usuário (`_receber_resultados` recebe
  `[]` nos dois casos).

## 17–19. Tradução, biblioteca e saves

- **Tradução:** a aquisição chama `traducao.run.auto_queue` depois de instalar. O fluxo comunidade-primeiro está no
  código desde 0.10.0. O aceite de ponta a ponta de um jogo baixado e traduzido continua **[pendente]**.
- **Biblioteca:** o caso EmuDeck foi validado por mim na VM (16/11), com 3.253 hashes preservados. O Codex diz ter
  conferido 32.488 hashes. **[Codex]** A biblioteca autenticada (Steam logada) continua sem comprovação na VM.
- **Saves:** proteções novas no código. A recuperação de perdas antigas não foi comprovada. **[Codex]**, de acordo.

## 20. Arquitetura multiplataforma

Hoje são dois produtos paralelos:

- Deck Commander: Python no Deck, bot próprio.
- RG505 Commander: Python no PC, bot próprio, ADB.

Proposta incremental, sem reescrita:

- busca e catálogo como módulo único (`dc/busca.py`) com provedores;
- dispositivos descritos por perfis de capacidade;
- RG505 como "dispositivo de destino" do mesmo bot, por um agente ADB no PC (reaproveitando `rg505_commander.py`).

## 21. Requisitos pendentes

`MASTER_REQUIREMENTS.md` tem 529 linhas: 527 `PENDING` e 2 `IN_PROGRESS`. Como o Codex reconheceu, isso não
representa a realidade.

- A reconciliação linha a linha é uma tarefa própria e ainda não foi feita.
- Não informo percentual de conclusão antes disso.
- RG505 e busca multiplataforma ainda não estão na matriz.

## 22. Bloqueios externos

- RG505 inacessível pelo ADB (ligar e ativar a depuração sem fio).
- Steam da VM sem primeiro login: precisa do dono.
- Servidor Debian pessoal ainda não localizado. **[pendente]**

## 23. Avaliação técnica independente

- **Pontos fortes do trabalho do Codex:**
  - o isolamento de testes está bem feito;
  - o download verificado (hash, retomada, sem link simbólico, publicação atômica) é sólido;
  - o relatório é honesto sobre os limites.
- **Pontos fracos:**
  - o fluxo de busca ficou preso a "plataforma primeiro" e a uma fonte lenta;
  - a seleção é feita por posição;
  - a matriz não foi reconciliada;
  - o trabalho do RG505 ficou fora do repositório e fora do relatório;
  - o reparo no Deck foi aplicado sem atualizar `VERSAO.txt`.

## 24. Estratégia de continuidade (em execução)

1. **P0 busca:**
   - `dc/busca.py` com provedores (catálogo local, biblioteca, Internet Archive direto, Prowlarr, Família) e estado
     por provedor;
   - consulta "título [plataforma]";
   - fuzzy, abreviações, deduplicação, paginação;
   - resultados com identidade estável e expiração;
   - detalhe com escolha de dispositivo e compatibilidade;
   - aquisição idempotente.
2. Testes unitários e de integração; depois VM; depois Deck com checkpoint.
3. Validação real pelo bot instalado com conteúdo autorizado (homebrew ou domínio público).
4. Consolidar o RG505 como destino.
5. Reconciliar a matriz.
6. P1: DMC3, saves, demais itens.
