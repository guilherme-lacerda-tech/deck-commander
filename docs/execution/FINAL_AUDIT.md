# Auditoria operacional em andamento

O último checkpoint de aquisição é 31a0e6e. A base de comparação é b8c48d3. A aprovação de uma etapa pode ser reproduzida a partir das versões, comandos e evidências em TEST_EVIDENCE.md. A matriz conserva itens que ainda precisam de inspeção; uma linha PENDING não prova ausência de implementação.

## Problemas corrigidos neste ciclo

1. A primeira sincronização comparava relógios de saves diferentes. Agora os dois históricos exigem ancestral comum ou decisão explícita.
2. A confirmação descartava o ancestral comum dos arquivos cuja transferência falhava. A confirmação atualiza apenas os hashes que coincidiram.
3. A retenção podia aceitar zero cópias e considerava uma amostra suficiente ao apagar snapshots mais antigos.
4. O teste anterior do RomM esperava id. O serviço real devolve task_id. O worker verifica o estado remoto e mantém publicações subsequentes na fila.
5.	O cliente qBittorrent presumiu o mesmo caminho no cliente e no servidor, e uma sessão local sem senha. O fluxo HomeLab usa autenticação e mapeamento explícito.
6.	O qBittorrent 5.3.1 usa HTTP 204 e um nome de cookie específico da porta. O cliente, o Compose e o teste foram corrigidos pela resposta do serviço real.
7.	Um perfil Steam sem shortcuts.vdf importava a ROM e falhava ao criar o primeiro atalho. A criação agora é exclusiva. Em arquivo existente há backup e verificação de round-trip.
8.	A verificação de integridade do qBittorrent podia ser tratada como arquivo concluído. O importador espera o estado final e um caminho acessível.
9.	O /sync podia ler o registro antes da trava e voltar a gravar dados antigos depois de liberá-la. As operações normais de leitura e escrita desse ciclo agora estão sob o mesmo lock.

## Limites do aceite

A validação completa do produto segue aberta. O recebimento do comando em uma conta Telegram real, os percursos de instalação existentes, autoatualização fora da rede, streaming, P2P, texto e fontes de cada versão de jogo, UI de cheats, ativos reais em RetroAchievements e fluidez no DMC3 exigem evidência própria. A comparação com todo o histórico de auditorias segue em reconciliação. Ainda não há denominador auditado para um percentual global de conclusão.

## Recuperação

Consultar EXECUTION_STATE.json, TEST_EVIDENCE.md e BLOCKERS.md. O checkpoint no Deck contém o código anterior de três módulos e fica em ~/.local/state/deck-commander/code-checkpoints/. O teste de aquisição usa somente o inventário descartável e a biblioteca vinculada a ele. Os dados de laboratório podem conter credenciais geradas e permanecem fora do Git.

## Prioridade de aquisição por nome

O P0 obrigatório passou a baixar jogos a partir do nome. O catálogo HTTPS funciona em processo separado, com fila SQLite, tamanho e SHA-256 fixados, escrita atômica, recuperação e deduplicação. A busca Prowlarr roda em segundo plano, seleciona uma identidade inequívoca e mantém pedidos sem fonte para nova tentativa. Doom Shareware e Super Tilt Bro foram instalados e abertos na VM SteamOS. A suíte completa aprovou 1080 testes com 3 pulados. O aceite integral ainda inclui transporte Telegram e publicação Steam autenticados, descritos em BLOCKERS.md.
