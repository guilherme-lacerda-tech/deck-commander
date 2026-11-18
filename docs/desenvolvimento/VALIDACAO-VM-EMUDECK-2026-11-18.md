# Validação em VM SteamOS + EmuDeck — 18/11/2026

Esta rodada foi feita numa VM SteamOS real, não em mocks do computador anfitrião. O disco da VM foi conferido antes e depois de cada reinicialização do QEMU.

## Ambiente observado

- SteamOS iniciado normalmente, com sessão de desktop e SSH operacional.
- EmuDeck detectado; a árvore `~/Emulation/roms` estava presente.
- Emuladores reais escolhidos no ambiente: DuckStation AppImage, PCSX2 AppImage do EmuDeck, Dolphin Flatpak e Ryujinx AppImage.
- O recurso de "continuar" foi confirmado **desligado por padrão** nesse Deck com EmuDeck, para não alterar a configuração dos emuladores dele.

## Casos executados dentro da VM

1. Instalação de plugin vazia, parcial, correta, inválida e com manifesto normalizado.
2. Configuração de emulador ausente, inválida, válida e apontando para binário inexistente.
3. Instalação sem EmuDeck e com EmuDeck: jogos existentes ficam fora por padrão, importação é por console, e migração não cria centenas de atalhos de Wii.
4. Escolha de emulador: prioriza AppImage/configuração do EmuDeck e não cria um PCSX2 Flatpak vazio.
5. E2E protegido: não inicia se houver jogo aberto; sincronização, duplicata, atalho e limpeza têm casos automatizados.
6. Save state/"continuar": expiração do ponto antigo e preservação do save normal.

Resultado da matriz focada: **56 aprovados**.

Resultado da suíte integral dentro do SteamOS: **990 aprovados, 4 ignorados**, em 5 min 16 s.

## Correção descoberta pela VM

A primeira execução integral falhou porque a detecção de RetroArch usava a pasta do usuário real mesmo quando recebia uma pasta de teste. Isso podia contaminar uma inspeção isolada. A detecção agora deriva os núcleos RetroArch da pasta efetivamente inspecionada; os testes de save state e launcher também isolam o EmuDeck do sistema que executa pytest. A suíte completa passou depois dessa correção.

## Limite gráfico, mantido explícito

Foram tentados WHPX e VirtIO com OpenGL. O SteamOS da VM não encontra uma GPU Vulkan compatível (`vulkaninfo` não detecta dispositivo), por ser uma imagem projetada para GPU AMD do Steam Deck. Assim, Steam em modo jogo, Decky e a renderização 3D não podem ser validados graficamente nessa VM. Essa parte foi validada no Steam Deck físico; a VM valida o cenário EmuDeck/instalação/configuração.
