# Tradução com IA e conversão de Switch (adições A1, A2, A3)

## Resumo
| Adição | Comando | Como funciona | Estado |
|---|---|---|---|
| A2 — tradução de Switch | `/traduzir <jogo>` | Os textos do jogo (MSBT) são traduzidos e instalados como **mod** do Ryujinx. O jogo nunca é alterado. | ✅ validado com arquivos reais de um jogo da Nintendo (552 MSBT, 12.742 frases, tags idênticas) e com IA real |
| A1 — tradução retrô | `/traduzir <jogo>` | Pokémon de GBA: o Meowth extrai e regrava o texto, a nossa IA traduz e sai uma ROM nova "(PT-BR)" + patch `.bps` | ⏳ código e testes prontos; falta testar com uma ROM real (S12) |
| A3 — conversão de Switch | `/converter <jogo> [organizar\|descompactar]` | Confere, organiza atualização e DLC numa pasta por jogo e descompacta NSZ/XCZ | ✅ diagnóstico validado na biblioteca real; descompactar depende do `nsz` |

## Como traduzir um jogo de Switch
1. **Uma vez por jogo**, no modo desktop: Ryujinx → botão direito no jogo → **Extrair dados → RomFS** →
   escolha a pasta `~/Emulation/romfs/<TitleID>` (o TitleID é o código `0100…` do nome do arquivo).
   Se você instalar o `hactool`, essa etapa é automática.
2. No Telegram: `/traduzir <nome do jogo>`. O bot responde na hora e avisa quando terminar.
3. Abra o jogo normalmente. A tradução aparece como mod "Deck Commander PT-BR" do Ryujinx.
   Para voltar ao inglês: `/traduzir desfazer <jogo>`.

O idioma traduzido é o **inglês** do jogo, porque o Ryujinx do Deck está em inglês. Os outros idiomas não são tocados.

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

## Ferramentas de diagnóstico (no Deck)
- `python3 tools/switch_text_check.py <romfs>`: só lê. Mostra quantos textos e frases existem e se tudo é reproduzido byte a byte.
- `python3 tools/switch_e2e_real.py <romfs> <pacote> <msbt>`: traduz um único arquivo real e grava o mod numa pasta temporária.
