# Lições: falhas que já aconteceram e o que impede que voltem

Cada linha é uma falha real deste projeto. A coluna "Trava" diz o que agora impede a repetição — de preferência um
teste automático (`tests/test_travas.py` e outros), que roda antes de toda implantação (`tools/implantar.py`).

| # | Falha | Causa | Trava |
|---|---|---|---|
| 1 | Arquivo Python quebrado (f-string com quebra de linha, função cortada no meio) chegou ao repositório | código gerado/colado por script com escape errado; nenhum teste importava aquele trecho | `test_todo_python_compila` compila TODO arquivo .py |
| 2 | Painel do Decky inteiro não abria | quebra de linha literal dentro de uma string JS | `test_painel_js_sintaxe` (node --check) |
| 3 | Script do PC com acento falhava ao rodar | PowerShell 5.1 lê .ps1 sem BOM como ANSI | `test_powershell_com_acento_tem_bom` + `test_powershell_sintaxe` |
| 4 | "Ragnarök" virou "RagnarÃ¶k" no Deck | texto enviado ao ssh pelo PowerShell em ANSI | `test_powershell_que_conversa_com_ssh_usa_utf8` |
| 5 | Regex que nunca casava; caminho "C:\AutomacaoCasa\agente" virou lixo | `\b`/`\a`/`\t` escritos por script viraram caracteres de controle | `test_sem_caractere_de_controle_invisivel` |
| 6 | IP do PC/Deck, IPs da Tailscale e MAC da casa no repositório público | valores reais usados como padrão no código e nos testes | `test_sem_endereco_real_no_repositorio` (lista só com hash) + cada Deck tem a própria config |
| 7 | Implantação feita no meio de um merge com conflito | comandos soltos de cópia, sem conferir o estado do git | `tools/implantar.py` recusa merge pendente, mudança sem commit e teste falhando (no PC e no Deck) |
| 8 | Arquivo de teste quebrado foi para o Deck | `… \| tail` escondia a falha do pytest e a cadeia seguia | `implantar.py` confere o código de saída real do pytest (PIPESTATUS) |
| 9 | Botão novo do painel chamando ação inexistente (risco) | painel e backend editados separados | `test_toda_acao_do_painel_existe_no_backend` |
| 10 | Comando anunciado no /help sem tratamento (risco) | ajuda e roteamento editados separados | `test_todo_comando_da_ajuda_e_atendido` |
| 11 | "Retomar" aparecia para tradução antiga já superada | painel listava todas as tarefas | uma tarefa por jogo (a mais nova pela data de criação) + teste |
| 12 | "Retomar" no Hercules (falha de formato) | tentar de novo dá o mesmo erro | falha de formato vira explicação, sem botão + teste |
| 13 | Botão B fechava o painel | o "fechar plugin" do Decky tem prioridade | o painel assume o fechar só dentro de uma tela |
| 14 | Textos do painel impossíveis de ler | o direcional só para em botões | texto é parada do direcional; quebra de linha em vez de corte |
| 15 | `moonlight list` travava e deixava processos órfãos | sem tela, o Moonlight trava ao baixar capas; o tempo-limite matava só o flatpak | o PC manda a lista de jogos; tempo-limite mata o grupo inteiro |
| 16 | Janela do PowerShell piscando a cada 5 min | `-WindowStyle Hidden` ainda pisca | tarefas rodam pelo `oculto.vbs` |
| 17 | Transferência longa podia ser cortada pelo sono do PC | o agente da casa dormia após 20 min "ocioso" | arquivo `*.ativo` vigiado pelo agente + pedido de energia do Windows |
| 18 | `pkill -f nome` matou o próprio comando ssh | o padrão casava a linha de comando de quem chamava | matar por PID (lição operacional) |
| 19 | Família casava um jogo com o torrent de outro jogo da mesma pasta | regra por "mesma pasta" com jogos soltos | só pasta própria do jogo + teste |
| 20 | Sincronizar saves levava ~2 min | listava os 166 mil arquivos do jogo para achar 4 saves | modo "só dados" nos dois lados (2,8 s) |
| 21 | Código da IA local com erros (sintaxe, chaves erradas, detecção da dock sempre "ligada", estado não relido, valor igual para todas as opções) | modelo local erra 1–3 coisas por módulo | regra: todo módulo gerado passa por testes escritos a partir da especificação ANTES de entrar; revisão por focos (`tools/ia-local-revisao.py`) |
| 22 | Chave AES do executável / tarefa agendada criada por mim | ações bloqueadas pela segurança (quebrar proteção; persistência no sistema) | não fazer; tarefas do sistema são instaladas pelo usuário (`-Instalar`) |
| 23 | Save com espaço no nome quebraria a cópia para o Deck | o PowerShell 5.1 perde as aspas duplas (`") ao chamar ssh.exe/scp.exe | `test_powershell_nao_passa_aspas_escapadas_ao_ssh`; aspas simples no comando remoto |
| 24 | Spotify do Deck não ligava | a documentação dizia `-config_dir`, mas o programa lia como `-c onfig_dir` (precisa de `--`) | teste confere `--config_dir`; regra: conferir o `--help` do próprio programa, não só a documentação |
| 25 | Spotify "tocava" sem som | o Spotify recusa a chave de áudio para players não oficiais (go-librespot #279/#317) | conta e playlists pelo go-librespot; tocar sempre pelo app oficial escondido (testado no Deck) |

## Regras de trabalho que saíram daqui
1. **Nada vai para o Deck sem `tools/implantar.py`.**
2. **Código gerado (IA local ou script) só entra com teste da especificação.** Primeiro o teste falha, depois passa.
3. **Escrever arquivos com o editor, não com `sed`/heredoc**, quando houver `\`, aspas ou acento.
4. **Arquivos .ps1 com acento: UTF-8 com BOM.** Scripts que falam com o ssh: `$OutputEncoding` UTF-8.
5. **Nada da rede de ninguém no código.** Cada aparelho guarda a própria configuração.
6. **Medir antes de otimizar** (ex.: ações do painel 0,2 s; saves 2,8 s).
7. **Testar no aparelho de verdade** o que depende de programa ou serviço de fora: a documentação e os testes simulados não pegaram as falhas 24 e 25.
