# Problemas comuns

**Antes de tudo:** `/diagnostico` no bot (ou `python3 -m dc x diagnose` no Deck) mostra o estado real.

| Sintoma | O que fazer |
|---|---|
| Jogo novo não aparece | Abra o Decky → **Deck Commander** → "Verificar agora". O painel mostra a fila e erros. Sem o plugin (ou com o Decky fora do ar depois de um update do SteamOS), o bot pede `/reiniciar`. |
| Jogo aparece em "All Games" mas não na aba | Confirme que o TabMaster está instalado. As abas seguem coleções do Steam; a primeira vez depois de instalar o TabMaster exige um reinício. |
| Jogo não abre | Aparece um aviso na tela com o motivo (cartão SD fora, jogo removido, emulador ausente). Detalhes em `~/.local/state/deck-commander/logs/launch.log`. Emulador ausente: `./setup-deck.sh --all`. |
| Jogo repetido | `/duplicados` e `/remover <nº>` (pede confirmação; arquivos ficam 30 dias na quarentena). |
| Jogo pesado ou com gráfico estranho | `/qualidade <jogo> 2x` ou `nativo` — só para aquele jogo. Ver [docs/QUALIDADE-E-CONTROLES.md](docs/QUALIDADE-E-CONTROLES.md). |
| Botão errado / controle não responde | `/controles`. O Switch usa A=A; para o padrão do Ryujinx: `python3 -m dc x controles positional`. |
| Bot não responde | Sem internet no Deck, ou o Deck está dormindo (com a tela apagada ele não baixa nem responde). `systemctl --user status deck-commander-bot`. |
| Downloads parados | Na bateria eles pausam sozinhos (o bot avisa). `/bateria sim` libera fora da tomada; abaixo de 30% sempre pausa. |
| Seeding parou | De propósito: depois de baixar, compartilha até razão 1.0 ou 60 min (protege o pacote de dados). Ajuste `seed_ratio`/`seed_minutes` em `~/.config/deck-commander/deck.json` (-1 = sem limite). |
| "Modo de segurança" | Liga sozinho se os testes semanais falharem 2x ou o `/sync` travar 3x. Downloads e automações param, **o bot continua**. Veja `/diagnostico` e mande `/sos off`. |
| Aviso de atualização ao abrir emulador | Rode `./setup-deck.sh --all` de novo (idempotente). |
| Algo deu muito errado | `/sos` (ou `./safe-mode.sh`): desliga automações, não apaga nada. Ver [recovery/README.md](recovery/README.md). |

Plugin, para quem desenvolve: erros de carregamento aparecem em `~/.local/share/Steam/logs/webhelper_js.txt`
(procure por "Deck Commander"); `python3 tools/cef_eval.py '<expressão JS>'` avalia no contexto do Steam.
`./setup-deck.sh` recarrega o plugin sozinho quando ele muda (sem reiniciar). Testes no aparelho:
`python3 tools/e2e_local.py` (download → biblioteca → duplicata → remoção, sem internet) e
`python3 tools/quality_check.py` (qualidade por jogo nos arquivos reais, devolvendo tudo).
