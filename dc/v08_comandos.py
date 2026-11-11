"""Comandos do bot da 0.8: /texturas, /netplay e o aviso de convite para jogar em rede."""
from __future__ import annotations

import subprocess
from pathlib import Path


def _achar(bot, nome: str) -> tuple[str, dict] | tuple[None, str]:
    from .remove import find
    lm = bot._map()
    hits = find(lm, nome)
    if len(hits) != 1:
        return None, ("Não achei esse jogo." if not hits else "Achei mais de um: " + ", ".join(
            lm[g]["title"] for g in hits[:6]))
    return hits[0], lm[hits[0]]


def _baixar(url: str, destino: Path) -> None:
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 deck-commander"})
    with urllib.request.urlopen(req, timeout=60) as r, open(destino, "wb") as f:  # noqa: S310 — link do usuário
        while True:
            bloco = r.read(1 << 20)
            if not bloco:
                break
            f.write(bloco)


def texturas(bot, args: list[str]) -> str:
    """/texturas <jogo> <link do pacote (.zip/.7z)> — PS2, GameCube e Wii."""
    link = next((a for a in args if a.startswith(("http://", "https://"))), "")
    nome = " ".join(a for a in args if a != link)
    if not link or not nome:
        return ("🖼️ Uso: /texturas <jogo> <link do pacote de texturas HD (.zip ou .7z)>\n"
                "Vale para PS2 (PCSX2), GameCube e Wii (Dolphin). O pacote vai para a pasta certa do emulador e a "
                "opção de texturas é ligada; vale na próxima vez que abrir o jogo.")
    gid, e = _achar(bot, nome)
    if not gid:
        return e
    from . import texturas as T
    try:
        return T.instalar(Path.home(), e.get("console", ""), Path(e["rom"]), link, _baixar)
    except (ValueError, RuntimeError, OSError) as ex:
        return f"🖼️ Não deu: {ex}"


def netplay(bot, args: list[str]) -> str:
    """/netplay <jogo> (convida o Deck do par e abre como anfitrião) · /netplay aceitar"""
    from . import familia_servico as fs
    from . import netplay as N
    estado = bot.paths.state
    if args[:1] == ["aceitar"]:
        try:
            c = N.aceitar(estado)
        except ValueError:
            return "Nenhum convite agora (vale 5 minutos)."
        _abrir(c["game_id"])
        return f"🎮 Abrindo {c['titulo']} conectado a {c['de']}…"
    if not args:
        return "🎮 Uso: /netplay <jogo> — chama o Deck do par para jogar junto (jogos do RetroArch)."
    gid, e = _achar(bot, " ".join(args))
    if not gid:
        return e
    from .retro import EMULADOR_DO_CONSOLE
    if EMULADOR_DO_CONSOLE.get(e.get("console")) != "RetroArch":
        return "🎮 Jogo em rede só nos consoles do RetroArch (NES, SNES, Mega Drive, GBA, N64…)."
    ip = N.ip_tailscale()
    if not ip:
        return "🎮 A Tailscale deste Deck não está ligada."
    try:
        par = fs._par(bot.paths)
    except ValueError as ex:
        return f"🎮 {ex}"
    eu = (fs.config(bot.paths).get("meu_nome") or "seu irmão")
    r = subprocess.run(N.comando_convidar_remoto(par["alvo"], par["chave"], eu, gid, e.get("title", gid), ip),
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        return f"🎮 Não consegui falar com o Deck de {par['nome']} (ligado e na Tailscale?)."
    N.pedir(estado, gid, "host")
    _abrir(gid)
    return f"🎮 Abrindo {e.get('title', gid)} como anfitrião; {par['nome']} recebeu o convite (vale 5 min)."


def _abrir(gid: str) -> None:
    """Abre o jogo pelo atalho do Steam (o lançador acrescenta --host/--connect)."""
    import glob
    from . import vdf
    for sc in glob.glob(str(Path.home() / ".local/share/Steam/userdata/*/config/shortcuts.vdf")):
        for s in vdf.read_shortcuts(Path(sc)):
            if s.get("LaunchOptions") == gid:
                aid = int(s["appid"]) & 0xFFFFFFFF
                subprocess.Popen(["steam", f"steam://rungameid/{vdf.shortcut_gameid64(aid)}"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                return


def avisar_convite(bot) -> None:
    """Laço do bot: convite novo do par vira mensagem com botão (uma vez)."""
    from . import netplay as N
    c = N.convite_pendente(bot.paths.state)
    marca = bot.paths.state / "netplay-avisado"
    if c and bot.cfg.get("notify_chat") and (not marca.exists() or marca.read_text() != str(c.get("quando"))):
        bot.send(bot.cfg["notify_chat"], f"🎮 {c['de']} chamou você para jogar {c['titulo']} em rede (vale 5 min).",
                 buttons=[("Aceitar e abrir", "/netplay aceitar")])
        marca.write_text(str(c.get("quando")))
