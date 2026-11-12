"""Família (dois Decks pareados pela Tailscale): o que liga o módulo `familia` ao Deck de verdade.

- Cada Deck PUBLICA um catálogo (texto): jogos + magnet de onde vieram + lista dos arquivos de tradução (mod PT-BR,
  patch .bps), mais o glossário de franquia. Nenhum arquivo de jogo sai do Deck.
- O outro Deck LÊ esse catálogo por SSH, PUXA um jogo: o magnet entra na fila de downloads DELE (qBittorrent) e o
  pacote de tradução vem por SSH (só os arquivos permitidos por `familia.filtrar_pacote`). Quando o download entra na
  biblioteca, o pacote é aplicado (mods copiados; patch de ROM aplicado com o próprio `dc.patches`).
- O bot avisa quando o Deck do par fica online.
Configuração em config/familia.json: {"meu_nome", "par": {"nome", "alvo": "deck@<ip tailscale>", "chave"}}.
"""
from __future__ import annotations

import io
import json
import os
import shlex
import shutil
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path

from . import familia
from .arquivo_json import gravar as _save
from .arquivo_json import ler as _load
from .paths import Paths

CHAVE_PADRAO = str(Path.home() / ".ssh" / "deck_commander_familia")


def _dir(paths: Paths) -> Path:
    d = paths.data / "familia"
    d.mkdir(parents=True, exist_ok=True)
    return d



def config(paths: Paths) -> dict:
    return _load(paths.config / "familia.json", {})


def salvar_config(paths: Paths, cfg: dict) -> None:
    _save(paths.config / "familia.json", cfg)


# ------------------------------------------------------------------------------------------- chave SSH
def minha_chave_publica(paths: Paths, run=subprocess.run) -> str:
    """Chave pública deste Deck (criada na 1ª vez) para o dono do outro Deck autorizar com /familia autorizar."""
    priv = Path(CHAVE_PADRAO)
    if not priv.exists():
        priv.parent.mkdir(parents=True, exist_ok=True)
        run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "deck-commander-familia", "-f", str(priv)],
            capture_output=True, text=True, timeout=30)
    pub = priv.with_suffix(".pub")
    return pub.read_text("utf-8").strip() if pub.exists() else ""


def autorizar(chave_publica: str) -> str:
    """Autoriza o Deck do par a LER o catálogo e os pacotes deste Deck (linha no authorized_keys)."""
    k = chave_publica.strip()
    if not k.startswith("ssh-ed25519 ") or len(k.split()) < 2:
        raise ValueError("isso não parece uma chave (começa com ssh-ed25519)")
    ak = Path.home() / ".ssh" / "authorized_keys"
    ak.parent.mkdir(parents=True, exist_ok=True)
    atual = ak.read_text("utf-8") if ak.exists() else ""
    if k.split()[1] in atual:
        return "Esse Deck já estava autorizado."
    with open(ak, "a", encoding="utf-8") as f:
        f.write(("" if atual.endswith("\n") or not atual else "\n") + k + "\n")
    os.chmod(ak, 0o600)
    return "Deck do par autorizado. Peça para ele mandar /familia atualizar."


# ------------------------------------------------------------------------------------------- catálogo
def _magnets(paths: Paths, qbt) -> dict:
    """Magnet de cada torrent (o qBittorrent gera mesmo para .torrent); guardado porque a lista pode ser limpa."""
    cache = _dir(paths) / "magnets.json"
    m = _load(cache, {})
    try:
        for t in qbt.torrents():
            if t.get("magnet_uri"):
                m[t["hash"]] = t["magnet_uri"]
        _save(cache, m)
    except Exception:  # noqa: BLE001 — qBittorrent desligado: usa o que já tinha
        pass
    return m


