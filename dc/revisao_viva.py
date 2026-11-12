"""Revisão AO VIVO no Deck: confere, no aparelho de verdade, cada coisa que já funcionou — para nada que funcionava
parar sem a gente ver. Pedido do usuário em 11/11/2026 ("o que tava funcionando parou de funcionar, não confio").
Roda sozinha depois de toda implantação (tools/implantar.py).

    python3 -m dc.revisao_viva          -> uma linha por item (OK/FALHA) e código de saída 1 se algo falhou

Cada item diz QUAL falha real ele vigia (docs/LICOES.md).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

H = Path.home()
CHECAGENS: list[tuple[str, Callable[[], tuple[bool, str]]]] = []


def item(nome: str):
    def reg(f):
        CHECAGENS.append((nome, f))
        return f
    return reg


def _ativo(unidade: str) -> bool:
    r = subprocess.run(["systemctl", "--user", "is-active", unidade], capture_output=True, text=True)
    return r.stdout.strip() == "active"


@item("serviços do Deck Commander")
def servicos():
    fora = [u for u in ("deck-commander-bot", "deck-commander-power", "deck-commander-ollama",
                        "deck-commander-qbittorrent") if not _ativo(u)]
    return not fora, "parados: " + ", ".join(fora) if fora else "bot, energia, IA e downloads rodando"


@item("painel do Decky = versão implantada")
def plugin():
    import hashlib
    inst = next(iter(H.glob("homebrew/plugins/deck-commander/dist/index.js")), None)
    repo = H / "deck-commander/decky-plugin/dist/index.js"
    if not inst or not repo.exists():
        return False, "plugin não instalado"
    igual = hashlib.sha1(inst.read_bytes()).digest() == hashlib.sha1(repo.read_bytes()).digest()
    return igual, "em dia" if igual else "o Decky está com uma versão velha do painel"


@item("Steam respondendo (porta do Decky)")
def steam_viva():
    from . import steam_cdp
    try:
        return steam_cdp.steam("1+1") == 2, "ok"
    except Exception as e:  # noqa: BLE001
        return False, f"sem resposta ({e})"


@item("emuladores com as teclas dos botões de trás (F9–F12)")
def emuladores():
    """Falha 0.8: F13–F16 não chegavam (XF86Tools); turbo segurando em vez de liga/desliga."""
    from . import retro as RT
    ruins = []
    # PCSX2 e Dolphin não voltam no tempo: não têm F11
    teclas = {"RetroArch": ("f9", "f10", "f11", "f12"), "DuckStation": ("f9", "f10", "f11", "f12"),
              "PCSX2": ("keyboard/f9", "keyboard/f10", "keyboard/f12"), "Dolphin": ("`f9`", "`f10`", "`f12`")}
    for nome, rel in RT.ARQUIVOS.items():
        p = H / rel
        if not p.exists():
            continue
        t = p.read_text("utf-8", "replace").lower()
        falta = [k for k in teclas[nome] if k not in t]
        if falta:
            ruins.append(f"{nome} sem {', '.join(falta)}")
    ds = H / RT.ARQUIVOS["DuckStation"]
    if ds.exists() and "togglefastforward = keyboard/f12" not in ds.read_text("utf-8", "replace").lower():
        ruins.append("DuckStation sem turbo liga/desliga no F12")
    return not ruins, "; ".join(ruins) if ruins else "RetroArch, DuckStation, PCSX2 e Dolphin ok"


@item("todo jogo retrô com os botões de trás")
def botoes():
    """Falha real 11/11/2026: a cópia PT-BR do Castlevania (atalho novo) ficou sem L4/R4/L5/R5."""
    from . import retro as RT, retro_hacks as R, transferir, vdf
    if not RT.estado(H)["aplicado"]:
        return True, "retrô ainda não ligado no painel"
    faltam = []
    jogos = RT.jogos_dos_emuladores(H, transferir.carregar_mapa())
    for conta in RT._contas(H):
        base = H / ".local/share/Steam/steamapps/common/Steam Controller Configs" / conta / "config"
        cs_arq = base / "configset_controller_neptune.vdf"
        cs = vdf.load_text(cs_arq.read_text("utf-8"))["controller_config"] if cs_arq.exists() else {}
        for nome, _a in jogos:
            arq = base / nome.lower() / "controller_neptune.vdf"
            if not (arq.exists() and R.tem_botoes_de_tras(arq.read_text("utf-8", "replace"))) or \
                    cs.get(nome.lower()) != {"autosave": "1"}:
                faltam.append(nome)
    if not (H / ".local/share/Steam/controller_base/templates" / RT.MODELO).exists():
        faltam.append("(modelo Deck Commander Retro sumiu)")
    return not faltam, ("sem botões: " + ", ".join(faltam[:5])) if faltam else f"{len(jogos)} jogo(s) ok"


@item("DuckStation abre sem a camada que segurava em 60%")
def duckstation_wsi():
    """Falha 0.8: ENABLE_GAMESCOPE_WSI segurava o PS1 PAL em 30 FPS (60%)."""
    from . import launch
    cmd = launch.sem_wsi_do_gamescope(["/x/DuckStation-x64.AppImage", "-batch", "--", "jogo.cue"])
    return "ENABLE_GAMESCOPE_WSI=0" in " ".join(cmd), "ok"


@item("biblioteca: todo jogo aponta para um arquivo que existe")
def biblioteca():
    from . import transferir
    sumiu = []
    for gid, e in transferir.carregar_mapa().items():
        rom = e.get("rom")
        if rom and e.get("console") not in ("pc", "steam") and not Path(rom).exists():
            sumiu.append(gid)
    return not sumiu, ("arquivo sumiu: " + ", ".join(sumiu[:5])) if sumiu else "ok"


@item("Zelda TotK abre em português (oficial) e com a dublagem instalada")
def zelda():
    from . import quality
    from .paths import get_paths
    gid = "switch-the-legend-of-zelda-tears-of-the-kingdom"
    from . import transferir
    if gid not in transferir.carregar_mapa():
        return True, "jogo não está no Deck"
    idioma = quality.get_language(get_paths(), gid)
    dub = H / ".config/Ryujinx/mods/contents/0100f2c0115b6000/Dublagem PT-BR (Deck Commander)/romfs"
    n = sum(1 for _ in dub.rglob("*.bwav")) if dub.exists() else 0
    return idioma == "BrazilianPortuguese", f"idioma ao abrir: {idioma}; {n} fala(s) dublada(s)"


@item("Castlevania PT-BR com acentos e menus")
def castlevania():
    import struct
    pasta = H / "Emulation/roms/psx/Castlevania - Symphony of the Night PSX (PAL)/c-sotn_pal"
    pt = pasta / "Castlevania - Symphony of the Night PSX (PAL) (PT-BR).bin"
    if not pt.exists():
        return True, "sem cópia PT-BR"
    from .traducao import sotn_falas_fonte as F
    from .traducao.psx_disco import Disco
    d, o = Disco(pt), Disco(pasta / "Castlevania - Symphony of the Night PSX (PAL).bin")
    laco = struct.unpack_from("<I", d.ler("DRA.BIN"), 0x80106CDC - F.DRA_BASE)[0] == 0x2F220019
    fonte = d.ler("BIN/F_GAME.BIN") != o.ler("BIN/F_GAME.BIN")
    botoes = d.ler("ST/SEL/F_SEL.BIN") != o.ler("ST/SEL/F_SEL.BIN")
    ok = laco and fonte and botoes
    return ok, "ok" if ok else f"acento nas falas={laco}, fonte 8x8={fonte}, botões da tela de arquivos={botoes}"


@item("IA de tradução respondendo")
def ia():
    import urllib.request
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=5) as r:
            n = len(json.load(r).get("models", []))
        return n > 0, f"{n} modelo(s)"
    except OSError as e:
        return False, f"Ollama do Deck sem resposta ({e})"


@item("Tailscale (netplay, família, PC)")
def tailscale():
    ts = shutil.which("tailscale") or "/opt/tailscale/tailscale"
    r = subprocess.run([ts, "ip", "-4"], capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip().startswith("100."), r.stdout.strip() or r.stderr.strip()[:80]


@item("protetor de tela (arte dos seus jogos)")
def protetor():
    from . import protetor as P
    pasta = H / ".steam/root/config/uioverrides/screensavers" / P.NOME
    imgs = len(list((pasta / "img").glob("*"))) if (pasta / "img").exists() else 0
    return (pasta / "index.html").exists() and imgs > 0 and " " not in P.NOME, f"{imgs} imagem(ns)"


@item("Spotify (conta e playlists)")
def spotify():
    from . import spotify as S
    from .paths import get_paths
    return S.instalado(get_paths()), "go-librespot instalado" if S.instalado(get_paths()) else "não instalado"


@item("espaço em disco")
def disco():
    u = shutil.disk_usage(H)
    livre = u.free / u.total
    return livre > 0.10, f"{u.free / 2**30:.0f} GB livres ({livre:.0%})"


def rodar() -> list[tuple[str, bool, str]]:
    out = []
    for nome, f in CHECAGENS:
        try:
            ok, det = f()
        except Exception as e:  # noqa: BLE001 — uma checagem quebrada vira FALHA, não derruba as outras
            ok, det = False, f"a checagem quebrou: {type(e).__name__}: {e}"
        out.append((nome, bool(ok), det))
    return out


def main() -> int:
    res = rodar()
    for nome, ok, det in res:
        print(("OK     " if ok else "FALHA  ") + nome + (f" — {det}" if det else ""))
    falhas = sum(1 for _n, ok, _d in res if not ok)
    print(f"REVISAO: {len(res) - falhas}/{len(res)} ok")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
