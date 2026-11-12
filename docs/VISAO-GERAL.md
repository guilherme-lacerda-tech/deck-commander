# Deck Commander — Visão geral do projeto

Tudo o que o sistema faz hoje, o que foi testado de verdade, os limites conhecidos e ideias do que adicionar.
Situação em 12/11/2026, versão 0.8.2. São 804 testes automáticos passando, 247 versões salvas no histórico e cerca de
30 mil linhas de código em 119 módulos. O repositório é público: github.com/guilherme-lacerda-tech/deck-commander.

> **Legenda:**
> - ✅ funcionando e testado de verdade no Deck ou no PC
> - 🧪 pronto e com testes automáticos, mas ainda sem uso real
> - ⚠️ funciona com limitação
> - 🆕 novo desde o último relatório (11/11, versão 0.7)

---

## 1. Em uma frase
O Deck Commander transforma o Steam Deck numa central de jogos. Você manda um link pelo Telegram, ou toca num botão no
Deck, e o jogo:
- baixa sozinho;
- entra na biblioteca do Steam com capa e na aba do console;
- já vem configurado, ajustado e traduzido para português.

Além disso, ele conversa com o seu PC: dá para jogar os jogos do PC no Deck e levar jogos e saves de um lado para o
outro. Também conversa com o Deck do seu irmão e toca a sua música.

## 2. Como se usa (as três portas de entrada)
| Porta | Para quê | Situação |
|---|---|---|
| **Telegram** (seu bot) | Baixar, traduzir, organizar, ver status de qualquer lugar | ✅ |
| **Painel no Deck** (botão "…" → Decky → Deck Commander) | Tudo pelo controle, sem Telegram nem terminal | ✅ |
| **Assistente no PC** (`tools\pc\Assistente Deck Commander.bat`) | Ligar o PC ao Deck, emuladores, transferências, biblioteca do PC | 🧪 partes testadas; a janela ainda não foi usada por você |

Telas do painel:
- Telegram;
- Downloads;
- Tradução;
- Computador;
- Transferências;
- 🆕 Música;
- 🆕 Família;
- Qualidade e controles;
- 🆕 Retrô (botões de trás, turbo e filtros de tela);
- Melhorias;
- 🆕 Espaço;
- Desinstalar;
- Diagnóstico;
- Modo seguro.

---

## 3. Biblioteca do Steam
- ✅ **Atalho com capa e aba:** cada jogo de emulador vira um jogo no Steam, com capa (SteamGridDB) e na aba do console
  (TabMaster).
- ✅ **Entra ao vivo** pelo plugin do Decky, em ~10 s, sem reiniciar o Steam. Se um atalho sumir sem querer, ele é
  recriado.
- ✅ **Abas automáticas:**
  - uma por console;
  - uma por loja (Epic/GOG pelo Unifideck);
  - "Em português";
  - "Computador";
  - "Emuladores".

  Aba vazia fica escondida.
- ✅ **28 consoles reconhecidos**, do NES ao Switch 2, incluindo PS1–PS3, PSP, Xbox/360, Wii/Wii U, Dreamcast, Arcade e
  PC.
- ✅ **Atalho fixo por jogo:** trocar a ROM, o formato ou o emulador não perde horas jogadas, capa nem coleções.
- ✅ **Vários discos, update e DLC:** jogos com vários discos viram um atalho só, e atualização e DLC de Switch entram
  sozinhas.

## 4. Downloads
- ✅ **Basta o link:** mande o console e o `.torrent` ou magnet. Quando termina, o jogo entra na biblioteca e o bot
  avisa.
- ✅ **Avisos e recusas:**
  - avisa antes de baixar um jogo repetido;
  - recusa link inválido;
  - não duplica o mesmo magnet.
- ✅ **Bateria:** na bateria os downloads esperam a tomada (`/bateria sim` libera). Abaixo de 30%, sempre pausam.
- ✅ **Download travado:** o bot avisa se ficar 30 min parado ou der erro (disco cheio, cartão SD removido).
- ✅ **Pelo painel:** pausar ou retomar, e limpar o histórico.

## 5. Tradução para português (o coração do projeto)
### 5.1 Como funciona
- ✅ **Automática:** baixou um jogo que não está em português, ele entra na fila e chega traduzido. Avisa a cada 20%.
- ✅ **Ordem de preferência:**
  1. já em português (oficial, inclusive o PT-BR escondido dentro do jogo);
  2. tradução da comunidade;
  3. IA.
