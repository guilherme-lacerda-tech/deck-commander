# Simulação total — 10/11/2026 (manhã)

Tudo foi simulado no Deck em pastas temporárias (`/tmp/dc-sim*`, já apagadas), com Telegram, qBittorrent, Steam, systemctl e IA trocados por versões falsas. Não mandei mensagem no seu Telegram, não baixei jogo, ROM, BIOS ou chave, não toquei na biblioteca real e não parei a tradução do Final Fantasy (`36f85722cec7`), que continua rodando.

## (a) Está pronto para você testar?

**Sim, pode mandar jogos.** O caminho "magnet ou .torrent → download → /sync → atalho no Steam → tradução automática" funcionou em todos os consoles que simulei. Os 9 problemas que achei hoje estão corrigidos, testados e já rodando no Deck: o bot foi reiniciado às 10:25 com o código novo, e o Deck está idêntico à `main`.

Ressalvas:
- Arquivo `.iso`, `.chd`, `.cue`, `.rvz` ou `.cso` **sem o nome do console** no download continua gerando a pergunta "qual console?". Esses formatos existem em vários consoles. Para evitar a pergunta, mande o nome do console antes do magnet (ex.: `PS2`).
- **O benchmark não rodou.** A IA do Deck estava traduzindo o FF (carga 4,7, modelo carregado), e a regra era não medir nessas condições. Aproveitei para colocar uma trava: agora o benchmark se recusa a rodar sozinho quando isso acontece.

## (b) Cenários

