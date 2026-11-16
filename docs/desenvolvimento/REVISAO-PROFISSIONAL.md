# Revisão profissional (15–16/11/2026)

Motivo: instalado no Deck do irmão do usuário (que já usava EmuDeck), o Deck Commander pareceu amador. Este arquivo é
o plano e o andamento — atualizado a cada etapa (✅ feito e testado · 🔄 em andamento · ⏳ falta).

## Falhas relatadas
| # | Falha | Causa encontrada | Estado |
|---|---|---|---|
| 1 | Abas de console sumiram da biblioteca (Deck do usuário) | ao acordar do descanso o serviço regravou as abas do TabMaster com a lista de atalhos incompleta → listas vazias → aba escondida | ✅ proteção + abas regravadas (por coleção) |
| 2 | ~400 jogos de Wii do EmuDeck viraram atalhos | a biblioteca varria toda `Emulation/roms`, que é a MESMA pasta do EmuDeck | ✅ `dc/biblioteca.py`: com EmuDeck/RetroDECK só entra o que o Deck Commander trouxe; limpeza única com aviso |
| 3 | PS2 abriu "como primeira vez" (pediu ROMs e BIOS) | comando fixo no PCSX2 Flatpak (o EmuDeck usa o AppImage, com outra configuração); Flatpak novo sem configuração | ✅ emulador existente primeiro, escolha no painel, Flatpak pronto (BIOS/jogos/controle) |
| 4 | Toda atualização exige reinstalar | não existe atualização automática | ✅ `dc/atualizar.py` — testado de ponta a ponta no Deck |
| 5 | Escolher o emulador de cada console (Switch tem vários) | comando fixo por console | ✅ painel → Qualidade e controles |
| 6 | Port nativo feito pela comunidade não apareceu | biblioteca só conhece ROMs | ✅ jogo não-Steam → aba do console (painel) |
| 7 | Acompanhar RetroAchievements (platinar) | não existia | ✅ tela Conquistas + /conquistas |

## Plano técnico
- **Emuladores** (`dc/emulators.py`): candidatos por console (AppImage do EmuDeck/`~/Applications` primeiro, depois
  Flatpak, depois núcleo do RetroArch); escolha do usuário em `emulators.json`, tela no painel; não instalar Flatpak se
  o console já tem emulador; Flatpak que o Deck Commander instalar já sai configurado (BIOS em `~/Emulation/bios`,
  sem assistente de primeira vez, pasta de jogos).
- **Configuração de outros programas**: com EmuDeck/RetroDECK, os recursos que mexem na configuração dos emuladores
  (botões de trás, continuar) só ligam se o usuário pedir; sempre com backup.
- **Atualização** (`dc/atualizar.py`): confere 1×/dia a versão no GitHub (repositório público), avisa no painel e no
  Telegram, atualiza com um toque (guarda a versão anterior para voltar), recarrega serviços e plugin.
- **Ports nativos**: biblioteca reconhece ports da comunidade instalados (Flatpak/AppImage/pasta `ports`).
- **RetroAchievements**: conta do usuário (nome + chave de API colados por ele), progresso por jogo no painel e no bot.
- **Ramos prontos para juntar**: `re/nova` (filtro do RomTranslate), `melhorias/analise` (Castlevania).
- **Engenharias reversas** (sessões): Soul Calibur 3, Call of Duty X360, Dragon Quest VIII — retomar quando o
  limite de uso renovar.
- **Teste de verdade**: Deck simulado com EmuDeck (pasta pessoal falsa) do instalador ao primeiro jogo.

## Andamento
- 15/11 22:40 — 1 e 2 resolvidos (commits `tabs` e `ce339e7`).
- 15/11 23:10 — 3 a 7 resolvidos, com testes; atualização testada de verdade no Deck (baixou, testou 937 testes no
  Deck, trocou, serviços voltaram, revisão 14/14). Ramos `re/nova` (filtro do RomTranslate) e `melhorias/analise`
  (Castlevania) juntados. Instalador no repositório (`tools/instalador/`), com 3 defeitos corrigidos.
- Versão 0.10.0: manual, tutorial, changelog e visão geral atualizados.
