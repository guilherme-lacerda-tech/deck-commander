# M9 — Fork do Panel de Control

**Status: não aplicado (bloqueado por decisão de segurança).**

A v5.1 exige, antes de qualquer PR, um teste que FALHE no upstream e PASSE no fork, para cada melhoria.
O plugin instalado no Deck veio de um zip (`~/Downloads/Panel.de.Control.zip`), sem repositório
upstream identificável, e as 10 melhorias mexem no Auto-TDP (potência do hardware). Sem upstream para
comparar e sem uma bancada de medição (FPS/consumo — exige MangoHud e cenário fixo, M10.2), aplicar
mudanças no controle de energia seria às cegas, o que a própria v5.1 proíbe.

O que libera o M9: o link do repositório oficial do Panel de Control. Com ele: clonar, escrever um teste
por melhoria, manter só as que falham no upstream, 1 PR cada, rebase mensal registrado aqui.

## Histórico de rebases
(nenhum)
