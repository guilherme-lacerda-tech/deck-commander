# Tradução com IA e conversão de Switch (adições A1, A2, A3)

## Resumo
| Adição | Comando | Como funciona | Estado |
|---|---|---|---|
| A2 — tradução de Switch | `/traduzir <jogo>` | Os textos do jogo (MSBT) são traduzidos e instalados como **mod** do Ryujinx. O jogo nunca é alterado. | ✅ validado com arquivos reais de um jogo da Nintendo (552 MSBT, 12.742 frases, tags idênticas) e com IA real |
| A1 — tradução retrô | `/traduzir <jogo>` (ou automático ao baixar) | PS1, PS2, PSP, GBA, SNES, NES, N64, GameCube, DS pelo **RomTranslate Studio**; Pokémon de GBA pelo **Meowth**. Sai "<jogo> (PT-BR)" + patch `.bps`, e o original some da biblioteca | ✅ FireRed traduzido de ponta a ponta (2.332 frases, 0 problemas) |
| A3 — conversão de Switch | `/converter <jogo> [organizar\|descompactar]` | Confere, organiza atualização e DLC numa pasta por jogo e descompacta NSZ/XCZ | ✅ diagnóstico validado na biblioteca real; descompactar depende do `nsz` |

## Automático: baixou, chega traduzido
Quando um download entra na biblioteca e o jogo **não** está em português, o bot já coloca a tradução na fila
e avisa ("traduzindo sozinho"). Quando termina, o jogo aparece na aba "Em português", sem duplicar.
Desligar: `auto_traduzir = false` em `~/.config/deck-commander/traducao.toml`.

Ordem de preferência:
1. **Já em português**: a versão baixada já traduzida ou dublada, ou o português oficial do Switch. Nada a fazer.
2. **Tradução da comunidade**: quando existe um patch publicado e conferível (hoje: o acervo aberto `romhack_db`
   para SNES/NES/GB). O romhacking.net bloqueia acesso automático, e o acervo dele no Internet Archive exige login.
3. **IA**, na cadeia abaixo.

## IA: Index-Translate → seu PC → o Deck
| Provedor | Quando |
|---|---|
| Index-Translate-9B (grátis, na internet) | primeiro: rápido (~60 frases por minuto) |
| **Seu PC** (Ollama + placa de vídeo, `qwen2.5:7b`) | se o Index falhar; o PC empresta a IA pela rede por um túnel SSH (nada é aberto no firewall) |
| Ollama no Deck (`translategemma:4b`) | sem internet e sem PC; lento |

Erro passageiro (o servidor recusa resposta longa, limite de uso) não derruba o provedor rápido: a tradução tenta de novo
com lotes menores e volta ao principal. Se a tradução passar do espaço do jogo, a IA recebe o limite e é pedida uma
versão mais curta.
**Ligar a IA do PC** (uma vez, no PC, em PowerShell):
```
powershell -ExecutionPolicy Bypass -File C:\dev\deck-commander\tools\pc\instalar-tunel-ia.ps1
```

## Aba "Em português" (jogar sem se perder)
A biblioteca **não é duplicada**:
- **Switch:** tradução vira mod, e o jogo continua um só.
- **Retrô:** a ROM "(PT-BR)" substitui o atalho do original. O arquivo original fica guardado, e `/devolver` traz de volta.

A aba **"Em português"** mostra só o que dá para jogar em português:
| Tipo | Como é detectado |
|---|---|
| Switch com **PT-BR oficial** | lido do arquivo de controle do jogo, já com a atualização. O jogo abre com o Ryujinx em português **só para ele** |
| Switch com a nossa tradução | mod "Deck Commander PT-BR" instalado |
| ROM traduzida/dublada | nome com (BR), PT-BR, Dublado, DUB, Dub-e-Leg, VERSÃO I.A, romsportugues… |

`/traduzir lista` mostra o que está em português, o que dá para traduzir e o que não dá.

