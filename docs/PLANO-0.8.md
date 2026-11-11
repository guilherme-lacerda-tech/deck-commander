# Plano 0.8 — Extensão de Emulação

Pedido de 11/11/2026: 10 módulos. A ordem abaixo é por **valor ÷ risco**: primeiro o que só mexe em configuração de
emulador (dá para desfazer), depois o que depende de rede, contas ou formatos de jogo. Código gerado pela IA local
sempre passa por testes escritos a partir deste documento antes de entrar (regra do `LICOES.md`).

## Decisão pendente: botões de trás
O pedido usa o **L4 duas vezes** (Save State no módulo 1 e Rewind no módulo 7). Proposta:

| Botão | Ação |
|---|---|
| L4 | Salvar estado (rápido) |
| R4 | Carregar estado |
| L5 (segurar) | Voltar no tempo (rewind) |
| R5 (segurar) | Turbo (acelerar) |

Como funciona: para atalhos que não são da Steam, o Steam não manda os botões de trás para o jogo. O Deck Commander
cria um layout do Steam Input para cada atalho de emulador em que os botões de trás viram teclas reservadas. Cada
emulador recebe essas teclas como atalho de salvar, carregar, voltar e acelerar. Isso é testado no Deck emulador por
emulador.

## Fase 1 — só configuração, desfazível (começa já)
| Módulo | O que entra | Emuladores | Critério de aceite |
|---|---|---|---|
| 1. retro-hacks | Botões de trás para salvar/carregar estado e turbo (2x/4x; o áudio acompanha a velocidade) | RetroArch, DuckStation, PCSX2, Dolphin | L4 salva e R4 carrega em < 1 s, testado no Deck |
| 7. rewind / runahead | Rewind no L5; runahead de 1 quadro nos consoles leves (o Deck aguenta até SNES/MD/GBA) | RetroArch | Segurar L5 volta no tempo sem travar |
| 8. shaders | CRT suave em consoles 2D, nítido no 3D; botão Ligar/Desligar no painel | RetroArch (por núcleo); Switch: filtro nítido do Ryujinx | Troca pelo painel; vale na próxima abertura (o RetroArch não troca shader por arquivo com o jogo aberto) |
| 6. cheats | Base oficial libretro-database (GitHub); lista em português simples no painel; ligar ou desligar por jogo; limpa ao fechar | RetroArch (Game Genie, Action Replay, GameShark) | Ativar "Vidas infinitas" num jogo de NES/SNES e ver no jogo |
| "Save scumming" | Estado automático a cada N minutos, além do salvamento manual (o RetroArch já tem salvamento por tempo) | RetroArch | R4 volta para o último estado |

Limite honesto do save scumming: "salvar 1 s antes de entrar em batalha" exige ler a memória de cada jogo.
Começamos pelo automático por tempo.

## Fase 2 — painel e confiança
| Módulo | O que entra | Critério de aceite |
|---|---|---|
| 4. painel contextual | O painel vê qual jogo está aberto (o plugin já sabe) e mostra só as telas úteis: Switch → Tradução, Controles, Melhorias; stream do PC → Controles, Rede; nada aberto → gerenciamento. Botão "ver tudo" sempre disponível | Abas mudam sem piscar |
| 5. guardião | Antes de qualquer atualização de emulador (EmuDeck, Flatpak, AppImage nova), guarda uma cópia das configurações; depois abre o emulador escondido por alguns segundos; se não abrir ou perder a config, volta a cópia e avisa | Simular atualização quebrada e ver a volta automática |

## Fase 3 — rede e nuvem (precisam de você em 1 passo)
| Módulo | O que entra | O que você faz |
|---|---|---|
| 10. saves na nuvem | `rclone` (oficial) espelha os saves numa pasta do seu Google Drive; recuperar tudo num Deck novo. Funciona com o "continuar em outro aparelho" que já existe para o PC | Entrar no Google pelo navegador do PC uma vez (o Google não permite login do rclone por QR no Deck) |
| 3. netplay | Botão "Jogar com o irmão": abre o RetroArch nos dois Decks com o endereço Tailscale já preenchido (sem abrir porta no roteador). Multi-tela local: o jogo roda no PC/Deck e a TV recebe pelo Moonlight no Fire Stick | Os dois Decks na mesma conta Tailscale; Moonlight no Fire Stick (guia já existe) |

## Fase 4 — dependem de cada jogo
| Módulo | O que entra | Limite honesto |
|---|---|---|
| 9. texturas HD | Instalar pacotes de textura que você escolher (links de fontes conhecidas: N64, GameCube/Wii, PS2) na pasta certa do emulador, com tamanho e confirmação antes de baixar | Pacotes de 1–10 GB; nem todo emulador do Deck aguenta 4K, então usamos a melhor resolução que roda liso |
| 2. dublagem | Protótipo: legendas PT-BR para cutscenes primeiro (Whisper no PC transcreve, o tradutor do projeto traduz). Voz com Edge-TTS (grátis) só onde o vídeo for de formato aberto | Cada jogo guarda vídeo em formato próprio (USM, BK2, THP…); trocar o áudio sem quebrar exige suporte por formato. Sincronia labial perfeita não é realista; sincronia por frase, sim |

## Situação (11/11/2026)
| Módulo | Situação |
|---|---|
| 1. botões de trás + turbo | ✅ instalado no Deck (17 jogos, DuckStation/PCSX2/RetroArch/Dolphin); falta o seu teste no jogo |
| 7. rewind/runahead | ✅ RetroArch (por núcleo) e rewind no DuckStation; runahead só nos consoles leves |
| 8. filtros de tela | ✅ CRT/LCD por núcleo no RetroArch, liga/desliga no painel (troca na hora com o jogo aberto) |
| 6. cheats | 🧪 leitor/escritor da base oficial pronto e testado; tela de escolher cheat por jogo vem com o 1º jogo retrô |
| 4. painel por contexto | ✅ com jogo aberto o início mostra só as telas daquele jogo ("ver todas" sempre) |
| 5. guardião | ✅ cópia diária das configurações; atualizou e quebrou → devolve a config e volta a versão (Flatpak) |
| 10. saves na nuvem | 🧪 pronto; falta você rodar tools/pc/nuvem-google.ps1 no PC (login do Google) |
| 3. netplay | próximo |
| 9. texturas HD | próximo |
| 2. dublagem (legendas primeiro) | próximo |

## Já feito nesta rodada
- **Protetor de tela "Deck Commander":** o protetor novo do Steam (versão de 13/10/2026) mostrava preto com os
  atalhos de emulador. Agora há um protetor próprio com a arte e o logo dos seus jogos (recentes primeiro),
  refeito sozinho todo dia.
