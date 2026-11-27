# Continuidade do Deck Commander

A retomada agendada ocorre a cada 30 minutos nesta conversa. A fonte de estado é `docs/execution/EXECUTION_STATE.json`. Consulte também a matriz e as evidências em `docs/execution/`.

1. Confira a branch, o último commit, o índice e as alterações locais. Preserve o trabalho iniciado.
2. Confira se a rodada anterior deixou testes, instalações ou outras operações em execução. Recolha o resultado disponível antes de repetir a operação.
3. Retome o requisito em andamento. Se depender exclusivamente do Steam Deck físico, registre a evidência que falta e avance para o próximo requisito executável no PC, na VM SteamOS ou no HomeLab local. Enquanto o proprietário leva o Deck ao trabalho, mantenha as conexões e implantações restritas a esses ambientes de teste.
4. Após cada mudança relevante, registre o comando, ambiente e resultado em TEST_EVIDENCE.md. Atualize EXECUTION_STATE.json com arquivos pendentes, etapa concluída, falha reproduzível ou próxima ação concreta.
5. Preserve saves, perfis manuais e credenciais. Execute ensaios de instalação e recuperação em cópias descartáveis. Só atribua validação física a uma medição feita no dispositivo correspondente.
