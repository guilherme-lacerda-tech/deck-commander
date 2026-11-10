# Tutorial: como montar o Deck Commander do zero

Este guia é para quem vai instalar o Deck Commander num Steam Deck novo (e, se quiser, num PC Windows).
Siga na ordem. A Parte 1 é a única obrigatória. As outras são extras que você liga quando quiser.

| Parte | O que você ganha | Tempo | Precisa de |
|---|---|---|---|
| 1. Steam Deck | Jogos de emulador na biblioteca do Steam com capa e aba por console; downloads pelo Telegram | ~30 min | Steam Deck, internet, Telegram no celular |
| 2. Tradução com IA | Jogos traduzidos para português automaticamente | ~10 min | Parte 1 |
| 3. Ligar o PC ao Deck | Base para as partes 4 e 5 | ~10 min | PC Windows na mesma rede |
| 4. Transferir jogos do Deck para o PC | Jogo + emulador + configuração + saves no PC, com um botão no Telegram | ~15 min | Parte 3 |
| 5. Jogar os jogos do PC no Deck | Aba "Computador" no Deck com Fortnite, Steam do PC etc. transmitidos do PC | ~30 min | Parte 3, PC com placa de vídeo |

> **Regra de ouro:** o Deck Commander não baixa nem fornece jogos, BIOS, chaves ou firmware. Use só cópias suas
> (tiradas dos seus próprios jogos e consoles).

---

## Parte 1 — Steam Deck

### 1.1 Crie uma senha no Deck
Vá para o **modo Desktop** (botão STEAM → Ligar/Desligar → Mudar para o modo Desktop) e abra o **Konsole**
(menu do canto inferior esquerdo → Sistema → Konsole). Digite e crie uma senha (ela não aparece enquanto você digita):

```bash
passwd
```

### 1.2 Instale o Decky Loader
No modo Desktop, abra o navegador, entre em **https://decky.xyz**, clique em **Download** e abra o arquivo baixado.
Ele pede a senha que você criou. O Decky é a "loja de plugins" do modo de jogo.

### 1.3 Instale o Deck Commander
Ainda no Konsole:

- **Se o repositório estiver público**, um comando só:
  ```bash
  curl -fsSL https://raw.githubusercontent.com/guilherme-lacerda-tech/deck-commander/main/install.sh | bash
  ```
- **Se estiver privado** (o Guilherme precisa te adicionar como colaborador no GitHub antes):
  ```bash
  git clone https://github.com/guilherme-lacerda-tech/deck-commander.git ~/deck-commander
  cd ~/deck-commander && ./install.sh
  ```
  O `git clone` pede seu usuário do GitHub e, no lugar da senha, um **token** (GitHub → Settings → Developer settings →
  Personal access tokens → Generate new token, com acesso de leitura a repositórios).

O instalador leva alguns minutos. Ele instala os emuladores que faltarem, os serviços e o plugin, tudo dentro da sua
pasta pessoal (nada do sistema é alterado).

### 1.4 Crie o seu bot do Telegram
No fim da instalação aparece um **QR code**:
1. Aponte a câmera do celular. Abre o **@BotFather** (o robô oficial do Telegram que cria bots).
2. Mande `/newbot`, escolha um nome e um usuário terminado em `bot`.
3. Ele responde com um **token** (uma linha comprida). Copie e cole no Konsole. Não aparece na tela, é normal.
4. Aparece um **segundo QR code**: ele abre o **seu** bot. Toque em **Iniciar**. Pronto: só a sua conta manda no Deck.

Pulou essa parte? Rode depois: `python3 -m dc x telegram-setup`.

### 1.5 Plugins no modo de jogo
Volte ao **modo de jogo**. Aperte o botão **…** (três pontinhos) → ícone do Decky (tomada):
1. **TabMaster** (loja do Decky, ícone de sacola): instale. É ele que mostra uma aba por console.
2. **Plugin do Deck Commander**: ⚙️ Configurações do Decky → ligue o **Modo Desenvolvedor** → aba **Desenvolvedor** →
   **Instalar plugin de ZIP** → escolha `Downloads/deck-commander-plugin.zip`.
3. Reinicie o Deck **uma vez**.

### 1.6 Seus jogos e BIOS
- Jogos que você já tem: coloque em `~/Emulation/roms/<console>/` (ou no cartão SD em `Emulation/roms/<console>/`).
  Pastas: `psx ps2 ps3 psp gc wii wiiu n64 snes nes gba gb gbc nds n3ds switch switch2 x360` e outras.
  Depois mande `/sync` no Telegram (ou rode `python3 -m dc library --apply`).
