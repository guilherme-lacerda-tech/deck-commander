# Evidências da execução de 26/11/2026

| Ambiente | Teste e dados | Resultado observado |
|---|---|---|
| Windows | Base b8c48d3, python -m pytest -q | 1051 aprovados, 3 pulados, 94,86 s |
| Linux | Cópia de trabalho, pytest no Ubuntu WSL2, HOME descartável, primeira rodada após proteção de saves | 1051 aprovados, 5 pulados, 30,71 s |
| Steam Deck físico | SteamOS 3.9.5, Python 3.14.6, HOME e DC_ROOT exclusivos em /tmp, 6 módulos pytest | 24 aprovados, 1 aviso de plugin pytest do sistema |
| Steam Deck físico | SHA-256 anterior de backup.py, saves_regra.py e saves_sync.py igual à base Git. Processo de jogo ausente. Cópias feitas antes da troca e comparação byte a byte após instalação | 3 módulos substituídos; checkpoint de código save-sync-blyremwr |
| Infraestrutura | Ansible Core 2.22.0, community.docker 5.4.1, ansible-lint 26.11.1. Docker em WSL2 | Syntax-check, check e aplicação passaram. Segunda aplicação: ok=7, changed=0, failed=0. Lint: 0 erros, 0 avisos de regra |
| RomM | Conta de teste criada pelo fluxo de instalação, autenticação OAuth2, POST /api/tasks/scan, GET de tarefa e GET /api/roms | RomM 5.4.1 encontrou Commander Controller Check.nes |
| Aquisição | homelab/tests/validate_acquisition.py, Torznab privado, libtorrent 2.0.12, ROM iNES gerada. qBittorrent 5.3.1 acessado por API autenticada | Busca Prowlarr, bytes do torrent conferidos, download por peer, SHA-256, /sync, leitura do primeiro shortcuts.vdf e consulta ao catálogo RomM passaram |
| IA local | Ollama em loopback, qwen2.5-coder:7b | Respondeu à consulta de revisão de concorrência. Nenhuma credencial no prompt |
| VM SteamOS | Disco de sobreposição qcow2, inicialização KVM e consulta SSH em loopback | SteamOS 3.8.14 respondeu com Steam em execução, EmuDeck e plugin presentes |
| PC, retomada de 27/11/2026 | `python -m pytest -q tests/test_primeiro_controle.py tests/test_emulators.py tests/test_plugin_matrix.py tests/test_instalacao_nova.py` | 20 aprovados em 1,33 s |

O teste do catálogo usou um perfil de arquivos Steam vazio. Abertura do atalho no cliente gráfico, envio pelo Telegram público, tradução linguística, achievements autenticados e desempenho em partida têm critérios de aceite próprios.

## P0 por nome em 27/11/2026

O pedido de nome até download e instalação passou a preceder as demais funcionalidades.

| Ambiente | Execução | Resultado |
|---|---|---|
| Windows | python -m pytest -q, saída em outputs/pytest-name-download.log | 1080 aprovados, 3 pulados, 68,48 s |
| Windows | tests/test_doom_download.py, test_catalogo_downloads.py, test_bot_entradas.py, test_prowlarr.py | 71 aprovados |
| SteamOS 3.8.14 em VM KVM | python3 homelab/tests/validate_name_download.py --root /home/deck/commander-nome.ZXdmhF/profile "Super Tilt Bro" "Doom" | Dois pedidos pelo handler normal, subprocesso real, download HTTPS, SHA-256, instalação, mapa de lançamento e repetição idempotente aprovados |
| VM, Super Tilt Bro 1.0 NES | Launcher dc-launch nes-super-tilt-bro e core Nestopia existente do EmuDeck | Tela inicial inspecionada em outputs/vm-super-tilt.png |
| VM, Doom Shareware | ZIP real da distribuição Libretro, membro Doom/doom1.wad, core PrBoom existente e instalação de prboom.wad com hash | Launcher dc-launch doom-doom1 abriu a fase jogável. Entrada de teclado pelo monitor QEMU e captura em outputs/vm-doom.png |
| VM, instalação | setup-deck.sh --modules M0,M2,M3,M4 --no-downloads usando os emuladores existentes | Serviços qBittorrent e power ativos, plugin integral conferido por diff. Instalação repetida terminou com plugin em dia |
| VM, preservação | sha256sum --check --quiet do manifesto anterior de .config/EmuDeck, .config/PCSX2 e Emulation | Todos os 32488 arquivos originais conferiram. Log hash-check.log vazio, exit 0 |
| IA local | Ollama qwen2.5-coder:7b revisou catálogo HTTP | Parecer em outputs/name-download-local-review.txt. As suspeitas de traversal foram conferidas contra validação de nomes e testes específicos |

O artefato implantado teve SHA-256 e79fc1be770c4fb14f176439fcb630f598e359fa104ac4837c1adc5905cd4294. O backup do código anterior está em /home/deck/commander-nome.ZXdmhF/codigo-anterior.tar.gz. A primeira transferência foi refeita após detectar um arquivo tar incompleto e a implantação seguinte conferiu hash e leitura integral do pacote.

A instalação encontrou plugin.json protegido pelo proprietário root na VM. A pasta específica do plugin recebeu a propriedade deck, e a segunda aplicação atualizou o manifesto. A terceira aplicação confirmou o conteúdo em dia. O Deck físico permaneceu fora deste ensaio.

Os downloads estão em ~/Emulation/roms/nes/Super Tilt Bro e ~/Emulation/roms/doom/Doom Shareware. O relatório estruturado está em outputs/name-download-vm-result.json. Super Tilt Bro tem SHA-256 ed0369a686a945c1f19c30aef9b6d02e184ff592876622610675c3474e2b3d8c. Doom1.wad tem SHA-256 1d7d43be501e67d927e415e0b8f3e29c3bf33075e859721816f652a526cac771.

A VM está sem conta Steam autenticada e sem token Telegram. O teste exerceu o handler de mensagens com entradas locais e a aquisição em rede real. As operações ficaram em waiting_steam com os arquivos instalados. Faltam o transporte público do Telegram e a visualização do atalho na Steam autenticada para fechar o aceite integral P0-NOME. Títulos comerciais adicionais requerem fontes configuradas que disponibilizem a edição solicitada. Os testes desta rodada usaram Doom Shareware e Super Tilt Bro.
