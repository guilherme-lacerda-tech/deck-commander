"""Luigi's Mansion 3 (Switch, 0100DCA0064A6000): tradução das falas e menus como mod LayeredFS.

Onde está o texto: na atualização (1.4), dentro de `init.patch`, seção 5 (ver `nlg.py`): 13 tabelas, uma
por idioma. O Ryujinx em inglês usa a tabela 0 (inglês dos EUA); a 9 é o inglês europeu. As duas são
traduzidas. O mod é um único arquivo: `romfs/init.patch` (o original nunca é alterado).

Regra de ouro do formato: cada tabela mantém EXATAMENTE o tamanho original (o jogo guarda esse tamanho
em vários índices). Por isso o português precisa caber no espaço do inglês: a IA recebe um limite por
frase e, se no fim o total ainda não couber, as frases que mais cresceram voltam para o inglês
(contadas no relatório).

Códigos do jogo:
    [tp:0.03]…[/tp]   velocidade/pausa da fala     [clr:FFE98B]…[/clr]  cor
    [p] quebra de linha manual                     [pb] nova caixa de diálogo
    {0} {1} {}        valores que o jogo preenche
`[p]` simples vira espaço antes da IA e a quebra é refeita depois na mesma largura do original.
"""
from __future__ import annotations

import json
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import ia, nlg

TITLE_IDS = {"0100DCA0064A6000"}
PATCH_NAME = "init.patch"
LOCALES = (0, 9)                       # inglês EUA e inglês Europa
GROWTH = 1.12                          # quanto uma frase pode crescer antes de pedir versão curta
GROWTH_2 = 1.6                         # 2ª chance (usa a folga que sobrou na tabela)
CODE = re.compile(r"\[tp:[^\]]*\] ?\[/tp\]|\[[^\[\]]*\]|\{\d*\}")
TAG = re.compile(r"\[[^\[\]]*\]")


def supported(title_id: str) -> bool:
    return (title_id or "").upper() in TITLE_IDS


# ----------------------------------------------------------------------------- texto <-> IA
@dataclass
class Prepared:
    prefix: str                 # códigos do começo (ex.: [tp:0.03]) mantidos fora da IA
    core: str                   # texto com ⟦n⟧ que vai para a IA
    suffix: str
    codes: list[str]
    width: int = 0              # largura (em letras) das linhas do original; 0 = sem quebra refeita
    lines: int = 1              # máximo de linhas por caixa no original


def visible(s: str) -> str:
    return TAG.sub("", s)


def prepare(s: str) -> Prepared:
    # só códigos de fala ([tp…]) ficam fora da IA; cor ([clr]) acompanha a palavra e vai como ⟦n⟧
    m1 = re.match(r"^(?:\[/?tp[^\]]*\]|\s)*", s)
    prefix = m1.group(0)
    rest = s[len(prefix):]
    m2 = re.search(r"(?:\[/?tp[^\]]*\]|\s)*$", rest)
    suffix = m2.group(0) if m2 else ""
    core = rest[:len(rest) - len(suffix)] if suffix else rest
    # "[tp:0.3] [/tp]" no fim do prefixo/sufixo já está fora; [p] dentro do miolo: quebra refeita depois
    width, lines = 0, 1
    if "[p]" in core and "[p][p]" not in s and not re.search(r"\[p\]\s*\[pb\]|\[pb\]\s*\[p\]", s):
        pages = core.split("[pb]")
        ls = [ln for pg in pages for ln in pg.split("[p]")]
        width = max(len(visible(ln).strip()) for ln in ls)
        lines = max(pg.count("[p]") + 1 for pg in pages)
        # quebra depois de fim de frase é intencional (fica); as outras são só largura (refeitas)
        core = re.sub(r"(?<![.!?…:])((?:\[[^\[\]]*\])*)\s*\[p\]\s*", r"\1 ", core)
    text, codes = ia.protect(core, CODE)
    return Prepared(prefix, text, suffix, codes, width, lines)