### Resultado na biblioteca de teste (2026-11-09)
| Jogo | Situação |
|---|---|
| Super Mario Galaxy, Galaxy 2, Castlevania Belmont's Curse | ✅ PT-BR oficial: abrem em português |
| 13 de PS2 + Final Fantasy Tactics (PS1) | ✅ já traduzidos/dublados (pelo nome) |
| FireRed (Switch) | ✅ a ROM de GBA de dentro foi traduzida (2.332 frases) e entrou como mod. O Meowth aumenta a ROM para 32 MB: confira se abre; se não, `/traduzir desfazer firered` |
| LeafGreen e versões espanholas | ⏳ na fila (mesmo caminho do FireRed) |
| Luigi's Mansion 3 | 🟡 traduzido e instalado como mod (1.314 de 1.612 frases; o resto ficou em inglês). Arquivo conferido byte a byte; **falta conferir no jogo** (ver "Luigi's Mansion 3" abaixo) |
| Pokémon Legends Z-A | 🟡 traduzível: textos lidos do `data.trpfs` (Oodle descomprimido em Python), 427 arquivos / 76.810 frases relidos byte a byte; fonte tem todos os acentos. Testado no Deck: com o mod o jogo abre e lê os textos soltos (ver abaixo) |
| Hercules (PS1) | RomTranslate: o jogo quase não tem texto comum (nomes de fase e mensagens do sistema; as falas são voz/imagem) |
| Shadow of the Colossus (inglês) | você já tem a versão dublada |
| Donkey Kong Bananza, Pokopia | ❌ Switch 2 (Lichii): ainda sem suporte |

## Como traduzir um jogo de Switch
1. Nada a preparar: o Deck Commander abre o jogo, já com a atualização, usando as chaves que o seu Ryujinx
   já tem, e copia **só os arquivos de texto**. Não altera nada no jogo.
   - Se o jogo tiver português oficial, ele só liga o idioma e não usa IA.
   - Se não conseguir abrir o jogo, extraia pelo Ryujinx (modo desktop: botão direito no jogo → Extrair dados →
     RomFS → `~/Emulation/romfs/<TitleID>`).
2. No Telegram: `/traduzir <nome do jogo>`. O bot responde na hora e avisa quando terminar.
3. Abra o jogo normalmente. A tradução aparece como mod "Deck Commander PT-BR" do Ryujinx.
   Para voltar ao inglês: `/traduzir desfazer <jogo>`.

O idioma traduzido é o **inglês** do jogo, porque o Ryujinx do Deck está em inglês. Os outros idiomas não são tocados.

## Luigi's Mansion 3
Os textos não são MSBT: ficam no `init.patch` da atualização 1.4 (formato da Next Level Games, lido em Python puro).
- Dentro dele há um bloco zlib com 13 tabelas de texto, uma por idioma. São traduzidos o **inglês dos EUA** (o que
  o Ryujinx em inglês mostra) e o inglês europeu. Os outros 11 idiomas ficam iguais.
- O mod é um único arquivo: `mods/contents/0100dca0064a6000/Deck Commander PT-BR/romfs/init.patch`.
- **Precisa da atualização** (1.4, `[v327680]`). Sem ela o bot avisa e não faz nada.
- Antes de traduzir, o `init.patch` é lido e regravado sem mudar um byte (as 13 tabelas e o arquivo).
- O jogo guarda o tamanho de cada tabela em vários lugares, então a tabela traduzida tem **exatamente o tamanho
  da original** (o que sobra vira zeros). A IA recebe um limite por frase; frase que passar fica em inglês.
- `[p]` (quebra de linha) é refeito na largura do original; quebra depois de ponto final fica onde estava.
- Fonte: á é í ó ú â ô à ç aparecem nos textos oficiais (espanhol/francês). **ã e õ não aparecem em nenhum texto
  oficial**: a fonte tem a posição dessas letras (a tradução russa as usa), mas ainda não foi visto na tela.
- Resultado (2026-11-09, Index-Translate): 1.314 de 1.612 frases traduzidas; 81 ficaram em inglês (passaram do
  espaço ou a IA estragou um código); 30 frases ficaram com uma linha a mais que o original.
- Fora da fila do bot: `python3 tools/lm3_traduzir.py [--sem-instalar]` (mesmo código e mesmo cache do `/traduzir`).

