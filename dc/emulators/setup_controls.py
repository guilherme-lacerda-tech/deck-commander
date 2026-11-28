"""Prepara os controles do primeiro jogador antes do primeiro lançamento Flatpak no Steam Deck."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

PROFILES = Path(__file__).resolve().parents[2] / "config/controller-profiles"
LAYOUTS = {
    "org.azahar_emu.Azahar": ("azahar.ini", "config/azahar-emu/qt-config.ini"),
    "info.cemu.Cemu": ("cemu.xml", "config/Cemu/controllerProfiles/controller0.xml"),
    "net.rpcs3.RPCS3": ("rpcs3.yml", "config/rpcs3/input_configs/global/Default.yml"),
}


def prepare(cmd, home=None, dmi=Path("/sys/class/dmi/id")):
    """Retorna o arquivo criado. Perfis existentes e outros dispositivos ficam com a configuração atual."""
    if len(cmd) < 3 or Path(cmd[0]).name != "flatpak" or cmd[1] != "run" or cmd[2] not in LAYOUTS:
        return None
    if not (dmi / "sys_vendor").is_file() or (dmi / "sys_vendor").read_text().strip() != "Valve":
        return None
    if (dmi / "board_name").read_text().strip() not in {"Jupiter", "Galileo"}:
        return None
    home = Path(home or Path.home())
    app = home / ".var/app" / cmd[2]
    template, rel = LAYOUTS[cmd[2]]
    target = app / rel
    if target.exists() or target.is_symlink():
        return None
    if cmd[2] == "info.cemu.Cemu":
        # Cemu migra perfis de versões anteriores. Não tome precedência sobre esse fluxo.
        legacy = [app / "data/cemu/controllerProfiles", target.parent]
        if any(folder.is_dir() and any(folder.iterdir()) for folder in legacy):
            return None
    if cmd[2] == "net.rpcs3.RPCS3" and target.parent.exists() and any(target.parent.iterdir()):
        return None
    if target.resolve().is_relative_to(app.resolve()) is False:
        return None
    contents = (PROFILES / template).read_bytes()
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".dc-controle-", delete=False) as fd:
        scratch = Path(fd.name)
        try:
            fd.write(contents)
            fd.flush()
            os.fsync(fd.fileno())
        except BaseException:
            fd.close()
            scratch.unlink(missing_ok=True)
            raise
    try:
        os.link(scratch, target)
        return target
    except FileExistsError:
        return None
    finally:
        scratch.unlink(missing_ok=True)
