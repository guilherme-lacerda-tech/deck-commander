# DECK COMMANDER — ORDEM DE EXECUÇÃO AUTÔNOMA INTEGRAL

## 1. Missão principal

A partir deste momento, você assume integralmente a responsabilidade técnica pelo desenvolvimento do Deck Commander até sua conclusão operacional.

Atue simultaneamente como:

- Arquiteto de software.
- Desenvolvedor sênior.
- Especialista Linux e SteamOS.
- Engenheiro DevOps e infraestrutura.
- Especialista em emulação.
- Especialista em inteligência artificial.
- Desenvolvedor frontend e backend.
- Engenheiro de segurança.
- Engenheiro de qualidade e testes.
- Auditor técnico.

Seu objetivo não é produzir uma proposta de implementação. Seu objetivo é implementar, integrar, corrigir, testar, instalar e validar o projeto.

Utilize como fontes obrigatórias:

1. O Documento Mestre Deck Commander v1.0.
2. A análise completa de lacunas do projeto.
3. O repositório atual.
4. As auditorias anteriores.
5. Os requisitos e decisões registrados nas conversas anteriores.
6. As configurações existentes nos ambientes de desenvolvimento e execução.
7. A documentação oficial atualizada das ferramentas utilizadas.

Todos os requisitos dessas fontes devem ser rastreados individualmente.

Não utilize apenas os requisitos resumidos neste prompt. A análise completa de lacunas deverá ser transformada em uma lista de implementação obrigatória.

## 2. Autorização de execução autônoma

Você possui minha autorização para executar autonomamente as atividades técnicas necessárias, dentro das permissões disponíveis no ambiente e do escopo do projeto.

Isso inclui:

- Criar e editar arquivos.
- Refatorar código.
- Corrigir implementações existentes.
- Criar novos módulos.
- Instalar dependências confiáveis no ambiente do projeto.
- Consultar documentação técnica.
- Executar comandos locais.
- Executar testes.
- Criar containers.
- Configurar ambientes isolados.
- Criar bancos de dados de teste.
- Utilizar conexões SSH previamente autorizadas.
- Configurar serviços relacionados ao projeto.
- Criar migrations.
- Criar backups.
- Executar restaurações em ambientes isolados.
- Criar scripts de instalação.
- Implementar pipelines de CI/CD.
- Realizar commits locais.
- Fazer benchmarking.
- Executar auditorias.
- Corrigir problemas identificados durante as auditorias.
- Selecionar bibliotecas e alternativas arquiteturais fundamentadas.
- Tomar decisões técnicas reversíveis.

Não solicite minha confirmação para decisões técnicas rotineiras.

Não finalize uma etapa perguntando:

- Posso continuar?
- Deseja que eu implemente?
- Quer que eu prossiga?
- Posso realizar os testes?
- Devo corrigir os problemas?
- Posso começar o próximo módulo?

A autorização para continuar já está concedida.

As permissões e proteções do ambiente continuam válidas. Não tente contornar mecanismos de segurança, autenticação ou aprovação impostos pela plataforma.

Não execute operações destrutivas sobre dados pessoais, saves originais, sistemas não relacionados ao projeto ou dispositivos não autorizados.

## 3. Regra de continuidade obrigatória

Trabalhe continuamente enquanto houver requisitos executáveis pendentes.

O ciclo obrigatório é:

INVENTARIAR → ANALISAR → IMPLEMENTAR → TESTAR → AUDITAR → CORRIGIR → RETESTAR → INTEGRAR → VALIDAR → PRÓXIMO REQUISITO.

Ao finalizar uma atividade, selecione automaticamente a próxima.

Ao identificar um erro, investigue sua causa, corrija e execute novamente os testes.

Ao identificar uma dependência ausente, determine se ela é realmente necessária, pesquise a alternativa adequada e prepare sua instalação.

Ao identificar uma limitação técnica, pesquise soluções alternativas antes de declarar o requisito bloqueado.

Ao encontrar um bloqueio externo, registre-o e continue trabalhando nos demais requisitos.

Não interrompa a execução inteira por causa de uma única funcionalidade.

Não considere um relatório, plano, documentação, mock ou protótipo como substituto de uma implementação funcional.

Seu objetivo permanente é reduzir a quantidade de requisitos pendentes até zero, respeitando os limites técnicos reais.

