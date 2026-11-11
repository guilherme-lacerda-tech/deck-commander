# Transferência de jogo: Deck ⇄ PC (nos dois sentidos)

| Sentido | Pedido | Quem faz | Script |
|---|---|---|---|
| Deck → PC | `/transferir <jogo>` ou painel "Do Deck para o PC" | o PC busca no Deck | `tools\pc\transferir-do-deck.ps1` |
| PC → Deck | `/trazer <jogo do PC>` ou painel "Do PC para o Deck" | o PC envia para o Deck | `tools\pc\enviar-para-deck.ps1` |

Os dois pedidos ficam na mesma fila do Deck (`~/.local/share/deck-commander/transferir-fila.json`, campo `direcao`
`"deck->pc"` ou `"pc->deck"`). A tarefa do PC `tools\pc\transferir-fila.ps1` (a cada 5 min e no logon) atende os dois
sentidos e marca `copiando` / `pronto` / `falhou`; o bot avisa no Telegram pelo mesmo `notificar()`.

**O emulador vai junto.** Antes de enviar, o lado que recebe é conferido. Se o emulador não existir lá, é instalada
a versão **oficial** — origens num lugar só: `config/emuladores-oficiais.json` (Lichii, Ryujinx, PCSX2, DuckStation,
PPSSPP, Xenia Canary, RetroArch, Dolphin, Cemu, RPCS3, Azahar, melonDS, xemu, Flycast):

- **Deck → PC:** o PC baixa a versão Windows da página oficial de releases (API do GitHub ou do Forgejo do Ryujinx),
  **a mesma build do Deck** quando dá para saber (o sha256 do AppImage do Deck é procurado nos `digest` das releases;
  ex.: o AppImage do Lichii do Deck → build-83 → `lichii-windows-x86_64-pgo.zip` da build-83), senão a estável mais
  recente. Confere o sha256 publicado (campo `digest` do GitHub; sem ele, o tamanho), extrai em modo portátil em
  `D:\Emuladores\<pasta>` (Lichii: `user`; Ryujinx: `publish\portable`; PCSX2: `portable.ini`; DuckStation/Xenia:
  `portable.txt`) e registra em `D:\Emuladores\_downloads\downloads.json`. Nunca sobrescreve uma pasta que já existe.
  Opções: `-SemBaixarEmulador`, `-SimularEmulador`. Sozinho: `tools\pc\emulador-oficial.ps1 -Detectar` /
  `-Emulador lichii -Simular`.
- **PC → Deck:** o Deck instala o Flatpak do Flathub quando existe (`flatpak install --user -y flathub <id>`), senão o
  AppImage oficial da mesma página de releases (Lichii: `lichii-linux-x86_64-pgo.AppImage` da mesma build do PC;
  DuckStation: `DuckStation-x64.AppImage`; Xenia: o `.tar.xz` Linux), com sha256 quando publicado, nos lugares que
  o `dc/emulators.py` já procura (`~/Emulation/Lichii`, `~/Applications`, `~/.local/share/deck-commander/emus`).
- Dolphin no Windows não tem download automático oficial: o resumo indica https://dolphin-emu.org/download/.
- O resumo antes de enviar (bot e painel) diz "o emulador X vai ser instalado do outro lado (versão Y, da página
  oficial)". No Deck → PC isso vem da lista que o PC publica (`emuladores_pc`).

Ver dos dois lados, sem baixar nada (consulta a API oficial de verdade e mostra o que baixaria e de onde):

```
tools\pc\enviar-para-deck.ps1 -Detectar
```

# Deck → PC

Leva um jogo do Steam Deck para o PC Windows **com tudo**: arquivos (base, update, DLC), emulador
(o binário Linux vai só como referência) e toda a configuração — global e do jogo, controles, mods,
cheats, saves, perfis e keys/firmware/BIOS. Assim não precisa configurar de novo.

## Como usar

No Telegram: `/transferir <jogo>` mostra o que vai, o tamanho e o comando para o PC
(ligar no bot: `from .transferir import comando_transferir` → `return comando_transferir(self, args)`).

No PC (duplo clique pergunta o jogo):

```
tools\pc\transferir-do-deck.bat -Jogo switch2-donkey-kong-bananza
```

