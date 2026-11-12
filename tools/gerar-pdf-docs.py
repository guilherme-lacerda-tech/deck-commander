"""Converte os .md do Deck Commander em HTML bonito e imprime em PDF com o Edge (sem dependências)."""
import html
import re
import subprocess
import sys
from pathlib import Path

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

CSS = """
@page { size: A4; margin: 16mm 15mm 18mm 15mm; }
body { font-family: 'Segoe UI', Arial, sans-serif; font-size: 10.5pt; line-height: 1.5; color: #1d232b; }
.capa { background: linear-gradient(135deg, #1a1f2e, #2b3a67); color: #fff; padding: 26px 28px; border-radius: 10px;
        margin-bottom: 18px; }
.capa h1 { color: #fff; border: 0; margin: 0 0 6px 0; font-size: 22pt; }
.capa p { margin: 0; color: #c9d4ff; font-size: 11pt; }
h1 { font-size: 18pt; color: #2b3a67; border-bottom: 2px solid #2b3a67; padding-bottom: 4px; }
h2 { font-size: 14pt; color: #fff; background: #2b3a67; padding: 6px 10px; border-radius: 6px; margin-top: 22px;
     page-break-after: avoid; }
h3 { font-size: 11.5pt; color: #2b3a67; margin: 14px 0 4px; page-break-after: avoid; }
code { font-family: Consolas, monospace; background: #eef1f7; padding: 1px 4px; border-radius: 3px; font-size: 9.5pt; }
pre { background: #1a1f2e; color: #e6edf3; padding: 10px 12px; border-radius: 6px; white-space: pre-wrap;
      word-break: break-all; page-break-inside: avoid; }
pre code { background: none; color: inherit; padding: 0; }
table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 9.5pt; page-break-inside: avoid; }
th { background: #2b3a67; color: #fff; text-align: left; padding: 5px 7px; }
td { border-bottom: 1px solid #d6dbe6; padding: 5px 7px; vertical-align: top; }
tr:nth-child(even) td { background: #f5f7fb; }
blockquote { border-left: 4px solid #f0a020; background: #fff7e6; margin: 10px 0; padding: 6px 12px; border-radius: 4px; }
hr { border: 0; border-top: 1px dashed #c3cad8; margin: 18px 0; }
a { color: #2b5cd6; text-decoration: none; }
li { margin: 2px 0; }
"""


def inline(t: str) -> str:
    t = html.escape(t, quote=False)
    t = re.sub(r"`([^`]+)`", lambda m: "<code>" + m.group(1) + "</code>", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"<a href='\2'>\1</a>", t)
    return t


def convert(md: str) -> str:
    out, lines, i = [], md.split("\n"), 0
    stack = []  # pilha de listas: (tipo, indent)

    def close_lists(to=0):
        while len(stack) > to:
            out.append("</%s>" % stack.pop()[0])
    while i < len(lines):
        ln = lines[i]
        if ln.strip().startswith("```"):
            close_lists()
            ind = len(ln) - len(ln.lstrip())
            code = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i][ind:] if lines[i][:ind].strip() == "" else lines[i])
                i += 1
            out.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
            i += 1
            continue
        if ln.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s\-:|]+\|$", lines[i + 1].strip()):
            close_lists()
            head = [c.strip() for c in ln.strip().strip("|").split("|")]
            rows = []
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in re.split(r"(?<!\\)\|", lines[i].strip().strip("|"))])
                i += 1
            t = "<table><tr>" + "".join(f"<th>{inline(h)}</th>" for h in head) + "</tr>"
            for r in rows:
                t += "<tr>" + "".join(f"<td>{inline(c.replace(chr(92) + '|', '|'))}</td>" for c in r) + "</tr>"
            out.append(t + "</table>")
            continue
        m = re.match(r"^(#{1,3}) (.*)", ln)
        if m:
            close_lists()
            out.append(f"<h{len(m.group(1))}>{inline(m.group(2))}</h{len(m.group(1))}>")
            i += 1
            continue
        if ln.strip() == "---":
            close_lists(); out.append("<hr>"); i += 1; continue
        if ln.startswith(">"):
            close_lists()
            q = []
            while i < len(lines) and lines[i].startswith(">"):
                q.append(lines[i].lstrip("> ").rstrip()); i += 1
            out.append("<blockquote>" + inline(" ".join(q)) + "</blockquote>")
            continue
        m = re.match(r"^(\s*)([-*]|\d+\.) (.*)", ln)
        if m:
            ind = len(m.group(1)); kind = "ol" if m.group(2)[0].isdigit() else "ul"
            while stack and stack[-1][1] > ind:
                out.append("</%s>" % stack.pop()[0])
            if not stack or stack[-1][1] < ind:
                stack.append((kind, ind)); out.append(f"<{kind}>")
            text = m.group(3)
            i += 1
            while i < len(lines) and lines[i].startswith(" " * (ind + 2)) and lines[i].strip() \
                    and not re.match(r"^\s*([-*]|\d+\.) ", lines[i]) and not lines[i].strip().startswith("```"):
                text += " " + lines[i].strip(); i += 1
            out.append("<li>" + inline(text) + "</li>")
            continue
        if not ln.strip():
            if not (i + 1 < len(lines) and re.match(r"^\s+([-*]|\d+\.) |^\s+```", lines[i + 1])):
                close_lists()
            i += 1
            continue
        close_lists()
        para = [ln.strip()]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#|\||>|```|\s*([-*]|\d+\.) )", lines[i]):
            para.append(lines[i].strip()); i += 1
        out.append("<p>" + inline(" ".join(para)) + "</p>")
    close_lists()
    return "\n".join(out)