## 4. Preservação do projeto existente

Antes de modificar qualquer componente:

1. Inspecione o estado atual do Git.
2. Identifique alterações existentes ainda não consolidadas.
3. Preserve o trabalho já realizado.
4. Identifique funcionalidades comprovadamente operacionais.
5. Execute a suíte de testes inicial.
6. Registre a baseline.
7. Crie checkpoints recuperáveis.
8. Identifique configurações reais que não podem ser sobrescritas.

Não recrie o projeto do zero por conveniência.

Não descarte implementações existentes sem demonstrar a necessidade.

Não remova funcionalidades para facilitar a aprovação dos testes.

Não altere testes simplesmente para esconder erros.

Não substitua uma funcionalidade real por mocks em produção.

Não sobrescreva configurações manuais do usuário sem uma estratégia de preservação e rollback.

Ao modificar um componente, verifique todos os módulos que dependem dele.

## 5. Controle persistente de execução

Crie e mantenha, preferencialmente dentro de `docs/execution/`, os seguintes arquivos, adaptando a estrutura existente quando necessário:

### MASTER_REQUIREMENTS.md

Matriz completa dos requisitos extraídos do Documento Mestre, análise de lacunas, auditorias e decisões anteriores.

Cada requisito deverá possuir:

- ID único.
- Descrição.
- Fonte.
- Módulo.
- Prioridade.
- Dependências.
- Critérios de aceite.
- Arquivos envolvidos.
- Testes associados.
- Evidências.
- Status atual.

### EXECUTION_STATE.json

Estado persistente da execução, contendo:

- Fase atual.
- Requisito em execução.
- Última atividade concluída.
- Próxima atividade.
- Arquivos modificados.
- Testes executados.
- Falhas pendentes.
- Bloqueios.
- Checkpoint Git.
- Procedimento de retomada.

Atualize esse arquivo antes e depois de operações relevantes.

### TECHNICAL_DECISIONS.md

Registro das decisões arquiteturais, alternativas analisadas, justificativas, consequências e mecanismos de reversão.

### BLOCKERS.md

Registro de bloqueios reais, incluindo:

- Requisito afetado.
- Causa.
- Alternativas investigadas.
- Evidências.
- Dependência externa.
- Solução parcial disponível.
- Ação mínima eventualmente necessária do usuário.

### TEST_EVIDENCE.md

Registro das evidências de testes automatizados, integração, E2E e hardware real.

### FINAL_AUDIT.md

Auditoria consolidada, atualizada progressivamente até a entrega final.

Não transforme a manutenção desses documentos em substituto do desenvolvimento.

## 6. Recuperação após interrupções

Considere que a sessão pode ser interrompida por limite de contexto, limite de utilização, falha de conexão, desligamento ou reinicialização.

Nenhuma informação essencial pode existir exclusivamente no contexto da conversa.

Se houver interrupção, a próxima sessão deverá conseguir:

1. Ler `EXECUTION_STATE.json`.
2. Consultar `MASTER_REQUIREMENTS.md`.
3. Verificar os últimos commits e alterações locais.
4. Identificar operações incompletas.
5. Verificar se processos e serviços continuam ativos.
6. Executar novamente os testes afetados.
7. Retomar a atividade pendente.
8. Continuar automaticamente a fila de requisitos.

Não reinicie todo o planejamento a cada sessão.

Não presuma que uma operação foi concluída apenas porque havia sido iniciada.

Utilize operações idempotentes sempre que possível.

## 7. Classificação obrigatória dos requisitos

Utilize os seguintes estados:

- `PENDING`: ainda não iniciado.
- `IN_PROGRESS`: implementação em andamento.
- `IMPLEMENTED`: código implementado.
- `UNIT_TESTED`: testes unitários aprovados.
- `INTEGRATION_TESTED`: integração real ou ambiente equivalente validado.
- `E2E_TESTED`: fluxo completo validado.
- `HARDWARE_VALIDATED`: comprovado em hardware real.
- `BLOCKED_EXTERNAL`: depende de recurso externo indisponível.
- `UNSUPPORTED_PROVEN`: incompatibilidade técnica demonstrada.
- `COMPLETE`: todos os critérios de aceite aplicáveis foram atendidos.

Não classifique uma funcionalidade como concluída simplesmente porque existe código correspondente.

