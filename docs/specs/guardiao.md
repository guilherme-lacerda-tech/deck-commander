Arquivo: dc/guardiao.py — Guardião dos emuladores: guarda cópia das configurações de cada emulador, percebe quando
o emulador foi atualizado, testa se ele ainda abre e se a configuração continua lá; se quebrou, devolve a
configuração e (Flatpak) volta para a versão anterior. Python 3.11, só biblioteca padrão, type hints, docstrings
curtas em português. TODA chamada externa passa pelo parâmetro `run` (padrão subprocess.run) para poder testar.

1) EMULADORES: dict[str, dict] — nome → {"tipo": "flatpak"|"appimage", "id": str, "config": str, "marca": str}
   "config" = pasta de configuração relativa à home; "marca" = arquivo (relativo à pasta config) que precisa
   continuar existindo e não-vazio depois da atualização.
     "RetroArch":   flatpak org.libretro.RetroArch,  config ".var/app/org.libretro.RetroArch/config/retroarch", marca "retroarch.cfg"
     "PCSX2":       flatpak net.pcsx2.PCSX2,         config ".var/app/net.pcsx2.PCSX2/config/PCSX2", marca "inis/PCSX2.ini"
     "Dolphin":     flatpak org.DolphinEmu.dolphin-emu, config ".var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu", marca "Dolphin.ini"
     "PPSSPP":      flatpak org.ppsspp.PPSSPP,       config ".var/app/org.ppsspp.PPSSPP/config/ppsspp", marca "PSP/SYSTEM/ppsspp.ini"
     "melonDS":     flatpak net.kuribo64.melonDS,    config ".var/app/net.kuribo64.melonDS/config/melonDS", marca "melonDS.toml"
     "Cemu":        flatpak info.cemu.Cemu,          config ".var/app/info.cemu.Cemu/config/Cemu", marca "settings.xml"
     "RPCS3":       flatpak net.rpcs3.RPCS3,         config ".var/app/net.rpcs3.RPCS3/config/rpcs3", marca "config.yml"
     "Azahar":      flatpak org.azahar_emu.Azahar,   config ".var/app/org.azahar_emu.Azahar/config/azahar-emu", marca "qt-config.ini"
     "DuckStation": appimage "Applications/DuckStation-x64.AppImage", config ".local/share/duckstation", marca "settings.ini"
     "Ryujinx":     appimage "Applications/Ryujinx.AppImage", config ".config/Ryujinx", marca "Config.json"

2) def versao(nome: str, home: Path, run=subprocess.run) -> str | None
   flatpak: roda ["flatpak", "info", "--show-commit", id] (capture_output=True, text=True, timeout=30);
            devolve stdout.strip() se returncode == 0, senão None.
   appimage: se o arquivo home/id existe, devolve f"{tamanho}-{int(mtime)}"; senão None.

3) class Guardiao:
     __init__(self, home: Path, dados: Path, run=subprocess.run, agora=time.time)
        dados = pasta própria (ex.: ~/.local/share/deck-commander/guardiao); estado em dados/"estado.json":
        {nome: {"versao": str, "copia": "arquivo.tar.gz", "quando": float}}
     copiar(self, nome) -> Path | None
        Se a pasta de config existe: cria dados/nome/<versao-curta 12 chars>-<AAAAmmdd-HHMMSS>.tar.gz com tarfile
        (modo "w:gz"), contendo a pasta config (arcname = nome da pasta). IGNORA arquivos maiores que 50 MB e as
        subpastas chamadas "shaders", "cache", "shadercache", "logs", "states", "saves", "screenshots",
        "thumbnails" (filtro do tarfile.add). Mantém só as 3 cópias mais novas daquele emulador (apaga as mais
        antigas). Atualiza o estado (versao, copia, quando). Devolve o caminho.
     testar(self, nome) -> tuple[bool, str]
        a) a marca existe e tem tamanho > 0; senão (False, "configuração sumiu").
        b) flatpak: run(["flatpak", "run", "--command=true", id], timeout=60) com returncode 0 (o pacote abre);
           appimage: o arquivo existe e é executável (os.access X_OK).
        Devolve (True, "ok") ou (False, motivo).
     restaurar(self, nome) -> str
        Extrai a cópia do estado POR CIMA da pasta config (antes renomeia a pasta atual para
        "<pasta>.quebrada-<data>" — nunca apaga). Extração segura: só membros comuns/pastas, sem caminho absoluto
        nem "..". Devolve uma frase em português.
     voltar_versao(self, nome, commit_antigo: str) -> bool
        Só flatpak: run(["flatpak", "update", "-y", "--user", f"--commit={commit_antigo}", id], timeout=1800);
        True se returncode == 0. (Depois disso, também roda ["flatpak", "mask", "--user", id] para não atualizar
        de novo sozinho até o usuário liberar; ignore falha do mask.)
     rodada(self) -> list[str]
        Para cada emulador instalado (versao() não é None):
          - sem estado ainda: copiar() e segue (primeira vez).
          - mesma versão: se a última cópia tem mais de 24 h, copiar() de novo.
          - versão mudou (= foi atualizado): testar(). Se ok: copiar() e registra aviso
            "✅ <nome> atualizou e passou no teste". Se falhou: restaurar(); se flatpak, voltar_versao(versão
            antiga do estado) e testar() de novo; avisos em português dizendo o que aconteceu
            ("🛡️ <nome> atualizou e quebrou (<motivo>): devolvi a configuração e voltei para a versão anterior").
        Devolve a lista de avisos (para o bot mandar no Telegram).

Exemplo de teste (precisa passar), com home e dados em pastas temporárias e run falso:
   - cria home/".var/app/org.libretro.RetroArch/config/retroarch/retroarch.cfg" com 'a = "1"'
   - run falso responde "abc123\n" para flatpak info do RetroArch e returncode 1 (não instalado) para os outros
   - Guardiao(...).rodada() == [] e existe 1 .tar.gz em dados/"RetroArch"
   - muda a resposta para "def456", apaga retroarch.cfg, rodada() → aviso com "quebrou" e retroarch.cfg volta
     com 'a = "1"'; houve chamada com "--commit=abc123".
