# Soul Calibur III (PS2, versão russa "RUS NTSC") — engenharia reversa para PT-BR

Pedido do usuário em 14/11/2026 ("se precisar fazer engenharia reversa pode fazer"). Não existe tradução de fãs
PT-BR (procurado no Hugging Face do João13, romhacking.net.br e buscas gerais). A tradução genérica por IA
(RomTranslate) falhou: achou texto de vários idiomas misturado.

## Disco
- ISO de 4,5 GB, código `SLUS_212.16`. 17 arquivos; quase tudo em `ROOT.OLK` (1,7 GB, LBA 612612).
  Outros: `BGM.AFS`, `MOVIE.AFS`, `VOICE.AFS`, `SE.AFS`, `SLUS_212.16` (programa), `FLISTD.TXT`.

## Formato do pacote "olnk" (ROOT.OLK e os pacotes dentro dele)
- Cabeçalho (16 bytes): `u32 n` · `"olnk"` · `u32 0x800` · `u32 0`.
- Depois, `n+1` linhas de 16 bytes: `u32 posição` · `u32 tamanho` · `u32 data` · `u32 0`.
  - Linha 0: a posição é o INÍCIO DOS DADOS (tamanho da tabela, ex.: 0x800 ou 0x3800).
  - Linhas 1..n: arquivo em `início_do_pacote + início_dos_dados + posição`, com `tamanho` bytes (tamanho 0 = vaga).
- Pacotes ficam dentro de pacotes (ex.: entrada 3 do ROOT.OLK = pacote em 0x897000, 0x11DAC000 bytes).

## Arquivos de mensagens
- Ex.: ROOT.OLK → entrada 3 → entrada 10 (em 0xAED800, 0x10900 bytes): menus e descrições.
- Começam com `u32 8` (8 blocos de idioma) e as posições de cada bloco (`0x80`, `0x1180`, `0x1800`…).
- Cada bloco: tabela de posições (`u32`) + frases terminadas em `\0`.
- Há blocos em coreano (UTF-8), francês, espanhol etc.

## Como o russo foi feito (descoberto pela memória do jogo)
- No menu, a memória do PS2 (save state do PCSX2 → `eeMemory.bin`) tem "режим одного игрока." gravado como
  `pegnm 0dh0f0 nfp0ka.`: os tradutores DESENHARAM letras cirílicas no lugar das latinas da fonte e escreveram o
  russo com os códigos latinos. Mapeamento visto: р→p, е→e, ж→g, и→n, м→m, о→0 (zero), д→d, н→h, г→f, к→k, а→a.
- Achado por "busca de padrão" (mesmas letras nas mesmas posições), porque não é nenhuma codificação russa
  conhecida nem ordem alfabética nem do teclado.

## Consequência para o PT-BR
- O bloco que o jogo mostra (o inglês, sobrescrito pelo russo) não tem mais o texto original; os blocos francês e
  espanhol estão intactos → traduzir do ESPANHOL (mais perto do português).
- A fonte precisa voltar a ter letras latinas + acentos do português (ç, ã, õ, á, é, í, ó, ú, â, ê, ô, à): achar a
  textura da fonte e redesenhar.

## Teste no Deck
- O PCSX2 do Deck só tem o controle (SDL) ligado: para navegar por teclado (xdotool), ligar temporariamente
  `Keyboard/Return` (Start), `Keyboard/Z` (X) e setas no `[Pad1]` do `PCSX2.ini` e DEVOLVER depois.
- O jogo leva ~70 s até o menu (abertura longa).

## Arquivos de mensagens por idioma (pacote 3 do ROOT.OLK, em 0x897000)
| entrada | posição no ROOT.OLK | idioma |
|---|---|---|
| 10 | 0xAED800 (0x10900 bytes) | inglês — TODO sobrescrito pelo russo (8 conjuntos: sistema, menus, opções…) |
| 11 | 0xAFE800 | francês (Latin-1: é = 0xE9) |
| 12 | 0xB11000 | italiano |
| 13 | 0xB23800 | alemão |
| 14 | 0xB35800 | espanhol → base para o PT-BR |
| 15 | 0xB48000 | coreano (UTF-8) |
| 16 | 0xB50000 | japonês |
Cada arquivo: `u32 8` + 8 posições de conjunto; cada conjunto: `u32 1`, `u32 n`, … tabela de posições + frases `\0`.

## Fonte (em andamento)
- Entradas 18 e 19 do pacote 3 (0xB61800 e 0xBA3000, 0x41600 bytes cada, conteúdos diferentes): `u32 2` + posições
  0x80 (textura, 0x40500 bytes) e 0x40580 (dados das letras, magia `A5 53 63 46`).
- A textura é um pacote GIF: imagem enviada como PSMCT32 512×128 em DBP 0x37F0, DBW 8 (256 KB); paleta de 16 cores
  em 0x37ED (64 bytes) → textura de 4 bits. Ler como PSMT4 1024×512 (TBW 16) ou 512×1024 (TBW 8) com as tabelas do
  GS (`tools/gs_memoria.py`, conferidas com `pcsx2/GS/GSTables.cpp`) ainda sai embaralhado; as camadas de 4 bits
  (PSMT4HL/HH) também. Próximo passo: achar o TEX0 real (registrador da textura) no programa ou na memória do GS na
  hora em que o menu está na tela, ou testar se os dados da textura são comprimidos.
- No save state, a memória de vídeo (GS.bin) começa 9 bytes depois do início do arquivo; a região 0x37F0 bate só em
  parte com os arquivos 18/19 (o jogo pode reaproveitar a região).
- Material salvo no Deck: `~/Emulation/downloads/comunidade/ps2-soul-calibur-3-rus/engenharia/` (memória do jogo no
  menu russo, GS.bin, fontes 18/19, save state).

## O que falta (estimativa honesta: vários dias de trabalho)
1. Decodificar a textura e o formato das letras (FcS) e redesenhar a fonte com letras latinas + acentos do PT.
2. Traduzir o arquivo do espanhol (entrada 14) para PT-BR com a IA e gravar no lugar do inglês (entrada 10), com as
   tabelas de posição refeitas; o espaço de cada arquivo no pacote é fixo (ou refazer o pacote inteiro).
3. Achar os textos das histórias (Tales of Souls, Chronicles of the Sword — prováveis entradas 38–44, `u32 0x0b`).
4. Testar no Deck (menu, uma luta, uma história).