- ✅ **IAs grátis**, nesta ordem: Index-Translate na internet, a IA do seu PC (pela placa de vídeo, por túnel seguro)
  e a IA do próprio Deck (sem internet).
- ✅ **Nunca estraga o jogo:**
  - Switch vira mod;
  - retrô vira uma cópia "(PT-BR)";
  - os códigos de cor e de variáveis do texto ficam protegidos;
  - tudo é conferido antes de instalar.
- ✅ **2ª chance:** frase quebrada é refeita, e frase que não cabe na caixa é encurtada.
- 🆕✅ **Glossário por franquia:** nomes de personagens, golpes e lugares ficam iguais em todos os jogos da mesma série
  (Pokémon, Zelda, Mario…).
- 🆕🧪 **Corrigir uma frase:** mande a foto da frase estranha com `/corrigir <jogo>`. A IA do PC lê a imagem, acha a
  frase e corrige só ela.

### 5.2 O que já foi traduzido de verdade
| Jogo | Formato | Resultado |
|---|---|---|
| Pokémon Legends Z-A | Trinity (Oodle) | ✅ 75.152 frases |
| Zelda: Breath of the Wild | MSBT dentro de SARC | ✅ 27.220 frases |
| Final Fantasy Resonance | Unreal Engine | ✅ 24.717 frases |
| Luigi's Mansion 3 | init.patch | ✅ mod instalado |
| Pokémon FireRed / LeafGreen (GBA no Switch) | Meowth | ✅ |
| Castlevania Belmont's Curse | Unity | ✅ já tinha PT-BR oficial, configurado para abrir em português |
| 🆕 Castlevania: Symphony of the Night (PS1) | formato próprio, por engenharia reversa | ✅ falas e menus com acento (fonte nova), botões da tela de arquivos em português, patch .bps de 57 KB |
| 🆕 Zelda: Tears of the Kingdom | PT-BR oficial + dublagem | ✅ abre em português, com 360 falas das cenas dubladas |

### 5.3 Formatos que o sistema lê
- ✅ **Testados com jogo real:** Nintendo MSBT, SARC, Trinity, Next Level Games, Unreal (sem criptografia) e Unity.
- 🧪 **Prontos, ainda sem jogo real:** GameMaker, Godot, RE Engine (Capcom), RPG Maker MV/MZ e CRI. Eles perguntam
  antes, mostrando quantas frases o jogo tem e quanto tempo leva.
- ✅ **Retrô** (PS1, PS2, PSP, SNES, NES, N64, GameCube, DS, GBA), pelo RomTranslate Studio.
- 🆕✅ **Patch para compartilhar:** tradução de cartucho e de disco gera também um arquivo `.bps` (um patch pequeno).
  Quem tem o jogo original aplica com o Floating IPS e fica com a mesma tradução, sem você mandar o jogo.
- 🆕✅ **Vídeos com legenda:** cenas em vídeo sem legenda ganham legenda em português (dublar é opcional).
- ⚠️ **Não traduz:** Unreal com pacote criptografado (seria quebrar a proteção do jogo) e formatos ainda
  desconhecidos. No Hercules, por exemplo, o painel explica o motivo.

## 6. Qualidade, desempenho, energia e controles
- ✅ **Resolução:** perfil por console e exceção por jogo (nativo / 2x / 3x).
- ✅ **Auto-ajuste:** sobe a qualidade quando o jogo roda liso e desce na primeira travada.
- ✅ **Medição:** benchmark sem jogar e medição real de cada partida (MangoHUD).
- 🆕✅ **Energia (TDP) por console:** aplicada ao abrir o jogo e devolvida ao fechar. Na dock ou TV, usa o máximo.
  Testado: 12 W → 7 W → 12 W.
- 🆕🧪 **Shaders à noite:** compila shaders na tomada, com o Deck parado, para o jogo não engasgar na primeira vez.
- 🆕✅ **Melhorias por emulador** (painel → Melhorias): widescreen, 60 FPS, filtros e outras opções conhecidas, ligadas
  e desligadas com um toque.
- ✅ **Controles:** "Controle de Xbox" ou "Controle de Switch" no Ryujinx e no Lichii. Dolphin e melonDS são
  configurados sozinhos.
- 🆕✅ **Perfil de controle do stream do PC:** salvo e reaplicado sozinho.
- ⚠️ **Controle manual:** Azahar (3DS), Cemu (Wii U) e RPCS3 (PS3) pedem que você escolha o controle uma vez no modo
  Desktop.

