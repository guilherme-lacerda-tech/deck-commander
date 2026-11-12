"""Entradas maliciosas/absurdas em todos os comandos do bot e ações do painel (revisão de lançamento 11/11/2026).
Roda dentro do teste de usuário novo (tools/usuario_novo.sh), sem rede e numa pasta pessoal vazia."""
import json
import re
import subprocess
import sys
import time

from dc import bot as B
from dc import painel
from dc.paths import get_paths

RUINS = ["'; rm -rf ~; echo '", "$(touch /tmp/dc-pwned)", "`touch /tmp/dc-pwned`", "../../../../etc/passwd",
         "ç" * 3000, "99999999999999999999", "-1", "\x00\x01\x1b[31m", "%s%n", "{{7*7}}", "--help"]
p = get_paths()
p.ensure()
b = B.Bot(p, "123:fake")
b.cfg = {"allowed": [1]}
b.save_cfg = lambda: None
b.send = lambda *a, **k: None
b.call = lambda *a, **k: {}
b.limited = lambda uid: False
cmds = sorted(set(re.findall(r"(/[a-z_]+)", B.HELP)) - {"/sync", "/update", "/reboot", "/desligar", "/sos"})
quebrou = 0
for c in cmds:
    for r in RUINS:
        t0 = time.monotonic()
        try:
            b.handle(1, 1, f"{c} {r}")
        except SystemExit:
            pass
        except Exception as e:  # noqa: BLE001
            quebrou += 1
            print(f"QUEBROU  {c} {r[:20]!r}: {type(e).__name__}: {str(e)[:150]}")
        if time.monotonic() - t0 > 20:
            print(f"LENTO    {c} {r[:20]!r}: {time.monotonic() - t0:.0f}s")
for nome in sorted(painel.ACOES):
    for campo in ("gid", "nome", "uri", "op", "acao", "jogo", "alvo"):
        args = json.dumps({campo: RUINS[0], "gid": RUINS[3], "sim": True})
        try:
            pr = subprocess.run([sys.executable, "-m", "dc.painel", nome], input=args, capture_output=True,
                                text=True, timeout=60)
        except subprocess.TimeoutExpired:
            print(f"LENTO    painel {nome}: mais de 60 s")
            break
        if "Traceback" in pr.stderr or not any(l.startswith("{") for l in pr.stdout.splitlines()):
            quebrou += 1
            print(f"QUEBROU  painel {nome} ({campo}): {pr.stderr.strip()[-160:]}")
        break
import os  # noqa: E402
print("INJEÇÃO FUNCIONOU!" if os.path.exists("/tmp/dc-pwned") else "nenhuma injeção de comando funcionou")
print(f"FUZZ: {quebrou} quebra(s) em {len(cmds) * len(RUINS)} comandos do bot + {len(painel.ACOES)} ações do painel")
