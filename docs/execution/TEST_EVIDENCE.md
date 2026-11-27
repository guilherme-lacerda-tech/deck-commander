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
