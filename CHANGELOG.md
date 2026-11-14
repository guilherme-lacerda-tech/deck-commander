# Changelog

## 0.9.0 — 2026-11-14 — experiência de console
- **Continuar de onde parou** (PS1, PS2, PSP, GameCube/Wii, RetroArch): ponto salvo ao apertar o botão Steam/"…",
  antes de dormir e a cada 10 min; o jogo abre nele. Testado no Deck em DuckStation, PCSX2, PPSSPP e RetroArch.
  Os saves do L4 nunca são trocados; ponto de outra versão do emulador não é carregado.
- **Voltar no tempo pelo painel** (5/10/30 s) e voltar no tempo também no PSP (L5).
- **Detonado por capítulo em português** (StrategyWiki, CC BY-SA): por insígnia/capítulo/colosso, lembra onde você
  está, lê sem internet.
- **Perfis de imagem**: Beleza / Desempenho / Retrô / Automático (`/perfil`).
- **Vibração** ligada no Switch (Ryujinx) e no GameCube/Wii (Dolphin) — vinham desligadas.
- **A/B por console**: NES, SNES, Game Boy e GBA podem usar "A do Deck = A do jogo".
- **Modo repouso**: na tomada, com download/tradução, o Deck não dorme até terminar (uma permissão de administrador).
- **Patch `.xdelta` (VCDIFF) sem programa de fora**, em pedaços (patch de 1 GB sem estourar a memória). Disco de
  outra versão com receita: leva só os arquivos traduzidos para o seu disco. **God of War: Chains of Olympus** (PSP)
  agora em português com a tradução da OAleex e cia (era a ISO russa): menus, legendas e acentos testados no Deck.
- **Detonado acompanha o jogo** quando a versão "(PT-BR)" substitui a original.
- Corrigido (achado no teste do Deck): o arquivo de controles do PSP criado para o "continuar" tinha só as teclas
  novas, e o PPSSPP desligava **todos os outros botões** (o controle do Deck parava no PSP). Agora o arquivo novo
  traz os botões padrão, e quem já tinha o arquivo estragado recebe os botões de volta ao abrir um jogo de PSP.
- Corrigido: tradução de retrô pelo RomTranslate quebrava no fim ("RtsReport sem strings").
- Corrigido: jogo PAL (50 quadros) era sempre julgado "travando" e ficava preso na resolução nativa; partida de menos
  de 2 min não ensina mais o auto-ajuste.

## 0.8.2 — 2026-11-12 — saves que não se perdem
- **Cópia automática dos saves** de cada jogo (save do jogo e saves rápidos) antes de cada vez que ele abre; ficam as
  5 últimas em `~/Backups/DeckCommander/saves/<jogo>/`. No bot: `/saves copias <jogo>` e `/saves voltar <jogo> <n>`
  (o save de agora vira cópia antes de voltar).
- RetroArch grava a bateria do cartucho (save do próprio jogo) a cada 10 s, não só ao fechar.

## 0.8.1 — 2026-11-12 — revisão de retrogamer
- RetroArch: **porta de comandos pela rede fechada** (a UDP 55355 aceitava "fechar jogo"/"carregar estado" de
  qualquer aparelho da rede local). Trocar o filtro de tela com o jogo aberto agora vale ao reabrir o jogo.
- RetroAchievements: o modo **hardcore** fica desmarcado enquanto as conquistas estiverem desligadas (antes, ligar as
  conquistas tirava salvar/carregar, voltar no tempo e turbo sem aviso). Quem já usa conquistas não é afetado.
- **Aviso de emulador atualizado**: ao abrir um jogo depois de o emulador mudar de versão, aparece um aviso de que
  save states antigos podem não abrir (o save do próprio jogo sempre abre).
- Tradução de disco (Castlevania) gera também o **patch .bps** ao lado da cópia PT-BR, para compartilhar sem o jogo.
- Configurações feitas pela 0.8.0 são corrigidas sozinhas (com o RetroArch fechado).

