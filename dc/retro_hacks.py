from typing import Dict, List, Optional, Set, Tuple, Union

TECLAS = {"salvar": "F13", "carregar": "F14", "voltar": "F15", "turbo": "F16"}

def definir(texto: str, valores: Dict[str, str]) -> str:
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
        "input_save_state": "f13",
        "input_load_state": "f14",
        "input_rewind": "f15",
        "input_hold_fast_forward": "add",
        "fastforward_ratio": f"{turbo:.6f}",
        "rewind_enable": "true",
        "rewind_granularity": "2",
        "audio_fastforward_mute": "false",
        "network_cmd_enable": "true",
        "network_cmd_port": "55355",
        "apply_cheats_after_load": "true"
    }
    return definir(texto, valores)

def override_nucleo(texto: Optional[str], runahead: bool, rewind: bool, shader: Optional[str]) -> str:
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
    "crt": "/app/share/libretro/shaders/shaders_slang/crt/crt-easymode.slangp",
    "lcd": "/app/share/libretro/shaders/shaders_slang/handheld/lcd-grid-v2.slangp"
}

def preset_shader(tipo: str) -> str:
    """Devolve conteúdo de um preset .slangp referenciando o shader."""
    if tipo not in SHADERS:
        raise KeyError(f"Shader '{tipo}' não encontrado")
    return f'#reference "{SHADERS[tipo]}"\n'

def ini_definir(texto: str, secao: str, valores: Dict[str, str]) -> str:
    """Define chaves em uma seção do arquivo .ini."""
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
        linhas.append(f'\n[{secao}]\n')
        secao_inicial = len(linhas) - 1
    
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

def ini_remover_tecla(texto: str, secao: str, tecla: str, manter: Set[str]) -> str:
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
        "SaveSelectedSaveState": "Keyboard/F13",
        "LoadSelectedSaveState": "Keyboard/F14",
        "Rewind": "Keyboard/F15",
        "FastForward": "Keyboard/F16"
    }
    
    main = {
        "RewindEnable": "false",  # ligado deixou o Castlevania MUITO travado no Deck (salvava 10x por segundo)
        "RewindFrequency": "0.100000",
        "RewindSaveSlots": "100",
        "FastForwardSpeed": f"{turbo:.6f}"
    }
    
    texto = ini_definir(texto, "Hotkeys", hotkeys)
    texto = ini_definir(texto, "Main", main)
    
    manter = set(hotkeys.keys())
    texto = ini_remover_tecla(texto, "Hotkeys", "Keyboard/F13", manter)
    texto = ini_remover_tecla(texto, "Hotkeys", "Keyboard/F14", manter)
    texto = ini_remover_tecla(texto, "Hotkeys", "Keyboard/F15", manter)
    texto = ini_remover_tecla(texto, "Hotkeys", "Keyboard/F16", manter)
    
    return texto

def ini_pcsx2(texto: str, turbo: float = 2.0) -> str:
    """Configura PCSX2.ini com teclas de trás do Steam Deck."""
    hotkeys = {
        "SaveStateToSlot": "Keyboard/F13",
        "LoadStateFromSlot": "Keyboard/F14",
        "HoldTurbo": "Keyboard/F16"
    }
    
    framerate = {
        "TurboScalar": f"{turbo:.6f}"
    }
    
    texto = ini_definir(texto, "Hotkeys", hotkeys)
    texto = ini_definir(texto, "Framerate", framerate)
    
    manter = set(hotkeys.keys())
    texto = ini_remover_tecla(texto, "Hotkeys", "Keyboard/F13", manter)
    texto = ini_remover_tecla(texto, "Hotkeys", "Keyboard/F14", manter)
    texto = ini_remover_tecla(texto, "Hotkeys", "Keyboard/F16", manter)
    
    return texto

def hotkeys_dolphin(texto: Optional[str]) -> str:
    """Configura Hotkeys.ini do Dolphin com teclas de trás."""
    if texto is None or "[Hotkeys]" not in texto:
        texto = "[Hotkeys]\nDevice = XInput2/0/Virtual core pointer\n\n"
    
    valores = {
        "Save State/Save to Selected Slot": "`F13`",
        "Load State/Load from Selected Slot": "`F14`",
        "Emulation Speed/Disable Emulation Speed Limit": "`F16`"
    }
    
    return ini_definir(texto, "Hotkeys", valores)

BOTOES_DE_TRAS = {
    "button_back_left": ["key_press F13, Salvar estado"],
    "button_back_right": ["key_press F14, Carregar estado"],
    "button_back_left_upper": ["key_press F15, Voltar no tempo"],
    "button_back_right_upper": ["key_press F16, Turbo", "key_press KEYPAD_PLUS, Turbo"],
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
