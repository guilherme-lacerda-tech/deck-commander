# Deck Commander — relatório de entregas, pendências e paralisação

Data: 28/11/2026. Trabalho interrompido por determinação do proprietário.

## 1. Situação geral

**O projeto não está concluído. O download de jogos apenas pelo nome ainda não foi entregue de ponta a ponta no bot instalado no Deck. A falha que impedia o DMC3 de abrir foi corrigida e verificada no aparelho.**

Há três estados diferentes que precisam permanecer separados:

| Ambiente | Estado comprovado antes da paralisação |
|---|---|
| Steam Deck físico | Base identificada como `76ab40c`, com reparos diretos de proteção de saves e de lançamento/atualização. Bot e Prowlarr presentes. O módulo novo `dc/catalogo_downloads.py` ainda não estava instalado. |
| GitHub, branch `main` | Correção `61158ce` publicada. Contém isolamento dos testes, reparo do launcher e proteções de saves. Não contém o fluxo novo completo de aquisição por nome. |
| Branch local `execucao/validacao-integral-20261126` | Último commit de implementação/registro `4fd16bb`. Contém aquisição por nome, recuperação HTTP, integrações HomeLab/RomM e outras mudanças ainda não publicadas integralmente em `main`. |
| VM SteamOS | Instalação de teste identificada como `d884e20`; cópias separadas foram usadas para validar versões posteriores. Dois jogos baixados e abertos. Steam sem primeiro login; a publicação na biblioteca autenticada não foi comprovada nesse ambiente. |
| HomeLab de laboratório | Stack real em Docker/WSL, provisionada e testada. Não equivale a implantação no servidor Debian pessoal. |

O relatório distingue execução observada, testes de código e registros históricos. Informações antigas não foram promovidas a conclusão atual sem evidência. A paralisação interrompe também a implementação que começava a adaptar a busca ao exemplo “god”, com opções de PS2 e PSP.

## 2. O que foi parado

- A automação Codex `retomar-o-deck-commander`, de 30 em 30 minutos, foi alterada para **PAUSED** e conferida no arquivo de configuração.
- A listagem de agentes passou a conter somente o agente principal responsável por este relatório. Não havia subagentes de implementação ativos ao consolidar o documento.
- Não foram iniciados novos testes, downloads, instalações ou alterações funcionais após o pedido de parar. As ações posteriores foram leitura local, pausa da automação e documentação.
- Antes da elaboração deste relatório, o Git não mostrava alterações pendentes nos arquivos rastreados; apenas `outputs/` estava fora do versionamento. A nova busca multiplataforma não apareceu como implementação incorporada ao repositório.
- Os serviços normais do produto não foram desligados para produzir o relatório. As tarefas Windows de transferência e do suporte de IA são distintas da retomada automática do Codex. Não foi executado shutdown do Deck, da VM ou do HomeLab.
- A retomada do desenvolvimento depende de uma nova instrução do proprietário. A existência de instruções antigas de execução autônoma não revoga esta pausa.

## 3. Correções e entregas verificadas

### 3.1 DMC3 não abria pela biblioteca

**Defeito reproduzido no Deck:** o script `~/.local/share/deck-commander/bin/dc-launch` importava o programa de uma pasta `/tmp/dc-atualizar-...` que havia sido removida. O resultado era `ModuleNotFoundError: No module named dc`, antes de iniciar o emulador.

**Causa identificada:** um teste de sincronização de jogos do PC usava caminhos de dados temporários, mas continuava usando o HOME real para gravar o launcher. O teste executado durante a atualização podia, portanto, danificar a instalação em uso. O pós-atualização não regenerava esse launcher. O timer semanal também executava a suíte sem isolamento.

**Correções executadas:**

