# Validação física — 18/11/2026

Este registro descreve apenas o que foi executado e observado no Steam Deck real nesta data. Ele não trata alegações de testes anteriores como evidência.

## Versão validada

- Commit: `dcc9d93` — *Block integration test while a game is open*.
- Serviços `deck-commander-bot` e `deck-commander-power`: ativos após a implantação.
- Verificação de atualização: sem versão pendente.

## Verificações aprovadas

1. A revisão ao vivo passou em 16 de 16 verificações: Steam/CDP, Decky/plugin, abas, biblioteca, configurações de emuladores, traduções, arte e serviços.
2. O teste de integração foi executado no próprio Deck, com o jogo fechado. Ele criou um torrent isolado, sincronizou e extraiu uma ROM PS2 sintética, criou o atalho no Steam e confirmou sua visibilidade. Em seguida enviou uma segunda cópia, confirmou o bloqueio de duplicata, removeu o atalho e confirmou a limpeza integral. Resultado do teste: `TUDO OK`.
3. O ambiente final foi conferido sem restos do teste: sem torrent com a etiqueta de teste, sem diretório temporário e sem atalho de teste.
4. A proteção de teste com jogo aberto foi exercitada antes: o E2E recusou iniciar enquanto o PCSX2 estava em execução. O teste agora faz essa checagem antes de criar qualquer artefato.

## Correção aplicada ao Devil May Cry 3

Durante a investigação no Deck, o PCSX2 estava salvando um state comprimido em segundo plano a cada dez minutos. A gravação de um state pode pausar o emulador e explica a travada relatada durante a luta. A versão validada:

- desativou o save periódico durante a partida (`INTERVALO = 0`);
- preserva o ponto de continuar para ações explícitas de descanso/saída, sem tocar no save normal do jogo;
- só carrega automaticamente um ponto de continuar com até cinco minutos; um state antigo permanece guardado, mas não faz o jogo voltar para uma sessão de 20–30 minutos antes;
- mantém o recurso de continuar ligado no Deck, com expiração automática de 300 segundos.

## Limite de evidência

Não foi feita uma nova luta longa de Devil May Cry 3 deliberadamente após a correção, para não alterar o progresso do usuário. Portanto, a correção foi verificada por código, testes automatizados e configuração real, mas a confirmação de desempenho em combate ainda depende da próxima sessão normal do jogo. Caso haja nova travada, devem ser guardados horário e nome do jogo para correlacionar com o log, em vez de assumir que o detector funcionou.

Também não se deve considerar a simulação anterior de VM como substituta desta validação: a VM não concluiu uma sessão SteamOS/EmuDeck reproduzível nesta rodada. O Deck físico foi usado como evidência principal.