def _wrap_page(page: str, width: int) -> list[str]:
    lines = []
    for seg in page.split("[p]"):  # [p] que sobrou = quebra intencional
        lines += _wrap_seg(seg.strip(" "), width)
    return lines


def _wrap_seg(seg: str, width: int) -> list[str]:
    # espaço dentro de código (pausa "[tp:0.3] [/tp]") não é ponto de quebra
    glued = re.sub(r"\[tp:[^\]]*\] \[/tp\]|\[[^\[\]]*\]", lambda m: m.group(0).replace(" ", "\x01"), seg)
    words = [w.replace("\x01", " ") for w in glued.split(" ")]
    lines, cur = [], ""
    for w in words:
        cand = w if not cur else cur + " " + w
        if cur and len(visible(cand)) > width:
            lines.append(cur)
            cur = w
        else:
            cur = cand
    if cur or not lines:
        lines.append(cur)
    return lines


def wrap(text: str, width: int, max_lines: int) -> tuple[str, bool]:
    """Refaz as quebras [p] na largura do original. Devolve (texto, coube_nas_linhas_do_original)."""
    out, fits = [], True
    for page in text.split("[pb]"):
        page = re.sub(r" {2,}", " ", page.strip(" "))
        lines = _wrap_page(page, width)
        if len(lines) > max_lines:  # tenta só um pouco mais largo antes de aceitar uma linha a mais
            wider = _wrap_page(page, int(width * 1.1) + 1)
            if len(wider) <= max_lines:
                lines = wider
            else:
                fits = False
        out.append("[p]".join(lines))
    return "[pb]".join(out), fits


def finish(p: Prepared, translated: str) -> tuple[str, bool]:
    body = ia.restore(translated, p.codes)
    fits = True
    if p.width:
        body, fits = wrap(body, p.width, p.lines)
        # a pausa "[tp:x] [/tp]" já tem o espaço; o [p] que virou espaço não pode duplicar
        body = re.sub(r"(\[tp:[^\]]*\] \[/tp\]) (?=\S)", r"\1", body)
    return p.prefix + body + p.suffix, fits


def utf16_len(s: str) -> int:
    return len(s.encode("utf-16-le", "surrogatepass")) // 2


# ----------------------------------------------------------------------------- relatório
@dataclass
class Lm3Report:
    title_id: str
    strings: int = 0
    translated: int = 0
    flagged: int = 0
    reverted_space: int = 0     # frases que voltaram ao inglês por falta de espaço
    extra_line: int = 0         # frases que ficaram com uma linha a mais que o original
    provider: str = ""
    tokens: int = 0
    mod_dir: str = ""
    applied: bool = False
    selfcheck: str = ""
    errors: list[str] = field(default_factory=list)
    flagged_samples: list[str] = field(default_factory=list)

    def pct_flagged(self) -> float:
        return 100.0 * (self.flagged + self.reverted_space) / max(1, self.strings)

    def text(self) -> str:
        L = [f"Luigi's Mansion 3 · frases: {self.strings} · traduzidas: {self.translated}",
             f"mantidas em inglês: {self.flagged} (problema na IA) + {self.reverted_space} (não couberam no espaço)",
             f"com uma linha a mais que o original: {self.extra_line}",
             f"IA: {self.provider or '-'} · tokens: {self.tokens}",
             f"conferência do arquivo: {self.selfcheck or '-'}"]
        L += [f"⚠️ {e}" for e in self.errors[:5]]
        L.append(("✅ mod ativo em " if self.applied else "⏸ mod guardado (não aplicado) em ") + self.mod_dir)
        return "\n".join(L)


