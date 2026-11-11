# Plano da versão 0.7.0

Código escrito pelas IAs locais do PC (qwen3-coder 30B via Ollama, `tools/ia-local-codigo.py`) a partir de
especificações curtas; revisão, testes e integração feitos depois. Ordem: do mais simples/útil ao mais pesado.

| # | Módulo | O que entra | Situação |
|---|---|---|---|
| 1 | dc-power | TDP automático por console ao abrir o jogo (SteamOS Manager, sem root) e volta ao fechar; dock/TV detectada → TDP máximo | em andamento |
| 2 | dc-audio | Mixer jogo × música (PipeWire/pactl), play/pause/próxima e "tocando agora" (MPRIS pelo busctl), playlists rápidas, `/musica` | precisa do Spotify instalado no Deck (Flathub) — pedir OK |
| 3 | TV | Botão "Jogar na TV" e `/tv`: o agente da casa liga a TV no PC e o Sunshine transmite | agente já tem o modo TV |
| 4 | Limpeza de disco | "Não joga X há 3 meses e ocupa 20 GB: levar para o PC ou desinstalar?" (último jogo pelo log do dc-launch) | — |
| 5 | Glossário de franquia | Termos guardados por série (ex.: Mario) e usados em todos os jogos dela | — |
| 6 | `/corrigir` | Frase estranha → corrige só ela no mod, sem refazer o jogo (por texto primeiro; por foto exige um modelo de visão local) | — |
| 7 | Patches de melhoria | 60 fps / widescreen pelos bancos de patch que os próprios emuladores já trazem (PCSX2, DuckStation, Dolphin), sem baixar ROM modificada | — |
| 8 | Controle remoto no PC | Antes do stream, o PC ajusta o controle do emulador | — |
| 9 | Saves Deck ↔ PC | Sincronizar com conflito perguntado (data) | maior; depois |
| 10 | Shaders à noite | Na tomada e parado, abre cada jogo 1 min para gerar o cache | depois |
| 11 | Fire Stick | Guia + PIN de pareamento do Sunshine no painel | depois |
| 12 | Texturas (OCR) | Estudo de viabilidade | depois |

**Fora do plano:** compartilhar ROMs com outra pessoa (distribuir cópias de jogos). O "modo família" pode
compartilhar configurações, glossários e a lista de traduções — cada pessoa usa os próprios jogos.
