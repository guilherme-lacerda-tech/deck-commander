"""Teste real 28/11/2026: 'Próxima' demorava porque nuvem/guardião/protetor/avisos rodavam no mesmo laço que lê o
Telegram. Agora a manutenção roda numa thread e as tarefas longas não seguram a trava do bot."""
import threading

from dc import bot
from dc.paths import get_paths


def test_tarefa_longa_da_manutencao_nao_bloqueia_os_botoes(tmp_path, monkeypatch):
    b = bot.Bot(get_paths(tmp_path).ensure(), "TOK")
    entrou, libera = threading.Event(), threading.Event()

    def protetor_lento():
        entrou.set()
        libera.wait(5)
        return "ok"
    from dc import protetor
    monkeypatch.setattr(protetor, "montar", protetor_lento)
    th = threading.Thread(target=b._manutencao_longa, daemon=True)
    th.start()
    try:
        assert entrou.wait(3)
        assert b.trava.acquire(timeout=0.5), "a tarefa longa segurou a trava do bot"
        b.trava.release()
    finally:
        libera.set()
        th.join(5)


def test_laco_do_telegram_nao_roda_manutencao(tmp_path):
    import inspect
    fonte = inspect.getsource(bot.Bot.run)
    for passo in ("nuvem", "guardiao", "protetor", "notify_performance", "avisar_presenca"):
        assert passo not in fonte, passo
    assert "_laco_manutencao" in fonte