1. Backup do launcher, atalhos, mapa, configurações PCSX2, 20 arquivos de estados e dois cartões de memória.
2. Substituição atômica do launcher para usar `/home/deck/deck-commander`, preservando o caminho do atalho e seu AppID.
3. Isolamento de testes com `bubblewrap`: fonte somente para leitura, HOME/XDG privados, separação de processos, rede e sessão do usuário.
4. Atualização bloqueada quando o executor isolado não pode iniciar; sem execução direta de pytest como alternativa.
5. Regeneração do launcher na instalação definitiva após atualizar.
6. Correção do teste que escapava do HOME de ensaio.
7. Reativação do timer semanal após instalar e verificar a proteção.
8. Publicação da correção em `main`, commit `61158ce`.

**Prova física:** o Steam abriu o atalho original do DMC3; o PCSX2 carregou o executável do jogo `SLES_541.86`, CRC `18C9343F`, Vulkan, áudio Cubeb e Steam Virtual Gamepad. Os 22 arquivos de progresso mantiveram os mesmos hashes. Não foi executada restauração de save. No arquivo de atalhos, a única diferença observada foi o horário da última execução escrito pelo Steam.

**Limite:** abertura do jogo não demonstra correção dos engasgos na luta com Vergil. A tela inicial PAL apresentou aproximadamente 50 FPS; esse dado não foi tratado como teste de combate a 60 FPS.

### 3.2 Proteção de saves e backups

Três módulos foram corrigidos e instalados no Deck com checkpoint anterior:

- Dois saves diferentes na primeira sincronização passam a ser conflito; o programa não escolhe automaticamente um deles apenas pelo relógio.
- Uma transferência incompleta não apaga o registro da última versão comum dos arquivos divergentes.
- Retenção rejeita zero cópias e verifica integralmente os snapshots antes de considerar apagar excedentes.

Houve testes focados no Deck em perfil descartável, comparação dos módulos antes/depois e publicação das proteções na release corretiva. A verificação recente de 22 arquivos comprova preservação durante o reparo. Ela não comprova recuperação dos minutos de gameplay perdidos em episódios anteriores.

### 3.3 Aquisição por nome em laboratório

Foi implementado um catálogo HTTPS padrão e pessoal, com:

- Identificação por nome e plataforma.
- Operações persistentes em SQLite e worker separado do bot.
- Verificação de tamanho e SHA-256.
- Extração de membro especificado de arquivo ZIP.
- Instalação em diretório determinado, proteção contra sobrescrita de arquivo diferente e deduplicação.
- Estados de espera quando existe jogo aberto ou falta o primeiro login Steam.
- Busca Prowlarr em segundo plano e persistência de pedidos sem fonte.
- Suporte a adicionar arquivos `.torrent`, além de magnets.
- Retomada HTTP após interrupção, com validação de `Content-Range` e do arquivo final.

**Ensaios reais na VM:**

| Jogo/ensaio | Resultado |
|---|---|
| Super Tilt Bro 1.0, NES | Pedido por nome ao handler, download HTTPS, hash, instalação e tela inicial no Nestopia. |
| Doom Shareware | Pedido por nome ao handler, download do ZIP, extração de `doom1.wad`, instalação de dado auxiliar do PrBoom e abertura de fase jogável. |
| Pedido repetido | Reutilizou operação/arquivo existente, sem nova instalação duplicada. |
| Download interrompido | Worker encerrado por SIGKILL; 1.048.576 bytes preservados, retomada a partir desse ponto, conclusão de 4.196.020 bytes com hash correto, uma operação e duas tentativas. |

**O que isso não entregou:** a mensagem entrando pelo Telegram público e terminando em um jogo novo na biblioteca Steam autenticada do proprietário. O ensaio chamou o handler local com o nome do jogo; não foi uma conversa real completa no Telegram. O catálogo padrão contém esses dois títulos, não um catálogo universal de jogos.

### 3.4 Prowlarr e diagnóstico mais recente

No Deck foi confirmado:

