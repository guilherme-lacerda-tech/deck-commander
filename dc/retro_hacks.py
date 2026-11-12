

def definir(texto: str, valores: dict[str, str]) -> str:
    """Substitui ou adiciona linhas no formato 'chave = "valor"'."""
    linhas = texto.splitlines(keepends=True)
    if not linhas or not linhas[-1].endswith('\n'):
        linhas.append('\n')
    
    chaves_existentes = {linha.split(' = ')[0]: i for i, linha in enumerate(linhas) if ' = ' in linha}
    
    for chave, valor in valores.items():
        if chave in chaves_existentes:
            idx = chaves_existentes[chave]
            linhas[idx] = f'{chave} = "{valor}"\n'
        else:
            linhas.append(f'{chave} = "{valor}"\n')
    
    return ''.join(linhas)

def cfg_retroarch(texto: str, turbo: float = 2.0) -> str:
    """Configura retroarch.cfg com teclas de trás do Steam Deck."""
    valores = {
        "input_save_state": "f9",
        "input_load_state": "f10",
        "input_rewind": "f11",
        "input_toggle_fast_forward": "f12",  # um toque liga o turbo, outro desliga (pedido do usuário)
        "input_hold_fast_forward": "nul",
        "fastforward_ratio": f"{turbo:.6f}",
        "rewind_enable": "true",
        "rewind_granularity": "2",
        "audio_fastforward_mute": "false",
        "network_cmd_enable": "true",
        "network_cmd_port": "55355",
        "apply_cheats_after_load": "true",
        "video_font_enable": "true",  # avisos na tela: "estado salvo", "carregado", turbo
        # Revisão retrô 12/11/2026: L4 gravava sempre no MESMO espaço — um toque sem querer apagava o save bom.
        # Agora cada L4 vai para o espaço seguinte (R4 carrega o mais novo) e ficam os 10 últimos.
        "savestate_auto_index": "true",
        "savestate_max_keep": "10",
    }
    texto = definir(texto, valores)
    # a mesma tecla em outra função do RetroArch (ex.: f9 = mudo, f11 = prender o mouse) vira "nul"
    nossas = set(valores) | {k + s for k in valores for s in ("_btn", "_axis", "_mbtn")}
    linhas = texto.splitlines(keepends=True)
    for i, linha in enumerate(linhas):
        chave, _, valor = linha.partition(" = ")
        if chave.startswith("input_") and chave not in nossas and valor.strip() in ('"f9"', '"f10"', '"f11"', '"f12"'):
            linhas[i] = chave + ' = "nul"' + ("\n" if linha.endswith("\n") else "")
    return "".join(linhas)

def override_nucleo(texto: str | None, runahead: bool, rewind: bool, shader: str | None) -> str:
    """Cria ou atualiza arquivo de exceção por núcleo."""
    if texto is None:
        texto = ""
    valores = {
        "run_ahead_enabled": "true" if runahead else "false",
        "run_ahead_frames": "1",
        "run_ahead_secondary_instance": "true",
        "rewind_enable": "true" if rewind else "false"
    }
    return definir(texto, valores)

NUCLEOS = {
    "Snes9x": {"runahead": True, "rewind": True, "shader": "crt"},
    "Nestopia": {"runahead": True, "rewind": True, "shader": "crt"},
    "Genesis Plus GX": {"runahead": True, "rewind": True, "shader": "crt"},
    "Gambatte": {"runahead": True, "rewind": True, "shader": "lcd"},
    "mGBA": {"runahead": True, "rewind": True, "shader": "lcd"},
    "FinalBurn Neo": {"runahead": True, "rewind": True, "shader": "crt"},
    "Beetle PCE Fast": {"runahead": True, "rewind": True, "shader": "crt"},
    "Mupen64Plus-Next": {"runahead": False, "rewind": False, "shader": None},
    "Beetle Saturn": {"runahead": False, "rewind": False, "shader": None}
}

SHADERS = {
    # zfast-crt: feito para portáteis e escala não inteira. O crt-easymode (antes) pede escala inteira: na tela de
    # 800 linhas do Deck (SNES 224 linhas = 3,57x) as linhas de varredura saíam irregulares (revisão retrô 12/11/2026)
    "crt": "/app/share/libretro/shaders/shaders_slang/crt/zfast-crt.slangp",
    "lcd": "/app/share/libretro/shaders/shaders_slang/handheld/lcd-grid-v2.slangp"
}

