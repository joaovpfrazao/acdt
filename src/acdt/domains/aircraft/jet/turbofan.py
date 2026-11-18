# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""High-bypass turbofan L0 correlation, not a thermodynamic engine deck.

Mattingly, Heiser & Pratt (2002), Aircraft Engine Design, 2nd ed., Ch. 2:
alpha = delta0 [1 - 0.49 sqrt(M) - 3 max(theta0-TR,0)/(1.5+M)].
delta0=p_t/p_SL, theta0=T_t/T_SL (isentropic freestream totals).
Ihme, ME257 Gas Turbines (2025), Eq. 2.77: installed TSFC in lb/(lbf h)
= (0.4 + 0.45 M) sqrt(T/Tref), https://ihmegroup.github.io/assets/pdf/ME257.pdf
Raymer (2018), Ch. 13: preliminary propulsion sizing context.
PRESSUPOSTO: TR=1.05, installation factor=0.97, TSFC multiplier=1.
Bleed/offtakes, hot-day, transient or engine calibration are out of scope here.
Opt-in Mach/altitude/throttle maps (tables or corrected parameters) live in engine_map.engine_point;
this function remains the default maximum-rating correlation.
Ram recovery means thrust is NOT globally monotonic in Mach; it declines
initially but may recover at cruise. Altitude lapse at fixed Mach is monotonic
in the supported ISA range. No pyCycle/OpenMDAO dependency (deferred L2).
"""
import math
from acdt import G0
from acdt.core.atmosphere import isa, P0, T0
from ._validation import bounded


def turbofan_point(mach: float, altitude_m: float, thrust_sl_N: float = 120000.0,
                   installation_factor: float = 0.97, throttle_ratio: float = 1.05,
                   tsfc_multiplier: float = 1.0) -> dict:
    """One engine at maximum dry rating. thrust_sl_N is UNINSTALLED SLS [N]."""
    bounded("mach", mach, 0, 0.9)
    bounded("altitude_m", altitude_m, 0, 15000)
    bounded("thrust_sl_N", thrust_sl_N, 0, 1e7, open_lower=True)
    bounded("installation_factor", installation_factor, 0, 1, open_lower=True)
    bounded("throttle_ratio", throttle_ratio, 1, 1.3)
    bounded("tsfc_multiplier", tsfc_multiplier, 0, 10, open_lower=True)
    atm = isa(altitude_m)
    ram = 1 + 0.2*mach**2
    theta0 = atm.T/T0*ram
    delta0 = atm.p/P0*ram**3.5
    alpha = delta0*(1 - 0.49*math.sqrt(mach) - 3*max(theta0-throttle_ratio, 0)/(1.5+mach))
    if alpha <= 0:
        raise ValueError("thrust correlation outside positive-thrust domain")
    thrust = thrust_sl_N*alpha*installation_factor
    # lb mass / (lbf h) = 1/(g0*3600) kg/(N s). Ihme is already INSTALLED.
    tsfc_imperial = (0.4 + 0.45*mach)*math.sqrt(atm.T/T0)*tsfc_multiplier
    tsfc = tsfc_imperial/(G0*3600)
    return {"mach": mach, "altitude_m": altitude_m, "thrust_installed_N": thrust,
            "thrust_lapse_uninstalled": alpha, "thrust_lapse_installed": alpha*installation_factor,
            "TSFC_kg_N_s": tsfc, "TSFC_lb_lbf_h": tsfc_imperial,
            "fuel_flow_kg_s": thrust*tsfc, "theta0": theta0, "delta0": delta0,
            "pressupostos": {"thrust_sl_N": thrust_sl_N, "installation_factor": installation_factor,
                             "throttle_ratio": throttle_ratio, "tsfc_multiplier": tsfc_multiplier,
                             "ISA": True},
            "citations": ["Mattingly et al. 2002 Ch. 2 high-bypass thrust lapse", "Ihme 2025 Eq. 2.77"],
            "limitations": "Generic maximum-rating correlation, not CFM56/LEAP data or a part-throttle deck."}