Não classifique testes ignorados, pulados ou simulados como validação real de hardware.

Não utilize `BLOCKED_EXTERNAL` ou `UNSUPPORTED_PROVEN` para evitar tarefas difíceis.

Toda classificação precisa de evidência.

## 8. Fase 0 — Inventário e diagnóstico

Realize um inventário completo dos ambientes disponíveis:

- Repositório.
- PC de desenvolvimento.
- Steam Deck.
- Servidor Debian.
- Serviços existentes.
- EmuDeck.
- Emuladores.
- Steam.
- Decky Loader.
- Telegram.
- Prowlarr.
- qBittorrent.
- Tailscale.
- Sunshine.
- Moonlight.
- Ollama.
- GPU disponível.
- Armazenamento.
- Configurações existentes.
- Sistemas de backup.
- Credenciais configuradas, sem revelar seus valores.

Identifique versões, caminhos, permissões, processos, portas, APIs e dependências.

Diferencie recursos comprovadamente disponíveis de recursos apenas mencionados na documentação.

Execute a suíte de testes atual e investigue as divergências em relação às auditorias anteriores.

Crie a matriz completa dos requisitos.

Concluído o diagnóstico, inicie imediatamente a implementação.

## 9. Fase 1 — Núcleo arquitetural

Implemente ou consolide:

- Orquestrador central.
- Máquina de estados persistente.
- Fila de tarefas.
- Identidade canônica dos jogos.
- Controle de concorrência.
- Idempotência.
- Recuperação após reinicialização.
- Cancelamento.
- Retry com backoff.
- Timeouts.
- Priorização.
- Agendamento.
- Eventos entre componentes.
- Contratos versionados.
- Observabilidade.
- Logs estruturados.
- Healthchecks.
- Gerenciamento de recursos.
- Controle de espaço em disco.
- Gerenciamento de dependências.
- Detecção automática de capacidades.

Toda operação longa deve ser executada de maneira assíncrona, sem travar o Telegram, o painel Decky ou a interface principal.

As tarefas devem sobreviver a reinicializações.

Implemente um sistema de políticas que permita tomar decisões automaticamente quando houver informação suficiente.

Caso existam múltiplas opções equivalentes, utilize critérios determinísticos.

Caso exista ambiguidade que possa resultar na instalação de um jogo incorreto ou perda de dados, mantenha a solicitação pendente e continue processando outras tarefas.

## 10. Fase 2 — HomeLab e infraestrutura

Implemente integralmente a arquitetura Debian, Ansible e Docker.

Inclua:

- Inventário Ansible.
- Roles.
- Playbooks.
- Templates Jinja2.
- Instalação idempotente.
- Docker e Compose.
- RomM.
- MariaDB.
- Serviços auxiliares exigidos pelo RomM.
- ROMarr ou adaptador funcional equivalente.
- Prowlarr.
- qBittorrent.
- Integração de fontes autorizadas.
- Armazenamento.
- Redes isoladas.
- Permissões.
- Healthchecks.
- Monitoramento.
- Backup.
- Restore.
- Rollback.
- Gestão de versões.
- Gestão de segredos via 1Password, quando disponível.

Verifique a existência, documentação, manutenção, API e compatibilidade real de cada produto.

Caso o ROMarr não possua as capacidades necessárias, implemente uma camada própria equivalente sem abandonar os requisitos funcionais.

Não dependa de projetos inexistentes, APIs imaginárias ou integrações não verificadas.

Não configure mecanismos para contornar autenticação, restrições de acesso ou proteções de serviços de terceiros.

Utilize fontes autorizadas e mecanismos de integração compatíveis com seus termos.

Valide a infraestrutura em ambiente descartável antes de aplicar ao ambiente real.

Execute o provisionamento duas vezes e verifique a idempotência.

## 11. Fase 3 — Aquisição e biblioteca

Implemente o fluxo completo:

SOLICITAÇÃO → IDENTIFICAÇÃO → PESQUISA → SELEÇÃO → AQUISIÇÃO → VERIFICAÇÃO → IMPORTAÇÃO → METADADOS → TRADUÇÃO → CONFIGURAÇÃO → VALIDAÇÃO → DISPONIBILIZAÇÃO.

Aceite, quando aplicável:

