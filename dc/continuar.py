"""Continuar de onde parou (pedido 13/11/2026, "descanso + save extra").

O descanso do Deck (botão de ligar) já congela QUALQUER jogo, de qualquer emulador. Isto é o seguro extra para os
emuladores que têm save rápido: o Deck Commander guarda um "ponto de continuar" por jogo e, ao abrir o jogo de novo,
o emulador já começa nele — mesmo que a bateria acabe durante o descanso ou que o jogo tenha sido fechado.

Quando o ponto é salvo (sem tocar nos seus saves do L4):
- ao apertar o botão Steam com o jogo aberto (o caminho para "Sair do jogo") e antes de o Deck dormir — o plugin chama
  `python3 -m dc.continuar salvar`;
- a cada 10 minutos de jogo (dc-launch).
Por que não "na hora de sair": medido no Deck em 13/11/2026, a Steam fecha o emulador 0,2 s depois do "Sair do jogo",
e o DuckStation ignora o pedido de fechar (SIGTERM) — não dá tempo nem jeito de salvar ali.

Como a tecla chega ao emulador: `xdotool` na tela virtual do jogo (DISPLAY do dc-launch). Testado no Deck: o teclado
virtual (/dev/uinput) é criado mas o modo de jogo não tem permissão de lê-lo; o xdotool funciona.

Cada emulador salva num espaço só do Deck Commander (combinação Ctrl+F9, que ninguém usa); o arquivo é copiado para
`<pasta de estados do emulador>/dc-continuar/<jogo>` e o espaço original fica como estava. Ao abrir, o emulador recebe
esse arquivo — só se a versão do emulador for a mesma de quando salvou (estado de outra versão pode travar o jogo).

Sem save rápido (Switch, Wii U, Xbox 360, Switch 2) ou fora (PS3, a pedido): vale só o descanso do Deck.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

H = Path.home()
TECLA = "ctrl+F9"
INTERVALO = 600  # s entre pontos automáticos durante o jogo


@dataclass
class Emu:
    nome: str
    pastas: list  # onde o emulador grava os estados (a primeira que existir)
    padrao: str  # arquivo novo que a tecla cria (glob)
    tecla: str = TECLA
    devolver_espaco: bool = False  # o emulador não tem espaço próprio: o espaço usado volta ao que era
    apagar_criado: bool = False  # RetroArch: o arquivo criado sai da fila dos seus saves (vira só o ponto)
    extras: list = field(default_factory=list)


EMUS = {
    "duckstation": Emu("DuckStation", [H / ".local/share/duckstation/savestates",
                                       H / ".var/app/org.duckstation.DuckStation/data/duckstation/savestates"],
                       "savestate_10.sav"),
    "pcsx2": Emu("PCSX2", [H / ".var/app/net.pcsx2.PCSX2/config/PCSX2/sstates"], "*.10.p2s"),
    "ppsspp": Emu("PPSSPP", [H / ".var/app/org.ppsspp.PPSSPP/config/ppsspp/PSP/PPSSPP_STATE"], "*.ppst",
                  tecla="F2", devolver_espaco=True),
    "dolphin": Emu("Dolphin", [H / ".var/app/org.DolphinEmu.dolphin-emu/data/dolphin-emu/StateSaves"], "*.s10"),
    "retroarch": Emu("RetroArch", [], "", tecla="F9", apagar_criado=True),
}
# Teclas do "ponto de continuar" na configuração de cada emulador (seção, chave, valor)
ATALHOS = {
    "duckstation": [(H / ".local/share/duckstation/settings.ini", "Hotkeys", "SaveGameState10",
                     "Keyboard/Control & Keyboard/F9")],
    "pcsx2": [(H / ".var/app/net.pcsx2.PCSX2/config/PCSX2/inis/PCSX2.ini", "Hotkeys", "SaveStateToSlot10",
               "Keyboard/Control & Keyboard/F9")],
    "dolphin": [(H / ".var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu/Hotkeys.ini", "Hotkeys",
                 "Save State/Save State Slot 10", "@(`Control_L`+`F9`)")],
}


def qual(cmd: list[str]) -> str | None:
    from .versao_emulador import _sem_env
    texto = " ".join(str(c) for c in _sem_env(list(cmd))[:4]).lower()
    return next((k for k in EMUS if k in texto), None)


def ligado(paths) -> bool:
    return not (paths.config / "continuar-desligado").exists()


def definir(paths, ligar: bool) -> None:
    f = paths.config / "continuar-desligado"
    if ligar:
        f.unlink(missing_ok=True)
    else:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("1")


# ------------------------------------------------------------------------------------------------ configuração
def _ini_com(texto: str, secao: str, chave: str, valor: str) -> str:
    linhas, dentro, feito, out = texto.splitlines(), False, False, []
    for ln in linhas:
        s = ln.strip()
        if s.startswith("[") and s.endswith("]"):
            if dentro and not feito:
                out.append(f"{chave} = {valor}"); feito = True
            dentro = s[1:-1] == secao
        elif dentro and ln.split("=")[0].strip() == chave:
            if not feito:
                out.append(f"{chave} = {valor}"); feito = True
            continue
        out.append(ln)
    if not feito:
        if not dentro:
            out.append(f"[{secao}]")
        out.append(f"{chave} = {valor}")
    return "\n".join(out) + "\n"


def preparar(emu: str) -> list[str]:
    """Põe a tecla do ponto de continuar na configuração do emulador (só se o arquivo já existe)."""
    feito = []
    for arq, secao, chave, valor in ATALHOS.get(emu, []):
        if not arq.exists():
            continue
        velho = arq.read_text("utf-8", "replace")
        novo = _ini_com(velho, secao, chave, valor)
        if novo != velho:
            tmp = arq.with_name(arq.name + ".dc-tmp")
            tmp.write_text(novo, "utf-8")
            os.replace(tmp, arq)
            feito.append(f"{EMUS[emu].nome}: tecla do ponto de continuar")
    if emu == "retroarch":
        from . import retro as RT
        from . import retro_hacks as RH
        ra = H / RT.ARQUIVOS["RetroArch"]
        if ra.exists():  # carrega o <jogo>.state.auto ao abrir (o .auto só é gravado pelo Deck Commander)
            velho = ra.read_text("utf-8", "replace")
            novo = RH.definir(velho, {"savestate_auto_load": "true", "savestate_auto_save": "false"})
            if novo != velho:
                ra.write_text(novo, "utf-8"); feito.append("RetroArch: abre no ponto de continuar")
    return feito


def _pasta_estados(emu: str) -> Path | None:
    if emu == "retroarch":
        from . import retro as RT
        cfg = H / RT.ARQUIVOS["RetroArch"]
        d = None
        if cfg.exists():
            for ln in cfg.read_text("utf-8", "replace").splitlines():
                k, _, v = ln.partition("=")
                if k.strip() == "savestate_directory":
                    d = v.strip().strip('"')
        if d and d != "default":
            return Path(d.replace("~", str(H), 1))
        return H / RT.RA / "states"
    return next((p for p in EMUS[emu].pastas if p.exists()), None)


# ------------------------------------------------------------------------------------------------ guardar o ponto
def _meta_path(paths, game_id: str) -> Path:
    return paths.data / "continuar" / f"{game_id}.json"


def _fotos(pasta: Path, padrao: str) -> dict[Path, float]:
    return {p: p.stat().st_mtime for p in pasta.rglob(padrao) if p.is_file() and "dc-continuar" not in p.parts}


def _novo(antes: dict, pasta: Path, padrao: str, desde: float) -> Path | None:
    for p, m in _fotos(pasta, padrao).items():
        if m >= desde - 1 and antes.get(p) != m and not p.name.endswith((".png", ".auto", ".bak", ".undo")):
            return p
    return None


def _tecla(display: str, tecla: str) -> bool:
    env = dict(os.environ, DISPLAY=display)
    return subprocess.run(["xdotool", "key", tecla], env=env, capture_output=True, timeout=10).returncode == 0


def salvar_ponto(paths, game_id: str, cmd: list[str], display: str, rom: str = "", espera: float = 8,
                 tecla_fn=_tecla) -> str | None:
    """Aperta a tecla no emulador, espera o arquivo novo e guarda como ponto de continuar do jogo."""
    emu = qual(cmd)
    if not emu or not ligado(paths):
        return None
    e = EMUS[emu]
    pasta = _pasta_estados(emu)
    if pasta is None:
        return None
    padrao = f"{Path(rom).stem}.state*" if emu == "retroarch" else e.padrao
    antes = _fotos(pasta, padrao)
    guardado = {}
    if e.devolver_espaco:  # cópia em disco (save de PSP tem dezenas de MB): o espaço volta a ser o seu depois
        bk = pasta / "dc-continuar" / ".espaco"
        bk.mkdir(parents=True, exist_ok=True)
        for i, p in enumerate(antes):
            guardado[p] = bk / f"{i}.bak"
            shutil.copy2(p, guardado[p])
    t0 = time.time()
    if not tecla_fn(display, e.tecla):
        return None
    arq, fim = None, t0 + espera
    while time.time() < fim:
        arq = _novo(antes, pasta, padrao, t0)
        if arq:
            t1 = arq.stat().st_size
            time.sleep(0.6)  # terminou de gravar? (o tamanho parou)
            if arq.exists() and arq.stat().st_size == t1 and t1 > 0:
                break
        time.sleep(0.25)
    else:
        if guardado:
            shutil.rmtree(pasta / "dc-continuar" / ".espaco", ignore_errors=True)
        return None
    destino = pasta / "dc-continuar" / f"{game_id}{''.join(arq.suffixes[-1:])}"
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(destino.name + ".tmp")
    shutil.copy2(arq, tmp)
    os.replace(tmp, destino)
    if e.devolver_espaco:  # o espaço que o emulador usou volta a ter o seu save de antes
        if arq in guardado:
            shutil.copy2(guardado[arq], arq)
        else:
            arq.unlink(missing_ok=True)
        shutil.rmtree(pasta / "dc-continuar" / ".espaco", ignore_errors=True)
    if e.apagar_criado:
        arq.unlink(missing_ok=True)
        arq.with_name(arq.name + ".png").unlink(missing_ok=True)
    from . import versao_emulador
    try:
        versao = versao_emulador.identidade(cmd)
    except Exception:  # noqa: BLE001
        versao = None
    meta = {"arquivo": str(destino), "emulador": emu, "versao": versao, "quando": time.time(),
            "pasta_original": str(arq.parent)}
    m = _meta_path(paths, game_id)
    m.parent.mkdir(parents=True, exist_ok=True)
    m.write_text(json.dumps(meta, ensure_ascii=False), "utf-8")
    return str(destino)


# ------------------------------------------------------------------------------------------------ abrir no ponto
def ponto(paths, game_id: str) -> dict | None:
    try:
        meta = json.loads(_meta_path(paths, game_id).read_text("utf-8"))
    except (OSError, ValueError):
        return None
    return meta if Path(meta.get("arquivo", "")).exists() else None


def esquecer(paths, game_id: str) -> bool:
    meta = ponto(paths, game_id)
    _meta_path(paths, game_id).unlink(missing_ok=True)
    if not meta:
        return False
    Path(meta["arquivo"]).unlink(missing_ok=True)
    if meta.get("emulador") == "retroarch":
        Path(meta.get("auto", "")).unlink(missing_ok=True) if meta.get("auto") else None
    return True


def ao_abrir(paths, game_id: str, cmd: list[str], rom: str, versao_fn=None) -> tuple[list[str], str | None]:
    """Comando que já abre no ponto de continuar (ou o mesmo comando) + uma linha para o registro."""
    emu = qual(cmd)
    if not emu or not ligado(paths):
        return cmd, None
    try:
        preparar(emu)
    except OSError:
        pass
    meta = ponto(paths, game_id)
    if not meta or meta.get("emulador") != emu:
        return cmd, None
    if versao_fn is None:
        from .versao_emulador import identidade as versao_fn
    try:
        agora = versao_fn(cmd)
    except Exception:  # noqa: BLE001
        agora = None
    if meta.get("versao") and agora and agora != meta["versao"]:
        return cmd, "continuar: o emulador mudou de versão desde o ponto salvo; abrindo normal (o ponto fica guardado)"
    arq = meta["arquivo"]
    if emu == "retroarch":  # o RetroArch carrega sozinho o <jogo>.state.auto ao abrir (savestate_auto_load)
        auto = Path(meta.get("pasta_original") or Path(arq).parent.parent) / f"{Path(rom).stem}.state.auto"
        shutil.copy2(arq, auto)
        meta["auto"] = str(auto)
        _meta_path(paths, game_id).write_text(json.dumps(meta, ensure_ascii=False), "utf-8")
        return cmd, f"continuar: RetroArch abre no ponto salvo ({auto.name})"
    extra = {"duckstation": ["-statefile", arq], "pcsx2": ["-statefile", arq], "dolphin": [f"--save_state={arq}"],
             "ppsspp": [f"--state={arq}"]}[emu]
    novo = list(cmd)
    if "--" in novo:
        i = novo.index("--")
        novo[i:i] = extra
    else:
        novo[-1:-1] = extra
    return novo, f"continuar: abrindo no ponto salvo de {time.strftime('%d/%m %H:%M', time.localtime(meta['quando']))}"


# ------------------------------------------------------------------------------------------------ jogo aberto
def jogo_aberto(paths) -> dict | None:
    try:
        j = json.loads((paths.state / "jogo-aberto.json").read_text("utf-8"))
    except (OSError, ValueError):
        return None
    pid = j.get("pid")
    if pid and not Path(f"/proc/{pid}").exists():
        return None
    return j


def salvar_agora(paths, motivo: str = "") -> str:
    j = jogo_aberto(paths)
    if not j or not j.get("cmd") or not j.get("display"):
        return "nenhum jogo aberto"
    if not qual(j["cmd"]):
        return "este emulador não tem save rápido (vale o descanso do Deck)"
    r = salvar_ponto(paths, j["game_id"], j["cmd"], j["display"], j.get("rom", ""))
    return f"ponto de continuar salvo ({motivo})" if r else "não consegui salvar o ponto agora"


def main(argv: list[str]) -> int:
    from .paths import get_paths
    paths = get_paths()
    if argv[:1] == ["salvar"]:
        msg = salvar_agora(paths, " ".join(argv[1:]) or "pedido")
        try:
            with open(paths.logs / "launch.log", "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} continuar: {msg}\n")
        except OSError:
            pass
        print(msg)
        return 0
    print("uso: python3 -m dc.continuar salvar [motivo]")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))


# ------------------------------------------------------------------------------------------------ voltar no tempo
REBOBINA = {"retroarch": 30, "duckstation": 10}  # até quantos segundos dá para voltar (memória de cada emulador)


def voltar_no_tempo(paths, segundos: int, tecla_fn=None) -> str:
    """Botões do painel "Voltar 5 s / 10 s / 30 s": segura a tecla do voltar no tempo (F11, a mesma do L5) no jogo
    aberto. O emulador volta mostrando o jogo andando para trás (cerca de 2x a velocidade normal)."""
    j = jogo_aberto(paths)
    if not j or not j.get("cmd"):
        return "Abra um jogo primeiro."
    emu = qual(j["cmd"])
    if emu not in REBOBINA:
        return ("Este emulador não tem voltar no tempo. Use o R4 (carrega o último save rápido) ou o ponto de "
                "continuar.")
    seg = min(int(segundos), REBOBINA[emu])
    env = dict(os.environ, DISPLAY=j.get("display") or ":1")
    if tecla_fn is None:
        def tecla_fn(acao):
            subprocess.run(["xdotool", acao, "F11"], env=env, capture_output=True, timeout=10)
    tecla_fn("keydown")
    try:
        time.sleep(seg / 2)  # a volta toca a ~2x
    finally:
        tecla_fn("keyup")
    return f"Voltei cerca de {seg} s." + (f" ({EMUS[emu].nome} guarda no máximo {REBOBINA[emu]} s.)"
                                          if seg < int(segundos) else "")
