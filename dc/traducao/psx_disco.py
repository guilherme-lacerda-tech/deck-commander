import shutil
from pathlib import Path
from typing import BinaryIO


class Disco:
    def __init__(self, caminho: Path):
        self._caminho = caminho
        self._setor_size = 2352
        self._dados_size = 2048
        self._offset_dados = 24
        
    def _bloco(self, f: BinaryIO, setor: int, tamanho: int) -> bytes:
        """Dados (2048 por setor, a partir do byte 24) de `tamanho` bytes começando em `setor`."""
        out = bytearray()
        n = 0
        while len(out) < tamanho:
            f.seek((setor + n) * self._setor_size + self._offset_dados)
            out += f.read(self._dados_size)
            n += 1
        return bytes(out[:tamanho])

    def arquivos(self) -> dict[str, tuple[int, int]]:
        """nome completo ("ST/ST0/ST0.BIN", sem ";1") -> (setor inicial, tamanho). Guardado depois da 1ª leitura."""
        if getattr(self, "_cache", None) is None:
            with open(self._caminho, "rb") as f:
                pvd = self._bloco(f, 16, 2048)
                raiz = pvd[156:190]
                arqs: dict[str, tuple[int, int]] = {}
                self._ler_diretorio(f, int.from_bytes(raiz[2:6], "little"), int.from_bytes(raiz[10:14], "little"),
                                    "", arqs, set())
            self._cache = arqs
        return dict(self._cache)

    def _ler_diretorio(self, f: BinaryIO, setor: int, tamanho: int, caminho: str,
                       arquivos: dict[str, tuple[int, int]], vistos: set) -> None:
        """Lê um diretório (recursivo). Pula "." e ".." e nunca visita o mesmo setor duas vezes."""
        if setor in vistos:
            return
        vistos.add(setor)
        dados = self._bloco(f, setor, tamanho)
        i = 0
        while i < len(dados):
            tam = dados[i]
            if tam == 0:  # resto deste setor vazio: próximo setor do diretório
                i = (i // self._dados_size + 1) * self._dados_size
                continue
            inicio = int.from_bytes(dados[i + 2:i + 6], "little")
            tam_arq = int.from_bytes(dados[i + 10:i + 14], "little")
            flags = dados[i + 25]
            nl = dados[i + 32]
            nome = dados[i + 33:i + 33 + nl].decode("ascii", errors="replace")
            if nome not in ("\x00", "\x01"):
                completo = caminho + nome.split(";")[0]
                if flags & 2:
                    self._ler_diretorio(f, inicio, tam_arq, completo + "/", arquivos, vistos)
                else:
                    arquivos[completo] = (inicio, tam_arq)
            i += tam

    def ler(self, nome: str) -> bytes:
        """Lê os bytes de um arquivo."""
        arqs = self.arquivos()
        if nome not in arqs:
            raise FileNotFoundError(f"Arquivo {nome} não encontrado")
            
        inicio, tamanho = arqs[nome]
        
        with open(self._caminho, 'rb') as f:
            f.seek(inicio * self._setor_size + self._offset_dados)
            dados = b""
            bytes_lidos = 0
            
            while bytes_lidos < tamanho:
                setor = inicio + (bytes_lidos // self._dados_size)
                offset = bytes_lidos % self._dados_size
                bytes_a_ler = min(self._dados_size - offset, tamanho - bytes_lidos)
                
                f.seek(setor * self._setor_size + self._offset_dados + offset)
                dados += f.read(bytes_a_ler)
                bytes_lidos += bytes_a_ler
                
        return dados
    
    def gravar_copia(self, destino: Path, novos: dict[str, bytes]) -> None:
        """Grava uma cópia do disco com novos dados."""
        # Verificar tamanhos
        arqs = self.arquivos()
        for nome, novo_dado in novos.items():
            if nome not in arqs:
                raise ValueError(f"Arquivo {nome} não encontrado no disco original")
            _, tamanho_original = arqs[nome]
            if len(novo_dado) != tamanho_original:
                raise ValueError(f"Tamanho incorreto para {nome}: esperado {tamanho_original}, foi {len(novo_dado)}")
        
        # Copiar o arquivo bin
        shutil.copyfile(self._caminho, destino)
        
        with open(destino, 'r+b') as f:
            for nome, novo_dado in novos.items():
                inicio, tamanho = arqs[nome]
                
                # Escrever os dados nos setores
                bytes_escritos = 0
                while bytes_escritos < tamanho:
                    setor = inicio + (bytes_escritos // self._dados_size)
                    offset = bytes_escritos % self._dados_size
                    
                    f.seek(setor * self._setor_size + self._offset_dados + offset)
                    bytes_a_escrever = min(self._dados_size - offset, len(novo_dado) - bytes_escritos)
                    f.write(novo_dado[bytes_escritos:bytes_escritos + bytes_a_escrever])
                    bytes_escritos += bytes_a_escrever

def gravar_cue(cue_original: Path, cue_novo: Path, bin_novo_nome: str) -> None:
    """Grava um novo arquivo .cue com o nome do bin alterado."""
    with open(cue_original, 'r') as f:
        conteudo = f.read()
        
    linhas = conteudo.splitlines()
    novas_linhas = []
    
    for linha in linhas:
        if linha.strip().startswith('FILE "'):
            # Substituir o nome do arquivo
            inicio = linha.find('"') + 1
            fim = linha.rfind('"')
            linha = linha[:inicio] + bin_novo_nome + linha[fim:]
        novas_linhas.append(linha)
        
    with open(cue_novo, 'w') as f:
        f.write('\n'.join(novas_linhas) + '\n')
