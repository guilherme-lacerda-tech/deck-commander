# Qualidade (nativo, 2x, 3x…) e controles

## Resolução: como funciona

Cada emulador desenha o jogo numa resolução interna. **Nativo (1x)** é a resolução do console original.
**2x, 3x…** multiplicam essa resolução: a imagem fica mais nítida, mas a GPU trabalha mais.

| Console | Nativo | Tela do Deck (1280×800) | Padrão do Deck Commander |
|---|---|---|---|
| PS1 (DuckStation) | 320×240 | ~3x já preenche | o valor do emulador (perfis: `dc x profile ps1 …`) |
| PS2 (PCSX2) | ~640×448 | 2x preenche | o valor do emulador (perfis: `dc x profile ps2 …`) |
| GameCube/Wii (Dolphin) | 640×528 | 2x preenche | 2x |
| PSP (PPSSPP) | 480×272 | 3x preenche | 2x |
| Switch (Ryujinx) | 720p portátil / 1080p na TV | 1x | 1x |
| SNES, GBA, N64 (RetroArch) | — | — | sempre nativo (2D; não precisa) |

Acima do que a tela mostra (ex.: PS2 em 3x numa tela de 800p), o ganho é só um antisserrilhado, e o custo
é desempenho.

### Três camadas
1. **Global por emulador** (padrão do console), valendo para todos os jogos daquele console.
2. **Correções automáticas do próprio emulador.** PCSX2 e DuckStation têm um banco interno com
   correções por jogo (por exemplo, desligar um efeito que quebra fora do nativo). Isso já funciona sozinho
   e é a maior parte do "tratamento por jogo" que um jogo exige.
3. **Exceção por jogo** (Deck Commander): `/qualidade <jogo> nativo|2x|3x|padrão`.
   - Vale **só** para aquele jogo. O valor é trocado quando o jogo abre e devolvido quando ele fecha,
     inclusive pelo botão "Sair do jogo" do Steam.
   - Se você mudar a resolução pelo menu do emulador durante o jogo, a sua mudança é respeitada.
   - `/qualidade lista` mostra os jogos com exceção.

### Quando usar a exceção
- **Jogo travando ou lento** (ex.: Shadow of the Colossus no PCSX2 em 3x): `/qualidade shadow 2x`.
- **Gráfico com linhas, bordas ou sombras erradas** em 2x ou mais (alguns jogos 2D/sprites de PS1/PS2):
  `/qualidade <jogo> nativo`.
- Não existe tabela automática "este jogo = 2x". Ela teria de ser medida jogo a jogo no Deck (benchmark,
  item pendente do M10). O padrão é o global, e você ajusta o que incomodar.

## Controles: como funciona

No modo jogo, o **Steam Input** entrega aos emuladores um controle padrão (layout Xbox: A embaixo, B à
direita). Cada emulador é mapeado **uma vez**, e o mapeamento vale para todos os jogos dele:

| Emulador | Como mapeia | Situação |
|---|---|---|
| DuckStation / PCSX2 | automático (SDL) | ✅ funciona de fábrica |
| RetroArch / PPSSPP | autoconfiguração | ✅ funciona de fábrica |
| Ryujinx (Switch) | por **rótulo**: apertar A no Deck = A no jogo | ✅ aplicado pelo instalador |
| Dolphin (GC/Wii) | precisa escolher o controle 1 vez | ⚠️ `/controles` avisa se faltar |

**Botões do Switch:** o Nintendo Switch tem A à direita e B embaixo (o contrário do Deck). O padrão do
Ryujinx é por *posição* (o "A" do Switch fica no botão da direita do Deck, que se chama B). Por isso
você precisou apertar B para avançar no Galaxy. Agora é por *rótulo* (A=A). Para voltar ao padrão:
`python3 -m dc x controles positional`.

**Ajuste por jogo:** quase nenhum jogo precisa. Quando precisar (ex.: inverter a câmera), use o próprio
Steam: botão do controle → **Configurações do controle** naquele jogo. O Steam guarda o layout por atalho
e não mexe nos outros jogos.
