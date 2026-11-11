Arquivo: dc/nuvem.py — saves na nuvem (Google Drive) com o rclone oficial: espelha as pastas de save de cada
emulador numa pasta "DeckCommander" do Drive, nos dois sentidos, sem nunca apagar em massa. Python 3.11, só
biblioteca padrão, type hints, docstrings curtas em português. Toda chamada externa pelo parâmetro `run`
(padrão subprocess.run) e downloads pelo parâmetro `baixar` (função url -> bytes) para poder testar.

1) RCLONE_VERSAO = "v1.76.0"
   RCLONE_URL = f"https://downloads.rclone.org/{RCLONE_VERSAO}/rclone-{RCLONE_VERSAO}-linux-amd64.zip"
   RCLONE_SHA256 = "<preenchido depois>"   (deixe a constante com string vazia "")
   def instalar_rclone(bin_dir: Path, baixar, sha256: str = RCLONE_SHA256) -> Path
     Se bin_dir/"rclone" já existe, devolve. Senão baixa o zip, confere hashlib.sha256 == sha256 (se diferente:
     RuntimeError "não confere"), extrai com zipfile SÓ o membro que termina em "/rclone", grava em
     bin_dir/"rclone.tmp", chmod 755, renomeia para bin_dir/"rclone". Devolve o caminho.

2) PASTAS: list[tuple[str, str]] — (nome na nuvem, caminho relativo à home). Só saves e estados, nunca jogos:
     ("RetroArch/saves",  ".var/app/org.libretro.RetroArch/config/retroarch/saves")
     ("RetroArch/states", ".var/app/org.libretro.RetroArch/config/retroarch/states")
     ("DuckStation/memcards", ".local/share/duckstation/memcards")
     ("DuckStation/savestates", ".local/share/duckstation/savestates")
     ("PCSX2/memcards", ".var/app/net.pcsx2.PCSX2/config/PCSX2/memcards")
     ("PCSX2/sstates", ".var/app/net.pcsx2.PCSX2/config/PCSX2/sstates")
     ("Dolphin/GC", ".var/app/org.DolphinEmu.dolphin-emu/data/dolphin-emu/GC")
     ("Dolphin/Wii-save", ".var/app/org.DolphinEmu.dolphin-emu/data/dolphin-emu/Wii/title")
     ("PPSSPP/SAVEDATA", ".var/app/org.ppsspp.PPSSPP/config/ppsspp/PSP/SAVEDATA")
     ("Ryujinx/save", ".config/Ryujinx/bis/user/save")
     ("Azahar/sdmc", ".var/app/org.azahar_emu.Azahar/data/azahar-emu/sdmc/Nintendo 3DS")
     ("melonDS/saves", ".var/app/net.kuribo64.melonDS/data/melonDS")

3) def conf_rclone(token_json: str) -> str
   Conteúdo do rclone.conf com um remoto chamado "gdrive":
     [gdrive]
     type = drive
     scope = drive.file
     token = <token_json numa linha só (json.dumps(json.loads(token_json)))>
   (scope drive.file: o rclone só enxerga o que ele mesmo criou no Drive — não lê o resto do seu Drive.)
   ValueError se token_json não for JSON com "access_token" e "refresh_token".

4) class Nuvem:
     __init__(self, home: Path, rclone: Path, conf: Path, estado: Path, run=subprocess.run)
       estado = arquivo JSON {nome_nuvem: {"feito": float, "ok": bool, "msg": str}}
     configurada(self) -> bool : conf existe e contém "[gdrive]".
     comando(self, local: Path, nome: str, primeira: bool) -> list[str]
       [str(rclone), "bisync", str(local), f"gdrive:DeckCommander/{nome}", "--config", str(conf),
        "--create-empty-src-dirs", "--compare", "size,modtime", "--conflict-resolve", "newer",
        "--conflict-loser", "num", "--max-delete", "10", "--resilient", "--recover",
        "--workdir", str(estado.parent / "bisync")] + (["--resync"] if primeira else [])
     sincronizar(self) -> list[str]
       Para cada PASTA cuja pasta local existe: primeira = nome ainda não tem "ok": True no estado.
       Roda o comando (capture_output=True, text=True, timeout=1800). Se returncode != 0 e a saída contém
       "--resync" (o rclone pede resync), roda de novo com primeira=True uma vez. Grava no estado
       {"feito": time.time(), "ok": returncode == 0, "msg": últimas 300 letras de stderr}.
       Devolve frases em português: "☁️ <nome>: em dia" ou "⚠️ <nome>: <msg curta>". Pastas inexistentes são
       puladas sem frase.
     resumo(self) -> str : uma linha por pasta do estado: "✅ nome (há X min)" ou "⚠️ nome: msg".

Exemplo de teste (precisa passar):
   - conf_rclone('{"access_token":"a","refresh_token":"r","expiry":"x"}') contém "scope = drive.file" e "token = {"
   - conf_rclone('{"x":1}') levanta ValueError
   - com home temporária contendo só ".local/share/duckstation/memcards", run falso que devolve returncode 0:
     Nuvem(...).sincronizar() == ["☁️ DuckStation/memcards: em dia"] e o 1º comando tem "--resync";
     rodando de novo, o comando NÃO tem "--resync".
