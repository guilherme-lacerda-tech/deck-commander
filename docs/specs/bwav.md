Arquivo: dc/traducao/bwav.py — ler e gravar arquivos de voz .bwav (Zelda Tears of the Kingdom e outros da
Nintendo) com áudio em "Opus da Nintendo" (codec 2), MONO. Python 3.11, só biblioteca padrão, type hints,
docstrings curtas em português. Tudo little-endian, exceto onde dito "BE" (big-endian).

Estrutura (lida de um arquivo real do jogo):
 0x00 "BWAV" | 0x04 u16 0xFEFF | 0x06 u16 versão (1) | 0x08 u32 CRC32 | 0x0C u16 prefetch (0) | 0x0E u16 canais (1)
 0x10 informação do canal (0x4C bytes):
   +0x00 u16 codec (2 = Opus) | +0x02 u16 pan (2) | +0x04 u32 taxa (48000) | +0x08 u32 amostras |
   +0x0C u32 amostras (de novo) | +0x10 32 bytes de zeros (coeficientes DSP, não usados no Opus) |
   +0x30 u32 deslocamento dos dados (0x80) | +0x34 u32 o mesmo (0x80) | +0x38 u32 1 | +0x3C u32 0xFFFFFFFF |
   +0x40 u32 0 | +0x44..+0x4B zeros
 0x5C..0x7F zeros (preenchimento até 0x80)
 0x80 bloco "info": u32 0x80000001 | u32 tamanho 0x18 | u8 versão 0 | u8 canais 1 | u16 tamanho do quadro 0 |
      u32 taxa 48000 | u32 deslocamento dos dados relativo a 0x80 (0x20) | u32 0 | u32 0 | u32 pré-salto (pre-skip)
 0xA0 bloco "dados": u32 0x80000004 | u32 tamanho dos pacotes (bytes que seguem) | pacotes...
 Cada pacote: u32 BE tamanho do pacote Opus | u32 BE "final range" (pode ser 0) | os bytes do pacote Opus.

@dataclass
class Bwav: taxa: int; amostras: int; preskip: int; pacotes: list[bytes]

1) def ler(d: bytes) -> Bwav
   Confere "BWAV", canais == 1 e codec == 2 (senão ValueError). Lê taxa e amostras do canal, o deslocamento dos
   dados (canal +0x30), o pré-salto (bloco info +0x1C) e os pacotes do bloco 0x80000004 até o fim do tamanho dele.

2) def gravar(b: Bwav) -> bytes
   Monta o arquivo na estrutura acima (mesmos valores fixos: pan 2, +0x38 = 1, +0x3C = 0xFFFFFFFF, final range 0).
   CRC32 em 0x08 = zlib.crc32 dos bytes do bloco de dados inteiro (de 0xA0 até o fim). ler(gravar(b)) == b.

3) def pacotes_do_ogg(ogg: bytes) -> tuple[list[bytes], int]
   Lê um arquivo Ogg Opus (gerado pelo ffmpeg -c:a libopus) e devolve (pacotes de áudio, pre_skip). Formato Ogg:
   páginas que começam com "OggS"; byte 26 = número de segmentos N; bytes 27..27+N = tabela de tamanhos (lacing);
   os dados vêm depois. Um pacote termina num segmento < 255 (segmentos de 255 continuam no próximo, inclusive
   atravessando páginas). O 1º pacote é "OpusHead" (pre_skip = u16 LE no byte 10 dele) e o 2º "OpusTags": não
   entram na lista.

4) def de_ogg(ogg: bytes, amostras: int) -> Bwav : Bwav(48000, amostras, pre_skip, pacotes).

Exemplo de teste (precisa passar): um Bwav com 3 pacotes b"\x01\x02", b"\x03", b"\x04\x05\x06" e amostras 2880,
preskip 120 sobrevive a gravar/ler; o arquivo gravado começa com b"BWAV\xff\xfe\x01\x00", tem codec 2 em 0x10 e
o bloco 0x80000001 em 0x80; um Ogg montado à mão com OpusHead (pre_skip 312), OpusTags e 2 pacotes de áudio
(um deles com 300 bytes, que usa lacing 255+45) devolve exatamente esses 2 pacotes e 312.
