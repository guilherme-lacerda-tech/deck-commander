import re
import unicodedata

# TRADUCOES: dicionário de termos em inglês para português
TRADUCOES = {
    "Infinite Lives": "Vidas infinitas",
    "Infinite Health": "Vida infinita",
    "Infinite Energy": "Vida infinita",
    "Infinite HP": "Vida infinita",
    "Infinite Ammo": "Munição infinita",
    "Max Money": "Dinheiro máximo",
    "Infinite Money": "Dinheiro infinito",
    "Invincibility": "Invencível",
    "Have All Items": "Todos os itens",
    "Moon Jump": "Pulo lunar",
    "Infinite Time": "Tempo infinito",
    "Level Select": "Escolher fase",
    "Infinite Continues": "Continues infinitos",
    "Infinite Magic": "Magia infinita",
    "Infinite MP": "Magia infinita",
    "Max Stats": "Atributos no máximo",
    "Walk Through Walls": "Atravessar paredes",
    "Infinite Items": "Itens infinitos",
    "Max Level": "Nível máximo",
    "Infinite Bombs": "Bombas infinitas",
    "Start With": "Começar com",
    "Player 1": "Jogador 1",
    "Player 2": "Jogador 2",
    "Always": "Sempre",
    "Instant Win": "Vitória instantânea",
    "Max Exp": "Experiência máxima"
}

def ler_cht(texto: str) -> list[dict]:
    """Lê um conteúdo .cht e retorna lista de cheats."""
    linhas = [l.strip() for l in texto.splitlines() if l.strip() and not l.strip().startswith("#")]
    n_cheats = 0
    for linha in linhas:
        if linha.startswith("cheats = "):
            n_cheats = int(linha.split("= ")[1])
            break

    cheats = []
    cheat_atual = {}
    idx = -1

    for linha in linhas:
        if linha.startswith("cheat") and "=" in linha:
            match = re.match(r"cheat(\d+)_(\w+)\s*=\s*(.*)", linha)
            if not match:
                continue
            i, chave, valor = match.groups()
            i = int(i)
            if i != idx:
                if idx >= 0 and cheat_atual:
                    cheats.append(cheat_atual)
                cheat_atual = {"i": i, "desc": "", "code": "", "enable": False, "extra": {}}
                idx = i
            valor = valor.strip().strip('"')
            if chave == "desc":
                cheat_atual["desc"] = valor
            elif chave == "code":
                cheat_atual["code"] = valor
            elif chave == "enable":
                cheat_atual["enable"] = valor.lower() == "true"
            else:
                cheat_atual["extra"][chave] = valor
        elif linha.startswith("cheats = "):
            continue
    if idx >= 0 and cheat_atual:
        cheats.append(cheat_atual)

    if not n_cheats:
        n_cheats = len(cheats)
    if len(cheats) < n_cheats:
        for i in range(len(cheats), n_cheats):
            cheats.append({"i": i, "desc": "", "code": "", "enable": False, "extra": {}})

    return sorted(cheats, key=lambda x: x["i"])

def escrever_cht(cheats: list[dict]) -> str:
    """Gera texto no formato .cht a partir de lista de cheats."""
    if not cheats:
        return ""
    n = len(cheats)
    saida = [f"cheats = {n}\n"]
    for c in cheats:
        saida.append(f"cheat{c['i']}_desc = \"{c['desc']}\"\n")
        saida.append(f"cheat{c['i']}_code = \"{c['code']}\"\n")
        saida.append(f"cheat{c['i']}_enable = {str(c['enable']).lower()}\n")
        for k, v in c["extra"].items():
            saida.append(f"cheat{c['i']}_{k} = {v}\n")
        saida.append("\n")
    return "".join(saida).rstrip("\n") + "\n"

def normalizar(nome: str) -> str:
    """Normaliza nome de jogo para comparar com nomes de arquivos."""
    nome = re.sub(r"\.[A-Za-z0-9]{1,4}$", "", nome)  # extensão (.sfc, .cht, .zip…)
    nome = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", nome)  # tudo entre () e [] some: (USA), [!]
    nome = re.sub(r"&", "and", nome)
    nome = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode("ascii")
    nome = re.sub(r"[^a-z0-9 ]", "", nome.lower())
    nome = re.sub(r"\s+", " ", nome).strip()
    return nome

def achar_cht(arquivos: list[str], jogo: str) -> str | None:
    """Encontra o arquivo .cht que casa com o nome do jogo."""
    norm_jogo = normalizar(jogo)
    if not norm_jogo:
        return None
    exatos = [f for f in arquivos if normalizar(f) == norm_jogo]
    candidatos = exatos or [f for f in arquivos if normalizar(f).startswith(norm_jogo)]  # igual vence "começa com"
    if not candidatos:
        return None
    regiao = lambda f: 0 if "(USA)" in f else 1 if "(Europe)" in f else 2  # noqa: E731
    return min(candidatos, key=lambda f: (regiao(f), len(f)))

def traduzir_desc(desc: str) -> str:
    """Traduz descrição de cheat usando TRADUCOES."""
    desc = desc.strip()
    for termo, traducao in sorted(TRADUCOES.items(), key=lambda x: len(x[0]), reverse=True):
        if termo.lower() in desc.lower():
            desc = re.sub(re.escape(termo), traducao, desc, flags=re.IGNORECASE)
    return desc

def com_ativos(cheats: list[dict], ativos: set[int]) -> list[dict]:
    """Retorna cópia dos cheats com apenas os índices em `ativos` ativados."""
    novos = []
    for c in cheats:
        novo = dict(c)
        novo["enable"] = novo["i"] in ativos
        novos.append(novo)
    return novos
