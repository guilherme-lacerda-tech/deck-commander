# Bloqueios externos e trabalho de engenharia

| Requisito | Verificação | O que falta | Alternativa em uso |
|---|---|---|---|
| Implantação no servidor Debian do proprietário | O projeto fornece hosts.example.yml com CHANGE_ME. A conexão autorizada encontrada é do Deck. No PC há uma distribuição Ubuntu via WSL2 | Endpoint SSH e inventário de produção identificáveis para essa máquina | Stack real em projeto Docker descartável com Ansible |
| RetroAchievements com conta pessoal | O formulário e as ações de configuração já existem | Evidência de progresso de uma conta autorizada. Não registrar chave no relatório | Cobertura da lógica em tests/test_conquistas.py |
| Aceite de DMC3 durante a luta | SteamOS e PCSX2 foram inventariados. Uma consulta ao sistema indicou jogo fechado durante a implantação de proteção de saves | Medição de FPS, frametime, velocidade do emulador, perfil ativo e consumo durante a luta | Harness de telemetria e testes específicos já presentes |
| HDMI-CEC e vibração percebida | Capacidade depende da dock, TV, jogo, núcleo e saída reais | Captura de eventos junto com resposta física | Manter a validação específica por configuração |
| Castlevania | O adaptador existente atende Symphony of the Night de PS1. O formato da fonte está identificado em dc/traducao/sotn_fonte.py | Identidade e asset da edição Unity, se for um título diferente. A edição PS1 precisa de validação visual separada | Nunca aplicar uma receita Unity sobre a imagem PS1 |

O desenvolvimento do painel de cheats, da fila, das receitas de tradução e da sincronização de saves segue como trabalho de engenharia. O acesso ao Debian pessoal não é pré-requisito para testar os serviços em Docker.