## 0.8.0 — 2026-11-12 — retrô de verdade e revisão de lançamento
- **Botões de trás** nos jogos retrô (RetroArch, DuckStation, PCSX2, Dolphin): L4 salva, R4 carrega, L5 (segurar)
  volta no tempo, R5 liga/desliga o turbo. Aplicado **uma vez** por jogo: o layout que você escolher depois é
  respeitado. `/retro desfazer` devolve emuladores e layouts como estavam.
- RetroArch: rewind, run-ahead e filtros de tela por núcleo; DuckStation a 100% (sem a camada WSI do gamescope).
- **Castlevania: Symphony of the Night em PT-BR**: engenharia reversa dos 2 formatos de texto, acentos de verdade
  (fonte 8x8 e falas), menus com pontuação japonesa, botões da tela de arquivos redesenhados em português.
- **Zelda: Tears of the Kingdom**: PT-BR oficial ao abrir e dublagem PT-BR das cenas (BWAV idêntico ao original).
- Vídeos sem legenda ganham **legenda PT-BR** (padrão); dublagem com `--dublar`.
- Texturas HD (PS2/GC/Wii), netplay com o par pela Tailscale, saves na nuvem (Google Drive), protetor de tela com a
  arte dos seus jogos, guardião que desfaz atualização de emulador que quebrou.
- **Revisão de lançamento**: downloads de programas conferidos pelo sha256 publicado; trava única nos arquivos
  que o plugin e o Deck Commander dividem; plugin não abre mais um Python por minuto (bateria); painel usa o código
  novo sem reiniciar o Decky; emulador que cai ao abrir vira aviso na tela; **desinstalar tira tudo** (atalhos,
  layouts, teclas, protetor, .zip) e pede ao Decky para tirar o plugin; checagem ao vivo no Deck depois de toda
  implantação (`python3 -m dc.revisao_viva`).

## 0.7.0 — 2026-11-11 — o Deck conversa com a casa
- Transferência de jogos nos dois sentidos (Deck ⇄ PC) com o emulador oficial do outro lado; aba **Computador**
  (jogos do PC por streaming); botão **Jogar na TV**; **Liberar espaço**.
- Saves Deck ↔ PC por jogo (`/saves`), automáticos ao fechar o jogo; `/voltar` versão de emulador.
- Família: catálogo compartilhado pela Tailscale; `/corrigir` frase traduzida por foto (OCR no PC).
- TDP automático por console; volume do jogo × música; Spotify (conta e playlists) pelo painel.
- Painel completo no menu "…" do Decky (status, Telegram com QR, downloads, tradução, PC, transferências, qualidade,
  desinstalar jogos com quarentena de 30 dias).
## 0.6.0 — 2026-11-09 — baixou, chega traduzido
- **RomTranslate Studio** (compilado no Deck num contêiner) integrado: PS1, PS2, PSP, GBA, SNES, NES, N64, GC, DS.
  Só frases de verdade vão para a IA (a varredura genérica acha muito lixo), com o limite de espaço informado e
  encurtamento; sem acento onde o jogo não tem; `.cue` novo para PS1.
- **Tradução automática** de downloads que não estão em português (`auto_traduzir`).
- **IA do PC** pela rede (túnel SSH reverso; pulada na hora se o PC estiver desligado).
- IA mais robusta: erro passageiro não abandona o provedor rápido; teto de resposta; aspas de diálogo preservadas.
- Tarefas de tradução rodam como serviço próprio do systemd (não morrem se o bot reiniciar).
- FireRed (Switch) traduzido de ponta a ponta: 2.332 frases, 0 problemas.
- **Todos os consoles pré-prontos**: 3DS, Wii U, PS3, Xbox, Dreamcast, Saturn, Sega CD, Mega Drive, Master System,
  Game Gear, NES, Game Boy/Color, PC Engine e Arcade (emulador instalado, aba, nome no bot, controle).
- **Tradução de qualquer idioma** (russo, japonês, espanhol…): detecta a língua do jogo; tabelas cirílicas
  CP1251/CP866/KOI8-R para versões russas.
