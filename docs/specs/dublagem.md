Arquivo: dc/dublagem.py — dublar em PT-BR um vídeo de cena de jogo (cutscene): transcreve a fala (Whisper),
traduz, gera voz em português (edge-tts) e mistura de volta no vídeo SEM mexer na imagem. Também gera legenda .srt.
Python 3.11, só biblioteca padrão, type hints, docstrings curtas em português. Chamadas externas pelo parâmetro
`run` (subprocess.run); transcrever, traduzir e falar são funções passadas por parâmetro (para testar sem IA).

@dataclass
class Fala: ini: float; fim: float; texto: str       # segundos

1) def srt(falas: list[Fala]) -> str
   Legenda SRT: blocos numerados a partir de 1, "HH:MM:SS,mmm --> HH:MM:SS,mmm", texto, linha em branco.

2) def comando_extrair_audio(video: Path, wav: Path) -> list[str]
   ["ffmpeg", "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", str(wav)]

3) def duracao(arquivo: Path, run=subprocess.run) -> float
   run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(arquivo)],
   capture_output=True, text=True, timeout=60) -> float(stdout); 0.0 se falhar.

4) def comando_mixar(video: Path, falas_audio: list[tuple[float, Path]], saida: Path, volume_original: float = 0.25)
   -> list[str]
   ffmpeg que: mantém o vídeo copiado (-c:v copy), abaixa o áudio original para `volume_original` (fica de fundo:
   música e efeitos) e põe cada arquivo de voz no seu instante. Use -i video e um -i por voz; filter_complex:
   "[0:a]volume=<v>[bg];[1:a]adelay=<ms>|<ms>[v1];[2:a]adelay=...[v2];...;[bg][v1][v2]...amix=inputs=<n+1>:
   duration=first:dropout_transition=0:normalize=0[a]" ; mapeia "-map 0:v -map [a] -c:v copy -c:a aac -b:a 160k".
   Se falas_audio vazio: devolve só a cópia do vídeo (["ffmpeg","-y","-i",video,"-c","copy",saida]).

5) def ajustar_velocidade(arquivo: Path, alvo: float, run=subprocess.run) -> Path
   Se a voz gerada durar mais que `alvo` segundos (duracao()), acelera com ffmpeg atempo (máximo 1.5; encadeia
   "atempo=1.2,atempo=1.25" se precisar) gravando "<nome>.rapido.mp3" e devolve esse caminho; senão devolve o
   original. (Mantém a voz dentro do tempo da fala original — sincronia por frase.)

6) def dublar(video: Path, saida: Path, trab: Path, transcrever, traduzir, falar, run=subprocess.run) -> dict
   - extrai o áudio (comando 2) para trab/"orig.wav";
   - falas = transcrever(trab/"orig.wav") -> list[Fala] (texto em inglês/japonês);
   - textos = traduzir([f.texto for f in falas]) -> list[str] em PT-BR (mesma ordem);
   - para cada fala i: falar(texto_pt, trab/f"v{i}.mp3"); ajustar_velocidade(..., f.fim - f.ini);
   - grava trab/"legenda.srt" com as falas traduzidas (srt()) e roda comando_mixar.
   Devolve {"falas": n, "saida": str(saida), "legenda": str(srt_path)}. Se não houver fala, copia o vídeo e
   devolve falas 0. RuntimeError se algum ffmpeg falhar (returncode != 0), com as últimas 300 letras do stderr.

7) def videos_do_jogo(arquivos: list[str]) -> list[str]
   Filtra caminhos de vídeo que dá para dublar: extensões .mp4, .webm, .mkv, .mov (sem diferenciar maiúsculas).

Exemplo de teste (precisa passar): srt([Fala(1.5, 3.25, "Olá")]) == "1\n00:00:01,500 --> 00:00:03,250\nOlá\n\n";
comando_mixar com 2 vozes nos instantes 1.0 e 2.5 gera um filter_complex com "adelay=1000|1000" e "adelay=2500|2500"
e "amix=inputs=3"; dublar() com run falso (returncode 0) e funções falsas chama falar 2 vezes e grava legenda.srt.
