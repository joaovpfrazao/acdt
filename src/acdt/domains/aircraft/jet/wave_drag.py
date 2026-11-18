# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Korn–Mason swept-wing drag divergence and Lock drag rise (L0).

Korn empirical relation (early 1970s), extended by simple sweep theory:
Mdd = kappa/cos(sweep) - (t/c)/cos(sweep)^2 - CL/(10*cos(sweep)^3).
Mason, Configuration Aerodynamics (2006), Ch. 7, Eqs. 7-3, 7-6–7-8:
https://archive.aoe.vt.edu/mason/Mason_f/ConfigAeroTransonics.pdf
Gur, Mason & Schetz (2010), Full-Configuration Drag Estimation, Journal of Aircraft 47(4), doi:10.2514/1.47557.
Raymer (2018), Aircraft Design, Ch. 12: compressibility context.
Mcrit = Mdd - (0.1/80)^(1/3), CDwave = 20 max(M-Mcrit, 0)^4;
this defines divergence by dCD/dM=0.1, not a fixed drag increment.
PRESSUPOSTO: a single representative wing strip, wing-area reference;
sweep_deg is the half-chord sweep per Mason Eq. 7-4 (not leading edge);
not a strip integral, buffet prediction, fuselage wave drag or CFD validation.
"""
import math
from ._validation import bounded


def wave_drag(mach: float, cl: float = 0.5, thickness_ratio: float = 0.12,
              sweep_deg: float = 25.0, technology_factor: float = 0.95) -> dict:
    """Representative swept wing; moderate CL, 0<=M<=0.9, sweep<=45 deg."""
    bounded("mach", mach, 0, 0.9)
    bounded("cl", cl, 0, 1.2)
    bounded("thickness_ratio", thickness_ratio, 0.04, 0.2)
    bounded("sweep_deg", sweep_deg, 0, 45)
    bounded("technology_factor", technology_factor, 0.8, 0.96)
    c = math.cos(math.radians(sweep_deg))
    mdd = technology_factor/c - thickness_ratio/c**2 - cl/(10*c**3)
    mcrit = mdd - (0.1/80)**(1/3)
    if not 0 < mcrit < mdd < 1:
        raise ValueError("Korn result outside subsonic validity; revise wing inputs")
    return {"mach": mach, "M_crit": mcrit, "M_dd": mdd,
            "CD_wave": 20*max(mach-mcrit, 0)**4,
            "dCD_dMach": 80*max(mach-mcrit, 0)**3,
            "pressupostos": {"wing_strip_equivalent": True, "technology_factor": technology_factor,
                             "cl": cl, "thickness_ratio": thickness_ratio, "sweep_deg": sweep_deg},
            "citation": "Korn; Mason 2006 Ch. 7 Eqs. 7-3, 7-6–7-8; Journal of Aircraft 47(4), doi:10.2514/1.47557",
            "limitations": "Representative wing only; no buffet or whole-aircraft wave drag validation."}
