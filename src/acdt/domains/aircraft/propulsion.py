"""Propulsion lapse models and helpers (first-cut).

* Piston (normally aspirated): Gagg & Ferrar (1934) relation
  P/P_SL = σ − (1 − σ)/7.55, as given in Gudmundsson (2014) Sec. 7.2.
* Turbojet/turbofan and turboprop, first approximation: available thrust/power
  proportional to density ratio σ (Anderson, *Aircraft Performance and Design*,
  1999, Ch. 3). Replace by engine deck in Phase 3 (Mattingly, *Aircraft Engine
  Design*, 2002, Ch. 2 lapse models; or pyCycle/OpenMDAO).
* Electric: shaft power independent of altitude (Hepperle 2012); motor/ESC
  thermal limits handled in acdt.core.systems.
"""
from __future__ import annotations


def lapse(kind: str, sigma: float) -> float:
    if kind == "electric":
        return 1.0
    if kind == "piston_prop":
        return sigma - (1 - sigma) / 7.55
    if kind in ("jet", "turboprop"):
        return sigma
    raise ValueError(f"unknown propulsion kind '{kind}'")


def is_propeller(kind: str) -> bool:
    return kind in ("electric", "piston_prop", "turboprop")
