"""Autopilot/avionics selection by requirement filtering, and electrical power budget.

* Selection is a transparent filter + minimum-mass choice over the example DB
  (no scoring heuristics): sensor redundancy (IMU, barometer counts),
  interfaces (CAN, Ethernet), firmware stack, mass limit.
* Power budget: classical electrical load analysis — sum of connected loads
  with duty factors (MIL-E-7016F 'Electric load and power source capacity,
  aircraft, analysis of'; Moir & Seabridge, *Aircraft Systems*, 3rd ed., Ch. 5).
  Average and peak power, BEC/regulator sizing with margin.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AutopilotRequirements:
    min_imu: int = 1
    min_baro: int = 1
    min_can: int = 0
    ethernet: bool = False
    firmware: str | None = None  # "px4" | "ardupilot"
    max_mass: float | None = None


def select_autopilot(autopilots: list[dict], req: AutopilotRequirements) -> tuple[dict | None, list[str]]:
    ok, rejected = [], []
    for a in autopilots:
        why = []
        if a["imu"] < req.min_imu:
            why.append(f"IMU {a['imu']}<{req.min_imu}")
        if a["baro"] < req.min_baro:
            why.append(f"baro {a['baro']}<{req.min_baro}")
        if a["can"] < req.min_can:
            why.append(f"CAN {a['can']}<{req.min_can}")
        if req.ethernet and not a.get("ethernet"):
            why.append("no Ethernet")
        if req.firmware and req.firmware not in a.get("firmware", []):
            why.append(f"no {req.firmware}")
        if req.max_mass is not None and a["mass"] > req.max_mass:
            why.append("mass")
        (rejected if why else ok).append((a, why))
    best = min((a for a, _ in ok), key=lambda a: a["mass"]) if ok else None
    return best, [f"{a['id']}: {', '.join(w)}" for a, w in rejected]


@dataclass
class Load:
    name: str
    power_w: float
    duty: float = 1.0  # average fraction of time at that power
    peak_w: float | None = None
    bus: str = "avionics"  # avionics | servo | payload


@dataclass
class PowerBudget:
    loads: list[Load] = field(default_factory=list)
    regulator_margin: float = 1.5

    @property
    def average_w(self) -> float:
        return sum(l.power_w * l.duty for l in self.loads)

    @property
    def peak_w(self) -> float:
        return sum(l.peak_w if l.peak_w is not None else l.power_w for l in self.loads)

    def bus_peak(self, bus: str) -> float:
        return sum(l.peak_w if l.peak_w is not None else l.power_w for l in self.loads if l.bus == bus)

    def regulator_rating_w(self, bus: str) -> float:
        return self.regulator_margin * self.bus_peak(bus)

    def table(self) -> list[dict]:
        return [{"load": l.name, "bus": l.bus, "P_W": l.power_w, "duty": l.duty,
                 "P_avg_W": l.power_w * l.duty, "P_peak_W": l.peak_w if l.peak_w is not None else l.power_w}
                for l in self.loads]
