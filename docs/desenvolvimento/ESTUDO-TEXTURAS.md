# Estudo: traduzir texto que está em IMAGEM (menus/texturas) — viabilidade

Alguns jogos (muitos de PS1/PS2) desenham menus, títulos e placas como imagens, não como texto. A tradução normal não
alcança essas partes. Este estudo diz o que dá para fazer e o que custaria.

## Como seria
1. **Achar as texturas com texto:** exportar as texturas do jogo enquanto ele roda — PCSX2 e DuckStation têm
   "Dump Textures"; o Dolphin também. Só aparecem as telas que você visitar (o dump é feito jogando).
2. **Ler o texto:** OCR com o modelo de visão do PC (qwen2.5vl:7b — já instalado e testado lendo legenda de jogo).
3. **Traduzir:** a mesma cadeia de IA + glossário de franquia (o texto de menu é curto).
4. **Redesenhar a imagem:** apagar o texto original (preencher com o fundo — "inpainting") e escrever o português com uma
   fonte parecida, no mesmo tamanho. Este é o passo difícil: precisa de um modelo de imagem (ex.: Stable Diffusion com
   inpainting, que roda na RTX 3050 de 6 GB, lento) ou de um preenchimento simples (bom para fundo liso).
5. **Recolocar no jogo sem mexer na ROM:** PCSX2, DuckStation e Dolphin aceitam **pacotes de texturas substitutas**
   (pasta `textures/<serial>/replacements`), carregados por cima — o jogo original fica intacto.

## Conclusão
| Parte | Situação |
|---|---|
| Ler o texto da imagem (OCR local) | ✅ viável — já funciona (usado no /corrigir) |
| Traduzir | ✅ viável — já existe |
| Substituir sem alterar a ROM | ✅ viável — os três emuladores suportam pacote de texturas |
| Exportar as texturas | ⚠️ manual: precisa jogar com o "dump" ligado (o sistema pode ligar/desligar para você) |
| Redesenhar com qualidade | ⚠️ o ponto fraco: fundo liso fica bom; arte/efeitos ficam visivelmente editados |

**Recomendação:** fazer uma v1 para PS2/PS1 só com **fundo liso** (menus e caixas de texto), ligando o dump por jogo no
painel e gerando o pacote de texturas sozinho depois que você jogar um pouco. Arte complexa fica de fora até haver um
modelo de imagem local com qualidade boa o suficiente.
