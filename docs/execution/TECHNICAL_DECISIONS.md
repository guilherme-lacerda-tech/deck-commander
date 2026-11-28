# Decisões técnicas

| Decisão | Motivo e custo | Recuperação |
|---|---|---|
| Conservar a base na branch de execução | O checkpoint b8c48d3 contém o trabalho local que antecede a rodada. A instalação dos clientes lê a branch de lançamento | Comparar com b8c48d3 e publicar separadamente após aceite |
| Usar a API de tarefas do RomM 5.4.1 | O POST devolve task_id. O trabalho remoto pode continuar depois da saída do cliente. Publicações posteriores ficam em uma geração subsequente no SQLite | Cada consulta pode retomar pelo ID. Um crash entre envio e persistência pode disparar outra varredura |
| Testar aquisição com uma ROM iNES criada no laboratório | Um catálogo Torznab e um peer BitTorrent oferecem apenas o arquivo criado no teste. Prowlarr, qBittorrent, MariaDB e RomM usam suas implementações distribuídas | Os dados pertencem ao projeto Compose dc-audit-* |
| Restringir os serviços administrativos a loopback | O Deck pode usar encaminhamento SSH. O cliente qBittorrent traduz os caminhos do contêiner para o volume acessível ao Deck | Remover a configuração do cliente restaura o uso local |
| Escolher saves por ancestral comum | Relógios de dispositivos diferentes e restaurações antigas podem inverter a ordem por data | Se os hashes divergirem sem base comum, preservar ambos e expor o conflito |
| Criar o primeiro VDF por publicação exclusiva | Steam pode gravar os primeiros atalhos entre o planejamento e a publicação | Em colisão, a nova tentativa relê o arquivo existente |
| Usar os perfis específicos do Steam Deck no primeiro lançamento Flatpak | O emulador escolhido pelo usuário conserva sua pasta original. O modelo Valve e o identificador do Flatpak determinam o caminho | Instalação exclusiva e preservação do perfil anterior |
| Usar uma imagem de sobreposição na VM | Testes de instalação podem mudar o disco, firmware e serviços do convidado | Usar novamente o arquivo base e sua NVRAM original |

Fontes de contratos de integração: [RomM 5.4.1](https://github.com/rommapp/romm/blob/5.4.1/backend/endpoints/tasks.py), [Web API qBittorrent](https://github.com/qbittorrent/qBittorrent/wiki/WebUI-API-%28qBittorrent-5.0%29), [Prowlarr](https://github.com/Prowlarr/Prowlarr/blob/develop/src/Prowlarr.Api.V1/Search/SearchController.cs), [perfis EmuDeck](https://github.com/dragoonDorise/EmuDeck/tree/d181675eb9ab43b270daf8b459d178b829258c5c/configs).