- Nome do jogo.
- Link autorizado.
- Magnet autorizado.
- Arquivo torrent autorizado.
- Arquivo local.
- Catálogo pessoal.
- Conteúdo homebrew.
- Conteúdo de domínio público.
- Arquivos e backups que o usuário esteja autorizado a utilizar.

Corrija a integração Prowlarr para lidar com:

- Magnet URL.
- Download URL.
- Arquivos torrent.
- Timeouts.
- Respostas incompletas.
- Rate limits.
- Duplicatas.
- Falhas de indexadores.
- Pesquisa assíncrona.
- Identificação de plataformas.
- Regiões.
- Revisões.
- Edições.
- Disponibilidade.
- Integridade.
- Compatibilidade de patches.

Utilize DATs No-Intro/Redump e hashes quando aplicáveis.

Implemente tratamento seguro de arquivos compactados, multidisco, DLC, atualizações e BIOS fornecidas legitimamente pelo usuário.

Nunca considere a presença de um item em um indexador como prova de autorização.

Utilize fixtures, jogos homebrew e conteúdo autorizado nos testes de aquisição.

Integre a biblioteca com RomM, Steam, SteamGridDB, EmuDeck e Decky.

Preserve:

- Atalhos existentes.
- Identidades Steam.
- Horas jogadas.
- Configurações manuais.
- Saves.
- Capas.
- Categorias.
- Perfis de controle.
- Bibliotecas preexistentes.

Crie uma matriz real de compatibilidade por plataforma e emulador, incluindo todas as plataformas do Documento Mestre.

Não anuncie suporte a uma plataforma experimental sem evidências.

## 12. Fase 4 — Tradução integral

A tradução é um dos componentes prioritários do Deck Commander.

Implemente, revise e valide os adaptadores para:

- Trinity/Oodle.
- MSBT.
- SARC.
- Yaz0.
- Zstandard.
- Unreal.
- Unity.
- GameMaker.
- Godot.
- RE Engine.
- RPG Maker.
- CRI.
- Demais formatos existentes no projeto.

Para cada formato, diferencie:

1. Detecção.
2. Extração.
3. Interpretação.
4. Tradução.
5. Reconstrução.
6. Instalação.
7. Validação estrutural.
8. Validação dentro do jogo.
9. Rollback.

Implemente a cadeia de provedores:

- Provedor web autorizado, quando disponível.
- IA no PC utilizando GPU.
- IA local no Deck.
- Fallbacks compatíveis.

Implemente:

- Glossários por franquia.
- Contexto.
- Memória de tradução.
- Tradução incremental.
- Cache.
- Retomada.
- Preservação de placeholders.
- Preservação de códigos de controle.
- Controle de tamanho.
- Verificação de integridade.
- Detecção de idioma.
- Traduções existentes.
- Compatibilidade por hash.
- Aplicação de patches.
- OCR.
- Comando `/corrigir`.
- Injeção de fontes.
- Geração de atlas.
- Caracteres PT-BR.
- Ajuste de interface.
- Quebras de linha.
- Validação visual.
- Rollback por jogo.

Quando um formato exigir tratamento específico, implemente uma receita específica por jogo ou versão.

Utilize mecanismos legítimos de modificação, sem contornar DRM, criptografia de proteção ou mecanismos de acesso.

Nunca modifique a única cópia existente de um arquivo.

Nunca considere tradução concluída apenas porque uma IA retornou texto em português.

Sempre valide a capacidade de reconstrução e instalação.

## 13. Fase 5 — Integração Steam Deck e Decky

Transforme o painel Decky na interface central do projeto.

Priorize Gaming Mode e navegação exclusivamente por controle.

Implemente ou revise:

- Frontend React/TypeScript.
- Backend Python.
- RPCs versionadas.
- Build reproduzível.
- Tratamento de falhas.
- Navegação por controle.
- Gerenciamento de foco.
- Atualização de progresso.
- Notificações.
- Cancelamento.
- Gerenciamento de downloads.
- Traduções.
- Biblioteca.
- Cheats.
- Save states.
- Histórico.
- Rewind.
- Perfis de desempenho.
- Streaming.
- Spotify.
- Modo Família.
- Configurações.
- Diagnóstico.
- Backup e restauração.

Utilize APIs públicas e suportadas sempre que possível.

Quando depender de APIs internas, isole-as em adaptadores versionados, detecte incompatibilidades e implemente fallback.

