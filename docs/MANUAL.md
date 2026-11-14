# Manual do Deck Commander

Versão 0.9.0 · 14/11/2026. Este manual serve para quem usa no dia a dia e para quem vai explicar a outra pessoa.
Instalação num Deck novo: [TUTORIAL-INSTALACAO.md](TUTORIAL-INSTALACAO.md).
Testes que só dão para fazer com o Deck na mão, em 6 sessões curtas: [TESTES-NO-DECK.md](TESTES-NO-DECK.md).

---

## 1. O que é, em uma frase
Você manda um link de jogo pelo Telegram (ou toca num botão no Deck). O Deck baixa, coloca o jogo na biblioteca do
Steam com capa, ajusta a qualidade e traduz para português, tudo sozinho.

## 2. Como funciona por dentro (o que contar para quem vai usar)
Pense em cinco peças:

| Peça | Onde roda | O que faz |
|---|---|---|
| **Bot do Telegram** | no Deck, sempre ligado | recebe o que você manda, responde e avisa quando algo termina |
| **qBittorrent** | no Deck, escondido | baixa os jogos (só ele fala com a internet de torrent) |
| **Organizador** (`/sync`) | no Deck | descompacta, descobre o console, coloca o jogo na pasta certa e cria o atalho |
| **Plugin do Decky** | dentro do Steam | faz o atalho aparecer na hora (sem reiniciar o Steam), põe capa e a aba do console; é também o **painel** |
| **Tradutor** | no Deck (e no PC, se ligado) | tira os textos do jogo, traduz com IA e instala como mod ou cópia "(PT-BR)" |

O caminho de um jogo:

1. Você manda `Switch` e depois o `.torrent` ou o magnet.
2. O bot confere se é um link válido e se o jogo já existe. Se já existir, ele avisa antes de baixar.
3. O qBittorrent baixa o jogo. Na bateria ele espera a tomada; com menos de 30% de bateria ele sempre pausa.
4. Quando o download termina, o organizador descompacta e reconhece o console.
5. O plugin cria o atalho, com capa, na aba do console.
6. Se o jogo não está em português, ele entra sozinho na fila de tradução. O bot avisa a cada 20% e quando acaba.
7. Ao abrir o jogo, o atalho chama o `dc-launch`. Ele:
   - escolhe o emulador;
   - ajusta a resolução e a energia (e o modo dock, se houver monitor);
   - guarda uma cópia dos saves;
   - ao fechar, devolve tudo como estava.

**Por que nada se estraga:**
- O jogo original nunca é alterado. No Switch, a tradução é um mod; no retrô, é uma cópia nova.
- Nada é apagado sem pedir confirmação, e o que você remove fica 30 dias numa quarentena.
- Toda atualização do sistema roda mais de 800 testes antes de entrar no Deck e confere 14 itens no próprio Deck depois.
  Se algo falhar, o Deck continua na versão anterior. Para desfazer uma atualização: `/voltar`.

## 3. Baixar um jogo
1. Mande o nome do console: `Switch`, `PS2`, `PS1`, `GBA`, `SNES`, `Wii`…
2. Encaminhe o arquivo `.torrent` ou cole o link `magnet:`. Também vale tudo numa mensagem só: `PS2 magnet:?xt=…`.
3. Pronto. O bot avisa quando terminar, e o jogo aparece na aba do console, com capa.

**Console errado ou esquecido:**
- Mandou o arquivo **sem** dizer o console? O bot pergunta na hora. Responda só o nome (ex.: `PS1`): vale para
  **esse** download. Para o próximo, mande o console de novo antes do link.
- O nome do próprio download vale mais que o console dito antes. Ex.: você disse `PS1` e encaminhou
  "(PS2)Darkwatch": o bot baixa como PS2 e avisa.
- Errou mesmo assim? Cada download mostra "Console errado? `/console <código> <console>`". Funciona enquanto ele
  ainda está baixando (também pelo nome: `/console darkwatch ps2`).
- PS1 e PS2 são conferidos pelo próprio disco na hora de ir para a biblioteca: um jogo de PS2 marcado como PS1 vai
  para a aba do PS2 sozinho, e o aviso diz isso.

| Situação | O que acontece |
|---|---|
| Jogo repetido | O bot avisa **antes** de baixar. Quer mesmo assim: `/baixar` |
| Link incompleto, arquivo que não é `.torrent`, console que não existe | O bot explica o que está errado e não baixa |
| Torrent sem ninguém compartilhando | Depois de 30 min o bot avisa; os outros downloads continuam andando |
| Disco cheio ou cartão SD fora | O bot avisa; libere espaço ou recoloque o cartão e mande `/resume` |
| Na bateria | Espera a tomada. Liberar: `/bateria sim` |
| O bot perguntou o console | Responda só o nome do console, ou `/console <código> <console>` (o código vem na pergunta) |

