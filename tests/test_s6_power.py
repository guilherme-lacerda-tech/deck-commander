"""S6 (parte simulável) — descoberta dinâmica + histerese + unknown != carregando.
Os nomes de pasta são variados de propósito: a lógica não pode depender de AC/ ou BAT0/.
A validação com o sysfs REAL (LCD e OLED) fica para o Deck (deck/DECK-PROMPT.md)."""
import pytest

from dc.power import PowerPolicy, read_power


def fake_sysfs(root, supplies):
    for name, files in supplies.items():
        d = root / name; d.mkdir(parents=True)
        for k, v in files.items():
            (d / k).write_text(f"{v}\n")
    return root


@pytest.mark.parametrize("layout", [
    {"ACAD": {"type": "Mains", "online": 1}, "BAT1": {"type": "Battery", "capacity": 80, "status": "Charging"}},
    {"ADP1": {"type": "Mains", "online": 1}, "BAT0": {"type": "Battery", "capacity": 80, "status": "Charging"},
     "ucsi-source-psy-USBC000-001": {"type": "USB", "online": 0}},
])
def test_discovers_any_layout(tmp_path, layout):
    r = read_power(fake_sysfs(tmp_path / "ps", layout))
    assert r.ac_online is True and r.battery_pct == 80


def test_usb_c_only_charger(tmp_path):
    r = read_power(fake_sysfs(tmp_path / "ps", {
        "ACAD": {"type": "Mains", "online": 0}, "usbc": {"type": "USB", "online": 1},
        "BAT1": {"type": "Battery", "capacity": 50, "status": "Charging"}}))
    assert r.ac_online is True


def test_missing_sysfs_is_unknown(tmp_path):
    r = read_power(tmp_path / "nada")
    assert r.ac_online is None and r.battery_pct is None
    p = PowerPolicy(state="RUN")
    st, why, changed = p.update(r)
    assert st == "RUN" and not changed and "unknown" in why  # não chuta


class T:
    def __init__(self): self.t = 0.0
    def __call__(self): return self.t


def reading(ac, pct, status="Charging"):
    from dc.power import PowerReading
    return PowerReading(ac, pct, status)


def test_debounce_prevents_flapping():
    clk = T(); p = PowerPolicy(debounce_s=60, clock=clk, state="RUN")
    for i in range(10):  # cabo com mau contato: alterna a cada 5s
        clk.t += 5
        st, _, changed = p.update(reading(i % 2 == 0, 80, "Discharging" if i % 2 else "Charging"))
        assert st == "RUN" and not changed
    for _ in range(13):  # desconectado de verdade por >60s
        clk.t += 5; st, why, changed = p.update(reading(False, 80, "Discharging"))
    assert st == "PAUSE"


def test_battery_hysteresis():
    clk = T(); p = PowerPolicy(min_battery_pct=30, hysteresis_pct=5, allow_on_battery=True,
                               debounce_s=0, clock=clk, state="PAUSE")
    assert p.update(reading(False, 32, "Discharging"))[0] == "PAUSE"  # 32 < 35
    assert p.update(reading(False, 36, "Discharging"))[0] == "RUN"
    assert p.update(reading(False, 31, "Discharging"))[0] == "RUN"   # dentro da faixa, segue
    assert p.update(reading(False, 29, "Discharging"))[0] == "PAUSE"


def test_slow_charge_treated_as_battery():
    p = PowerPolicy(debounce_s=0, state="RUN")
    st, why, _ = p.update(reading(True, 60, "Discharging"))
    assert st == "PAUSE" and "carga lenta" in why