- Bot ativo e token Telegram válido por `getMe`, sem consumir mensagens nem enviar mensagens de teste.
- Prowlarr `3.1.0.5799` acessível em loopback.
- Um indexador habilitado, Internet Archive.
- A consulta por “Doom Shareware” excedeu 15 segundos no cliente.
- O log do Prowlarr mostrou a chamada ao Internet Archive terminando por timeout após aproximadamente 100 segundos e o healthcheck marcou falha dos indexadores.
- Pouco antes da pausa, a mesma consulta à API do Internet Archive, feita diretamente com Python no Deck, respondeu em aproximadamente 0,9 segundo. Uma busca menor por “god” também respondeu.

Portanto, a investigação localizou uma diferença entre o caminho Prowlarr/Cardigann e o acesso direto. **Não foi concluída a causa interna dessa diferença nem implantada uma correção/fonte alternativa.** A proposta de adaptador direto e a nova busca com resultados PS2/PSP estavam em investigação quando o proprietário mandou parar.

### 3.5 qBittorrent, importação e RomM

No código de desenvolvimento foram corrigidos:

- Autenticação e mapeamento dos diretórios entre cliente e servidor qBittorrent.
- Respostas reais do qBittorrent 5.3.1, incluindo HTTP 204 e cookie específico da porta.
- Espera da verificação de integridade antes de tratar o download como concluído.
- Criação do primeiro `shortcuts.vdf` em perfil vazio; backup e releitura em perfil existente.
- Uso da mesma trava para leitura e escrita da sincronização, evitando gravar estado antigo depois de liberar o lock.
- Cliente real RomM com `POST /api/tasks/scan`, consulta da tarefa e fila persistente.
- Tratamento de `task_id`, em vez de presumir uma resposta com campo `id`.

O laboratório exerceu Prowlarr → torrent → qBittorrent autenticado → download por peer → hash → importação → primeiro arquivo de atalhos → catálogo RomM. Foi usada uma ROM iNES de teste, não o fluxo completo de um jogo comercial traduzido e jogado no aparelho do proprietário.

### 3.6 HomeLab e instalação em VM

- Estrutura Ansible com inventário de exemplo, roles Docker/media_stack, playbooks de aplicação e validação.
- Template Compose com RomM, MariaDB, Prowlarr, qBittorrent e redes frontend/apps/database; banco em rede interna.
- Serviço ROMarr condicional à definição de uma imagem. Isso não demonstra um ROMarr funcional implantado.
- Syntax-check, check mode e ansible-lint aprovados no laboratório.
- Aplicação repetida com `changed=0` e `failed=0` no inventário de teste.
- RomM real 5.4.1 com autenticação e descoberta da ROM de teste.
- VM SteamOS 3.8.14 com EmuDeck, plugin e emuladores existentes.
- Instalação repetida na VM e conferência do plugin por comparação de arquivos.
- Conferência de **32.488 hashes** anteriores de EmuDeck, PCSX2 e Emulation, todos preservados no ensaio.

O servidor Debian pessoal não foi inventariado e provisionado nesta execução. A integração efetiva com 1Password também não foi demonstrada.

### 3.7 Controles iniciais e IA local

- Criados perfis e preparação de primeiro uso para Azahar, Cemu e RPCS3 em Flatpak no Steam Deck. O código preserva perfis existentes e só cria onde faltam.
- Testes focados de controles/emuladores/instalação aprovaram 20 casos. Isso não equivale a conferir os três controles em partidas reais.
- Ollama com `qwen2.5-coder:7b` foi utilizado em revisões de código, com respostas registradas. Sugestões genéricas ou incorretas não foram incorporadas automaticamente.
- A execução não foi conduzida integralmente por IAs locais. Não foi demonstrado um sistema completo de agentes locais autônomos, nem uma medição de economia de tokens/RAM/VRAM cobrindo todo o trabalho.

## 4. Pendências por área