## 6.1 Jogos retrô de verdade 🆕
Feito pensando em quem joga retrô a sério (revisão de "retrogamer" em 12/11).
- ✅ **Botões de trás** em todo jogo de RetroArch, DuckStation (PS1), PCSX2 (PS2) e Dolphin (GameCube/Wii):
  - **L4** salva o estado (save rápido);
  - **R4** carrega o mais novo;
  - **L5** (segurando) volta no tempo;
  - **R5** liga/desliga o turbo (2x, 3x ou 4x).

  Cada jogo recebe esse layout **uma vez**. Se você trocar o layout de um jogo, ninguém sobrescreve.
- ✅ **Save rápido que não apaga o anterior:** o RetroArch guarda os 10 últimos; o DuckStation guarda cópia do anterior.
- ✅ **Cópia automática dos saves:** antes de cada vez que um jogo abre, os saves dele (o do jogo e os rápidos) são
  copiados. Ficam as 5 últimas cópias em `~/Backups/DeckCommander/saves/<jogo>/`. Voltar: `/saves copias <jogo>` e
  `/saves voltar <jogo> <n>` (o save de agora vira cópia antes). Medido no Deck: menos de meio segundo por jogo.
- ✅ **Save do cartucho gravado na hora:** o RetroArch grava a bateria do cartucho a cada 10 s, não só ao fechar.
- ✅ **Aviso de emulador atualizado:** se o emulador mudou de versão, aparece um aviso ao abrir o jogo (save rápido
  antigo pode não abrir; o save do jogo sempre abre).
- ✅ **Atraso de controle menor:** run-ahead de 1 quadro nos consoles leves (NES, SNES, Mega Drive, GB/GBA, Arcade,
  PC Engine); desligado no N64 e no Saturn, onde pesa.
- ✅ **Filtros de tela:** TV antiga (zfast-crt, feito para tela de portátil) e grade de LCD nos portáteis.
- ✅ **DuckStation a 100%:** a camada de vídeo do modo de jogo segurava o PS1 em 60% da velocidade; agora abre sem ela.
- ✅ **Seguro na rede:** a porta de comandos do RetroArch (que aceitava comandos de qualquer aparelho do Wi-Fi) está
  fechada, e o modo "hardcore" das conquistas não tira mais o save rápido sem aviso.
- ⚠️ **Conquistas (RetroAchievements):** funcionam nos 4 emuladores depois de você entrar na sua conta em cada um.
  A Steam não deixa mostrar conquistas de atalhos de fora; elas aparecem na tela do jogo e no site
  retroachievements.org.

## 7. Música (Spotify) 🆕
- ✅ **Volume separado** do jogo e da música, e controle (tocar/pausar/próxima) pelo painel e pelo `/musica`.
- ✅ **Playlists rápidas:** cole o link de uma playlist no bot ou no painel e ela vira um botão.
- ✅ **Suas playlists no painel e no bot:** a aba Música mostra as playlists da sua conta. Elas tocam com o jogo aberto,
  e você não precisa abrir o Spotify: o app oficial abre escondido, sem janela. Testado no Deck em 11/11, com 50
  playlists. Também dá para pedir pelo nome no Telegram: `/musica funk`.
- ✅ **Entrar na conta uma vez:** Música → "Conectar Spotify". Leia o QR com o celular e confirme (ou mande
  `/musica conectar` no bot). Ninguém vê sua senha. A lista se atualiza sozinha a cada 6 h, ou pelo botão
  "Atualizar lista".
- ⚠️ **O Spotify só toca pelo app oficial.** Ele recusa o som para players não oficiais, e contornar isso seria quebrar
  a proteção dele. Por isso o player de código aberto (go-librespot) serve só para a conta e a lista, e fica ligado
  apenas alguns segundos. Precisa de Premium e de internet na hora de tocar.

## 8. Organizar, espaço e desinstalar
- ✅ **Duplicados:** `/duplicados` lista e remove os repetidos.
- 🆕✅ **Desinstalar o Deck Commander tira tudo:** atalhos, layouts e teclas dos botões de trás, protetor de tela,
  serviços e o código. No fim, o Decky pergunta na tela se tira o plugin também. ROMs e saves nunca são tocados.
- ✅ **Desinstalar um jogo como no Steam:** "Gerenciar → Remover" pergunta se apaga os arquivos também. Funciona também pelo
  painel ou pelo Telegram, e os arquivos ficam 30 dias na quarentena.
- 🆕✅ **Espaço:** o painel lista os jogos grandes que você não abre há tempo e quanto liberaria. Ele só sugere, nunca
  apaga sozinho.
