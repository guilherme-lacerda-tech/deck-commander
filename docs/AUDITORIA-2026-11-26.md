# Auditoria de continuidade — 26/11/2026

## Resultado verificável

| Item | Evidência | Resultado |
|---|---|---|
| Regressão completa | `python -m pytest -q` | 1.020 passaram; 3 pulados por dependerem do ambiente |
| Detonados DMC3 | 20 arquivos de missão, todos com `pt`; auditoria de frases não achou texto longo original em inglês | 20/20 disponíveis offline em português |
| IA local | túnel SSH reverso do PC para o Deck; Ollama `qwen2.5:7b` respondeu pelo endereço local do Deck e carregou na GPU do PC | ativo, privado e persistente ao login do Windows |
| Atualizações fora da mesma rede | consulta GitHub com fallback por `git ls-remote`; cache do Deck conferido | versão instalada é a atual e não há atualização pendente |
| Biblioteca | diagnóstico DB × disco × Steam | nenhum arquivo ou atalho ausente/modificado sem procedência do Deck Commander |
| Instalação ponta a ponta no Deck | torrent local → `.zip` → `/sync` → atalho Steam ao vivo → duplicata → remoção | passou duas vezes; a segunda confirmou limpeza de atalho, torrent, quarentena de teste, arte e detonado temporários |
| Serviços | `deck-commander-bot` e `deck-commander-power` | ativos |
| Controle de DMC3 | VDF do Steam Input no próprio Deck | R4 = Save1; L5 = histórico com setas e A |
| States PCSX2 | hash antes/depois das implantações | inalterado; 20 arquivos presentes |
| Métrica DMC3 | CSV do MangoHud da sessão longa | duração corrigida de 5.581 min falsos para 160,2 min reais; cópias dos JSONs anteriores foram preservadas |

## Correções feitas nesta rodada

1. DMC3 deixou de depender do índice incompleto da StrategyWiki. Usa Devil May Cry Wiki sob CC BY-SA, com atribuição no painel e as 20 missões existentes.
2. O cache antigo de DMC3 migra sozinho mesmo se antes estivesse marcado como "pronto" por páginas ausentes.
3. O painel não aceita um detonado parcialmente traduzido: se faltar qualquer bloco em português, continua em preparação e não mistura inglês no texto.
4. Trabalhadores de guia são executados com prioridade baixa no Deck. A tradução usa primeiro a IA local do PC/GPU e só usa o modelo do Deck como reserva.
5. O cálculo de duração usa MangoHud quando a suspensão do Deck torna o relógio de parede inválido. A telemetria antiga afetada foi reparada a partir do CSV original.
6. O E2E apagava o jogo de teste mas deixava caches de capa/detonado. A limpeza agora remove esses dois caches do `game_id` de teste e a execução real confirmou que não sobrou resíduo.

## Pendências que ainda exigem prova externa

- Uma partida real de DMC3, com luta pesada e save state, para aferir a reação ao vivo de TDP/FPS no hardware. A lógica e o log estão instalados; não existe substituto automático para essa prova.
- Confirmação física dos botões L4/R4/L5 pelo usuário no perfil que o Steam carregar.
- VM SteamOS em Game Mode: o Windows atual informa virtualização de firmware indisponível e não tem Hyper-V disponível. WSL não valida o SteamOS/Game Mode.
- Azahar, Cemu e RPCS3 precisam da escolha única do controle dentro de suas próprias interfaces; não são configurados por chute para não criar uma primeira execução nova.
- RetroAchievements aguarda nome de usuário e Web API Key; a integração não pode inventar credenciais.
- A base oficial de cheats RetroArch está configurada, mas a seleção/ativação de cheats ainda é feita pelo menu do RetroArch, não por um painel próprio do Commander.

Essas pendências são bloqueios de validação ou de dados que pertencem ao proprietário, não falhas ocultadas pelo relatório.
