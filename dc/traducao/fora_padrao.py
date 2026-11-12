"""Tradução fora do padrão: para jogos cujo texto não está num formato conhecido (MSBT, tabelas de ROM etc.).

Só roda depois de o usuário responder "Sim" no bot, e só com as IAs locais (PC pelo túnel + Deck).
Regras de segurança (lição do Luigi's Mansion 3):
- acha frases em UTF-16/UTF-8 dentro de cada arquivo (inclusive dentro de zlib/zstd);
- troca SÓ no mesmo lugar e com o mesmo tamanho (o que sobra vira zeros): ponteiros e índices do jogo
  continuam valendo, porque nenhuma posição muda;
- o texto achado precisa ser de uma língua só (idioma.extraction_is_clean); senão não grava nada e
  devolve o diagnóstico (arquivos, compressão, idiomas) em vez de tentar no escuro;
- o jogo original nunca é alterado: Switch/3DS viram mod (LayeredFS), o resto vira cópia "(PT-BR)".
"""
from __future__ import annotations

import shutil
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import generico, ia, idioma

MEDIA = (".bfstm", ".bwav", ".bwar", ".bars", ".mp4", ".webm", ".bntx", ".bfres", ".bcstm", ".bcwav",
         ".at9", ".ogg", ".wav", ".mp3", ".png", ".jpg", ".dds", ".ktx", ".astc", ".bclim", ".bflim", ".pmf")
MAX_FILE = 32 * 1024 * 1024
# pacotes/índices de motor de jogo: trocar bytes aqui quebra o jogo (FF Resonance, 09/11: o .utoc da Unreal
# tinha nomes de arquivo e bytes soltos que pareciam japonês — "traduzir" isso corrompe o índice)
CONTAINERS = (".utoc", ".ucas", ".pak", ".uasset", ".uexp", ".umap", ".ubulk", ".uptnl", ".resS", ".ress",
              ".resource", ".assets", ".bundle", ".unity3d", ".ttf", ".otf", ".tps", ".nro", ".nso", ".npdm",
              ".rpx", ".rpl", ".elf", ".self", ".sprx", ".prx", ".dll", ".exe", ".so")
SKIP = tuple(x.lower() for x in MEDIA + CONTAINERS)


@dataclass
class Report:
    files: int = 0
    with_text: int = 0
    found: int = 0
    translated: int = 0
    skipped_long: int = 0
    langs: str = ""
    compression: Counter = field(default_factory=Counter)
    changed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    provider: str = ""

    def text(self) -> str:
        lines = [f"Arquivos examinados: {self.files} · com frases: {self.with_text} · frases: {self.found}"]
        if self.compression:
            lines.append("Compressão: " + ", ".join(f"{k} {v}" for k, v in self.compression.items()))
        if self.langs:
            lines.append("Idiomas achados: " + self.langs)
        if self.translated:
            lines.append(f"✅ Traduzidas: {self.translated} (não couberam no espaço original: {self.skipped_long})")
        lines += [f"⚠️ {e}" for e in self.errors[:3]]
        return "\n".join(lines)


def local_chain(paths, cfg: dict) -> list:
    """Só as IAs locais: a do PC (túnel) e a do Deck. Nada de serviço externo nem de token do Claude."""
    loc = dict(cfg, provider="ollama_pc", fallback=["ollama"])
    return ia.build_chain(paths, loc)


def candidates(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() not in SKIP
                  and p.stat().st_size <= MAX_FILE)


