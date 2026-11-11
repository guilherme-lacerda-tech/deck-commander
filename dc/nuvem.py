"""Saves na nuvem (Google Drive) com o rclone oficial — docs/specs/nuvem.md. Só pastas de save, nunca jogos.

    python3 -m dc.nuvem configurar   (entrada: token do Google, mandado pelo tools/pc/nuvem-google.ps1)
    python3 -m dc.nuvem sincronizar | resumo
"""
import hashlib
import json
import subprocess
import time
import zipfile
from pathlib import Path
from typing import List, Tuple, Callable

RCLONE_VERSAO = "v1.76.0"
RCLONE_URL = f"https://downloads.rclone.org/{RCLONE_VERSAO}/rclone-{RCLONE_VERSAO}-linux-amd64.zip"
RCLONE_SHA256 = "b00f00b3266c3764413afe599d3ec316f6f43b3e0ea8a0bc1d186d2133e46df7"  # SHA256SUMS oficial

PASTAS: List[Tuple[str, str]] = [
    ("RetroArch/saves", ".var/app/org.libretro.RetroArch/config/retroarch/saves"),
    ("RetroArch/states", ".var/app/org.libretro.RetroArch/config/retroarch/states"),
    ("DuckStation/memcards", ".local/share/duckstation/memcards"),
    ("DuckStation/savestates", ".local/share/duckstation/savestates"),
    ("PCSX2/memcards", ".var/app/net.pcsx2.PCSX2/config/PCSX2/memcards"),
    ("PCSX2/sstates", ".var/app/net.pcsx2.PCSX2/config/PCSX2/sstates"),
    ("Dolphin/GC", ".var/app/org.DolphinEmu.dolphin-emu/data/dolphin-emu/GC"),
    ("Dolphin/Wii-save", ".var/app/org.DolphinEmu.dolphin-emu/data/dolphin-emu/Wii/title"),
    ("PPSSPP/SAVEDATA", ".var/app/org.ppsspp.PPSSPP/config/ppsspp/PSP/SAVEDATA"),
    ("Ryujinx/save", ".config/Ryujinx/bis/user/save"),
    ("Azahar/sdmc", ".var/app/org.azahar_emu.Azahar/data/azahar-emu/sdmc/Nintendo 3DS"),
    ("melonDS/saves", ".var/app/net.kuribo64.melonDS/data/melonDS")
]

def instalar_rclone(bin_dir: Path, baixar: Callable[[str], bytes], sha256: str = RCLONE_SHA256) -> Path:
    """Instala o rclone na pasta bin_dir, baixando e verificando o checksum."""
    rclone_path = bin_dir / "rclone"
    if rclone_path.exists():
        return rclone_path

    zip_data = baixar(RCLONE_URL)
    if hashlib.sha256(zip_data).hexdigest() != sha256:
        raise RuntimeError("o rclone baixado não confere (sha256) — não instalei")

    import io
    with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
        membro = next((m for m in zf.namelist() if m.endswith("/rclone")), None)
        if not membro:
            raise RuntimeError("rclone não encontrado no zip")
        conteudo = zf.read(membro)
    bin_dir.mkdir(parents=True, exist_ok=True)
    tmp = bin_dir / "rclone.tmp"
    tmp.write_bytes(conteudo)
    tmp.chmod(0o755)
    tmp.replace(rclone_path)
    return rclone_path

def conf_rclone(token_json: str) -> str:
    """Gera conteúdo do arquivo de configuração rclone com remoto 'gdrive'."""
    try:
        token = json.loads(token_json)
        if not all(k in token for k in ("access_token", "refresh_token")):
            raise ValueError("token_json deve conter access_token e refresh_token")
    except json.JSONDecodeError:
        raise ValueError("token_json inválido")

    return f"""[gdrive]
type = drive
scope = drive.file
token = {json.dumps(token)}
"""

