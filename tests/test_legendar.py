"""Legenda em português é o PADRÃO (pedido do usuário 11/11/2026); a dublagem fica como opção (--dublar)."""
import subprocess
from pathlib import Path

from dc import dublagem as D


def test_comando_legendar():
    c = D.comando_legendar(Path("C:/a b/v.mp4"), Path("C:/t/it's.srt"), Path("saida.mp4"))
    assert c[0] == D.FFMPEG and "-vf" in c and "libx264" in c and c[-1] == "saida.mp4"
    filtro = c[c.index("-vf") + 1]
    assert filtro.startswith(r"subtitles='C\:/t/it\'s.srt'")  # ':' e apóstrofo escapados para o filtro do ffmpeg
    assert c[c.index("-map") + 1] == "0:v:0" and "0:a?" in c and c[c.index("-c:a") + 1] == "copy"
    w = D.comando_legendar(Path("v.webm"), Path("l.srt"), Path("o.webm"))
    assert "libvpx-vp9" in w and "libx264" not in w


def test_legendar_nao_gera_voz(tmp_path):
    chamadas = []

    def run(cmd, **k):
        chamadas.append(cmd)
        err = "Duration: 00:00:10.00, start\n Stream #0:1: Audio: aac" if "-i" in cmd and len(cmd) <= 4 else ""
        return subprocess.CompletedProcess(cmd, 0, "", err)
    falas = [D.Fala(0.5, 2.0, "Hello there")]
    r = D.legendar(Path("v.mp4"), tmp_path / "o.mp4", tmp_path / "t", lambda w: falas, lambda ts: ["Olá"], run=run)
    assert r["falas"] == 1 and "Olá" in Path(r["legenda"]).read_text("utf-8")
    assert any("-vf" in c for c in chamadas)