| Opção | Padrão | Para quê |
|---|---|---|
| `-Jogos` | `D:\DeckCommander\Jogos` | jogo em `<Jogos>\<console>\<jogo>\` |
| `-Destino` | `D:\DeckCommander\Transferidos` | `<id>\`: manifesto, cópia dos dados do emulador, LEIA-ME |
| `-Emuladores` | `D:\Emuladores` | emuladores portáteis procurados primeiro aqui |
| `-EmuDir` | — | força a pasta de dados do emulador |
| `-SoInstalar` | — | já copiou; só confere e instala no emulador |
| `-SoConfig` | — | só saves/config/mods/keys (o jogo já está no PC) |
| `-SemInstalar` / `-SemEmuladorLinux` / `-SemCacheNoDeck` | — | não instala / sem o binário Linux / não grava o cache de hash no Deck |

## Por que é segura

- **Hash**: o Deck calcula o sha256 de cada arquivo (em streaming, com cache por tamanho+data em
  `~/.local/share/deck-commander/transferir-hash-cache.json`). O PC confere cada um com `Get-FileHash`.
- **Retomável**: rodar de novo só baixa o que falta. Arquivo pela metade continua com `reget` do sftp.
  Arquivo com hash errado é baixado de novo (até 3 rodadas).
- **Backup**: antes de sobrescrever qualquer arquivo do emulador do PC, uma cópia vai para
  `<pasta de dados do emulador>\_backup-deck-commander\<data>-<jogo>\`.
- **Deck só é lido**: ssh/sftp de leitura. Nada é apagado nem alterado no Deck (o único arquivo escrito
  é o cache de hash, desligável com `-SemCacheNoDeck`).

## O que vai, por emulador

| Console | Emulador | Saves | Config/mods |
|---|---|---|---|
| Switch 2 | Lichii (Eden) `~/.config/eden`, `~/.local/share/eden` | `nand/user/save/0…0/<UUID>/<TITLE ID>/` + perfil `nand/system/save/8000000000000010` | `qt-config.ini`, `custom/<TID>.ini`, `load/<TID>`, `sdmc/atmosphere/contents/<TID>`, keys, firmware (`nand/system/Contents`) |
| Switch | Ryujinx `~/.config/Ryujinx` | `bis/user/save/<save_data_id>/`, achado pelo `bis/system/save/8000000000000000/0/imkvdb.arc` | `Config.json`, `profiles/`, `games/<tid>/` (sem cache), `mods/contents/<tid>`, keys, firmware |
| PS1 | DuckStation | `memcards/<título>_1.mcd`, `savestates/<serial>_*.sav` | `settings.ini`, `gamesettings/<serial>.ini`, cheats/patches, BIOS de 512 KB |
| PS2 | PCSX2 (flatpak) | `memcards/Mcd00*.ps2` (cartões compartilhados), `sstates/<serial>*` | `inis/PCSX2.ini`, `gamesettings/<serial>_*.ini`, pnach pelo CRC, BIOS |
| SNES/GBA/… | RetroArch | `saves/<rom>.*`, `states/<rom>.*` | `config/<núcleo>/<rom>.*`, remaps (o `retroarch.cfg` do Linux vai só de referência) |

Title id do Switch 2 vem do `base/exefs/main.npdm` (META → ACI0 + 0x10). Formato do `imkvdb.arc`
(Ryujinx) está documentado no topo de `dc/transferir.py`.

**Não vai**: cache de shader / PPTC (compilado para a GPU, o driver e o sistema do Deck; no PC o
emulador recompila e os primeiros minutos podem engasgar), logs.

**Keys, firmware e BIOS vão** (categoria `keys`): são do próprio usuário, tiradas do console dele, e o
emulador do PC precisa delas. Keys, firmware e BIOS nunca são baixadas da internet (só o emulador oficial, quando falta).

## Caminhos

Arquivos de config com caminhos do Deck (`/home/deck/…`, `/run/media/deck/…`) são reescritos na
instalação para os do PC (com `/`), pelas regras `reescrever` do manifesto. O que sobrar apontando para
o Deck (ex.: uma pasta de Downloads que não veio) é listado no `LEIA-ME.txt`.

## Limites conhecidos

- Ryujinx: se o PC já tem saves de outros jogos (índice `imkvdb.arc` diferente), o índice e os saves não
  são trocados; o LEIA-ME explica como copiar o save à mão.
- Controles: o mapeamento vem, mas o controle do Deck tem outro ID no PC; pode ser preciso escolher o
  controle do PC na tela de controles do emulador (os botões já vêm mapeados).
- PSP, Xbox 360 e outros sem coletor próprio: vai só o jogo (o manifesto avisa).
- Manifesto é TSV: arquivo com TAB/quebra de linha no nome fica de fora (listado em `excluidos`).

# PC → Deck

Leva um jogo do PC para o Deck com os dados do emulador do PC (saves, config do jogo, mods, keys/firmware/BIOS do
próprio usuário).

## Como usar

No Telegram: `/trazer` lista os jogos do PC; `/trazer <jogo>` mostra o que vem e o botão **Trazer pro Deck**;
`/trazer fila` mostra o andamento. No painel do Decky: bloco **Do PC para o Deck**.

No PC, direto:

```
tools\pc\enviar-para-deck.ps1 -Listar                 jogos do PC que podem ir
tools\pc\enviar-para-deck.ps1 -Jogo psx-hercules      envia e instala
tools\pc\enviar-para-deck.ps1 -Jogo <id> -Simular     só mostra o que iria
tools\pc\enviar-para-deck.ps1 -Jogo <id> -DestinoTeste ~/dc-teste-receber   tudo dentro da pasta de teste
```

| Opção | Padrão | Para quê |
|---|---|---|
| `-Jogos` | `D:\DeckCommander\Jogos` | jogos em `<Jogos>\<console>\<jogo>\` |
| `-Emuladores` | `D:\Emuladores` | emuladores portáteis (de onde saem os dados e as pastas de ROM configuradas) |
| `-Destino` | `D:\DeckCommander\Enviados` | `<id>\`: manifesto.json, SHA256SUMS, cache de hash, log da instalação |
| `-DestinoTeste` | — | área e instalação dentro dessa pasta do Deck (não toca `~/Emulation` nem os emuladores; não instala emulador) |
| `-Simular` / `-SemEmulador` / `-ConfigGlobal` | — | não copia / não instala emulador no Deck / troca também a config global do Deck |
| `-Publicar` | — | manda a lista `pc-jogos-transferiveis.json` ao Deck (a tarefa faz isso sozinha quando muda) |

## Manifesto do PC

Jogos transferíveis = pastas em `D:\DeckCommander\Jogos\<console>\<jogo>` + jogos soltos nas pastas de ROM
configuradas nos emuladores portáteis (DuckStation e PCSX2: `[GameList]`; Lichii: `Paths\gamedirs`; Ryujinx:
`game_dirs`; só leitura, caminhos do Deck ignorados). Id = `<console>-<nome>` (ex.: `psx-hercules-slus-00529`).

Cada arquivo vai com sha256, tamanho, categoria e destino lógico: `{JOGOS}/<console>/<jogo>/...` e `{EMU}/...` (pasta
de dados do emulador). Coletores (o inverso dos do Deck → PC): Lichii (pelo title id do `main.npdm`), Ryujinx (saves
pelo `imkvdb.arc`), DuckStation (serial/título), PCSX2 (serial, memcards), PPSSPP (id do UMD), RetroArch (nome da ROM).

## No Deck

1. Área de recebimento: `~/.local/share/deck-commander/receber/<id>/` (`manifesto.json`, `SHA256SUMS`,
   `arquivos/JOGOS/...`, `arquivos/EMU/...`).
2. Cópia por sftp com `put`/`reput` (arquivo pela metade continua de onde parou); conferência **no Deck** com
   `sha256sum --strict -c`; o que não bate é mandado do zero (até 3 rodadas).
3. `python3 -m dc.transferir receber <id>` confere de novo, instala o emulador se faltar e copia:
   - jogo → `~/Emulation/roms/<console>/<jogo>/`;
   - `{EMU}` → pasta Linux do emulador: Lichii `~/.local/share/eden` (e `{EMU}/config` → `~/.config/eden`), Ryujinx
     `~/.config/Ryujinx`, DuckStation `~/.local/share/duckstation`, PCSX2 `~/.var/app/net.pcsx2.PCSX2/config/PCSX2`,
     PPSSPP `~/.var/app/org.ppsspp.PPSSPP/config/ppsspp`, RetroArch `~/.var/app/org.libretro.RetroArch/config/retroarch`;
   - `.ini/.json/.cfg` com caminhos do Windows (`D:/Emuladores/...`, `D:\\...` em JSON) são reescritos para os do Deck;
   - **backup** de qualquer arquivo do Deck antes de sobrescrever: `<pasta>/_backup-deck-commander/<data>-<id>/`
     (jogos: `~/.local/share/deck-commander/_backup-deck-commander/...`);
   - config **global** do emulador do Deck é mantida se já existe (`--config-global` troca); Ryujinx com índice de
     saves diferente no Deck: índice e saves não são misturados (aviso no relatório);
   - no fim, o jogo entra na biblioteca do Steam pela mesma função do `/sync` (`syncer.add_to_steam`).
4. Se o Deck ainda não tem `dc/receber.py` instalado, o PC manda o arquivo pela entrada padrão (`python3 - receber`),
   sem instalar nada.

Nada é apagado no PC. No Deck, só a pasta de teste do `-DestinoTeste` pode ser apagada por você depois.

## Limites conhecidos (PC → Deck)

- Sem title id/serial/id do UMD, vão o jogo e a config geral, sem saves (o manifesto avisa).
- Perfis do Lichii (`nand/system/save`) e config global só entram se o Deck não tiver: se o perfil do PC tiver outro
  UUID, o save pode precisar ser copiado para a pasta do perfil do Deck.
- Dolphin, Cemu, RPCS3, Azahar, melonDS, xemu, Flycast: vai o jogo (e o emulador, se faltar), sem coletor de dados.
