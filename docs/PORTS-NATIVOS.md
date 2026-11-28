# Ports nativos (recompilação) que batem com a biblioteca do Deck

Fonte: pesquisa da sessão "Análise e melhorias do projeto (fork)" em 28/11/2026, conferida por ela nas páginas
oficiais do GitHub. **Não validado por esta sessão**: versões, licenças e compatibilidade com Linux/Deck podem mudar.
Nenhum desses ports vem com o jogo; cada um pede o dump do próprio dono.

Como entram no Deck Commander: o port é um jogo não-Steam. O `dc/ports.py` põe ele na aba do console quando você
marca no painel → "Ports" (ou `python3 -m dc.ports marcar "<nome>" <console>`).

## Servem agora (o dump que o dono tem é aceito)

| Jogo | Port | Versão | Plataformas | Dump aceito | Situação no Deck do dono |
|---|---|---|---|---|---|
| Donkey Kong Bananza | DKB Recomp — github.com/Lucas-blip-png/dkb-pc-recomp | v0.5.3 (28/11), GPL-3.0 | Windows + Linux AppImage (Linux em "prévia") | 1.0.0 ou atualização 3.2.0 (title version 458752), `.nup`/`.nx` ou pastas ExeFS/RomFS | `~/Emulation/roms/switch2/Donkey Kong Bananza` tem `updates/458752` (3.2.0). Tem perfil de Steam Deck (1280x800, 40 fps; números não medidos). A sessão fork estava instalando. |
| Zelda Tears of the Kingdom | TotK PC Recomp — github.com/valentderah/totk-pc-recomp | v0.5.1 (8.4k estrelas) | Windows + Linux AppImage/PGO, perfil 16:10 de Deck | base + atualização 1.1.0, 1.2.1 ou 1.4.3 | Dono tem base + v720896 (1.4.3) em `~/Emulation/roms/switch/The Legend of Zelda Tears of the Kingdom [NSP]/` |
| Zelda TotK (alternativa) | UltraTears — github.com/kuraeow/ultratears | v0.4.0 | opção "For Linux (Steam Deck)" | só 1.4.3 | idem |

## Parcial

| Jogo | Port | Observação |
|---|---|---|
| God of War 1 (PS2) | gow-native-pc — github.com/Vnnc1/gow-native-pc v0.6.1, sobre PS2Recomp (github.com/ran-j/PS2Recomp) | Exige o disco americano SCUS-97399 (Europa/Japão têm builds isoladas). O "God of War 1 (Dublado)" do dono provavelmente não serve direto. Suporte a tradução de fãs existe. Linux/Deck experimental, não validado. |

## Sem port jogável (continuam no emulador)

- Pokopia (3 repositórios, 0–1 estrela).
- Super Mario Galaxy (só decompilação: SMGCommunity/Petari).
- Castlevania SotN (só decompilação: Xeeynamo/sotn-decomp).
- BotW, Luigi's Mansion 3, Pokémon Legends Z-A: nada utilizável.
- CoD Black Ops 1/2: nada utilizável. De BO só existe port de Zombies (Joolace/T5-Jool---Black-Ops-Recomp, 20 estrelas).

## Úteis fora do escopo

- Hollow Knight Silksong: tem versão nativa Linux na Steam (melhor que emular o de Switch).
- Kits de recompilação Xbox 360: rexglue/rexglue-sdk, XenonRecomp.
- Listas gerais: portedgames.com/recompiled-games, recompendium.com.

## Pendências

- Validar no Deck cada port marcado "servem agora": abre, controle, desempenho medido (não usar os números do
  autor), saves no lugar certo e backup.
- Painel: sugerir o port quando o jogo da biblioteca tiver um port conhecido. Hoje a marcação é manual.
