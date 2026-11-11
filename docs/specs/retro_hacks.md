Arquivo: dc/retro_hacks.py — funções PURAS (texto entra, texto sai) que configuram os emuladores para os botões de
trás do Steam Deck. Nada de ler/gravar disco nestas funções (outra parte do programa faz isso). Python 3.11, só
biblioteca padrão, type hints, docstrings curtas em português.

Teclas reservadas (os botões de trás do Deck viram estas teclas pelo Steam Input):
  L4 = F13 (salvar estado), R4 = F14 (carregar estado), L5 = F15 (voltar no tempo, segurar),
  R5 = F16 e também KEYPAD_PLUS (turbo, segurar).

Constante:
  TECLAS = {"salvar": "F13", "carregar": "F14", "voltar": "F15", "turbo": "F16"}

1) def cfg_retroarch(texto: str, turbo: float = 2.0) -> str
   Formato do retroarch.cfg: uma linha por chave, `chave = "valor"` (valor SEMPRE entre aspas duplas).
   Troca o valor se a chave existe (mantendo a posição da linha), senão acrescenta no fim. Não mexe nas outras linhas.
   Chaves a definir:
     input_save_state = "f13"
     input_load_state = "f14"
     input_rewind = "f15"
     input_hold_fast_forward = "add"        (tecla + do teclado numérico; o RetroArch não conhece f16)
     fastforward_ratio = "<turbo com 6 casas, ex. 2.000000>"
     rewind_enable = "true"
     rewind_granularity = "2"
     audio_fastforward_mute = "false"
     network_cmd_enable = "true"
     network_cmd_port = "55355"
     apply_cheats_after_load = "true"
   Se o texto não termina com "\n", garante uma quebra antes de acrescentar.
   Função auxiliar pública: def definir(texto: str, valores: dict[str, str]) -> str  (faz o trabalho acima para
   qualquer dicionário; os valores entram entre aspas).

2) def override_nucleo(texto: str | None, runahead: bool, rewind: bool, shader: str | None) -> str
   Arquivo de exceção por núcleo do RetroArch (mesmo formato do retroarch.cfg). Usa definir() sobre texto ou "".
   Define: run_ahead_enabled = "true"/"false", run_ahead_frames = "1", run_ahead_secondary_instance = "true",
   rewind_enable = "true"/"false". (o parâmetro shader é ignorado aqui; existe para o futuro)

3) NUCLEOS: dict[str, dict] — nome da pasta do núcleo no RetroArch → opções:
     "Snes9x": runahead True, rewind True, shader "crt"
     "Nestopia": runahead True, rewind True, shader "crt"
     "Genesis Plus GX": runahead True, rewind True, shader "crt"
     "Gambatte": runahead True, rewind True, shader "lcd"
     "mGBA": runahead True, rewind True, shader "lcd"
     "FinalBurn Neo": runahead True, rewind True, shader "crt"
     "Beetle PCE Fast": runahead True, rewind True, shader "crt"
     "Mupen64Plus-Next": runahead False, rewind False, shader None
     "Beetle Saturn": runahead False, rewind False, shader None
   Cada valor: {"runahead": bool, "rewind": bool, "shader": str | None}

4) SHADERS = {"crt": "/app/share/libretro/shaders/shaders_slang/crt/crt-easymode.slangp",
              "lcd": "/app/share/libretro/shaders/shaders_slang/handheld/lcd-grid-v2.slangp"}
   def preset_shader(tipo: str) -> str
   Devolve o conteúdo de um preset .slangp que só referencia o shader:  '#reference "<caminho>"\n'
   KeyError se o tipo não existir.