- Downloads em **RAR dividido** (`.rar` + `.r00`… ou `.partN.rar`) e CD de PS1 em **`.mdf/.mds`** (Alcohol 120%,
  com ou sem subcanal, com faixas de áudio) viram `.bin + .cue`; arquivo com nome de código (SLES_…) ganha o nome do download.

## 0.5.1 — 2026-11-09 — "Em português" sem duplicar a biblioteca
- Aba/coleção **"Em português"**: só os jogos que você pode jogar em português (PT-BR oficial do Switch,
  tradução do Deck Commander, ROMs traduzidas/dubladas pelo nome). Atualiza ao vivo; sai da aba o que deixar de estar.
- **PT-BR oficial do Switch**: lido do control.nacp (com a atualização). Esses jogos abrem com o Ryujinx em
  BrazilianPortuguese só para eles (aplicado ao abrir, devolvido ao fechar). Na biblioteca de teste: Super Mario
  Galaxy, Galaxy 2 e Castlevania Belmont's Curse.
- **Extração automática** dos textos do Switch (sem Ryujinx/hactool): leitor próprio em Python puro de
  NSP/NCA/ticket, NCA esparso e atualização (BKTR), com as chaves do próprio Ryujinx. Só leitura.
- ROM de GBA dentro de jogo de Switch (FireRed/LeafGreen) traduzida como mod (precisa do Meowth).
- Tradução retrô substitui o atalho do original (sem duplicar); `/devolver` traz de volta.
- `/traduzir lista`; jogo que já está em português é avisado em vez de traduzido de novo.

## 0.5.0 — 2026-11-09 — Tradução com IA e conversão de Switch (adições A1/A2/A3)
- `/traduzir <jogo>`: Switch vira **mod LayeredFS** do Ryujinx (jogo nunca alterado); Pokémon de GBA via
  Meowth vira ROM "(PT-BR)" + patch BPS. Validado com 552 MSBT reais (12.742 frases, 8.614 tags) lidos e
  regravados byte a byte, e tradução real com tags preservadas.
- IA em cadeia: Index-Translate-9B (padrão, grátis) → Ollama no Deck → GitHub Models → pagos (com estimativa
  e aprovação). Glossário, referências (memória de tradução + few-shot), cache para retomar, limite diário.
- Executor em segundo plano: fila, pausa na bateria e com jogo aberto, aviso no Telegram, `retomar`.
- `/converter <jogo>`: diagnóstico, `organizar` update/DLC, `descompactar` NSZ/XCZ (nsz).
- Leitores próprios sem dependências: MSBT, SARC, Yaz0, zstd (Python 3.14), BFFNT.
- Correção: o `/sync` pegava "a próxima operação da fila" em vez da sua (`store.claim`).
- `./setup-deck.sh --modules A1,A2,A3`: Ollama no $HOME + modelo, Meowth e nsz em ambientes isolados.

## 0.4.2 — 2026-11-07 (revisão para uso longe do PC)
- **Safe-mode nunca derruba o bot** (antes, entrar em safe-mode desligava o próprio bot e o `/sos off` ficava
  impossível de longe) e o `/sos off` religa exatamente o que desligou — antes o qBittorrent ficava parado.
  O bot avisa quando o safe-mode liga sozinho. Teste semanal só conta falha real (pytest ausente não conta).
- Jogo que não abre mostra o **motivo na tela** (cartão SD fora, jogo removido, emulador ausente).
- Plugin: jogo removido e baixado de novo na mesma sessão volta a aparecer (antes ficava escondido até reiniciar).
- Atualizar o plugin não exige mais reiniciar: o instalador pede ao Decky para recarregá-lo.
- Energia: download novo também pausa na bateria (antes baixava), o bot avisa, `/bateria sim|nao`;
  pausa que sobrou de antes de um reinício é retomada no carregador.
