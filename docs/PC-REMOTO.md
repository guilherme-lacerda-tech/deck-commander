# Jogos do PC no Steam Deck (aba "Computador")

Cada jogo instalado no PC vira um atalho no Deck, na aba **Computador**. Ao abrir, o Deck acorda o PC,
espera ficar pronto e transmite o jogo pelo Moonlight. Os botões do Deck chegam ao PC como um controle de Xbox.
Quando você fecha o jogo, o PC volta a dormir.

## Como funciona
1. **No PC**, `tools/pc/biblioteca-pc.ps1` encontra os jogos (Epic, Riot, Steam e, se houver, GOG, Ubisoft e Xbox)
   e cria uma entrada para cada um no Sunshine (`apps.json`), com capa quando acha uma.
   - "Desktop", "Steam Big Picture" e qualquer app que você tenha criado à mão ficam intactos.
   - Antes de gravar, faz backup do `apps.json` em `C:\ProgramData\DeckCommander\backup\`. Só grava se algo mudou,
     e só reinicia o Sunshine se algo mudou e não tem nenhum Deck jogando naquela hora.
   - Ele roda sozinho pela tarefa agendada "DeckCommander Biblioteca PC": no boot e uma vez por dia
     (se o PC estava dormindo, roda quando ele acordar). A tarefa nunca acorda o PC.
   - Log: `C:\ProgramData\DeckCommander\biblioteca-pc.log`.
2. **No Deck**, `dc/pc_remoto.py` lê essa lista com `moonlight list` e cria os atalhos pelo mesmo caminho dos outros
   jogos: o lançador `dc-launch`, o plugin do Decky e a coleção/aba "Computador". O layout de controle desses atalhos
   é "Gamepad com trackpad como mouse".
   - A lista se atualiza sozinha depois de cada partida (o PC ainda está acordado nessa hora) ou com `/pc sincronizar`.
   - Jogos desinstalados do PC somem do Deck. Se você remover um atalho pelo Steam, ele não volta.
3. **Ao abrir um jogo:**
   1. O Deck acorda o PC: primeiro pede ao Fire TV ("porteiro") pela Tailscale, depois pelo WiFi de casa,
      e por último manda o sinal de acordar direto para o PC (esse último só funciona em casa).
   2. Espera o Sunshine responder, por até 90 s.
   3. Abre o Moonlight em 1280x800, 60 fps e HEVC. A taxa é 30 Mbps em casa e 15 Mbps fora.
4. **Ao fechar** (botão STEAM → Sair do jogo):
   1. O Deck pede ao PC para encerrar o app (`--quit-after` e `moonlight quit`).
   2. O Sunshine fecha os processos da pasta do jogo (`fechar-jogo.ps1`).
   3. O agente da casa põe o PC para dormir **2 min depois**, desde que o PC tenha sido acordado pela rede
      e ninguém esteja usando ele.
   - Se o Deck só desconectar (suspendeu, ficou sem sinal), o agente põe o PC para dormir 5 min depois.
     Se nada disso acontecer, ele dorme depois de 20 min sem uso.

## O que você precisa fazer (uma vez)
1. **No PC**, abra o PowerShell na pasta do Deck Commander e rode:
   `powershell -ExecutionPolicy Bypass -File tools\pc\biblioteca-pc.ps1 -Instalar`
   O Windows vai pedir permissão (UAC): clique **Sim**. O comando copia os scripts para
   `C:\Program Files\DeckCommander\pc`, cria a tarefa agendada e já roda uma vez.
   Para só ver o que ele faria, sem gravar nada: `... biblioteca-pc.ps1 -Simular`
2. **No Deck**, coloque o código do porteiro na config. Ele fica em `~/.local/share/deck-commander/pc-remoto.json`,
   com permissão só para você ler.
   `python3 -m dc x pc config codigo <conteúdo de C:\AutomacaoCasa\agente\codigo-acordar.txt>`
3. Com o PC acordado, rode `python3 -m dc x pc sincronizar` (ou `/pc sincronizar` no Telegram,
   depois que esse comando for ligado ao bot).

## Dentro e fora de casa
- **Em casa:** o PC acorda pelo porteiro ou pelo sinal direto. O stream usa a Tailscale, que vai direto pelo WiFi,
  e cai para o IP de casa (192.168.0.20) se a Tailscale estiver desligada.
- **Fora de casa:** precisa da Tailscale ligada no Deck. Só o porteiro consegue acordar o PC (o Fire TV precisa estar
  ligado na tomada, com a Tailscale dele ativa).

## Comandos
- `python3 -m dc x pc status | listar | sincronizar | acordar | jogar <app> | config [chave valor]`
- Bot: `dc.pc_remoto.comando_pc(bot, args)` → `/pc listar | sincronizar | acordar | status` (falta ligar no `bot.py`).

## O que NÃO foi testado de verdade
- Nenhum stream foi iniciado. Ainda não foram testados: o jogo abrir pelo Sunshine, o controle chegar ao PC,
  `--quit-after`/`moonlight quit` fecharem o app e o tempo real até o PC dormir (pela leitura do agente: ~2 min + suspender).
- O `-Instalar` não foi executado, porque precisa do seu clique no UAC. O Sunshine ainda só tem "Desktop" e "Steam Big Picture".
- Acordar pelo porteiro e pelo sinal direto (nada foi enviado ao PC nos testes).
- O layout de controle gravado em `configset_controller_neptune.vdf`: com o Steam aberto, ele pode sobrescrever o arquivo.
  Sem a entrada, o Steam já usa um layout de gamepad.
- Se outro app já estiver aberto no PC (ex.: "Desktop"), não se sabe o que o Moonlight faz pela linha de comando.
- GOG/Ubisoft/Xbox: o código existe, mas não há jogos dessas lojas neste PC. EA app: não suportado (os jogos EA daqui
  são da Steam).