def _pacotes(paths: Paths, lm: dict) -> dict:
    """Arquivos de tradução de cada jogo: mod PT-BR do Switch (pasta do Ryujinx) e patch .bps dos retrô."""
    from .dedup import base_title_id
    from .traducao import run, switch
    out: dict[str, list[str]] = {}
    for g, e in lm.items():
        if e.get("console") == "switch":
            tid = base_title_id(Path(e.get("rom", "")).name)
            if tid:
                d = switch.mod_target(tid)
                if d.exists():
                    out[g] = [str(f) for f in d.rglob("*") if f.is_file()]
    for j in run.all_jobs(paths):
        pt = (j.get("result") or {}).get("patch")
        if j.get("status") == "concluido" and pt and Path(pt).exists():
            out.setdefault(j["game_id"], []).append(pt)
    return out


def publicar(paths: Paths, qbt) -> dict:
    """Grava data/familia/meu-catalogo.json (lido pelo Deck do par). Só texto; arquivos de jogo nunca entram."""
    from . import remove, syncer
    from .traducao import ia
    lm = remove.effective_map(paths)
    ing = syncer._state(paths).get("ingested", {})
    pac = {g: familia.filtrar_pacote(fs)[0] for g, fs in _pacotes(paths, lm).items()}
    cat = familia.montar_catalogo(lm, ing, _magnets(paths, qbt), pac)
    g = ia.glossary_path(paths)
    dados = {"de": config(paths).get("meu_nome") or "Deck", "em": datetime.now(timezone.utc).isoformat(),
             "jogos": cat, "glossario": str(g) if g.exists() else None}
    _save(_dir(paths) / "meu-catalogo.json", dados)
    return dados


def _par(paths: Paths) -> dict:
    p = config(paths).get("par") or {}
    if not p.get("alvo"):
        raise ValueError("par não configurado: /familia par <nome> <deck@ip-tailscale>")
    p.setdefault("chave", CHAVE_PADRAO)
    p.setdefault("nome", "par")
    return p


def online(paths: Paths, run=subprocess.run) -> bool:
    try:
        p = _par(paths)
    except ValueError:
        return False
    return familia.par_online(p["alvo"], p["chave"], run=run)


def catalogo_do_par(paths: Paths, run=subprocess.run) -> dict:
    """Busca o catálogo do par por SSH (guarda uma cópia para mostrar mesmo com ele offline)."""
    p = _par(paths)
    r = run(familia.ssh_base(p["alvo"], p["chave"]) + ["cat", ".local/share/deck-commander/familia/meu-catalogo.json"],
            capture_output=True, text=True, timeout=30)
    if r.returncode != 0 or not r.stdout.strip():
        raise RuntimeError(f"não consegui ler o catálogo de {p['nome']} (ele está online e autorizou este Deck?)")
    dados = json.loads(r.stdout)
    _save(_dir(paths) / "catalogo-do-par.json", dados)
    return dados


def catalogo_guardado(paths: Paths) -> dict:
    return _load(_dir(paths) / "catalogo-do-par.json", {"jogos": []})


# ------------------------------------------------------------------------------------------- puxar
def _rel_home(caminho: str) -> str | None:
    """Caminho relativo ao /home/deck do par (pacote espelha o home dele); None se estiver fora."""
    pre = "/home/deck/"
    return caminho[len(pre):] if caminho.startswith(pre) else None