| Área | O que existe ou foi verificado | O que falta para considerar entregue |
|---|---|---|
| Nome do jogo no Telegram — P0 | Código de catálogo e ensaios reais de dois jogos na VM; bot físico e token presentes | Integrar as mudanças à release, implantar no Deck e provar conversa real até biblioteca e execução. |
| Busca “god” em PS2/PSP | Requisito detalhado; código anterior ainda pede plataforma antes da pesquisa geral | Lista multiplataforma, filtros, paginação, seleção protegida contra botão antigo e categoria correta ao baixar. O novo comportamento não foi incorporado antes da pausa. |
| Fontes e timeout | Um indexador configurado; falha localizada no caminho Prowlarr | Resolver a requisição lenta ou implementar alternativa compatível; provar recuperação e resultados reais, sem esconder falhas atrás de lista vazia. |
| Escolha de edição | Há seleção de resultados e tentativa de identificação inequívoca | Distinguir plataforma, revisão, região, pacote, idioma e tamanho; impedir escolha errada e manter variedade de plataformas. |
| Tradução após aquisição | Existe integração com fila de tradução e vários motores | Demonstrar baixar, traduzir, validar e abrir um jogo completo suportado; tratamento claro quando não houver receita compatível. |
| Biblioteca Steam/EmuDeck | Ensaios de preservação e primeiro atalho; launcher DMC3 reparado | Matriz completa: instalação vazia, existente, incompleta, configuração errada, caminhos alternativos, emuladores diferentes e usuário Steam real. |
| Wii e biblioteca poluída | Há lógica de identificação, deduplicação e testes relacionados | Reproduzir o conjunto que gerou centenas de atalhos e comprovar importação correta de jogos, arquivos auxiliares e formatos ambíguos, preservando a biblioteca real. |
| Ports nativos/escolha de emulador | Há infraestrutura de biblioteca e comandos de lançamento | Aceite completo de ports nativos e troca de emulador por plataforma/jogo sem recriar configurações pessoais. |
| Atualização em redes distintas | Consulta GitHub, reparo publicado, pós-instalação e testes isolados | Percurso integral de atualização e rollback pela interface, fora da mesma rede, com instalação existente e falha/interrupção controlada. |
| Desempenho DMC3 | Telemetria e ajuste de TDP existem; abertura foi verificada | Reproduzir combate pesado, medir velocidade/FPS/frametime/TDP/temperatura e preservar a melhor qualidade estável; economia apenas após desempenho, conforme prioridade do usuário. |
| Qualidade durante o jogo | Perfis e ajuste antes do lançamento; controle de energia ao vivo | Troca de qualidade suportada em tempo real sem exigir reiniciar a partida, com feedback correto e sem prometer aplicação de um INI que o emulador ignora. |
| L4/R4/L5 e dez saves | Código e registros históricos de L4/save, R4/último, L5/histórico; proteção recente verificada | Revalidar no perfil efetivamente carregado pelo Steam: dez estados cronológicos, setas/A, R4 no Save1, prevenção de seleção/salvamento acidental e preservação de todos os estados. |
| Engasgo ao salvar/recuperação de progresso | Proteções de arquivo e histórico existentes | Medir atraso do save state, avaliar estabilidade e comprovar recuperação de versões anteriores; não há prova de recuperação das perdas antigas. |
| Detonado PT-BR offline | Auditoria histórica registra 20 missões DMC3 em português e cache offline | Revalidar navegação no painel sem internet e identificação correta da missão/cena, sem voltar ao inglês ou mostrar conteúdo errado. |
| RetroAchievements | Backend e tela de usuário/Web API Key encontrados no plugin | Credencial do Commander e consulta de progresso real no painel; não foi comprovado esse aceite. Na última listagem de segredos do Commander não apareceu a chave correspondente. |
| Cheats no painel | Parser/serializador `.cht` e base relacionada existem | Interface própria de seleção, backend de ativação e aplicação real da edição correta durante a partida. Não foi encontrada a entrega do `CheatsPanel.tsx` solicitado nem comprovado um fluxo equivalente no painel atual. |
| Unity: atlas e UI | Motor lê e regrava textos/estruturas Unity | Injetor de glifos/atlas PT-BR e ajuste visual completo. O motor atual ainda avisa que fontes TextMeshPro podem precisar ser refeitas e que ele não faz essa reconstrução. O arquivo solicitado `unity_font_injector.py` não existe na árvore examinada. |
| Castlevania | Adaptadores específicos de Symphony of the Night de PS1 existem | Confirmar edição/engine e validar fonte, acentos, largura, integridade e restauração na versão correta; não aplicar receita Unity ao jogo de PS1. |
| Demais formatos de tradução | Motores e testes para diversos formatos estão no projeto | Validar extração, tradução, reinserção, referências, integridade e resultado visual para cada engine/edição. A existência de um parser não prova tradução integral de todos os jogos. |
| Música e cutscenes | Módulos de áudio e Spotify existem | Detecção confiável de cutscene e pausa/retomada automática preservando o áudio do jogo; nenhum aceite recente demonstra isso. |
| Modo Família/P2P | Catálogo, pareamento, aquisição e sincronização têm código | Teste real entre dois dispositivos, em redes distintas, com catálogo, download, tradução e conflitos de save. |
| Streaming PC/Deck/TV | Integrações Sunshine/Moonlight, WoL e Tailscale no projeto | Provar ciclo de acordar, conectar, jogar e recuperar falhas em cada cenário de rede, inclusive TV. |
| HomeLab pessoal | Stack real validada no laboratório | Inventário do Debian pessoal, implantação, volumes/permissões, segredos/1Password, backups e restauração completa. |
| ROMarr | Entrada condicional no Compose e adaptadores próprios de aquisição | Definir e validar serviço/imagem compatível ou fechar equivalência funcional do adaptador. |
| Quick Resume/Fast Exit/Rest Mode | Módulos de continuar e repouso existem | Critérios do documento: múltiplos jogos, tempo de retomada, segurança de save e comportamento real durante suspensão. Não foi demonstrada a promessa de três jogos retomados em menos de dois segundos. |
| Rewind, HDMI-CEC, HD Rumble | Itens documentados; componentes relacionados de emulação | Implementação e aceite correspondente a cada requisito, incluindo regressões de desempenho e resposta real. Sem comprovação de entrega completa. |
| Texturas HD, dublagem, shaders e netplay | Módulos relacionados existentes | Receitas e testes de ponta a ponta por emulador/jogo, preservação de originais e validação visual/sonora/rede. |
| Segurança e recuperação | Locks, fila, hashes, checkpoints e algumas correções comprovadas | Ensaios completos de disco cheio, permissões, interrupção, rollback, corrupção, concorrência e restauração em cada subsistema. |
| Auditoria global/documentação | Inventário e matriz criados | Reconciliar cada requisito com commit, ambiente, teste e implantação; atualizar documentos contraditórios e fechar critérios de aceite. |

