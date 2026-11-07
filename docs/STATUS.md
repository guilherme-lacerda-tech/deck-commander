# Estado do projeto (v0.4.0)

Validado num Steam Deck LCD (SteamOS 3.9.5). 113 testes automatizados (CI no GitHub + timer semanal no Deck).

| Módulo (spec v5.1) | Estado | Observação |
|---|---|---|
| M-1 Inventário | ✅ | procedência `unknown` sem chute; inclui cartão SD; BIOS detectadas por tamanho |
| M0 Segurança | ✅ | backup verificado com fallback, quarentena, restore que fecha/reabre o Steam, safe-mode ≠ uninstall |
| M18+M19 Operation Store | ✅ | lock com reentrância segura (validado com reboot real), aprovação 1 h, `db verify` |
| M27 Contratos | ✅ | 21 contratos, validação no CI |
| M1 Plugins | ✅ parcial | dono por função documentado, `plugins.lock`; instalar plugins do Decky é manual (não há CLI oficial) |
| M2 Biblioteca | ✅ | lançador fixo + mapa, plugin ao vivo, autocorreção que respeita remoção, coleções/abas por console e por loja, capas, duplicatas (antes de baixar, no /sync e /duplicados + /remover) |
| M3 Qualidade | ✅ parcial | 10 consoles; perfis com read-back; respeita ajuste manual; **resolução por jogo** (/qualidade); verificação de controles. Shader/aspect ratio por emulador e mapeamento automático do Dolphin ainda não |
| M4 Telegram/torrent | ✅ | console por texto, .torrent/magnet, /sync automático com nova tentativa, .zip/.7z/.rar seguros, multidisco, energia com histerese |
| M5 Traduções | ✅ parcial | IPS/BPS/UPS nativos com CRC; XDelta e instaladores .exe são detectados e recusados |
| M6 Saves | ✅ | 4 tipos, backup diário, import que nunca sobrescreve em conflito |
| M7 Disco | ✅ | top 10 + sugestões (nunca apaga) |
| M20/M21 | ✅ | sensores com estado próprio; diagnóstico auto/ask/alert com limite de 3 tentativas |
| M10 Status/testes | ✅ parcial | /status, painel local, testes semanais + relatório HTML. Benchmark (exige MangoHud e cenário fixo) e E2E automatizado: pendentes |
| M11/M12/M15/M16/M17 | ✅ | versão, updates (só avisa), instalador por módulo, uninstall com confirmação, recuperação, export sem segredos |
| M8 Proton Pulse | ⛔ | plugin opcional não instalado no Deck de teste |
| M9 Fork do Panel | ⛔ | depende do repositório oficial do Panel de Control |

## Limitações conhecidas
- **Primeira instalação** do plugin e do TabMaster exige um reinício (o Decky só carrega plugins ao ligar).
  Depois disso, jogos novos aparecem sem reiniciar.
- **Switch 2** é experimental (Lichii, dumps extraídos `base/exefs/main`); o download automático de Switch 2 não é organizado sozinho.
- **Unifideck** grava `shortcuts.vdf` diretamente; se ele regravar o arquivo enquanto o Steam tiver
  atalhos ainda não salvos, a autocorreção do plugin recria os do Deck Commander.
- Testado só no modelo LCD. O OLED usa a mesma lógica de energia (por tipo, não por nome), mas não foi validado em hardware.

## Próximos passos sugeridos
1. Publicar o plugin na loja do Decky (evita o modo desenvolvedor).
2. Benchmark reproduzível com MangoHud (M10.2) e E2E com jogos homebrew (M10.4).
3. XDelta (empacotar `xdelta3` estático) e mapeamento de shader/aspect ratio por emulador.
