# Deck Commander

### Prioridade obrigatória de entrega

Enviar o nome do jogo e receber o download instalado é o primeiro critério de aceite.
As demais funcionalidades seguem após esse fluxo e suas dependências.
O catálogo incluído oferece Doom Shareware e Super Tilt Bro para download HTTPS com SHA-256.
O catálogo pessoal, o catálogo da família e o Prowlarr configurado ampliam as fontes disponíveis.
Os testes reais e as pendências de integração estão registrados em `docs/execution/TEST_EVIDENCE.md`.

Centro de comando para o **Steam Deck**: seus jogos de emulador organizados na biblioteca do Steam, com
capa e aba por console, baixados e instalados por **mensagem no Telegram** — tudo no Gaming Mode, sem
abrir o modo Desktop no dia a dia.

> *English summary:* Steam Deck companion that turns your emulator games into first-class Steam
> library entries (artwork, per-console tabs via TabMaster), adds them live through a small Decky plugin
> (no Steam restart), and lets you queue downloads from a Telegram bot. Everything stays in `$HOME`;
> SteamOS system files are never touched. Docs are in Portuguese (pt-BR).

> **Começando do zero?** Siga o [tutorial de instalação](docs/TUTORIAL-INSTALACAO.md) e depois o
> [manual de uso](docs/MANUAL.md).

## O que ele faz

| | |
|---|---|
| 📚 **Biblioteca** | Cada ROM vira um jogo no Steam, com capa (SteamGridDB) e na aba do console certo. |
| ⚡ **Ao vivo** | Um plugin do Decky adiciona o jogo em ~10 s — **sem reiniciar o Steam**. |
| 🗂️ **Abas** | Uma aba por console (PS1, PS2, Switch, GameCube, Wii, PSP, N64, SNES, GBA…), uma por loja do Unifideck (Epic, GOG) e "Emuladores". Abas vazias ficam escondidas. |
| 🤖 **Telegram** | Mande o nome do jogo. Escolha a plataforma quando solicitado. O bot busca nas fontes configuradas, baixa a versão identificada e acompanha a instalação. |
| 🎮 **Emuladores** | Perfis de qualidade por console, BIOS conferidas, avisos de atualização desligados, Switch com A/B no lugar certo. |
| 🛟 **Segurança** | Backup diário de configs e saves, quarentena (nada é apagado sozinho), safe-mode, autodiagnóstico, testes automáticos semanais. |

## Requisitos

