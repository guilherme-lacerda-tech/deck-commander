# Transferência de jogo: Deck → PC

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
emulador do PC precisa delas. Nada é baixado da internet.

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
