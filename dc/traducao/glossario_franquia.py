import json
import re
import tempfile
import shutil
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Union

FRANQUIAS: Dict[str, Tuple[str, ...]] = {
    "pokemon": ("pokemon",),
    "zelda": ("zelda",),
    "mario": ("mario",),
    "donkey kong": ("donkey kong",),
    "final fantasy": ("final fantasy",),
    "castlevania": ("castlevania",),
    "god of war": ("god of war",),
    "metroid": ("metroid",),
    "kirby": ("kirby",),
    "sonic": ("sonic",),
    "resident evil": ("resident evil", "biohazard"),
    "persona": ("persona",),
    "dragon quest": ("dragon quest",),
    "kingdom hearts": ("kingdom hearts",),
    "fire emblem": ("fire emblem",),
    "xenoblade": ("xenoblade",),
    "luigi": ("luigi",),
    "shadow of the colossus": ("shadow of the colossus", "ico")
}

PARADAS = {
    "The", "A", "An", "I", "You", "He", "She", "It", "We", "They",
    "My", "Your", "OK", "Yes", "No", "Hey", "Oh", "Hmm", "Huh", "Ah",
    "What", "Why", "How", "Who", "Where", "When", "This", "That",
    "These", "Those", "There", "Here", "Mr", "Mrs", "Ms", "Dr",
    "Lv", "HP", "MP", "PP", "Exp", "A/B/X/Y"
}

def franquia(titulo: str, extras: Optional[Dict[str, Tuple[str, ...]]] = None) -> Optional[str]:
    """Retorna a franquia correspondente ao título ou None."""
    import unicodedata
    # sem acento ANTES de limpar (senão "Pokémon" vira "pokmon"); extras do usuário têm prioridade
    titulo = "".join(c for c in unicodedata.normalize("NFD", titulo) if unicodedata.category(c) != "Mn").lower()
    frans = {**(extras or {}), **{k: v for k, v in FRANQUIAS.items() if k not in (extras or {})}}
    for nome, palavras in frans.items():
        for palavra in palavras:
            if palavra in titulo:
                return nome
    return None

def candidatos(textos: List[str], min_vezes: int = 3, limite: int = 150) -> List[str]:
    """Nomes próprios que se repetem: 1 a 4 palavras com maiúscula, fora do começo da frase, >= min_vezes."""
    from collections import Counter
    palavra = r"[A-ZÀ-Ý][\w'À-ÿ]*"
    rx = re.compile(rf"{palavra}(?:[ -]{palavra}){{0,3}}")
    cont: Counter = Counter()
    for t in textos:
        t = re.sub(r"<[^>]*>|\{[^}]*\}|⟦[^⟧]*⟧", " ", t)
        for m in rx.finditer(t):
            antes = t[:m.start()].rstrip()
            termo = m.group(0)
            if not antes or antes[-1] in ".!?:\"“":  # começo de frase: a 1ª maiúscula é só da frase...
                if " " not in termo:
                    continue
                termo = termo.split(" ", 1)[1]  # ..."Ask Bowser" / "The Mushroom Kingdom": o nome vem depois
            while termo.split(" ")[0] in PARADAS and " " in termo:  # "The Mushroom Kingdom" -> "Mushroom Kingdom"
                termo = termo.split(" ", 1)[1]
            if termo in PARADAS or len(termo) < 2:
                continue
            cont[termo] += 1
    return [t for t, n in cont.most_common() if n >= min_vezes][:limite]


def carregar(path: Path) -> Dict[str, Dict[str, str]]:
    """Carrega glossário de um arquivo JSON."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def salvar(path: Path, dados: Dict[str, Dict[str, str]]) -> None:
    """Salva glossário em arquivo JSON de forma atômica."""
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=1)
        shutil.move(tmp_path, path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()

def do_jogo(dados: Dict[str, Dict[str, str]], chave: Optional[str]) -> Dict[str, str]:
    """Retorna o glossário da franquia ou vazio."""
    return dados.get(chave, {}) if chave else {}

def faltando(dados: Dict[str, Dict[str, str]], chave: str, termos: List[str]) -> List[str]:
    """Retorna lista de termos que ainda não estão no glossário."""
    glossario = do_jogo(dados, chave)
    return [t for t in termos if t not in glossario]

def pedido_ia(termos: List[str], franquia: str) -> Tuple[str, str]:
    """Retorna instrução de sistema e texto do usuário para IA traduzir nomes."""
    instrucao = (
        "Você é um tradutor especializado em jogos eletrônicos. "
        "Traduza os seguintes termos para o português do Brasil. "
        "Se o nome deve permanecer igual (ex: nome de personagem), responda com '='."
    )
    texto = (
        f"Traduza os seguintes nomes da franquia {franquia} para o português do Brasil:\n"
        + "\n".join(f"- {t}" for t in termos)
        + "\n\nResponda apenas com um JSON no formato: "
        + '{"termo original": "tradução"}'
    )
    return instrucao, texto

def ler_resposta(texto: str, termos: List[str]) -> Dict[str, str]:
    """Pega o primeiro objeto JSON da resposta da IA (mesmo cercado de crases) e fica só com os termos pedidos.
    "=" quer dizer: o nome fica igual."""
    ini = texto.find("{")
    fim = texto.rfind("}")
    if ini < 0 or fim <= ini:
        return {}
    try:
        bruto = json.loads(texto[ini:fim + 1])
    except ValueError:
        return {}
    out: Dict[str, str] = {}
    for termo in termos:
        v = bruto.get(termo) if isinstance(bruto, dict) else None
        if isinstance(v, str) and v.strip():
            out[termo] = termo if v.strip() == "=" else v.strip()
    return out


def juntar(dados: Dict[str, Dict[str, str]], chave: str, novos: Dict[str, str]) -> Dict[str, Dict[str, str]]:
    """Cópia com os termos novos da franquia, sem sobrescrever os que já existem (correção à mão vale)."""
    out = {k: dict(v) for k, v in dados.items()}
    atual = out.setdefault(chave, {})
    for termo, trad in novos.items():
        atual.setdefault(termo, trad)
    return out