## Segurança (o que nunca acontece)
- O arquivo do jogo (NSP/XCI) e a ROM original **nunca** são alterados.
- Cada arquivo de texto precisa ser lido e regravado **sem mudar um byte** antes de ser traduzido. O que não passar é pulado e aparece no relatório.
- Códigos do jogo (cores, pausas, nome do jogador, ícones) viram marcadores `⟦0⟧`. Se a IA perder ou inventar um marcador, a frase fica no original e entra no relatório.
- Se a **fonte do jogo não tiver acentos** (ã, ç…), a tradução é bloqueada. `--forcar` aplica mesmo assim.
- Se mais de 10% das frases derem problema, o mod fica guardado sem aplicar. Veja com `/traduzir revisar <op>` e aplique com `/traduzir aplicar <op>`.
- Na bateria a tradução espera a tomada. Com a IA no próprio Deck, ela pausa enquanto um jogo estiver aberto.
- Se o Deck reiniciar no meio, `/traduzir retomar <op>` continua de onde parou: o que já foi traduzido não é refeito nem gasta de novo.

## IA: qual é usada (`~/.config/deck-commander/traducao.toml`)
| Provedor | Custo | Observação |
|---|---|---|
| **Index-Translate-9B** (padrão) | grátis | Rápido (um jogo inteiro em ~1 h). O texto do jogo vai para o servidor da Bilibili. Pode limitar uso (erro 429); aí passa para o próximo. |
| Ollama no Deck (`translategemma:4b`) | grátis | Privado e funciona sem internet, mas lento: pode levar horas. Instale com `./setup-deck.sh --modules A1`. |
| Ollama no seu PC | grátis | Bem mais rápido que no Deck. Configure `[providers.ollama_pc] url = "http://IP-DO-PC:11434"`. |
| GitHub Models | grátis (limite diário) | Precisa de um token: `~/.config/deck-commander/secrets/github_pat`. |
| OpenAI / Anthropic / Gemini | pago | Chave em `secrets/ia_api.key`. O bot mostra a **estimativa de tokens** e só começa depois de `/traduzir aprovar <op>`. Respeita `limite_diario_tokens`. |

`/traduzir config` mostra a cadeia ativa (com a chave mascarada) e o uso do dia.

## Glossário e referências (as suas traduções)
- **`~/.config/deck-commander/glossario.toml`** guarda termos fixos. `"="` mantém o termo como está (nomes próprios).
  ```toml
  [geral]
  "HP" = "="
  [Pokemon]
  "Potion" = "Poção"
  "Pikachu" = "="
  ```
- **`~/.config/deck-commander/referencias.toml`** aponta para as traduções que você já tem.
  ```toml
  [[ref]]
  titulo = "Luigi's Mansion 3 (BR)"
  console = "switch"            # ou "gba"
  title_id = "0100DCA0064A6000"
  original = "~/Emulation/romfs/0100DCA0064A6000"        # RomFS (Switch) ou ROM (GBA) original
  traduzido = "~/Traducoes/LM3-BR/romfs"                  # a versão traduzida
  idioma_origem = "en"
  idioma_destino = "pt-BR"
  equipe = "nome da equipe"
  versao = "1.0"
  ```
  O que a referência faz:
  - **Mesmo jogo:** as frases que já existem na sua tradução são usadas **direto**, sem passar pela IA, e o relatório mostra o quanto a IA ficou parecida com ela.
  - **Outros jogos:** os pares viram exemplos (few-shot) para a IA manter o estilo.