# ----------------------------------------------------------------------------- extração
def fetch_patch(rom: Path, title_id: str, roots: list[Path],
                dest_root: Path = Path.home() / "Emulation/romfs") -> Path:
    """Copia (uma vez) o init.patch do jogo (base + atualização) para o cache. Só lê o jogo."""
    from . import converter, extract, nca, switch
    kp = switch.keys_path()
    if not kp:
        raise nca.NcaError("o Ryujinx ainda não tem prod.keys (abra um jogo nele uma vez)")
    upd = extract.latest_update(converter.collect(roots, title_id))
    if not upd:
        raise nca.NcaError("Luigi's Mansion 3: a tradução precisa da atualização 1.4 (init.patch) instalada")
    dest = dest_root / title_id / "nlg" / PATCH_NAME
    stamp = dest.parent / "extraido-por-deck-commander.json"
    want = {"base": rom.name, "update": upd.name}
    try:
        if json.loads(stamp.read_text("utf-8")) == want and dest.is_file():
            return dest
    except (OSError, ValueError):
        pass
    rfs, handles = nca.open_romfs(rom, nca.load_keys(kp), upd)
    try:
        files = rfs.files()
        if PATCH_NAME not in files:
            raise nca.NcaError("init.patch não encontrado no jogo")
        off, size = files[PATCH_NAME]
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".part")
        with open(tmp, "wb") as f:
            pos = 0
            while pos < size:
                n = min(8 << 20, size - pos)
                f.write(rfs.read_at(off + pos, n))
                pos += n
        tmp.replace(dest)
        stamp.write_text(json.dumps(want, ensure_ascii=False), "utf-8")
        return dest
    finally:
        for h in handles:
            h.close()


# ----------------------------------------------------------------------------- tradução
def _fit(table: nlg.TextTable, originals: list[str], new: dict[int, str], budget: int) -> int:
    """Aplica as traduções na tabela; se não couber no espaço, devolve ao inglês as que mais cresceram."""
    for i, s in new.items():
        table.strings[i] = s
    over = table.size() - budget
    reverted = 0
    if over > 0:
        growth = sorted(new, key=lambda i: utf16_len(new[i]) - utf16_len(originals[i]), reverse=True)
        for i in growth:
            if over <= 0:
                break
            gain = 2 * (utf16_len(new[i]) - utf16_len(originals[i]))
            if gain <= 0:
                break
            table.strings[i] = originals[i]
            for j, k in table.shared.items():
                if k == i:
                    table.strings[j] = originals[i]
            over -= gain
            reverted += 1
    return reverted