def translate_dir(paths, src: Path, stage: Path, title: str = "", expected_lang: str | None = None,
                  chain=None, progress=lambda d, t: None, should_pause=lambda: False,
                  log: Callable[[str], None] = lambda s: None) -> Report:
    """Traduz os arquivos de `src` e grava SÓ os que mudaram em `stage` (mesmo caminho relativo)."""
    rep = Report()
    cfg = ia.load_cfg(paths)
    chain = chain if chain is not None else local_chain(paths, cfg)
    if not chain:
        rep.errors.append("nenhuma IA local respondendo (ligue o PC ou confira o Ollama do Deck)")
        return rep
    found = {}  # rel -> (body, kind, slots)
    for p in candidates(src):
        rep.files += 1
        try:
            body, kind = generico.unpack(p.read_bytes())
        except Exception:  # noqa: BLE001 — arquivo que não abre só fica de fora
            continue
        slots = generico.find_strings(body, sentences_only=True)
        if slots:
            rel = str(p.relative_to(src)).replace("\\", "/")
            found[rel] = (body, kind, slots)
            rep.with_text += 1
            rep.found += len(slots)
            if kind:
                rep.compression[kind] += 1
    texts = [s.text for _, _, sl in found.values() for s in sl]
    ok, why = idioma.extraction_is_clean(texts, expected_lang) if texts else (False, "nenhuma frase achada")
    rep.langs = why if ok else ""
    if not ok:
        rep.errors.append(f"não traduzi para não estragar o jogo: {why}")
        langs = Counter(idioma.language(t) or "?" for t in texts)
        rep.langs = ", ".join(f"{k} {v}" for k, v in langs.most_common(4))
        return rep
    cfg = dict(cfg, idioma_origem=idioma.dominant_language(texts) or "en")
    items = []
    for rel, (_, _, slots) in found.items():
        for s in slots:
            budget = s.length // 2 if s.encoding.startswith("utf-16") else s.length
            items.append(ia.Item(f"{rel}@{s.offset}", s.text, max_len=budget))
    res = ia.translate(paths, cfg, items, f"fora-{title or src.name}", ia.load_glossary_jogo(paths, cfg, items, title),
                       chain=chain, progress=progress, should_pause=should_pause)
    rep.provider = res.provider_used
    rep.errors += res.errors[:3]
    for rel, (body, kind, slots) in found.items():
        new = {s.offset: res.translated[f"{rel}@{s.offset}"] for s in slots if f"{rel}@{s.offset}" in res.translated}
        if not new:
            continue
        data, applied, skipped = generico.apply(body, slots, new)
        rep.translated += applied
        rep.skipped_long += skipped
        if applied:
            out = stage / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            packed = generico.pack(data, kind)
            if generico.unpack(packed)[0] != data:
                rep.errors.append(f"recompressão de {rel} não confere; arquivo deixado de fora")
                continue
            out.write_bytes(packed)
            rep.changed.append(rel)
    return rep


def install_layeredfs(stage: Path, mod_romfs: Path) -> Path:
    """Copia os arquivos traduzidos para a pasta romfs do mod (substitui só o mod do Deck Commander)."""
    if mod_romfs.exists():
        shutil.rmtree(mod_romfs)
    mod_romfs.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(stage, mod_romfs)
    return mod_romfs


def extract_switch(rom: Path, title_id: str, roots: list[Path], dest: Path) -> int:
    """Extrai do jogo de Switch (base + atualização mais nova) os arquivos que podem ter texto."""
    from . import converter, extract, nca, switch
    kp = switch.keys_path()
    if not kp:
        raise nca.NcaError("o Ryujinx ainda não tem prod.keys (abra um jogo nele uma vez)")
    upd = extract.latest_update(converter.collect(roots, title_id))
    rfs, handles = nca.open_romfs(rom, nca.load_keys(kp), upd)
    n = 0
    try:
        for rel, (off, size) in rfs.files().items():
            if size > MAX_FILE or Path(rel).suffix.lower() in SKIP:
                continue
            out = dest / rel.lstrip("/")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(rfs.read_at(off, size))
            n += 1
    finally:
        for h in handles:
            h.close()
    return n


def hardlink_copy(src: Path, dst: Path) -> None:
    """Cópia de uma pasta de jogo sem gastar espaço (links); os arquivos traduzidos são trocados depois."""
    for p in src.rglob("*"):
        q = dst / p.relative_to(src)
        if p.is_dir():
            q.mkdir(parents=True, exist_ok=True)
            continue
        q.parent.mkdir(parents=True, exist_ok=True)
        try:
            q.hardlink_to(p)
        except OSError:
            shutil.copy2(p, q)


def folder_game_root(console: str, rom: Path) -> Path | None:
    """Pasta do jogo para consoles de jogo em pasta (PS3: PS3_GAME/USRDIR/EBOOT.BIN; Wii U: code/*.rpx)."""
    if console == "ps3" and rom.name == "EBOOT.BIN":
        return rom.parent.parent.parent
    if console == "wiiu" and rom.suffix.lower() == ".rpx" and rom.parent.name == "code":
        return rom.parent.parent
    return None


SUPPORTED = ("switch", "n3ds", "ps3", "wiiu")
