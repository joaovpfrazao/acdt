"""Lift estimation (Raymer 6th ed. Ch. 12; USAF DATCOM Sec. 4.1.3.2).

* Lift-curve slope: Helmbold/DATCOM form as given in Raymer Eq. 12.6
  CLα = 2πA / (2 + sqrt(4 + A²β²/η² (1 + tan²Λ_maxt/β²))) · (S_exp/S_ref) · F,
  η = clα/(2π/β), F = 1.07 (1 + d/b)² (fuselage lift factor, Raymer Eq. 12.9).
* Clean CLmax for high-aspect-ratio wings: Raymer Eq. 12.15,
  CLmax = 0.9 clmax cos Λ_c/4.
* Flap increments: Raymer Eq. 12.21, ΔCLmax = 0.9 Δclmax (S_flapped/S_ref) cos Λ_HL,
  Δclmax per device from Raymer Table 12.2.
* Take-off CLmax ≈ 80 % of landing CLmax (Raymer Sec. 5.3).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = ["lift_curve_slope", "clmax_clean", "delta_clmax_flap", "HighLiftDevice", "FLAP_DCLMAX", "HighLiftSummary",
           "high_lift_summary"]

# Raymer Table 12.2: Δclmax (airfoil) by device; c'/c factor applies where noted
FLAP_DCLMAX = {
    "none": (0.0, False), "plain": (0.9, False), "split": (0.9, False), "slotted": (1.3, False),
    "fowler": (1.3, True), "double_slotted": (1.6, True), "triple_slotted": (1.9, True),
    "le_flap": (0.3, False), "slat": (0.4, True), "kruger": (0.3, False),
}


def lift_curve_slope(AR: float, mach: float = 0.0, sweep_maxt: float = 0.0, cla_airfoil: float | None = None,
                     S_exp_over_S_ref: float = 1.0, fuselage_diameter: float = 0.0, span: float = 1.0) -> float:
    """Wing CLα [1/rad] — Raymer Eq. 12.6 (DATCOM 4.1.3.2 semi-empirical).

    ``cla_airfoil`` default 2π·0.95 per rad (η≈0.95, Raymer Sec. 12.4.1).
    Fuselage lift factor F = 1.07 (1+d/b)^2 (Raymer Eq. 12.9); the product
    (S_exp/S_ref)·F is capped at 0.98 as recommended by Raymer.
    """
    beta2 = 1 - mach**2
    beta = math.sqrt(beta2)
    if cla_airfoil is None:
        cla_airfoil = 0.95 * 2 * math.pi / beta
    eta = cla_airfoil / (2 * math.pi / beta)
    F = 1.07 * (1 + fuselage_diameter / span) ** 2
    factor = min(S_exp_over_S_ref * F, 0.98) if fuselage_diameter > 0 else 1.0
    den = 2 + math.sqrt(4 + AR**2 * beta2 / eta**2 * (1 + math.tan(sweep_maxt) ** 2 / beta2))
    return 2 * math.pi * AR / den * factor


def clmax_clean(clmax_airfoil: float, sweep_c4: float = 0.0) -> float:
    """Raymer Eq. 12.15 (high-AR wing): CLmax = 0.9 clmax cos Λ_c/4."""
    return 0.9 * clmax_airfoil * math.cos(sweep_c4)


@dataclass
class HighLiftDevice:
    kind: str = "plain"
    flapped_area_ratio: float = 0.6  # S_flapped / S_ref
    chord_extension: float = 1.0  # c'/c for Fowler-type devices
    hinge_sweep: float = 0.0


def delta_clmax_flap(dev: HighLiftDevice) -> float:
    """Raymer Eq. 12.21: ΔCLmax = 0.9 Δclmax (S_flapped/S_ref) cos Λ_HL."""
    dcl, scaled = FLAP_DCLMAX[dev.kind]
    if scaled:
        dcl *= dev.chord_extension
    return 0.9 * dcl * dev.flapped_area_ratio * math.cos(dev.hinge_sweep)


@dataclass
class HighLiftSummary:
    CLmax_clean: float
    CLmax_landing: float
    CLmax_takeoff: float


def high_lift_summary(clmax_airfoil: float, sweep_c4: float, flap: HighLiftDevice | None,
                      slat: HighLiftDevice | None = None, takeoff_fraction: float = 0.8) -> HighLiftSummary:
    """Combine clean CLmax and device increments; take-off CLmax = 0.8 × landing (Raymer Sec. 5.3)."""
    c = clmax_clean(clmax_airfoil, sweep_c4)
    dl = (delta_clmax_flap(flap) if flap else 0.0) + (delta_clmax_flap(slat) if slat else 0.0)
    land = c + dl
    to = max(c, takeoff_fraction * land)
    return HighLiftSummary(c, land, to)