Fila: `/queue` · `/pause` · `/resume` · `/disk` (espaço).

## 4. Encontrar e jogar
- Cada console tem a **sua aba** (PlayStation 2, Nintendo Switch…). Aba vazia fica escondida.
- **Em português:** tudo que já está em português (oficial, traduzido ou dublado).
- **Computador:** os jogos do PC (seção 9).
- O jogo novo não apareceu? Espere uns 10 segundos. Se ainda não vier, mande `/sync`, e em último caso `/reiniciar`
  (reinicia o Steam).

## 5. Na TV ou no monitor (modo dock)
Ligue o Deck no monitor ou na TV (cabo USB-C → HDMI ou dock) e abra o jogo normalmente. O Deck Commander percebe o
monitor **no momento em que o jogo abre** e:
- coloca a **energia no máximo** do Deck (a dock fica na tomada, então pode);
- **sobe a resolução** para a imagem ficar nítida na tela grande:

  | Console | Na dock |
  |---|---|
  | PS1 | 4x |
  | PSP e 3DS | 3x |
  | PS2, GameCube e Wii | 2x |
  | Switch | já roda em modo dock, 1080p |

- quando o jogo fecha, **volta** tudo para o modo portátil.

Detalhes que valem saber:
- A resolução só sobe. Se você já deixou um jogo mais alto (`/qualidade <jogo> 5x`), ele fica como está.
- Jogar na dock não muda o auto-ajuste do portátil, porque a energia e a tela são outras.
- Ligou o monitor com o jogo já aberto? Feche e abra o jogo de novo.
- Use um controle de verdade: Bluetooth (Xbox ou PlayStation) ou USB na dock. Pareie em Configurações → Bluetooth.
- Não quer o modo dock? No Deck, crie o arquivo `~/.config/deck-commander/dock-desligado`.

**Como conferir que funcionou:** abra um jogo de PS1, PS2 ou GameCube com o monitor ligado. A imagem fica bem mais
nítida do que no portátil, e o log mostra a linha "monitor/TV ligado: modo dock":

```bash
tail -5 ~/.local/state/deck-commander/launch.log
```

## 6. Tradução para português
- **Primeiro a tradução feita por fãs (regra desde 14/11/2026):** todo jogo novo que não está em português vai
  antes para a fila "procurar tradução da comunidade". Quem procura é uma **tarefa agendada no PC** (a cada 2 h,
  enquanto o app do Claude estiver aberto; se o PC estava desligado, ela roda assim que ele ligar). Ela:
  - procura em sites de tradução brasileiros (João13, romhacking.net.br, PO.B.R.E. e outros);
  - baixa **só o patch** (nunca o jogo) e confere se ele é para a mesma versão do seu disco (ex.: SLUS-00594);
  - aplica, coloca o jogo "(PT-BR)" na biblioteca no lugar do original e avisa no Telegram.
  - Se o site só entrega o arquivo com clique no navegador, o bot avisa com o link: baixe pelo navegador do PC e
    salve em `Downloads\deck-traducoes`. Na próxima rodada a tarefa aplica.
  - Não existe tradução de fã? A IA traduz, como antes. Se o PC ficar 72 h sem procurar, a IA também começa.
  - Fila no Deck: `python3 -m dc.traducao.comunidade listar`.
- **Automática (IA):** o jogo que não tem tradução de fã entra na fila da IA sozinho.
- **Manual:** `/traduzir <jogo>`. Para traduzir todos os jogos de uma vez: `/traduzir biblioteca` (ele pergunta antes).
- **Motor diferente** (Unity, GameMaker, Godot, RE Engine, RPG Maker, CRI): o bot pergunta antes, com o número de
  frases e o tempo estimado. Responda Sim ou Não.
- **Acompanhar e controlar:**
  - `/traduzir status` mostra o andamento e `/traduzir lista` mostra os jogos;
  - `/traduzir desfazer <jogo>` desfaz a tradução;
  - se a tradução ficar 45 min parada, o bot avisa. `/traduzir parar <código>` libera a fila, e
    `/traduzir retomar <código>` continua de onde parou.
