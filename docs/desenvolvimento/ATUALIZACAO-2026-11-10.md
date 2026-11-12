# Atualização do sistema — 10/11/2026 (pente fino)

Feito em paralelo com a sessão "Análise e melhorias do projeto", no mesmo checkout. Eu commitei só os meus arquivos.
A tradução do Final Fantasy (tarefa `36f85722cec7`) seguiu rodando o tempo todo. **O bot não foi reiniciado.**

## Problema | Como reproduzi | Corrigido? | Commit/teste

| Problema | Como reproduzi | Corrigido? | Commit / teste |
|---|---|---|---|
| Magnet incompleto ou inválido (`magnet:?xt`, `/add abc`, `/add switch notamagnet`) ia direto para o qBittorrent | Chamei `handle_message` com essas mensagens, sem rede | sim | `77702d6` + `6dc605f` · `test_bot_entradas.py::test_invalid_magnet_*` |
| Console escrito errado no `/add` (`/add Swich magnet…`) virava a categoria "Swich" no qBittorrent | idem | sim | `test_misspelled_console_in_add_*` |
| "Switch magnet:?…" na mesma mensagem: o bot guardava o console e **ignorava o magnet** | idem | sim | `test_console_and_magnet_in_same_message` |
| "playstation 5", "PS5" e "Xbox One" eram aceitos como PS1/Xbox | idem | sim (agora: "Não conheço o console") | `test_console_names` |
| Arquivo `.torrent` falso (HTML ou zip renomeado) ia para o qBittorrent | `urlopen` falso devolvendo HTML | sim | `test_file_that_is_not_a_torrent` |
| Internet caindo enquanto o bot baixa o `.torrent` do Telegram dava "erro interno" | `urlopen` que lança `OSError` | sim (mensagem clara) | `test_torrent_download_fails_network` |
| Botão de mensagem antiga: o bot ficava em silêncio | callback com código que não existe mais | sim ("botão antigo, mande de novo") | `test_old_button_gets_an_answer` |
| Botão cujo comando dava erro: ficava sem resposta | `handle` que lança erro | sim | `test_button_whose_command_crashes_still_answers` |
| `/console` e `/aprovar` sem argumento respondiam "Comando desconhecido" | `handle_message` | sim (mostram o uso) | `test_commands_without_arguments_show_usage` |
| `/traduzir biblioteca` num Deck **sem nenhum jogo** (caso do Deck do seu irmão) dava erro | Deck vazio em pasta temporária | sim | `test_translate_library_on_fresh_deck_without_games` |
| Mensagem vazia, só espaço, emoji ou 5.000 caracteres | idem | ok (nunca dá erro; espaço não gera mais "Não conheço o console \"\"") | `test_empty_or_weird_messages_never_raise` |
| `dc x diagnose` acusava "lançador quebrado" no `psx-sles-00524`, que você **removeu** | `dc x diagnose` no Deck | sim, implantado | `245ff9d` · `test_diagnose_removido.py` |
| A dica do diagnóstico mandava rodar `dc db index`, comando que não existe | idem | sim (`python3 -m dc x db index`) | idem |
| `/diagnostico` quebrava num Deck em que o Steam ainda não teve login | teste sem usuário Steam | sim | `test_diagnose_without_steam_login_does_not_crash` |
| **3 torrents sem fontes travavam a fila inteira.** O qBittorrent do Deck tinha 3 vagas de download e contava torrent parado como vaga | Li as preferências do qBittorrent no Deck: `max_active_downloads=3`, `dont_count_slow_torrents=False` | sim, implantado (aplicado no qBittorrent agora; o serviço de energia reaplica 1x/h) | `aebe3e9` · `test_fila_sem_fontes.py` |
| Torrent sem fontes ou com erro (disco cheio, cartão SD removido): ninguém avisava | — | **solução pronta na branch `pronto/aviso-sem-fontes` — aguarda seu OK para implantar** | `4a0d6db` · `test_aviso_sem_fontes.py` |
| Atalho duplicado (Shadow of the Colossus) | Contei os atalhos no Deck: 36 do Deck Commander, nenhum nome, jogo ou AppID repetido | ok hoje (correção da revisão anterior) | — |
| Atalhos do Unifideck (500) | O código só mexe em atalhos `dc-launch`; o `library.py` pula os do Unifideck | ok | — |

