# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Clean symmetric maneuver envelope, CS-25 / 14 CFR 25 L0 aid only.

14 CFR 25.333–25.337 (consulted 2026-11-06):
https://www.law.cornell.edu/cfr/text/14/25.335
https://www.law.cornell.edu/cfr/text/14/25.337
CS-25.333–.337 use the corresponding transport maneuver provisions.
Raymer (2018), Ch. 14: V-n construction; n=q S CL/W.
Regulatory: n+=min(3.8,max(2.5,2.1+24000/(W_lb+10000))), n-=-1
through VC, linearly to 0 at VD; VA >= VS1 sqrt(n+) subject to .335(c).
PRESSUPOSTO: chosen VC (EAS), clean CLmax/min; VD=1.25 VC uses the
simple .335(b) speed-ratio option, NOT a universal mandated margin.
No gusts (.341), buffet, flap loads, aeroelasticity, dive simulation,
Mach-limited envelope, systems credit or compliance demonstration.
"""
import math
from acdt import G0
from acdt.core.atmosphere import RHO0
from acdt.domains.aircraft.weights import LB
from ._validation import bounded


def flight_envelope(mass_kg: float, wing_area_m2: float, vc_eas_m_s: float,
                    cl_max: float = 1.5, cl_min: float = -1.0,
                    vd_ratio: float = 1.25) -> dict:
    """Speeds are equivalent airspeed m/s throughout, not TAS/CAS/Mach."""
    bounded("mass_kg", mass_kg, 0, 1e6, open_lower=True)
    bounded("wing_area_m2", wing_area_m2, 0, 2000, open_lower=True)
    bounded("vc_eas_m_s", vc_eas_m_s, 0, 400, open_lower=True)
    bounded("cl_max", cl_max, 0, 4, open_lower=True)
    bounded("cl_min", cl_min, -4, -0.01)
    bounded("vd_ratio", vd_ratio, 1.25, 2)
    weight = mass_kg*G0
    npos = min(3.8, max(2.5, 2.1+24000/(mass_kg/LB+10000)))
    vs = math.sqrt(2*weight/(RHO0*wing_area_m2*cl_max))
    va = vs*math.sqrt(npos)
    vc, vd = vc_eas_m_s, vc_eas_m_s*vd_ratio
    if va > vc:
        raise ValueError("VA stall/load intersection exceeds selected VC; unsupported envelope")
    vneg = math.sqrt(2*weight/(RHO0*wing_area_m2*abs(cl_min)))
    if vneg > vc:
        raise ValueError("negative stall intersection exceeds VC; revise clean CLmin or VC")
    def point(v):
        qS_W = 0.5*RHO0*v*v*wing_area_m2/weight
        lower_limit = -1.0 if v <= vc else -(vd-v)/(vd-vc)
        return {"V_eas_m_s": v, "n_positive": min(npos, qS_W*cl_max),
                "n_negative": max(lower_limit, qS_W*cl_min)}
    speeds = sorted(set([i*vd/80 for i in range(81)] + [vs, va, vneg, vc, vd]))
    return {"VS1_eas_m_s": vs, "VA_eas_m_s": va, "VC_eas_m_s": vc, "VD_eas_m_s": vd,
            "V_negative_corner_eas_m_s": vneg, "n_limit_positive": npos, "n_limit_negative": -1.0,
            "points": [point(v) for v in speeds],
            "regulatory": {"positive_limit": "25.337(b), W in lb", "negative_limit": "25.337(c)",
                           "VA": "stall/load intersection, 25.335(c)",
                           "VD": "simple VC/VD <= 0.8 option, 25.335(b)"},
            "pressupostos": {"VC_eas_m_s": vc, "VD_VC": vd_ratio, "cl_max": cl_max, "cl_min": cl_min},
            "disclaimer": "Analysis aid only; no CS-25 compliance claim. Gust/Mach/buffet envelopes omitted."}
