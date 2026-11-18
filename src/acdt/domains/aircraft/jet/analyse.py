# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Fixed-MTOW subsonic jet analysis, not a full MDA sizing loop.

Raymer (2018), Table 3.1 jet_transport We/W0=1.02*(W0_lb)^(-0.06),
Table 3.2 mission segments and Eqs. 3.5/3.11 jet Breguet + reserve;
reuse weights.py rather than introduce a transport component regression.
Anderson (2017), Introduction to Flight: CL=W/(qS), CD=CD0+CL²/(pi AR e).
PRESSUPOSTO: cruise at 0.85 MTOW, CD0=0.020, e=0.82, L/D=17 for
Breguet (separate from the one-point polar), reserve/trapped=6% of fuel,
crew=800 kg. L0 empty mass is statistical We, NOT airline-specific OEW.
No component build-up, pressurised fuselage or certification claim.
"""
import math
from acdt import G0
from acdt.core.atmosphere import isa
from acdt.domains.aircraft.weights import statistical_fraction, statistical_source, SEGMENT_FRACTIONS
from acdt.domains.aircraft.weights import breguet_range_fraction_jet
from ._validation import bounded
from .wave_drag import wave_drag
from .engine_map import engine_point
from .loads_cs25 import flight_envelope

DEFAULTS = {"cruise_mass_fraction": 0.85, "cd0": 0.020, "oswald": 0.82,
            "mission_ld": 17.0, "reserve_fraction": 0.06, "crew_kg": 800.0}


def analyse_jet(spec: dict) -> dict:
    """SI dict: mtow_kg, wing_area_m2, aspect_ratio, mach, altitude_m,
    range_m, thrust_sl_N (per engine); optional wave/engine/loads dicts.
    Fixed MTOW only: remaining_payload_kg is a budget, not converged sizing.
    """
    if not isinstance(spec, dict):
        raise ValueError("jet spec must be a mapping")
    limits = {"mtow_kg": (1000, 1e6), "wing_area_m2": (1, 2000), "aspect_ratio": (2, 20),
              "mach": (0.1, 0.9), "altitude_m": (0, 15000), "range_m": (0, 2e7),
              "thrust_sl_N": (1, 1e7)}
    for key, (lo, hi) in limits.items():
        if key not in spec:
            raise ValueError(f"missing jet input: {key}")
        bounded(key, spec[key], lo, hi)
    n_engines = spec.get("n_engines", 2)
    if isinstance(n_engines, bool) or not isinstance(n_engines, int) or not 1 <= n_engines <= 8:
        raise ValueError("n_engines must be an integer in [1,8]")
    a = {key: spec.get(key, val) for key, val in DEFAULTS.items()}
    for key, lo, hi in [("cruise_mass_fraction", 0.1, 1), ("cd0", 0.001, 0.2),
                         ("oswald", 0.1, 1), ("mission_ld", 1, 40),
                         ("reserve_fraction", 0, 0.5), ("crew_kg", 0, spec["mtow_kg"])]:
        bounded(key, a[key], lo, hi)
    mass, area, mach = spec["mtow_kg"], spec["wing_area_m2"], spec["mach"]
    atm = isa(spec["altitude_m"])
    speed = mach*atm.a
    q = 0.5*atm.rho*speed**2
    cl = mass*a["cruise_mass_fraction"]*G0/(q*area)
    wave = wave_drag(mach=mach, cl=cl, **spec.get("wave", {}))
    engine = engine_point(mach, spec["altitude_m"], spec["thrust_sl_N"], throttle=1.0, **spec.get("engine", {}))
    if engine.get("status") == "unassessed":
        raise ValueError("engine map unassessed at analyse cruise point")
    cd = a["cd0"] + cl**2/(math.pi*spec["aspect_ratio"]*a["oswald"]) + wave["CD_wave"]
    drag = q*area*cd
    thrust = engine["thrust_installed_N"]*n_engines
    empty_fraction = statistical_fraction("jet_transport", mass)
    cruise_fraction = breguet_range_fraction_jet(spec["range_m"], speed, a["mission_ld"], engine["TSFC_kg_N_s"])
    mission_fraction = math.prod(SEGMENT_FRACTIONS.values())*cruise_fraction
    fuel_fraction = (1+a["reserve_fraction"])*(1-mission_fraction)
    payload = mass*(1-empty_fraction-fuel_fraction)-a["crew_kg"]
    # Loads is a separate single-altitude EAS construction; VC is NOT cruise TAS.
    loads_inputs = {"vc_eas_m_s": 160.0, **spec.get("loads", {})}
    loads = flight_envelope(mass, area, **loads_inputs)
    checks = [
        {"name": "cruise_thrust", "passed": thrust >= drag, "margin_N": thrust-drag},
        {"name": "mass_budget", "passed": payload >= 0, "margin_kg": payload},
    ]
    return {"level": "L0", "analysis": "fixed-MTOW jet transport, not full sizing", "inputs": spec,
            "cruise": {"speed_tas_m_s": speed, "CL": cl, "CD": cd, "L_D": cl/cd,
                       "drag_N": drag, "thrust_available_N": thrust},
            "wave_drag": wave, "turbofan_per_engine": engine, "loads": loads,
            "weights": {"empty_fraction": empty_fraction, "empty_mass_kg": mass*empty_fraction,
                        "fuel_fraction": fuel_fraction, "fuel_mass_kg": mass*fuel_fraction,
                        "remaining_payload_kg": payload, "source": statistical_source("jet_transport"),
                        "note": "We regression, not an OEW/component build-up; crew separate."},
            "pressupostos": {**a, "n_engines": n_engines, "loads_VC_default": "loads" not in spec or
                             "vc_eas_m_s" not in spec["loads"]},
            "assumed_defaults": [k for k in DEFAULTS if k not in spec],
            "checks": checks, "issues": [c["name"] for c in checks if not c["passed"]],
            "disclaimer": "Analysis aid only; not CS-25 compliance or certification accuracy."}


def check_reference(reference: dict) -> dict:
    """Reference {spec, published, sources}; coarse We vs OEW comparison only.

    Comparison tolerance 25% is PRESSUPOSTO, not a validated accuracy band.
    Range and thrust are reference inputs, NOT independently validated outputs.
    """
    result = analyse_jet(reference["spec"])
    published = reference["published"]
    oew = bounded("published.oew_kg", published["oew_kg"], 0, reference["spec"]["mtow_kg"], open_lower=True)
    delta = result["weights"]["empty_mass_kg"]/oew-1
    check = {"name": "coarse_We_vs_OEW", "passed": abs(delta) <= 0.25, "relative_error": delta,
             "margin": 0.25-abs(delta), "tolerance_PRESSUPOSTO": 0.25}
    result["checks"].append(check)
    result["issues"] = [c["name"] for c in result["checks"] if not c["passed"]]
    result["reference"] = {"name": reference.get("name"), "published": published,
                           "sources": reference.get("sources", []),
                           "note": "Order-of-magnitude check only; different We/OEW definitions. Range/thrust not validated."}
    return result
