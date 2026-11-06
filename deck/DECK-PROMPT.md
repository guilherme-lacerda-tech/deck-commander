# Prompt para o Claude Code no Steam Deck

> Copie tudo abaixo da linha e cole no Claude Code rodando no Deck (Modo Desktop),
> com a pasta `deck-commander` já copiada para `~/deck-commander`.

---

Você vai executar os **spikes de validação no Steam Deck real** do projeto Deck Commander.
O código e os testes já foram feitos e validados no PC (Windows). Aqui você confirma o que só o
hardware real prova. Responda sempre em português.

## Contexto (leia antes de agir)
- Projeto: `~/deck-commander`. Leia `docs/ANALISE-v5.1.md` e `docs/SPIKES-REPORT.md`.
- Núcleo em Python 3.11+ só com biblioteca padrão (pacote `dc/`). CLI: `python3 -m dc --help`.
- Spec completa: v5.1 (resumida na análise). Não adicione escopo; ideias vão para `docs/sugestoes-futuras.md`.

## Regras invioláveis
1. **Nunca** escrever em `/usr`, `/etc`, nem rodar `steamos-readonly disable`, `pacman`, `sudo`.
   Tudo fica no `$HOME`.
2. **Nunca** rodar `srm nuke` nem qualquer comando que remova atalhos em massa.
3. **Nunca** modificar `shortcuts.vdf`, `localconfig.vdf` ou configs reais de emulador sem:
   (a) backup com `python3 -m dc backup create` concluído OK, (b) mostrar o dry-run,
   (c) aprovação explícita do usuário no chat. Tudo o mais é leitura.
4. **Nunca** fechar/matar o Steam sem perguntar (o usuário pode estar com algo aberto).
5. Interação mínima: faça tudo o que for leitura/teste isolado sozinho; junte as perguntas e as
   ações físicas (tirar carregador, reiniciar) e peça de uma vez só, no momento certo.
6. Não marque nada como PASSOU sem evidência (comando + saída).

## Passo 0 — Ambiente de testes (sozinho)
```bash
cd ~/deck-commander
python3 --version            # precisa >= 3.11
python3 -m venv ~/.local/share/deck-commander/venv
~/.local/share/deck-commander/venv/bin/pip install pytest
~/.local/share/deck-commander/venv/bin/python -m pytest -q
```
Esperado: todos os testes passam também no Linux real (aqui o lock usa `fcntl.flock` de verdade,
no PC usou o fallback do Windows). Se algo falhar, diagnostique e corrija **com teste**.

## Passo 1 — Inventário somente leitura (sozinho)
```bash
python3 deck/deck_probe.py
```
Leia `~/deck-commander-probe/probe.json` e registre no relatório: modelo (Jupiter = LCD, Galileo = OLED),
versão do SteamOS, sessão atual, portas abertas (confirme se 1337 é o Decky e se 8080/8765 estão livres —
achado F13), ferramentas disponíveis, emuladores e caminhos de config encontrados, plugins Decky,
local do Steam ROM Manager.

## Passo 2 — S6 Energia (1 ação física)
```bash
python3 -m dc power
```
Rode com o carregador **conectado**, depois peça ao usuário para **desconectar**, rode de novo, e
peça para reconectar. Critério: `ac_online` correto nos dois casos, fontes descobertas pelo `type`
(não por nome fixo), bateria lida. Se o usuário tiver os dois modelos (LCD e OLED), repetir no outro;
se não, registrar como parcial.

## Passo 3 — S1 Reboot real (1 ação física)
```bash
python3 deck/s1_reboot.py prepare
# usuário reinicia o Deck
python3 deck/s1_reboot.py check
```
Critério: `integrity_check: ok`, operação passa de `running` para `interrupted`, lock adquirível.
Se a sessão do Claude Code cair no reboot, o usuário reabre e você continua a partir do `check`.

## Passo 4 — S5 Adaptadores (sozinho, só em CÓPIAS)
Para cada emulador encontrado no probe (DuckStation, PCSX2, Dolphin, RetroArch, **PPSSPP** — são
5 adaptadores, achado F8):
1. Identifique no arquivo real a chave de escala de resolução interna, backend/renderer, aspect ratio
   e limitador de FPS. Documente em `docs/adapters-keys.md` (arquivo, seção, chave, valores válidos,
   versão do emulador).
2. Copie o arquivo para `~/deck-commander-spikes/s5/<emulador>/` e, **na cópia**, escreva os 3 perfis
   (Econômico/Equilibrado/Desempenho) e leia de volta. Critério: valor escrito = valor lido, resto do
   arquivo byte-a-byte igual.
3. Implemente `dc/adapters/<emulador>.py` com `supports()`, `write(profile)`, `read_back()` e testes
   com o arquivo copiado como fixture (sem segredos — retire linhas de usuário/senha).
4. Validar que o emulador **respeita** o valor (abrir o jogo) fica para o final, como pergunta ao usuário.

## Passo 5 — S3 SRM + Gaming Mode (precisa aprovação)
Leia F1 na análise: no Gaming Mode o Steam é a sessão; "fechar o Steam" reinicia a sessão.
1. Sozinho: localize o SRM, rode `--help`/`list` (somente leitura) e documente os comandos de CLI
   disponíveis nesta versão.
2. Com aprovação: em Modo Desktop, backup (`python3 -m dc backup create`, com `~/.config/deck-commander/backup.toml`
   apontando para `shortcuts.vdf`, `localconfig.vdf` e as configs de emulador — modelo em
   `config/backup.example.toml`), depois adicionar via SRM CLI **um** atalho de teste (ROM homebrew,
   ex.: um `.gba` homebrew livre) com Steam fechado; reabrir; conferir contagem de atalhos e coleções
   antes/depois; remover o atalho de teste do mesmo jeito.
3. Só documentar (não testar sem o usuário pedir): o que acontece com `steam -shutdown` em Gaming Mode.
   Registre as alternativas (API `SteamClient.Apps.AddShortcut` via plugin Decky × janela offline).

## Passo 6 — S4 Playtime (leitura primeiro)
1. Sozinho: em `localconfig.vdf` (use `dc.vdf.load_text`), descubra **onde** fica o playtime de atalhos
   não-Steam e com qual ID (o `appid` do `shortcuts.vdf`? o da fórmula `dc.vdf.shortcut_appid`? o 64-bit?).
   O probe já lista `appid` × `appid_formula` dos primeiros atalhos.
2. Com aprovação + backup: renomear um atalho de teste que tenha horas e verificar se o playtime fica
   órfão (achado F2). Restaurar do backup ao final.

## Entregável
Escreva `docs/SPIKES-DECK-REPORT.md` neste formato para cada spike:

```
### S<n> — <nome>
Status: PASSOU / FALHOU / PARCIAL
Evidência: comandos + saídas relevantes
Problemas encontrados:
Impacto no projeto:
```
E uma **Conclusão** com: módulos liberados, módulos bloqueados (motivo), ajustes necessários na v5.1.

Depois faça `git add -A && git commit` no repositório (sem `probe.json` cru — ele pode ter dados
pessoais; só o resumo vai no relatório). No fim, liste ao usuário **numa única mensagem** tudo que
ainda depende dele.
