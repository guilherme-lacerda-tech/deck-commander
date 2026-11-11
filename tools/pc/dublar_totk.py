"""Dublagem PT-BR do Zelda Tears of the Kingdom, feita no PC.

    python tools/pc/dublar_totk.py <cena> [<cena>…] [--voz-f pt-BR-FranciscaNeural] [--voz-m pt-BR-AntonioNeural]
    python tools/pc/dublar_totk.py --todas            (as 223 cenas com voz; demora)

Para cada fala com texto: o Deck manda o texto em inglês e a duração da voz original -> o PC traduz (IA local do
Ollama), gera a voz em português (edge-tts), ajusta para a MESMA duração (acelera até 1,6x ou completa com silêncio),
codifica em Opus 48 kHz, grava no formato .bwav do jogo (dc.traducao.bwav, conferido byte a byte com os originais),
confere tocando de volta e manda para o Deck instalar como mod do Ryujinx.
"""
from __future__ import annotations

import argparse
import re
import asyncio
import json
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
from dc.traducao import bwav  # noqa: E402

CHAVE = str(Path.home() / ".ssh" / "deck_commander_ed25519")


def alvo() -> str:
    f = Path.home() / ".deck-commander" / "deck.txt"
    return f.read_text().strip() if f.exists() else "deck@steamdeck"


def ssh(cmd: str, timeout: int = 900) -> str:
    r = subprocess.run(["ssh", "-i", CHAVE, "-o", "BatchMode=yes", alvo(), cmd], capture_output=True, text=True,
                       timeout=timeout, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[-400:])
    return r.stdout


def scp(o: str, d: str) -> None:
    subprocess.run(["scp", "-q", "-i", CHAVE, "-o", "BatchMode=yes", o, d], check=True, timeout=600)


ESPANHOL = re.compile(r"\b(recuerdos?|también|usted(es)?|ahora|entonces|mientras|nosotros|muy|ella|hasta|siempre|"
                      r"porque|pero|aquí|allí|cuando|donde|tiempo atrás|señor|señora|gracias|bueno)\b|[¿¡ñ]", re.I)


def traduzir(textos: list[str], modelo: str = "qwen2.5:7b") -> list[str]:
    """Tradução da cena; refaz (até 3x) se escapar espanhol — falha real: 'recuerdo' numa fala da Zelda."""
    aviso = ""
    saida = list(textos)
    for _ in range(4):
        try:
            saida = _traduzir1(textos, modelo, aviso)
        except RuntimeError as e:  # quantidade de falas não bateu (falha real: 5 para 4): pede de novo
            aviso = f" ATENÇÃO: devolva EXATAMENTE {len(textos)} falas, uma para cada linha. ({e})"
            continue
        ruins = [i for i, t in enumerate(saida) if ESPANHOL.search(t)]
        if not ruins:
            return saida
        aviso = (" ATENÇÃO: a resposta anterior teve palavras em ESPANHOL (" +
                 ", ".join(ESPANHOL.search(saida[i]).group(0) for i in ruins[:5]) +
                 "). Use SOMENTE português do Brasil (lembrança, também, você, agora, então…).")
    return saida


