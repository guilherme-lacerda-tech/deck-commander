"""Tradução de jogos da engine Trinity (Pokémon Legends Z-A; o formato é o mesmo de Scarlet/Violet).

1. Extrai (uma vez, com cache) do `arc/data.trpfs` só os pacotes de mensagem do idioma de origem e as fontes,
   lendo o RomFS (base + atualização) com `nca.py`. Os pacotes são descomprimidos com `oodle.py`.
2. Cada `.dat` precisa ser relido e regravado sem mudar um byte; o que não passar é pulado.
3. Traduz com `ia.translate` (códigos do jogo viram ⟦n⟧) e reajusta as quebras de linha à largura original.
4. Mod LayeredFS do Ryujinx: os `.dat` traduzidos soltos em romfs/<caminho> + `romfs/arc/data.trpfd` sem os
   hashes desses arquivos (assim o jogo lê os soltos, técnica do Trinity Mod Loader). O jogo nunca é alterado.
"""
from __future__ import annotations

import json
import re
import shutil
import struct
from pathlib import Path
from typing import Callable, Optional

from ..paths import Paths
from . import ia, trinity, trinity_msg as tm

TRPFD = "arc/data.trpfd"
TRPFS = "arc/data.trpfs"
MSG_ROOT = "ik_message/dat"
LANG_DIR = {"en": "English", "es": "Spanish", "fr": "French", "de": "German", "it": "Italian", "ja": "JPN"}
FONT_PACK = re.compile(r"^arc/uifontbin.*\.bf[ot]tf\.trpak$")
BOX_BREAKS = (0xBE00, 0xBE01)


def is_trinity(files: dict) -> bool:
    return TRPFD in files and TRPFS in files


# ============================================================================ caminhos
def pack_prefix(lang_dir: str) -> str:
    return "arc/" + MSG_ROOT.replace("/", "") + lang_dir


def resolve_paths(pack_name: str, lang_dir: str, hashes: set[int]) -> dict[int, str]:
    """O nome do pacote é o caminho sem as barras (ex.: arc/ik_messagedatEnglishcommonbag.tbl.trpak).
    Recupera os caminhos reais testando onde ficam as barras e conferindo o hash FNV-1a com o pacote."""
    pre = pack_prefix(lang_dir)
    if not (pack_name.startswith(pre) and pack_name.endswith(".trpak")):
        return {}
    rest = pack_name[len(pre):-len(".trpak")]
    stem = rest.rsplit(".", 1)[0]
    base = f"{MSG_ROOT}/{lang_dir}/"
    found: dict[int, str] = {}
    n = len(stem)
    for i in range(1, n):
        for j in [None] + list(range(i + 1, n)):
            parts = [stem[:i], stem[i:]] if j is None else [stem[:i], stem[i:j], stem[j:]]
            for ext in (".dat", ".tbl"):
                p = base + "/".join(parts) + ext
                h = trinity.fnv1a64(p)
                if h in hashes:
                    found[h] = p
        if len(found) == len(hashes):
            break
    return found


# ============================================================================ extração (com cache)
def ryujinx_update(tid: str) -> Optional[Path]:
    """Atualização que o Ryujinx REALMENTE carrega (games/<tid>/updates.json, campo "selected").
    Sem ela o jogo roda a versão base. O data.trpfd do mod precisa ser o dessa mesma versão: o de outra
    versão aponta para pacotes errados e o jogo trava ao abrir."""
    from . import switch
    for d in switch.RYU_DIRS:
        p = d / "games" / tid.lower() / "updates.json"
        try:
            sel = json.loads(p.read_text("utf-8")).get("selected") or ""
        except (OSError, ValueError, AttributeError):
            continue
        return Path(sel) if sel and Path(sel).is_file() else None
    return None


def cache_dir(paths: Paths, tid: str) -> Path:
    return paths.data / "traducao" / "trinity" / tid.upper()