- Seeding limitado (razão 1.0 ou 60 min) para não gastar o pacote de dados do celular.
- Decky fora do ar (update do SteamOS): o `/sync` percebe e usa o caminho sem plugin (+ `/reiniciar`).
- Dolphin (GameCube/Wii) mapeado no controle do Deck quando ainda estava no teclado.
- Qualidade por jogo devolve o arquivo do emulador byte a byte igual (conferido no Deck nos 6 consoles).
- `dc x … --apply/--force/--confirm` voltaram a funcionar no terminal; `/remover` limpa também o banco.
- `/baixar` agora vale até o fim (o /sync aceita a cópia confirmada); terceira cópia com o mesmo nome vira
  "(novo 2)" em vez de entrar dentro de outra pasta; `/devolver` traz de volta jogo tirado pelo Steam.
- Busca de jogo por palavras (`/qualidade shadow dub 2x`); `/duplicados` diz se a cópia está no SD ou na memória.
- Serviços com `Restart=always`. Ferramentas de teste no aparelho: `tools/e2e_local.py`, `tools/quality_check.py`,
  `tools/bot_dryrun.py`.

## 0.4.0 — 2026-11-06
- **Duplicatas**: o bot confere antes de baixar (biblioteca e downloads em andamento; Switch pelo Title ID,
  demais pelo nome sem região/versão) e só baixa repetido com `/baixar`. O `/sync` não cria segundo atalho
  para um jogo que já existe (a cópia nova vai para a quarentena). `/duplicados` + `/remover` (com confirmação).
- **Remover jogo**: atalho sai do Steam ao vivo (plugin 0.4.0), arquivos vão para a quarentena (no SD, ficam no SD),
  download sai do qBittorrent. Atalho apagado por você no Steam **não é mais recriado** pela autocorreção.
- **Qualidade por jogo** (`/qualidade`): nativo/2x/3x/4x só para aquele jogo, aplicado ao abrir e devolvido ao fechar
  (inclusive quando o Steam fecha o jogo à força). DuckStation, PCSX2, Dolphin, PPSSPP e Ryujinx.
- **Controles**: `/controles` verifica cada emulador; layout do Switch por rótulo (A=A) aplicado pelo instalador.
- Correções de brechas: extração longa (>5 min) não perde o registro (antes podia gerar cópia "(novo)") nem conta
  como travamento; falta de espaço não manda o download para a quarentena (avisa e tenta de novo); ROM com o mesmo
  nome de um jogo da Epic/GOG entra com o console no nome; atalho manual com o mesmo nome agora é avisado.

## 0.3.0 — 2026-11-06
- Plugin do Decky 0.3.0: espera o Steam terminar de carregar antes de criar atalhos (corrige atalho
  perdido no reinício), autocorreção (recria atalhos sumidos), trava contra duplicação.
- Abas ao vivo: uma **coleção do Steam** por console/loja, mantida pelo plugin; TabMaster filtra por coleção.
- Abas por loja do Unifideck (Epic Games, GOG).
- Bot: aceita "Switch"/"PS2"… + `.torrent` encaminhado ou magnet solto; /sync automático ao terminar o download.
- Switch 2 (experimental, via Lichii) com dumps extraídos.
- Detecção automática de emuladores (EmuDeck, AppImage, Flatpak); conta Steam ativa em Decks com várias contas.
- /sync usa hardlink no mesmo disco (não duplica GBs).
- `dc x profile` (perfis de qualidade PS1/PS2), `dc x dedup` (relatório de duplicatas, nunca apaga).
- `dc restore --apply` fecha e reabre o Steam quando necessário.
- /sync abre **.7z e .rar** (7-Zip do SteamOS) com as mesmas regras de segurança do .zip; `.mdf` de PS2 vira `.iso`.
- Download que não entrou na biblioteca é tentado de novo sozinho (1x por hora, avisa só se entrar).

## 0.2.0
- Projeto v5.1 completo: segurança (M0), Operation Store (M18/M19), contratos (M27), biblioteca (M2),
  qualidade (M3), Telegram/torrent (M4), traduções IPS/BPS/UPS (M5), saves (M6), disco (M7),
  sensores (M20), diagnóstico (M21), status/testes (M10), updates (M11), setup/uninstall (M12/M15),
  recuperação (M16), privacidade/export (M17).

## 0.1.0
- Spikes S1–S6 e S10 validados (PC + Steam Deck LCD).
