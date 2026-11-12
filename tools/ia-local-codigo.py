"""Gera código com a IA local (Ollama no PC) a partir de uma especificação em texto.

    python tools/ia-local-codigo.py <especificacao.md> <arquivo-de-saida> [modelo]

A especificação diz o que o módulo faz; o modelo devolve UM bloco de código, gravado no arquivo de saída.
Tudo roda no PC (nada vai para a internet). Sempre revise e teste o que sair daqui.
"""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

URL = "http://127.0.0.1:11434/api/generate"
SISTEMA = ("Você é um programador Python sênior. Responda SOMENTE com um único bloco de código ```python ...```, "
           "completo e pronto para salvar no arquivo pedido, sem explicações fora do bloco. Use apenas a biblioteca "
           "padrão do Python 3.11, type hints, docstrings e comentários curtos em português.")


def gerar(spec: str, modelo: str) -> str:
    corpo = json.dumps({"model": modelo, "system": SISTEMA, "prompt": spec, "stream": False,
                        "options": {"temperature": 0.2, "num_ctx": 16384}}).encode()
    req = urllib.request.Request(URL, corpo, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=3600) as r:
        txt = json.loads(r.read())["response"]
    m = re.search(r"```(?:python|py|powershell|javascript|js)?\s*\n(.*?)```", txt, re.DOTALL)
    return (m.group(1) if m else txt).rstrip() + "\n"


if __name__ == "__main__":
    spec, saida = Path(sys.argv[1]), Path(sys.argv[2])
    modelo = sys.argv[3] if len(sys.argv) > 3 else "qwen3-coder:30b"
    t0 = time.time()
    codigo = gerar(spec.read_text("utf-8"), modelo)
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(codigo, "utf-8")
    print(f"{saida}: {len(codigo.splitlines())} linhas em {time.time() - t0:.0f}s ({modelo})")
