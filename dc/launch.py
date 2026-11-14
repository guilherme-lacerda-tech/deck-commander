"""dc-launch <game_id> — resolve o jogo no mapa e executa o emulador certo (substitui o processo)."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .library import build_command
from .paths import get_paths

# Emuladores que a camada de vídeo do modo de jogo (gamescope WSI) segura em 30 quadros por segundo.
# Medido no Deck em 11/11/2026: DuckStation ficava a 60% da velocidade (30 de 50 quadros) com o processador
# parado; com ENABLE_GAMESCOPE_WSI=0 foi a 100%. O PCSX2 roda normal (60) e fica como está.
SEM_WSI = ("duckstation",)


def sem_wsi_do_gamescope(cmd: list[str]) -> list[str]:
    """Abre o emulador sem a camada WSI do gamescope quando ele está na lista SEM_WSI."""
    if any(any(n in str(p).lower() for n in SEM_WSI) for p in cmd[:4]) and "ENABLE_GAMESCOPE_WSI=0" not in cmd:
        if cmd and cmd[0] == "/usr/bin/env":
            return [cmd[0], "ENABLE_GAMESCOPE_WSI=0"] + cmd[1:]
        return ["/usr/bin/env", "ENABLE_GAMESCOPE_WSI=0"] + cmd
    return cmd


def _jogar_pc(game_id: str, entry: dict, paths, say, fail) -> None:
    from . import pc_remoto
    app = entry.get("app") or entry.get("title", game_id)
    say(f"lançando {game_id}: PC remoto, app {app!r}")
    code, msg = pc_remoto.jogar(app, paths, say=say)
    if code and msg:
        fail(f"pc: {msg}", msg)
    sys.exit(code)


def main(argv: list[str]) -> None:
    paths = get_paths()
    log = paths.logs / "launch.log"
    paths.logs.mkdir(parents=True, exist_ok=True)

    def say(msg: str) -> None:
        with open(log, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now(timezone.utc).isoformat()} {msg}\n")

    def fail(msg: str, user_msg: str) -> None:
        """Registra e deixa o aviso para o plugin mostrar na tela do Deck (o Steam não mostra nada)."""
        say(msg)
        try:
            (paths.data / "launch-error.json").write_text(json.dumps(
                {"at": datetime.now(timezone.utc).isoformat(), "message": user_msg}, ensure_ascii=False), "utf-8")
        except OSError:
            pass
        sys.exit(1)

    if not argv:
        say("erro: sem game_id"); sys.exit(2)
    game_id = argv[0]
    try:
        launch_map = json.loads((paths.data / "launch-map.json").read_text("utf-8"))
    except Exception as e:  # noqa: BLE001
        fail(f"erro ao ler o mapa: {e}", "Esse jogo foi removido ou não está mais na biblioteca.")
    if launch_map.get(game_id, {}).get("console") == "pc":  # jogo do PC de casa por streaming
        try:
            _jogar_pc(game_id, launch_map[game_id], paths, say, fail)
        except Exception as e:  # noqa: BLE001
            fail(f"pc: erro {e!r}", f"{launch_map[game_id].get('title', game_id)}: não deu para abrir no PC ({e}).")
    try:
        emu_cfg = paths.config / "emulators.json"
        emulators = json.loads(emu_cfg.read_text("utf-8")) if emu_cfg.exists() else {}
        cmd = sem_wsi_do_gamescope(build_command(game_id, launch_map, emulators))
    except KeyError as e:
        fail(f"erro ao resolver {game_id}: {e}", "Esse jogo foi removido ou não está mais na biblioteca.")
    except Exception as e:  # noqa: BLE001
        fail(f"erro ao montar o comando de {game_id}: {e!r}",
             f"Não deu para abrir: configuração do emulador com problema ({type(e).__name__}). Veja o Diagnóstico.")
    try:  # "Jogar com o irmão": pedido de abrir em rede (vale uma vez, 5 min) — nunca impede o jogo de abrir
        from . import netplay
        cmd = netplay.aplicar_no_comando(cmd, netplay.argumentos(paths.state, game_id))
    except Exception as e:  # noqa: BLE001 — (revisão 11/11/2026: antes um erro aqui dizia "jogo removido")
        say(f"netplay: ignorado ({e})")
    title = launch_map[game_id].get("title", game_id)
    if not Path(cmd[-1]).exists():
        sd = cmd[-1].startswith("/run/media/")
        fail(f"erro: ROM não encontrada {cmd[-1]} (cartão SD fora?)",
             f"{title}: arquivo do jogo não encontrado" + (" — o cartão SD está colocado?" if sd else "."))
    if not Path(cmd[0]).exists():
        fail(f"erro: emulador não encontrado {cmd[0]}", f"{title}: emulador não encontrado ({Path(cmd[0]).name}).")
    if launch_map[game_id].get("console") == "switch":
        try:  # mod de tradução Trinity (Pokémon Z-A) de outra versão trava o jogo: desliga antes de abrir
            from .dedup import base_title_id
            from .traducao import trinity_game
            tid = base_title_id(Path(cmd[-1]).name)
            if tid:  # mod de tradução feito para a atualização mais nova: o Ryujinx precisa abrir essa versão
                from . import syncer
                from .traducao import switch as sw
                umsg = sw.ensure_update_selected(tid, syncer.rom_roots())
                if umsg:
                    say(umsg)
            gmsg = tid and trinity_game.guard_version(tid, paths.data / "traducao" / "mods-desligados")
            if gmsg:
                say(gmsg)
        except Exception as e:  # noqa: BLE001 — a conferência nunca impede o jogo de abrir
            say(f"conferência da tradução: ignorada ({e})")
    if launch_map[game_id].get("console") in ("switch", "switch2", "gc", "wii"):
        try:  # vibração: o emulador pode ter recriado a configuração com ela desligada
            from . import controls
            for linha in controls.vibracao():
                say(f"controle: {linha}")
        except Exception as e:  # noqa: BLE001 — nunca impede o jogo de abrir
            say(f"vibração: não conferi ({e})")
    try:  # cópia dos saves ANTES de jogar (5 últimas), em segundo plano: o jogo não espera
        import subprocess
        subprocess.Popen([sys.executable, "-m", "dc.copia_saves", game_id], cwd=str(Path(__file__).resolve().parents[1]),
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except Exception as e:  # noqa: BLE001 — nunca impede o jogo de abrir
        say(f"cópia dos saves: não iniciei ({e})")
    try:  # emulador atualizado desde a última vez: save state antigo pode não abrir (só avisa, nunca impede)
        from . import versao_emulador
        aviso = versao_emulador.conferir(paths.state, launch_map[game_id].get("console", ""), cmd)
        if aviso:
            say(f"aviso: {aviso}")
            (paths.data / "launch-error.json").write_text(json.dumps(
                {"at": datetime.now(timezone.utc).isoformat(), "title": "Deck Commander — emulador atualizado",
                 "message": aviso}, ensure_ascii=False), "utf-8")
    except Exception as e:  # noqa: BLE001
        say(f"versão do emulador: não conferi ({e})")
    try:  # filtro de tela do RetroArch conforme o perfil (Beleza/Retrô ligam, Desempenho desliga)
        from . import perfil
        f = perfil.filtros(paths)
        if f is not None and any("retroarch" in str(c).lower() for c in cmd[:4]):
            from . import retro as RT
            from . import retro_hacks as RH
            ra = Path.home() / RT.ARQUIVOS["RetroArch"]
            if ra.exists():
                velho = ra.read_text("utf-8", "replace")
                novo = RH.definir(velho, {"video_shader_enable": "true" if f else "false"})
                if novo != velho:
                    ra.write_text(novo, "utf-8")
    except Exception as e:  # noqa: BLE001 — nunca impede o jogo de abrir
        say(f"perfil: filtro não aplicado ({e})")
    cont_emu = None
    try:  # continuar de onde parou: abre no ponto salvo (emuladores com save rápido)
        from . import continuar
        cont_emu = continuar.qual(cmd) if continuar.ligado(paths) else None
        cmd, cmsg = continuar.ao_abrir(paths, game_id, cmd, launch_map[game_id].get("rom", ""))
        if cmsg:
            say(cmsg)
    except Exception as e:  # noqa: BLE001 — nunca impede o jogo de abrir
        say(f"continuar: ignorado ({e})")
    from . import quality
    try:
        from .tdp import em_dock
        na_dock = em_dock()
    except Exception:  # noqa: BLE001
        na_dock = False
    try:
        msg = quality.restore(paths)  # sobra de um jogo anterior fechado à força
        if msg:
            say(f"qualidade: {msg}")
        from . import autotune
        autotune.ensure(paths, game_id, launch_map[game_id]["console"])  # jogo novo: começa no nível "OK"
        rec = quality.apply_for_launch(paths, game_id, launch_map[game_id]["console"], dock=na_dock)
        if na_dock:
            say("monitor/TV ligado: modo dock (resolução maior e energia no máximo)")
    except Exception as e:  # noqa: BLE001 — ajuste de qualidade nunca impede o jogo de abrir
        say(f"qualidade: ignorado ({e})"); rec = None
    from . import perf
    console = launch_map[game_id]["console"]
    measure = perf.enabled(paths)
    log_dir = None
    secs = None
    if measure:
        try:
            bs = paths.data / "bench-seconds"  # deixado pelo benchmark: vale só para esta abertura
            secs = int(bs.read_text()) if bs.exists() else None
            if secs:
                bs.unlink()
            cmd, log_dir = perf.wrap_command(cmd, seconds=secs)
        except Exception as e:  # noqa: BLE001 — medição nunca impede o jogo de abrir
            say(f"desempenho: medição desligada ({e})"); measure = False
    tdp_ctl = None
    try:  # TDP (energia) do console; sobra de um jogo fechado à força volta antes
        from . import tdp
        tdp_ctl = tdp.Tdp(paths.state / "tdp-anterior.json")
        if not (paths.config / "tdp-desligado").exists():
            say(f"energia: {tdp_ctl.aplicar_console(console, na_dock)}")
        else:
            tdp_ctl = None
    except Exception as e:  # noqa: BLE001 — energia nunca impede o jogo de abrir
        say(f"energia: ignorado ({e})"); tdp_ctl = None
    try:  # saves iguais no Deck e no PC: ao fechar, a sincronização entra na fila sozinha
        from . import saves_sync
        saves_auto = saves_sync.auto_ligado(paths, game_id)
    except Exception:  # noqa: BLE001
        saves_auto = False
    say(f"lançando {game_id}: {cmd}")
    try:  # quem está aberto: vigia do monitor (dock_watch) e o "salvar ponto" do plugin (botão Steam / descanso)
        (paths.state / "jogo-aberto.json").write_text(json.dumps(
            {"game_id": game_id, "console": console, "title": title, "pid": os.getpid(), "cmd": cmd,
             "display": os.environ.get("DISPLAY", ":1"), "rom": launch_map[game_id].get("rom", "")},
            ensure_ascii=False), "utf-8")
    except OSError:
        pass
    if not rec and not measure and not tdp_ctl and not saves_auto and not cont_emu:
        os.execvp(cmd[0], cmd)
    if rec:
        say(f"qualidade deste jogo: {rec['key']} {rec['old']} -> {rec['new']} (volta ao fechar)")
    import signal
    import subprocess
    import time
    t0 = time.time()
    child = subprocess.Popen(cmd)
    if cont_emu:  # ponto de continuar automático a cada 10 min de jogo (seguro se a bateria acabar no descanso)
        import threading

        def _pontos():
            from . import continuar
            while child.poll() is None:
                time.sleep(continuar.INTERVALO)
                if child.poll() is None:
                    try:
                        r = continuar.salvar_ponto(paths, game_id, cmd, os.environ.get("DISPLAY", ":1"),
                                                   launch_map[game_id].get("rom", ""))
                        say(f"continuar: ponto salvo ({'10 min' if r else 'não deu agora'})")
                    except Exception as e:  # noqa: BLE001
                        say(f"continuar: {e}")
        threading.Thread(target=_pontos, daemon=True).start()
    sampler = perf.Sampler().start() if measure else None

    def _stop(signum, _frame):  # "Sair do jogo" do Steam: fecha o emulador e ainda devolve a qualidade
        child.send_signal(signum)
        if cmd[0].endswith("flatpak") and len(cmd) > 2:  # o emulador roda no sandbox: fechar só o flatpak não basta
            app = next((a for a in cmd[2:] if not a.startswith("-")), None)
            if app:
                subprocess.run(["flatpak", "kill", app], check=False, capture_output=True)
        try:
            child.wait(timeout=8)
        except subprocess.TimeoutExpired:
            child.kill()
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGHUP, _stop)
    code = 1
    try:
        code = child.wait()
        if code not in (0, None) and time.time() - t0 < 15:  # o emulador caiu logo ao abrir: o Steam não mostra nada
            try:
                (paths.data / "launch-error.json").write_text(json.dumps(
                    {"at": datetime.now(timezone.utc).isoformat(),
                     "message": f"{title}: o emulador fechou com erro logo ao abrir (código {code}). "
                                "Veja o Diagnóstico no painel."}, ensure_ascii=False), "utf-8")
            except OSError:
                pass
            say(f"emulador caiu ao abrir: código {code}")
    finally:
        (paths.state / "jogo-aberto.json").unlink(missing_ok=True)
        if saves_auto:
            try:
                if saves_sync.pedir_ao_fechar(paths, game_id, title, time.time() - t0):
                    say("saves: sincronização com o PC na fila")
            except Exception as e:  # noqa: BLE001
                say(f"saves: não pus na fila ({e})")
        if sampler:
            try:
                res = perf.finish_session(paths, game_id, console, title, log_dir, t0, sampler, rec)
                say(f"desempenho: {res}")
                from . import autotune
                v = json.loads(res).get("verdict") if res.startswith("{") else None
                # na dock a energia e a resolução são outras: a partida não ensina nada para o modo portátil
                from . import perfil  # perfil fixo (Beleza/Desempenho/Retrô) também não ensina o auto-ajuste
                # partida de menos de 2 min (abriu e fechou) não diz nada sobre o jogo: não ensina (o benchmark sim)
                curta = secs is None and time.time() - t0 < 120
                change = (None if na_dock or curta or not perfil.aprende(paths)
                          else autotune.record(paths, game_id, console, v))
                if change:
                    say(f"auto-ajuste: {change}")
            except Exception as e:  # noqa: BLE001
                say(f"desempenho: não registrado ({e})")
        if tdp_ctl:
            try:
                say(f"energia: {tdp_ctl.restaurar()}")
            except Exception as e:  # noqa: BLE001
                say(f"energia: devolução falhou ({e})")
        if rec:
            try:
                say(f"qualidade: {quality.restore(paths)}")
            except Exception as e:  # noqa: BLE001
                say(f"qualidade: devolução falhou ({e}); o serviço tenta de novo")
    sys.exit(code)