def build(md_path: Path, pdf_path: Path, titulo: str, sub: str) -> None:
    md = md_path.read_text("utf-8")
    md = re.sub(r"^# .*\n", "", md, count=1)  # o título vai na capa
    md = md.replace("(TUTORIAL-INSTALACAO.md)", "(Tutorial de instalação — outro PDF)").replace(
        "(MANUAL.md)", "(Manual de uso — outro PDF)")
    body = f"<div class='capa'><h1>{html.escape(titulo)}</h1><p>{html.escape(sub)}</p></div>" + convert(md)
    doc = f"<!doctype html><html lang='pt-br'><head><meta charset='utf-8'><title>{html.escape(titulo)}</title>" \
          f"<style>{CSS}</style></head><body>{body}</body></html>"
    import shutil
    import tempfile
    tmpd = Path(tempfile.gettempdir())
    h = tmpd / "dc-doc.html"
    tmp_pdf = tmpd / "dc-doc.pdf"
    tmp_pdf.unlink(missing_ok=True)
    h.write_text(doc, "utf-8")
    subprocess.run([EDGE, "--headless", "--disable-gpu", "--no-pdf-header-footer", f"--user-data-dir={tmpd / 'edge-pdf'}",
                    f"--print-to-pdf={tmp_pdf}", "file:///" + str(h).replace("\\", "/")], check=True, timeout=120)
    import time
    for _ in range(120):  # o msedge.exe sai antes do processo filho terminar de gravar o PDF
        if tmp_pdf.exists() and tmp_pdf.stat().st_size > 0:
            time.sleep(1.5)
            break
        time.sleep(0.5)
    shutil.move(str(tmp_pdf), str(pdf_path))
    h.unlink()
    print(pdf_path, pdf_path.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    root = Path(sys.argv[1]); out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
    build(root / "docs/TUTORIAL-INSTALACAO.md", out / "Deck Commander - Tutorial de instalacao.pdf",
          "Deck Commander — Tutorial de instalação", "Como montar tudo do zero: Steam Deck, tradução, PC")
    build(root / "docs/MANUAL.md", out / "Deck Commander - Manual de uso.pdf",
          "Deck Commander — Manual de uso", "Tudo o que dá para fazer no dia a dia, pelo Telegram e pelo Deck")
    build(root / "docs/VISAO-GERAL.md", out / "Deck Commander - Visao geral do projeto.pdf",
          "Deck Commander — Visão geral do projeto", "Tudo o que o sistema faz hoje, o que foi testado e ideias do que adicionar")
    if (root / "docs/REVISAO-NOTURNA.md").exists():
        build(root / "docs/REVISAO-NOTURNA.md", out / "Deck Commander - Revisao noturna.pdf",
              "Deck Commander — Revisão noturna", "O que foi conferido, o que estava errado e foi corrigido, e o que falta")
