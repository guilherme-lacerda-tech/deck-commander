"""Revisão de código pela IA local (Ollama no PC), em pedaços e com vários focos. Os achados vão para um .jsonl;
NADA é corrigido sozinho — cada achado precisa ser conferido (a IA local erra).

    python tools/ia-local-revisao.py <saida.jsonl> <arquivo> [<arquivo> ...]
"""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

URL = "http://127.0.0.1:11434/api/generate"
MODELO = "qwen3-coder:30b"
FOCOS = {
    "erros": "erros de lógica, condições invertidas, índices errados, exceções não tratadas que derrubam o programa, "
             "valores None não tratados, variáveis usadas antes de definir",
    "robustez": "o que acontece com arquivo ausente/corrompido, rede caindo, processo travado, disco cheio, dados de "
                "entrada inesperados, condições de corrida, perda de dados, segurança (caminhos, comandos montados com "
                "texto do usuário)",
    "desempenho": "trabalho repetido desnecessário, leitura de arquivos enormes inteiros na memória, laços quadráticos, "
                  "chamadas de rede/subprocesso dentro de laço, falta de tempo-limite (timeout)",
}
PEDACO = 220  # linhas por pedaço (com 20 de sobreposição)


def perguntar(prompt: str) -> str:
    corpo = json.dumps({"model": MODELO, "prompt": prompt, "stream": False,
                        "options": {"temperature": 0.1, "num_ctx": 16384}}).encode()
    req = urllib.request.Request(URL, corpo, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        return json.loads(r.read())["response"]


def revisar(arquivo: Path, foco: str, descricao: str):
    linhas = arquivo.read_text("utf-8", "replace").splitlines()
    for ini in range(0, max(1, len(linhas)), PEDACO - 20):
        trecho = "\n".join(f"{i + 1:5d}| {l}" for i, l in enumerate(linhas[ini:ini + PEDACO], start=ini))
        prompt = (f"Revise este trecho do arquivo {arquivo.as_posix()} (projeto Python/PowerShell/JS para Steam Deck).\n"
                  f"Foco: {descricao}.\nAponte SÓ problemas reais e concretos, com a linha. Se não houver, responda [].\n"
                  "Responda SOMENTE um JSON: lista de objetos {\"linha\": int, \"gravidade\": \"alta|media|baixa\", "
                  "\"problema\": str, \"sugestao\": str}.\n\n" + trecho)
        t0 = time.time()
        try:
            txt = perguntar(prompt)
        except Exception as e:  # noqa: BLE001
            yield {"arquivo": arquivo.as_posix(), "foco": foco, "erro": str(e)}
            continue
        m = re.search(r"\[.*\]", txt, re.DOTALL)
        try:
            achados = json.loads(m.group(0)) if m else []
        except ValueError:
            achados = []
        for a in achados if isinstance(achados, list) else []:
            if isinstance(a, dict):
                yield {"arquivo": arquivo.as_posix(), "foco": foco, "segundos": round(time.time() - t0), **a}
        if ini + PEDACO >= len(linhas):
            break


if __name__ == "__main__":
    saida = Path(sys.argv[1])
    with saida.open("a", encoding="utf-8") as f:
        for arq in sys.argv[2:]:
            for foco, desc in FOCOS.items():
                for achado in revisar(Path(arq), foco, desc):
                    f.write(json.dumps(achado, ensure_ascii=False) + "\n")
                    f.flush()
            print("revisado:", arq, flush=True)
