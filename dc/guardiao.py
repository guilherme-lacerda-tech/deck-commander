import json
import os
import shutil
import subprocess
import tarfile
import time
from collections import defaultdict
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Union

EMULADORES = {
    "RetroArch": {"tipo": "flatpak", "id": "org.libretro.RetroArch", "config": ".var/app/org.libretro.RetroArch/config/retroarch", "marca": "retroarch.cfg"},
    "PCSX2": {"tipo": "flatpak", "id": "net.pcsx2.PCSX2", "config": ".var/app/net.pcsx2.PCSX2/config/PCSX2", "marca": "inis/PCSX2.ini"},
    "Dolphin": {"tipo": "flatpak", "id": "org.DolphinEmu.dolphin-emu", "config": ".var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu", "marca": "Dolphin.ini"},
    "PPSSPP": {"tipo": "flatpak", "id": "org.ppsspp.PPSSPP", "config": ".var/app/org.ppsspp.PPSSPP/config/ppsspp", "marca": "PSP/SYSTEM/ppsspp.ini"},
    "melonDS": {"tipo": "flatpak", "id": "net.kuribo64.melonDS", "config": ".var/app/net.kuribo64.melonDS/config/melonDS", "marca": "melonDS.toml"},
    "Cemu": {"tipo": "flatpak", "id": "info.cemu.Cemu", "config": ".var/app/info.cemu.Cemu/config/Cemu", "marca": "settings.xml"},
    "RPCS3": {"tipo": "flatpak", "id": "net.rpcs3.RPCS3", "config": ".var/app/net.rpcs3.RPCS3/config/rpcs3", "marca": "config.yml"},
    "Azahar": {"tipo": "flatpak", "id": "org.azahar_emu.Azahar", "config": ".var/app/org.azahar_emu.Azahar/config/azahar-emu", "marca": "qt-config.ini"},
    "DuckStation": {"tipo": "appimage", "id": "Applications/DuckStation-x64.AppImage", "config": ".local/share/duckstation", "marca": "settings.ini"},
    "Ryujinx": {"tipo": "appimage", "id": "Downloads/publish/Ryujinx", "config": ".config/Ryujinx", "marca": "Config.json"}
}

def versao(nome: str, home: Path, run=subprocess.run) -> Optional[str]:
    emul = EMULADORES[nome]
    if emul["tipo"] == "flatpak":
        res = run(["flatpak", "info", "--show-commit", emul["id"]], capture_output=True, text=True, timeout=30)
        return res.stdout.strip() if res.returncode == 0 else None
    else:
        path = home / emul["id"]
        if not path.exists():
            return None
        stat = path.stat()
        return f"{stat.st_size}-{int(stat.st_mtime)}"

