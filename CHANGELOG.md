# Changelog

## 0.4.2 — 2026-11-07 (revisão para uso longe do PC)
- **Safe-mode nunca derruba o bot** (antes, entrar em safe-mode desligava o próprio bot e o `/sos off` ficava
  impossível de longe) e o `/sos off` religa exatamente o que desligou — antes o qBittorrent ficava parado.
  O bot avisa quando o safe-mode liga sozinho. Teste semanal só conta falha real (pytest ausente não conta).
- Jogo que não abre mostra o **motivo na tela** (cartão SD fora, jogo removido, emulador ausente).
- Plugin: jogo removido e baixado de novo na mesma sessão volta a aparecer (antes ficava escondido até reiniciar).
- Atualizar o plugin não exige mais reiniciar: o instalador pede ao Decky para recarregá-lo.
- Energia: download novo também pausa na bateria (antes baixava), o bot avisa, `/bateria sim|nao`;
  pausa que sobrou de antes de um reinício é retomada no carregador.
- Seeding limitado (razão 1.0 ou 60 min) para não gastar o pacote de dados do celular.
- Decky fora do ar (update do SteamOS): o `/sync` percebe e usa o caminho sem plugin (+ `/reiniciar`).
- Dolphin (GameCube/Wii) mapeado no controle do Deck quando ainda estava no teclado.
- Qualidade por jogo devolve o arquivo do emulador byte a byte igual (conferido no Deck nos 6 consoles).
- `dc x … --apply/--force/--confirm` voltaram a funcionar no terminal; `/remover` limpa também o banco.
- Busca de jogo por palavras (`/qualidade shadow dub 2x`); `/duplicados` diz se a cópia está no SD ou na memória.
- Serviços com `Restart=always`. Ferramentas de teste no aparelho: `tools/e2e_local.py`, `tools/quality_check.py`,
  `tools/bot_dryrun.py`.

## 0.4.0 — 2026-11-06
- **Duplicatas**: o bot confere antes de baixar (biblioteca e downloads em andamento; Switch pelo Title ID,
  demais pelo nome sem região/versão) e só baixa repetido com `/baixar`. O `/sync` não cria segundo atalho
  para um jogo que já existe (a cópia nova vai para a quarentena). `/duplicados` + `/remover` (com confirmação).
- **Remover jogo**: atalho sai do Steam ao vivo (plugin 0.4.0), arquivos vão para a quarentena (no SD, ficam no SD),
  download sai do qBittorrent. Atalho apagado por você no Steam **não é mais recriado** pela autocorreção.
- **Qualidade por jogo** (`/qualidade`): nativo/2x/3x/4x só para aquele jogo, aplicado ao abrir e devolvido ao fechar
  (inclusive quando o Steam fecha o jogo à força). DuckStation, PCSX2, Dolphin, PPSSPP e Ryujinx.
- **Controles**: `/controles` verifica cada emulador; layout do Switch por rótulo (A=A) aplicado pelo instalador.
- Correções de brechas: extração longa (>5 min) não perde o registro (antes podia gerar cópia "(novo)") nem conta
  como travamento; falta de espaço não manda o download para a quarentena (avisa e tenta de novo); ROM com o mesmo
  nome de um jogo da Epic/GOG entra com o console no nome; atalho manual com o mesmo nome agora é avisado.

## 0.3.0 — 2026-11-06
- Plugin do Decky 0.3.0: espera o Steam terminar de carregar antes de criar atalhos (corrige atalho
  perdido no reinício), autocorreção (recria atalhos sumidos), trava contra duplicação.
- Abas ao vivo: uma **coleção do Steam** por console/loja, mantida pelo plugin; TabMaster filtra por coleção.
- Abas por loja do Unifideck (Epic Games, GOG).
- Bot: aceita "Switch"/"PS2"… + `.torrent` encaminhado ou magnet solto; /sync automático ao terminar o download.
- Switch 2 (experimental, via Lichii) com dumps extraídos.
- Detecção automática de emuladores (EmuDeck, AppImage, Flatpak); conta Steam ativa em Decks com várias contas.
- /sync usa hardlink no mesmo disco (não duplica GBs).
- `dc x profile` (perfis de qualidade PS1/PS2), `dc x dedup` (relatório de duplicatas, nunca apaga).
- `dc restore --apply` fecha e reabre o Steam quando necessário.
- /sync abre **.7z e .rar** (7-Zip do SteamOS) com as mesmas regras de segurança do .zip; `.mdf` de PS2 vira `.iso`.
- Download que não entrou na biblioteca é tentado de novo sozinho (1x por hora, avisa só se entrar).

## 0.2.0
- Projeto v5.1 completo: segurança (M0), Operation Store (M18/M19), contratos (M27), biblioteca (M2),
  qualidade (M3), Telegram/torrent (M4), traduções IPS/BPS/UPS (M5), saves (M6), disco (M7),
  sensores (M20), diagnóstico (M21), status/testes (M10), updates (M11), setup/uninstall (M12/M15),
  recuperação (M16), privacidade/export (M17).

## 0.1.0
- Spikes S1–S6 e S10 validados (PC + Steam Deck LCD).
