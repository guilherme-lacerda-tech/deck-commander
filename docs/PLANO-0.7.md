# Plano da versão 0.7.0

Código escrito pelas IAs locais do PC (qwen3-coder 30B via Ollama, `tools/ia-local-codigo.py`) a partir de
especificações curtas; revisão, testes e integração feitos depois. Ordem: do mais simples/útil ao mais pesado.

| # | Módulo | O que entra | Situação |
|---|---|---|---|
| 1 | dc-power | TDP automático por console ao abrir o jogo (SteamOS Manager, sem root) e volta ao fechar; dock/TV detectada → TDP máximo | ✅ no ar (testado: 12→7→12 W) |
| 2 | dc-audio | Mixer jogo × música (PipeWire/pactl), play/pause/próxima e "tocando agora" (MPRIS pelo busctl), playlists rápidas, `/musica` | ✅ no ar (Spotify instalado; falta você entrar na conta) |
| 3 | TV | Botão "Jogar na TV" e `/tv`: o agente da casa liga a TV no PC e o Sunshine transmite | ✅ no ar (/pc tv e botão no painel; só em casa) |
| 4 | Limpeza de disco | "Não joga X há 3 meses e ocupa 20 GB: levar para o PC ou desinstalar?" (último jogo pelo log do dc-launch) | ✅ no ar (painel → Desinstalar jogos → Liberar espaço) |
| 5 | Glossário de franquia | Termos guardados por série (ex.: Mario) e usados em todos os jogos dela | ✅ no ar (usado antes de toda tradução; vai junto na família) |
| 6 | `/corrigir` | Frase estranha → corrige só ela no mod, sem refazer o jogo (por texto primeiro; por foto exige um modelo de visão local) | ✅ no ar (foto + OCR qwen2.5vl:7b no PC, testado lendo legenda) |
| 7 | Patches de melhoria | 60 fps / widescreen pelos bancos de patch que os próprios emuladores já trazem (PCSX2, DuckStation, Dolphin), sem baixar ROM modificada | ✅ no ar (painel → Qualidade → Melhorias: 16:9 e sem tremido) |
| 8 | Controle remoto no PC | Antes do stream, o PC ajusta o controle do emulador | ✅ no ar (perfil de stream aplicado antes e restaurado depois; salve uma vez com tools\pc\perfil-controle.ps1 -Acao Salvar) |
| 9 | Saves Deck ↔ PC | Sincronizar com conflito perguntado (data) | ✅ no ar (/saves <jogo>; testado com o Donkey Kong: 4 saves iguais) |
| 10 | Shaders à noite | Na tomada e parado, abre cada jogo 1 min para gerar o cache | ✅ no ar (opcional, painel → Qualidade) |
| 11 | Fire Stick | Guia + PIN de pareamento do Sunshine no painel | ✅ no ar (docs/FIRE-STICK.md + painel → PC com QR) |
| 12 | Texturas (OCR) | Estudo de viabilidade | ✅ estudo pronto (docs/ESTUDO-TEXTURAS.md) |

**Família:** ✅ no ar — catálogo com magnet + tradução pronta pela Tailscale; o jogo baixa pelo link no Deck de cada um; arquivo de jogo nunca é copiado entre os Decks.
compartilhar configurações, glossários e a lista de traduções — cada pessoa usa os próprios jogos.