## 5. Testes e significado dos números

| Versão/escopo | Ambiente | Resultado registrado |
|---|---|---|
| Base `b8c48d3` | Windows | 1.051 aprovados, 3 pulados |
| Proteção de saves | Deck físico, perfil descartável | 24 aprovados |
| Aquisição por nome | Windows | 1.080 aprovados, 3 pulados |
| Branch de desenvolvimento com correções | VM, isolamento real | 1.090 aprovados, 5 pulados |
| Cópia exata da instalação física com reparo | VM | 1.048 aprovados, 5 pulados |
| Release corretiva `61158ce` | VM | 1.050 aprovados, 5 pulados |
| Proteção do executor | Deck físico | 1 teste real aprovado |
| Aquisição/Prowlarr/retomada focados | Windows | 77 aprovados |
| Provisionamento Ansible | WSL/Docker | Syntax-check/check/lint aprovados; segunda aplicação sem mudanças |

Esses totais são de versões e escopos diferentes. Não devem ser somados nem convertidos em percentual de conclusão. Testes pulados não contam como aprovados. A suíte inclui testes de unidade com dependências substituídas; as linhas explicitamente descritas como ensaio real são as que exercitaram serviços/processos/rede reais.

## 6. Falhas do trabalho e limitações que precisam ficar registradas