- ✅ **Conversão de Switch:** confere update e DLC, organiza e descompacta NSZ.

## 9. Jogar os jogos do PC no Deck (aba "Computador")
- ✅ **Jogos achados sozinhos:** Steam, Epic, Riot, GOG, Ubisoft e Xbox, mais qualquer atalho colocado na pasta
  "Jogos do PC". Hoje são 14 jogos.
- ✅ **Acordar e dormir:** acorda o PC, inclusive de fora de casa, e ele volta a dormir ~2 min depois de fechar o jogo.
- ✅ **Stream:** Sunshine (PC) + Moonlight (Deck).
- 🆕🧪 **Jogar na TV** (`/pc tv` ou botão): o PC liga a TV e transmite.
- 🧪 **Falta o teste de ponta a ponta** com um jogo de verdade.

## 10. Levar jogos e saves entre o Deck e o PC
- ✅ **Deck → PC:** vai tudo:
  - o jogo, update e DLC;
  - saves e mods;
  - a configuração e os controles do emulador;
  - keys, firmware e BIOS.

  Cada arquivo é conferido (sha256), a cópia retoma se cair e nada é apagado no Deck. Testado com Donkey Kong
  Bananza: 19,7 GB, 166 mil arquivos.
- 🆕✅ **PC → Deck** (`/trazer`): se o emulador faltar no Deck, instala o oficial junto.
- 🆕✅ **Saves iguais nos dois lados** (`/saves <jogo>`):
  - vale o mais novo;
  - se os dois mudaram, você escolhe qual lado vale;
  - backup antes de trocar;
  - leva 2,8 s.
- 🆕🧪 **Saves automáticos:** ao fechar um jogo que já foi sincronizado uma vez, os saves entram na fila e o PC iguala
  quando estiver ligado. Ele só avisa se der conflito (`/saves auto sim|nao`).
- 🆕🧪 **Progresso da cópia** no painel e no bot ("copiando 1.200/5.000 arquivos, 3,1 de 9,8 GB").
- 🆕🧪 **Aviso de cópia parada:** se um pedido ficar 30 min sem sinal (PC desligado ou sem rede), avisa uma vez, com o
  botão "Acordar PC".
- 🆕🧪 **Backups de save:** ficam os 5 mais novos de cada save, nos dois lados.

## 11. Família (Deck do seu irmão) 🆕
- 🧪 **Pareamento:** os dois Decks se pareiam por chave (`/familia par`, `/familia autorizar`). Quando o Deck dele fica
  online, o seu avisa.
- 🧪 **Catálogo:** você vê o que ele tem e "puxa" o jogo. Isso põe o **link magnet** na sua fila de downloads e copia o
  **pacote de tradução pronto**. Nenhum arquivo de jogo é enviado entre os Decks; uma trava automática garante isso.
- 🧪 **Tradução aplicada sozinha:** quando o download termina, a tradução é aplicada (mods, glossário, patches).

## 12. Segurança, confiança e saúde
- ✅ **Backup diário** de configurações e saves, com teste de restauração.
- ✅ **Quarentena de 30 dias:** nada é apagado sozinho.
- ✅ **Modo seguro e diagnóstico** (`/sos`, painel).
- ✅ **Testes:** 804 testes automáticos. Rodam toda semana no Deck e antes de toda atualização.
- 🆕✅ **Revisão ao vivo:** depois de toda atualização, 14 conferências no próprio Deck (serviços, painel, botões de
  trás, Castlevania, Zelda, IA, Tailscale, protetor de tela, Spotify, espaço…). Hoje: 14 de 14.
- 🆕✅ **Painel mais leve na bateria:** a checagem dos botões de trás passou de 1 por minuto para só quando entra jogo
  novo (e uma a cada 30 min).
- 🆕✅ **Atualização segura** (`tools/implantar.py`): só instala se os testes passarem no PC e no Deck. Se algo falhar,
  o Deck continua na versão anterior.
- 🆕🧪 **`/voltar`:** desfaz a última atualização com um toque. Os jogos e as configurações não mudam.
- 🆕✅ **11 travas contra falhas antigas.** Cada erro que já aconteceu virou um teste que impede a volta (lista em
  `docs/LICOES.md`).
- 🆕✅ **Revisão noturna:** 66 revisões da IA local, todas conferidas, e 6 falhas reais corrigidas (relatório próprio
  em PDF).
