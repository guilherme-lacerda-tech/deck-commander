"""Melhorias pelos bancos de patch dos próprios emuladores (widescreen, sem entrelaçamento): só edita .ini, com backup.

Escrito pela IA local (qwen3-coder) e revisado.
"""
import os
import shutil
from pathlib import Path
from typing import Dict, List, Tuple

OPCOES: Dict[str, Dict] = {
    "pcsx2": {
        "nome": "PCSX2 (PS2)",
        "arquivo": ".var/app/net.pcsx2.PCSX2/config/PCSX2/inis/PCSX2.ini",
        "opcoes": {
            "widescreen": [
                ("EmuCore", "EnableWideScreenPatches", "true", "false")
            ],
            "sem_entrelacamento": [
                ("EmuCore", "EnableNoInterlacingPatches", "true", "false")
            ]
        }
    },
    "duckstation": {
        "nome": "DuckStation (PS1)",
        "arquivo": ".local/share/duckstation/settings.ini",
        "opcoes": {
            "widescreen": [
                ("GPU", "WidescreenHack", "true", "false"),
                ("Display", "AspectRatio", "16:9", "Auto (Game Native)")
            ],
            "sem_entrelacamento": []
        }
    },
    "dolphin": {
        "nome": "Dolphin (GameCube/Wii)",
        "arquivo": ".var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu/GFX.ini",
        "opcoes": {
            "widescreen": [
                ("Settings", "wideScreenHack", "True", "False"),
                ("Settings", "AspectRatio", "1", "0")
            ],
            "sem_entrelacamento": []
        }
    }
}

def ler_ini_valor(texto: str, secao: str, chave: str) -> str | None:
    """Lê o valor de uma chave em uma seção do arquivo INI (case-insensitive)."""
    secao = secao.lower()
    chave = chave.lower()
    for linha in texto.splitlines():
        if linha.strip().startswith('[') and linha.strip().endswith(']'):
            atual_secao = linha.strip()[1:-1].lower()
        elif '=' in linha:
            k, v = linha.split('=', 1)
            if k.strip().lower() == chave and atual_secao == secao:
                return v.strip()
    return None

def trocar_ini_valor(texto: str, secao: str, chave: str, valor: str) -> str:
    """Altera o valor de uma chave em uma seção do arquivo INI, preservando formatação."""
    linhas = texto.splitlines(keepends=True)
    nova_linha = f"{chave} = {valor}\n"
    encontrou_secao = False
    encontrou_chave = False
    i = 0

    while i < len(linhas):
        linha = linhas[i]
        if linha.strip().startswith('[') and linha.strip().endswith(']'):
            atual_secao = linha.strip()[1:-1]
            if atual_secao.lower() == secao.lower():
                encontrou_secao = True
            else:
                encontrou_secao = False
        elif '=' in linha and encontrou_secao:
            k, _ = linha.split('=', 1)
            if k.strip().lower() == chave.lower():
                linhas[i] = nova_linha
                encontrou_chave = True
                break
        i += 1

    if not encontrou_chave:
        if not encontrou_secao:
            linhas.append(f"[{secao}]\n")
        linhas.append(nova_linha)

    return ''.join(linhas)

def estado(home: Path) -> List[Dict]:
    """Retorna o estado atual das opções para emuladores existentes."""
    resultado = []
    for emulador, dados in OPCOES.items():
        arquivo_path = home / dados["arquivo"]
        if not arquivo_path.exists():
            continue
        try:
            conteudo = arquivo_path.read_text(encoding="utf-8")
        except Exception:
            continue

        opcoes_estado = {}
        for nome_opcao, lista_chaves in dados["opcoes"].items():
            todas_ligadas = True
            for secao, chave, valor_ligado, _ in lista_chaves:
                valor_atual = ler_ini_valor(conteudo, secao, chave)
                if not valor_atual or valor_atual.lower() != valor_ligado.lower():
                    todas_ligadas = False
                    break
            opcoes_estado[nome_opcao] = todas_ligadas

        resultado.append({
            "emulador": emulador,
            "nome": dados["nome"],
            "opcoes": opcoes_estado
        })

    return resultado

def definir(home: Path, emulador: str, opcao: str, ligar: bool) -> str:
    """Aplica ou desaplica uma opção para um emulador."""
    if emulador not in OPCOES:
        raise ValueError("Emulador inválido.")
    if opcao not in OPCOES[emulador]["opcoes"]:
        raise ValueError("Opção inválida.")

    dados = OPCOES[emulador]
    arquivo_path = home / dados["arquivo"]
    if not arquivo_path.exists():
        raise ValueError(f"Abra o {dados['nome']} uma vez para ele criar a configuração.")

    backup_path = arquivo_path.with_suffix(arquivo_path.suffix + ".antes-deck-commander")
    if not backup_path.exists():
        shutil.copy2(arquivo_path, backup_path)

    conteudo = arquivo_path.read_text(encoding="utf-8")
    novo_conteudo = conteudo

    # cada chave tem o próprio valor (ex.: DuckStation: WidescreenHack=true E AspectRatio=16:9)
    for secao, chave, valor_ligado, valor_desligado in dados["opcoes"][opcao]:
        novo_conteudo = trocar_ini_valor(novo_conteudo, secao, chave, valor_ligado if ligar else valor_desligado)

    temp_path = arquivo_path.with_suffix(arquivo_path.suffix + ".tmp")
    temp_path.write_text(novo_conteudo, encoding="utf-8")
    temp_path.replace(arquivo_path)

    nome_opcao = {"widescreen": "Tela cheia 16:9", "sem_entrelacamento": "Sem tremido (entrelaçamento)"}.get(opcao, opcao)
    frase = f"{nome_opcao} {'ligado' if ligar else 'desligado'} no {dados['nome']}."
    return f"{frase} Vale na próxima vez que abrir o jogo."
