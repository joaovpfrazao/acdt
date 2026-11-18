"""Battery pack sizing: series/parallel configuration from mission energy and peak current.

* Energy requirement comes from the sizing stage (Hepperle 2012 energy equations,
  including reserve and depth-of-discharge, see acdt.domains.aircraft.weights.battery_energy).
* Series count S from the bus voltage; parallel count P = max(energy, current) need.
* C-rate check: I_peak <= P · I_cont,cell (cell continuous rating).
* Pack mass = S · P · m_cell · k_pack, k_pack = packaging/BMS/wiring overhead
  (user assumption, default 1.20; cf. Hepperle 2012 Sec. 2 cell vs. pack energy).
Battery safety/transport: UN 38.3 and ASTM F3005 (see compliance.py).
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class BatteryPack:
    cell: dict
    S: int
    P: int
    energy_nom_J: float
    capacity_ah: float
    v_nom: float
    v_max: float
    mass: float
    c_rate_peak: float
    current_ok: bool
    specific_energy_Wh_kg: float
    limiting: str


def size_battery(cell: dict, energy_required_J: float, i_peak: float, S: int, k_pack: float = 1.20) -> BatteryPack:
    e_string = S * cell["v_nom"] * cell["capacity_ah"] * 3600
    p_energy = math.ceil(energy_required_J / e_string - 1e-9)
    p_current = math.ceil(i_peak / cell["i_cont"] - 1e-9)
    P = max(p_energy, p_current, 1)
    cap = P * cell["capacity_ah"]
    mass = S * P * cell["mass"] * k_pack
    E = e_string * P
    return BatteryPack(cell, S, P, E, cap, S * cell["v_nom"], S * cell["v_max"], mass, i_peak / cap,
                       i_peak <= P * cell["i_cont"], E / 3600 / mass, "energy" if p_energy >= p_current else "current")


def best_pack(cells: list[dict], energy_required_J: float, i_peak: float, S_for_cell, k_pack: float = 1.20,
              chemistry: str | None = None) -> BatteryPack:
    packs = [size_battery(c, energy_required_J, i_peak, S_for_cell(c), k_pack) for c in cells
             if chemistry in (None, c["chemistry"])]
    if not packs:
        raise ValueError("no cell matches the chemistry filter")
    return min(packs, key=lambda p: p.mass)