### Regressões antigas (erros que já aconteceram e têm teste)

Xbox 360 caindo como Xbox (`test_x360.py`), RAR dividido e `.mdf/.mds` com subcanal (`test_rar_partes_mdf.py`), nome `SLES_xxxxx` e AppID com sinal (`test_plugin_bridge.py`, `test_dedup_remove_quality.py`), `.nsz` (`test_traducao.py`), "fora do padrão" (`test_generico.py`), texto em japonês falso (`test_idioma.py`), PCSX2 não fechando e jobs mortos (`test_tuning.py`, `test_s1_concurrency.py`). Conferi isso procurando os testes por palavra-chave, sem reler cada um. Esta sessão acrescentou os testes da tabela acima. Não achei teste específico para "MangoHud sem gravar no flatpak" nem para "túnel do PC caído" além do pulo de provedor em `test_traducao.py`.

## Ainda depende de você

1. **OK para a branch `pronto/aviso-sem-fontes`.**
   - **Plano:** o bot avisa uma vez quando um download passa 30 min sem fontes, e quando ele para com erro (disco cheio ou cartão SD fora). Para implantar: `git merge pronto/aviso-sem-fontes`, enviar `dc/bot.py` e reiniciar o bot (**só depois de a tradução do Final Fantasy terminar**).
   - **O que muda para você:** em vez de um download que nunca anda em silêncio, chega no Telegram "⚠️ «jogo» está há mais de 30 min sem fontes… os outros downloads continuam".
2. **As correções do bot desta madrugada estão na main e testadas, mas não estão rodando.** Isso vale para as minhas (`77702d6`, `6dc605f`) e para as da outra sessão (`46227f8`, `5023619`). O bot só pega código novo quando reinicia, e eu não reiniciei por causa da tradução.
   - **Plano:** quando o bot avisar que o FF terminou, rodar `git archive HEAD dc/ | ssh … "cd ~/deck-commander && tar -x"` e depois `systemctl --user restart deck-commander-bot`. Reiniciar o bot não para as traduções, porque elas rodam como serviço próprio.
3. **Dois plugins de TDP instalados ao mesmo tempo: PowerTools e "Panel de Control".** Os dois mexem em TDP e ventoinha e podem brigar entre si. O auto-ajuste do Deck Commander não mexe em TDP, só na resolução do emulador, então não conflita com nenhum dos dois.
   - **Plano:** desative um deles no menu do Decky. Sugiro manter só o PowerTools.
   - Isso não tem branch porque desinstalar plugin é decisão sua.
4. **Banco × biblioteca (`dc x diagnose`):** "GOW GoS rus" está no Steam mas fora do banco, e há 1 arquivo registrado que não existe mais. Não afeta jogar.
   - **Plano:** rodar `python3 -m dc x db index` no Deck. Só registra arquivos, não apaga nada.
   - Deixei para você porque o diagnóstico marca isso como "usuário decide".
5. **Controles do Azahar (3DS), Cemu (Wii U) e RPCS3 (PS3):** é preciso configurar uma vez no modo desktop. Isso continua igual.
6. **Não testei o plugin se recuperando depois de reiniciar o Steam.** Reiniciar o Steam no meio da tradução e com você podendo estar jogando não era seguro.
   - **Plano:** com o Deck livre, mande `/reiniciar` e depois `/sync`. O plugin 0.4.1 já tem a trava contra duplicação, que confere se o atalho ainda existe.
