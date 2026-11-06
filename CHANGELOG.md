# Changelog

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
