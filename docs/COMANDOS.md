# Comandos do Deck Commander

Tudo roda a partir de `~/deck-commander` (Konsole no modo Desktop, ou SSH).

## Instalação e ciclo de vida (M12/M15)
| Comando | O que faz |
|---|---|
| `./setup-deck.sh --all` | instala/atualiza o projeto inteiro (idempotente) |
| `./setup-deck.sh --modules M0,M4` | só os módulos pedidos (+ dependências) |
| `./uninstall-module.sh M4 [--purge]` | desliga um módulo, preserva dados; avisa quem depende dele |
| `./safe-mode.sh` / `./safe-mode.sh off` | desliga/religa automações (não apaga nada) |
| `./uninstall-deck-commander.sh [--purge [--purge-backups]] --confirm APAGAR` | remove o projeto |

## Biblioteca e emuladores (M2/M3/M5)
| Comando | O que faz |
|---|---|
| `python3 -m dc library [--apply]` | coloca jogos novos de `~/Emulation/roms` e do SD no Steam (ao vivo com o plugin) |
| `python3 -m dc artwork` | baixa capas do SteamGridDB (não sobrescreve as suas) |
| `python3 -m dc x configure [--apply]` | perfil equilibrado em Dolphin/PPSSPP/RetroArch (respeita ajustes manuais) |
| `python3 -m dc x profile <ps1\|ps2> <economico\|equilibrado\|desempenho> [--apply] [--force]` | perfil de qualidade no DuckStation/PCSX2 (recusa sobrescrever ajuste manual sem --force) |
| `python3 -m dc x dedup` | lista cópias idênticas de ROMs byte a byte (só sugere, nunca apaga) |
| `python3 -m dc x duplicados` | jogos repetidos na biblioteca (mesmo jogo em outra versão/região/arquivo) |
| `python3 -m dc x remover <game_id ou nome> [--confirm]` | tira um jogo: atalho, mapa, arquivos → quarentena, download (sem `--confirm` só mostra o plano) |
| `python3 -m dc x qualidade [<jogo> nativo\|2x\|3x\|4x\|padrão]` | resolução só daquele jogo (sem argumentos lista os ajustes) |
| `python3 -m dc x controles [labels\|positional]` | situação dos controles; troca o layout de botões do Switch (labels = A=A) |
| `python3 -m dc x tabs` | regera as abas do TabMaster |
| `python3 -m dc x patch <rom> <patch>` | aplica tradução IPS/BPS/UPS/XDelta numa cópia "(patch)" (disco de outra versão: só com receita) |
| `python3 -m dc x steam-restart` | reinicia o Steam (recusa se houver jogo aberto; só necessário sem o plugin) |

## Tradução e conversão (A1/A2/A3) — pelo Telegram
| Comando | O que faz |
|---|---|
| `/traduzir <jogo> [--forcar]` | traduz para pt-BR com IA (Switch: mod; Pokémon GBA: ROM "(PT-BR)") |
| `/traduzir status \| config` | tarefas e cadeia de IA |
| `/traduzir revisar\|aplicar\|aprovar\|retomar <op>` | relatório, aplicar guardado, aprovar provedor pago, continuar |
| `/traduzir desfazer <jogo>` | remove o mod de tradução |
| `/converter <jogo> [organizar\|descompactar]` | Switch: diagnóstico, pasta por jogo, NSZ/XCZ |
| `./setup-deck.sh --modules A1,A2,A3` | instala Ollama local + modelo, Meowth e nsz |

## Conteúdo (M4) — pelo Telegram: `/help`
| Comando | O que faz |
|---|---|
| `python3 -m dc secret telegram` | guarda o token do bot (você cola, não aparece) |
| `python3 -m dc x telegram-pair` | gera o código de pareamento (`/start CODIGO` no bot) |
| `python3 -m dc x sync [tudo]` | mesmo que o /sync do bot |

## Segurança e operação (M0/M6/M7/M10/M11/M17/M19/M20/M21)
| Comando | O que faz |
|---|---|
| `python3 -m dc backup create` · `backup latest` · `restore <snap> [--apply]` | backups verificados |
| `python3 -m dc quarantine list` | quarentena (nunca apagada sozinha) |
| `python3 -m dc x saves` · `x saves import <snap> [--apply]` | backup/import de saves (conflito nunca sobrescreve) |
| `python3 -m dc x disk` | 10 maiores jogos + candidatos a remoção (só sugere) |
| `python3 -m dc x status` · `x sensors` · `x diagnose [--apply]` | status, sensores, diagnóstico/autorreparo |
| `python3 -m dc x db index` · `x db verify` | banco × disco × Steam (não corrige sozinho) |
| `python3 -m dc x tests` · `x updates` | testes automáticos · verificação de updates (não atualiza) |
| `python3 -m dc x export [arquivo.zip]` · `x import <zip> [--apply]` | configs para outro Deck, sem segredos |
| `python3 -m dc inventory` · `contracts` | inventário (M-1) · validação dos contratos (M27) |
| `systemctl --user enable --now deck-commander-dashboard` | painel em http://127.0.0.1:8765 (opcional) |
| `python3 -m dc x pc status · listar · sincronizar · acordar · jogar <app> · config [chave valor]` | jogos do PC na aba Computador (docs/PC-REMOTO.md) |
