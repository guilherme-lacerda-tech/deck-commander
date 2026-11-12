# Deck Commander — estado de implementação (2026-11-06, v0.2.0)

Deck LCD, SteamOS 3.9.5. 92 testes automatizados passando no PC e no Deck (também rodam semanalmente
pelo `deck-commander-tests.timer`). Instalado com `./setup-deck.sh --all --no-downloads`.

| Módulo | Estado | Evidência / observação |
|---|---|---|
| M-1 Inventário | ✅ | `dc inventory`; procedência `unknown` sem chute; SD incluído |
| M0 Segurança | ✅ | backup verificado + fallback + quarentena (S2), restore com guarda do Steam, safe-mode ≠ uninstall, backup diário |
| M18+M19 Operation Store | ✅ | lock + reentrância validada (S1 com reboot real), aprovação 1h, `db index/verify` |
| M27 Contratos | ✅ | 21 `contract.toml`, `dc contracts`, setup usa dependências |
| M1 Plugins | ✅ parcial | dono por hardware em ARCHITECTURE.md, `plugins.lock`; **TabMaster: instalação manual** (Decky não tem CLI) |
| M2 Biblioteca | ✅ | launcher fixo + mapa (escolha do usuário), 22 jogos testados pelo usuário, capas SteamGridDB |
| M3 Qualidade | ✅ parcial | 8 consoles; DuckStation/PCSX2 respeitam ajuste manual (5x/3x); Dolphin/PPSSPP/RetroArch no perfil equilibrado com read-back; **cores do RetroArch pendentes** (download bloqueado sem sua autorização) |
| M4 Telegram/torrent | ✅ código / ⏳ ativação | bot, /sync, classificação, ZIP seguro, multidisco .m3u, ROM hack, timeout, jogo aberto, energia; **falta: qbittorrent-nox (download) e token do bot** |
| M5 Traduções | ✅ parcial | IPS/BPS/UPS nativos com CRC; **XDelta e .exe detectados e recusados** (precisam de xdelta3 / Proton) |
| M6 Saves | ✅ | 4 tipos separados, backup diário, import com conflito que nunca sobrescreve |
| M7 Disco | ✅ | `dc x disk` (última sessão = LastPlayTime do shortcuts.vdf, achado do S4), só sugere |
| M20 Sensores | ✅ | estado por sensor, unknown ≠ zero; TDP/FPS indisponíveis (sem interface/MangoHud) |
| M21 Diagnóstico | ✅ | 10 cenários, auto/ask/alert, máx. 3 tentativas |
| M8 Proton Pulse | ⛔ bloqueado | plugin não instalado (opcional pela spec) |
| M9 Fork do Panel | ⛔ bloqueado | sem upstream identificável (ver docs/desenvolvimento/FORK-PANEL-DE-CONTROL.md) |
| M10 Status/testes | ✅ parcial | /status, painel 127.0.0.1:8765, testes + relatório HTML + safe-mode após 2 falhas; **benchmark e LSFG por jogo: manuais** (exigem MangoHud/cenário fixo; LSFG é ativado pela interface do plugin) |
| M11 Versão/updates | ✅ | VERSION, migrações do banco, `x updates` semanal (detecta Decky sumido, não atualiza) |
| M12 Onboarding/aprovação | ✅ | `setup-deck.sh --all/--modules/--dev`, aprovação por ID com validade |
| M15 Install/uninstall | ✅ | por módulo, avisa dependentes, `--purge` com confirmação, backups só com `--purge-backups` |
| M16 Recuperação | ✅ | `recovery/README.md`, 17 cenários |
| M17 Privacidade/export | ✅ | `PRIVACY.md`, export sem tokens/IDs/caminhos do home |

## Fora do escopo desta entrega
- Switch 2 (Lichii) na biblioteca: o emulador é experimental e a forma de abrir um jogo pela linha de
  comando não está documentada; os dumps ficam em ~/Downloads.
- Atualização do Eden: releases oficiais bloqueadas por DMCA; não uso fontes não oficiais.