- **Frase estranha:** mande a foto com `/corrigir <jogo>`.
- **Switch:** a tradução é um mod. O jogo precisa estar em inglês, que é o padrão do Ryujinx.
- **Retrô:** sai uma cópia "(PT-BR)" no lugar do original, que fica guardado (`/devolver` traz de volta). Ao lado
  dela fica um patch `.bps`: quem tem o jogo original aplica com o Floating IPS.
- **Tradução feita pela comunidade à mão (patch `.ips`, `.bps`, `.ups`, `.ppf` ou `.xdelta`):** no Deck (Konsole),
  `cd ~/deck-commander && python3 -m dc x patch <jogo> <patch>`. Sai um jogo novo ao lado do original, que não é alterado.
  - O patch confere se o jogo é exatamente o que ele pede. Se não for, nada é gravado e ele explica.
  - **Disco de outra versão** (ex.: uma ISO já traduzida para outra língua): para jogos com receita, o Deck
    Commander leva só os arquivos traduzidos (textos e fonte) para o seu disco. Hoje com receita:
    **God of War: Chains of Olympus** (tradução da OAleex e cia, v1.1), testado no Deck com menus, legendas e
    acentos em português.
- **Não traduz:** jogos com pacote criptografado, porque seria preciso quebrar a proteção do jogo.

## 7. Jogos retrô: botões de trás e saves
Ligue uma vez no painel: **Deck Commander → Retrô → Ligar**.

| Botão | O que faz |
|---|---|
| **L4** | salva o estado (save rápido); ficam os 10 últimos |
| **R4** | carrega o save rápido mais novo |
| **L5** (segurando) | volta no tempo (RetroArch, DuckStation e PSP) |
| **R5** | liga/desliga o turbo (2x, 3x ou 4x, escolhido no painel) |

- **Save rápido x save do jogo:**
  - o save rápido é uma "foto" do emulador e pode não abrir depois que o emulador atualiza (aparece um aviso);
  - o save feito pelo menu do jogo sempre abre;
  - use os dois.
- **Cópias automáticas:** antes de cada vez que o jogo abre, os saves dele são copiados, e ficam as 5 últimas cópias.
  - `/saves copias <jogo>` mostra as cópias;
  - `/saves voltar <jogo> <n>` volta para uma delas (feche o jogo antes).
- **Filtros de tela:** painel → Retrô. O filtro de TV antiga vale para os consoles e a grade de LCD para os portáteis.
- **Seu layout:** se você trocar o layout de controle de um jogo no Steam, o Deck Commander não mexe mais nele.
- **Conquistas:** crie uma conta em retroachievements.org e entre nela dentro de cada emulador.

### Continuar de onde parou
- **Descanso (todos os jogos, inclusive Switch e PC):** aperte o botão de ligar. O Deck congela o jogo e, ao apertar
  de novo, você está no mesmo quadro.
- **Seguro extra (PS1, PS2, PSP, GameCube/Wii e RetroArch):** o Deck Commander guarda um "ponto de continuar" do jogo
  quando você aperta o botão Steam ou o "…", quando o Deck vai dormir e a cada 10 minutos. Ao abrir o jogo de novo,
  ele já começa no ponto — mesmo que a bateria tenha acabado ou que você tenha saído do jogo.
  - O ponto fica num espaço só dele: os seus saves do L4 nunca são trocados.
  - Se o emulador mudou de versão desde o ponto, o jogo abre normal (ponto de outra versão pode travar).
  - Desligar: painel → Retrô → Continuar, ou `/continuar nao`. Abrir um jogo do começo: `/continuar esquecer <jogo>`.
- Switch, Wii U e Xbox 360 não têm save rápido nos emuladores: neles vale só o descanso. PS3 ficou de fora.

### Voltar no tempo pelo painel
Com o jogo aberto: painel → Retrô → **Voltar 5 s / 10 s / 30 s** (o mesmo que segurar o L5). Dá até 30 s no
RetroArch e no PSP e 10 s no DuckStation. PCSX2 (PS2) e Dolphin não têm essa função: neles use o R4.

### Detonado (passo a passo em português)
Painel → **Detonado**. Com um jogo aberto, ele já vem escolhido. O detonado vem da StrategyWiki, separado em partes
na ordem do jogo — no Pokémon por insígnia (ginásio), no God of War por capítulo, no Shadow of the Colossus por
colosso. Escolha a parte em que você está; o painel lembra. A primeira vez mostra o texto original e traduz em segundo
plano; depois fica em português e funciona sem internet. Se o jogo não for achado, digite o nome dele na StrategyWiki.

