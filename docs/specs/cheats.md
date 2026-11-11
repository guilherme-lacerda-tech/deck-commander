Arquivo: dc/cheats.py — cheats (Game Genie/Action Replay/GameShark) do RetroArch por jogo, ligados por chave no
painel. Python 3.11, só biblioteca padrão, type hints, docstrings curtas em português. Funções puras onde possível.

Formato .cht do RetroArch (base oficial libretro-database, pasta por console: "Nintendo - Super Nintendo
Entertainment System/Nome do Jogo (USA).cht"):
    cheats = 3

    cheat0_desc = "Infinite Lives"
    cheat0_code = "7E0DBE:09"
    cheat0_enable = false

    cheat1_desc = "Infinite Energy"
    cheat1_code = "C2A7-4FA4+C2A7-4F04"
    cheat1_enable = false
    ...
Podem existir outras chaves por cheat (cheat0_handler, cheat0_address, ...): preservar todas.

1) def ler_cht(texto: str) -> list[dict]
   Devolve lista na ordem do índice: {"i": int, "desc": str, "code": str, "enable": bool, "extra": dict[str, str]}
   (extra = outras chaves do cheat SEM o prefixo "cheatN_", com o valor como texto cru, sem aspas externas).
   Valores podem vir com ou sem aspas. Ignora linhas vazias/comentários (#). Se "cheats = N" faltar, usa os
   índices encontrados.

2) def escrever_cht(cheats: list[dict]) -> str
   Gera o texto no mesmo formato: "cheats = N\n\n" e, para cada cheat (reindexado 0..N-1 na ordem da lista):
   cheatK_desc = "<desc>", cheatK_code = "<code>", cheatK_enable = true|false, depois as extras como
   cheatK_<chave> = <valor cru>. Linha em branco entre cheats. ler_cht(escrever_cht(x)) deve devolver o mesmo
   conteúdo (desc/code/enable/extra).

3) def normalizar(nome: str) -> str
   Para casar nome de jogo com nome de arquivo: minúsculas, remove extensão, remove tudo entre () e [],
   troca "&" por "and", remove acentos (unicodedata), mantém só [a-z0-9 ], espaços múltiplos viram um, strip.
   Ex.: normalizar("Super Mario World (USA) [!].sfc") == "super mario world"

4) def achar_cht(arquivos: list[str], jogo: str) -> str | None
   `arquivos` = nomes de .cht de UM console. Devolve o que casa com normalizar(jogo): 1º igualdade exata;
   2º o arquivo cujo nome normalizado COMEÇA com o nome do jogo normalizado, preferindo os que têm "(USA)" e
   depois "(Europe)" no nome original e, empatando, o nome mais curto. None se nada casar.

5) TRADUCOES: dict[str, str] com ~40 termos comuns em inglês → português para mostrar no painel
   (ex. "Infinite Lives" → "Vidas infinitas", "Infinite Health"/"Infinite Energy"/"Infinite HP" → "Vida infinita",
   "Infinite Ammo" → "Munição infinita", "Max Money"/"Infinite Money" → "Dinheiro máximo"/"Dinheiro infinito",
   "Invincibility" → "Invencível", "Have All Items" → "Todos os itens", "Moon Jump" → "Pulo lunar",
   "Infinite Time" → "Tempo infinito", "Level Select" → "Escolher fase", "Infinite Continues" → "Continues infinitos",
   "Infinite Magic"/"Infinite MP" → "Magia infinita", "Max Stats" → "Atributos no máximo",
   "Walk Through Walls" → "Atravessar paredes", "Infinite Items" → "Itens infinitos", "Max Level" → "Nível máximo",
   "Infinite Bombs" → "Bombas infinitas", "Start With" → "Começar com", "Player 1" → "Jogador 1",
   "Player 2" → "Jogador 2", "Always" → "Sempre", "Instant Win" → "Vitória instantânea", "Max Exp" → "Experiência máxima" ...)
   def traduzir_desc(desc: str) -> str : troca cada termo conhecido (sem diferenciar maiúsculas, termos mais longos
   primeiro) e devolve o resto como está.

6) def com_ativos(cheats: list[dict], ativos: set[int]) -> list[dict]
   Cópia com enable=True só nos índices `i` em `ativos` (os outros False).

Exemplo de teste (precisa passar):
   t = 'cheats = 2\n\ncheat0_desc = "Infinite Lives"\ncheat0_code = "7E0DBE:09"\ncheat0_enable = false\ncheat0_handler = 1\n\ncheat1_desc = "Max Money"\ncheat1_code = "AAAA-BBBB"\ncheat1_enable = false\n'
   c = ler_cht(t)
   assert c[0]["desc"] == "Infinite Lives" and c[0]["extra"] == {"handler": "1"} and c[1]["enable"] is False
   assert ler_cht(escrever_cht(com_ativos(c, {1})))[1]["enable"] is True
   assert achar_cht(["Super Mario World (Europe).cht", "Super Mario World (USA).cht", "Super Mario World 2 (USA).cht"], "Super Mario World (USA).sfc") == "Super Mario World (USA).cht"
   assert traduzir_desc("Infinite Lives P1") == "Vidas infinitas P1"
