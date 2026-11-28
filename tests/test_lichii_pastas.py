"""Lichii build 410 (28/11/2026): pastas eden -> lichii; backups e transferência continuam achando config e saves."""
from dc import lichii, nuvem


def test_instalacao_nova_so_com_lichii(tmp_path):
    (tmp_path / ".config/lichii").mkdir(parents=True)
    (tmp_path / ".local/share/lichii/nand/user/save").mkdir(parents=True)
    c, d = lichii.pastas(tmp_path)
    assert c.name == "lichii" and d.name == "lichii"
    assert lichii.saves(tmp_path) == tmp_path / ".local/share/lichii/nand/user/save"


def test_instalacao_antiga_so_com_eden(tmp_path):
    (tmp_path / ".local/share/eden/nand/user/save").mkdir(parents=True)
    assert lichii.pastas(tmp_path)[1].name == "eden"


def test_nuvem_inclui_saves_do_switch_e_do_port_do_bananza(tmp_path):
    """Falta achada em 28/11/2026: nenhum save de Switch nem do port nativo ia para a nuvem."""
    assert not any(n.startswith(("Lichii", "Ports")) for n, _ in nuvem.pastas(tmp_path))
    (tmp_path / ".local/share/lichii/nand/user/save").mkdir(parents=True)
    (tmp_path / "Games/DKB-Recomp/game/profile").mkdir(parents=True)
    extras = dict(nuvem.pastas(tmp_path))
    assert extras["Lichii/save"].replace("\\", "/") == ".local/share/lichii/nand/user/save"
    assert extras["Ports/DKB-Recomp-profile"].replace("\\", "/") == "Games/DKB-Recomp/game/profile"


def test_trava_presa_do_bisync_vence_sozinha(tmp_path):
    """28/11/2026: um .lck de sincronização interrompida travou o backup do PCSX2/sstates por horas."""
    import inspect
    assert '"--max-lock", "30m"' in inspect.getsource(nuvem)
