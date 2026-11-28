# Continuidade do Deck Commander

> **REASSUMIDO POR CLAUDE EM 28/11/2026** (autorização do proprietário). A automação Codex `retomar-o-deck-commander` continua PAUSED e NÃO deve ser reativada (dois agentes no mesmo código). Estado atual: `docs/execution/RELATORIO_REASSUNCAO_2026-11-28.md` e `docs/execution/EXECUTION_STATE.json`. Pausa do Codex: `docs/execution/RELATORIO_PARALISACAO_2026-11-28.md`.

A cada 30 minutos, releia as 24 seções da ordem de execução anexada a esta conversa. Uma cópia integral está em `docs/execution/ORDEM_DE_EXECUCAO.md`. Compare os critérios da ordem e do Documento Mestre com a matriz, as evidências e o código. Use `docs/execution/EXECUTION_STATE.json` para localizar o ponto de retomada e execute a próxima pendência da fila na mesma rodada.

A regressão de abertura do DMC3 foi corrigida no Deck em 27/11/2026 e publicada na release61158ce. O jogo abriu pelo Steam e os22 hashes de saves/cartões de memória foram preservados. Não repita abertura ou fechamento do jogo para esse reparo concluído. Retome P0-NOME no PC/VM, preservando a proteção do atualizador e as alterações locais em andamento.

A decisão anterior do usuário de 27/11/2026 torna obrigatória a prioridade P0-NOME. O usuário envia somente o nome do jogo, escolhe a plataforma quando necessário e o Commander pesquisa, baixa, verifica, importa e disponibiliza automaticamente. O usuário consegue iniciar esse fluxo sem enviar torrent ou link. Instale e valide na VM SteamOS com downloads reais de fontes autorizadas. As demais funcionalidades são secundárias até os critérios desse fluxo serem demonstrados, ressalvadas suas dependências e a preservação de dados.

1. Confira a branch, o último commit, o índice e as alterações locais. Preserve o trabalho iniciado.
2. Confira se a rodada anterior deixou testes, instalações ou outras operações em execução. Recolha o resultado disponível antes de repetir a operação.
3. Retome o requisito em andamento. Se depender exclusivamente do Steam Deck físico, registre a evidência que falta e avance para o próximo requisito executável no PC, na VM SteamOS ou no HomeLab local. O proprietário reconectou o Deck e autorizou corrigir a regressão de lançamento. Use o dispositivo para esse reparo com checkpoint e preservação dos dados; mantenha ensaios independentes no PC/VM.
4. Após cada mudança relevante, registre o comando, ambiente e resultado em TEST_EVIDENCE.md. Atualize EXECUTION_STATE.json com arquivos pendentes, etapa concluída, falha reproduzível ou próxima ação concreta.
5. Preserve saves, perfis manuais e credenciais. Execute ensaios de instalação e recuperação em cópias descartáveis. Só atribua validação física a uma medição feita no dispositivo correspondente.
