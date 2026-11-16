"""RetroAchievements no painel e no bot (pedido 15/11/2026: "ele gosta de platinar jogos").

Mostra, direto no Deck, o progresso de cada jogo retrô da sua conta do RetroAchievements: conquistas feitas / total,
pontos, e quais jogos você já MASTERIZOU (todas as conquistas no modo hardcore — o "platinar" do RetroAchievements).

Precisa de duas coisas que só você tem (o Deck Commander nunca cria conta nem digita senha):
- seu nome de usuário do retroachievements.org;
- sua "Web API Key" (no site: Settings → Keys → Web API Key). Ela só LÊ o seu progresso; não serve para entrar na
  conta. Fica guardada no Deck, só para você (arquivo com permissão 600).

Para GANHAR conquistas, entre na sua conta dentro do emulador uma vez (RetroArch: Configurações → Conquistas;
DuckStation, PCSX2, PPSSPP e Dolphin: Configurações → Conquistas / Achievements).

    python3 -m dc.conquistas            -> resumo da sua conta (jogos recentes e progresso)
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request

API = "https://retroachievements.org/API/{rota}.php"
SITE = "https://retroachievements.org"
SEGREDO = "retroachievements"
USUARIO_RX = re.compile(r"[A-Za-z0-9_]{2,32}")
CHAVE_RX = re.compile(r"[A-Za-z0-9]{20,64}")


def _get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "deck-commander"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def _url(rota: str, usuario: str, chave: str, **extra) -> str:
    q = {"u": usuario, "y": chave, **extra}
    return API.format(rota=rota) + "?" + urllib.parse.urlencode(q)


def credenciais(paths) -> tuple[str, str] | None:
    try:
        d = json.loads((paths.secrets / SEGREDO).read_text("utf-8"))
        return d["usuario"], d["chave"]
    except (OSError, ValueError, KeyError):
        return None


def salvar(paths, usuario: str, chave: str, get_json=_get_json) -> str:
    """Confere no site e guarda. Erros dizem exatamente o que fazer."""
    usuario, chave = (usuario or "").strip(), re.sub(r"\s+", "", chave or "")
    if not USUARIO_RX.fullmatch(usuario):
        raise ValueError("Escreva o seu nome de usuário do RetroAchievements (só letras, números e _).")
    if not CHAVE_RX.fullmatch(chave):
        raise ValueError("Isso não parece a Web API Key (no site: Settings → Keys → Web API Key; copie e cole inteira).")
    try:
        perfil = get_json(_url("API_GetUserProfile", usuario, chave, u=usuario))
    except Exception as e:
        raise ValueError(f"O site do RetroAchievements não aceitou (usuário ou chave errados, ou sem internet): "
                         f"{type(e).__name__}") from e
    if not isinstance(perfil, dict) or not perfil.get("User"):
        raise ValueError("O site não reconheceu esse usuário com essa chave. Confira os dois.")
    from .telegram_setup import save_secret
    save_secret(paths, SEGREDO, json.dumps({"usuario": perfil["User"], "chave": chave}))
    return f"Conta {perfil['User']} ligada: {perfil.get('TotalPoints', 0)} pontos."


def _int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def resumo(paths, get_json=_get_json, jogos: int = 15) -> dict:
    """Jogos recentes com progresso (normal e hardcore), pontos e quais estão masterizados."""
    cred = credenciais(paths)
    if not cred:
        return {"ligado": False}
    usuario, chave = cred
    cache = paths.state / "conquistas.json"
    try:
        d = get_json(_url("API_GetUserSummary", usuario, chave, g=jogos, a=5))
    except Exception as e:  # noqa: BLE001 — sem internet: mostra o último resumo guardado
        try:
            antigo = json.loads(cache.read_text("utf-8"))
            antigo["aviso"] = f"sem conexão agora ({type(e).__name__}); mostrando o resumo de {antigo.get('quando', '?')}"
            return antigo
        except (OSError, ValueError):
            return {"ligado": True, "usuario": usuario, "erro": "Sem conexão com o RetroAchievements agora."}
    premios = d.get("Awarded") or {}
    lista = []
    for j in d.get("RecentlyPlayed") or []:
        gid = str(j.get("GameID"))
        a = premios.get(gid) or {}
        total = _int(a.get("NumPossibleAchievements") or j.get("AchievementsTotal"))  # nomes da API oficial
        feitos = _int(a.get("NumAchieved") or j.get("NumAchieved"))
        hard = _int(a.get("NumAchievedHardcore") or j.get("NumAchievedHardcore"))
        lista.append({"id": gid, "titulo": j.get("Title", "?"), "console": j.get("ConsoleName", ""),
                      "total": total, "feitos": feitos, "hardcore": hard,
                      "pct": round(100 * max(feitos, hard) / total) if total else 0,
                      "masterizado": bool(total) and hard >= total, "completo": bool(total) and feitos >= total,
                      "ultimo": (j.get("LastPlayed") or "")[:10], "link": f"{SITE}/game/{gid}"})
    out = {"ligado": True, "usuario": d.get("User", usuario), "pontos": _int(d.get("TotalPoints")),
           "pontos_reais": _int(d.get("TotalTruePoints")), "posicao": d.get("Rank"),
           "masterizados": sum(1 for x in lista if x["masterizado"]), "jogos": lista,
           "quando": time.strftime("%d/%m %H:%M")}
    cache.write_text(json.dumps(out, ensure_ascii=False), "utf-8")
    return out


def texto(r: dict) -> str:
    """Resumo para o Telegram."""
    if not r.get("ligado"):
        return ("🏆 Conquistas (RetroAchievements): ainda não ligado. No painel do Deck Commander → Conquistas, cole "
                "seu usuário e a Web API Key (retroachievements.org → Settings → Keys).")
    if r.get("erro"):
        return "🏆 " + r["erro"]
    linhas = [f"🏆 {r['usuario']}: {r['pontos']} pontos · {r['masterizados']} jogo(s) masterizado(s)"]
    if r.get("aviso"):
        linhas.append("(" + r["aviso"] + ")")
    for j in r["jogos"][:10]:
        marca = "👑" if j["masterizado"] else ("✅" if j["completo"] else "▫️")
        linhas.append(f"{marca} {j['titulo']} ({j['console']}): {max(j['feitos'], j['hardcore'])}/{j['total']} "
                      f"({j['pct']}%)" + (f" · hardcore {j['hardcore']}" if j["hardcore"] and not j["masterizado"] else ""))
    return "\n".join(linhas)


def main(argv: list[str]) -> int:
    from .paths import get_paths
    print(texto(resumo(get_paths().ensure())))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
