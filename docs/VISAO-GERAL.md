# Deck Commander — Visão geral do projeto

Tudo o que o sistema faz hoje, o que foi testado de verdade, os limites conhecidos e ideias do que adicionar.
Situação em 10/11/2026 · versão 0.6.0 · 605 testes automáticos passando · repositório público
github.com/guilherme-lacerda-tech/deck-commander.

> **Legenda:** ✅ funcionando e testado de verdade no Deck/PC · 🧪 pronto, com testes automáticos, mas ainda sem
> uso real · ⚠️ funciona com limitação · ⏳ em andamento

---

## 1. Em uma frase
O Deck Commander transforma o Steam Deck numa central de jogos: você manda um link pelo Telegram (ou toca num botão
no Deck) e o jogo baixa, entra na biblioteca do Steam com capa e aba do console, já vem configurado, ajustado e
traduzido para português — e ainda conversa com o seu PC para jogar os jogos dele no Deck e levar jogos de um lado
para o outro.

## 2. Como se usa (as três portas de entrada)
| Porta | Para quê | Situação |
|---|---|---|
| **Telegram** (seu bot) | Baixar, traduzir, organizar, ver status de qualquer lugar | ✅ |
| **Painel no Deck** (botão "…" → Decky → Deck Commander) | Tudo pelo controle, sem Telegram nem terminal | ✅ |
| **Assistente no PC** (`tools\pc\Assistente Deck Commander.bat`) | Ligar o PC ao Deck, emuladores, transferências, biblioteca do PC | 🧪 (partes testadas; a janela em si ainda não foi usada por você) |

---

## 3. Biblioteca do Steam
- ✅ Cada jogo de emulador vira um jogo no Steam, com capa (SteamGridDB) e na **aba do console** (TabMaster).
- ✅ Entra **ao vivo** pelo plugin do Decky, em ~10 s, sem reiniciar o Steam. Se um atalho sumir sem querer, ele recria.
- ✅ Abas automáticas: uma por console, uma por loja (Epic/GOG pelo Unifideck), **"Em português"**, **"Computador"**
  (jogos do PC) e "Emuladores". Aba vazia fica escondida; aba nova aparece na hora.
- ✅ 28 consoles reconhecidos: PS1, PS2, PS3, PSP, Switch, Switch 2, 3DS, DS, Wii U, Wii, GameCube, N64, SNES, NES,
  GBA, GB, GBC, Xbox, Xbox 360, Dreamcast, Saturn, Sega CD, Mega Drive, Master System, Game Gear, PC Engine, Arcade, PC.
- ✅ Atalho fixo por jogo (`dc-launch`): trocar a ROM, o formato ou o emulador não perde horas jogadas, capa nem coleções.
- ✅ Jogos com vários discos viram um atalho só; atualização e DLC de Switch entram sozinhas.

## 4. Downloads
- ✅ Mande o nome do console e o `.torrent` ou magnet; quando termina, o jogo entra na biblioteca e o bot avisa.
- ✅ Reconhece o console pelo nome (ex.: "God of War" não vai mais parar no Xbox 360), aceita 7z/zip, PS3, Switch 2, Wii U.
- ✅ Avisa **antes** de baixar um jogo repetido (`/baixar` força).
- ✅ Link inválido é recusado com explicação; o mesmo magnet duas vezes não duplica.
- ✅ Bateria: na bateria os downloads esperam a tomada (abaixo de 30% sempre pausam); `/bateria sim` libera.
- ✅ Download sem ninguém compartilhando não trava a fila; o bot avisa se ficar 30 min parado ou der erro (disco cheio, cartão SD removido).
- ✅ Compartilhamento (seeding) para em razão 1.0 ou 60 min.
- ✅ Painel: pausar/retomar um ou todos, limpar da lista o que já está na biblioteca.