def preset_shader(tipo: str) -> str:
    """Devolve conteúdo de um preset .slangp referenciando o shader."""
    if tipo not in SHADERS:
        raise KeyError(f"Shader '{tipo}' não encontrado")
    return f'#reference "{SHADERS[tipo]}"\n'

def ini_definir(texto: str, secao: str, valores: dict[str, str]) -> str:
    """Define chaves em uma seção do arquivo .ini."""
    linhas = texto.splitlines(keepends=True)
    if linhas and not linhas[-1].endswith("\n"):
        linhas[-1] += "\n"
    secao_inicial = next((i for i, l in enumerate(linhas) if l.strip() == f"[{secao}]"), -1)
    if secao_inicial < 0:  # seção nova no fim do arquivo (corrigido: antes inseria as chaves ANTES do cabeçalho)
        if linhas and linhas[-1].strip():
            linhas.append("\n")
        linhas.append(f"[{secao}]\n")
        secao_inicial = len(linhas) - 1
    # fim da seção = próxima seção; linhas em branco no fim dela ficam depois das chaves novas
    secao_final = next((i for i in range(secao_inicial + 1, len(linhas)) if linhas[i].lstrip().startswith("[")),
                       len(linhas))
    while secao_final - 1 > secao_inicial and not linhas[secao_final - 1].strip():
        secao_final -= 1

    chaves_existentes = {}
    for i in range(secao_inicial + 1, secao_final):
        if '=' in linhas[i]:
            chave = linhas[i].split('=', 1)[0].strip()
            chaves_existentes[chave] = i
    
    for chave, valor in valores.items():
        if chave in chaves_existentes:
            idx = chaves_existentes[chave]
            linhas[idx] = f'{chave} = {valor}\n'
        else:
            linhas.insert(secao_final, f'{chave} = {valor}\n')
            secao_final += 1
    
    return ''.join(linhas)

def ini_remover_tecla(texto: str, secao: str, tecla: str, manter: set[str]) -> str:
    """Remove linhas com valor igual a `tecla` exceto se chave está em `manter`."""
    linhas = texto.splitlines(keepends=True)
    if not linhas or not linhas[-1].endswith('\n'):
        linhas.append('\n')
    
    secao_inicial = -1
    secao_final = len(linhas)
    
    for i, linha in enumerate(linhas):
        if linha.startswith(f'[{secao}]'):
            secao_inicial = i
        elif secao_inicial >= 0 and linha.strip() == '' and i > secao_inicial:
            secao_final = i
            break
        elif secao_inicial >= 0 and linha.startswith('[') and i > secao_inicial:
            secao_final = i
            break
    
    if secao_inicial < 0:
        return texto
    
    i = secao_inicial + 1
    while i < secao_final:
        linha = linhas[i]
        if '=' in linha:
            chave, valor = linha.split('=', 1)
            chave = chave.strip()
            valor = valor.strip()
            if valor == tecla and chave not in manter:
                del linhas[i]
                secao_final -= 1
                continue
        i += 1
    
    return ''.join(linhas)

def ini_duckstation(texto: str, turbo: float = 2.0) -> str:
    """Configura DuckStation.ini com teclas de trás do Steam Deck."""
    hotkeys = {
        "SaveSelectedSaveState": "Keyboard/F9",
        "LoadSelectedSaveState": "Keyboard/F10",
        "Rewind": "Keyboard/F11",
        "ToggleFastForward": "Keyboard/F12"  # liga/desliga com um toque
    }
    
    main = {
        "RewindEnable": "true",  # leve: 2 cópias por segundo, 10 s para trás (a lentidão de 11/11 era a camada WSI)
        "RewindFrequency": "0.500000",
        "RewindSaveSlots": "20",
        "FastForwardSpeed": f"{turbo:.6f}",
        "CreateSaveStateBackups": "true",  # o save anterior do espaço vira .bak (toque sem querer no L4 não apaga)
    }
    
    texto = ini_definir(texto, "Hotkeys", hotkeys)
    texto = ini_definir(texto, "Main", main)
    # avisos na tela ("estado salvo no espaço 1", ícone de turbo) — pedido do usuário: saber que funcionou
    # e a velocidade no canto ("100%"; com turbo "200%"): mostra na hora se o turbo e o jogo estão na velocidade certa
    texto = ini_definir(texto, "Display", {"ShowOSDMessages": "true", "ShowStatusIndicators": "true", "ShowSpeed": "true"})
    # pula a abertura do PlayStation (logo do console): o turbo não acelera essa parte nem os vídeos lidos do disco
    texto = ini_definir(texto, "BIOS", {"PatchFastBoot": "true"})

    manter = set(hotkeys.keys())
    texto = ini_remover_tecla(texto, "Hotkeys", "Keyboard/F9", manter)
    texto = ini_remover_tecla(texto, "Hotkeys", "Keyboard/F10", manter)
    texto = ini_remover_tecla(texto, "Hotkeys", "Keyboard/F11", manter)
    texto = ini_remover_tecla(texto, "Hotkeys", "Keyboard/F12", manter)
    
    return texto

