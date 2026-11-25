# Estado verificável do projeto

Atualizado em 25/11/2026. Este documento separa o que foi testado em código, o que foi instalado no Deck e o que ainda precisa de uma partida real. Não use a palavra “profissional” como sinônimo de “sem pendências”: a validação em hardware continua obrigatória para recursos que dependem do Steam Input e de emuladores reais.

## Funcionalidades entregues e cobertas por teste automatizado

| Área | Estado | Garantia atual |
|---|---|---|
| Biblioteca e atalhos | Coberta | O índice reconcilia metadados sem tocar ROMs, saves ou atalhos que não pertencem ao Deck Commander. Impede importação em massa do EmuDeck/RetroDECK, incluindo Wii. |
| Atualizações | Coberta | Consulta GitHub e tem fallback por `git ls-remote`; portanto encontra nova versão fora da mesma rede Wi-Fi. Instalação mantém backup, testes e rollback; não atualiza silenciosamente no meio de uma partida. |
| Save states PCSX2 | Coberta estruturalmente | L4 mantém uma janela rotativa de dez estados anteriores; R4 carrega Save1; L5 abre seleção com D-pad e A. A rotação espera o arquivo terminar de ser escrito para reduzir disputa de I/O. Nunca altera saves normais/ROMs. |
| Desempenho | Coberta em lógica | MangoHud detecta lentidão sustentada e aumenta TDP/solta o limite de FPS durante o jogo; perfis preservam resolução por jogo e aprendem piso de TDP estável. A política é imagem primeiro, fluidez em seguida e bateria apenas para não desperdiçar. |
| Detonados | Coberta | Baixa previamente, traduz com a IA local configurada e só mostra conteúdo PT-BR offline. DMC3 usa Devil May Cry Wiki (CC BY-SA), pois o índice da StrategyWiki listava páginas não publicadas; as 20 missões foram verificadas na fonte. |
| RetroArch cheats | Base corrigida | O caminho agora aponta para o banco oficial de 28 mil cheats dentro do Flatpak. A ativação de cheats pelo painel ainda não existe. |
| RetroAchievements | Integração pronta, sem conta | O painel detecta a integração, mas depende de usuário e API key do dono; credenciais não são inventadas nem gravadas fora do cofre local. |

## Auditoria de instalação atual

- Serviços `deck-commander-bot` e `deck-commander-power`: ativos na última verificação.
- Banco de biblioteca: reconciliado com segurança; a auditoria ficou em **9/10**. O ponto restante é a confirmação uma vez nos próprios emuladores Azahar (3DS), Cemu (Wii U) e RPCS3 (PS3). Não é seguro criar configurações desses emuladores por chute, pois isso pode fazê-los abrir como primeira execução.
- Estados do PCSX2: hash conferido antes/depois das implantações; nenhuma state foi apagada, renomeada ou restaurada durante a auditoria.
- Código: suíte completa de testes deve ser executada antes de cada implantação. O linter possui apontamentos históricos e ainda não é um selo de limpeza total.

## Limitações honestas que ainda faltam validar

1. Uma partida real do DMC3, incluindo save state sob carga, para medir FPS, TDP, temperatura e travadas. Testes de lógica não substituem isso.
2. Steam Input físico para confirmar L4/R4/L5 no perfil atualmente carregado.
3. Primeira instalação completa dentro de uma VM com SteamOS/Game Mode. O host Windows não dispõe de Hyper-V habilitado/elevado nem de uma imagem SteamOS; WSL não testa Game Mode.
4. Ativação de cheats RetroArch pela interface e vinculação do RetroAchievements após as credenciais do proprietário serem cadastradas.
5. Teste de uma biblioteca Wii real, com EmuDeck já configurado, para comprovar visualmente que não há poluição por centenas de ROMs.

## Critério de aceite recomendado

Considere o conjunto pronto para uso cotidiano quando os itens 1, 2 e 5 acima forem aprovados no Deck real. Considere-o pronto para distribuição a terceiros somente depois de também concluir o item 3 e validar os emuladores que a instalação deles utiliza.
