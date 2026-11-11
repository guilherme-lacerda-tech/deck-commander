"""Sincronização de saves: automático ao fechar o jogo."""


def test_saves_automaticos_ao_fechar(tmp_path, monkeypatch):
    """Melhoria: jogo já sincronizado uma vez entra na fila sozinho ao fechar; aviso só se der conflito/falha."""
    from types import SimpleNamespace
    from dc import saves_sync, transferir
    from dc.paths import get_paths
    paths = get_paths(tmp_path / "dc").ensure()
    monkeypatch.setattr(transferir, "_home", lambda home=None: tmp_path)
    assert not saves_sync.pedir_ao_fechar(paths, "nds-x", "X", 600)  # nunca sincronizado: não mexe
    (saves_sync._dir(paths) / "nds-x.json").write_text("{}")
    assert not saves_sync.pedir_ao_fechar(paths, "nds-x", "X", 20)  # abriu e fechou: não vale
    assert saves_sync.pedir_ao_fechar(paths, "nds-x", "X", 600)
    assert saves_sync.pedir_ao_fechar(paths, "nds-x", "X", 600)
    fila = transferir.ler_fila()
    assert len(fila) == 1 and fila[0]["direcao"] == "saves" and fila[0]["auto"]
    sent = []
    bot = SimpleNamespace(cfg={"notify_chat": 1}, send=lambda c, t, buttons=None: sent.append(t))
    transferir.marcar(fila[0]["id"], "pronto", "Pronto: 4 save(s) iguais")
    transferir.notificar(bot)
    assert sent == []  # deu certo: silêncio
    saves_sync.pedir_ao_fechar(paths, "nds-x", "X", 600)
    e = transferir.ler_fila()[-1]
    transferir.marcar(e["id"], "pronto", "  CONFLITO: {EMU}/x.sav — escolha no bot")
    transferir.notificar(bot)
    assert len(sent) == 1 and sent[0].startswith("✅ Saves")
    (paths.config / "saves-auto-desligado").write_text("1")
    assert not saves_sync.auto_ligado(paths, "nds-x")