- BIOS (dos seus consoles): em `~/Emulation/bios/`. O bot avisa se faltar alguma (`/diagnostico`).
- Switch: abra **qualquer** jogo uma vez no Ryujinx; ele guarda as chaves do seu console e a tradução passa a funcionar.

### 1.7 Capas (opcional)
Crie uma chave grátis em https://www.steamgriddb.com/profile/preferences/api e rode no Konsole:
```bash
python3 -m dc secret steamgriddb
```

**Teste da Parte 1:** mande `/status` para o bot. Ele deve responder "Deck Commander ativo".

---

## Parte 2 — Tradução com IA

A tradução já vem ligada: jogo baixado que não está em português entra na fila e chega traduzido. A IA principal é
grátis, pela internet. Para ela não depender só da internet, ligue as IAs locais:

- **No Deck** (lenta, mas funciona sem internet e sem PC):
  ```bash
  cd ~/deck-commander && ./setup-deck.sh --modules A1,A2,A3
  ```
- **No PC** (bem mais rápida, opcional): instale o **Ollama** (https://ollama.com), rode `ollama pull qwen2.5:7b`
  e depois faça a Parte 3 e rode no PowerShell do PC:
  ```bash
  powershell -ExecutionPolicy Bypass -File <pasta do projeto>\tools\pc\instalar-tunel-ia.ps1 -Deck deck@IP-DO-DECK
  ```

Veja tudo o que dá e o que não dá para traduzir em [TRADUCAO-E-CONVERSAO.md](TRADUCAO-E-CONVERSAO.md).

---

## Parte 3 — Ligar o PC ao Deck

O PC conversa com o Deck por **SSH** (conexão segura com chave; nada fica aberto para a internet).

### 3.1 No Deck: ligue o SSH e descubra o IP
No Konsole do Deck:
```bash
sudo systemctl enable --now sshd
ip -4 addr show | grep inet
```
Anote o IP que começa com `192.168.` ou `10.` (ex.: `192.168.0.50`). Vale reservar esse IP no roteador para ele não
mudar (procure "DHCP reservado" / "IP fixo" nas configurações do roteador).

### 3.2 No PC: crie a chave e autorize no Deck
Abra o **PowerShell** do Windows (sem ser administrador) e rode, trocando o IP:
```bash
ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\deck_commander_ed25519 -N '""'
type $env:USERPROFILE\.ssh\deck_commander_ed25519.pub | ssh deck@192.168.0.50 "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
```
O segundo comando pede a senha do Deck **uma vez**. Depois, grave o endereço do Deck para os scripts do PC:
```bash
mkdir $env:USERPROFILE\.deck-commander -Force; Set-Content $env:USERPROFILE\.deck-commander\deck.txt 'deck@192.168.0.50'
```

### 3.3 No PC: baixe o projeto
Com o Git for Windows (https://git-scm.com): `git clone https://github.com/guilherme-lacerda-tech/deck-commander.git C:\dev\deck-commander`
(ou, no GitHub, **Code → Download ZIP** e extraia em `C:\dev\deck-commander`).

**Teste da Parte 3:** `ssh -i $env:USERPROFILE\.ssh\deck_commander_ed25519 deck@192.168.0.50 echo ok` responde `ok`
sem pedir senha.

---

## Parte 4 — Transferir jogos do Deck para o PC

Leva o jogo com **tudo**: arquivos, updates, DLC, saves, configuração do emulador (geral e do jogo), controles, mods,
keys/firmware/BIOS. Cada arquivo é conferido, a cópia continua de onde parou se cair, a configuração do PC ganha
backup antes de ser trocada e **nada é apagado no Deck**.

### 4.1 Emuladores no PC
Baixe a versão Windows **oficial** e extraia em `D:\Emuladores\<Nome>` (se não tiver D:, use outra pasta e passe
`-Emuladores <pasta>`). Use a mesma versão do Deck quando puder, principalmente no Switch 2.

| Console | Emulador | Onde baixar | Modo portátil (tudo dentro da pasta) |
|---|---|---|---|
| Switch 2 | Lichii | github.com/zortos293/Lichii/releases | crie a pasta `user` ao lado do `lichii.exe` |
| Switch | Ryujinx | git.ryujinx.app/projects/Ryubing/releases | crie a pasta `portable` ao lado do `Ryujinx.exe` |
| PS2 | PCSX2 | github.com/PCSX2/pcsx2/releases | crie um arquivo vazio `portable.ini` |
| PS1 | DuckStation | github.com/stenzek/duckstation/releases | crie um arquivo vazio `portable.txt` |
| PSP | PPSSPP | github.com/hrydgard/ppsspp/releases | já é portátil |
| Xbox 360 | Xenia Canary | github.com/xenia-canary/xenia-canary-releases/releases | crie um arquivo vazio `portable.txt` |

### 4.2 Deixe o PC buscando os pedidos sozinho
No PowerShell do PC (não precisa ser administrador):
```bash
powershell -ExecutionPolicy Bypass -File C:\dev\deck-commander\tools\pc\transferir-fila.ps1 -Instalar
```
Isso cria a tarefa "DeckCommander Transferencias", que olha a fila do Deck a cada 5 minutos.

**Teste da Parte 4:** no Telegram, `/transferir <um jogo pequeno>` → toque em **Enviar pro PC**. Em até 5 minutos o
PC começa; o bot avisa quando terminar. Os jogos vão para `D:\DeckCommander\Jogos\<console>\<jogo>`.

---

## Parte 5 — Jogar os jogos do PC no Deck (aba "Computador")

O PC roda o jogo e transmite a imagem para o Deck; os botões do Deck chegam ao PC como um controle de Xbox.

### 5.1 No PC: Sunshine
1. Instale o **Sunshine** (github.com/LizardByte/Sunshine/releases, o instalador `.exe` do Windows).
2. Abra `https://localhost:47990` no navegador do PC e crie o usuário e a senha do Sunshine.

### 5.2 No Deck: Moonlight e pareamento
1. Modo Desktop → **Discover** (loja) → instale o **Moonlight**.
2. Abra o Moonlight. O PC aparece na lista (ou adicione pelo IP do PC). Clique nele: aparece um **PIN**.
3. No PC, em `https://localhost:47990` → **PIN** → digite o PIN do Deck.

### 5.3 No PC: biblioteca automática
No PowerShell do PC:
```bash
powershell -ExecutionPolicy Bypass -File C:\dev\deck-commander\tools\pc\biblioteca-pc.ps1 -Instalar
```
O Windows pede permissão (clique **Sim**). Ele acha os jogos do PC (Steam, Epic, Riot, GOG, Ubisoft, Xbox) e cria um
atalho para cada um no Sunshine; repete sozinho todo dia e quando o PC liga. A tarefa da Parte 4.2 manda essa lista
para o Deck, então faça a 4.2 também.

### 5.4 No Deck: diga onde está o PC
No Konsole do Deck (troque pelos valores do seu PC; no PC, `ipconfig /all` mostra o IP e o "Endereço Físico" = MAC):
```bash
cd ~/deck-commander
python3 -m dc x pc config host_casa 192.168.0.20
python3 -m dc x pc config rede_casa 192.168.0.
python3 -m dc x pc config mac AA-BB-CC-DD-EE-FF
```

### 5.5 Para o PC acordar e dormir sozinho
- **Acordar (Wake-on-LAN):** ligue "Wake on LAN" na BIOS do PC e, no Windows, em Gerenciador de Dispositivos →
  placa de rede → Propriedades → Gerenciamento de Energia, marque "Permitir que este dispositivo ative o computador"
  e "Somente pacote mágico". Cabo de rede é o mais garantido. Wi-Fi depende da placa.
- **Dormir:** em Configurações do Windows → Sistema → Energia → "Suspender após", escolha **15 minutos**
  (na tomada). Ao fechar o jogo no Deck, o PC fica parado e dorme sozinho.

### 5.6 Fora de casa (opcional, avançado)
- Instale a **Tailscale** no PC e no Deck, na mesma conta, e grave o IP Tailscale do PC:
  `python3 -m dc x pc config host_tailscale 100.x.y.z`.
- Acordar o PC **de fora de casa** precisa de um aparelho que fique sempre ligado em casa e mande o "acordar"
  (o Guilherme usa um Fire TV como "porteiro"). Sem isso, deixe o PC ligado quando for sair.

**Teste da Parte 5:** no Deck, aba **Computador** → abra "Área de trabalho do PC". Em até ~90 s aparece a tela do PC.
Mande `/pc status` no Telegram para ver o estado.

---

## Atualizar
No Konsole do Deck: `cd ~/deck-commander && git pull && ./setup-deck.sh --all` (não apaga nada).
No PC: `git pull` na pasta `C:\dev\deck-commander`.

## Deu problema?
1. Mande `/diagnostico` no Telegram: ele lista o que está errado e como resolver.
2. Algo ficou estranho? `/sos` desliga as automações sem apagar nada (`/sos off` volta ao normal).
3. Veja [TROUBLESHOOTING.md](../TROUBLESHOOTING.md) e o manual de uso: [MANUAL.md](MANUAL.md).
