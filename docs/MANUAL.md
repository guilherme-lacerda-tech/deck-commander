# Manual de uso do Deck Commander

Tudo se faz pelo **Telegram** (no bot que você criou na instalação) ou direto no **Steam Deck**, no modo de jogo.
Não precisa abrir o modo Desktop no dia a dia. Instalação: [TUTORIAL-INSTALACAO.md](TUTORIAL-INSTALACAO.md).

## 1. Baixar um jogo
1. Mande o nome do console: `Switch`, `PS2`, `PS1`, `GBA`, `SNES`, `Wii`…
2. Encaminhe o arquivo `.torrent` ou cole o link `magnet:`.
3. Pronto. Quando o download terminar, o bot avisa e o jogo aparece na aba do console, com capa.

- **Repetido?** O bot avisa **antes** de baixar. Quer mesmo assim: `/baixar`.
- **Na bateria** os downloads esperam a tomada (abaixo de 30% sempre pausam). Liberar: `/bateria sim`.
- **O bot perguntou o console?** Responda com `/console <código> <console>` (o código vem na pergunta).
- Fila e controle: `/queue` (fila) · `/pause` · `/resume` · `/disk` (espaço livre).

## 2. Encontrar e jogar
- No modo de jogo, cada console tem a **sua aba** (PlayStation 2, Nintendo Switch…). Abas vazias ficam escondidas.
- **Em português**: aba com tudo que já está em português (oficial, traduzido ou dublado).
- **Computador**: os jogos do seu PC (veja a seção 6).
- Jogo novo não apareceu? Espere ~10 s. Se não vier: `/sync`, e em último caso `/reiniciar` (reinicia o Steam).

## 3. Tradução para português
- **Automática:** jogo baixado que não está em português entra na fila sozinho e chega traduzido. O bot avisa a
  cada 20% e quando termina.
- **Manual:** `/traduzir <jogo>`. Todos os jogos de uma vez: `/traduzir biblioteca` (pergunta antes).
- **Jogo de motor diferente** (Unity, GameMaker, Godot, RE Engine, RPG Maker, CRI): o bot pergunta antes,
  com o número de frases e o tempo estimado. Responda **Sim** ou **Não**.
- Acompanhar: `/traduzir status` · lista: `/traduzir lista` · desfazer: `/traduzir desfazer <jogo>`.
- **Travou?** Se uma tradução ficar 45 min sem avançar, o bot avisa. `/traduzir parar <código>` libera e
  `/traduzir retomar <código>` continua de onde parou (nada traduzido se perde).
- **Switch:** a tradução vira um mod. O jogo precisa estar em **inglês** (padrão do Ryujinx). Viu quadradinhos no
  lugar de ã/õ/ç? Avise quem cuida do projeto: dá para trocar esses acentos.
- **Retrô:** sai uma cópia "(PT-BR)" que substitui o atalho do original. O original fica guardado (`/devolver`).
- Não dá para traduzir: jogos com o pacote criptografado (seria preciso quebrar a proteção do jogo).

## 4. Organizar a biblioteca
- **Repetidos:** `/duplicados` mostra; `/remover <nº ou nome>` tira (pede confirmação). Os arquivos ficam 30 dias
  na quarentena antes de sumir.
- **Tirou um jogo pelo Steam?** Ele não volta sozinho. Para trazer de volta: `/devolver <nome>` (`/devolver` lista).
- **Switch:** `/converter <jogo>` confere update e DLC; `organizar` arruma numa pasta só; `descompactar` tira o NSZ.

## 5. Qualidade e controles
- Jogo pesado ou com gráfico estranho: `/qualidade <jogo> nativo|2x|3x|padrão` muda a resolução só dele.
  `/qualidade lista` mostra as exceções.
- `/controles` mostra em quais emuladores o controle ainda precisa ser escolhido uma vez (no modo Desktop, abra o
  emulador → Controles → escolha o controle do Deck).

## 6. Jogar os jogos do PC no Deck (aba "Computador")
1. No Deck, abra a aba **Computador** e escolha o jogo.
2. O Deck acorda o PC e espera ele ficar pronto (de 30 a 90 s; a tela fica parada nesse tempo, é normal).
3. O jogo abre no PC e aparece no Deck. Os botões funcionam como controle de Xbox.
4. Para sair: botão **STEAM** → **Sair do jogo**. O jogo fecha no PC e o PC volta a dormir sozinho depois de alguns minutos.

- Jogo novo instalado no PC aparece no Deck sozinho quando o PC reinicia ou no dia seguinte. Para aparecer na hora,
  rode no PC `powershell -ExecutionPolicy Bypass -File C:\dev\deck-commander\tools\pc\biblioteca-pc.ps1` (como
  administrador) e espere até 5 min.
- No Telegram: `/pc status` (PC acordado? quantos jogos) · `/pc acordar` · `/pc sincronizar` · `/pc listar`.
- **Fora de casa:** a Tailscale precisa estar ligada no Deck.
- Jogos com antitrapaça (Vanguard da Riot, EAC) podem não deixar o sistema fechá-los, mas o PC dorme mesmo assim.