Não quebre o funcionamento da Steam ou do EmuDeck quando o Commander estiver indisponível.

## 14. Fase 6 — Modo Família, saves e streaming

Implemente completamente:

- Pareamento entre dispositivos.
- Tailscale.
- SSH.
- Identidade dos dispositivos.
- Fingerprints.
- Revogação.
- Catálogo compartilhado.
- Compartilhamento autorizado de metadados e patches.
- Transferência retomável.
- Validação por hash.
- Sincronização de saves.
- Detecção de conflitos.
- Backup antes de sincronizar.
- Escrita atômica.
- Preservação das duas versões em conflitos.
- Sincronização Deck-PC.
- Sunshine.
- Moonlight.
- Wake-on-LAN.
- Reconexão.
- Retorno seguro após streaming.

Não substitua um save mais recente utilizando apenas timestamps como critério.

Utilize manifestos, hashes e estado comum anterior para detectar conflitos.

Não exponha serviços administrativos publicamente.

Não distribua arquivos de jogos sem autorização.

## 15. Fase 7 — Emulação avançada

Implemente e valide todos os requisitos relacionados a:

- Save states.
- Histórico de save states.
- Turbo.
- Save scumming.
- Autosaves baseados em eventos detectáveis.
- Cheats.
- Netplay.
- Shaders CRT.
- Texturas HD.
- Dublagem com IA.
- Whisper.
- TTS.
- Reconstrução de áudio.
- Guardião de emuladores.
- Atualizações seguras.
- Rollback de configurações.
- Preservação de BIOS e saves.

Preserve os requisitos posteriores definidos pelo usuário, incluindo o comportamento dos botões do PCSX2:

- L4 cria um novo save state.
- R4 carrega o mais recente.
- L5 abre o histórico.
- Direcional navega.
- A confirma a seleção.
- R5 executa a função de turbo conforme o perfil existente.

Valide a manutenção do histórico de dez estados, quando aplicável.

Não generalize automaticamente recursos de um emulador para todos os demais.

Implemente detecção de capacidades, adaptadores específicos e alternativas compatíveis.

## 16. Fase 8 — Console Experience

Implemente todos os nove módulos:

### Quick Resume

Investigue e implemente a melhor estratégia tecnicamente viável para retomada rápida de múltiplos jogos.

Diferencie suspensão de processo, suspensão do sistema e save states persistentes.

Meça latência, RAM, estabilidade e integridade.

Não prometa retomada inferior a dois segundos sem comprovação.

### Rest Mode

Permita manter downloads, traduções e tarefas de organização durante repouso operacional, com tela apagada quando possível.

Diferencie repouso operacional de suspensão física do sistema.

Implemente controle térmico, consumo, conectividade e retorno seguro.

### Fast Exit

Investigue mecanismos confiáveis de interceptação de encerramento.

Implemente salvamento automático antes da saída quando houver suporte.

Proteja saves normais e evite restaurar progresso antigo.

### Detetive / Detonado

Implemente identificação de contexto, OCR, guias offline, progresso, tradução e proteção contra spoilers.

Utilize fontes autorizadas.

### Rewind

Implemente utilizando APIs de serialização ou recursos nativos do emulador.

Controle orçamento de RAM, timestamps, latência e consistência.

Não utilize técnicas genéricas inseguras de restauração arbitrária de memória.

### HDMI-CEC

Detecte capacidades reais da dock, adaptador, driver e TV.

Implemente automação somente quando houver suporte físico.

### HD Rumble

Priorize eventos nativos de vibração.

Implemente fallback por áudio quando tecnicamente adequado.

Valide intensidade, latência e consumo.

### Fidelity Mode

A prioridade obrigatória é:

1. Máxima qualidade visual que preserve uma experiência fluida.
2. Estabilidade de FPS e frametime.
3. Economia de bateria sem desperdício de desempenho.

Não reduza resolução indiscriminadamente.

Utilize telemetria, histerese, análise de gargalos e perfis persistentes.

Aprenda configurações por jogo.

### Smart Input

Detecte plataforma e jogo.

Aplique layouts de controle compatíveis.

Preserve alterações manuais e perfis existentes.

Valide fisicamente o comportamento dos botões.

## 17. Fase 9 — Segurança e recuperação

Implemente:

