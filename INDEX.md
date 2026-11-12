# Índice do repositório

- `README.md` — o que é, instalação, uso · `docs/STATUS.md` — estado de cada módulo · `CHANGELOG.md`
- `ARCHITECTURE.md` · `TROUBLESHOOTING.md` · `PRIVACY.md` · `docs/desenvolvimento/FORK-PANEL-DE-CONTROL.md` · `recovery/README.md` · `docs/COMANDOS.md`
- `dc/` — núcleo Python (ver ARCHITECTURE.md) · `dc/adapters/` — adaptadores de emulador
- `decky-plugin/` — plugin do Decky (JS puro + backend Python)
- `modules/*/contract.toml` — contratos entre módulos (M27)
- `config/backup.example.toml` — modelo de fontes de backup
- `setup-deck.sh` · `uninstall-module.sh` · `uninstall-deck-commander.sh` · `safe-mode.sh`
- `tests/` — pytest (rodam no CI e semanalmente no Deck)
- `tools/` — diagnóstico no Deck: `cef_eval.py`, `bootstrap_collections.py`, `deck_probe.py`, spikes `s1_reboot.py`/`s5_real_copy.py`
- `docs/PC-REMOTO.md` — jogos do PC no Deck (aba Computador): `dc/pc_remoto.py` + `tools/pc/biblioteca-pc.ps1`
- `dc/transferir.py` + `tools/pc/transferir-do-deck.ps1`/`.bat` — transferência segura de um jogo do Deck para o PC (`docs/TRANSFERENCIA.md`)
- `dc/receber.py` + `tools/pc/enviar-para-deck.ps1` — PC → Deck (`/trazer`): área de recebimento, sha256sum, instalação, emulador oficial no Deck
- `tools/pc/transferencia-funcoes.psm1` (+ `transferencia.Tests.ps1`) — manifesto do PC, emulador oficial no PC (`emulador-oficial.ps1`); origens em `config/emuladores-oficiais.json`
- `dc/painel.py` + `decky-plugin/` — interface gráfica no menu "…" do modo de jogo (ações JSON que reaproveitam os comandos do bot; `docs/MANUAL.md`, "Pelo painel do Deck")
- `docs/desenvolvimento/` — análise da spec v5.1, relatórios de spikes, histórico
- `tools/pc/Assistente Deck Commander.bat` → `assistente.ps1` (janela WinForms das Partes 3–5 do `docs/TUTORIAL-INSTALACAO.md`) + `assistente-funcoes.psm1` (lógica testável; testes Pester em `assistente.Tests.ps1`)