- Steam Deck (LCD ou OLED) com SteamOS 3.5+ (Python 3.11+ já vem no sistema).
- [Decky Loader](https://decky.xyz) instalado.
- Recomendado: **TabMaster** (loja do Decky) para as abas; **Unifideck** se você usa Epic/GOG.
- Emuladores: o instalador detecta os que você já tem (EmuDeck, Flatpak, AppImage) e instala
  RetroArch / Dolphin / PPSSPP pelo Flathub se faltarem.
- Opcional: uma conta no Telegram (bot) e uma chave gratuita do [SteamGridDB](https://www.steamgriddb.com/profile/preferences/api) (capas).

## Instalação rápida (1 comando)

1. Instale o [Decky Loader](https://decky.xyz) (se ainda não tiver).
2. No Deck, **modo Desktop** → abra o **Konsole** → cole e aperte Enter:

```bash
curl -fsSL https://raw.githubusercontent.com/guilherme-lacerda-tech/deck-commander/main/install.sh | bash
```

3. No fim aparece um **QR code**: aponte o celular, ele abre o **@BotFather** (o robô oficial do Telegram
   que cria bots). Mande `/newbot`, escolha um nome, copie o **token** e cole no Konsole (não aparece na tela).
4. Aparece um **segundo QR**: ele abre o **seu** bot já com o código de pareamento — toque em **Iniciar**. Pronto:
   só a sua conta manda no Deck.

O token fica só em `~/.config/deck-commander/secrets/` (nunca no git). Para refazer o passo do Telegram:
`python3 -m dc x telegram-setup`. A IA do PC (túnel) é opcional — veja `tools/pc/`.

## Instalação (passo a passo, manual)

No Deck, **modo Desktop**, abra o **Konsole**:

```bash
git clone https://github.com/guilherme-lacerda-tech/deck-commander.git ~/deck-commander
cd ~/deck-commander && ./setup-deck.sh --all
```

O instalador é idempotente (pode rodar de novo para atualizar) e mostra o que fez. Depois:

1. **Plugin (para os jogos aparecerem sem reiniciar):** volte ao Gaming Mode → botão **…** → Decky →
   ⚙️ Configurações → ative **Modo Desenvolvedor** → aba **Desenvolvedor** → **Instalar plugin de ZIP** →
   `Downloads/deck-commander-plugin.zip`. Reinicie o Deck **uma vez**.
2. **Capas (opcional):** `python3 -m dc secret steamgriddb` e cole a chave (não aparece na tela).
3. **Bot do Telegram (opcional):** o jeito fácil é `python3 -m dc x telegram-setup` (QR code). À mão:
   - No Telegram, fale com **@BotFather** → `/newbot` → copie o token.
   - `python3 -m dc secret telegram` (cole o token) → `systemctl --user restart deck-commander-bot`
   - `python3 -m dc x telegram-pair` → mande `/start CODIGO` para o seu bot. Só a sua conta passa a ter acesso.
4. **Jogos que você já tem:** coloque em `~/Emulation/roms/<console>/` (ou no cartão SD, em
   `Emulation/roms/<console>/`) e rode `python3 -m dc library --apply`.
   Pastas: `psx ps2 gc wii psp n64 snes gba switch switch2`. BIOS em `~/Emulation/bios/`.

## Uso no dia a dia

Pelo Telegram

1. Mande o nome do jogo, como `Doom` ou `Super Tilt Bro`.
2. Escolha a plataforma quando o bot perguntar. Versões ambíguas aparecem para seleção.
3. O download e a instalação seguem em segundo plano. O bot informa a conclusão ou a dependência pendente.

O catálogo padrão está em `config/download-catalog.json`. Entradas próprias em
`~/.config/deck-commander/download-catalog.json` complementam esse catálogo, com URL, licença,
plataforma, tamanho e SHA-256. O Prowlarr usa `~/.config/deck-commander/prowlarr.json`.
Um pedido sem fonte disponível permanece guardado e é pesquisado novamente a cada 15 minutos.
O primeiro login da Steam habilita a publicação dos jogos baixados na biblioteca.
O envio de torrent e magnet também continua disponível pelo bot.

Baixou repetido? O bot avisa **antes** de baixar (responda `/baixar` se quiser mesmo assim). Para limpar o que já
está repetido: `/duplicados` e `/remover <nº>` (pede confirmação; os arquivos ficam 30 dias na quarentena).
Removeu um jogo pelo próprio Steam? Ele não volta sozinho (`/devolver <nome>` traz de volta).

Jogo pesado ou com gráfico estranho? `/qualidade <jogo> nativo|2x|3x` muda a resolução só daquele jogo —
veja [docs/QUALIDADE-E-CONTROLES.md](docs/QUALIDADE-E-CONTROLES.md).

Quer jogar só o que está em português? Abra a aba **"Em português"**. Jogos de Switch com português oficial já
abrem em português sozinhos. Quer traduzir? `/traduzir <jogo>` traduz jogos de Switch (como mod, sem alterar o jogo) e Pokémon de GBA
com IA — veja [docs/TRADUCAO-E-CONVERSAO.md](docs/TRADUCAO-E-CONVERSAO.md).

Na bateria os downloads esperam a tomada (o bot avisa); `/bateria sim` libera. Depois de baixar, o compartilhamento
(seeding) para em razão 1.0 ou 60 min, para não gastar o pacote de dados.

Outros comandos: `/status` · `/queue` · `/pause` · `/resume` · `/disk` · `/diagnostico` · `/controles` · `/bateria` · `/sos` · `/help`.

**Pelo terminal:** veja [docs/COMANDOS.md](docs/COMANDOS.md).

## Como funciona (resumo)

- Todos os atalhos de ROM apontam para um lançador fixo (`dc-launch <jogo>`). Trocar a ROM, o formato
  ou o emulador muda só um mapa — o atalho, as horas jogadas, a capa e as coleções não se perdem.
- O plugin do Decky cria os atalhos com a mesma função do "Adicionar jogo não-Steam" e mantém uma
  **coleção do Steam** por console/loja; o TabMaster mostra cada coleção como aba, ao vivo.
  Se um atalho criado por ele sumir (ex.: desligamento brusco), ele recria sozinho.
- Nada é instalado fora do `$HOME`. Nada é apagado automaticamente: arquivos suspeitos vão para a
  quarentena, e toda alteração em arquivo do Steam tem backup antes.
- Detalhes: [ARCHITECTURE.md](ARCHITECTURE.md) · Privacidade: [PRIVACY.md](PRIVACY.md) ·
  Problemas: [TROUBLESHOOTING.md](TROUBLESHOOTING.md) · Recuperação: [recovery/README.md](recovery/README.md).

## Desinstalar

```bash
cd ~/deck-commander
./uninstall-deck-commander.sh                       # serviços e código (mantém configs e backups)
./uninstall-deck-commander.sh --purge --confirm APAGAR   # também configs, banco e logs
```
O plugin se remove pelo próprio Decky. ROMs, saves e backups nunca são apagados sem `--purge-backups`.

## ⚖️ Aviso legal

O Deck Commander é uma ferramenta de organização. **Ele não fornece, não hospeda e não indica jogos,
ROMs, BIOS, firmware ou chaves de console.** Use apenas cópias que você tem o direito de usar (por
exemplo, extraídas dos seus próprios jogos e consoles), conforme a lei do seu país. Torrents expõem seu
IP para outros participantes. O projeto não tem relação com Valve, Nintendo, Sony ou os autores dos
emuladores e plugins citados.

## Desenvolvimento

```bash
python3 -m venv .venv && .venv/bin/pip install pytest && .venv/bin/python -m pytest -q
```
Núcleo em Python 3.11+ **somente biblioteca padrão**; plugin em JavaScript puro (sem build).
No SteamOS, o teste pré-atualização e o timer semanal executam a suíte em
`bubblewrap`, com código somente para leitura e HOME, diretórios XDG, processos
e rede isolados da sessão do jogador. Requer `bwrap` e o venv dedicado com
`pytest`; se o isolamento estiver indisponível, a atualização é bloqueada.
O instalador pós-atualização regenera o lançador apontando para a pasta definitiva.
Histórico de decisões e validação no hardware: [docs/desenvolvimento/](docs/desenvolvimento/).

Licença: [MIT](LICENSE).