def extract(paths: Paths, rom: Path, tid: str, roots: list[Path], source: str = "en",
            log: Callable[[str], None] = lambda s: None) -> tuple[Path, dict]:
    """Copia data.trpfd + mensagens do idioma de origem + diagnóstico da fonte para o cache.
    Devolve (pasta, info). Reaproveita se base/atualização/idioma não mudaram."""
    from . import nca, switch
    kp = switch.keys_path()
    if not kp:
        raise nca.NcaError("o Ryujinx ainda não tem prod.keys (abra um jogo nele uma vez)")
    keys = nca.load_keys(kp)
    upd = ryujinx_update(tid)
    lang_dir = LANG_DIR.get(source, "English")
    dest = cache_dir(paths, tid)
    stamp = dest / "extraido.json"
    want = {"base": rom.name, "update": upd.name if upd else None, "lang": lang_dir, "v": 2}
    try:
        info = json.loads(stamp.read_text("utf-8"))
        if {k: info.get(k) for k in want} == want and (dest / "data.trpfd").exists():
            return dest, info
    except (OSError, ValueError):
        pass
    rfs, handles = nca.open_romfs(rom, keys, upd)
    try:
        files = rfs.files()
        if not is_trinity(files):
            raise trinity.TrinityError("não é um jogo da engine Trinity")
        o, s = files[TRPFD]
        fd_raw = rfs.read_at(o, s)
        fo, fsize = files[TRPFS]
        arc = trinity.Archive(fd_raw, lambda off, n: rfs.read_at(fo + off, n), fsize)
        tmp = dest.with_name(dest.name + ".tmp")
        shutil.rmtree(tmp, ignore_errors=True)
        (tmp / "romfs").mkdir(parents=True)
        (tmp / "data.trpfd").write_bytes(fd_raw)
        pre = pack_prefix(lang_dir)
        msgs = []
        for name in arc.fd.pack_names:
            if not name.startswith(pre):
                continue
            entries = arc.pack(name)
            where = resolve_paths(name, lang_dir, {e.hash for e in entries})
            for e in entries:
                p = where.get(e.hash)
                if not p or not p.endswith(".dat"):
                    continue
                out = tmp / "romfs" / p
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(e.content())
                msgs.append(p)
            arc._cache.clear()
        if not msgs:
            raise trinity.TrinityError(f"nenhuma mensagem em {lang_dir} no jogo")
        fonts = {}
        for name in arc.fd.pack_names:
            if FONT_PACK.match(name):
                try:
                    data = arc.pack(name)[0].content()
                    fonts[name.split("/")[-1]] = trinity.missing_ptbr(trinity.otf_chars(trinity.decrypt_bfotf(data)))
                except (trinity.TrinityError, struct.error, IndexError) as e:
                    fonts[name.split("/")[-1]] = f"? ({e})"
                arc._cache.clear()
        info = {**want, "mensagens": sorted(msgs), "fontes": fonts}
        (tmp / "extraido.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), "utf-8")
        shutil.rmtree(dest, ignore_errors=True)
        tmp.rename(dest)
        log(f"{len(msgs)} arquivos de mensagem extraídos")
        return dest, info
    finally:
        for h in handles:
            h.close()


# ============================================================================ texto ↔ IA
def to_marked(text: str) -> str:
    out, k = [], 0
    for ch in text:
        if ch == "\x00":
            out.append(f"{ia.PH_OPEN}{k}{ia.PH_CLOSE}")
            k += 1
        else:
            out.append(ch)
    return "".join(out)


def from_marked(marked: str, codes: list[tuple[int, ...]]) -> list[int]:
    """Texto traduzido com ⟦n⟧ (em qualquer ordem) -> palavras UTF-16 com os códigos originais."""
    words, used, last = [], set(), 0
    for m in ia._PH.finditer(marked):
        words += tm.join_codes(marked[last:m.start()], [])
        k = int(m.group(1))
        if k >= len(codes) or k in used:
            raise tm.MsgError("marcador inválido")
        used.add(k)
        words += codes[k]
        last = m.end()
    words += tm.join_codes(marked[last:], [])
    if len(used) != len(codes):
        raise tm.MsgError("marcador faltando")
    return words


def _is_box(code: tuple[int, ...]) -> bool:
    return len(code) > 2 and code[0] == tm.VAR and code[2] in BOX_BREAKS


def _visible_len(s: str) -> int:
    return len(ia._PH.sub("", s))


def layout(src_text: str, src_codes: list, marked: str) -> tuple[str, list, bool]:
    """Reajusta as quebras de linha do texto traduzido (com ⟦n⟧) à largura do original.
    Só mexe em texto de várias linhas. Devolve (texto marcado, códigos, cabe_na_caixa)."""
    if "\n" not in src_text:
        return marked, src_codes, True
    segs, cur, k = [], [], 0
    for ch in src_text:  # segmentos do original separados por quebra de caixa
        if ch == "\x00":
            if _is_box(src_codes[k]):
                segs.append("".join(cur)); cur = []
            k += 1
        else:
            cur.append(ch)
    segs.append("".join(cur))
    lines = [ln for s in segs for ln in s.strip("\n").split("\n")]
    width = max(30, max(len(ln) for ln in lines))
    per_box = max(2, max(len(s.strip("\n").split("\n")) for s in segs))
    dialog = any(_is_box(c) for c in src_codes)
    # divide o traduzido nas quebras de caixa que a IA manteve
    parts = re.split(r"(⟦\d+⟧)", marked)
    boxes: list[list[str]] = [[]]
    seps: list[str] = []
    for p in parts:
        m = ia._PH.fullmatch(p)
        if m and _is_box(src_codes[int(m.group(1))]):
            seps.append(p)
            boxes.append([])
        else:
            boxes[-1].append(p)
    codes = list(src_codes)
    out = []
    fits = True
    for bi, b in enumerate(boxes):
        words = "".join(b).replace("\n", " ").split()
        wrapped, line = [], ""
        for w in words:
            cand = f"{line} {w}" if line else w
            if line and _visible_len(cand) > width:
                wrapped.append(line); line = w
            else:
                line = cand
        if line or not wrapped:
            wrapped.append(line)
        chunks = [wrapped[i:i + per_box] for i in range(0, len(wrapped), per_box)]
        if len(chunks) > 1 and not dialog:
            fits = False  # texto sem caixas (descrição): não dá para abrir caixa nova
            chunks = [wrapped]
        pieces = []
        for ci, ch in enumerate(chunks):
            if ci:  # caixa nova como o jogo faz: fim de frase limpa a caixa (BE01), senão rola (BE00)
                prev = pieces[-1].rstrip()
                kind = 0xBE01 if prev and prev[-1] in ".!?…" else 0xBE00
                codes.append((tm.VAR, 1, kind))
                pieces.append(f"{ia.PH_OPEN}{len(codes) - 1}{ia.PH_CLOSE}\n")
            pieces.append("\n".join(ch))
        out.append("".join(pieces))
        if bi < len(seps):
            out.append(seps[bi] + "\n")
    return "".join(out), codes, fits


# ============================================================================ pipeline
def translate_game(paths: Paths, tid: str, rom: Path, roots: list[Path], game_name: str = "",
                   force_font: bool = False, chain=None, log: Callable[[str], None] = lambda s: None,
                   progress=lambda d, t: None, should_pause=lambda: False):
    from . import switch
    cfg = ia.load_cfg(paths)
    rep = switch.Report(tid)
    src_dir, info = extract(paths, rom, tid, roots, cfg["idioma_origem"], log)
    bad_fonts = {k: v for k, v in info.get("fontes", {}).items() if v}
    if not info.get("fontes"):
        rep.font, rep.font_ok = "⚠️ não achei as fontes do jogo para conferir os acentos", False
    elif bad_fonts:
        rep.font, rep.font_ok = "⚠️ a fonte do jogo não tem: " + "; ".join(f"{v} ({k})" for k, v in bad_fonts.items()), False
    else:
        rep.font = "fonte do jogo tem os acentos do português ✅"
    rep.compression.add("oodle")
    if not rep.font_ok and not force_font:
        rep.errors.append("tradução bloqueada: a fonte do jogo não mostra os acentos do português "
                          "(use /traduzir <jogo> --forcar para aplicar assim mesmo)")
        return rep
    dats: dict[str, tm.MsgDat] = {}
    for rel in info["mensagens"]:
        raw = (src_dir / "romfs" / rel).read_bytes()
        try:
            m = tm.read_dat(raw)
        except tm.MsgError as e:
            rep.skipped_files.append(f"{rel} ({e})")
            continue
        if tm.write_dat(m) != raw:
            rep.skipped_files.append(f"{rel} (formato não reproduzido com exatidão)")
            continue
        dats[rel] = m
    rep.msbt_count = len(dats)
    items, all_texts = [], {}
    for rel, m in dats.items():
        for i, (text, codes) in enumerate(m.texts()):
            iid = f"{rel}#{i}"
            all_texts[iid] = (rel, i, text, codes)
            marked = to_marked(text)
            if marked.strip():
                items.append(ia.Item(iid, marked))
    rep.strings = len(items)
    glossary = ia.load_glossary(paths, game_name or "Pokemon")
    res = ia.translate(paths, cfg, items, f"switch-{tid}", glossary, [], chain=chain,
                       progress=progress, should_pause=should_pause)
    rep.provider, rep.tokens, rep.errors = res.provider_used, res.tokens, rep.errors + res.errors
    rep.flagged, rep.review = len(res.flagged), len(res.review)
    rep.flagged_samples = [f"{to_marked(all_texts[k][2])[:60]} → {v}" for k, v in list(res.flagged.items())[:20]]
    changed: set[str] = set()
    overflow = 0
    for iid, (rel, i, text, codes) in all_texts.items():
        new = res.translated.get(iid)
        if new is None or new == to_marked(text):
            continue
        try:
            marked, codes2, fits = layout(text, codes, new)
            words = from_marked(marked, codes2)
        except tm.MsgError as e:
            rep.flagged += 1
            if len(rep.flagged_samples) < 20:
                rep.flagged_samples.append(f"{text[:60]} → {e}")
            continue
        overflow += not fits
        dats[rel].lines[i].words = words
        changed.add(rel)
        rep.translated += 1
    if overflow:
        rep.review += overflow
        rep.errors.append(f"{overflow} frase(s) ficaram com mais linhas que o original (podem sair da caixa)")
    return write_mod(paths, rep, src_dir, {r: dats[r] for r in sorted(changed)}, cfg)


def build_mod(stage: Path, trpfd_raw: bytes, dats: dict[str, tm.MsgDat]) -> list[str]:
    """Grava os .dat soltos + data.trpfd sem os hashes deles e confere tudo relendo. Devolve problemas."""
    problems = []
    shutil.rmtree(stage, ignore_errors=True)
    for rel, m in dats.items():
        data = tm.write_dat(m)
        back = tm.read_dat(data)
        if [l.words for l in back.lines] != [l.words for l in m.lines]:
            problems.append(f"{rel}: releitura não confere")
        dst = stage / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
    remove = {trinity.fnv1a64(rel) for rel in dats}
    new_fd = trinity.trpfd_without(trpfd_raw, remove)
    old, new = trinity.read_trpfd(trpfd_raw), trinity.read_trpfd(new_fd)
    keep = [(h, p) for h, p in zip(old.hashes, old.pack_index) if h not in remove]
    if list(zip(new.hashes, new.pack_index)) != keep or new.pack_names != old.pack_names:
        problems.append("data.trpfd alterado não confere")
    if any(new.pack_of(h) is not None for h in remove):
        problems.append("data.trpfd ainda aponta para os textos originais")
    (stage / "arc").mkdir(parents=True, exist_ok=True)
    (stage / TRPFD).write_bytes(new_fd)
    return problems


def write_mod(paths: Paths, rep, src_dir: Path, dats: dict[str, tm.MsgDat], cfg: dict):
    from . import switch
    threshold = float(cfg.get("flagged_threshold", 10))
    stage = paths.data / "traducao" / "mods" / rep.title_id / "romfs"
    shutil.rmtree(stage.parent, ignore_errors=True)
    if dats:
        rep.errors += build_mod(stage, (src_dir / "data.trpfd").read_bytes(), dats)
    stage.parent.mkdir(parents=True, exist_ok=True)
    (stage.parent / "relatorio.json").write_text(json.dumps(
        {"title_id": rep.title_id, "formato": "trinity", "arquivos": len(dats), "strings": rep.strings,
         "translated": rep.translated, "flagged": rep.flagged, "flagged_samples": rep.flagged_samples,
         "font": rep.font, "skipped": rep.skipped_files}, ensure_ascii=False, indent=1), "utf-8")
    rep.mod_dir = str(stage.parent)
    blocking = [e for e in rep.errors if "podem sair da caixa" not in e]
    if rep.translated and rep.pct_flagged() <= threshold and not blocking:
        rep.mod_dir = str(switch.install_mod(rep.title_id, stage.parent))
        rep.applied = True
    return rep


def find_rom_files(rom: Path, tid: str, roots: list[Path]) -> Optional[dict]:
    """Lista o RomFS só para saber se é Trinity (barato: só as tabelas do RomFS)."""
    from . import converter, extract as ex, nca, switch
    kp = switch.keys_path()
    if not kp:
        return None
    try:
        rfs, hs = nca.open_romfs(rom, nca.load_keys(kp), ex.latest_update(converter.collect(roots, tid)))
    except (nca.NcaError, OSError):
        return None
    try:
        return rfs.files()
    finally:
        for h in hs:
            h.close()
