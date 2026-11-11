import re
import difflib
import json
import base64
import urllib.request
import urllib.error
from pathlib import Path
from typing import List, Tuple, Dict

MARCADOR = re.compile(r"⟦\d+⟧")

def normalizar(t: str) -> str:
    """Remove marcadores, troca quebras de linha por espaço, minúsculas e remove pontuação."""
    t = MARCADOR.sub("", t)
    t = t.replace("\n", " ")
    t = t.lower()
    t = re.sub(r"[^\w\s]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

def parecidas(ocr: str, frases: Dict[str, str], limite: int = 3, minimo: float = 0.55) -> List[Tuple[str, float, str]]:
    """Encontra frases do cache mais parecidas com o OCR."""
    ocr_norm = normalizar(ocr)
    palavras_ocr = set(ocr_norm.split())
    candidatos = []

    for chave, frase in frases.items():
        if len(normalizar(frase)) < 4:
            continue
        frase_norm = normalizar(frase)
        palavras_frase = set(frase_norm.split())

        # Pré-filtro: verificar se há interseção de palavras longas
        palavras_longas_ocr = {p for p in palavras_ocr if len(p) >= 4}
        palavras_longas_frase = {p for p in palavras_frase if len(p) >= 4}
        if not palavras_longas_ocr & palavras_longas_frase:
            continue

        # Comparar com o OCR inteiro
        seq_matcher = difflib.SequenceMatcher(None, ocr_norm, frase_norm)
        nota_inteira = seq_matcher.ratio()

        # Comparar com cada linha do OCR
        linhas_ocr = [l.strip() for l in ocr.splitlines() if l.strip()]
        notas_linhas = []
        for linha in linhas_ocr:
            linha_norm = normalizar(linha)
            if len(linha_norm) < 4:
                continue
            matcher = difflib.SequenceMatcher(None, linha_norm, frase_norm)
            notas_linhas.append(matcher.ratio())
        
        melhor_nota = max(notas_linhas) if notas_linhas else nota_inteira
        if melhor_nota >= minimo:
            candidatos.append((chave, round(melhor_nota, 2), frase))

    return sorted(candidatos, key=lambda x: x[1], reverse=True)[:limite]

def marcadores_ok(antiga: str, nova: str) -> bool:
    """Verifica se as listas de marcadores são idênticas."""
    antigos = MARCADOR.findall(antiga)
    novos = MARCADOR.findall(nova)
    return sorted(antigos) == sorted(novos)  # a ordem pode mudar na tradução; os códigos não

def pedido_ia(frase: str, pedido_usuario: str = "") -> Tuple[str, str]:
    """Monta prompt para IA com instruções de tradução."""
    sistema = (
        "Você é um tradutor profissional de jogos eletrônicos. "
        "Traduza a frase abaixo para o português do Brasil natural, como numa tradução oficial de jogo. "
        "Mantenha EXATAMENTE os marcadores ⟦n⟧ no mesmo lugar e quantidade. "
        "Não use aspas nem explique. Apenas responda com a tradução."
    )
    usuario = f"Frase: {frase}"
    if pedido_usuario:
        usuario += f"\nOrientação: {pedido_usuario}"
    return sistema, usuario

def limpar_resposta(txt: str) -> str:
    """Tira prefixo tipo "Tradução:" e aspas/crases em volta da frase."""
    t = txt.strip()
    t = re.sub(r"^(tradu[cç][aã]o|resposta|frase|vers[aã]o)\s*(corrigida|melhor)?\s*:\s*", "", t, flags=re.I)
    t = t.strip().strip("`").strip()
    if len(t) >= 2 and t[0] in "\"'“«" and t[-1] in "\"'”»":
        t = t[1:-1]
    return t.strip()


def aplicar(arquivos: List[Path], chave: str, nova: str) -> List[Path]:
    """Aplica a nova tradução em arquivos de cache."""
    alterados = []
    for arquivo in arquivos:
        if not arquivo.exists():
            continue
        with open(arquivo, "r", encoding="utf-8") as f:
            dados = json.load(f)
        
        if chave not in dados:
            continue

        antiga = dados[chave]
        if not marcadores_ok(antiga, nova):
            raise ValueError("Marcadores não correspondem")

        # Criar backup se necessário
        backup = arquivo.with_suffix(arquivo.suffix + ".antes-correcao")
        if not backup.exists():
            with open(arquivo, "r", encoding="utf-8") as f:
                conteudo = f.read()
            with open(backup, "w", encoding="utf-8") as f:
                f.write(conteudo)

        dados[chave] = nova
        tmp = arquivo.with_suffix(arquivo.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
        tmp.replace(arquivo)
        alterados.append(arquivo)

    return alterados

def pedido_ocr(imagem: bytes, modelo: str) -> Dict:
    """Monta corpo da requisição OCR para Ollama."""
    return {
        "model": modelo,
        "prompt": (
            "Transcreva exatamente, linha por linha, o texto de legenda/diálogo em português que aparece "
            "nesta imagem de um jogo. Responda só com o texto."
        ),
        "images": [base64.b64encode(imagem).decode("utf-8")],
        "stream": False,
        "options": {"temperature": 0}
    }

def ocr(url_base: str, modelo: str, imagem: bytes, timeout: int = 180, abrir=urllib.request.urlopen) -> str:
    """Faz OCR usando Ollama."""
    try:
        req = urllib.request.Request(
            url_base + "/api/generate",
            data=json.dumps(pedido_ocr(imagem, modelo)).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with abrir(req, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data["response"].strip()
    except Exception as e:
        raise RuntimeError(f"Erro na requisição OCR: {str(e)}")