## Retrô (GBA)
- Hoje só funciona com **Pokémon de GBA** (Gen 3 e hacks), via [Meowth](https://github.com/Olcmyk/Meowth-GBA-Translator) (MIT).
  O "RomTranslate Studio" do plano original não existe. Para outros consoles não há extrator de texto confiável, e o bot avisa em vez de tentar.
- O GBA não tem as letras ã e õ: elas viram a e o, e o relatório conta quantas foram trocadas.
- Resultado: `<jogo> (PT-BR).gba` entra na biblioteca como jogo separado, com um `.bps` ao lado. A ROM original fica como está.

## Conversão de Switch (`/converter`)
- **Sem ação**, só diagnostica: base, atualizações, DLC, arquivos comprimidos, pastas espalhadas, arquivo maior que 4 GB num cartão FAT32.
- `organizar` só move arquivos para `switch/<Jogo> [TitleID]/`. Não move entre discos e não sobrescreve nada.
- `descompactar` usa a ferramenta `nsz` (`./setup-deck.sh --modules A3`) com as chaves do seu Ryujinx. O original comprimido vai para a quarentena (30 dias), no mesmo disco.
- Não faz, de propósito:
  - **fundir base+update+DLC**: o Ryujinx já carrega separado;
  - **converter NSP↔XCI**: o Ryujinx abre os dois;
  - **dividir em partes de 4 GB**: o cartão do Deck não é FAT32 por padrão.

## Instalação
```
./setup-deck.sh --modules A1,A2,A3
```
Instala o Ollama dentro da sua pasta pessoal (o SteamOS é somente leitura), baixa o modelo `translategemma:4b` (~3 GB), e instala o Meowth e o `nsz` em ambientes isolados.
A tradução de Switch com o Index-Translate funciona **sem instalar nada**.

## Pokémon Legends Z-A (engine Trinity)
Os textos não são MSBT: ficam dentro de `arc/data.trpfs`, em pacotes FlatBuffers comprimidos com Oodle.
- **Leitura:** só os pacotes de mensagem em inglês (~5 MB) e as fontes saem do jogo, com cache em
  `~/.local/share/deck-commander/traducao/trinity/<TitleID>/` (refeito se a atualização mudar). O Oodle (Mermaid)
  é descomprimido por um porte em Python do `ooz` (código aberto), sem programa extra.
- **Formato das falas:** `.dat` cifrado (formato TextFile do pkNX). Códigos do jogo (nome do jogador, pausas, troca
  de caixa, ícones) viram `⟦n⟧`. Depois da IA, as quebras de linha são refeitas na largura original, com no
  máximo 2 linhas por caixa (abre caixa nova como o jogo faz).
- **Mod:** os `.dat` traduzidos ficam soltos em `romfs/ik_message/dat/English/...`, mais um `romfs/arc/data.trpfd`
  sem esses arquivos na lista. Assim o jogo lê os soltos (mesma técnica do Trinity Mod Loader).
- **Versão:** o mod é feito da versão que o Ryujinx **carrega** (`games/<tid>/updates.json`; sem ele, a versão base).
  Um `data.trpfd` de outra versão aponta para pacotes errados e o jogo trava ao abrir (aconteceu no 1º piloto).
  Se você ligar/trocar a atualização no Ryujinx, rode `/traduzir <jogo> --forcar` de novo. Até lá o `dc-launch`
  desliga sozinho o mod de outra versão (vai para `traducao/mods-desligados`) e o jogo abre em inglês, sem travar.
- Testes de abertura no Deck: só com **um** Ryujinx aberto por vez (dois juntos fizeram o Z-A travar no teste).
- **Testado no Deck (Ryujinx 1.3.3, versão base):** com o mod, o jogo abre e roda; o log de acesso a arquivos mostra o
  jogo lendo os `.dat` soltos do RomFS (27 abertos só até a tela inicial). Se o jogo não abrir: `/traduzir desfazer z-a`.
- Tradução completa: ~63 mil frases (versão base). Com o Index-Translate, ~125 frases/min: cerca de 7 h (retoma de onde parou).
- Conferência com os arquivos reais: `python3 tools/trinity_check.py <jogo.nsp> [--piloto N --arquivo script/x.dat --saida DIR]`.

## Ferramentas de diagnóstico (no Deck)
- `python3 tools/switch_text_check.py <romfs>`: só lê. Mostra quantos textos e frases existem e se tudo é reproduzido byte a byte.
- `python3 tools/switch_e2e_real.py <romfs> <pacote> <msbt>`: traduz um único arquivo real e grava o mod numa pasta temporária.