## 7. Levar um jogo do Deck para o PC
1. `/transferir <jogo>`: o bot mostra o que vai e o tamanho, com o botão **Enviar pro PC**.
2. Toque no botão. O bot acorda o PC; em até 5 min o PC começa a copiar.
3. O bot avisa quando terminar. `/transferir fila` mostra o andamento.

- Vai **tudo**: jogo, update, DLC, saves, configuração do emulador (geral e do jogo), controles, mods, keys/firmware/BIOS.
- Seguro: cada arquivo é conferido; se cair, continua de onde parou; a configuração do PC ganha backup antes;
  nada é apagado no Deck. O PC não dorme enquanto copia.
- No PC: jogos em `D:\DeckCommander\Jogos\<console>\<jogo>`, emuladores em `D:\Emuladores`.
- Depois da cópia: na primeira vez, escolha o controle na tela de controles do emulador do PC. Os primeiros minutos
  podem engasgar enquanto os shaders são refeitos (normal).
- **Jogar esse jogo do PC também no Deck (streaming):** crie um atalho dele (.lnk, que abre o emulador com o jogo)
  na pasta `C:\Users\Public\Documents\Deck Commander\Jogos do PC`. Ele entra na aba **Computador** como os outros
  jogos do PC.

## 8. Saúde e segurança
- `/status`: tudo que está rodando, último backup, espaço livre.
- `/diagnostico`: procura problemas e diz como resolver.
- `/sos`: modo seguro (desliga as automações, não apaga nada). `/sos off` volta ao normal.
- Backup diário das configurações e saves; testes automáticos toda semana; nada é apagado sem confirmação.
- Quarentena: `/quarantine list` · `review <id>` · `clear <id>`.

## Pelo painel do Deck (sem Telegram)
No modo de jogo: botão **…** → ícone do Decky (tomada) → **Deck Commander**. Tudo funciona só com o controle
(A escolhe, B volta). A tela inicial mostra o **status** (downloads, traduções com % e previsão, espaço livre,
bateria), o botão **Diagnóstico** (o que falta fazer) e a chave **Modo seguro**. Abaixo, uma tela para cada coisa:

- **Telegram:** mostra se o bot está configurado e ligado ao seu celular. **Configurar bot** mostra o QR do
  @BotFather e um campo para o token (aperte A no campo para abrir o teclado); depois aparece o QR do seu bot para
  ligar o celular. O token fica só no Deck e não aparece na tela.
- **Downloads:** lista com andamento, pausar/retomar (um ou todos), **Baixar fora da tomada** e **Procurar jogos
  repetidos** (cada um com **Remover**, que mostra antes o que vai acontecer e pede confirmação).
- **Tradução:** **Traduzir sozinho** liga/desliga a tradução automática; **Perguntas** (Sim/Não dos jogos de motor
  diferente e da tradução fora do padrão); **Tarefas** com Parar/Retomar; **Não traduzidos** com o botão Traduzir.
- **PC:** campos do PC (IP de casa, rede de casa, MAC, IP da Tailscale, porteiro e código, opcionais), **Salvar**,
  **Testar conexão**, **Acordar PC**, **Sincronizar jogos do PC** e a lista dos jogos do PC.
- **Levar jogo para o PC:** busque o jogo, escolha na lista, veja o tamanho e o que vai junto e toque em
  **Enviar pro PC**. A fila mostra o andamento.
- **Qualidade e controles:** resolução por jogo (padrão, nativo, 2x, 3x…) e quais emuladores ainda precisam que
  você escolha o controle uma vez (no modo Desktop).
- **Biblioteca e desempenho:** situação dos atalhos criados pelo plugin e o ajuste de desempenho do jogo aberto.

O painel faz exatamente o mesmo que os comandos do bot (por baixo, `python3 -m dc.painel <ação>`). Se algo der
errado, aparece uma mensagem simples na própria tela; detalhes ficam em `~/.local/state/deck-commander/painel.log`.

## Todos os comandos
| Comando | Para quê |
|---|---|
| `Switch` / `PS2` / … + `.torrent` ou magnet | baixar um jogo |
| `/add [console] <magnet>` | baixar direto |
| `/sync` · `/sync tudo` | levar downloads prontos para a biblioteca |
| `/console <código> <console>` | responder qual é o console |
| `/baixar` | baixar mesmo um repetido |
| `/queue` · `/pause` · `/resume` · `/disk` | downloads |
| `/bateria sim\|nao` | baixar fora da tomada |
| `/duplicados` · `/remover <jogo>` · `/devolver <jogo>` | organizar |
| `/qualidade <jogo> <nível>` · `/controles` | qualidade e controles |
| `/traduzir <jogo>` · `biblioteca` · `status` · `lista` · `parar` · `retomar` · `desfazer` · `config` | tradução |
| `/converter <jogo> [organizar\|descompactar]` | Switch: update/DLC/NSZ |
| `/pc status\|acordar\|sincronizar\|listar` | jogos do PC no Deck |
| `/transferir <jogo>` · `/transferir fila` | levar jogo para o PC |
| `/status` · `/diagnostico` · `/sos` · `/sos off` | saúde |
| `/reiniciar` | reiniciar o Steam |
| `/help` | lista curta no próprio bot |
