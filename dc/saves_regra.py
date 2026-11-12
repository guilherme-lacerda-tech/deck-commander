

def decidir(deck: dict[str, dict], pc: dict[str, dict], ultimo: dict[str, str]) -> list[dict]:
    """
    Decide a sincronização de saves entre Steam Deck e PC com base em SHA256 e mtime.
    
    Args:
        deck: Dicionário de destinos no Deck com {sha256, mtime}.
        pc: Dicionário de destinos no PC com {sha256, mtime}.
        ultimo: Dicionário de destinos com o SHA256 que ambos tinham na última sincronização.
        
    Returns:
        Lista de ações a serem tomadas, cada uma com destino, ação e motivo.
    """
    acoes = []
    
    todos_destinos = set(deck.keys()) | set(pc.keys())
    
    for destino in todos_destinos:
        deck_info = deck.get(destino)
        pc_info = pc.get(destino)
        
        # Se só existe no Deck
        if deck_info and not pc_info:
            acoes.append({"destino": destino, "acao": "deck->pc", "motivo": "novo no Deck"})
        # Se só existe no PC
        elif pc_info and not deck_info:
            acoes.append({"destino": destino, "acao": "pc->deck", "motivo": "novo no PC"})
        # Se existe nos dois
        elif deck_info and pc_info:
            sha_deck = deck_info["sha256"]
            sha_pc = pc_info["sha256"]
            
            # Se são iguais, nada a fazer
            if sha_deck == sha_pc:
                continue
            
            # Se não há informação de última sincronização
            if destino not in ultimo:
                mtime_deck = deck_info["mtime"]
                mtime_pc = pc_info["mtime"]
                diff = abs(mtime_deck - mtime_pc)
                
                if diff < 120:
                    acoes.append({"destino": destino, "acao": "conflito", "motivo": "datas muito próximas"})
                elif mtime_deck > mtime_pc:
                    acoes.append({"destino": destino, "acao": "deck->pc", "motivo": "mais novo no Deck"})
                else:
                    acoes.append({"destino": destino, "acao": "pc->deck", "motivo": "mais novo no PC"})
            # Se há informação de última sincronização
            else:
                sha_ultimo = ultimo[destino]
                
                # Se só o Deck mudou
                if sha_deck != sha_ultimo and sha_pc == sha_ultimo:
                    acoes.append({"destino": destino, "acao": "deck->pc", "motivo": "jogado no Deck"})
                # Se só o PC mudou
                elif sha_pc != sha_ultimo and sha_deck == sha_ultimo:
                    acoes.append({"destino": destino, "acao": "pc->deck", "motivo": "jogado no PC"})
                # Se ambos mudaram
                else:
                    acoes.append({"destino": destino, "acao": "conflito", "motivo": "jogado nos dois desde a última vez"})
        # Se o destino foi removido de um lado e existe no outro
        else:
            # Verificamos se o destino estava em `ultimo` e foi removido de um dos lados
            if destino in ultimo:
                # Se foi removido do Deck, mas ainda está no PC
                if not deck_info and pc_info:
                    acoes.append({"destino": destino, "acao": "pc->deck", "motivo": "sumiu de um lado; mantido"})
                # Se foi removido do PC, mas ainda está no Deck
                elif not pc_info and deck_info:
                    acoes.append({"destino": destino, "acao": "deck->pc", "motivo": "sumiu de um lado; mantido"})
    
    return acoes


def novo_ultimo(deck_final: dict[str, dict], pc_final: dict[str, dict]) -> dict[str, str]:
    """
    Gera o dicionário de SHA256 para destinos onde ambos os lados têm o mesmo valor após cópias.
    
    Args:
        deck_final: Dicionário final de destinos no Deck.
        pc_final: Dicionário final de destinos no PC.
        
    Returns:
        Dicionário com destino -> sha256 quando iguais nos dois lados.
    """
    ultimo = {}
    
    todos_destinos = set(deck_final.keys()) & set(pc_final.keys())
    
    for destino in todos_destinos:
        if deck_final[destino]["sha256"] == pc_final[destino]["sha256"]:
            ultimo[destino] = deck_final[destino]["sha256"]
            
    return ultimo


def resumo(acoes: list[dict]) -> str:
    """
    Gera um resumo em português das ações a serem tomadas.
    
    Args:
        acoes: Lista de ações geradas por `decidir`.
        
    Returns:
        Frase descritiva do resumo.
    """
    if not acoes:
        return "Saves iguais nos dois lados."
    
    deck_para_pc = sum(1 for a in acoes if a["acao"] == "deck->pc")
    pc_para_deck = sum(1 for a in acoes if a["acao"] == "pc->deck")
    conflitos = sum(1 for a in acoes if a["acao"] == "conflito")
    
    partes = []
    
    if deck_para_pc:
        partes.append(f"{deck_para_pc} save{'s' if deck_para_pc > 1 else ''} vão para o PC")
    if pc_para_deck:
        partes.append(f"{pc_para_deck} vem para o Deck")
    if conflitos:
        partes.append(f"{conflitos} conflito{'s' if conflitos > 1 else ''} (você escolhe)")
    
    return ", ".join(partes) + "." if partes else "Saves iguais nos dois lados."
