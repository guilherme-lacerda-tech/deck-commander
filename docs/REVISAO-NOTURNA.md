# Revisão noturna — 11/11/2026

Pedido: análise geral de melhorias, compatibilidade, confiabilidade e desempenho, com cada parte revisada várias vezes
e um estudo das falhas antigas para que não se repitam.

## Resumo em 30 segundos

- **Tudo está funcionando e já está no Deck.** No fim da noite passaram **680 testes** no PC e os mesmos 680 no
  próprio Deck, antes da instalação.
- **6 falhas reais encontradas e corrigidas**, cada uma com um teste próprio. Nenhuma era grave a ponto de perder
  dados: todas eram travamentos ou mensagens confusas em situações raras.
- **10 travas automáticas** contra as falhas que já aconteceram no projeto (ver `LICOES.md`). Elas rodam antes de
  toda instalação.
- **Desempenho:** a sincronização de saves caiu de **1 min 55 s para 2,8 s**. As telas do painel abrem em **0,2 s**.
- **Ainda depende de você:** os testes de uso no dia a dia (lista no fim).

## Como foi revisado (as várias passadas)

| Passada | O que olhou | Resultado |
|---|---|---|
| 1. Analisador de código (ruff) | nomes indefinidos, código inalcançável, erros de digitação | 0 erros reais (só importações sobrando, que não fazem mal) |
| 2. Compilação de todos os arquivos | Python, painel (JavaScript) e scripts do PC (PowerShell) | todos válidos |
| 3. Codificação | acentos nos scripts do PC e no envio ao Deck | todos corretos |
| 4. Suíte de testes no PC | 680 testes | todos passam |
| 5. Suíte de testes no Deck | os mesmos 680, na versão que seria instalada | todos passam |
| 6. Painel no Deck de verdade | cada tela chamada e cronometrada | todas respondem "ok" em 0,2 s (Telegram 1,4 s, porque consulta a internet) |
| 7–9. IA local, 3 focos por arquivo | 22 arquivos × erros, robustez, desempenho = **66 revisões** | 744 apontamentos |
| 10. Conferência humana (eu) | cada apontamento grave conferido na linha do código | 6 reais; o resto era alarme falso |
| 11. Serviços no Deck | bot, energia, traduções | nenhum com falha, nenhum erro novo nos registros |

### Sobre os 744 apontamentos da IA local

A IA local (qwen3-coder 30B, no seu PC) leu cada arquivo três vezes: uma procurando erros, outra procurando falta de
robustez e outra procurando lentidão. Ela é **desconfiada demais**. Dos 327 apontamentos marcados como "graves",
quase todos eram coisas como "esta variável pode ser vazia" em lugares onde o código já trata isso, ou "isto pode ser
lento" em arquivos de poucos KB. Por isso **nada** dela entra sem conferência. Conferi todos os graves dos arquivos
que mexem com seus dados (saves, transferência, família, recebimento, painel) e os de "erro" dos demais.

## As 6 falhas reais (corrigidas)

| # | Onde | O que acontecia | Correção |
|---|---|---|---|
| 1 | Sincronizar saves | se o jogo apagasse ou trocasse um save no exato momento da leitura, a sincronização inteira caía | esse arquivo fica para a próxima vez; os outros seguem |
| 2 | Sincronizar saves | jogo fora da biblioteca ou entrada errada mostrava um erro técnico | agora mostra "Não deu para sincronizar: …" |
| 3 | Família: puxar tradução | pacote com **espaço no nome** (ex.: `Patches PT/jogo x.bps`) falhava ao copiar, porque o ssh junta tudo numa linha de comando | cada nome vai protegido entre aspas |
| 4 | Família: aplicar patch | um patch `.bps` com defeito derrubava o laço do bot e o pedido ficava tentando de novo para sempre | o aviso "patch não aplicou" chega no Telegram e o pedido é encerrado |
| 5 | Família: extração | extração do pacote dependia só da nossa checagem; o Python novo exige um filtro de segurança | filtro "data" do próprio Python, quando existe, além da nossa checagem |
| 6 | Saves no PC | com o Deck desligado, o script seguia adiante sem plano | para na hora: "Não consegui falar com o Deck. Nada foi copiado." |

## Compatibilidade conferida

- **Python do Deck e do PC:** o mesmo código roda nos dois. A suíte inteira roda nas duas máquinas antes de toda
  instalação.
- **PowerShell 5.1 (o que vem no Windows):** todos os scripts abrem sem erro de sintaxe. Os que têm acento estão
  salvos do jeito que ele entende (UTF-8 com BOM).
- **Painel do Decky:** sintaxe conferida. Todo botão chama uma ação que existe no backend (teste automático).
- **Nomes com acento** ("Ragnarök", "Pokémon"): chegam intactos ao Deck (teste automático).
- **Nomes com espaço:** corrigidos na família (item 3). A transferência e os saves já usavam aspas.

## Confiabilidade: o que impede erro de voltar

1. **`tools/implantar.py`.** Nada vai para o Deck se houver merge pendente, mudança sem salvar ou teste falhando, no
   PC **ou** no Deck. Se algo falhar, o Deck continua com a versão anterior. Usado três vezes esta noite.
2. **`tests/test_travas.py`.** São 10 travas, uma para cada falha antiga. Uma delas pegou um erro de verdade na
   primeira execução: a trava de endereços estava corrompida pelo mesmo problema que ela existe para impedir.
3. **`docs/LICOES.md`.** As 22 falhas reais do projeto, com a causa e a trava de cada uma, e 6 regras de trabalho que
   saíram delas.
4. **Código da IA local só entra com teste.** Ela erra de 1 a 3 coisas por módulo. Todo módulo gerado passou por
   testes escritos a partir da especificação antes de entrar.

## Desempenho medido

| O quê | Antes | Agora |
|---|---|---|
| Sincronizar saves do Donkey Kong (166 mil arquivos no jogo, 4 saves) | 1 min 55 s | **2,8 s** |
| Abrir telas do painel | — | 0,2 s |
| Tela do Telegram no painel | — | 1,4 s (depende da internet) |
| Suíte completa no Deck | — | 25 s |

## Pontos fracos conhecidos (baixa prioridade, não corrigidos)

- **Família:** ao aplicar um pacote, compara arquivos inteiros na memória. O limite é 300 MB por pacote, então cabe
  com folga nos 16 GB do Deck.
- **Saves no PC:** um caminho de save com apóstrofo (ex.: `Assassin's`) quebraria a cópia para o Deck. Os
  emuladores usam pastas com números (title id), então isso não acontece hoje.
- **Login do Spotify por QR:** adiado a seu pedido.
- **Importações sobrando no código:** só deixam o código mais feio, não afetam nada.

## O que só você pode testar

1. Salvar o perfil de controle durante um stream: `perfil-controle.ps1 -Acao Salvar`.
2. Rodar de novo `biblioteca-pc.ps1 -Instalar` como administrador, para o Donkey Kong e o perfil de controle
   aparecerem na aba Computador.
3. Jogar pelo PC: o stream, o botão "na TV" e o Donkey Kong.
4. Conferir dentro do jogo as traduções de Final Fantasy e Zelda BotW.
5. Configurar os controles uma vez no Azahar, no Cemu e no RPCS3.