| Cenário | Resultado | Erro/bug | Corrigido? | Commit |
|---|---|---|---|---|
| 1. Downloads de 30 tipos (Switch NSP/XCI + atualização, PS2 ISO/MDF/RAR em 3 partes, PS1 CUE+BIN/CHD multidisco, SNES ZIP, GBA 7Z, PS3 pasta, X360 GoD, 3DS, DS, GC, Wii, PSP, Wii U, DC, Xbox, N64, MD, ROM traduzida, vazio, txt, Switch 2) | 25 certos de cara depois da correção; os 5 que perguntam o console são ambíguos de verdade | **"God of War …" ia para o Xbox 360** (a palavra "GoD" casava com "God") e o PSP era descartado | sim | `46227f8` |
| 1. /add sem console | ok | a categoria "auto" fazia o nome do download ser **ignorado** (pasta "Shadow Hearts PS2" perguntava o console) | sim | `46227f8` |
| 1. ZIP/7Z de cartucho | ok | `.7z` ia sempre para "arcade" e o jogo era descartado; `.zip` sempre perguntava. Agora o bot olha a lista de arquivos dentro do pacote, sem extrair | sim | `46227f8` |
| 1. PS3 em pasta, X360 GoD sem "(GOD)", dump de Switch 2 | ok | perguntavam o console ou caíam como "Switch" e eram descartados; agora são reconhecidos pela estrutura da pasta | sim | `46227f8` |
| 1. "Wii U" no nome | ok | era classificado como Wii | sim | `46227f8` |
| 1. Multidisco PS1 (FF7, 3 discos) | ok | **4 atalhos** (o `.m3u` + cada disco solto); agora é 1 | sim | `46227f8` |
| 1. Atualização de Switch baixada sozinha | ok | era descartada ("nenhum arquivo jogável") e o aviso se repetia a cada /sync; agora vai para a pasta do Switch, de onde o Ryujinx carrega sozinho | sim | `46227f8` |
| 1. Download só com .txt | ok | perguntava o console; agora diz "não achei arquivo de jogo", uma vez só | sim | `46227f8` |
| 1. Título "Halo 3 (GOD)" | ok | agora "Halo 3" | sim | `46227f8` |
| 1. Vazio / repetido / tradução [BR] / RAR em partes / MDF de PS2 | ok | — | — | — |
| 2. Usuário novo (pareamento, /help, console, magnet, /sync, listas) | ok | código errado só dizia "Acesso negado"; agora explica que o código está errado ou venceu e como gerar outro | sim | `5023619` |
| 2. "sim"/"não" digitado em vez do botão | ok | **ignorado em silêncio**, inclusive o "Sim" da tradução fora do padrão, que nunca chegava ao bot real. Agora vale como tocar no botão e, sem pergunta aberta, o bot avisa | sim | `5023619` |
| 2. Mesmo magnet duas vezes | ok | dizia "Adicionado" de novo; agora diz "já está na fila (nome)" | sim | `5023619` |
| 2. Resposta "Adicionado (auto)" | ok | trocado por "descubro o console quando terminar; se não der, pergunto" | sim | `5023619` |
| 2. "baixa god of war pra mim" | ok | silêncio; agora explica que precisa do magnet ou do .torrent | sim | `5023619` |
| 2. Console "360" e "Xbox Series S" | ok | **caractere invisível** (backspace) no padrão: "360" não era reconhecido e "Series S" virava Xbox | sim | `5023619` |
| 2. /disk num Deck sem Steam logado | ok | dava erro; agora lista sem "última vez jogado" | sim | `5023619` |
| 2. Confuso: PS9, só texto, /traduzir inexistente, /traduzir biblioteca, /remover (ambíguo, nº errado, confirmação), /devolver, /qualidade, /status, /sync 3x, /console, /aprovar, botão velho, comando inexistente, /STATUS, /status@bot, emoji, "obrigado", 25 comandos por minuto | todas as respostas em português e claras; conversa comum é ignorada (de propósito) | — | — | — |
| 3. Fila MAX_JOBS=2 com 3 tarefas, uma morrendo em 40% | ok: nunca rodaram mais de 2 ao mesmo tempo; a morta foi avisada ("parou… /traduzir retomar"), retomou de 40% e terminou; nenhuma ficou "rodando" morta | — | — | — |
| 3. Avisos de 20% / cache | ok: "Acompanhando 40%" e retomada reaproveitando o cache (só pediu o que faltava) | — | — | — |
| 3. Provedor que falha (503) na tradução paralela | ok: sai depois de 3 falhas e os outros terminam | — | — | — |
| 3. **IA que cai no meio da resposta** (túnel do PC) | ok depois da correção | **a tradução paralela travava para sempre** como "rodando" e a serial morria inteira | sim | `074b773` |
| 3. Tarefa viva mas travada | pendente | o bot não tinha como parar; o "retomar" responde "ainda está rodando" | **solução pronta na branch `pronto/parar-tarefa-travada`** | `f116474` |
| 4. Benchmark com a IA do Deck traduzindo | recusado (correto) | antes rodaria e o FPS baixo faria o auto-ajuste baixar a qualidade à toa | sim | `9e3912e` |
| 4. Benchmark real (emulador fecha, MangoHud, auto-ajuste) | não rodou | IA do Deck ocupada com o FF (regra da tarefa) | — | — |
| 5. Instalação nova (HOME vazio, `./setup-deck.sh --all --no-downloads`) | ok: unidades, configs dos emuladores, controles, ZIP do plugin, bot esperando o token | **PS1 e Switch não abrem numa instalação nova**: o instalador não instala DuckStation nem Ryujinx (e o DuckStation saiu do Flathub); a ferramenta Oodle do PC tinha o IP deste Deck fixo | **solução pronta na branch `pronto/instalacao-nova`** | `9aa3d28` |
| Testes pré-existentes quebrados (magnets falsos curtos) | 2 arquivos corrigidos por mim; o terceiro era de outra sessão, que já corrigiu | — | sim | `46227f8` |

Testes na `main` (já com os merges de outras sessões): **525 passando, 3 pulados**. Cada branch `pronto/` passa na própria suíte inteira.

## (c) Como testar hoje (10 passos)

1. No Telegram, mande o **nome do console** (ex.: `PS2`) e depois cole o magnet ou encaminhe o `.torrent`. Se não mandar o console, tudo bem: o bot descobre pelo nome do download.
2. Mande **3 ou 4 jogos de consoles diferentes** (ex.: 1 Switch, 1 PS2, 1 PS1, 1 GBA). Mandar o mesmo de novo deve responder "já está na fila".
3. Espere o aviso "download terminou" (o bot avisa sozinho) ou acompanhe com `/status`.
4. Mande `/sync`. Cada jogo aparece como "✅ nome → console". Se aparecer "❓ qual console?", toque/responda `/console <código> ps2` e mande `/sync` de novo.
5. Abra a biblioteca do Steam: os jogos aparecem em ~10 segundos, já com capa (sem reiniciar).
6. Jogo que não está em português entra na tradução sozinho. Acompanhe com `/traduzir status`; o bot avisa a cada 20%.
7. Se o bot perguntar algo com Sim/Não, pode **tocar no botão ou digitar "sim"/"não"** (agora as duas formas funcionam).
8. Abra um jogo pelo Steam e jogue 2 minutos. Com um jogo aberto, a IA do Deck pausa a tradução para não roubar desempenho.
9. Teste `/remover <jogo>` (pede confirmação; os arquivos vão para a quarentena, nada é apagado) e `/devolver <jogo>`.
10. Com um jogo multidisco de PS1, confira que aparece **um** atalho só.