## 8. Qualidade e controles
- Jogo pesado ou com gráfico estranho: `/qualidade <jogo> nativo|2x|3x|padrão` muda só ele. As exceções aparecem em
  `/qualidade lista`.
- **Auto-ajuste:** no portátil, a qualidade sobe enquanto o jogo roda liso e desce um nível na primeira travada.
- **Energia:** cada console tem o seu limite de energia (TDP), que volta ao valor anterior quando o jogo fecha.
- **Perfil de imagem (todos os jogos):** painel → Qualidade → Perfil, ou `/perfil`:
  - **Beleza:** resolução alta e filtros;
  - **Desempenho:** resolução nativa, o mais liso possível;
  - **Retrô:** resolução nativa com filtro de TV antiga;
  - **Automático** (padrão): o auto-ajuste decide jogo a jogo.

  Vale ao abrir o jogo (os emuladores só leem a resolução ao abrir).
- **Botões A/B de NES, SNES, Game Boy e GBA:** painel → Qualidade → Botões: "como o controle original" (padrão) ou
  "A do Deck = A do jogo".
- **Vibração:** ligada sozinha no Switch (Ryujinx) e no GameCube/Wii (Dolphin), que vinham com ela desligada.
- **Limite de quadros:** ao abrir um jogo de emulador, o Deck Commander tira o limite de quadros do menu "…" (num
  emulador, limite abaixo do console deixa o jogo em câmera lenta). Jogos do PC ficam como você deixou. Para manter o
  seu limite também nos emuladores, crie o arquivo `~/.config/deck-commander/limite-quadros-manter`.
- **Controles:** `/controles` mostra o que falta. Azahar (3DS), Cemu (Wii U) e RPCS3 (PS3) pedem que você escolha o
  controle **uma vez**: modo Desktop → abra o emulador → Controles.

### Modo repouso (baixar e traduzir com a tela apagada)
Na tomada, com download ou tradução andando, o Deck não dorme até terminar; depois volta a dormir sozinho. Precisa de
uma permissão de administrador, **uma vez**: no Deck (Konsole), digite com a sua senha
`sudo bash ~/deck-commander/tools/deck/permitir-repouso.sh`. Ligar/desligar: `/repouso sim|nao`.

## 9. Jogos do PC no Deck (aba "Computador")
1. Escolha o jogo na aba **Computador**.
2. O Deck acorda o PC e espera de 30 a 90 segundos. A tela fica parada nesse tempo, e isso é normal.
3. O jogo abre no PC e aparece no Deck.
4. Para sair: **STEAM → Sair do jogo**. O PC volta a dormir sozinho.

- No Telegram: `/pc status` · `/pc acordar` · `/pc sincronizar` · `/pc listar` · `/pc tv`.
- Fora de casa, a Tailscale precisa estar ligada no Deck.

## 10. Levar jogos e saves entre o Deck e o PC
- **Do Deck para o PC:** `/transferir <jogo>` e depois toque em **Enviar pro PC**.
- **Do PC para o Deck:** `/trazer <jogo>` e depois toque em **Trazer pro Deck**.
- **Andamento:** `/transferir fila` ou `/trazer fila`.
- **O que vai junto:** o jogo, update, DLC, saves, mods, a configuração e os controles. Se o emulador faltar do outro
  lado, a versão oficial é instalada junto.
- **Segurança:** cada arquivo é conferido, a cópia continua de onde parou se cair, e nada é apagado na origem.
- **Saves iguais nos dois lados:** `/saves <jogo>`. Vale o save mais novo. Se os dois lados mudaram, você escolhe qual
  fica.

## 11. Família (Deck do irmão)
- **Parear os dois Decks:** `/familia par` num deles e `/familia autorizar` no outro.
- **Ver o catálogo:** `/familia` mostra o que o outro Deck tem.
- **Puxar um jogo:** `/familia puxar <jogo>`. Isso põe o **magnet** na sua fila e copia a **tradução pronta**.
- Arquivo de jogo nunca passa de um Deck para o outro. Uma trava automática garante isso.

## 12. Saúde e segurança
- `/status`: o que está rodando, o último backup e o espaço livre.
- `/diagnostico`: procura problemas e diz como resolver.
- `/sos` liga o modo seguro, que desliga as automações sem apagar nada. `/sos off` volta ao normal.
- Todo dia é feito um backup das configurações e dos saves. Toda semana rodam testes automáticos.

