"""Guardião: cópia das configurações, teste depois de atualizar e volta automática — docs/specs/guardiao.md."""
from types import SimpleNamespace

from dc import guardiao as G


class Run:
    def __init__(self):
        self.commit, self.chamadas, self.abre = "abc123\n", [], True

    def __call__(self, args, **k):
        self.chamadas.append(args)
        if args[:3] == ["flatpak", "info", "--show-commit"]:
            ok = args[3] == "org.libretro.RetroArch"
            return SimpleNamespace(returncode=0 if ok else 1, stdout=self.commit if ok else "", stderr="")
        if args[:2] == ["flatpak", "run"]:
            return SimpleNamespace(returncode=0 if self.abre else 1, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")


def _home(tmp_path):
    cfg = tmp_path / "home/.var/app/org.libretro.RetroArch/config/retroarch"
    cfg.mkdir(parents=True)
    (cfg / "retroarch.cfg").write_text('a = "1"')
    (cfg / "shaders").mkdir()
    (cfg / "shaders/grande.bin").write_bytes(b"x" * 10)
    return tmp_path / "home", cfg


def test_primeira_vez_so_copia(tmp_path):
    home, cfg = _home(tmp_path)
    g = G.Guardiao(home, tmp_path / "dados", run=Run())
    assert g.rodada() == []
    copias = list((tmp_path / "dados/RetroArch").glob("*.tar.gz"))
    assert len(copias) == 1
    import tarfile
    with tarfile.open(copias[0]) as tf:
        nomes = tf.getnames()
    assert any(n.endswith("retroarch.cfg") for n in nomes) and not any("shaders" in n for n in nomes)


def test_atualizou_e_quebrou_volta_tudo(tmp_path):
    home, cfg = _home(tmp_path)
    run = Run()
    g = G.Guardiao(home, tmp_path / "dados", run=run)
    g.espera = 0
    g.rodada()
    run.commit = "def456\n"
    (cfg / "retroarch.cfg").unlink()
    avisos = g.rodada()
    assert avisos and "quebrou" in avisos[0]
    assert (cfg / "retroarch.cfg").read_text() == 'a = "1"'
    assert any("--commit=abc123" in a for a in run.chamadas)
    assert list(cfg.parent.glob("retroarch.quebrada-*"))  # a quebrada fica guardada, nada apagado


def test_atualizou_e_passou(tmp_path):
    home, cfg = _home(tmp_path)
    run = Run()
    g = G.Guardiao(home, tmp_path / "dados", run=run)
    g.espera = 0
    g.rodada()
    run.commit = "def456\n"
    avisos = g.rodada()
    assert avisos and "passou" in avisos[0]
    assert not any("--commit=" in str(a) for a in run.chamadas)


def test_falha_passageira_nao_desfaz_nada(tmp_path):
    """Revisão 11/11/2026: uma falha única no teste restaurava cópia velha E voltava a versão do emulador."""
    home, cfg = _home(tmp_path)
    run = Run()
    g = G.Guardiao(home, tmp_path / "dados", run=run)
    g.espera = 0
    g.rodada()
    run.commit = "def456\n"
    falhas = iter([1])  # o 1º "flatpak run" falha, o 2º abre

    def run2(args, **k):
        if args[:2] == ["flatpak", "run"] and next(falhas, 0):
            run.chamadas.append(args)
            return SimpleNamespace(returncode=1, stdout="", stderr="")
        return run(args, **k)
    g.run = run2
    avisos = g.rodada()
    assert avisos and "passou" in avisos[0] and not any("--commit=" in str(a) for a in run.chamadas)


def test_restaurou_e_as_teclas_dos_botoes_voltam(tmp_path):
    """A cópia restaurada é de antes das teclas F9–F12: se o retrô estava ligado, elas são reaplicadas."""
    home, cfg = _home(tmp_path)
    run = Run()
    g = G.Guardiao(home, tmp_path / "dados", run=run)
    g.espera = 0
    g.rodada()  # cópia SEM as teclas
    (cfg / "retroarch.cfg").write_text('input_save_state = "f9"\n')  # depois o usuário ligou o retrô
    run.commit, run.abre = "def456\n", False
    g.rodada()
    assert 'input_save_state = "f9"' in (cfg / "retroarch.cfg").read_text()
