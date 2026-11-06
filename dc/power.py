"""M4.4 / S6 — Energia dinâmica com histerese. Leitura ausente = unknown (nunca 'carregando').

Descobre as fontes em <sysfs>/power_supply/* pelo arquivo `type` (sem path fixo como AC/).
A política decide RUN/PAUSE para downloads; quem aplica é o cliente do qBittorrent
(pausa por torrent via API, não o serviço inteiro).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

DEFAULT_SYSFS = Path("/sys/class/power_supply")
EXTERNAL_TYPES = {"Mains", "USB", "USB_C", "USB_PD", "USB_PD_DRP", "Wireless"}


def _read(p: Path) -> Optional[str]:
    try:
        return p.read_text("utf-8").strip()
    except OSError:
        return None


@dataclass
class Supply:
    name: str
    type: Optional[str]
    online: Optional[bool]
    capacity: Optional[int]
    status: Optional[str]
    scope: Optional[str] = None   # "Device" = periférico (mouse/controle), não alimenta o Deck


@dataclass
class PowerReading:
    ac_online: Optional[bool]          # None = unknown
    battery_pct: Optional[int]         # None = unknown
    battery_status: Optional[str]      # Charging/Discharging/Full/Not charging/None
    supplies: list[Supply] = field(default_factory=list)


def discover(sysfs: Path = DEFAULT_SYSFS) -> list[Supply]:
    out = []
    if not sysfs.is_dir():
        return out
    for d in sorted(sysfs.iterdir()):
        t = _read(d / "type")
        online = _read(d / "online")
        cap = _read(d / "capacity")
        out.append(Supply(d.name, t,
                          None if online is None else online == "1",
                          int(cap) if cap and cap.isdigit() else None,
                          _read(d / "status"), _read(d / "scope")))
    return out


def read_power(sysfs: Path = DEFAULT_SYSFS) -> PowerReading:
    # Achado no Deck real: mouse Logitech aparece como hidpp_battery_0 (type=Battery, scope=Device)
    sup = [s for s in discover(sysfs) if s.scope != "Device"]
    ext = [s for s in sup if s.type in EXTERNAL_TYPES and s.online is not None]
    bats = [s for s in sup if s.type == "Battery"]
    ac = any(s.online for s in ext) if ext else None
    bat = next((b for b in bats if b.capacity is not None), None)
    return PowerReading(ac, bat.capacity if bat else None, bat.status if bat else None, sup)


@dataclass
class PowerPolicy:
    min_battery_pct: int = 30          # abaixo disso, sempre pausa
    hysteresis_pct: int = 5            # só volta a rodar com min + histerese
    allow_on_battery: bool = False     # baixar fora do carregador?
    debounce_s: float = 60.0           # mudança precisa persistir esse tempo
    clock: Callable[[], float] = time.monotonic
    state: str = "PAUSE"
    _pending: Optional[str] = None
    _pending_since: float = 0.0

    def desired(self, r: PowerReading) -> tuple[Optional[str], str]:
        if r.ac_online is None and r.battery_pct is None:
            return None, "leituras de energia indisponíveis (unknown) — mantém estado"
        if r.battery_pct is not None and r.battery_pct < self.min_battery_pct:
            return "PAUSE", f"bateria {r.battery_pct}% < mínimo {self.min_battery_pct}%"
        if r.ac_online:
            if r.battery_status == "Discharging":
                return "PAUSE", "carregador conectado mas bateria descarregando (carga lenta)"
            return "RUN", "no carregador"
        if r.ac_online is None:
            return None, "estado do carregador unknown — mantém estado"
        if not self.allow_on_battery:
            return "PAUSE", "na bateria (allow_on_battery=false)"
        if r.battery_pct is None:
            return None, "na bateria com nível unknown — mantém estado"
        if self.state == "PAUSE" and r.battery_pct < self.min_battery_pct + self.hysteresis_pct:
            return "PAUSE", f"bateria {r.battery_pct}% abaixo da faixa de histerese"
        return "RUN", f"na bateria com {r.battery_pct}%"

    def update(self, r: PowerReading) -> tuple[str, str, bool]:
        """Retorna (estado, motivo, mudou?)."""
        want, why = self.desired(r)
        if want is None or want == self.state:
            self._pending = None
            return self.state, why, False
        t = self.clock()
        if self._pending != want:
            self._pending, self._pending_since = want, t
        if t - self._pending_since >= self.debounce_s:
            self.state, self._pending = want, None
            return self.state, why, True
        return self.state, f"{why} (aguardando estabilidade)", False