def translate_game(paths, title_id: str, patch_file: Path, game_name: str = "", chain=None,
                   progress: Callable[[int, int], None] = lambda d, t: None,
                   should_pause: Callable[[], bool] = lambda: False, install: bool = True) -> Lm3Report:
    from . import switch
    cfg = ia.load_cfg(paths)
    rep = Lm3Report(title_id)
    raw = patch_file.read_bytes()
    ok, why = nlg.selfcheck_patch(raw)
    if not ok:
        rep.errors.append(f"o init.patch não foi reproduzido com exatidão ({why}); nada foi feito")
        return rep
    p = nlg.read_patch(raw)
    spans = nlg.section_tables(p)
    tables = {loc: nlg.read_table(bytes(p.blob[o:o + n])) for loc, (o, n) in enumerate(spans) if loc in LOCALES}
    prepared: dict[str, Prepared] = {}
    items: list[ia.Item] = []
    seen: set[str] = set()
    for loc, t in tables.items():
        for i in t.order:
            s = t.strings[i]
            pr = prepare(s)
            key = f"{loc}#{i}"
            prepared[key] = pr
            if pr.core.strip() and not ia.only_codes(pr.core) and pr.core not in seen:
                seen.add(pr.core)
                items.append(ia.Item(key, pr.core, max_len=max(12, int(len(pr.core) * GROWTH) + 2)))
    rep.strings = len(tables[LOCALES[0]].order)
    glossary = ia.load_glossary_jogo(paths, cfg, items, game_name or "Luigi's Mansion 3")
    res = ia.translate(paths, cfg, items, f"switch-{title_id}", glossary, chain=chain,
                       progress=progress, should_pause=should_pause)
    # 2ª chance para o que só passou do limite por frase: a tabela tem folga no total (frases que encolheram),
    # então aceita até ~1,6× aqui; se no fim não couber, _fit devolve ao inglês as que mais cresceram
    longos = [ia.Item(it.id, it.text, max_len=max(16, int(len(it.text) * GROWTH_2) + 4)) for it in items
              if "maior que o espaço" in res.flagged.get(it.id, "")]
    if longos:
        res2 = ia.translate(paths, cfg, longos, f"switch-{title_id}", glossary, chain=chain,
                            should_pause=should_pause)
        for k, v in res2.translated.items():
            res.translated[k] = v
            res.flagged.pop(k, None)
        res.tokens += res2.tokens
    rep.provider, rep.tokens, rep.errors = res.provider_used, res.tokens, rep.errors + res.errors
    by_core = {}
    for it in items:
        if it.id in res.translated:
            by_core[it.text] = res.translated[it.id]
    rep.flagged = sum(1 for it in items if it.id in res.flagged)
    rep.flagged_samples = [f"{it.text[:60]} → {res.flagged[it.id]}" for it in items if it.id in res.flagged][:20]
    bad_out: set[str] = set()
    for loc, t in tables.items():
        originals = list(t.strings)
        new: dict[int, str] = {}
        extra = 0
        for i in t.order:
            pr = prepared[f"{loc}#{i}"]
            out = by_core.get(pr.core)
            if out is None or out == pr.core:
                continue
            s, fits = finish(pr, out)
            if "\x00" in s or "⟦" in s or "⟧" in s or s.count("[") != s.count("]"):
                bad_out.add(pr.core)  # marcador inventado/quebrado pela IA: fica o inglês
                continue
            new[i] = s
            extra += 0 if fits else 1
        for j, k in t.shared.items():
            if k in new:
                new[j] = new[k]
        o, n = spans[loc]
        reverted = _fit(t, originals, new, n)
        nlg.put_table(p, loc, t)
        if loc == LOCALES[0]:
            rep.translated = sum(1 for i in t.order if t.strings[i] != originals[i])
            rep.reverted_space, rep.extra_line = reverted, extra
    rep.flagged += len(bad_out)
    rep.flagged_samples += [f"{c[:60]} → marcador inventado pela IA" for c in sorted(bad_out)][:5]
    out = nlg.write_patch(p)
    # conferência: o arquivo novo abre, tem as mesmas 13 tabelas nos mesmos lugares e só a seção de texto mudou
    q = nlg.read_patch(out)
    if nlg.section_tables(q) != spans or len(q.blob) != len(p.blob):
        rep.errors.append("conferência do init.patch novo falhou; mod não aplicado")
        return rep
    a, b = spans[0][0], spans[-1][0] + spans[-1][1]
    if q.blob[:a] != nlg.read_patch(raw).blob[:a] or q.blob[b:] != nlg.read_patch(raw).blob[b:]:
        rep.errors.append("algo fora da seção de texto mudou; mod não aplicado")
        return rep
    for loc in LOCALES:
        nlg.read_table(bytes(q.blob[spans[loc][0]:spans[loc][0] + spans[loc][1]]))
    rep.selfcheck = "init.patch reproduzido byte a byte; novo arquivo reaberto com as 13 tabelas no lugar ✅"
    stage = paths.data / "traducao" / "mods" / title_id / "romfs"
    shutil.rmtree(stage.parent, ignore_errors=True)
    stage.mkdir(parents=True)
    (stage / PATCH_NAME).write_bytes(out)
    (stage.parent / "relatorio.json").write_text(json.dumps(
        {"title_id": title_id, "jogo": "Luigi's Mansion 3", "strings": rep.strings, "translated": rep.translated,
         "flagged": rep.flagged, "reverted_space": rep.reverted_space, "extra_line": rep.extra_line,
         "flagged_samples": rep.flagged_samples}, ensure_ascii=False, indent=1), "utf-8")
    rep.mod_dir = str(stage.parent)
    threshold = float(cfg.get("flagged_threshold", 10))
    if install and rep.translated and rep.pct_flagged() <= threshold and not res.errors:
        rep.mod_dir = str(switch.install_mod(title_id, stage.parent))
        rep.applied = True
    return rep