1. A validação anterior deixou passar um teste que escrevia na instalação real. A atualização terminou com um launcher inválido, quebrando a abertura do DMC3. Esse foi um defeito concreto do processo e do código.
2. O fluxo por nome avançou no laboratório, mas não chegou ao bot físico. Não deveria ser apresentado como entregue ao usuário.
3. Parte da documentação ficou atrás das mudanças. Por exemplo, uma auditoria antiga dizia que não havia VM utilizável; posteriormente foi levantada e usada uma VM SteamOS real. Outra dizia que controles iniciais não estavam preparados; depois foi adicionado código, mas sem aceite físico dos três emuladores.
4. A matriz contém 518 linhas principais: uma `IN_PROGRESS` e 517 `PENDING`, além de 11 requisitos de continuidade. Isso reflete falta de reconciliação dos estados, não 517 defeitos comprovados e nem ausência de todo o código.
5. A confirmação recente de abertura do DMC3 não resolveu por si só desempenho, histórico de saves, detonado ou todas as reclamações anteriores.
6. Credenciais Telegram já existem no Deck. A falta dessas credenciais na VM não deve ser apresentada como se o proprietário precisasse configurar tudo novamente.
7. Não foi medido um percentual confiável de conclusão. Não há base para afirmar “100% pronto”, “100% auditado” ou “profissional sem pendências”.

## 7. Ordem técnica pendente, caso o proprietário decida retomar

Esta seção é registro de continuidade, não autorização para executar durante a pausa.

1. Concluir o caminho de busca real que falha no Prowlarr e definir o fallback.
2. Implementar o comportamento solicitado no último exemplo: “god” mostra opções de plataformas diferentes; “god PSP” restringe; a escolha inicia o download correspondente.
3. Reunir uma release de aquisição que preserve a correção `61158ce` e não leve mudanças independentes sem validação.
4. Validar instalação/reinstalação na VM, depois implantar no Deck com checkpoint e sem interromper partidas.
5. Demonstrar a cadeia pelo Telegram real até biblioteca autenticada, abertura e tratamento de tradução quando suportada.
6. Reproduzir e medir os problemas de gameplay, save states, controle e qualidade ao vivo.
7. Fechar os casos de Wii/EmuDeck, detonado, RetroAchievements, cheats e fontes.
8. Completar HomeLab pessoal, P2P, streaming e os recursos de console, atualizando cada aceite individualmente.

## 8. Código, checkpoints e evidências

- Repositório de desenvolvimento: `C:/Users/guilh/Documents/Codex/2026-11-17/in/work/deck-commander`.
- Worktree da correção publicada: `C:/Users/guilh/Documents/Codex/2026-11-17/in/work/deck-commander-launch-hotfix`.
- Release pública do reparo: [commit 61158ce](https://github.com/guilherme-lacerda-tech/deck-commander/commit/61158ce).
- Checkpoint físico anterior à proteção de saves: `~/.local/state/deck-commander/code-checkpoints/save-sync-blyremwr`.
- Checkpoint físico do DMC3: `~/.local/state/deck-commander/code-checkpoints/dmc-launch-repair-loaflu21`. Contém código/configuração anteriores e cópias de progresso; não foi usado para sobrescrever os saves atuais.
- Evidências e logs: [TEST_EVIDENCE.md](TEST_EVIDENCE.md), `outputs/dmc-regression/`, `outputs/download-recovery-vm-result.json`, `outputs/name-download-vm-result.json`, `outputs/vm-doom.png` e `outputs/vm-super-tilt.png`.
- Matriz completa de requisitos: [MASTER_REQUIREMENTS.md](MASTER_REQUIREMENTS.md). Seus estados precisam da reconciliação descrita acima.
- Estado de continuidade: [EXECUTION_STATE.json](EXECUTION_STATE.json), agora marcado como pausado por ordem do proprietário.

Nenhuma senha, token ou chave foi incluída neste relatório.