def ini_pcsx2(texto: str, turbo: float = 2.0) -> str:
    """Configura PCSX2.ini com teclas de trás do Steam Deck."""
    hotkeys = {
        "SaveStateToSlot": "Keyboard/F9",
        "LoadStateFromSlot": "Keyboard/F10",
        "ToggleTurbo": "Keyboard/F12"  # liga/desliga com um toque
    }
    
    framerate = {
        "TurboScalar": f"{turbo:.6f}"
    }
    
    texto = ini_definir(texto, "Hotkeys", hotkeys)
    texto = ini_definir(texto, "Framerate", framerate)
    texto = ini_definir(texto, "EmuCore/GS", {"OsdShowMessages": "true", "OsdShowIndicators": "true", "OsdShowSpeed": "true"})  # avisos na tela

    manter = set(hotkeys.keys())
    for f in ("F9", "F10", "F11", "F12"):  # F9 era "renderização por software" no PCSX2
        texto = ini_remover_tecla(texto, "Hotkeys", "Keyboard/" + f, manter)
    
    return texto

def hotkeys_dolphin(texto: str | None) -> str:
    """Configura Hotkeys.ini do Dolphin com teclas de trás."""
    if texto is None or "[Hotkeys]" not in texto:
        texto = "[Hotkeys]\nDevice = XInput2/0/Virtual core pointer\n\n"
    
    valores = {
        "Save State/Save to Selected Slot": "`F9`",
        "Load State/Load from Selected Slot": "`F10`",
        "Emulation Speed/Disable Emulation Speed Limit": "`F12`"
    }
    
    return ini_definir(texto, "Hotkeys", valores)

BOTOES_DE_TRAS = {
    "button_back_left_upper": ["key_press F9, Salvar estado"],
    "button_back_right_upper": ["key_press F10, Carregar estado"],
    "button_back_left": ["key_press F11, Voltar no tempo"],
    "button_back_right": ["key_press F12, Turbo liga-desliga"],
}


def _bloco_bindings(linhas: list[str], botao: str) -> tuple[int, int, str] | None:
    """(linha do "{" do bindings, linha do "}" que fecha, indentação) do 1º Full_Press do botão; None se não há."""
    ini = next((n for n, l in enumerate(linhas) if l.strip() == f'"{botao}"'), None)
    if ini is None:
        return None
    fp = next((n for n in range(ini + 1, len(linhas)) if linhas[n].strip() == '"Full_Press"'), None)
    if fp is None:
        return None
    b = next((n for n in range(fp + 1, len(linhas)) if linhas[n].strip() == '"bindings"'), None)
    if b is None or b + 1 >= len(linhas) or linhas[b + 1].strip() != "{":
        return None
    prof = 0
    for n in range(b + 1, len(linhas)):  # acha o "}" que fecha este bloco, contando as chaves
        prof += linhas[n].count("{") - linhas[n].count("}")
        if prof == 0:
            return b + 1, n, linhas[b + 1][: len(linhas[b + 1]) - len(linhas[b + 1].lstrip())]
    return None


def layout_com_botoes_de_tras(texto: str) -> str:
    """Layout do Steam Input com os botões de trás ligados às teclas reservadas (o resto do layout fica igual)."""
    linhas = texto.splitlines(keepends=True)
    for botao, binds in BOTOES_DE_TRAS.items():
        pos = _bloco_bindings(linhas, botao)
        if pos is None:
            continue
        abre, fecha, ind = pos
        linhas[abre + 1:fecha] = [ind + '\t"binding"\t\t"' + b + '"\n' for b in binds]
    return "".join(linhas)


def tem_botoes_de_tras(texto: str) -> bool:
    """True se os 4 botões de trás já estão ligados às teclas certas."""
    linhas = texto.splitlines(keepends=True)
    for botao, binds in BOTOES_DE_TRAS.items():
        pos = _bloco_bindings(linhas, botao)
        if pos is None:
            return False
        dentro = "".join(linhas[pos[0] + 1:pos[1]])
        if any(f'"{b}"' not in dentro for b in binds):
            return False
    return True
