"""Dublagem PT-BR de vídeos de cena (0.8): transcreve a fala (Whisper), traduz, gera a voz (edge-tts) e mistura de volta
no vídeo SEM mexer na imagem (-c:v copy); gera também a legenda .srt. Roda no PC (tools/pc/dublar.py), que tem
a placa de vídeo para o Whisper; o Deck só tira o vídeo do jogo e instala o dublado como mod (dc.dublagem_deck).

1ª versão gerada pela IA local (docs/specs/dublagem.md); reescrita depois dos testes (filtro do ffmpeg malformado,
legenda em inglês, AAC dentro de .webm, vídeo sem áudio). Sincronia: por frase (cada voz começa no instante da fala
original e é acelerada até 1,5x para caber); movimento labial não.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

FFMPEG = "ffmpeg"  # o PC troca pelo caminho do imageio-ffmpeg


@dataclass
class Fala:
    ini: float
    fim: float
    texto: str


def _tempo(s: float) -> str:
    ms = int(round(s * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def srt(falas: list[Fala]) -> str:
    return "".join(f"{i}\n{_tempo(f.ini)} --> {_tempo(f.fim)}\n{f.texto}\n\n" for i, f in enumerate(falas, 1))


def comando_extrair_audio(video: Path, wav: Path) -> list[str]:
    return [FFMPEG, "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", str(wav)]


def info(arquivo: Path, run=subprocess.run) -> tuple[float, bool]:
    """(duração em segundos, tem áudio?) lendo a saída do próprio ffmpeg (o PC não tem ffprobe)."""
    try:
        r = run([FFMPEG, "-hide_banner", "-i", str(arquivo)], capture_output=True, text=True, timeout=60)
        err = r.stderr or ""
    except (OSError, subprocess.TimeoutExpired):
        return 0.0, False
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0
    return dur, bool(re.search(r"Stream #\S+.*: Audio:", err))


def duracao(arquivo: Path, run=subprocess.run) -> float:
    return info(arquivo, run)[0]


def comando_mixar(video: Path, falas_audio: list[tuple[float, Path]], saida: Path, volume_original: float = 0.25,
                  tem_audio: bool = True) -> list[str]:
    if not falas_audio:
        return [FFMPEG, "-y", "-i", str(video), "-c", "copy", str(saida)]
    cmd = [FFMPEG, "-y", "-i", str(video)]
    partes, rotulos = [], []
    for i, (inicio, arq) in enumerate(falas_audio, 1):
        cmd += ["-i", str(arq)]
        ms = int(round(inicio * 1000))
        partes.append(f"[{i}:a]adelay={ms}|{ms}[v{i}]")
        rotulos.append(f"[v{i}]")
    if tem_audio:  # som original de fundo (música/efeitos) mais baixo + as vozes novas
        partes.insert(0, f"[0:a]volume={volume_original}[bg]")
        rotulos.insert(0, "[bg]")
    fc = ";".join(partes) + ";" + "".join(rotulos) + \
        f"amix=inputs={len(rotulos)}:duration=longest:dropout_transition=0:normalize=0[a]"
    codec = ["-c:a", "libopus", "-b:a", "128k"] if saida.suffix.lower() == ".webm" else ["-c:a", "aac", "-b:a", "160k"]
    return cmd + ["-filter_complex", fc, "-map", "0:v", "-map", "[a]", "-c:v", "copy", *codec, "-shortest", str(saida)]


def ajustar_velocidade(arquivo: Path, alvo: float, run=subprocess.run) -> Path:
    """Voz mais longa que a fala original: acelera até 1,5x (atempo) para caber no tempo."""
    dur = duracao(arquivo, run)
    if alvo <= 0 or dur <= alvo:
        return arquivo
    fator = min(dur / alvo, 1.5)
    rapido = arquivo.with_name(arquivo.stem + ".rapido" + arquivo.suffix)
    r = run([FFMPEG, "-y", "-i", str(arquivo), "-af", f"atempo={fator:.3f}", str(rapido)], capture_output=True,
            timeout=120)
    return rapido if r.returncode == 0 else arquivo


def dublar(video: Path, saida: Path, trab: Path, transcrever, traduzir, falar, run=subprocess.run) -> dict:
    trab.mkdir(parents=True, exist_ok=True)
    _dur, tem_audio = info(video, run)
    wav = trab / "orig.wav"
    falas: list[Fala] = []
    if tem_audio:
        r = run(comando_extrair_audio(video, wav), capture_output=True, timeout=600)
        if r.returncode != 0:
            raise RuntimeError("ffmpeg (extrair áudio): " + str(r.stderr)[-300:])
        falas = transcrever(wav)
    if not falas:
        return {"falas": 0, "saida": "", "legenda": "", "sem_audio": not tem_audio}
    textos = traduzir([f.texto for f in falas])
    pt = [Fala(f.ini, f.fim, t) for f, t in zip(falas, textos)]
    vozes = []
    for i, f in enumerate(pt):
        mp3 = trab / f"v{i}.mp3"
        falar(f.texto, mp3)
        vozes.append((f.ini, ajustar_velocidade(mp3, f.fim - f.ini, run)))
    leg = trab / "legenda.srt"
    leg.write_text(srt(pt), encoding="utf-8")
    r = run(comando_mixar(video, vozes, saida, tem_audio=tem_audio), capture_output=True, timeout=1800)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg (mixar): " + str(r.stderr)[-300:])
    return {"falas": len(pt), "saida": str(saida), "legenda": str(leg)}


def _caminho_filtro(p: Path) -> str:
    return str(p).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def comando_legendar(video: Path, legenda: Path, saida: Path) -> list[str]:
    """Legenda PT-BR "queimada" na imagem (o jogo não sabe mostrar uma legenda que não previu). Rascunho da IA local
    (qwen2.5-coder:7b) corrigido: codec/qualidade trocados, sem -map, ignorava FFMPEG."""
    webm = saida.suffix.lower() == ".webm"
    video_cod = (["-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "32", "-row-mt", "1"] if webm else
                 ["-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p"])
    filtro = f"subtitles='{_caminho_filtro(legenda)}':force_style='FontSize=22,Outline=2'"
    return [FFMPEG, "-y", "-v", "error", "-i", str(video), "-map", "0:v:0", "-map", "0:a?", "-vf", filtro,
            *video_cod, "-c:a", "copy", str(saida)]


def legendar(video: Path, saida: Path, trab: Path, transcrever, traduzir, run=subprocess.run) -> dict:
    """PADRÃO (pedido do usuário 11/11/2026): legenda em português em vez de dublar — sem gerar voz, bem mais rápido.
    A dublagem (dublar) fica como opção para o jogo que ele quiser."""
    trab.mkdir(parents=True, exist_ok=True)
    _dur, tem_audio = info(video, run)
    if not tem_audio:
        return {"falas": 0, "saida": "", "legenda": "", "sem_audio": True}
    wav = trab / "orig.wav"
    r = run(comando_extrair_audio(video, wav), capture_output=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg (extrair áudio): " + str(r.stderr)[-300:])
    falas = transcrever(wav)
    if not falas:
        return {"falas": 0, "saida": "", "legenda": ""}
    textos = traduzir([f.texto for f in falas])
    leg = trab / "legenda.srt"
    leg.write_text(srt([Fala(f.ini, f.fim, x) for f, x in zip(falas, textos)]), encoding="utf-8")
    r = run(comando_legendar(video, leg, saida), capture_output=True, timeout=3600)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg (legendar): " + str(r.stderr)[-300:])
    return {"falas": len(falas), "saida": str(saida), "legenda": str(leg)}


def videos_do_jogo(arquivos: list[str]) -> list[str]:
    return [f for f in arquivos if Path(f).suffix.lower() in (".mp4", ".webm", ".mkv", ".mov")]
