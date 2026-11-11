"""Dublagem PT-BR das cenas em vídeo de um jogo de Switch do Deck, feita no PC (placa de vídeo).

    python tools/pc/dublar.py <id do jogo no Deck> [--max 3] [--voz pt-BR-AntonioNeural] [--so-listar]

Para cada vídeo do jogo: o Deck tira o vídeo do RomFS -> o PC transcreve (faster-whisper na GPU), traduz (IA local
do Ollama), gera a voz (edge-tts, grátis) e mistura (ffmpeg do imageio-ffmpeg) -> o vídeo dublado volta para o Deck
como mod do Ryujinx ("Dublagem PT-BR (Deck Commander)"; apagar a pasta desfaz). Vídeo sem som (ex.: Zelda TotK,
cuja voz fica em .bwav separados) é pulado com aviso.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
from dc import dublagem  # noqa: E402

CHAVE = str(Path.home() / ".ssh" / "deck_commander_ed25519")


def deck_alvo() -> str:
    f = Path.home() / ".deck-commander" / "deck.txt"
    return f.read_text().strip() if f.exists() else "deck@steamdeck"


def ssh(alvo: str, cmd: str, timeout: int = 900) -> str:
    r = subprocess.run(["ssh", "-i", CHAVE, "-o", "BatchMode=yes", alvo, cmd], capture_output=True, text=True,
                       timeout=timeout, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[-300:])
    return r.stdout


def scp(origem: str, destino: str) -> None:
    subprocess.run(["scp", "-q", "-i", CHAVE, "-o", "BatchMode=yes", origem, destino], check=True, timeout=1800)


def transcritor():
    from faster_whisper import WhisperModel
    try:
        modelo = WhisperModel("medium", device="cuda", compute_type="int8_float16")
    except Exception:  # noqa: BLE001 — sem CUDA livre: CPU (mais lento)
        modelo = WhisperModel("small", device="cpu", compute_type="int8")

    def transcrever(wav: Path) -> list[dublagem.Fala]:
        segs, _ = modelo.transcribe(str(wav), vad_filter=True)
        return [dublagem.Fala(s.start, s.end, s.text.strip()) for s in segs if s.text.strip()]
    return transcrever


def traduzir(textos: list[str], modelo: str = "qwen2.5:7b") -> list[str]:
    prompt = ("Traduza cada fala de cena de videogame para português do Brasil natural, curta, para ser DUBLADA "
              "(mesmo tom, sem explicar). Responda SOMENTE com uma lista JSON de strings, na mesma ordem e quantidade.\n"
              + json.dumps(textos, ensure_ascii=False))
    corpo = json.dumps({"model": modelo, "prompt": prompt, "stream": False, "format": "json",
                        "options": {"temperature": 0.3}}).encode()
    req = urllib.request.Request("http://127.0.0.1:11434/api/generate", corpo, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        txt = json.loads(r.read())["response"]
    try:
        out = json.loads(txt)
        if isinstance(out, dict):  # alguns modelos embrulham: {"falas": [...]}
            out = next(v for v in out.values() if isinstance(v, list))
    except (ValueError, StopIteration):
        out = []
    return [str(out[i]) if i < len(out) else textos[i] for i in range(len(textos))]


def falador(voz: str):
    import edge_tts

    def falar(texto: str, destino: Path) -> None:
        asyncio.run(edge_tts.Communicate(texto, voz).save(str(destino)))
    return falar


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("jogo")
    ap.add_argument("--max", type=int, default=3)
    ap.add_argument("--voz", default="pt-BR-AntonioNeural")
    ap.add_argument("--so-listar", action="store_true")
    a = ap.parse_args()
    import imageio_ffmpeg
    dublagem.FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
    alvo = deck_alvo()
    videos = json.loads(ssh(alvo, f"cd ~/deck-commander && python3 -m dc.dublagem_deck listar '{a.jogo}'"))
    print(f"{len(videos)} vídeo(s) no jogo")
    if a.so_listar:
        for v in videos:
            print(f"  {v['mb']:>7} MB  {v['caminho']}")
        return 0
    transcrever, falar = transcritor(), falador(a.voz)
    feitos = 0
    for v in sorted(videos, key=lambda x: x["mb"]):
        if feitos >= a.max:
            break
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            nome = Path(v["caminho"]).name
            ssh(alvo, f"cd ~/deck-commander && python3 -m dc.dublagem_deck extrair '{a.jogo}' '{v['caminho']}' /tmp/dc-dub/{nome}")
            scp(f"{alvo}:/tmp/dc-dub/{nome}", str(t / nome))
            ssh(alvo, f"rm -f /tmp/dc-dub/{nome}")
            saida = t / ("pt-" + nome)
            r = dublagem.dublar(t / nome, saida, t / "trab", transcrever, traduzir, falar)
            if not r["falas"]:
                print(f"  {nome}: " + ("sem som no vídeo (a voz do jogo fica em outro arquivo)" if r.get("sem_audio")
                                        else "nenhuma fala") + " — pulei")
                continue
            scp(str(saida), f"{alvo}:/tmp/dc-dub/{saida.name}")
            print(ssh(alvo, f"cd ~/deck-commander && python3 -m dc.dublagem_deck instalar '{a.jogo}' '{v['caminho']}' "
                            f"/tmp/dc-dub/{saida.name} && rm -f /tmp/dc-dub/{saida.name}").strip())
            print(f"  {nome}: {r['falas']} fala(s) dublada(s)")
            feitos += 1
    print(f"Pronto: {feitos} vídeo(s) dublado(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
