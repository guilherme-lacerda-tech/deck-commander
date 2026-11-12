"""Motor de tradução com IA (compartilhado por A1 retrô e A2 Switch). Só biblioteca padrão.

- Cadeia de provedores (traducao.toml): Ollama local -> GitHub Models -> Index-Translate -> pago.
  Todos menos o Ollama falam o formato OpenAI (`/chat/completions`), então um cliente serve para todos.
- Proteção de códigos: tudo que o jogo interpreta ([rival], {C1}, \\n, tags do Switch...) vira ⟦n⟧
  antes de ir para a IA e volta depois; se a IA perder ou inventar um ⟦n⟧, a frase é "flagged" e o
  original é mantido.
- Glossário (nomes que não se traduzem / traduções fixas) e few-shot (pares de traduções de referência).
- Cache por frase: retomar uma tradução interrompida não gasta de novo, nem repete trabalho.
- Uso diário de tokens (limite + alerta em 80%) para provedores pagos/limitados.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import tomllib

from ..paths import Paths

PH_OPEN, PH_CLOSE = "⟦", "⟧"
RETRY_WAIT = 5  # segundos (vezes o nº da tentativa) antes de tentar de novo o mesmo provedor
_PH = re.compile(r"⟦(\d+)⟧")

DEFAULT_CFG = {
    "provider": "index_translate",   # testado 2026-11-09: rápido, grátis, mantém os marcadores
    "fallback": ["ollama_pc", "ollama", "github_models"],
    "modelo": "translategemma:4b",
    "idioma": "pt-BR",
    "idioma_origem": "en",
    "few_shot": True,
    "limite_diario_tokens": 500000,
    "estimativa_antes_de_iniciar": True,
    "flagged_threshold": 10,          # % de frases com problema acima do qual NÃO aplica sozinho
    "permitir_bateria": False,
    "lote": 20,                       # frases por chamada (modelos "unitários" ignoram)
    "providers": {
        "ollama": {"tipo": "ollama", "url": "http://127.0.0.1:11434", "modelo": "translategemma:4b", "gratis": True},
        # IA do seu PC (placa de vídeo) chegando pelo túnel SSH que o PC abre (tools/pc/tunel-ia.ps1)
        "ollama_pc": {"tipo": "ollama", "url": "http://127.0.0.1:11435", "modelo": "qwen2.5:7b", "gratis": True,
                      "lote": 12},
        "index_translate": {"tipo": "openai", "url": "https://index-translate.bilibili.com/v1",
                            "modelo": "Index-Translate-9B", "chave": "", "gratis": True, "lote": 8},
        "github_models": {"tipo": "openai", "url": "https://models.github.ai/inference",
                          "modelo": "openai/gpt-4.1-mini", "segredo": "github_pat", "gratis": True},
        "openai": {"tipo": "openai", "url": "https://api.openai.com/v1", "modelo": "gpt-4.1-mini", "segredo": "ia_api.key"},
        "anthropic": {"tipo": "openai", "url": "https://api.anthropic.com/v1", "modelo": "claude-haiku-5-5",
                      "segredo": "ia_api.key"},
        "gemini": {"tipo": "openai", "url": "https://generativelanguage.googleapis.com/v1beta/openai",
                   "modelo": "gemini-2.5-flash", "segredo": "ia_api.key"},
    },
}
LANG_NAMES = {"pt-BR": "Brazilian Portuguese", "en": "English", "ru": "Russian", "es": "Spanish", "fr": "French", "de": "German",
              "it": "Italian", "ja": "Japanese", "zh": "Chinese"}


class ProviderError(RuntimeError):
    pass


# ----------------------------------------------------------------------------- configuração
def load_cfg(paths: Paths) -> dict:
    cfg = json.loads(json.dumps(DEFAULT_CFG))
    p = paths.config / "traducao.toml"
    if p.exists():
        user = tomllib.loads(p.read_text("utf-8"))
        provs = user.pop("providers", {})
        cfg.update(user)
        for k, v in provs.items():
            cfg["providers"][k] = {**cfg["providers"].get(k, {}), **v}
    return cfg


def write_default_cfg(paths: Paths) -> Path:
    p = paths.config / "traducao.toml"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            '# Tradução com IA (Deck Commander). Cadeia: provider, depois fallback na ordem.\n'
            '# index_translate: grátis e rápida (o texto do jogo vai para o servidor da Bilibili)\n'
            '# ollama: no próprio Deck, grátis, privada, sem internet, mas lenta (horas)\n'
            'provider = "index_translate"\n'
            'fallback = ["ollama", "github_models"]\n'
            'idioma = "pt-BR"\n'
            'idioma_origem = "en"\n'
            'few_shot = true\n'
            'limite_diario_tokens = 500000  # só vale para provedores com limite/pagos\n'
            'estimativa_antes_de_iniciar = true\n'
            'flagged_threshold = 10         # % de frases com problema que bloqueia a aplicação automática\n'
            'permitir_bateria = false       # traduzir só na tomada\n\n'
            '[providers.ollama]\nmodelo = "translategemma:4b"\n\n'
            '# IA rodando no seu PC pela rede de casa (mais rápida):\n'
            '# [providers.ollama_pc]\n# url = "http://192.168.0.10:11434"\n# modelo = "translategemma:12b"\n\n'
            '[switch]\npreservar_tags = true\npermitir_sem_fonte_ptbr = false\n'
            'validar_com_referencia = true\nsimilaridade_minima = 0.75\n', "utf-8")
    return p


def secret(paths: Paths, name: str) -> str:
    p = paths.secrets / name
    try:
        return p.read_text("utf-8").strip()
    except OSError:
        return ""


def mask(s: str) -> str:
    return (s[:4] + "…" + s[-2:]) if len(s) > 8 else ("…" if s else "(sem chave)")


# ----------------------------------------------------------------------------- proteção de códigos
def protect(text: str, pattern: re.Pattern) -> tuple[str, list[str]]:
    codes: list[str] = []

    def sub(m):
        codes.append(m.group(0))
        return f"{PH_OPEN}{len(codes) - 1}{PH_CLOSE}"
    return pattern.sub(sub, text), codes


def restore(text: str, codes: list[str]) -> str:
    return _PH.sub(lambda m: codes[int(m.group(1))] if int(m.group(1)) < len(codes) else m.group(0), text)


def placeholders_ok(src: str, out: str) -> bool:
    return sorted(_PH.findall(src)) == sorted(_PH.findall(out))


def only_codes(text: str) -> bool:
    """Frase sem nada traduzível: só códigos/números/pontuação, um caractere repetido (ícones do jogo,
    ex.: 'pppppppp' que a fonte desenha como figuras) ou identificador interno (Item_01, BTN_A)."""
    t = _PH.sub("", text).strip()
    if not re.search(r"[^\W\d_]", t):
        return True
    if re.fullmatch(r"(\S)\1+", t):
        return True
    if " " not in t and re.fullmatch(r"[A-Za-z0-9]+(?:[_.][A-Za-z0-9]+)+", t):
        return True
    return bool(re.search(r"[-]", t)) and not re.search(r"[A-Za-z]{3,}", t)


# ----------------------------------------------------------------------------- uso de tokens
def _usage_path(paths: Paths) -> Path:
    return paths.data / "traducao" / "uso.json"


def tokens_today(paths: Paths) -> int:
    try:
        return json.loads(_usage_path(paths).read_text("utf-8")).get(date.today().isoformat(), 0)
    except (OSError, ValueError):
        return 0


def add_tokens(paths: Paths, n: int) -> None:
    p = _usage_path(paths)
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        d = json.loads(p.read_text("utf-8"))
    except (OSError, ValueError):
        d = {}
    k = date.today().isoformat()
    d = {k: d.get(k, 0) + n}  # guarda só o dia de hoje
    p.write_text(json.dumps(d), "utf-8")


def estimate_tokens(texts: list[str]) -> int:
    """Estimativa grosseira: ~1 token a cada 3 caracteres, ida e volta, + instruções por lote."""
    chars = sum(len(t) for t in texts)
    return int(chars / 3 * 2.2) + 150 * (len(texts) // 20 + 1)


# ----------------------------------------------------------------------------- provedores
HttpFn = Callable[[str, dict, dict, float], dict]


def _http(url: str, body: dict, headers: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "deck-commander", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise ProviderError(f"HTTP {e.code}") from e
    except (OSError, ValueError, http.client.HTTPException) as e:  # inclui conexão que caiu no meio da resposta
        raise ProviderError(str(e) or type(e).__name__) from e


@dataclass
class Provider:
    name: str
    spec: dict
    key: str = ""
    http: HttpFn = _http

    @property
    def free(self) -> bool:
        return bool(self.spec.get("gratis"))

    @property
    def model(self) -> str:
        return self.spec.get("modelo", "")

    @property
    def single(self) -> bool:
        """Modelos só de tradução (TranslateGemma) recebem uma frase por vez."""
        return "translategemma" in self.model.lower() or self.spec.get("unitario", False)

    def chat(self, system: str, user: str, timeout: float = 180) -> tuple[str, int]:
        # teto de resposta proporcional à entrada: modelo pequeno que entra em repetição não trava a tarefa
        max_tokens = min(4096, 64 + len(user) * 2)
        if self.spec["tipo"] == "ollama":
            if not self.spec.get("url"):
                raise ProviderError("sem endereço configurado")
            out = self.http(self.spec["url"].rstrip("/") + "/api/chat",
                            {"model": self.model, "stream": False,
                             "options": {"temperature": 0.2, "num_predict": max_tokens, "repeat_penalty": 1.1},
                             "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
                            {}, timeout)
            try:
                return out["message"]["content"], int(out.get("prompt_eval_count", 0)) + int(out.get("eval_count", 0))
            except (KeyError, TypeError, ValueError) as e:
                raise ProviderError(f"resposta inesperada: {str(out)[:120]}") from e
        headers = {"Authorization": f"Bearer {self.key or 'deck-commander'}"}
        out = self.http(self.spec["url"].rstrip("/") + "/chat/completions",
                        {"model": self.model, "temperature": 0.2, "max_tokens": max_tokens,
                         "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
                        headers, timeout)
        try:
            return out["choices"][0]["message"]["content"], int((out.get("usage") or {}).get("total_tokens", 0))
        except (KeyError, IndexError, TypeError) as e:
            raise ProviderError(f"resposta inesperada: {str(out)[:120]}") from e


def build_chain(paths: Paths, cfg: dict, http: HttpFn = _http) -> list[Provider]:
    out = []
    for name in [cfg["provider"], *cfg.get("fallback", [])]:
        spec = cfg["providers"].get(name)
        if not spec:
            continue
        key = secret(paths, spec["segredo"]) if spec.get("segredo") else spec.get("chave", "")
        if spec.get("segredo") and not key:
            continue  # provedor que precisa de chave e você não configurou: pula
        if spec.get("tipo") == "ollama" and http is _http and not _ollama_up(spec):
            continue  # PC desligado / IA local não instalada: pula na hora, sem esperar
        out.append(Provider(name, spec, key, http))
    return out


def _ollama_up(spec: dict) -> bool:
    url = (spec.get("url") or "").rstrip("/")
    if not url:
        return False
    try:
        with urllib.request.urlopen(url + "/api/tags", timeout=3) as r:
            models = [m.get("name", "") for m in json.loads(r.read()).get("models", [])]
    except (OSError, ValueError):
        return False
    want = spec.get("modelo", "")
    return not want or want in models or f"{want}:latest" in models


# ----------------------------------------------------------------------------- tradução
@dataclass
class Item:
    id: str
    text: str                 # já com ⟦n⟧ no lugar dos códigos
    max_len: int | None = None


@dataclass
class Result:
    translated: dict[str, str] = field(default_factory=dict)   # id -> texto traduzido (com ⟦n⟧)
    flagged: dict[str, str] = field(default_factory=dict)      # id -> motivo (original mantido)
    review: dict[str, str] = field(default_factory=dict)       # id -> aviso (tradução aplicada)
    tokens: int = 0
    provider_used: str = ""
    errors: list[str] = field(default_factory=list)


def _limits_note(items: list) -> str:
    lim = {it.id: it.max_len for it in items if it.max_len}
    if not lim:
        return ""
    if len(items) == 1:
        return f"\nThe translation MUST have at most {lim[items[0].id]} characters (it replaces text in a fixed space)."
    return ("\nEach translation MUST fit its maximum number of characters (fixed space in the game): "
            + json.dumps(lim) + ". Prefer shorter words and abbreviations when needed.")


def _system_prompt(cfg: dict, glossary: dict, examples: list[tuple[str, str]], batch: bool) -> str:
    src = LANG_NAMES.get(cfg["idioma_origem"], cfg["idioma_origem"])
    dst = LANG_NAMES.get(cfg["idioma"], cfg["idioma"])
    lines = [f"You are a professional video game translator from {src} to {dst}.",
             "Keep every marker like ⟦0⟧, ⟦1⟧ exactly as is (they are game control codes); do not add new ones.",
             "Keep it natural for players, short like the original (text boxes are small), same tone.",
             "Never add explanations or notes."]
    if glossary:
        lines.append("Mandatory glossary (source => target; '=' means keep unchanged): " +
                     "; ".join(f"{k} => {v}" for k, v in list(glossary.items())[:80]))
    if examples:
        lines.append("Examples of the expected style:")
        lines += [f"- {a} => {b}" for a, b in examples[:8]]
    if batch:
        lines.append('Input is a JSON object {"id": "text"}. Answer ONLY with a JSON object with the same ids '
                     'and the translated texts.')
    else:
        lines.append("Answer only with the translation.")
    return "\n".join(lines)


def _parse_batch(raw: str) -> dict:
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise ValueError("sem JSON na resposta")
    return json.loads(m.group(0))


def _cache_path(paths: Paths, job: str) -> Path:
    return paths.data / "traducao" / "cache" / f"{job}.json"


def _h(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


PARALLEL_CHUNK = 40
DECK_LOCAL = ("127.0.0.1:11434", "localhost:11434")


def _is_deck_local(p: Provider) -> bool:
    return p.spec.get("tipo") == "ollama" and any(h in (p.spec.get("url") or "") for h in DECK_LOCAL)


def _translate_parallel(paths, cfg, items, job, glossary, examples, pool, progress, should_pause) -> Result:
    """Vários provedores ao mesmo tempo (internet + PC + Deck): as frases ficam numa fila de pacotes e cada
    provedor puxa o próximo quando termina o dele; o mais rápido faz mais. Um provedor que falha 3 pacotes
    seguidos sai e os pacotes dele voltam para a fila. A IA do Deck só trabalha sem jogo aberto (não rouba
    desempenho). Cada provedor guarda o próprio cache (job#provedor); no fim tudo vai para o cache do job, e
    retomar uma tradução interrompida reaproveita tudo o que já tinha sido feito."""
    import queue
    import threading

    from .. import ops
    res = Result()
    cdir = _cache_path(paths, job).parent
    known: dict[str, str] = {}
    for f in [_cache_path(paths, job), *cdir.glob(f"{job}#*.json")]:
        try:
            known.update(json.loads(f.read_text("utf-8")))
        except (OSError, ValueError):
            pass
    todo = []
    for it in items:
        if only_codes(it.text):
            res.translated[it.id] = it.text
        elif _h(it.text) in known:
            res.translated[it.id] = known[_h(it.text)]
        else:
            todo.append(it)
    total = len(items)
    state = {"done": total - len(todo)}
    progress(state["done"], total)
    q: queue.Queue[list] = queue.Queue()
    for i in range(0, len(todo), PARALLEL_CHUNK):
        q.put(todo[i:i + PARALLEL_CHUNK])
    lock = threading.Lock()
    alive = {p.name for p in pool}
    pending = {"n": q.qsize()}

    def worker(prov: Provider) -> None:
        fails = 0
        while True:
            with lock:
                if not pending["n"]:
                    return
            if _is_deck_local(prov) and ops.game_running():
                time.sleep(10)  # jogo aberto: a IA do Deck espera (os outros seguem)
                continue
            try:
                chunk = q.get(timeout=5)
            except queue.Empty:
                continue
            try:
                sub = translate(paths, cfg, chunk, f"{job}#{prov.name}", glossary, examples, chain=[prov],
                                should_pause=should_pause)
            except Exception as e:  # noqa: BLE001 — um provedor que quebra nunca pode prender o pacote (a
                sub = Result()      # tradução ficaria "rodando" para sempre): conta como falha e devolve
                for it in chunk:
                    sub.flagged[it.id] = f"falha na IA: {type(e).__name__}"
            bad = [it for it in chunk if it.id not in sub.translated and
                   sub.flagged.get(it.id, "").startswith(("nenhum provedor", "falha na IA"))]
            with lock:
                for k, v in sub.translated.items():
                    res.translated[k] = v
                    res.flagged.pop(k, None)
                for k, v in sub.flagged.items():
                    if k not in res.translated:
                        res.flagged[k] = v
                res.review.update(sub.review)
                res.tokens += sub.tokens
                if sub.provider_used and prov.name not in res.provider_used.split("+"):
                    res.provider_used = "+".join(x for x in (res.provider_used, prov.name) if x)
                if chunk and len(bad) == len(chunk):  # o provedor não traduziu nada: devolve o pacote
                    fails += 1
                    for it in chunk:
                        res.flagged.pop(it.id, None)
                    q.put(chunk)
                    if fails >= 3:
                        alive.discard(prov.name)
                        res.errors.append(f"{prov.name} saiu da tradução paralela (3 falhas seguidas)")
                        if not alive:
                            pending["n"] = 0
                        return
                    continue
                fails = 0
                state["done"] += len(chunk)
                pending["n"] -= 1
                progress(state["done"], total)

    threads = [threading.Thread(target=worker, args=(p,), daemon=True) for p in pool]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    leftover = False
    while not q.empty():  # todos os provedores saíram: o que sobrou fica no original
        leftover = True
        for it in q.get_nowait():
            res.flagged[it.id] = "nenhum provedor respondeu"
    if leftover:
        res.errors.append("todos os provedores falharam")
    # junta os caches dos provedores no cache do job
    merged = dict(known)
    for f in cdir.glob(f"{job}#*.json"):
        try:
            merged.update(json.loads(f.read_text("utf-8")))
        except (OSError, ValueError):
            pass
    cp = _cache_path(paths, job)
    cp.parent.mkdir(parents=True, exist_ok=True)
    tmp = cp.with_name(cp.name + ".tmp")
    tmp.write_text(json.dumps(merged, ensure_ascii=False), "utf-8")
    os.replace(tmp, cp)
    return res


def translate(paths: Paths, cfg: dict, items: list[Item], job: str, glossary: dict | None = None,
              examples: list[tuple[str, str]] | None = None, chain: list[Provider] | None = None,
              progress: Callable[[int, int], None] = lambda done, total: None,
              should_pause: Callable[[], bool] = lambda: False) -> Result:
    """Traduz `items`. Nunca levanta exceção por causa de uma frase: o problema vira `flagged`."""
    glossary = glossary or {}
    chain = chain if chain is not None else build_chain(paths, cfg)
    pool = [p for p in chain if p.free]
    if cfg.get("paralelo", True) and len(pool) > 1 and len(items) > PARALLEL_CHUNK and "#" not in job:
        return _translate_parallel(paths, cfg, items, job, glossary, examples, pool, progress, should_pause)
    res = Result()
    if not chain:
        res.errors.append("nenhum provedor de IA disponível (instale o Ollama ou configure uma chave)")
        return res
    cp = _cache_path(paths, job)
    cp.parent.mkdir(parents=True, exist_ok=True)
    try:
        cache = json.loads(cp.read_text("utf-8"))
    except (OSError, ValueError):
        cache = {}
    todo = []
    for it in items:
        if only_codes(it.text):
            res.translated[it.id] = it.text
        elif _h(it.text) in cache:
            res.translated[it.id] = cache[_h(it.text)]
        else:
            todo.append(it)
    total, done = len(items), len(items) - len(todo)
    progress(done, total)
    limit = int(cfg.get("limite_diario_tokens", 0) or 0)
    prov_i = 0

    def save_cache():
        tmp = cp.with_name(cp.name + ".tmp")
        tmp.write_text(json.dumps(cache, ensure_ascii=False), "utf-8")
        os.replace(tmp, cp)

    def accept(it: Item, out: str) -> None:
        out = out.strip()
        if not it.text.lstrip().startswith('"') and len(out) > 1 and out[0] == out[-1] == '"':
            out = out[1:-1]  # a IA embrulhou em aspas; diálogo que JÁ tinha aspas fica como está
        if not placeholders_ok(it.text, out):
            res.flagged[it.id] = "a IA perdeu/inventou códigos do jogo — mantido o original"
            return
        if not out:
            res.flagged[it.id] = "resposta vazia — mantido o original"
            return
        if it.max_len and len(out) > it.max_len:
            too_long[it.id] = out  # tenta encurtar logo depois (uma vez)
            res.flagged[it.id] = f"ficou maior que o espaço ({len(out)} > {it.max_len}) — mantido o original"
            return
        res.flagged.pop(it.id, None)
        res.translated[it.id] = out
        cache[_h(it.text)] = out
        g = apply_glossary_check(it.text, out, glossary)
        if g:
            res.review[it.id] = g  # traduzido, mas vale uma olhada

    i = 0
    fails = 0               # falhas seguidas no provedor atual
    shrink = 1              # divisor do lote depois de erro (respostas longas demais dão 504)
    since_fallback = 0      # frases feitas no reserva desde que saiu do principal
    dead: set[int] = set()  # provedores que pararam de vez nesta tradução (ex.: limite de tokens)
    while i < len(todo):
        while should_pause():
            time.sleep(30)
        if prov_i >= len(chain) or len(dead) >= len(chain):
            for it in todo[i:]:
                res.flagged[it.id] = "nenhum provedor respondeu"
            res.errors.append("todos os provedores falharam")
            break
        # no reserva há um tempo? tenta o principal de novo (o erro dele costuma ser passageiro)
        if prov_i > 0 and since_fallback >= 60 and 0 not in dead:
            prov_i, since_fallback, fails, shrink = 0, 0, 0, 1
        prov = chain[prov_i]
        if not prov.free and limit and tokens_today(paths) >= limit:
            res.errors.append(f"limite diário de tokens atingido ({limit}) no {prov.name}")
            dead.add(prov_i)
            prov_i += 1
            continue
        size = 1 if prov.single else max(1, int(prov.spec.get("lote", cfg.get("lote", 20))) // shrink)
        batch = todo[i:i + size]
        rel_ex = _relevant_examples(examples or [], batch)
        too_long: dict[str, str] = {}
        try:
            if size == 1:
                raw, tok = prov.chat(_system_prompt(cfg, _gloss_for(glossary, batch), rel_ex, False)
                                     + _limits_note(batch), batch[0].text)
                accept(batch[0], raw)
            else:
                raw, tok = prov.chat(_system_prompt(cfg, _gloss_for(glossary, batch), rel_ex, True) + _limits_note(batch),
                                     json.dumps({it.id: it.text for it in batch}, ensure_ascii=False))
                try:
                    got = _parse_batch(raw)
                except (ValueError, json.JSONDecodeError):
                    got = {}
                for it in batch:
                    if it.id in got and isinstance(got[it.id], str):
                        accept(it, got[it.id])
                    else:  # a IA pulou esta frase: tenta sozinha
                        try:
                            r1, t1 = prov.chat(_system_prompt(cfg, _gloss_for(glossary, [it]), rel_ex, False), it.text)
                            tok += t1
                            accept(it, r1)
                        except ProviderError as e:
                            res.flagged[it.id] = f"falha na IA: {e}"
            for it in [x for x in batch if x.id in too_long]:  # passou do espaço: pede versão mais curta
                try:
                    dst = LANG_NAMES.get(cfg["idioma"], cfg["idioma"])
                    r2, t2 = prov.chat(f"Rewrite this {dst} video game text with at most {it.max_len} characters, "
                                       "same meaning, keep every ⟦n⟧ marker exactly. Answer only with the text.",
                                       too_long[it.id])
                    tok += t2
                    too_long.pop(it.id, None)
                    accept(it, r2)
                    too_long.pop(it.id, None)
                except ProviderError:
                    pass
            res.tokens += tok
            res.provider_used = res.provider_used or prov.name
            if not prov.free:
                add_tokens(paths, tok)
            i += len(batch)
            done += len(batch)
            fails = 0
            if prov_i > 0:
                since_fallback += len(batch)
            progress(done, total)
            save_cache()
        except ProviderError as e:
            fails += 1
            if fails < 3:  # erro passageiro (504, 429, rede): espera, diminui o lote e tenta de novo
                shrink = min(shrink * 2, 8)
                time.sleep(RETRY_WAIT * fails)
                continue
            if len(res.errors) < 30:
                res.errors.append(f"{prov.name}: {e}")
            prov_i, fails, shrink, since_fallback = prov_i + 1, 0, 1, 0  # próximo da cadeia; a frase é tentada de novo
    save_cache()
    return res


def _gloss_for(glossary: dict, batch: list[Item]) -> dict:
    text = " ".join(it.text.lower() for it in batch)
    return {k: v for k, v in glossary.items() if k.lower() in text}


def _relevant_examples(examples: list[tuple[str, str]], batch: list[Item], n: int = 6) -> list[tuple[str, str]]:
    """Few-shot: os pares de referência que mais compartilham palavras com o lote."""
    if not examples:
        return []
    words = set(re.findall(r"\w{4,}", " ".join(it.text.lower() for it in batch)))
    scored = sorted(examples, key=lambda p: -len(words & set(re.findall(r"\w{4,}", p[0].lower()))))
    return scored[:n]


def apply_glossary_check(src: str, out: str, glossary: dict) -> str | None:
    """Glossário obrigatório: termo da origem presente => tradução fixa deve aparecer."""
    for k, v in glossary.items():
        want = k if v == "=" else v
        if k.lower() in src.lower() and want.lower() not in out.lower():
            return f"glossário: '{k}' deveria virar '{want}'"
    return None


def load_glossary(paths: Paths, name: str = "") -> dict:
    """glossario.toml: [geral] e [<jogo/franquia>]; "=" mantém o termo (nomes próprios)."""
    p = paths.config / "glossario.toml"
    if not p.exists():
        return {}
    g = tomllib.loads(p.read_text("utf-8"))
    out = dict(g.get("geral", {}))
    if name:
        for sec, terms in g.items():
            if sec != "geral" and isinstance(terms, dict) and sec.lower() in name.lower():
                out.update(terms)
    return out


def glossary_path(paths: Paths) -> Path:
    """Glossário por franquia (ex.: todos os Mario), montado sozinho e compartilhado com o Deck do par (família)."""
    return paths.config / "glossary.json"


def load_glossary_jogo(paths: Paths, cfg: dict, items: list, name: str = "") -> dict:
    """Glossário do jogo ANTES de traduzir: glossario.toml (à mão) + o da franquia. Se o jogo é de uma franquia
    conhecida, os nomes próprios que se repetem e ainda não estão no glossário são traduzidos UMA vez pela IA
    (e guardados), para todos os jogos da série usarem os mesmos nomes. Nunca impede a tradução."""
    out = load_glossary(paths, name)
    try:
        from . import glossario_franquia as gf
        chave = gf.franquia(name or "")
        if not chave:
            return out
        dados = gf.carregar(glossary_path(paths))
        falta = gf.faltando(dados, chave, gf.candidatos([getattr(i, "text", str(i)) for i in items]))[:80]
        chain = [p for p in build_chain(paths, cfg) if _instructable(p)] if falta else []
        for i in range(0, len(falta), 40):
            lote = falta[i:i + 40]
            system, user = gf.pedido_ia(lote, chave)
            raw = _ask(chain, system, user, lambda r: bool(gf.ler_resposta(r, lote)))
            if raw:
                dados = gf.juntar(dados, chave, gf.ler_resposta(raw, lote))
        if falta:
            gf.salvar(glossary_path(paths), dados)
        for termo, trad in gf.do_jogo(dados, chave).items():
            out.setdefault(termo, trad)  # o glossario.toml (feito à mão) vale mais
    except Exception:  # noqa: BLE001 — glossário é ajuda; nunca derruba a tradução
        pass
    return out


# ----------------------------------------------------------------------------- segunda chance
def _instructable(p: Provider) -> bool:
    """IA que segue instrução (não só traduz): serve para remontar códigos e encurtar."""
    return not p.single and "index-translate" not in (p.spec.get("url") or "")


def _ask(chain: list[Provider], system: str, user: str, ok: Callable[[str], bool]) -> str | None:
    for p in chain:
        try:
            raw, _tok = p.chat(system, user, timeout=120)
        except ProviderError:
            continue
        raw = raw.strip()
        if len(raw) > 1 and raw[0] == raw[-1] == '"' and not user.lstrip().startswith('"'):
            raw = raw[1:-1]
        if raw and ok(raw):
            return raw
    return None


def fix_codes(paths: Paths, cfg: dict, items: list[Item], glossary: dict | None = None,
              chain: list[Provider] | None = None) -> tuple[dict[str, str], dict[str, str]]:
    """Frases em que a IA perdeu/trocou os códigos ⟦n⟧ (nome do Pokémon, número…).
    1ª tentativa: uma a uma, numa IA que segue instrução, explicando que pode MOVER os códigos.
    2ª: traduz só os pedaços de texto entre os códigos e remonta na mesma ordem (sempre válida; pode ficar
    menos natural). Devolve (traduções, como: "ia" | "pedaços")."""
    chain = chain if chain is not None else build_chain(paths, cfg)
    smart = [p for p in chain if _instructable(p)]
    system = (_system_prompt(cfg, glossary or {}, [], False) +
              "\nEach ⟦n⟧ is a value the game inserts (a name, a number, a color). Every marker in the input must "
              "appear EXACTLY once in your answer. You may move markers to where the grammar needs them.")
    seg_system = _system_prompt(cfg, glossary or {}, [], False) + \
        "\nThis is a fragment of a sentence (game values go between fragments). Translate only the fragment."
    out: dict[str, str] = {}
    how: dict[str, str] = {}
    for it in items:
        got = _ask(smart, system, it.text, lambda r, s=it.text: placeholders_ok(s, r))
        if got is not None:
            out[it.id], how[it.id] = got, "ia"
            continue
        parts = re.split(r"(⟦\d+⟧)", it.text)
        okp = True
        for i, s in enumerate(parts):
            core = s.strip()
            if _PH.fullmatch(s) or not re.search(r"[^\W\d_]{2}", core):
                continue
            t = _ask(chain, seg_system, core, lambda r: not _PH.search(r))
            if t is None:
                okp = False
                break
            parts[i] = s[:len(s) - len(s.lstrip())] + t + s[len(s.rstrip()):]
        if okp:
            out[it.id], how[it.id] = "".join(parts), "pedaços"
    return out, how


def shorten(paths: Paths, cfg: dict, items: list[tuple[str, str, int, int]],
            fits: Callable[[str, str], bool], chain: list[Provider] | None = None) -> dict[str, str]:
    """Tradução que não coube na caixa: pede uma versão mais curta (mesmo sentido, mesmos códigos).
    items: (id, texto traduzido, linhas, letras por linha). `fits(id, texto)` confere de verdade."""
    chain = chain if chain is not None else build_chain(paths, cfg)
    smart = [p for p in chain if _instructable(p)]
    dst = LANG_NAMES.get(cfg["idioma"], cfg["idioma"])
    out: dict[str, str] = {}
    # 1º em lotes de 10 (uma chamada para várias frases: bem mais rápido); o que voltar errado vai uma a uma
    batch_sys = (f"You shorten {dst} video game texts so they fit small text boxes. Input: JSON "
                 '{"id": {"text": "...", "max_chars": N}}. Keep the meaning and the tone; use shorter words, drop '
                 "filler words, abbreviate if needed; each ⟦n⟧ marker counts as 8 characters and must be kept "
                 'exactly once. Answer ONLY with JSON {"id": "shortened text in one line"}.')
    flat_of = {iid: text.replace("\n", " ") for iid, text, _l, _w in items}
    for k in range(0, len(items), 10):
        chunk = items[k:k + 10]
        req = json.dumps({iid: {"text": flat_of[iid], "max_chars": lines * width} for iid, _t, lines, width in chunk},
                         ensure_ascii=False)
        for p in smart:
            try:
                raw, _tok = p.chat(batch_sys, req, timeout=240)
                got = _parse_batch(raw)
            except (ProviderError, ValueError):
                continue
            for iid, *_ in chunk:
                v = got.get(iid)
                if isinstance(v, str) and placeholders_ok(flat_of[iid], v.strip()) and fits(iid, v.strip()):
                    out[iid] = v.strip()
            break
    for iid, text, lines, width in items:
        if iid in out:
            continue
        flat = flat_of[iid]
        system = (f"You shorten {dst} video game texts so they fit a small text box: at most {lines} line(s) "
                  f"of {width} characters, {lines * width} characters in total (each ⟦n⟧ marker counts as 8). "
                  "Keep the meaning and the tone; use shorter words, drop filler words, abbreviate if needed. "
                  "Keep every ⟦n⟧ marker exactly once. Answer only with the text, in one line.")
        got = _ask(smart, system, flat, lambda r, s=flat, i=iid: placeholders_ok(s, r) and fits(i, r))
        if got is not None:
            out[iid] = got
    return out