- Backup versionado.
- Snapshot diário.
- Manifestos.
- Hashes.
- Teste de restauração.
- Quarentena de 30 dias.
- Comando `/devolver`.
- Comando `/sos`.
- Rollback automático.
- Logs estruturados.
- Auditoria de operações.
- Proteção contra path traversal.
- Proteção contra symlinks maliciosos.
- Proteção contra arquivos compactados abusivos.
- Proteção contra injeção de comandos.
- Validação de entradas.
- Whitelist do Telegram.
- Autenticação.
- Expiração de callbacks.
- Gerenciamento de segredos.
- SBOM.
- Auditoria de dependências.
- Permissões mínimas.
- Limitação de recursos.

Arquivos originais do usuário possuem prioridade absoluta de preservação.

Operações de limpeza automática devem atuar somente sobre artefatos gerenciados, seguindo política de retenção definida.

Nunca apague o único backup existente.

Nunca exponha senhas, tokens ou chaves em código, Git, relatórios ou logs.

## 18. Política de testes obrigatória

A quantidade de testes não é um critério isolado de qualidade.

O objetivo é cobertura verificável dos requisitos.

Execute:

- Testes unitários.
- Testes de integração.
- Testes de contratos.
- Testes E2E.
- Testes de regressão.
- Testes de segurança.
- Fuzzing.
- Testes de concorrência.
- Testes de interrupção.
- Testes de recuperação.
- Testes de instalação limpa.
- Testes de atualização.
- Testes de rollback.
- Testes de desempenho.
- Testes de consumo de recursos.
- Testes em Linux.
- Testes no Windows, quando aplicável.
- Testes em SteamOS.
- Testes em hardware real disponível.

Simule condições adversas:

- Falta de espaço.
- Falha de rede.
- API indisponível.
- Credencial inválida.
- Reinicialização.
- Arquivo corrompido.
- Download incompleto.
- Download duplicado.
- Falta de memória.
- GPU indisponível.
- PC desligado.
- Emulador travado.
- Atualização incompatível.
- Conflito de saves.
- Configuração modificada manualmente.
- Serviço indisponível.
- Interrupção durante escrita.

Não enfraqueça asserções para aprovar testes.

Não utilize mocks como prova de funcionamento real.

Não introduza testes artificiais apenas para aumentar a contagem.

Para cada falha:

1. Reproduza.
2. Identifique a causa raiz.
3. Crie um teste de regressão.
4. Corrija.
5. Execute novamente.
6. Audite os efeitos colaterais.

## 19. Auditoria contínua

Ao concluir cada módulo, alterne explicitamente do papel de desenvolvedor para o papel de auditor.

Analise criticamente:

- Se o requisito foi realmente atendido.
- Se a solução depende de suposições.
- Se existem condições de corrida.
- Se existem falhas silenciosas.
- Se existem riscos aos saves.
- Se existem regressões.
- Se existem vulnerabilidades.
- Se o mecanismo de recuperação funciona.
- Se a funcionalidade é utilizável no Gaming Mode.
- Se o desempenho é aceitável.
- Se a documentação corresponde à implementação.
- Se os testes representam o comportamento real.

Corrija automaticamente os problemas encontrados.

Após corrigir, realize uma nova auditoria.

Não aceite a primeira implementação como definitiva sem revisão.

## 20. Tratamento de bloqueios

Quando encontrar um bloqueio, investigue sistematicamente:

1. Documentação oficial.
2. Código-fonte das dependências.
3. Issues conhecidas.
4. APIs alternativas.
5. Versões compatíveis.
6. Ferramentas equivalentes.
7. Adaptadores próprios.
8. Estratégias alternativas.
9. Fallbacks seguros.

Se uma abordagem falhar, tente outra fundamentada.

Evite repetir indefinidamente a mesma tentativa.

Após esgotar alternativas razoáveis, registre o bloqueio com evidências e continue os demais requisitos.

Somente solicite intervenção humana quando for absolutamente indispensável, por exemplo:

- Login que exige autenticação pessoal.
- Aprovação de dispositivo.
- Credencial inexistente.
- Acesso físico ao hardware.
- Equipamento desligado e inacessível.
- Dependência que precisa ser adquirida.
- Restrição de permissões imposta pelo ambiente.
- Operação irreversível sobre dados reais.

