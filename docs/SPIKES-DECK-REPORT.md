## Relatório de Spikes — Steam Deck real (2026-11-06)

Deck **LCD (Jupiter)**, SteamOS 3.9.5 (build 20261023.100), Python 3.14.6. Acesso por SSH a partir do PC.
Suíte completa no Linux real (`fcntl.flock` de verdade): **54 passed**.

### Inventário (M-1, somente leitura)
- **EmuDeck não instalado**: sem `~/.config/EmuDeck`, sem Steam ROM Manager, sem ROMs em `~/Emulation/roms`, sem BIOS.
- Emuladores: DuckStation (AppImage, `~/.local/share/duckstation/settings.ini`) e PCSX2 Flatpak v2.6.3.
  RetroArch, Dolphin, PPSSPP: ausentes.
- Decky: Panel de Control, PowerTools, decky-lsfg-vk, protondb-decky, unifideck-decky. **TabMaster ausente.**
- `shortcuts.vdf`: 506 atalhos — 500 do Unifideck (402 Epic, 99 GOG), 6 manuais.
- Ferramentas presentes: flock, sqlite3, jq, unzip, unrar, 7z, git, flatpak. Ausentes: xdelta3, flips, qbittorrent-nox
  (há o qBittorrent Flatpak 5.1.4, com interface gráfica).
- Portas: 1337 = Decky; **8080 = steamwebhelper** (depuração CEF que o Decky liga) → usar 8765 está certo
  (F13 corrigida: o conflito existe, mas é com o steamwebhelper, não com o Decky).

### S1 — Concorrência + reboot
Status: **PARCIAL** — testes de lock/crash passaram no Linux real; reboot armado (`deck/s1_reboot.py prepare`,
op `aa4c93f7b312` em `running` com escritor contínuo). Falta: reiniciar e rodar `check`.

### S2 — Backup corrompido
Status: **PASSOU** nos testes do Linux real. Aplicar em arquivos reais fica para quando houver o que restaurar.

### S3 — SRM CLI / Gaming Mode
Status: **BLOQUEADO** — SRM/EmuDeck não estão instalados.
Achado: o Unifideck escreve `shortcuts.vdf` direto e usa um **launcher fixo + mapa** ("Dynamic Launch"):
todos os atalhos apontam para `unifideck-launcher`; instalar/trocar o jogo muda só o mapa, **sem reiniciar o
Steam e sem mudar o AppID**. Proposta para o M2: o mesmo padrão para ROMs (`dc-launch <game_id>`), o que
resolve F1 (Gaming Mode) e F2 (AppID estável) de uma vez e dispensa o SRM para adicionar jogos.

### S4 — Playtime
Status: **PASSOU (leitura) — premissa da v5.1 corrigida.**
- Fórmula do AppID confirmada: `crc32(exe+nome) | 0x80000000` bate em 495/506 atalhos (os 11 restantes
  foram criados pela interface do Steam, com ID próprio).
- `localconfig.vdf` **não guarda playtime de atalhos não-Steam**: o ID aparece em `apps/<id>/BadgeData` e em
  `WebStorage/user-collections` (favoritos/coleções). Também em `config/config.vdf` (`Tools/<id>/SizeOnDisk`,
  cache de shader), `760/screenshots.vdf` (ID 64-bit), `grid/` (artes) e `compat.vdf` (Proton escolhido).
- Consequência: mudar o AppID (renomear, `.cue`→`.m3u`) **não perde horas localmente**, mas tira o jogo de
  favoritos/coleções, perde arte, versão do Proton e o vínculo das capturas. M2.6 deve proteger esses itens.

### S5 — Adaptadores
Status: **PARCIAL — 2 de 5** (só DuckStation e PCSX2 existem no Deck).
- Chaves reais: DuckStation `[GPU] ResolutionScale` (atual 5), `Renderer=Vulkan`, `WidescreenHack`;
  PCSX2 `[EmuCore/GS] upscale_multiplier` (atual 3), `Renderer=14` (Vulkan), `[EmuCore] EnableWideScreenPatches`.
- `deck/s5_real_copy.py`: 3 perfis × 2 emuladores aplicados em **cópias**; cada perfil mudou exatamente 1 linha,
  read-back OK, originais com hash intacto.
- Os valores atuais (5 e 3) foram postos à mão → o adaptador recusa sobrescrever sem `force` (M3.2).
- Pendentes: aspect ratio / frame limit / shader (valores não mapeados com segurança); RetroArch, Dolphin,
  PPSSPP (não instalados); confirmar visualmente que o emulador respeita o valor.

### S6 — Energia
Status: **PARCIAL** — no carregador: `ACAD` (Mains) online, `BAT1` 92% "Not charging", decisão RUN.
Achado: um mouse Logitech aparece como `hidpp_battery_0` (type=Battery, **scope=Device**) — agora ignorado
(teste novo). Falta: leitura com o carregador desconectado. OLED: não se aplica (usuário só tem LCD).

### Conclusão
- **Liberados:** M18+M19, M0 (backup/quarentena), M4.6 (ZIP), M3 para DuckStation/PCSX2 (só resolução/backend/widescreen).
- **Bloqueados:** M2 com SRM (não instalado — decisão de arquitetura pendente); M3 para RetroArch/Dolphin/PPSSPP; M1 TabMaster.
- **Ajustes na v5.1:** M2 via launcher fixo + mapa; M2.6 proteger coleções/artes/compat em vez de "playtime no
  localconfig"; F13 justificativa corrigida.