- ✅ **Nenhum segredo nem endereço da sua casa no código**, e há teste automático para isso.

## 13. Instalação e distribuição
- ✅ **Instalação em 1 comando** no Deck, com QR para criar o bot do Telegram.
- ✅ **Documentos e assistente:** tutorial, manual, esta visão geral e o relatório da revisão em PDF, mais o assistente
  gráfico no PC.
- ✅ **Repositório público:** cada pessoa configura a própria rede.
- 🆕🧪 **Guia do Fire Stick** (`docs/FIRE-STICK.md`): jogar o PC na TV da sala pelo Fire Stick.

## 14. Integração com a sua casa
- ✅ **O PC não dorme no meio do trabalho:** o agente da casa segura o PC acordado durante uma transferência e o devolve
  ao sono depois.
- ✅ **Sem janela piscando:** as tarefas do PC rodam escondidas.

---

## 15. O que mudou desde o último relatório (11/11 → 12/11)
**Versão 0.8.0 — retrô e revisão de lançamento**
- botões de trás, turbo, voltar no tempo e filtros de tela nos jogos retrô;
- Castlevania: Symphony of the Night em português, com acentos;
- Zelda: Tears of the Kingdom em português e dublado;
- legenda em português nos vídeos;
- desinstalar que tira tudo;
- erro ao abrir jogo explicado na tela (antes, todo erro dizia "jogo removido");
- correção de uma disputa entre o plugin e o `/pc sincronizar` (a marca de um jogo podia ser apagada).

**Versão 0.8.1 — revisão de retrogamer**
- porta de comandos do RetroArch fechada e "hardcore" desmarcado;
- aviso de emulador atualizado;
- patch `.bps` das traduções de disco.

**Versão 0.8.2 — saves que não se perdem**
- cópia automática dos saves (5 últimas), com `/saves copias` e `/saves voltar`;
- save do cartucho gravado a cada 10 s.

## 15.1 O que ainda falta (com honestidade)
**Testes que só você faz, com as mãos no Deck**
- jogar e conferir os botões de trás num jogo retrô;
- as falas do Castlevania em português dentro do jogo;
- uma cena dublada do Zelda;
- um jogo do PC transmitido para o Deck, do começo ao fim;
- a desinstalação completa (não foi rodada no seu Deck, para não desmontar nada).

**Prontos, mas sem uso real ainda**
- Família (Deck do seu irmão), jogar na TV, assistente do PC, `/corrigir` por foto.
- Cópia automática dos saves no RetroArch: testada no PC; no Deck ainda não há jogo de RetroArch.

**Limites que não dependem do Deck Commander**
- Conquistas retrô não aparecem na página do jogo da Steam (a Steam só permite isso para jogos vendidos nela).
- O Spotify só toca pelo app oficial.
- Jogos com pacote criptografado não são traduzidos.

**Não feito**
- Deck OLED (tela de 90 Hz): falta um OLED para testar o ajuste de 60 quadros.
- Trapaças (começado, não ligado no painel) e benchmark reproduzível.
- Tradução por IA não tem revisão humana: frases estranhas se corrigem com `/corrigir`.

## 16. Ideias do que adicionar
**Mais fácil de usar**
1. Tela com **capa, tamanho e tempo jogado** de cada jogo, com ações rápidas (traduzir, qualidade, levar para o PC,
   desinstalar).
2. **Notificação na tela do Deck**, além do Telegram, quando um download ou uma tradução termina.
3. **Modo criança:** painel só com "jogar", sem as telas de configuração.
4. **Atualizar pelo painel** com um botão, com página de novidades.

**Saves e nuvem**
5. **Cópias dos saves no painel** (hoje é pelo bot), com "voltar para ontem" num toque.
6. **Aba de conquistas** (RetroAchievements) no painel, com o progresso de cada jogo.

**Tradução**
7. **Legendas de cutscenes** com IA local.
8. Tradução feita **pelo PC** quando ele estiver ligado (mais rápida), devolvendo o mod para o Deck.
9. Novos formatos conforme aparecerem jogos (VX Ace, Godot otimizado, RE Engine com zstd).

**Música**
10. **Música por jogo:** uma playlist que começa sozinha ao abrir um jogo (ex.: lo-fi no Stardew).
11. Baixar playlists para ouvir **sem internet**. O Spotify só permite isso no app oficial, então seria pelo app.

**PC e casa**
12. **Fila agendada para a madrugada** (transferências grandes).
13. Gravar os **melhores momentos** do jogo (clipe de 30 s) e mandar no Telegram.