## 5. Tradução para português (o coração do projeto)
### 5.1 Como funciona
- ✅ **Automática:** baixou um jogo que não está em português → entra na fila e chega traduzido; avisa a cada 20%.
- ✅ **Ordem de preferência:** 1) já em português (oficial, inclusive o PT-BR "escondido" dentro do jogo, como no
  Castlevania Belmont's Curse); 2) tradução da comunidade conferível; 3) IA.
- ✅ **IAs (todas grátis):** Index-Translate na internet → IA do seu PC (qwen2.5 pela placa de vídeo, por túnel
  seguro) → IA do próprio Deck (sem internet).
- ✅ **Nunca estraga o jogo:** Switch vira **mod** (o jogo original não é tocado); retrô vira cópia "(PT-BR)"; códigos
  de cor/variáveis do texto são protegidos; tudo é relido e conferido antes de instalar.
- ✅ **2ª chance:** frase em que a IA perdeu os códigos é refeita (até por pedaços); frase que não cabe na caixa é
  encurtada (prova real no Pokémon Z-A: 20/20 códigos corrigidos, 17/20 passaram a caber).
- ✅ **Nada fica "impossível para sempre":** quando o sistema aprende um formato novo, ele tenta de novo sozinho os jogos que falharam.
- ✅ Perguntas pendentes (Sim/Não), parar/retomar (sem perder o que já foi traduzido), aviso de tarefa travada, limpar histórico.

### 5.2 O que já foi traduzido de verdade
| Jogo | Formato | Resultado |
|---|---|---|
| Pokémon Legends Z-A | Trinity (Oodle) | ✅ 75.152 frases |
| Zelda: Breath of the Wild | MSBT dentro de SARC | ✅ 27.220 frases |
| Final Fantasy Resonance | Unreal Engine (.locres/.pak) | ✅ 24.717 frases |
| Luigi's Mansion 3 | init.patch (formato próprio) | ✅ mod instalado |
| Pokémon FireRed / LeafGreen (GBA dentro do Switch) | Meowth | ✅ |
| Castlevania Belmont's Curse | Unity | ✅ já tinha PT-BR oficial — configurado para abrir em português |

### 5.3 Formatos que o sistema lê
- ✅ Nintendo MSBT (padrão), SARC aninhado, Trinity (Pokémon), Next Level Games (LM3), Unreal Engine (.pak sem criptografia), Unity (tabelas do pacote Localization, testado com jogo real).
- 🧪 GameMaker, Godot, RE Engine (Capcom), RPG Maker MV/MZ, CRI (.cpk): prontos, perguntam antes com nº de frases e tempo estimado; ainda sem jogo real desses motores na biblioteca.
- ✅ Retrô (PS1, PS2, PSP, SNES, NES, N64, GameCube, DS, GBA) pelo RomTranslate Studio, com filtro rigoroso contra lixo.
- ⚠️ Não traduz: Unreal com pacote criptografado (seria quebrar a proteção do jogo); jogos cujo texto está num formato
  ainda desconhecido (ex.: Hercules PS1 — o painel explica em vez de oferecer "Retomar").

## 6. Qualidade, desempenho e controles
- ✅ Perfis de resolução por console e exceção por jogo (`/qualidade` ou painel): nativo / 2x / 3x / padrão.
- ✅ **Auto-ajuste:** começa num nível que roda bem, sobe a cada medição lisa e desce na primeira travada.
- ✅ **Benchmark sem jogar:** abre o jogo sozinho, mede e fecha (recusa se a IA do Deck estiver traduzindo).
- ✅ Medição real de cada partida (MangoHUD).
- ✅ Controles: verificação por emulador; Dolphin e melonDS configurados sozinhos; **escolha simples "Controle de Xbox"
  ou "Controle de Switch"** no Ryujinx e no Lichii (painel).
- ⚠️ Azahar (3DS), Cemu (Wii U) e RPCS3 (PS3) pedem que você escolha o controle uma vez no modo Desktop.

## 7. Organizar e desinstalar
- ✅ `/duplicados` e remover repetidos.
- ✅ **Desinstalar como no Steam:** "Gerenciar → Remover jogo não Steam" abre na tela a pergunta "apagar os arquivos
  também?"; ou pelo painel ("Desinstalar jogos"); ou pelo Telegram. Arquivos ficam 30 dias na quarentena (dá para desfazer).
- ✅ `/devolver` traz de volta um jogo tirado; o original de um jogo traduzido fica guardado.
- ✅ Conversão de Switch: confere update/DLC, organiza numa pasta, descompacta NSZ.

## 8. Jogar os jogos do PC no Deck (aba "Computador")
- ✅ Acha os jogos do PC sozinho (Steam, Epic, Riot, GOG, Ubisoft, Xbox) e também **qualquer atalho** colocado em
  `C:\Users\Public\Documents\Deck Commander\Jogos do PC` (ex.: Donkey Kong no Lichii do PC).
- ✅ Hoje: 14 jogos na aba (Fortnite, 2XKO, VALORANT, Cyberpunk, God of War Ragnarök…), lista atualizada pelo próprio PC.
- ✅ Acorda o PC (Wi-Fi, inclusive de fora de casa pelo "porteiro" Fire TV + Tailscale) e ele volta a dormir ~2 min depois de fechar o jogo.
- ✅ Streaming pelo Sunshine (PC) + Moonlight (Deck); os botões do Deck chegam como controle de Xbox.
- 🧪 Ainda não testado de ponta a ponta com um jogo de verdade (abrir, jogar, PC dormir).

## 9. Levar jogos entre o Deck e o PC
- ✅ **Deck → PC:** jogo + update + DLC + saves + configuração do emulador (geral e do jogo) + controles + mods +
  keys/firmware/BIOS. Cada arquivo conferido (sha256), retoma se cair, backup antes de sobrescrever, nada apagado no Deck,
  o PC não dorme enquanto copia. Pelo Telegram (`/transferir` + botão "Enviar pro PC") ou pelo painel.
- ✅ Testado de verdade: Hercules (PS1) e **Donkey Kong Bananza** (19,7 GB, 166 mil arquivos) instalado no Lichii do PC.
- ✅ Emuladores Windows oficiais em `D:\Emuladores` (Lichii, Ryujinx, PCSX2, DuckStation, PPSSPP, Xenia), modo portátil, assinatura conferida.
- ⏳ **PC → Deck** e "instalar o emulador do outro lado se faltar": em desenvolvimento.

## 10. Segurança e saúde
- ✅ Backup diário de configurações e saves (com teste de restauração antes de valer).
- ✅ Quarentena: nada é apagado sozinho; arquivo suspeito ou removido fica 30 dias.
- ✅ Modo seguro (`/sos` ou painel): desliga as automações sem apagar nada.
- ✅ Diagnóstico: confere tudo e diz o que falta fazer, sem mudar nada.
- ✅ Testes automáticos toda semana no próprio Deck (hoje 605 passando).
- ✅ Nenhum segredo no código (token, códigos e IPs ficam só nas configurações de cada aparelho).

## 11. Instalação e distribuição
- ✅ Instalação em 1 comando no Deck, com QR code para criar e parear o bot do Telegram.
- ✅ Tutorial de instalação e manual de uso em PDF; assistente gráfico no PC.
- ✅ Repositório público no GitHub; cada pessoa configura a própria rede (nada da sua casa no código).
- ✅ Atualizar = rodar o instalador de novo (não apaga nada).

## 12. Integração com a sua casa
- ✅ O agente da casa (C:\AutomacaoCasa) não deixa o PC dormir durante uma transferência e devolve ao sono depois.
- ✅ Tarefas do PC rodam sem janela piscando.

---

## 13. Ideias do que adicionar
**Mais fácil de usar**
1. Tela no painel mostrando **capa + tamanho + tempo jogado** de cada jogo, com ações rápidas (traduzir, qualidade, desinstalar, levar para o PC).
2. **Busca de jogos para baixar** dentro do painel a partir de fontes legais que você mesmo cadastrar (seus próprios dumps em rede/HD externo).
3. **Notificação na tela do Deck** (não só no Telegram) quando um download ou tradução termina.
4. Painel com **modo família**: só jogar, sem as telas de configuração.

**Saves e nuvem**
5. **Saves sincronizados** Deck ↔ PC automaticamente (jogou no PC, continua no Deck), com histórico de versões.
6. Backup dos saves para a nuvem (Google Drive/OneDrive) com um clique.

**Tradução**
7. **Revisão da tradução no próprio jogo**: marcar uma frase estranha (foto/descrição) e o sistema corrige só ela.
8. **Dublagem/legenda de vídeos** dos jogos (cutscenes) com IA local.
9. Novos formatos conforme forem aparecendo jogos (ex.: VX Ace, OptimizedTranslation do Godot, zstd do RE Engine).
10. Glossário compartilhado entre jogos da mesma série (nomes de golpes, lugares).

**Desempenho**
11. **Perfil de energia por jogo** (TDP/GPU do Deck) aplicado sozinho junto com a resolução.
12. Pré-compilar shaders em segundo plano quando o Deck está na tomada e parado.

**PC e casa**
13. **Jogar do Deck na TV** pelo PC (o PC liga a TV e transmite) com um botão.
14. Fila de transferência agendada para a madrugada.
15. Tradução feita **pelo PC** quando ele estiver ligado (mais rápida), devolvendo o mod para o Deck.

**Para o seu irmão / outras pessoas**
16. **Instalador com tela** no próprio Deck (sem Konsole).
17. Página de releases no GitHub com changelog e atualização com um botão no painel.