**O que NÃO esperar ainda:**
- `.iso`/`.chd`/`.cue`/`.rvz`/`.cso` sem o console no nome: o bot vai perguntar (passo 4).
- Tradução de jogo grande leva **horas**. Com a IA do PC ocupada pelo FF, os próximos jogos ficam na fila (2 de cada vez).
- Switch 2 não é aceito (o Lichii é experimental).
- O benchmark (`python3 -m dc x bench`) recusa enquanto a IA do Deck estiver traduzindo.
- Tarefa de tradução travada "viva": hoje só dá para parar pelo SSH. A correção está na branch abaixo, esperando seu OK.

## (d) O que falta para 100% e para outras pessoas usarem

**Soluções prontas (cada uma testada, numa branch própria, sem deploy e sem merge):**

| Pendência | Plano | Solução | O que muda para você |
|---|---|---|---|
| Tradução que trava "viva" (IA travou sem cair) fica "rodando" para sempre, e o bot não tem como parar | (1) vigia: 45 min "rodando" sem progresso → um aviso no Telegram; (2) `/traduzir parar <código>` encerra o processo e marca "interrompida"; (3) `/traduzir retomar` continua do cache | **solução pronta na branch `pronto/parar-tarefa-travada` — aguarda seu OK para implantar** | Se uma tradução empacar, chega "⚠️ X está parada há 45 min" com os botões parar e retomar. Nada traduzido se perde. Implantar = merge + enviar `dc/traducao/comandos.py` + reiniciar o bot (as traduções continuam) |
| Instalação para outra pessoa: PS1 e Switch não abrem (sem DuckStation/Ryujinx); IP deste Deck fixo na ferramenta Oodle do PC | (1) PS1 sem DuckStation abre no RetroArch com o núcleo SwanStation (o DuckStation saiu do Flathub); (2) o Ryujinx do Flathub (1.3.3) só é instalado se o Deck não tiver um; (3) a ferramenta Oodle pede o endereço do Deck em vez de assumir o seu | **solução pronta na branch `pronto/instalacao-nova` — aguarda seu OK para implantar** | No seu Deck, nada (você já tem os dois emuladores e a detecção dá preferência a eles). No Deck do seu irmão, PS1 e Switch passam a abrir. Implantar = merge (só vale na próxima instalação/`setup-deck.sh`) |

Branches de outras sessões que continuam esperando seu OK (não mexi): `pronto/nunca-desistir`, `pronto/entradas-ajuste`.

**Depende de você:**
1. Criar o repositório no GitHub. Depois eu troco o `SEU-USUARIO` no `install.sh` e no README e faço o push.
2. Reinstalar a tarefa do túnel da IA no PC (comando no `docs/REVISAO-2026-11-10.md`, item d.1).
3. Jogar 10 minutos o BotW e o FF quando as traduções terminarem.
4. Benchmark real: rodar `python3 -m dc x bench <jogo> 60` num momento sem tradução, ou me pedir para rodar.

**Observação:** outra sessão afrouxou a checagem do magnet (`valid_magnet` agora aceita qualquer `btih:` e deixa o qBittorrent recusar o resto). Um magnet cortado (`btih:123`) agora responde "Adicionado" em vez de "magnet incompleto". Na simulação o qBittorrent era falso, então não deu para ver a resposta final que o qBittorrent real daria. Vale conferir com um magnet cortado de propósito.

**Melhorias para depois (não são falhas):** reconhecer o console de `.iso`/`.rvz`/`.chd` pelo conteúdo (cabeçalho do disco), para o bot perguntar menos.
