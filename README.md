# Deck Commander

Centro de comando para o Steam Deck (spec v5.1). Estado: **fase de spikes**.

- Análise de falhas da v5.1: [docs/ANALISE-v5.1.md](docs/ANALISE-v5.1.md)
- Resultado dos spikes no PC: [docs/SPIKES-REPORT.md](docs/SPIKES-REPORT.md)
- Prompt para o Claude Code no Deck: [deck/DECK-PROMPT.md](deck/DECK-PROMPT.md)

## Requisitos
Python 3.11+ (só biblioteca padrão). Testes: `pytest`.

```bash
python3 -m pytest -q
python3 -m dc --help
```

## Instalar no Deck (Modo Desktop)
Copie a pasta para `~/deck-commander` e siga `deck/DECK-PROMPT.md`.
Nada é instalado fora do `$HOME`.