## 13. Depois de atualizar o SteamOS
A atualização do SteamOS troca o sistema, mas **não toca na sua pasta** (`/home`). Jogos, saves, traduções, o bot, o
qBittorrent e a IA ficam todos lá e voltam sozinhos. Duas peças ficam fora dessa pasta e podem precisar de atenção:

| Sintoma depois do update | Causa | O que fazer |
|---|---|---|
| O painel do Deck Commander (e os outros plugins) sumiu do menu **…** | o SteamOS apagou o serviço do Decky Loader | reinstale o Decky (decky.xyz, como na instalação). Os plugins e as configurações continuam lá e voltam juntos |
| `/pc` ou a Família não conectam fora de casa | a Tailscale fica em `/opt` e pode ser apagada | rode de novo o passo da Tailscale do tutorial |

Depois de qualquer atualização, mande `/diagnostico`: ele diz se algo dessas duas peças precisa de você.

## 14. Pelo painel do Deck (sem Telegram)
Botão **…** → ícone do Decky (tomada) → **Deck Commander**. Tudo funciona só com o controle: A escolhe, B volta.

A tela inicial mostra:
- downloads e traduções, com porcentagem e previsão;
- o espaço livre e a bateria;
- o **Diagnóstico** e o **Modo seguro**.

Telas:
- Telegram;
- Downloads;
- Tradução;
- Computador;
- Transferências;
- Música;
- Família;
- Qualidade e controles;
- Retrô;
- Melhorias;
- Espaço;
- Desinstalar.

O painel faz o mesmo que os comandos do bot.

## 15. Roteiro para instalar e explicar (sábado)
1. **Deck dele (uns 30 min):** siga a Parte 1 do [tutorial](TUTORIAL-INSTALACAO.md):
   - senha;
   - Decky;
   - `install.sh`;
   - criar o bot dele no Telegram pelo QR do painel. **Cada pessoa tem o próprio bot.**
2. **Teste com um jogo leve:** mande `GBA` e um magnet. Mostre o aviso de download, a aba do console e a capa.
3. **Mostre o painel:** **… → Deck Commander**, com status, Downloads e Diagnóstico.
4. **Explique as três regras:**
   - o jogo original nunca é alterado;
   - nada é apagado sem confirmação;
   - quando algo der errado, o primeiro passo é o `/diagnostico`.
5. **Parte 2 do tutorial:** tradução com IA (uns 10 min).
6. **Família:** pareie os dois Decks (`/familia par` e `/familia autorizar`).
7. **Modo dock:** ligue o Deck no monitor e abra um jogo de PS2 para ele ver a diferença.

## Todos os comandos
| Comando | Para quê |
|---|---|
| `Switch` / `PS2` / … + `.torrent` ou magnet | baixar um jogo |
| `/add [console] <magnet>` | baixar direto |
| `/sync` · `/sync tudo` | levar downloads prontos para a biblioteca |
| `/console <código ou nome> <console>` | responder ou corrigir o console de um download (também baixando) |
| `/baixar` | baixar mesmo um repetido |
| `/queue` · `/pause` · `/resume` · `/disk` | downloads |
| `/bateria sim\|nao` | baixar fora da tomada |
| `/duplicados` · `/remover <jogo>` · `/devolver <jogo>` | organizar |
| `/qualidade <jogo> <nível>` · `/controles` | qualidade e controles |
| `/traduzir <jogo>` · `biblioteca` · `status` · `lista` · `parar` · `retomar` · `desfazer` · `config` | tradução |
| `/corrigir <jogo>` (foto) | corrigir uma frase traduzida |
| `/converter <jogo> [organizar\|descompactar]` | Switch: update/DLC/NSZ |
| `/pc status\|acordar\|sincronizar\|listar\|tv` | jogos do PC |
| `/transferir <jogo>` · `/trazer <jogo>` · `fila` | levar jogos entre Deck e PC |
| `/saves <jogo>` · `/saves copias <jogo>` · `/saves voltar <jogo> <n>` | saves |
| `/continuar sim\|nao` · `/continuar esquecer <jogo>` | continuar de onde parou |
| `/perfil [beleza\|desempenho\|retro\|auto]` | perfil de imagem |
| `/repouso sim\|nao` | baixar/traduzir com o Deck na tomada sem dormir |
| `/familia` · `/familia puxar <jogo>` | Deck do irmão |
| `/musica [playlist\|pausar\|proxima]` | Spotify |
| `/status` · `/diagnostico` · `/sos` · `/sos off` | saúde |
| `/reiniciar` · `/voltar` | reiniciar o Steam · desfazer a última atualização |
| `/help` | lista curta no próprio bot |
