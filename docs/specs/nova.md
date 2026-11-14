# Nova the Squirrel (NES) — não traduzir

**Não traduzir.** Pedido do autor no README oficial do jogo: não envolver o jogo em projetos feitos com IA.
Respeitamos o pedido: o jogo fica sem tradução por IA (marcado para não traduzir no Deck Commander).

O filtro do RomTranslate (`dc/traducao/rts.py`) foi corrigido por causa dos defeitos achados na tentativa
de 14/11/2026 (a cópia travava em tela branca depois do Start):

1. Tradução mais curta que a original era completada com bytes zero. Em menus guardados em sequência,
   esses zeros a mais viram opções vazias e o jogo se perde. Agora completamos com espaços até o tamanho
   exato da original (`ajustar`).
2. O limite de tamanho às vezes vinha vazio (sem limite) ou maior que a frase. Agora nunca passa do
   tamanho da frase original, então o zero que fecha a frase nunca é apagado (`espaco_original`).
3. Pedaços de frase (começo comprimido, linha de continuação ou palavra cortada) eram traduzidos
   sozinhos. Agora são recusados e ficam no original (`fragmento`).

Testes: `tests/test_rts_gravacao_segura.py` (só dados sintéticos).
