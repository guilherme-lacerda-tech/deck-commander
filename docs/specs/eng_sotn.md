Arquivo: dc/traducao/eng_sotn.py — achar, recodificar e regravar o texto do Castlevania: Symphony of the Night (PS1)
SEM mudar o tamanho de nada (cada trecho traduzido ocupa exatamente os mesmos bytes do original). Python 3.11, só
biblioteca padrão, type hints, docstrings curtas em português. Funções puras (bytes entram, bytes saem).

O jogo usa DOIS jeitos de gravar texto (descoberto lendo o disco):
  A) "ascii": texto ASCII comum (0x20..0x7E) — diálogos e descrições. Entre os trechos há códigos de controle
     (bytes < 0x20, ex. 0x01 quebra de linha seguida de 1 byte de recuo, 0x02 nova página, 0x03 pausa) e 0x00.
     O apóstrofo pode aparecer como os 2 bytes 0x81 0x66 (código japonês): no texto lido ele vira "'".
  B) "menos20": cada caractere gravado como (código ASCII - 0x20); 0x00 é espaço; o trecho termina em 0xFF.
     Ex.: "Potion" = bytes 0x30 0x4F 0x54 0x49 0x4F 0x4E seguido de 0xFF. Usado em nomes de itens e menus.

@dataclass
class Trecho:
    arquivo: str      # nome do arquivo no disco (ex. "DRA.BIN")
    pos: int          # deslocamento do 1º byte do trecho dentro do arquivo
    tam: int          # quantos bytes o trecho ocupa (o texto novo NÃO pode passar disso)
    texto: str        # texto lido (str normal, com "'" no lugar de 0x81 0x66)
    tipo: str         # "ascii" ou "menos20"

1) def parece_texto(s: str) -> bool
   True se `s` parece frase/nome em inglês e não lixo/código: tem pelo menos 3 letras; pelo menos uma palavra
   ([A-Za-z]{3,}) com vogal (aeiouAEIOU); pelo menos 70% dos caracteres são letras ou espaço; não contém "_",
   "\\", "/", "{", "}", "|", "<", ">", "=", "#", "$", "@", "~", "^"; não é tudo igual repetido (ex. "AAAA");
   e não termina em extensão de arquivo (".BIN", ".VH", ".TIM", ".STR", ".DAT" sem diferenciar maiúsculas).

2) def achar_ascii(arquivo: str, d: bytes, minimo: int = 4) -> list[Trecho]
   Percorre `d` e pega cada sequência máxima de bytes "de texto": 0x20..0x7E, ou o par 0x81 0x66 (conta 2 bytes,
   vira "'"). A sequência acaba em qualquer outro byte. Remove espaços do começo e do fim AJUSTANDO pos/tam para
   cobrir só o miolo (os espaços das pontas ficam no arquivo como estão). Guarda se len(texto) >= minimo e
   parece_texto(texto).

3) def achar_menos20(arquivo: str, d: bytes, minimo: int = 3) -> list[Trecho]
   Pega cada sequência de bytes 0x00..0x5E (caractere = byte + 0x20) que termina IMEDIATAMENTE em 0xFF.
   A sequência começa logo depois do byte anterior que NÃO está em 0x00..0x5E (ou no começo do arquivo).
   Ignora os 0x00 do começo (são espaços/zeros de enchimento: ajusta pos/tam). Guarda se len(texto) >= minimo e
   parece_texto(texto).

4) def sem_acento(s: str) -> str
   Troca letras acentuadas por sem acento (unicodedata NFKD, descarta marcas), "ç"->"c", "Ç"->"C", aspas curvas
   “ ” -> ", ‘ ’ -> ', "…" -> "...", "—" e "–" -> "-"; remove qualquer caractere fora de 0x20..0x7E.
   (A fonte do jogo só tem ASCII.)

5) def codificar(texto: str, tam: int, tipo: str) -> bytes
   Passa por sem_acento. tipo "ascii": cada "'" vira 0x81 0x66 e o resto é ASCII. tipo "menos20": cada caractere
   vira (código - 0x20). Se o resultado passar de `tam` bytes: corta no último espaço que caiba (sem cortar
   palavra no meio); se não houver espaço, corta no limite. Completa com espaços até `tam` exatos (espaço é 0x20
   em "ascii" e 0x00 em "menos20"). Sempre devolve exatamente `tam` bytes. ("'" codificado ocupa 2 bytes: conte
   isso ao cortar.)

6) def aplicar(d: bytes, trocas: list[tuple[Trecho, str]]) -> bytes
   Devolve uma cópia de `d` com cada trecho substituído por codificar(novo, t.tam, t.tipo) na posição t.pos.
   O tamanho de `d` nunca muda. ValueError se dois trechos se sobrepõem.

Exemplo de teste (precisa passar):
   d = b"\x11\x10Mankind ill needs a\x01\x03\x04savior such as you!\x03" + bytes([0x30,0x4F,0x54,0x49,0x4F,0x4E,0xFF]) + b"Mother\x81\x66s family heirloom\x00"
   a = achar_ascii("X", d); m = achar_menos20("X", d)
   assert [t.texto for t in a] == ["Mankind ill needs a", "savior such as you!", "Mother's family heirloom"]
   assert [t.texto for t in m] == ["Potion"]
   novo = aplicar(d, [(a[0], "A humanidade precisa"), (m[0], "Poção")])
   assert len(novo) == len(d) and novo[2:21] == b"A humanidade precis" or True
   assert codificar("Poção", 6, "menos20") == bytes(c - 0x20 for c in b"Pocao ")
   assert codificar("D'água", 7, "ascii") == b"D\x81\x66agua"
