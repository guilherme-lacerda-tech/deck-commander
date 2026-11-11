Arquivo: dc/traducao/psx_disco.py — ler e regravar arquivos dentro de uma imagem de CD de PlayStation 1 (.bin
MODE2/2352, ISO9660). Python 3.11, só biblioteca padrão, type hints, docstrings curtas em português.

Formato do .bin (MODE2/2352): cada setor tem 2352 bytes; os dados do usuário de um setor "Form 1" são os 2048 bytes
a partir do deslocamento 24 dentro do setor (12 de sincronia + 4 de cabeçalho + 8 de subcabeçalho). O setor N começa
no byte N*2352 do arquivo.

ISO9660: o descritor de volume primário fica no setor 16; o registro do diretório raiz está nos bytes 156..189 desse
setor (34 bytes). Registro de diretório: byte 0 = tamanho do registro; bytes 2..5 = setor inicial (little-endian
uint32); bytes 10..13 = tamanho em bytes (LE uint32); byte 25 = flags (bit 1 = diretório); byte 32 = tamanho do nome;
bytes 33.. = nome (ASCII, com ";1" no fim nos arquivos). Nomes "\x00" e "\x01" são "." e "..". Um registro com
tamanho 0 significa "pula para o próximo setor de 2048 do diretório".

class Disco:
    __init__(self, caminho: Path)
    arquivos(self) -> dict[str, tuple[int, int]]
        nome completo com "/" e SEM ";1" (ex. "ST/ST0/ST0.BIN") -> (setor inicial, tamanho em bytes). Percorre
        subdiretórios recursivamente.
    ler(self, nome: str) -> bytes
        os bytes do arquivo (lendo setor a setor os 2048 bytes de dados; corta no tamanho exato).
    gravar_copia(self, destino: Path, novos: dict[str, bytes]) -> None
        Copia o .bin inteiro para `destino` (shutil.copyfile) e, na CÓPIA, regrava cada arquivo de `novos` nos
        mesmos setores (só os 2048 bytes de dados de cada setor; o resto do setor fica igual). Os novos bytes
        precisam ter EXATAMENTE o tamanho original — senão ValueError antes de copiar qualquer coisa.
        O original nunca é aberto para escrita.

def gravar_cue(cue_original: Path, cue_novo: Path, bin_novo_nome: str) -> None
    Lê o .cue original e grava um novo trocando o nome do arquivo na linha FILE "…" BINARY pelo novo nome
    (mantém o resto igual).

Exemplo de teste (precisa passar): montar em memória um .bin falso com setor 16 contendo um descritor com raiz no
setor 18, um diretório com um arquivo "A.BIN;1" de 3000 bytes no setor 20 (ocupa 2 setores), conferir
Disco(p).arquivos() == {"A.BIN": (20, 3000)}, ler() devolve os 3000 bytes, gravar_copia() com bytes novos de 3000
regrava os dois setores na cópia sem mudar os 24 primeiros bytes de cada setor, e com tamanho errado levanta
ValueError.
