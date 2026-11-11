Arquivo: dc/texturas.py — instalar pacotes de texturas HD (de um link que o usuário escolheu) na pasta certa do
emulador e ligar a opção de usar texturas. Python 3.11, só biblioteca padrão, type hints, docstrings curtas em
português. Chamadas externas pelo parâmetro `run` (subprocess.run) e downloads pelo parâmetro `baixar`
(função (url, destino: Path) -> None) para poder testar.

1) def serial_ps2(iso: Path) -> str | None
   Imagem ISO de PS2 (setores de 2048 bytes, ISO9660): descritor primário no setor 16 (byte 16*2048); registro da
   raiz nos bytes 156..189 desse setor; dentro do diretório raiz procure o arquivo "SYSTEM.CNF;1" (registro:
   byte 0 = tamanho, bytes 2..5 = setor LE, 10..13 = tamanho LE, 32 = tamanho do nome, 33.. = nome). Leia o
   SYSTEM.CNF e ache a linha "BOOT2 = cdrom0:\\SLUS_203.12;1": devolva "SLUS-20312" (troca "_" por "-" e remove
   o "."). None se não achar.

2) def id_gc(iso: Path) -> str | None
   GameCube/Wii (.iso/.gcm): os 6 primeiros bytes do arquivo em ASCII (ex. "GALE01"); None se não for A-Z0-9.

3) PASTAS = {
     "ps2": ".var/app/net.pcsx2.PCSX2/config/PCSX2/textures/{id}/replacements",
     "gc":  ".var/app/org.DolphinEmu.dolphin-emu/data/dolphin-emu/Load/Textures/{id}",
     "wii": ".var/app/org.DolphinEmu.dolphin-emu/data/dolphin-emu/Load/Textures/{id}",
   }
   def pasta_destino(home: Path, console: str, jogo_id: str) -> Path

4) def ligar_opcao(home: Path, console: str) -> None
   ps2: no arquivo home/".var/app/net.pcsx2.PCSX2/config/PCSX2/inis/PCSX2.ini", seção [EmuCore/GS]:
        LoadTextureReplacements = true e LoadTextureReplacementsAsync = true (troca se existir, senão acrescenta
        na seção; cria a seção no fim se não existir).
   gc/wii: home/".var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu/GFX.ini", seção [Settings]:
        HiresTextures = True e CacheHiresTextures = False.
   Antes da 1ª mudança guarda cópia "<arquivo>.antes-texturas" (só se ainda não existir).

5) def extrair(pacote: Path, destino: Path, run=subprocess.run) -> int
   .zip: zipfile, extração segura (ignora membros com caminho absoluto ou ".."). .7z/.rar: run(["7z", "x", "-y",
   f"-o{destino}", str(pacote)], capture_output=True) — RuntimeError("7z não instalado no Deck") se FileNotFoundError.
   Depois "achata" um nível: se o destino ficou com UMA única pasta dentro e nenhum arquivo, move o conteúdo dela
   para o destino e apaga a pasta vazia. Devolve quantos arquivos ficaram no destino (recursivo).

6) def instalar(home: Path, console: str, rom: Path, url: str, baixar, run=subprocess.run, tmp: Path | None = None) -> str
   console "ps2" -> serial_ps2(rom); "gc"/"wii" -> id_gc(rom); outro console -> ValueError("texturas HD só para
   PS2, GameCube e Wii por enquanto"). Sem id -> ValueError("não consegui ler o código do jogo").
   Baixa o pacote para tmp (padrão: home/".cache/deck-commander/texturas/<nome do arquivo do link>"), extrai em
   pasta_destino, liga_opcao, apaga o pacote baixado. Devolve frase em português:
   "🖼️ Texturas HD instaladas: <n> arquivos em <id>. Vale na próxima vez que abrir o jogo."

Exemplo de teste (precisa passar): ISO falsa de PS2 com SYSTEM.CNF contendo "BOOT2 = cdrom0:\SLUS_203.12;1\n"
→ serial_ps2 == "SLUS-20312"; instalar() com baixar falso que grava um .zip com "pack/a.png" e "pack/b.dds" →
2 arquivos em .../textures/SLUS-20312/replacements/ (sem a pasta "pack"), e PCSX2.ini com
"LoadTextureReplacements = true" na seção [EmuCore/GS].