def puxar(paths: Paths, qbt, gid: str, run=subprocess.run) -> str:
    """Puxa do par: magnet na fila de downloads DESTE Deck + pacote de tradução por SSH (tar), só arquivos permitidos."""
    from . import syncer
    p = _par(paths)
    cat = catalogo_do_par(paths, run=run)
    it = next((x for x in cat.get("jogos", []) if x["gid"] == gid), None)
    if not it:
        raise ValueError("esse jogo não está no catálogo do par")
    partes = []
    if it.get("magnet"):
        cons = it.get("console") or "auto"
        qbt.add(it["magnet"], cons, str(Path(syncer._cfg(paths)["downloads_root"]) / cons), extra_tags="dc-familia")
        partes.append("download na fila")
    rels = [r for r in (_rel_home(c) for c in it.get("pacote", []) + ([cat["glossario"]] if cat.get("glossario") else []))
            if r and not any(r.lower().endswith(e) for e in familia.EXT_JOGO)]
    if rels:
        dest = _dir(paths) / "pacotes" / gid
        r = run(familia.ssh_base(p["alvo"], p["chave"]) + ["tar", "-c", "-C", "/home/deck", "--", *map(shlex.quote, rels)],  # o ssh junta tudo numa linha de shell: espaço no nome quebrava
                capture_output=True, timeout=600)
        if r.returncode != 0:
            raise RuntimeError("não consegui copiar o pacote de tradução do par")
        shutil.rmtree(dest, ignore_errors=True)
        dest.mkdir(parents=True)
        with tarfile.open(fileobj=io.BytesIO(r.stdout)) as tf:
            for m in tf.getmembers():  # extração segura: só arquivos comuns, sem caminho absoluto nem ".."
                if m.isfile() and not m.name.startswith("/") and ".." not in Path(m.name).parts:
                    tf.extract(m, dest, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
        partes.append(f"tradução recebida ({len(rels)} arquivo(s))")
    familia.registrar_pedido(_dir(paths) / "pedidos.json", it, p["nome"])
    return f"{it['titulo']}: " + " + ".join(partes or ["nada para puxar"]) + "."


def aplicar_prontos(paths: Paths) -> list[str]:
    """Pedido cujo jogo já entrou na biblioteca: aplica o pacote (mods/glossário; patch .bps na ROM). Devolve avisos."""
    from . import syncer
    from .traducao import glossario_franquia as gf
    from .traducao import ia
    est = _dir(paths) / "pedidos.json"
    ing = syncer._state(paths).get("ingested", {})
    avisos = []
    for pd in familia.pedidos(est):
        if pd.get("status") != "baixando":
            continue
        if pd.get("hash") and pd["hash"] not in ing and pd.get("magnet"):
            continue  # ainda baixando
        pac = _dir(paths) / "pacotes" / pd["gid"]
        feitos = []
        if pac.exists():
            gl = pac / ".config/deck-commander/glossary.json"
            if gl.exists():  # glossário: junta (não troca o seu)
                meu = gf.carregar(ia.glossary_path(paths))
                for ch, termos in gf.carregar(gl).items():
                    meu = gf.juntar(meu, ch, termos)
                gf.salvar(ia.glossary_path(paths), meu)
                gl.unlink()
            for bps in list(pac.rglob("*.bps")) + list(pac.rglob("*.ips")) + list(pac.rglob("*.ups")):
                rom = _rom_do_pedido(paths, pd, ing)
                if rom:
                    from . import patches
                    try:
                        feitos.append(str(patches.apply_file(rom, bps)))
                    except Exception as e:  # noqa: BLE001  patch ruim não pode travar os outros pedidos
                        avisos.append(f"⚠️ patch {bps.name} não aplicou em {pd['titulo']}: {e}")
                bps.unlink()
            feitos += familia.aplicar_pacote(pac, Path.home())
        familia.marcar(est, pd["gid"], "pronto", f"{len(feitos)} arquivo(s) de tradução aplicados")
        avisos.append(f"👪 {pd['titulo']} (de {pd.get('de', 'par')}) chegou" +
                      (" já traduzido." if feitos else "." ) + " Rode /sync se ainda não apareceu.")
    return avisos


def _rom_do_pedido(paths: Paths, pd: dict, ing: dict) -> Path | None:
    exts = (".gba", ".sfc", ".smc", ".nes", ".gb", ".gbc", ".n64", ".z64", ".nds", ".bin", ".iso")
    for f in (ing.get(pd.get("hash"), {}) or {}).get("files", []):
        if f.lower().endswith(exts) and Path(f).exists():
            return Path(f)
    return None


# ------------------------------------------------------------------------------------------- bot
def comando(bot, args: list[str]) -> str:
    """/familia [status|par <nome> <deck@ip>|nome <seu nome>|chave|autorizar <chave>|atualizar|jogos|puxar <jogo>]"""
    paths = bot.paths
    sub = args[0].lower() if args else "status"
    try:
        if sub == "par" and len(args) >= 3:
            cfg = config(paths)
            cfg["par"] = {"nome": args[1], "alvo": args[2], "chave": CHAVE_PADRAO}
            salvar_config(paths, cfg)
            return f"Par: {args[1]} ({args[2]}). Agora mande /familia chave e peça para ele autorizar."
        if sub == "nome" and len(args) >= 2:
            cfg = config(paths)
            cfg["meu_nome"] = " ".join(args[1:])
            salvar_config(paths, cfg)
            return "Nome guardado."
        if sub == "chave":
            return ("Mande esta linha para o dono do outro Deck colar no bot DELE com /familia autorizar:\n\n"
                    + minha_chave_publica(paths))
        if sub == "autorizar" and len(args) >= 2:
            return autorizar(" ".join(args[1:]))
        if sub == "atualizar":
            publicar(paths, bot.qbt)
            n = len(catalogo_do_par(paths).get("jogos", []))
            return f"Catálogo atualizado: {n} jogo(s) no Deck do par."
        if sub == "jogos":
            js = catalogo_guardado(paths).get("jogos", [])
            if not js:
                return "Catálogo do par vazio. Mande /familia atualizar com o Deck dele ligado."
            return "\n".join(f"• {j['titulo']} ({j['console']})" + (" 🇧🇷" if j.get("tem_traducao") else "")
                             for j in js[:40]) + "\n\nPuxar: /familia puxar <nome do jogo>"
        if sub == "puxar" and len(args) >= 2:
            q = " ".join(args[1:]).lower()
            js = catalogo_guardado(paths).get("jogos", [])
            hit = [j for j in js if q == j["gid"] or q in j["titulo"].lower()]
            if len(hit) != 1:
                return "Não achei um só jogo com esse nome (/familia jogos)." if not hit else \
                    "Achei mais de um:\n" + "\n".join(f"• {j['titulo']}" for j in hit[:10])
            return "👪 " + puxar(paths, bot.qbt, hit[0]["gid"])
        par = config(paths).get("par") or {}
        if not par:
            return ("Família não configurada.\n1) /familia par <nome> <deck@ip-tailscale-do-outro-deck>\n"
                    "2) /familia chave → mande para ele, que cola com /familia autorizar <chave>\n"
                    "3) /familia atualizar · /familia jogos · /familia puxar <jogo>")
        return f"👪 {par.get('nome')}: {'🟢 online' if online(paths) else '⚫ offline'} · " \
               f"{len(catalogo_guardado(paths).get('jogos', []))} jogo(s) no catálogo dele."
    except (ValueError, RuntimeError) as e:
        return f"👪 {e}"


def avisar_presenca(bot) -> None:
    """No laço do bot (a cada ~5 min): publica o catálogo, aplica pedidos que chegaram e avisa se o par ficou online."""
    import time
    paths = bot.paths
    if not config(paths).get("par"):
        return
    est = _dir(paths) / "presenca.json"
    st = _load(est, {})
    if time.time() - st.get("checado", 0) < 300:
        return
    st["checado"] = time.time()
    try:
        publicar(paths, bot.qbt)
    except Exception:  # noqa: BLE001
        pass
    chat = bot.cfg.get("notify_chat")
    for aviso in aplicar_prontos(paths):
        if chat:
            bot.send(chat, aviso)
    agora = online(paths)
    if agora and not st.get("online") and chat:
        nome = (config(paths).get("par") or {}).get("nome", "par")
        bot.send(chat, f"🟢 O Deck de {nome} está online. Quer algo dele? /familia jogos",
                 buttons=[("Ver jogos dele", "/familia atualizar")])
    st["online"] = agora
    _save(est, st)
