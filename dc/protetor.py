"""Protetor de tela "Deck Commander": apresentação com a arte (fundo + logo) dos seus jogos, recentes primeiro.

O protetor novo do Steam (11/2026) mostra a arte dos jogos jogados recentemente. Quando os recentes são atalhos de
emulador, ele ficou preto no Deck. O Steam aceita protetores próprios: uma pasta com uma página HTML em
~/.steam/root/config/uioverrides/screensavers/<nome>/ (como o "bouncinglogo" da Valve em steamui/screensavers).
Este módulo monta essa pasta com links para as artes que já estão em userdata/<id>/config/grid (não ocupa espaço)
e é refeito sozinho pelo bot uma vez por dia. Escolha em Configurações → Personalização → Protetor de tela.
"""
from __future__ import annotations

import glob
import json
import os
import random
import shutil
from pathlib import Path

from . import vdf

NOME = "deckcommander"  # vira o endereço uioverride-<NOME>.steamscreensavers.host: sem espaço nem maiúscula (espaço deu erro -105)
MAX_IMAGENS = 60

HTML = """<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="UTF-8"><title>Deck Commander</title>
<style>
html,body{margin:0;height:100%;background:#000;overflow:hidden;font-family:sans-serif}
.s{position:absolute;inset:0;opacity:0;transition:opacity 2s ease}
.s.v{opacity:1}
.s img.f{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;transform:scale(1.0);
 transition:transform 12s linear}
.s.v img.f{transform:scale(1.08)}
.s img.l{position:absolute;left:5%;bottom:8%;max-width:38%;max-height:28%;filter:drop-shadow(0 4px 12px #000)}
.s .t{position:absolute;left:5%;bottom:8%;color:#fff;font-size:5vh;text-shadow:0 3px 12px #000}
.g{position:absolute;inset:0;background:linear-gradient(transparent 55%,rgba(0,0,0,.65))}
</style></head><body>
<script>
const JOGOS = __JOGOS__;
let i = -1, atual = null;
function slide(j) {
  const d = document.createElement("div"); d.className = "s";
  const f = document.createElement("img"); f.className = "f"; f.src = j.fundo; d.appendChild(f);
  const g = document.createElement("div"); g.className = "g"; d.appendChild(g);
  if (j.logo) { const l = document.createElement("img"); l.className = "l"; l.src = j.logo;
    l.onerror = () => { l.remove(); const t = document.createElement("div"); t.className = "t"; t.textContent = j.titulo; d.appendChild(t); };
    d.appendChild(l);
  } else { const t = document.createElement("div"); t.className = "t"; t.textContent = j.titulo; d.appendChild(t); }
  return d;
}
function proximo() {
  if (!JOGOS.length) return;
  i = (i + 1) % JOGOS.length;
  const d = slide(JOGOS[i]); document.body.appendChild(d);
  requestAnimationFrame(() => requestAnimationFrame(() => d.classList.add("v")));
  const velho = atual; atual = d;
  if (velho) { velho.classList.remove("v"); setTimeout(() => velho.remove(), 2500); }
}
proximo(); setInterval(proximo, 9000);
</script></body></html>
"""


def _grid_dirs(home: Path) -> list[Path]:
    return [Path(p) for p in glob.glob(str(home / ".local/share/Steam/userdata/*/config/grid"))]


def _arte(grid: Path, appid: int, sufixos: tuple[str, ...]) -> Path | None:
    for s in sufixos:
        p = grid / f"{appid}{s}"
        if p.is_file() and p.stat().st_size > 0:
            return p
    return None


def escolher(home: Path, maximo: int = MAX_IMAGENS, rnd: random.Random | None = None) -> list[dict]:
    """Jogos com arte de fundo: os 20 mais recentes primeiro, depois outros sorteados (muda a cada dia)."""
    rnd = rnd or random.Random()
    out = []
    for grid in _grid_dirs(home):
        try:
            atalhos = vdf.read_shortcuts(grid.parent / "shortcuts.vdf")
        except (OSError, ValueError, KeyError):
            continue
        for s in atalhos:
            aid = int(s.get("appid", 0)) & 0xFFFFFFFF
            fundo = _arte(grid, aid, ("_hero.jpg", "_hero.png"))
            if not fundo or str(s.get("LaunchOptions", "")).startswith("app-"):  # apps (Spotify…) não são jogos
                continue
            out.append({"titulo": s.get("AppName", ""), "fundo": fundo,
                        "logo": _arte(grid, aid, ("_logo.png",)), "quando": int(s.get("LastPlayTime", 0) or 0)})
    out.sort(key=lambda j: -j["quando"])
    recentes, resto = out[:20], out[20:]
    rnd.shuffle(resto)
    return (recentes + resto)[:maximo]


def _ligar(origem: Path, destino: Path) -> None:
    try:
        os.link(origem, destino)  # mesmo disco: não ocupa espaço
    except OSError:
        shutil.copy2(origem, destino)


def montar(home: Path | None = None, rnd: random.Random | None = None) -> str:
    """(Re)monta a pasta do protetor. Devolve um resumo."""
    home = home or Path.home()
    jogos = escolher(home, rnd=rnd)
    pasta = home / ".steam/root/config/uioverrides/screensavers" / NOME
    tmp = pasta.with_name(NOME + ".novo")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    lista = []
    for n, j in enumerate(jogos):
        fundo = f"img/{n}f{j['fundo'].suffix}"
        (tmp / "img").mkdir(exist_ok=True)
        _ligar(j["fundo"], tmp / fundo)
        item = {"titulo": j["titulo"], "fundo": fundo, "logo": None}
        if j["logo"]:
            item["logo"] = f"img/{n}l.png"
            _ligar(j["logo"], tmp / item["logo"])
        lista.append(item)
    (tmp / "index.html").write_text(HTML.replace("__JOGOS__", json.dumps(lista, ensure_ascii=False)), "utf-8")
    velho = pasta.with_name(NOME + ".velho")
    shutil.rmtree(velho, ignore_errors=True)
    if pasta.exists():
        pasta.rename(velho)
    tmp.rename(pasta)
    shutil.rmtree(velho, ignore_errors=True)
    return f"Protetor de tela: {len(lista)} jogo(s)."