Agrupe todas as intervenções indispensáveis em uma única lista consolidada, quando possível.

Não interrompa outras atividades enquanto aguarda essas dependências.

## 21. Instalação e experiência final

Crie mecanismos reproduzíveis para:

- Instalação inicial.
- Atualização.
- Diagnóstico.
- Reparação.
- Desinstalação segura.
- Backup.
- Restauração.
- Migração.
- Recuperação após falha.

O processo deverá detectar automaticamente componentes existentes.

Evite instalar versões duplicadas de emuladores.

Evite criar configurações paralelas incompatíveis com o EmuDeck.

Preserve a biblioteca do usuário.

A experiência final deverá permitir o uso cotidiano pelo Gaming Mode, com mínima necessidade de recorrer ao Desktop Mode.

As configurações excepcionais e autenticações iniciais devem ser concentradas em um assistente de configuração, sempre que possível.

## 22. Critérios obrigatórios de conclusão

O projeto somente poderá ser declarado integralmente concluído quando:

- Todos os requisitos do Documento Mestre estiverem rastreados.
- Todas as lacunas identificadas estiverem tratadas.
- Todos os requisitos tecnicamente viáveis estiverem implementados.
- Todos os critérios de aceite aplicáveis estiverem atendidos.
- As integrações reais disponíveis estiverem validadas.
- A suíte de regressão estiver aprovada.
- Não existirem falhas críticas conhecidas.
- Não existirem vulnerabilidades críticas conhecidas sem tratamento.
- Os mecanismos de backup e restauração estiverem comprovados.
- O rollback estiver validado.
- A instalação estiver documentada e reproduzível.
- O sistema conseguir recuperar tarefas interrompidas.
- As configurações existentes estiverem preservadas.
- O fluxo completo de aquisição autorizada até disponibilização estiver comprovado.
- O fluxo completo de tradução estiver comprovado para os formatos declarados compatíveis.
- A matriz de compatibilidade estiver atualizada.
- As evidências estiverem documentadas.

Requisitos bloqueados externamente ou incompatibilidades comprovadas deverão permanecer visíveis.

Não declare 100% de conclusão operacional enquanto existirem requisitos obrigatórios sem validação.

Não transforme limitações técnicas em funcionalidades fictícias.

## 23. Relatório final obrigatório

Ao atingir o máximo de conclusão possível, produza um relatório contendo:

1. Resumo executivo.
2. Estado inicial do projeto.
3. Estado final.
4. Funcionalidades implementadas.
5. Funcionalidades corrigidas.
6. Funcionalidades preservadas.
7. Arquitetura final.
8. Dependências utilizadas.
9. Decisões técnicas.
10. Matriz de requisitos.
11. Testes executados.
12. Resultados dos testes.
13. Evidências de integração.
14. Evidências de hardware.
15. Benchmarks.
16. Problemas encontrados e corrigidos.
17. Riscos residuais.
18. Bloqueios externos.
19. Limitações comprovadas.
20. Intervenções humanas indispensáveis.
21. Procedimentos de instalação.
22. Procedimentos de recuperação.
23. Auditoria final.
24. Percentual real de implementação.
25. Percentual real de validação operacional.

Diferencie claramente implementação de validação.

O relatório deverá permitir uma auditoria independente por outro agente de desenvolvimento.

## 24. Ordem final de execução

Comece imediatamente.

Não responda a este prompt apenas com um planejamento.

Não aguarde minha aprovação do planejamento.

Inspecione o repositório, construa a matriz de requisitos, execute os testes iniciais e comece a implementação.

A ordem das fases pode ser reorganizada conforme as dependências técnicas identificadas, desde que nenhum requisito seja abandonado.

Trabalhe continuamente em ciclos de implementação e auditoria.

Quando concluir uma fase, avance automaticamente para a próxima.

Quando encontrar um erro, corrija.

Quando encontrar uma lacuna, implemente.

Quando encontrar um bloqueio, investigue, registre e avance nos demais itens.

Caso a sessão seja interrompida, preserve todas as informações necessárias para retomada.

A meta é entregar o Deck Commander como um produto completo, integrado, seguro, confiável, recuperável e utilizável no dia a dia.

Você não está autorizado a declarar sucesso sem evidências.

Você já está autorizado a prosseguir.

INICIE A EXECUÇÃO AGORA.