def _traduzir1(textos: list[str], modelo: str, aviso: str = "") -> list[str]:
    prompt = ("Você dubla The Legend of Zelda para o português do Brasil. Traduza cada fala de forma natural e fiel, "
              "com o vocabulário oficial da série (Hyrule, Link, Zelda, Ganondorf, Rauru, Sonia, Rei Demônio, Espada "
              "Mestra, Pedra Secreta, blood moon = Lua de Sangue, Demon King = Rei Demônio, Sage = Sábio). "
              "Português correto e falado no Brasil (nada de 'ameaça-se': use 'está ameaçado'; 'Witness' = 'Vejam'). "
              "Nunca escreva em espanhol. Tamanho parecido com o original (é dublagem)." + aviso +
              ' Diga também quem fala cada linha: "f" (Zelda, Sonia, Mineru, Riju, Purah, Paya, Impa e outras '
              'personagens femininas) ou "m" (Link, Rauru, Ganondorf, Tulin, Yunobo, Sidon e outros masculinos), pelo '
              'contexto. Responda SOMENTE um JSON {"falas": [...], "vozes": [...]} com a mesma quantidade e ordem.\n'
              + json.dumps(textos, ensure_ascii=False))
    corpo = json.dumps({"model": modelo, "prompt": prompt, "stream": False, "format": "json",
                        "options": {"temperature": 0.2}}).encode()
    req = urllib.request.Request("http://127.0.0.1:11434/api/generate", corpo, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        out = json.loads(json.loads(r.read())["response"])
    lista = out.get("falas") if isinstance(out, dict) else out
    if not isinstance(lista, list) or len(lista) != len(textos):
        raise RuntimeError(f"tradução veio com {len(lista) if isinstance(lista, list) else '?'} falas para {len(textos)}")
    vozes = out.get("vozes") if isinstance(out, dict) else None
    global ULTIMAS_VOZES
    ULTIMAS_VOZES = [str(v).lower()[:1] for v in vozes] if isinstance(vozes, list) and len(vozes) == len(textos) else []
    return [_fala(x, i) for i, x in enumerate(lista)]


def _fala(x, i: int) -> str:
    """Falha real: a IA devolveu {'f': 'Você vê...'} / {'texto': ..., 'voz': 'm'} no lugar da fala, e a voz leu as
    chaves. Tira o texto de dentro (e a voz, se veio junto)."""
    if isinstance(x, dict):
        voz = x.get("voz") or next((k for k in x if k in ("f", "m")), None)
        if voz and i < len(ULTIMAS_VOZES):
            ULTIMAS_VOZES[i] = str(voz).lower()[:1]
        x = x.get("texto") or x.get("fala") or next((v for v in x.values() if isinstance(v, str) and len(v) > 1), "")
    s = str(x).strip()
    if s.startswith("{"):
        raise RuntimeError("fala veio como objeto: " + s[:60])
    return s


ULTIMAS_VOZES: list[str] = []  # "f"/"m" por fala, da última tradução (quem fala cada linha)


def duracao(ff: str, arq: Path) -> float:
    import re
    err = subprocess.run([ff, "-hide_banner", "-i", str(arq)], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0


def voz_bwav(ff: str, texto: str, voz: str, amostras: int, canais: int, t: Path) -> bytes:
    import edge_tts
    import time
    mp3 = t / "v.mp3"
    for tentativa in range(3):  # o serviço de voz às vezes não responde ("No audio was received"): tenta de novo
        try:
            asyncio.run(edge_tts.Communicate(texto.replace("\n", " "), voz).save(str(mp3)))
            break
        except edge_tts.exceptions.NoAudioReceived:
            if tentativa == 2:
                raise
            time.sleep(3 * (tentativa + 1))
    alvo_s = amostras / 48000
    fator = min(max(duracao(ff, mp3) / alvo_s, 1.0), 1.6) if alvo_s > 0 else 1.0
    ogg = t / "v.ogg"
    filtro = f"atempo={fator:.3f},apad,atrim=end_sample={amostras}"  # mesma duração da voz original
    r = subprocess.run([ff, "-y", "-v", "error", "-i", str(mp3), "-af", filtro, "-ar", "48000", "-ac", "1",
                        "-c:a", "libopus", "-b:a", "64k", "-frame_duration", "20", "-application", "voip", str(ogg)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg: " + r.stderr[-300:])
    b = bwav.de_ogg(ogg.read_bytes(), amostras)
    b.outros = [list(b.pacotes) for _ in range(canais - 1)]  # estéreo: a mesma voz nos dois lados
    dados = bwav.gravar(b)
    # conferência: o .bwav gravado precisa tocar de volta com a duração da fala original
    volta = t / "volta.ogg"
    volta.write_bytes(bwav.para_ogg(bwav.ler(dados)))
    if abs(duracao(ff, volta) - alvo_s) > 0.1:
        raise RuntimeError(f"duração não confere ({duracao(ff, volta):.2f}s x {alvo_s:.2f}s)")
    return dados


def dublar_cena(ff: str, cena: str, voz_f: str, voz_m: str) -> int:
    falas = json.loads(ssh(f"cd ~/deck-commander && python3 -m dc.dublagem_totk falas '{cena}'"))
    if not falas:
        return 0
    pt = traduzir([f["texto"] for f in falas])
    voz = voz_f if any(n.lower() in cena.lower() for n in ("_ZE_", "Zelda")) else voz_m  # Lua de Sangue (_SY_) é o Ganondorf
    import tarfile
    feitas = 0
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        # uma ida e uma volta por cena (antes eram 3 conexões por fala)
        ssh(f"cd ~/deck-commander && python3 -m dc.dublagem_totk originais '{cena}' /tmp/dc-dub/{cena}.tar")
        scp(f"{alvo()}:/tmp/dc-dub/{cena}.tar", str(t / "orig.tar"))
        with tarfile.open(t / "orig.tar") as tf:
            originais = {Path(m.name).stem: tf.extractfile(m).read() for m in tf.getmembers() if m.isfile()}
        novos = t / "novos.tar"
        with tarfile.open(novos, "w") as saida:
            for f, texto in zip(falas, pt):
                if not any(c.isalpha() for c in texto) or f["rotulo"] not in originais:
                    continue  # "..." / só pontuação: fica a voz original
                canais = 1 + len(bwav.ler(originais[f["rotulo"]]).outros)
                k = falas.index(f)  # quem fala esta linha (a IA indica); sem isso, a regra da cena
                voz_da_fala = (voz_f if ULTIMAS_VOZES[k] == "f" else voz_m) if k < len(ULTIMAS_VOZES) else voz
                try:
                    dados = voz_bwav(ff, texto, voz_da_fala, f["amostras"], canais, t)
                except Exception as e:  # noqa: BLE001 — uma fala ruim não para a cena: fica a voz original
                    print(f"  {f['rotulo']}: pulei ({str(e)[:80]})")
                    continue
                arq = t / f"{f['rotulo']}.bwav"
                arq.write_bytes(dados)
                saida.add(arq, arcname=arq.name)
                print(f"  {f['rotulo']}: {f['texto'][:50]!r} -> {texto[:50]!r}")
                feitas += 1
        if feitas:
            scp(str(novos), f"{alvo()}:/tmp/dc-dub/{cena}-pt.tar")
            ssh(f"cd ~/deck-commander && python3 -m dc.dublagem_totk instalar_tar '{cena}' /tmp/dc-dub/{cena}-pt.tar")
        ssh(f"rm -f /tmp/dc-dub/{cena}.tar /tmp/dc-dub/{cena}-pt.tar")
    return feitas


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cenas", nargs="*")
    ap.add_argument("--todas", action="store_true")
    ap.add_argument("--voz-f", default="pt-BR-FranciscaNeural")
    ap.add_argument("--voz-m", default="pt-BR-AntonioNeural")
    a = ap.parse_args()
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    ssh("mkdir -p /tmp/dc-dub")
    cenas = json.loads(ssh("cd ~/deck-commander && python3 -m dc.dublagem_totk cenas")) if a.todas else a.cenas
    total = 0
    feitas = Path("D:/DeckCommander/logs/dublagem-totk-cenas-feitas.txt")
    prontas = set(feitas.read_text("utf-8").split()) if feitas.exists() else set()
    for c in cenas:
        if c in prontas and a.todas:  # continua de onde parou
            continue
        try:
            n = dublar_cena(ff, c, a.voz_f, a.voz_m)
        except Exception as e:  # noqa: BLE001 — uma cena com problema não para as outras
            print(f"{c}: pulei ({str(e)[:120]})")
            continue
        print(f"{c}: {n} fala(s) dublada(s)")
        total += n
        with open(feitas, "a", encoding="utf-8") as f:
            f.write(c + "\n")
    print(f"Pronto: {total} fala(s) em {len(cenas)} cena(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
