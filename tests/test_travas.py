"""Travas contra falhas que JÁ aconteceram neste projeto (ver docs/LICOES.md). Cada teste diz qual falha ele impede."""
import hashlib
import py_compile
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
JS = RAIZ / "decky-plugin" / "dist" / "index.js"


def _arquivos(*globs):
    for g in globs:
        yield from (p for p in RAIZ.glob(g) if "__pycache__" not in p.parts and ".git" not in p.parts)


def test_todo_python_compila(tmp_path):
    """Falha antiga: código gerado/colado com escape errado (\\n virando quebra de linha) quebrou bot.py e
    glossario_franquia.py sem nenhum teste importar aquele trecho."""
    erros = []
    for p in _arquivos("dc/**/*.py", "tools/**/*.py", "decky-plugin/*.py"):
        try:
            py_compile.compile(str(p), cfile=str(tmp_path / "x.pyc"), doraise=True)
        except py_compile.PyCompileError as e:
            erros.append(f"{p.relative_to(RAIZ)}: {e.msg.splitlines()[0]}")
    assert not erros, erros


@pytest.mark.skipif(not shutil.which("node"), reason="node não instalado")
def test_painel_js_sintaxe():
    """Falha antiga: uma quebra de linha literal dentro de string deixou o painel do Decky inteiro sem abrir."""
    r = subprocess.run(["node", "--check", str(JS)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_powershell_com_acento_tem_bom():
    """Falha antiga: o PowerShell 5.1 lê .ps1 sem BOM como ANSI — acento quebrou a sintaxe (sincronizar-saves.ps1)."""
    ruins = [p.name for p in _arquivos("tools/**/*.ps1", "tools/**/*.psm1")
             if any(b > 127 for b in p.read_bytes()) and not p.read_bytes().startswith(b"\xef\xbb\xbf")]
    assert not ruins, f"salve com BOM (UTF-8 com assinatura): {ruins}"


@pytest.mark.skipif(not shutil.which("powershell"), reason="PowerShell só existe no Windows")
def test_powershell_sintaxe():
    """Falha antiga: script gerado pela IA local com "$var:" (referência inválida) só quebrava ao rodar."""
    cmd = ("$r=@(); Get-ChildItem -Recurse -Include *.ps1,*.psm1 '" + str(RAIZ / "tools") + "' | ForEach-Object { "
           "$e=$null; [System.Management.Automation.Language.Parser]::ParseFile($_.FullName,[ref]$null,[ref]$e)|Out-Null; "
           "if ($e.Count) { $r += $_.Name } }; $r -join ','")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=120)
    assert not r.stdout.strip(), f"erro de sintaxe em: {r.stdout.strip()}"


def test_powershell_que_conversa_com_ssh_usa_utf8():
    """Falha antiga: texto mandado ao ssh pelo PowerShell saía em ANSI ("Ragnarök" virou "RagnarÃ¶k")."""
    faltando = [p.name for p in _arquivos("tools/pc/*.ps1")
                if re.search(r"\|\s*&\s*ssh\.exe", p.read_text("utf-8-sig", "replace"))
                and "$OutputEncoding" not in p.read_text("utf-8-sig", "replace")]
    assert not faltando, f"defina $OutputEncoding = UTF-8 sem BOM: {faltando}"


def test_toda_acao_do_painel_existe_no_backend():
    """Falha antiga (risco): botão novo no painel chamando ação que não foi registrada em dc/painel.py."""
    from dc import painel
    usadas = set(re.findall(r'(?:painel|fazer|useDados)\("([a-z_]+)"', JS.read_text("utf-8")))
    faltam = sorted(a for a in usadas if a not in painel.ACOES)
    assert not faltam, faltam


def test_todo_comando_da_ajuda_e_atendido(tmp_path):
    """Falha antiga (risco): comando anunciado no /help que o bot responde "Comando desconhecido"."""
    from dc import bot
    from dc.paths import get_paths
    cmds = sorted(set(re.findall(r"^(/[a-z_]+)", bot.HELP, re.M)))
    x = bot.Bot(get_paths(tmp_path).ensure(), "T")
    x.cfg["allowed"] = [1]
    x.send = lambda *a, **k: None
    codigo = Path(bot.__file__).read_text("utf-8")
    sem_tratamento = [c for c in cmds if f'"{c}"' not in codigo]
    assert not sem_tratamento, sem_tratamento


# hashes (sha256) de endereços REAIS da casa do autor: nunca podem voltar ao repositório público
_PROIBIDOS = {
    "181a4a6223c470b20b94078e732491a2cf07fe3cd8ba884d4cd5ca0e6d07a484",
    "1fd85619550e849b241a3d1599f7828adc4ab612b90f80d6aec84df80e7053e6",
    "273d5bbcd1b6771e493caaccdad9992021efe37c7e9d1f0c58bbd82d83fad59f",
    "3ad1fa0a59e50baa55583d5f72761fd315f27034b04c09fd179a9db4d7d5179a",
    "4aa70675b0b5045e338298a03312027f784791595d562d55ff9aacf77ce6431f",
    "4fc7e183a4974a19abaf5f1c4fd36eb4a9120a3b864cb0da3b1632a7c267a189",
    "9bf23fd9ac57b32141922f61f871dbc2201a3e0e4820fa2d5297162d83a34a19",
}


def _hash(s: str) -> str:
    return hashlib.sha256(s.lower().encode()).hexdigest()


def test_sem_endereco_real_no_repositorio():
    """Falha antiga: IP do PC/Deck, IPs da Tailscale e MAC da casa ficaram no código e nos testes do repo público.
    A lista guarda só o sha256 dos valores reais (o próprio teste não os revela)."""
    achados = []
    for p in _arquivos("dc/**/*.py", "tools/**/*.py", "tools/**/*.ps1", "tools/**/*.psm1", "tests/*.py", "docs/*.md",
                       "*.md", "install.sh", "config/*"):
        txt = p.read_text("utf-8", "replace")
        candidatos = set(re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", txt))
        candidatos |= {m.replace(":", "-") for m in re.findall(r"\b[0-9A-Fa-f]{2}(?:[-:][0-9A-Fa-f]{2}){5}\b", txt)}
        achados += [f"{p.relative_to(RAIZ)}: {c}" for c in candidatos if _hash(c) in _PROIBIDOS]
    assert not achados, achados


def test_familia_nunca_envia_arquivo_de_jogo():
    """Regra de escopo: a família só troca texto (catálogo/magnet) e pacotes de tradução — nunca ROM/ISO."""
    from dc import familia
    for ext in (".nsp", ".xci", ".iso", ".chd", ".gba", ".sfc", ".nds", ".3ds", ".rvz", ".wbfs", ".7z", ".zip"):
        assert ext in familia.EXT_JOGO
    ok, nao = familia.filtrar_pacote(["/x/jogo.nsp", "/x/base/exefs/main"])
    assert ok == [] and len(nao) == 2


def test_sem_caractere_de_controle_invisivel():
    """Falha antiga (2x): "\b" e "\a" escritos por script viraram caracteres de controle invisíveis — regex que nunca
    casa e caminho "C:\AutomacaoCasa\agente" virando lixo. Tab e quebra de linha são permitidos."""
    ruins = []
    for p in _arquivos("dc/**/*.py", "tools/**/*.py", "tests/*.py", "decky-plugin/**/*.js", "decky-plugin/*.py",
                       "tools/**/*.ps1", "tools/**/*.psm1"):
        if "node_modules" in p.parts:
            continue
        txt = p.read_text("utf-8", "replace")
        if any(ord(c) < 32 and c not in "\t\n\r\f" for c in txt):
            ruins.append(str(p.relative_to(RAIZ)))
    assert not ruins, ruins


def test_powershell_nao_passa_aspas_escapadas_ao_ssh():
    """Falha encontrada na revisão: o PowerShell 5.1 perde as aspas duplas (`") ao chamar ssh.exe/scp.exe, então um
    caminho com espaço ("Pokemon Emerald.srm") quebrava. Use aspas simples no comando remoto."""
    ruins = [f"{p.name}:{i}" for p in _arquivos("tools/pc/*.ps1") for i, l in
             enumerate(p.read_text("utf-8-sig", "replace").splitlines(), 1)
             if re.search(r"&\s*(ssh|scp)\.exe", l) and '`"' in l]
    assert not ruins, ruins