class Guardiao:
    def __init__(self, home: Path, dados: Path, run=subprocess.run, agora=time.time):
        self.home = home
        self.dados = dados
        self.run = run
        self.agora = agora
        self.estado_path = dados / "estado.json"
        self.estado = self._carregar_estado()

    def _carregar_estado(self) -> Dict[str, Dict]:
        if not self.estado_path.exists():
            return {}
        with open(self.estado_path, "r") as f:
            return json.load(f)

    def _salvar_estado(self):
        with open(self.estado_path, "w") as f:
            json.dump(self.estado, f, indent=2)

    def copiar(self, nome: str) -> Optional[Path]:
        emul = EMULADORES[nome]
        config_path = self.home / emul["config"]
        if not config_path.exists():
            return None

        versao_atual = versao(nome, self.home, self.run)
        if not versao_atual:
            return None

        timestamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(self.agora()))
        nome_arquivo = f"{versao_atual[:12]}-{timestamp}.tar.gz"
        destino = self.dados / nome / nome_arquivo
        destino.parent.mkdir(parents=True, exist_ok=True)

        fora = {"shaders", "cache", "shadercache", "logs", "states", "saves", "screenshots", "thumbnails"}

        def filtrar(tarinfo):
            if Path(tarinfo.name).name.lower() in fora or tarinfo.size > 50 * 1024 * 1024:
                return None
            return tarinfo

        with tarfile.open(destino, "w:gz") as tar:  # dentro do arquivo: a pasta com o próprio nome dela
            tar.add(config_path, arcname=config_path.name, filter=filtrar)

        # Manter só as 3 cópias mais novas (pela data do arquivo, não pelo nome)
        copias = sorted((self.dados / nome).glob("*.tar.gz"), key=lambda c: c.stat().st_mtime)
        for old in copias[:-3]:
            old.unlink()

        self.estado[nome] = {
            "versao": versao_atual,
            "copia": str(destino),
            "quando": self.agora()
        }
        self._salvar_estado()
        return destino

    def testar(self, nome: str) -> Tuple[bool, str]:
        emul = EMULADORES[nome]
        marca_path = self.home / emul["config"] / emul["marca"]
        if not marca_path.exists() or marca_path.stat().st_size == 0:
            return False, "configuração sumiu"

        if emul["tipo"] == "flatpak":
            res = self.run(["flatpak", "run", "--command=true", emul["id"]], timeout=60)
            return (True, "ok") if res.returncode == 0 else (False, "o emulador não abre mais")
        else:
            path = self.home / emul["id"]
            if not path.exists() or not os.access(path, os.X_OK):
                return False, "executável ausente ou não é executável"
            return True, "ok"

    def restaurar(self, nome: str) -> str:
        emul = EMULADORES[nome]
        estado = self.estado.get(nome)
        if not estado:
            return f"❌ {nome}: sem estado para restaurar"
        copia_path = Path(estado["copia"])
        config_path = self.home / emul["config"]
        backup_path = config_path.with_name(
            f"{config_path.name}.quebrada-{time.strftime('%Y%m%d-%H%M%S', time.localtime(self.agora()))}")
        if config_path.exists():
            config_path.rename(backup_path)  # nunca apaga: a quebrada fica ao lado
        with tarfile.open(copia_path, "r:gz") as tar:
            for member in tar.getmembers():
                partes = Path(member.name).parts
                if (member.name.startswith("/") or ".." in partes or not partes or partes[0] != config_path.name
                        or not (member.isfile() or member.isdir())):
                    continue
                tar.extract(member, path=config_path.parent)
        return f"🛡️ {nome}: configuração restaurada de {copia_path.name}"

    def voltar_versao(self, nome: str, commit_antigo: str) -> bool:
        emul = EMULADORES[nome]
        if emul["tipo"] != "flatpak":
            return False
        res = self.run(["flatpak", "update", "-y", "--user", f"--commit={commit_antigo}", emul["id"]], timeout=1800)
        if res.returncode == 0:
            try:
                self.run(["flatpak", "mask", "--user", emul["id"]], timeout=30)
            except:
                pass
        return res.returncode == 0

    def rodada(self) -> List[str]:
        avisos = []
        for nome in EMULADORES:
            versao_atual = versao(nome, self.home, self.run)
            if not versao_atual:
                continue
            estado = self.estado.get(nome, {})
            if not estado:
                self.copiar(nome)
                continue

            if estado["versao"] == versao_atual:
                if self.agora() - estado["quando"] > 24 * 3600:
                    self.copiar(nome)
                continue

            # Versão mudou, testar
            ok, msg = self.testar(nome)
            if ok:
                self.copiar(nome)
                avisos.append(f"✅ {nome} atualizou e passou no teste")
            else:
                self.restaurar(nome)
                if EMULADORES[nome]["tipo"] == "flatpak":
                    commit_antigo = estado["versao"]
                    self.voltar_versao(nome, commit_antigo)
                    ok2, _ = self.testar(nome)
                    if not ok2:
                        avisos.append(f"❌ {nome} atualizou e quebrou ({msg}): não foi possível restaurar")
                    else:
                        avisos.append(f"🛡️ {nome} atualizou e quebrou ({msg}): devolvi a configuração e voltei para a versão anterior")
                else:
                    avisos.append(f"🛡️ {nome} atualizou e quebrou ({msg}): devolvi a configuração")

        return avisos
