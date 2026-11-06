"""S5 — adaptadores: escreve, lê de volta, preserva o resto, respeita override manual.
Fixtures com as linhas reais do Deck do usuário (2026-11-06), sem dados pessoais.
No Deck, deck/s5_real_copy.py repete o teste numa CÓPIA do arquivo real."""
import pytest

from dc.adapters import ManualOverride, SchemaChanged, get_adapter

DS = """[Main]\r\nSettingsVersion = 3\r\n\r\n[GPU]\r\nRenderer = Vulkan\r\nResolutionScale = 5\r\nWidescreenHack = false\r\n\r\n[Display]\r\nAspectRatio = Auto (Game Native)\r\n"""
PS = """[EmuCore]\nEnableWideScreenPatches = false\n\n[EmuCore/GS]\nRenderer = 14\nupscale_multiplier = 3\nAspectRatio = Auto 4:3/3:2\n"""


@pytest.fixture
def files(tmp_path):
    a = tmp_path / "settings.ini"; a.write_bytes(DS.encode())
    b = tmp_path / "PCSX2.ini"; b.write_bytes(PS.encode())
    return {"duckstation": (a, "ps1"), "pcsx2": (b, "ps2"), "state": tmp_path / "state.json"}


@pytest.mark.parametrize("emu", ["duckstation", "pcsx2"])
@pytest.mark.parametrize("profile", ["economico", "equilibrado", "desempenho"])
def test_profiles_write_and_read_back(files, emu, profile):
    path, console = files[emu]
    before = path.read_bytes().splitlines(keepends=True)
    ad = get_adapter(emu)
    if ad.plan(path, console, profile):
        with pytest.raises(ManualOverride):  # valor atual foi posto à mão
            ad.apply(path, console, profile, files["state"], dry_run=False)
    ad.apply(path, console, profile, files["state"], force=True, dry_run=False)
    ad.read_back(path, console, profile)
    after = path.read_bytes().splitlines(keepends=True)
    assert len(before) == len(after)
    changed = [i for i, (x, y) in enumerate(zip(before, after)) if x != y]
    assert all(b"Scale" in after[i] or b"multiplier" in after[i] for i in changed)
    assert all(after[i].endswith(before[i][len(before[i].rstrip(b"\r\n")):]) for i in changed)  # EOL igual


def test_after_dc_owns_value_no_force_needed(files):
    path, console = files["duckstation"]
    ad = get_adapter("duckstation")
    ad.apply(path, console, "equilibrado", files["state"], force=True, dry_run=False)
    ad.apply(path, console, "desempenho", files["state"], dry_run=False)  # DC já é dono
    assert b"ResolutionScale = 6" in path.read_bytes()


def test_user_edit_after_dc_is_respected(files):
    path, console = files["duckstation"]
    ad = get_adapter("duckstation")
    ad.apply(path, console, "equilibrado", files["state"], force=True, dry_run=False)
    path.write_bytes(path.read_bytes().replace(b"ResolutionScale = 4", b"ResolutionScale = 8"))
    with pytest.raises(ManualOverride):
        ad.apply(path, console, "desempenho", files["state"], dry_run=False)


def test_schema_change_blocks(files):
    path, console = files["pcsx2"]
    path.write_bytes(path.read_bytes().replace(b"upscale_multiplier", b"UpscaleMultiplier"))
    with pytest.raises(SchemaChanged):
        get_adapter("pcsx2").plan(path, console, "equilibrado")


def test_dry_run_does_not_write(files):
    path, console = files["pcsx2"]
    raw = path.read_bytes()
    ch = get_adapter("pcsx2").apply(path, console, "economico", files["state"], force=True)
    assert ch and path.read_bytes() == raw
