"""Extração automática dos TEXTOS de um jogo de Switch (sem Ryujinx, sem hactool).

Monta o RomFS (base + atualização mais nova) com `nca.py` e copia só o que a tradução precisa
(mensagens MSBT/pacotes de mensagem e fontes do idioma de origem) para ~/Emulation/romfs/<TitleID>/romfs.
Fica registrado de qual versão da atualização veio: se a atualização mudar, extrai de novo.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Optional

from . import converter, nca, switch

H = Path.home()
TEXT_DIRS = re.compile(r"(^|/)(mals?|msg|message|messages|text|texts|lms|font|fonts|localize|localization|"
                       r"language|languages)(/|$)|\.msbt(\.zs)?$|\.bffnt(\.zs)?$|(^|/)(mal|msg)[^/]*\.(sarc|szs|zs|pack)|"
                       r"(^|/)Bootup_[A-Z]{2}[a-z]{2}\.pack$|(^|/)ZsDic\.pack\.zs$",  # ZsDic: dicionário zstd (Zelda TotK)
                       re.I)
MAX_FILE = 64 << 20


def text_files(files: dict[str, tuple[int, int]], source: str = "en") -> list[str]:
    cand = [p for p, (_, size) in files.items() if TEXT_DIRS.search(p) and size <= MAX_FILE
            and not p.lower().endswith((".bntx", ".bntx.zs", ".bfres", ".bfres.zs", ".bars", ".bwav", ".bfstm"))]
    return sorted(switch.pick_language(cand, source))


def _version(p: Path) -> int:
    m = re.search(r"\[v(\d+)\]", p.name)
    return int(m.group(1)) if m else 0


def latest_update(tf: converter.TitleFiles) -> Optional[Path]:
    ups = [p for p in tf.updates if p.suffix.lower() == ".nsp"]
    return max(ups, key=_version) if ups else None


def extract_texts(rom: Path, title_id: str, roots: list[Path], source: str = "en",
                  dest_root: Path = H / "Emulation/romfs") -> tuple[Path, str]:
    """Extrai (ou reaproveita) os textos. Devolve (pasta romfs, descrição)."""
    kp = switch.keys_path()
    if not kp:
        raise nca.NcaError("o Ryujinx ainda não tem prod.keys (abra um jogo nele uma vez)")
    keys = nca.load_keys(kp)
    upd = latest_update(converter.collect(roots, title_id))
    dest = dest_root / title_id / "romfs"
    stamp = dest.parent / "extraido-por-deck-commander.json"
    want = {"base": rom.name, "update": upd.name if upd else None, "source": source}
    try:
        if json.loads(stamp.read_text("utf-8")) == want and dest.is_dir():
            return dest, "reaproveitado (mesma versão)"
    except (OSError, ValueError):
        pass
    tmp_dir = dest.parent / "descompactado.tmp"  # jogo .nsz: cópia temporária só para ler os textos
    try:
        rfs, handles = nca.open_romfs(rom, keys, upd)
    except nca.NcaError as e:
        if "NCZ" not in str(e):
            raise
        shutil.rmtree(tmp_dir, ignore_errors=True)
        r2 = converter.decompress_temp(rom, tmp_dir) if rom.suffix.lower() in (".nsz", ".xcz") else rom
        u2 = converter.decompress_temp(upd, tmp_dir) if upd and upd.suffix.lower() in (".nsz", ".xcz") else upd
        if not r2 or (upd and not u2):
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise nca.NcaError("jogo comprimido (NSZ) e não consegui descompactar uma cópia temporária "
                               "(falta espaço livre ou a ferramenta nsz)") from e
        rfs, handles = nca.open_romfs(r2, keys, u2)
    try:
        files = rfs.files()
        picked = text_files(files, source)
        if not picked:
            raise nca.NcaError("nenhum arquivo de texto reconhecido no jogo")
        tmp = dest.parent / "romfs.tmp"
        shutil.rmtree(tmp, ignore_errors=True)
        total = 0
        for p in picked:
            off, size = files[p]
            out = tmp / p
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(rfs.read_at(off, size))
            total += size
        shutil.rmtree(dest, ignore_errors=True)
        tmp.rename(dest)
        stamp.write_text(json.dumps(want, ensure_ascii=False), "utf-8")
        return dest, f"{len(picked)} arquivo(s), {total / 1e6:.1f} MB" + (" (com a atualização)" if upd else "")
    finally:
        for h in handles:
            h.close()
        shutil.rmtree(tmp_dir, ignore_errors=True)