5) INI no estilo Qt (DuckStation, PCSX2): seções `[Nome]`, linhas `Chave = Valor` (sem aspas).
   def ini_definir(texto: str, secao: str, valores: dict[str, str]) -> str
   - Se a seção existe: troca as chaves existentes nela (mantendo a posição) e acrescenta as que faltam no fim
     DAQUELA seção (antes da próxima seção; se houver linhas em branco no fim da seção, insere antes delas).
   - Se não existe: acrescenta no fim do texto "\n[secao]\n" + linhas.
   - Não altera nada fora da seção. Comparação de chave exata (sensível a maiúsculas).
   def ini_remover_tecla(texto: str, secao: str, tecla: str, manter: set[str]) -> str
   - Dentro da seção, remove linhas cujo valor seja exatamente `tecla` (ex.: "Keyboard/F13") e cuja chave NÃO
     esteja em `manter` (evita a mesma tecla em duas ações).

6) def ini_duckstation(texto: str, turbo: float = 2.0) -> str
   [Hotkeys]: SaveSelectedSaveState = Keyboard/F13, LoadSelectedSaveState = Keyboard/F14, Rewind = Keyboard/F15,
              FastForward = Keyboard/F16
   [Main]: RewindEnable = false (ligado travou o jogo no Deck), RewindFrequency = 0.100000, RewindSaveSlots = 100,
           FastForwardSpeed = <turbo com 6 casas>
   Depois remove de [Hotkeys] outras ações que usem as mesmas teclas (ini_remover_tecla com manter = as 4 acima).

7) def ini_pcsx2(texto: str, turbo: float = 2.0) -> str
   [Hotkeys]: SaveStateToSlot = Keyboard/F13, LoadStateFromSlot = Keyboard/F14, HoldTurbo = Keyboard/F16
   [Framerate]: TurboScalar = <turbo com 6 casas>
   Mesma limpeza de teclas repetidas.

8) def hotkeys_dolphin(texto: str | None) -> str
   Arquivo Hotkeys.ini do Dolphin. Seção [Hotkeys]. Se texto é None ou não tem a seção, cria:
     [Hotkeys]
     Device = XInput2/0/Virtual core pointer
   Define (ini_definir; os valores levam crases):
     Save State/Save to Selected Slot = `F13`
     Load State/Load from Selected Slot = `F14`
     Emulation Speed/Disable Emulation Speed Limit = `F16`

9) Steam Input (layout do Steam para cada jogo). Formato VDF texto: blocos `"nome" { ... }`, pares
   `"chave"\t\t"valor"`. Os botões de trás aparecem assim (bindings vazio ou com linhas "binding"):
       "button_back_left"
       {
           "activators"
           {
               "Full_Press"
               {
                   "bindings"
                   {
                   }
               }
           }
       }
   def layout_com_botoes_de_tras(texto: str) -> str
   Para cada um dos 4 nomes abaixo, troca TODO o conteúdo do bloco "bindings" do PRIMEIRO "Full_Press" daquele
   botão pelas linhas indicadas (preservando a indentação do bloco; use tabs):
     button_back_left        -> "binding"		"key_press F13, Salvar estado"
     button_back_right       -> "binding"		"key_press F14, Carregar estado"
     button_back_left_upper  -> "binding"		"key_press F15, Voltar no tempo"
     button_back_right_upper -> "binding"		"key_press F16, Turbo"  E  "binding"		"key_press KEYPAD_PLUS, Turbo"
   Se um botão não existir no texto, deixa como está. Use um parser simples por chaves {} (não regex gulosa que
   atravesse blocos). Deve funcionar com o arquivo inteiro de ~800 linhas.
   def tem_botoes_de_tras(texto: str) -> bool : True se os 4 botões já têm a tecla certa.

Exemplo de teste (o arquivo precisa passar):
   t = 'a = "1"\nfastforward_ratio = "0.000000"\n'
   r = cfg_retroarch(t)
   assert 'fastforward_ratio = "2.000000"' in r and r.startswith('a = "1"\n') and 'input_save_state = "f13"' in r
   i = "[Hotkeys]\nFastForward = Keyboard/Tab\nScreenshot = Keyboard/F16\n\n[Main]\nX = 1\n"
   d = ini_duckstation(i)
   assert "FastForward = Keyboard/F16" in d and "Screenshot" not in d and "X = 1" in d and "RewindEnable = false" in d