class Nuvem:
    def __init__(self, home: Path, rclone: Path, conf: Path, estado: Path, run=subprocess.run):
        self.home = home
        self.rclone = rclone
        self.conf = conf
        self.estado = estado
        self.run = run

    def configurada(self) -> bool:
        """Verifica se o arquivo de configuração existe e contém [gdrive]."""
        return self.conf.exists() and "[gdrive]" in self.conf.read_text()

    def comando(self, local: Path, nome: str, primeira: bool) -> List[str]:
        """Monta o comando rclone bisync para sincronizar uma pasta."""
        cmd = [
            str(self.rclone), "bisync", str(local), f"gdrive:DeckCommander/{nome}",
            "--config", str(self.conf),
            "--create-empty-src-dirs", "--compare", "size,modtime",
            "--conflict-resolve", "newer", "--conflict-loser", "num",
            "--max-delete", "10", "--resilient", "--recover",
            "--workdir", str(self.estado.parent / "bisync")
        ]
        if primeira:
            cmd.append("--resync")
        return cmd

    def sincronizar(self) -> List[str]:
        """Sincroniza todas as pastas configuradas."""
        try:
            estado_atual = json.loads(self.estado.read_text()) if self.estado.exists() else {}
        except Exception:
            estado_atual = {}

        resultados = []
        for nome_nuvem, caminho_relativo in PASTAS:
            local = self.home / caminho_relativo
            if not local.exists():
                continue

            primeira = nome_nuvem not in estado_atual or not estado_atual[nome_nuvem].get("ok", False)
            cmd = self.comando(local, nome_nuvem, primeira)

            try:
                res = self.run(cmd, capture_output=True, text=True, timeout=1800)
                if res.returncode != 0 and "--resync" in res.stderr:
                    # Tenta novamente com --resync
                    cmd = self.comando(local, nome_nuvem, True)
                    res = self.run(cmd, capture_output=True, text=True, timeout=1800)

                ok = res.returncode == 0
                msg = res.stderr[-300:] if res.stderr else ""
                estado_atual[nome_nuvem] = {
                    "feito": time.time(),
                    "ok": ok,
                    "msg": msg
                }
                self.estado.parent.mkdir(parents=True, exist_ok=True)
                self.estado.write_text(json.dumps(estado_atual, indent=2))

                if ok:
                    resultados.append(f"☁️ {nome_nuvem}: em dia")
                else:
                    resultados.append(f"⚠️ {nome_nuvem}: {msg.strip()}")
            except Exception as e:
                estado_atual[nome_nuvem] = {
                    "feito": time.time(),
                    "ok": False,
                    "msg": str(e)
                }
                self.estado.parent.mkdir(parents=True, exist_ok=True)
                self.estado.write_text(json.dumps(estado_atual, indent=2))
                resultados.append(f"⚠️ {nome_nuvem}: erro ao sincronizar")

        return resultados

    def resumo(self) -> str:
        """Retorna um resumo das últimas sincronizações."""
        try:
            estado = json.loads(self.estado.read_text()) if self.estado.exists() else {}
        except Exception:
            return ""

        linhas = []
        for nome, dados in estado.items():
            if dados["ok"]:
                minutos = int((time.time() - dados["feito"]) / 60)
                linhas.append(f"✅ {nome} (há {minutos} min)")
            else:
                linhas.append(f"⚠️ {nome}: {dados['msg'][:50]}...")
        return "\n".join(linhas)


def _baixar(url: str) -> bytes:
    import urllib.request
    with urllib.request.urlopen(url, timeout=120) as r:  # noqa: S310 — endereço fixo do site oficial
        return r.read()


def do_deck():
    """Nuvem com os caminhos do Deck Commander (rclone em data/bin, configuração em config/)."""
    from .paths import get_paths
    paths = get_paths()
    return Nuvem(Path.home(), paths.data / "bin" / "rclone", paths.config / "rclone.conf", paths.state / "nuvem.json"), paths


def main(argv: list) -> int:
    import sys
    n, paths = do_deck()
    if argv[:1] == ["configurar"]:
        conf = conf_rclone(sys.stdin.read().strip().lstrip("﻿"))
        instalar_rclone(paths.data / "bin", _baixar)
        n.conf.write_text(conf, "utf-8")
        n.conf.chmod(0o600)
        print("\n".join(n.sincronizar()) or "Nuvem ligada (nenhuma pasta de save ainda).")
        return 0
    if argv[:1] == ["sincronizar"]:
        print("\n".join(n.sincronizar()) if n.configurada() else "Nuvem não configurada (rode tools/pc/nuvem-google.ps1 no PC).")
        return 0
    print(n.resumo() or "Nada sincronizado ainda.")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
