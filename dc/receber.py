"""Transferência PC -> Deck: recebe um jogo do PC (jogo + dados do emulador) e instala no Deck.

O PC (tools/pc/enviar-para-deck.ps1) monta o MANIFESTO do PC, copia tudo por sftp (com retomada) para uma
ÁREA DE RECEBIMENTO no Deck e confere cada arquivo com `sha256sum -c`. Depois chama
`python3 -m dc.transferir receber <id>`, que:

  1. confere de novo o sha256 de cada arquivo da área;
  2. se o Deck não tem o emulador, instala a versão OFICIAL para Linux (Flatpak do Flathub quando existe,
     senão o AppImage/tar da página oficial de releases, com sha256 conferido quando publicado);
  3. põe o jogo em ~/Emulation/roms/<console>/<jogo> e os dados do emulador nos caminhos Linux dele
     (o inverso do mapeamento de dc/transferir.py), trocando caminhos do Windows (D:/...) pelos do Deck
     nos .ini/.json; antes de sobrescrever QUALQUER arquivo do Deck faz backup em
     <pasta>/_backup-deck-commander/<data>-<jogo>/;
  4. põe o jogo na biblioteca do Steam (a mesma função do /sync).

Área de recebimento: ~/.local/share/deck-commander/receber/<id>/ com manifesto.json, SHA256SUMS e
arquivos/<JOGOS|EMU>/... . Com --destino-teste <pasta>, tudo (área e instalação) fica dentro dessa pasta,
que faz o papel de "home": nada toca ~/Emulation nem as pastas reais dos emuladores, e nada é instalado.

Formato do manifesto do PC (JSON):
  {"versao": 1, "direcao": "pc->deck", "game_id", "titulo", "console", "emulador",
   "emulador_pc": {"versao", "exe"}, "reescrever": [{"de": "D:/Emuladores/DuckStation", "para": "{EMU}"}, ...],
   "arquivos": [{"rel": "JOGOS/psx/Jogo/jogo.cue", "destino": "{JOGOS}/psx/Jogo/jogo.cue", "sha256", "tamanho",
                 "categoria", "reescrever": true|false}], "avisos": [], "notas": []}

Só stdlib e sem import relativo no topo: roda instalado (`python3 -m dc.transferir receber <id>`) ou mandado
pelo PC pela entrada padrão (`cd ~/deck-commander; python3 - receber <id>`), sem instalar nada.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

VERSAO = 1
TABELA_NOME = "emuladores-oficiais.json"
TEXTO_EXTS = {".ini", ".json", ".cfg", ".opt", ".rmp", ".txt", ".pnach", ".cht", ".m3u", ".cue"}
FLATPAK = "/usr/bin/flatpak"
UA = "deck-commander-transferencia"


# ------------------------------------------------------------------ caminhos -----------
def _home(home=None) -> Path:
    return Path(home) if home else Path(os.environ.get("DC_ROOT") or Path.home())


def _data_dir(home: Path) -> Path:
    if os.environ.get("XDG_DATA_HOME") and not os.environ.get("DC_ROOT"):
        return Path(os.environ["XDG_DATA_HOME"]) / "deck-commander"
    return home / ".local/share/deck-commander"


def _expandir(p: str | None, home: Path) -> Path | None:
    if not p:
        return None
    return home / p[2:] if p.startswith("~/") else Path(p)


def area_de(gid: str, home=None, destino_teste: Path | None = None) -> Path:
    home = _home(home)
    if destino_teste:
        return Path(destino_teste) / "area" / gid
    return _data_dir(home) / "receber" / gid


def jogos_pc_path(home=None) -> Path:
    """Lista de jogos do PC que podem vir para o Deck (o PC grava pela transferir-fila.ps1)."""
    return _data_dir(_home(home)) / "pc-jogos-transferiveis.json"


def ler_jogos_pc(home=None) -> dict:
    try:
        d = json.loads(jogos_pc_path(home).read_text("utf-8-sig"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


# ------------------------------------------------------------------ tabela oficial -----
def tabela(home=None, area: Path | None = None) -> dict:
    """config/emuladores-oficiais.json (o PC também manda uma cópia junto da área de recebimento)."""
    home = _home(home)
    cands = []
    if os.environ.get("DC_EMU_TABELA"):
        cands.append(Path(os.environ["DC_EMU_TABELA"]))
    if area:
        cands += [Path(area) / TABELA_NOME, Path(area).parent / TABELA_NOME]
    cands.append(_data_dir(home) / "receber" / TABELA_NOME)
    try:
        cands.append(Path(__file__).resolve().parents[1] / "config" / TABELA_NOME)
    except (NameError, IndexError):
        pass
    cands.append(Path.cwd() / "config" / TABELA_NOME)
    for c in cands:
        try:
            return json.loads(c.read_text("utf-8-sig"))["emuladores"]
        except (OSError, ValueError, KeyError):
            continue
    return {}


def emu_do_console(console: str, tab: dict) -> str | None:
    for k, e in tab.items():
        if console in e.get("consoles", []):
            return k
    return None


# ------------------------------------------------------------------ emulador no Deck ---
def flatpak_info(app_id: str) -> str | None:
    """Versão do Flatpak instalado ("" se instalado sem versão), None se não está instalado."""
    try:
        r = subprocess.run([FLATPAK, "info", app_id], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    mm = re.search(r"^\s*(?:Version|Versão):\s*(\S+)", r.stdout, re.MULTILINE)
    return mm.group(1) if mm else ""


def _versao_do_nome(p: str) -> str | None:
    mm = re.search(r"(build-\d+|v?\d+\.\d+(?:\.\d+)*)", Path(p).name)
    return mm.group(1) if mm else None


def emulador_no_deck(emu: str, home=None, tab: dict | None = None, flatpak=flatpak_info) -> dict:
    """{emulador, nome, instalado, tipo (appimage|pasta|flatpak), onde, versao}. Só lê."""
    home = _home(home)
    tab = tab if tab is not None else tabela(home)
    e = tab.get(emu) or {}
    lx = e.get("linux") or {}
    out = {"emulador": emu, "nome": e.get("nome", emu), "instalado": False, "tipo": None, "onde": None,
           "versao": None, "pagina": e.get("pagina")}
    for g in lx.get("procurar", []):
        hits = [h for h in sorted(glob.glob(str(home / g)), reverse=True) if os.path.isfile(h)]
        if hits:
            out.update(instalado=True, tipo="appimage" if hits[0].endswith(".AppImage") else "pasta", onde=hits[0],
                       versao=_versao_do_nome(hits[0]))
            return out
    if lx.get("flatpak") and flatpak:
        v = flatpak(lx["flatpak"])
        if v is not None:
            out.update(instalado=True, tipo="flatpak", onde=lx["flatpak"], versao=v or None)
    return out


def detectar_todos(home=None, tab: dict | None = None, flatpak=flatpak_info) -> list[dict]:
    tab = tab if tab is not None else tabela(home)
    return [emulador_no_deck(k, home, tab, flatpak) for k in tab]


# ------------------------------------------------------------------ releases oficiais --
def _get_json(url: str, timeout: float = 30):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - só URLs da tabela oficial
        return json.loads(r.read().decode("utf-8"))


def _api_base(fonte: dict, linux: bool = False) -> str | None:
    if fonte.get("tipo") == "github":
        repo = fonte.get("repo_linux") if linux and fonte.get("repo_linux") else fonte.get("repo")
        return f"https://api.github.com/repos/{repo}"
    if fonte.get("tipo") == "forgejo":
        return fonte["api"]
    return None


def release(fonte: dict, versao: str | None = None, linux: bool = False, get=_get_json) -> dict | None:
    """Release oficial: a da versão pedida (mesma build do outro lado) ou a estável mais recente."""
    base = _api_base(fonte, linux)
    if not base:
        return None
    r = None
    if versao:
        try:
            r = get(f"{base}/releases/tags/{versao}")
        except Exception:  # noqa: BLE001 - versão que não existe mais: cai na mais recente
            r = None
    if not r:
        r = get(f"{base}/releases/latest")
    assets = [{"nome": a.get("name"), "url": a.get("browser_download_url"), "tamanho": a.get("size"),
               "sha256": (a.get("digest") or "").split(":", 1)[1] if (a.get("digest") or "").startswith("sha256:") else None}
              for a in r.get("assets", [])]
    return {"versao": r.get("tag_name"), "assets": assets, "pedida": versao,
            "mesma_versao": bool(versao) and r.get("tag_name") == versao}


def plano_instalacao(emu: str, versao: str | None = None, home=None, tab: dict | None = None,
                     get=_get_json) -> dict:
    """O que instalar no Deck quando falta o emulador (consulta a API oficial; não baixa nada)."""
    home = _home(home)
    tab = tab if tab is not None else tabela(home)
    e = tab.get(emu)
    if not e:
        return {"acao": "nenhum", "motivo": f"emulador sem origem oficial na tabela: {emu}"}
    lx = e.get("linux") or {}
    base = {"emulador": emu, "nome": e.get("nome", emu), "pagina": e.get("pagina")}
    if lx.get("flatpak"):
        return {**base, "acao": "flatpak", "id": lx["flatpak"], "versao": "a do Flathub",
                "comando": f"flatpak install --user -y flathub {lx['flatpak']}"}
    if not lx.get("asset"):
        return {**base, "acao": "nenhum", "motivo": "sem versão Linux oficial automática; instale pela página oficial"}
    try:
        rel = release(e["fonte"], versao, linux=True, get=get)
    except Exception as ex:  # noqa: BLE001
        return {**base, "acao": "nenhum", "motivo": f"não consegui consultar a página oficial: {ex}"}
    if not rel:
        return {**base, "acao": "nenhum", "motivo": "fonte oficial sem API de releases"}
    a = next((x for x in rel["assets"] if x["nome"] and re.search(lx["asset"], x["nome"])), None)
    if not a:
        return {**base, "acao": "nenhum", "motivo": f"a release {rel['versao']} não tem o arquivo Linux esperado"}
    destino = lx.get("instalar_em") or f"Applications/{a['nome']}"
    return {**base, "acao": "tar" if destino.endswith("/") else "appimage", "versao": rel["versao"],
            "mesma_versao": rel["mesma_versao"], "url": a["url"], "arquivo": a["nome"], "tamanho": a["tamanho"],
            "sha256": a["sha256"], "destino": str(home / destino)}


def texto_plano(p: dict) -> str:
    if p.get("acao") == "flatpak":
        return f"o emulador {p['nome']} vai ser instalado no Deck (Flatpak {p['id']} do Flathub, página oficial)"
    if p.get("acao") in ("appimage", "tar"):
        mesma = " — mesma versão do PC" if p.get("mesma_versao") else ""
        conf = (f"sha256 publicado {p['sha256'][:12]}…, conferido no download" if p.get("sha256")
                else "sem sha256 publicado")
        return (f"o emulador {p['nome']} vai ser instalado no Deck (versão {p['versao']}{mesma}, da página oficial: "
                f"{p['url']}; {conf}) em {p['destino']}")
    return f"o emulador {p.get('nome', '?')} NÃO está no Deck e não dá para instalar sozinho: {p.get('motivo', '')}"


def _baixar(url: str, dest: Path, sha256: str | None) -> None:
    import urllib.request
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".baixando")
    h = hashlib.sha256()
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:  # noqa: S310
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            h.update(b)
            f.write(b)
    if sha256 and h.hexdigest() != sha256.lower():
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"sha256 do download não confere com o publicado ({url})")
    os.replace(tmp, dest)


def instalar_emulador(p: dict, simular: bool = False, run=subprocess.run) -> str:
    """Executa o plano. Nunca sobrescreve um emulador que já existe."""
    if simular or p.get("acao") == "nenhum":
        return ("[simulação] " if simular else "") + texto_plano(p)
    if p["acao"] == "flatpak":
        r = run([FLATPAK, "install", "--user", "-y", "flathub", p["id"]], capture_output=True, text=True, timeout=1800)
        if r.returncode != 0:
            raise RuntimeError(f"flatpak install falhou: {(r.stderr or r.stdout)[-300:]}")
        return f"instalado: {p['nome']} (Flatpak {p['id']})"
    dest = Path(p["destino"])
    if p["acao"] == "appimage":
        if dest.exists():
            return f"{dest} já existe: não mexi"
        _baixar(p["url"], dest, p.get("sha256"))
        dest.chmod(0o755)
        return f"instalado: {p['nome']} {p['versao']} em {dest}"
    # tar (Xenia): extrai numa pasta nova
    if dest.exists() and any(dest.iterdir()):
        return f"{dest} já existe: não mexi"
    import tarfile
    arq = dest.parent / p["arquivo"]
    _baixar(p["url"], arq, p.get("sha256"))
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(arq) as t:
        if hasattr(tarfile, "data_filter"):
            t.extractall(dest, filter="data")
        else:  # pragma: no cover - python antigo
            t.extractall(dest)
    arq.unlink(missing_ok=True)
    return f"instalado: {p['nome']} {p['versao']} em {dest}"


# ------------------------------------------------------------------ mapeamento ---------
def dados_emulador(emu: str, home: Path, tab: dict, prefer_flatpak: bool = False) -> tuple[Path, dict[str, Path]]:
    """Pasta de dados do emulador no Deck ({EMU}) e subpastas que ficam em outro lugar (Lichii: config)."""
    lx = (tab.get(emu) or {}).get("linux") or {}
    cands = [home / d for d in lx.get("dados", [])] or [home / ".local/share" / emu]
    base = next((c for c in cands if c.is_dir()), None)
    if base is None:
        flat = [c for c in cands if "/.var/app/" in c.as_posix()]
        base = flat[0] if (prefer_flatpak and flat) else cands[0]
    sub = {k: home / v for k, v in (lx.get("sub") or {}).items()}
    return base, sub


def caminho_deck(destino: str, roms: Path, base: Path, sub: dict[str, Path]) -> Path:
    """{JOGOS}/psx/X/a.bin -> ~/Emulation/roms/psx/X/a.bin ; {EMU}/config/x -> ~/.config/eden/x (Lichii)."""
    tok, _, resto = destino.partition("/")
    partes = [x for x in resto.split("/") if x]
    if any(x in ("..", ".") for x in partes):
        raise ValueError(f"caminho inválido no manifesto: {destino}")
    if tok == "{JOGOS}":
        return roms.joinpath(*partes)
    if tok == "{EMU}":
        if partes and partes[0] in sub:
            return sub[partes[0]].joinpath(*partes[1:])
        return base.joinpath(*partes)
    raise ValueError(f"destino desconhecido no manifesto: {destino}")


_SEP = r"(?:\\\\|\\|/)"


def reescrever(txt: str, regras: list[dict], roms: Path, base: Path, sub: dict[str, Path]) -> str:
    """Troca caminhos do Windows (D:/x, D:\\x, D:\\\\x em JSON) pelos do Deck, mantendo o resto do caminho."""
    for r in sorted(regras, key=lambda r: -len(r["de"])):
        partes = [x for x in re.split(r"[\\/]+", r["de"]) if x]
        if not partes:
            continue
        pat = re.compile(_SEP.join(re.escape(x) for x in partes) + r"((?:" + _SEP + r"[^\"'\r\n;,=]*)?)", re.IGNORECASE)

        def troca(mm, para=r["para"]):
            cauda = re.sub(r"[\\/]+", "/", mm.group(1)).rstrip("/")
            log = (para + cauda) if cauda else para
            try:
                return caminho_deck(log if "/" in log else log + "/", roms, base, sub).as_posix().rstrip("/")
            except ValueError:
                return mm.group(0)
        txt = pat.sub(troca, txt)
    return txt


# ------------------------------------------------------------------ conferência --------
def sha256_arquivo(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def ler_manifesto(area: Path) -> dict:
    man = json.loads((area / "manifesto.json").read_text("utf-8-sig"))
    if man.get("direcao") != "pc->deck":
        raise ValueError("manifesto.json não é de uma transferência PC -> Deck")
    return man


def conferir(area: Path, man: dict) -> list[dict]:
    """Arquivos da área que faltam ou não batem com o sha256 do manifesto."""
    ruins = []
    for a in man["arquivos"]:
        p = area / "arquivos" / a["rel"]
        if not p.is_file() or p.stat().st_size != a["tamanho"]:
            ruins.append({"rel": a["rel"], "motivo": "falta" if not p.is_file() else "tamanho diferente"})
        elif sha256_arquivo(p) != a["sha256"].lower():
            ruins.append({"rel": a["rel"], "motivo": "sha256 diferente"})
    return ruins


# ------------------------------------------------------------------ instalação ---------
def _backup(alvo: Path, raiz_bk: Path, rel: str) -> Path:
    b = raiz_bk / rel
    b.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(alvo, b)
    return b


def _raiz_de(alvo: Path, raizes: list[Path]) -> Path | None:
    for r in sorted(raizes, key=lambda x: -len(str(x))):
        try:
            alvo.relative_to(r)
            return r
        except ValueError:
            continue
    return None


def receber(gid: str, home=None, destino_teste: Path | None = None, simular: bool = False,
            sem_emulador: bool = False, config_global: bool = False, biblioteca: bool = True,
            flatpak=flatpak_info, get=_get_json) -> dict:
    """Instala no Deck o que o PC deixou na área de recebimento. Devolve o relatório."""
    home = _home(home)
    area = area_de(gid, home, destino_teste)
    man = ler_manifesto(area)
    if man.get("game_id") != gid:
        raise ValueError(f"a área {area} é de outro jogo ({man.get('game_id')})")
    tab = tabela(home, area)
    emu = man.get("emulador") or emu_do_console(man.get("console", ""), tab) or ""
    alvo_home = Path(destino_teste) / "home" if destino_teste else home
    rel = {"game_id": gid, "titulo": man.get("titulo", gid), "console": man.get("console"), "emulador": emu,
           "area": str(area), "teste": bool(destino_teste), "simulacao": simular, "instalados": 0, "iguais": 0,
           "backups": 0, "mantidos": [], "pulados": [], "sobras": [], "emulador_deck": None, "biblioteca": None,
           "avisos": list(man.get("avisos", []))}

    ruins = conferir(area, man)
    if ruins:
        rel["erro"] = f"{len(ruins)} arquivo(s) da área não conferem com o PC (sha256): rode o envio de novo"
        rel["ruins"] = ruins[:20]
        return rel

    # emulador do Deck: se falta, instala o oficial (no teste/simulação só mostra o plano)
    det = emulador_no_deck(emu, home, tab, flatpak) if emu else {"instalado": True}
    rel["emulador_deck"] = det
    if emu and not det.get("instalado") and not sem_emulador:
        plano = plano_instalacao(emu, (man.get("emulador_pc") or {}).get("versao"), home, tab, get=get)
        rel["emulador_plano"] = plano
        rel["emulador_instalacao"] = instalar_emulador(plano, simular=simular or bool(destino_teste))
    prefer_flat = det.get("tipo") == "flatpak" or (rel.get("emulador_plano") or {}).get("acao") == "flatpak"
    if destino_teste:  # pastas "reais" dentro da pasta de teste
        b_real, s_real = dados_emulador(emu, home, tab, prefer_flat)
        base = alvo_home / b_real.relative_to(home)
        sub = {k: alvo_home / v.relative_to(home) for k, v in s_real.items()}
    else:
        base, sub = dados_emulador(emu, home, tab, prefer_flat)
    roms = alvo_home / "Emulation/roms"
    rel["destinos"] = {"jogos": str(roms), "dados_emulador": str(base), **{f"dados_{k}": str(v) for k, v in sub.items()}}

    stamp = time.strftime("%Y%m%d-%H%M%S")
    bk_nome = f"_backup-deck-commander/{stamp}-{gid}"
    raiz_jogos_bk = (Path(destino_teste) if destino_teste else _data_dir(home)) / bk_nome / "roms"
    raizes = [base, *sub.values()]

    # Ryujinx: índice de saves (imkvdb.arc) diferente no Deck => não mistura saves (como no sentido Deck -> PC)
    pular_ryu = False
    if emu == "ryujinx":
        idx = base / "bis/system/save/8000000000000000/0/imkvdb.arc"
        nosso = next((a for a in man["arquivos"]
                      if a["destino"] == "{EMU}/bis/system/save/8000000000000000/0/imkvdb.arc"), None)
        pular_ryu = bool(nosso and idx.is_file() and sha256_arquivo(idx) != nosso["sha256"].lower())

    for a in man["arquivos"]:
        destino = a["destino"]
        alvo = caminho_deck(destino, roms, base, sub)
        relp = destino.split("/", 1)[1]
        if pular_ryu and (relp.startswith("bis/system/save/8000000000000000/") or relp.startswith("bis/user/save/")):
            rel["pulados"].append(f"{relp} (o Ryujinx do Deck já tem outros saves; índice imkvdb.arc diferente)")
            continue
        if emu == "retroarch" and relp == "retroarch.cfg":
            rel["pulados"].append("retroarch.cfg (config global do Windows; o do Deck fica)")
            continue
        origem = area / "arquivos" / a["rel"]
        dados = None
        if a.get("reescrever") or (Path(destino).suffix.lower() in TEXTO_EXTS and a["categoria"].startswith("config")):
            txt = origem.read_text("utf-8", errors="surrogateescape")
            novo = reescrever(txt, man.get("reescrever", []), roms, base, sub)
            for ln in novo.splitlines():
                if re.search(r"\b[A-Za-z]:[\\/]", ln):
                    rel["sobras"].append(f"{relp}: {ln.strip()[:160]}")
            dados = novo.encode("utf-8", errors="surrogateescape")
        if alvo.exists():
            igual = (alvo.read_bytes() == dados) if dados is not None else (sha256_arquivo(alvo) == a["sha256"].lower())
            if igual:
                rel["iguais"] += 1
                continue
            if a["categoria"] == "config-global" and not config_global:
                rel["mantidos"].append(f"{relp} (config global do Deck mantida; --config-global para trocar)")
                continue
            if not simular:
                r = _raiz_de(alvo, raizes)
                if r is not None:
                    _backup(alvo, r / bk_nome, alvo.relative_to(r).as_posix())
                else:
                    _backup(alvo, raiz_jogos_bk, alvo.relative_to(roms).as_posix())
            rel["backups"] += 1
        if not simular:
            alvo.parent.mkdir(parents=True, exist_ok=True)
            tmp = alvo.with_name(alvo.name + ".dc-recebendo")
            if dados is not None:
                tmp.write_bytes(dados)
            else:
                shutil.copyfile(origem, tmp)
            os.replace(tmp, alvo)
        rel["instalados"] += 1
    rel["backup_em"] = [str(r / bk_nome) for r in raizes] + [str(raiz_jogos_bk)]

    if biblioteca and not destino_teste and not simular:
        rel["biblioteca"] = _biblioteca()
    elif destino_teste:
        rel["biblioteca"] = "teste: o jogo NÃO entrou na biblioteca do Steam"
    return rel


def _biblioteca() -> str:
    """Mesma função do /sync: escaneia ~/Emulation/roms e cria os atalhos que faltam no Steam."""
    try:
        from dc import syncer
        from dc.lock import OperationLock
        from dc.paths import get_paths
        from dc.store import Store
    except ImportError as ex:
        return f"não pus na biblioteca agora ({ex}); mande /sync"
    paths = get_paths().ensure()
    store = Store(paths.db)
    op = store.enqueue("receber", {})
    store.claim(op)
    try:
        with OperationLock(paths.lock, op, "receber", is_running=store.is_running):
            nomes = syncer.add_to_steam(paths, store, op)
        store.finish(op, True, result={"shortcuts": len(nomes)})
        return ("na biblioteca: " + ", ".join(nomes)) if nomes else "já estava na biblioteca"
    except Exception as ex:  # noqa: BLE001 - jogo já está no lugar; o /sync resolve depois
        store.finish(op, False, error=str(ex))
        return f"não pus na biblioteca agora ({ex}); mande /sync"


def texto_relatorio(r: dict) -> str:
    if r.get("erro"):
        return "ERRO: " + r["erro"] + "\n" + "\n".join(f"  {x['rel']}: {x['motivo']}" for x in r.get("ruins", []))
    pre = "[TESTE] " if r["teste"] else ("[SIMULAÇÃO] " if r["simulacao"] else "")
    ls = [f"{pre}{r['titulo']} ({r['console']}, emulador {r['emulador']}): {r['instalados']} instalado(s), "
          f"{r['iguais']} já iguais, {r['backups']} backup(s)",
          f"jogo em: {r['destinos']['jogos']}", f"dados do emulador em: {r['destinos']['dados_emulador']}"]
    d = r.get("emulador_deck") or {}
    if d.get("instalado") and d.get("onde"):
        ls.append(f"emulador no Deck: {d['onde']}" + (f" ({d['versao']})" if d.get("versao") else ""))
    if r.get("emulador_instalacao"):
        ls.append("emulador: " + r["emulador_instalacao"])
    ls += [f"mantido: {x}" for x in r["mantidos"][:10]]
    ls += [f"pulado: {x}" for x in r["pulados"][:10]]
    if r["sobras"]:
        ls.append("caminhos do Windows que sobraram na config (ajuste no emulador se precisar):")
        ls += [f"  {x}" for x in r["sobras"][:10]]
    if r.get("biblioteca"):
        ls.append("biblioteca: " + r["biblioteca"])
    ls += [f"aviso: {x}" for x in r["avisos"][:6]]
    ls.append("Nada foi apagado no PC; arquivos do Deck que mudaram têm cópia em _backup-deck-commander.")
    return "\n".join(ls)


# ------------------------------------------------------------------ pedido pelo Deck ---
def _norm(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().casefold()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def achar_jogo_pc(consulta: str, home=None) -> list[dict]:
    jogos = ler_jogos_pc(home).get("jogos") or []
    q = _norm(consulta)
    exato = [j for j in jogos if j.get("id") == consulta.strip()]
    if exato or not q:
        return exato
    return [j for j in jogos if all(t in _norm(j.get("titulo", "") + " " + j.get("id", "")) for t in q.split())]


def gb(n: int) -> str:
    return f"{n / 1e9:.2f} GB" if n >= 1e8 else f"{n / 1e6:.1f} MB"


def texto_emulador_lado_pc(emu: str, versao_deck: str | None, home=None) -> str | None:
    """Deck -> PC: se a lista do PC diz que falta o emulador, avisa que o PC vai instalá-lo."""
    d = ler_jogos_pc(home)
    if not emu or "emuladores_pc" not in d:
        return None
    if emu in (d.get("emuladores_pc") or {}):
        return None
    tab = tabela(home)
    e = tab.get(emu) or {}
    if not e:
        return f"o PC não tem o emulador {emu} e ele não tem origem oficial conhecida: o jogo vai, o emulador não"
    if (e.get("windows") or {}).get("manual"):
        return f"o PC não tem o {e.get('nome', emu)}: instale pela página oficial ({e.get('pagina')}) — o jogo vai"
    v = f"versão {versao_deck}, a mesma do Deck" if versao_deck else "mesma build do Deck se achar, senão a estável mais recente"
    return f"o emulador {e.get('nome', emu)} vai ser instalado no PC ({v}, da página oficial: {e.get('pagina')})"


def texto_jogo_pc(j: dict, home=None, flatpak=flatpak_info) -> str:
    ls = [f"{j.get('titulo')} ({j.get('console')}, emulador {j.get('emulador') or '?'}) — {gb(j.get('tamanho', 0))} "
          f"em {j.get('arquivos', 0)} arquivos (no PC)"]
    for c, r in (j.get("resumo") or {}).items():
        ls.append(f"• {c}: {r.get('arquivos', 0)} arquivos, {gb(r.get('bytes', 0))}")
    emu = j.get("emulador")
    if emu:
        det = emulador_no_deck(emu, home, None, flatpak)
        if det["instalado"]:
            ls.append(f"emulador no Deck: {det['nome']} ({det['onde']}) — os dados do PC vão para ele")
        else:
            tab = tabela(home)
            lx = (tab.get(emu) or {}).get("linux") or {}
            vpc = ((ler_jogos_pc(home).get("emuladores_pc") or {}).get(emu) or {}).get("versao")
            if lx.get("flatpak"):
                ls.append(f"o emulador {det['nome']} vai ser instalado no Deck (Flatpak {lx['flatpak']} do Flathub, "
                          "página oficial)")
            elif lx.get("asset"):
                v = f"versão {vpc}, a mesma do PC" if vpc else "a estável mais recente"
                ls.append(f"o emulador {det['nome']} vai ser instalado no Deck ({v}, da página oficial: {det['pagina']})")
            else:
                ls.append(f"⚠️ o Deck não tem o {det['nome']} e não há instalação automática: {det['pagina']}")
    ls.append("Configuração global do Deck é mantida; saves, config do jogo, mods e keys/BIOS do PC entram "
              "(com backup do que já existir).")
    return "\n".join(ls)


def comando_trazer(bot, args: list[str]) -> str:
    """/trazer — lista os jogos do PC; /trazer <jogo> mostra o que vem e o botão; /trazer <jogo> enviar põe na fila."""
    from . import transferir as tr
    d = ler_jogos_pc()
    jogos = d.get("jogos") or []
    if not args or args[0].lower() == "lista":
        if not jogos:
            return ("Ainda não tenho a lista de jogos do PC. Ela chega sozinha quando o PC liga "
                    "(tarefa DeckCommander Transferencias).")
        ls = [f"• {j['titulo']} ({j['console']}, {gb(j.get('tamanho', 0))}) → {j['id']}" for j in jogos[:40]]
        return ("Jogos do PC que podem vir para o Deck:\n" + "\n".join(ls) +
                "\n\n/trazer <jogo> — mostra o que vem (emulador, saves, config) e pergunta antes")
    if args[0].lower() == "fila":
        f = [e for e in tr.ler_fila() if e.get("direcao") == "pc->deck"][-10:]
        return "\n".join(f"• {e['titulo']}: {e['status']}" for e in reversed(f)) or "Nada pedido do PC."
    enviar = args[-1].lower() == "enviar"
    if enviar:
        args = args[:-1]
    hits = achar_jogo_pc(" ".join(args))
    if not hits:
        return "Não achei esse jogo na lista do PC. /trazer mostra a lista."
    if len(hits) > 1:
        return "Achei mais de um:\n" + "\n".join(f"• {j['titulo']} ({j['console']}) → {j['id']}" for j in hits[:10])
    j = hits[0]
    if enviar:
        e = tr.enfileirar(j["id"], j.get("titulo", j["id"]), direcao="pc->deck")
        return (f"📥 {e['titulo']} na fila para vir do PC.{tr._acordar_pc(bot)} O PC envia em até 5 min, confere "
                "cada arquivo no Deck e instala; aviso aqui quando acabar. (/trazer fila)")
    bot.next_buttons = [("Trazer pro Deck", f"/trazer {j['id']} enviar")]
    return (texto_jogo_pc(j) + "\n\nTrazer do PC agora? O PC acorda e envia sozinho: confere cada arquivo (sha256), "
            "retoma se cair, faz backup do que já existir no Deck; nada é apagado no PC.")


# ------------------------------------------------------------------ linha de comando ---
def _opt(argv: list[str], nome: str) -> str | None:
    if nome in argv:
        i = argv.index(nome)
        if i + 1 < len(argv):
            return argv[i + 1]
    return None


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    home = _home()
    teste = _expandir(_opt(argv, "--destino-teste"), home)
    if teste and teste.resolve() in (home.resolve(), (home / "Emulation").resolve(), (home / "Emulation/roms").resolve()):
        print("ERRO: --destino-teste precisa ser uma pasta só de teste (ex.: ~/dc-teste-receber)", file=sys.stderr)
        return 2
    cmd = argv[0] if argv else ""
    if cmd == "emuladores":  # detecção (só leitura)
        tab = tabela(home, area_de("x", home, teste).parent if teste else None)
        r = detectar_todos(home, tab)
        if "--json" in argv:
            print(json.dumps(r, ensure_ascii=False))
        else:
            for d in r:
                print(f"{d['emulador']:12} {'SIM' if d['instalado'] else 'não':4} {d['tipo'] or '':9} "
                      f"{d['onde'] or ''}" + (f"  ({d['versao']})" if d.get("versao") else ""))
        return 0
    if cmd == "emulador-plano" and len(argv) >= 2:  # o que instalaria (consulta a API oficial; não baixa)
        tab = tabela(home, area_de("x", home, teste).parent if teste else None)
        p = plano_instalacao(argv[1], _opt(argv, "--versao"), home, tab)
        print(json.dumps(p, ensure_ascii=False) if "--json" in argv else texto_plano(p))
        return 0
    if cmd in ("receber", "conferir") and len(argv) >= 2:
        gid = argv[1]
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", gid):
            print(f"ERRO: id inválido: {gid}", file=sys.stderr)
            return 2
        try:
            if cmd == "conferir":
                area = area_de(gid, home, teste)
                ruins = conferir(area, ler_manifesto(area))
                print(json.dumps(ruins, ensure_ascii=False))
                return 0 if not ruins else 1
            r = receber(gid, home, teste, simular="--simular" in argv, sem_emulador="--sem-emulador" in argv,
                        config_global="--config-global" in argv, biblioteca="--sem-biblioteca" not in argv)
        except (OSError, ValueError) as ex:
            print(f"ERRO: {ex}", file=sys.stderr)
            return 1
        print(json.dumps(r, ensure_ascii=False) if "--json" in argv else texto_relatorio(r))
        return 1 if r.get("erro") else 0
    print("uso: python3 -m dc.transferir receber <id> [--destino-teste ~/pasta] [--simular] [--sem-emulador] "
          "[--config-global] | conferir <id> | emuladores [--json] | emulador-plano <emu> [--versao X]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
