# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""VTOL / eVTOL L0 sizing: hover power, transition and cruise energy, battery mass, architecture compare.

Architectures (PRESSUPOSTO defaults per architecture in ``ARCHITECTURES``, every one overridable):

* ``multirotor``: n lift rotors, cruise edgewise on the same rotors (equivalent L/D_eff, no wing);
* ``lift_cruise``: dedicated lift rotors (stopped in cruise) + cruise propeller on a wing;
* ``tilt_rotor``: the same disks hover and cruise (conversion via a simple L0 envelope).

Methods:

* Hover / climb power by momentum theory with figure of merit (``momentum``; Johnson, *Helicopter Theory*,
  Princeton 1980, Ch. 2; Leishman, *Principles of Helicopter Aerodynamics*, 2nd ed., Cambridge 2006, Ch. 2).
* Transition (winged architectures): constant-acceleration sweep 0 → V_conv; the wing carries
  W (V / V_wing)^2 and the rotors the rest, rotor induced velocity from Glauert's level-disk model
  (Leishman 2006 Sec. 2.14); propulsive power for drag + acceleration taken as cruise power (PRESSUPOSTO).
  Tilt-rotor adds a conversion penalty factor (PRESSUPOSTO 1.10). No transition dynamics or trim (deferred).
* Cruise shaft power P = W V / (L/D · eta_p) (Raymer, *Aircraft Design*, 6th ed. 2018, Sec. 17.2 power
  required; Hepperle 2012 electric range form).
* Electric chain eta = eta_motor · eta_esc. In hover the rotor efficiency is the FM; in cruise it is eta_p.
  Nominal pack energy E_nom = E (1 + reserve) / DoD and pack mass E_nom / (Wh/kg) (Hepperle, "Electric
  Flight — Potential and Limitations", NATO STO-MP-AVT-209, 2012, Eqs. 5–7, same convention as
  ``acdt.domains.aircraft.weights.battery_energy``). The pack is also sized for peak power,
  m >= P_peak / (C_max · Wh/kg) (C_max PRESSUPOSTO 6, Li-ion power cells ≈ 3–10C; LiPo higher); the larger governs. Pack Wh/kg is a pack-level PRESSUPOSTO (cells ≈ 250 Wh/kg,
  pack ≈ 150–200 Wh/kg after packaging overhead, cf. Hepperle 2012 Sec. 2).
* eVTOL sizing reference (method family, no code or data imported): Johnson, "NDARC — NASA Design and
  Analysis of Rotorcraft", NASA/TP-2015-218751, 2015; Johnson, Silva & Solis, "Concept Vehicles for VTOL Air
  Taxi Operations", AHS Aeromechanics Design for Transformative Vertical Flight, 2018.

Limits (L0): mass is an input unless the opt-in ``closure`` block is given (``vtol.closure``: component
build-up MTOW closure; no MDA), no BEMT rotor design, no rotor–rotor or rotor–wing
interference beyond a download factor, no noise, no transition dynamics, no OEI case.
"""
from __future__ import annotations

import copy
import math
from typing import Any

from acdt.core.atmosphere import isa

from . import momentum as M

G0 = M.G0

CITATIONS = [
    "Johnson, W., Helicopter Theory, Princeton University Press, 1980 (Dover 1994), Ch. 2 — momentum theory.",
    "Leishman, J.G., Principles of Helicopter Aerodynamics, 2nd ed., Cambridge University Press, 2006, Ch. 2 — "
    "actuator disk, figure of merit, climb, Glauert forward-flight inflow, blade loading.",
    "Hepperle, M., Electric Flight — Potential and Limitations, NATO STO-MP-AVT-209, 2012 — battery energy, "
    "reserve and depth of discharge.",
    "Raymer, D.P., Aircraft Design: A Conceptual Approach, 6th ed., AIAA, 2018, Sec. 17.2 — power required.",
    "Johnson, W., NDARC — NASA Design and Analysis of Rotorcraft, NASA/TP-2015-218751, 2015 — eVTOL sizing "
    "method reference (not imported).",
    "Johnson, W., Silva, C., Solis, E., Concept Vehicles for VTOL Air Taxi Operations, AHS Technical Conference "
    "on Aeromechanics Design for Transformative Vertical Flight, 2018 — architecture reference.",
]

# PRESSUPOSTO defaults (small eVTOL / UAV class). Each one is reported back under "pressupostos".
_COMMON = {
    "altitude_m": 0.0, "dT": 0.0,
    "rotors": {"FM": 0.70, "solidity": 0.10, "mach_tip_max": 0.60, "ct_sigma_max": 0.13,
               "thrust_to_weight_max": 1.5},
    "electric": {"eta_motor": 0.85, "eta_esc": 0.95, "pack_Wh_kg": 180.0, "reserve": 0.20, "dod": 0.80,
                 "c_rate_max": 6.0, "systems_power_W": 0.0, "battery_fraction_max": 0.40},
    "mission": {"t_hover_s": 60.0, "climb_height_m": 0.0, "climb_rate_m_s": 2.0, "cruise_distance_m": 0.0,
                "cruise_speed_m_s": 18.0, "t_loiter_s": 0.0},
}
ARCHITECTURES: dict[str, dict] = {
    "multirotor": {"rotors": {"n": 4, "disk_loading_N_m2": 150.0}, "download_factor": 1.02,
                   "cruise": {"LD": 4.0, "eta_prop": 0.65},
                   "transition": {"n": 0, "t_s": 0.0},
                   "note": "edgewise cruise on lift rotors; L/D_eff PRESSUPOSTO (no wing)"},
    "lift_cruise": {"rotors": {"n": 4, "disk_loading_N_m2": 200.0}, "download_factor": 1.06,
                    "cruise": {"LD": 10.0, "eta_prop": 0.80},
                    "transition": {"n": 2, "t_s": 15.0, "V_wing_frac": 0.75, "conv_penalty": 1.0},
                    "note": "dedicated lift rotors stopped in cruise; L/D includes their drag (PRESSUPOSTO)"},
    "tilt_rotor": {"rotors": {"n": 4, "disk_loading_N_m2": 350.0}, "download_factor": 1.10,
                   "cruise": {"LD": 11.0, "eta_prop": 0.75},
                   "transition": {"n": 2, "t_s": 20.0, "V_wing_frac": 0.75, "conv_penalty": 1.10},
                   "note": "same disks hover and cruise; prop-rotor compromise on FM/eta_p (PRESSUPOSTO)"},
}


def _merge(base: dict, over: dict | None) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        elif v is not None:
            out[k] = v
    return out


def resolve_inputs(spec: dict) -> tuple[dict, list[str]]:
    """Merge user spec over common + architecture defaults; list the defaulted (PRESSUPOSTO) keys."""
    arch = spec.get("architecture", "multirotor")
    if arch not in ARCHITECTURES:
        raise ValueError(f"unknown architecture {arch!r}; use one of {sorted(ARCHITECTURES)}")
    base = _merge(_COMMON, {k: v for k, v in ARCHITECTURES[arch].items() if k != "note"})
    cfg = _merge(base, spec)
    cfg["architecture"] = arch
    assumed: list[str] = []

    def walk(d: dict, s: dict, prefix: str):
        for k, v in d.items():
            p = f"{prefix}{k}"
            if isinstance(v, dict):
                walk(v, s.get(k) or {}, p + ".")
            elif k not in s:
                assumed.append(p)
    walk(base, spec, "")
    if "mass_kg" not in cfg:
        raise ValueError("mass_kg is required")
    return cfg, assumed


def hover_point(mass_kg: float, n_rotors: int, diameter_m: float | None = None,
                disk_loading_N_m2: float | None = None, FM: float = 0.70, altitude_m: float = 0.0,
                dT: float = 0.0, download_factor: float = 1.0, mach_tip_max: float = 0.60,
                solidity: float = 0.10, ct_sigma_max: float = 0.13) -> dict[str, Any]:
    """Hover state for n equal isolated rotors (momentum theory + FM)."""
    atm = isa(altitude_m, dT)
    T = mass_kg * G0 * download_factor
    Tr = T / n_rotors
    if diameter_m:
        Ar = math.pi * diameter_m ** 2 / 4
    elif disk_loading_N_m2:
        Ar = Tr / disk_loading_N_m2
        diameter_m = math.sqrt(4 * Ar / math.pi)
    else:
        raise ValueError("give diameter_m or disk_loading_N_m2")
    P_id_r = M.ideal_hover_power(Tr, atm.rho, Ar)
    P_r = P_id_r / FM
    Vtip = M.tip_speed_limit(atm.a, mach_tip_max)
    cts = M.blade_loading(Tr, atm.rho, Ar, Vtip, solidity)
    return {
        "rho_kg_m3": atm.rho, "a_m_s": atm.a, "thrust_total_N": T, "thrust_per_rotor_N": Tr,
        "n_rotors": n_rotors, "diameter_m": diameter_m, "area_per_rotor_m2": Ar, "area_total_m2": Ar * n_rotors,
        "disk_loading_N_m2": Tr / Ar, "v_induced_m_s": M.induced_velocity_hover(Tr, atm.rho, Ar),
        "P_ideal_W": P_id_r * n_rotors, "P_hover_shaft_W": P_r * n_rotors, "P_per_rotor_W": P_r,
        "power_loading_N_W": T / (P_r * n_rotors), "FM": FM,
        "tip_speed_max_m_s": Vtip, "rpm_max": Vtip / (diameter_m / 2) * 60 / (2 * math.pi),
        "ct_sigma_at_tip_limit": cts, "ct_sigma_margin": ct_sigma_max / cts - 1.0,
    }


def _transition(cfg: dict, hp: dict, P_cruise_shaft: float) -> dict[str, Any]:
    tr = cfg["transition"]
    n, t = int(tr.get("n", 0)), float(tr.get("t_s", 0.0))
    if n <= 0 or t <= 0 or cfg["architecture"] == "multirotor":
        return {"n": 0, "t_s": 0.0, "P_avg_shaft_W": 0.0, "power_factor": 0.0, "envelope": []}
    if tr.get("power_factor") is not None:  # user override (PRESSUPOSTO from the user)
        k = float(tr["power_factor"])
        return {"n": n, "t_s": t, "P_avg_shaft_W": k * hp["P_hover_shaft_W"], "power_factor": k,
                "envelope": [], "source": "user power_factor"}
    V_wing = float(tr.get("V_wing_frac", 0.75)) * cfg["mission"]["cruise_speed_m_s"]
    rho, nr = hp["rho_kg_m3"], hp["n_rotors"]
    Ar, FM, W = hp["area_per_rotor_m2"], cfg["rotors"]["FM"], hp["thrust_total_N"]
    env, Ps = [], []
    for i in range(11):
        V = V_wing * i / 10
        Treq = W * max(0.0, 1.0 - (V / V_wing) ** 2) if V_wing > 0 else W
        if Treq > 0:
            vi = M.induced_velocity_forward(Treq / nr, rho, Ar, V)
            P_rot = Treq * vi / FM   # induced power / FM (profile lumped in FM, L0)
        else:
            vi, P_rot = 0.0, 0.0
        P = (P_rot + P_cruise_shaft) * float(tr.get("conv_penalty", 1.0))
        env.append({"V_m_s": V, "rotor_thrust_N": Treq, "v_i_m_s": vi, "P_shaft_W": P})
        Ps.append(P)
    P_avg = sum(Ps) / len(Ps)  # constant acceleration → uniform in V
    return {"n": n, "t_s": t, "V_wing_m_s": V_wing, "P_avg_shaft_W": P_avg,
            "power_factor": P_avg / hp["P_hover_shaft_W"], "envelope": env,
            "source": "Glauert inflow + wing-borne fraction (V/V_wing)^2 (PRESSUPOSTO envelope)"}


def size_vtol(spec: dict, *, disciplines: bool = True) -> dict[str, Any]:
    """L0 VTOL / eVTOL sizing for one architecture. ``spec`` keys: architecture, mass_kg, rotors{n, diameter_m |
    disk_loading_N_m2, FM, bemt? (opt-in axial BEMT; unassessed≠pass), …}, mission{t_hover_s, climb_height_m, climb_rate_m_s, cruise_distance_m,
    cruise_speed_m_s, t_loiter_s}, cruise{LD, eta_prop}, transition{n, t_s, V_wing_frac, power_factor?},
    electric{eta_motor, eta_esc, pack_Wh_kg, reserve, dod, c_rate_max, systems_power_W}, download_factor.

    Opt-in (versioned addition): a ``closure`` block (and NO mass_kg) solves MTOW from component masses via
    ``vtol.closure.close_vtol``; without it the behaviour is unchanged (fixed supplied mass_kg)."""
    onboard_bridge_report = None
    if isinstance(spec, dict) and "onboard" in spec:
        from acdt.domains.aircraft.onboard_bridge import apply_onboard_to_vtol_spec
        spec, onboard_bridge_report = apply_onboard_to_vtol_spec(spec)

    if isinstance(spec, dict) and "closure" in spec:
        from .closure import close_vtol
        return close_vtol(spec)
    if "storage" in spec:
        from acdt.core.energy_storage import validate_storage
        validate_storage(spec["storage"])
    cfg, assumed = resolve_inputs(spec)
    r, e, mi, cr = cfg["rotors"], cfg["electric"], cfg["mission"], cfg["cruise"]
    m = float(cfg["mass_kg"])
    hp = hover_point(m, int(r["n"]), r.get("diameter_m"), r.get("disk_loading_N_m2") if not r.get("diameter_m")
                     else None, r["FM"], cfg["altitude_m"], cfg["dT"], cfg["download_factor"], r["mach_tip_max"],
                     r["solidity"], r["ct_sigma_max"])
    if r.get("bemt"):
        from .bemt import attach_to_hover
        hp = attach_to_hover(hp, r["bemt"])
        if hp.get("power_source") == "bemt" and hp.get("FM"):
            r = dict(r)
            r["FM"] = hp["FM"]
    eta_el = e["eta_motor"] * e["eta_esc"]
    W = m * G0
    # peak (control authority) — same disks at T/W_max
    Tmax_r = hp["thrust_per_rotor_N"] * r["thrust_to_weight_max"]
    P_peak_shaft = M.hover_power(Tmax_r, hp["rho_kg_m3"], hp["area_per_rotor_m2"], r["FM"]) * hp["n_rotors"]
    cts_peak = M.blade_loading(Tmax_r, hp["rho_kg_m3"], hp["area_per_rotor_m2"], hp["tip_speed_max_m_s"],
                               r["solidity"])
    # climb
    t_climb = mi["climb_height_m"] / mi["climb_rate_m_s"] if mi["climb_height_m"] > 0 else 0.0
    P_climb = (M.climb_power(hp["thrust_per_rotor_N"], hp["rho_kg_m3"], hp["area_per_rotor_m2"],
                             mi["climb_rate_m_s"], r["FM"]) * hp["n_rotors"]) if t_climb else 0.0
    # cruise
    V = mi["cruise_speed_m_s"]
    P_cruise = W * V / (cr["LD"] * cr["eta_prop"])
    t_cruise = mi["cruise_distance_m"] / V if V > 0 else 0.0
    t_loiter = mi["t_loiter_s"]
    tr = _transition(cfg, hp, P_cruise)
    t_tr = tr["n"] * tr["t_s"]
    segs = [
        ("hover", hp["P_hover_shaft_W"], mi["t_hover_s"]),
        ("vertical_climb", P_climb, t_climb),
        ("transition", tr["P_avg_shaft_W"], t_tr),
        ("cruise", P_cruise, t_cruise),
        ("loiter", P_cruise, t_loiter),
    ]
    t_total = sum(s[2] for s in segs)
    seg_out, E = [], 0.0
    for name, Ps, ts in segs:
        if ts <= 0:
            continue
        Pe = Ps / eta_el
        seg_out.append({"segment": name, "P_shaft_W": Ps, "P_elec_W": Pe, "t_s": ts, "E_Wh": Pe * ts / 3600})
        E += Pe * ts
    from ..native_disciplines import hotel_adjustment
    hotel, hotel_src = hotel_adjustment(float(e["systems_power_W"]), "electric.systems_power_W", spec)
    energy_complete = hotel is not None
    if hotel is None:
        hotel = float(e["systems_power_W"])
    E += hotel * t_total
    E_Wh = E / 3600
    E_nom_Wh = E_Wh * (1 + e["reserve"]) / e["dod"]
    if "systems_peak_power_W" in e:
        from acdt.core.energy_storage import number
        number("systems_peak_power_W",e["systems_peak_power_W"])
        if e["systems_peak_power_W"]<e["systems_power_W"]: raise ValueError("hotel peak below average")
    P_peak_elec = P_peak_shaft / eta_el + e.get("systems_peak_power_W",e["systems_power_W"])
    m_batt_E = E_nom_Wh / e["pack_Wh_kg"]
    m_batt_P = P_peak_elec / (e["c_rate_max"] * e["pack_Wh_kg"])  # power-limited pack (C-rate)
    m_batt = max(m_batt_E, m_batt_P)
    limiting = "energy" if m_batt_E >= m_batt_P else "power"
    c_rate = P_peak_elec / (m_batt * e["pack_Wh_kg"])
    frac = m_batt / m
    checks = {
        "battery_fraction": {"value": frac, "max": e["battery_fraction_max"], "ok": frac <= e["battery_fraction_max"]},
        "c_rate_peak": {"value": c_rate, "max": e["c_rate_max"], "ok": c_rate <= e["c_rate_max"] * (1 + 1e-9)},
        "ct_sigma_peak": {"value": cts_peak, "max": r["ct_sigma_max"], "ok": cts_peak <= r["ct_sigma_max"]},
    }
    out = {
        "architecture": cfg["architecture"], "name": cfg.get("name"), "level": "L0",
        "mass_kg": m, "note": ARCHITECTURES[cfg["architecture"]]["note"],
        "hover": hp,
        "peak": {"thrust_to_weight": r["thrust_to_weight_max"], "P_shaft_W": P_peak_shaft,
                 "P_per_rotor_W": P_peak_shaft / hp["n_rotors"], "P_elec_W": P_peak_elec, "ct_sigma": cts_peak},
        "cruise": {"V_m_s": V, "LD": cr["LD"], "eta_prop": cr["eta_prop"], "P_shaft_W": P_cruise,
                   "P_elec_W": P_cruise / eta_el},
        "transition": tr,
        "segments": seg_out, "t_total_s": t_total, "eta_chain": eta_el,
        "hotel_W": hotel, "hotel_source": hotel_src, "energy_complete": energy_complete,
        "energy_Wh": E_Wh, "energy_nominal_Wh": E_nom_Wh, "battery_mass_kg": m_batt,
        "battery_mass_energy_kg": m_batt_E, "battery_mass_power_kg": m_batt_P, "battery_limiting": limiting,
        "battery_mass_fraction": frac, "c_rate_peak": c_rate,
        "margins": {k: v["max"] / v["value"] - 1.0 if v["value"] > 0 else None for k, v in checks.items()},
        "checks": checks, "feasible": all(c["ok"] for c in checks.values()),
        "pressupostos": sorted(assumed), "inputs_resolved": cfg, "citations": CITATIONS,
        "deferred": ["W0 closure / full size MDA", "yawed/forward-flight BEMT, rotor–rotor interference", "NDARC-level component weights",
                     "noise", "transition dynamics / trim", "OEI and rotor interference"],
    }

    if "storage" in spec:
        from acdt.domains.aircraft.storage import aircraft_storage
        out["storage"] = aircraft_storage(spec["storage"], "vtol_size", out)
    if onboard_bridge_report and onboard_bridge_report.get("applied"):
        out["onboard_bridge"] = onboard_bridge_report
    if disciplines:
        from ..native_disciplines import attach
        attach("vtol", out, spec)
    return out


def compare_architectures(spec: dict, architectures: list[str] | None = None,
                          overrides: dict[str, dict] | None = None) -> dict[str, Any]:
    """Same mass and mission across architectures (architecture defaults unless ``overrides[arch]``).

    Architecture-specific keys in ``spec`` (rotors.n, disk loading, cruise, transition, download) are dropped so
    each architecture uses its own defaults; pass them per architecture in ``overrides``."""
    archs = architectures or list(ARCHITECTURES)
    common = {k: v for k, v in spec.items() if k not in ("architecture", "cruise", "transition", "download_factor")}
    rot = {k: v for k, v in (spec.get("rotors") or {}).items() if k not in ("n", "diameter_m", "disk_loading_N_m2")}
    common["rotors"] = rot
    rows, results = [], {}
    for a in archs:
        s = _merge(common, (overrides or {}).get(a))
        s["architecture"] = a
        res = size_vtol(s)
        results[a] = res
        rows.append({"architecture": a, "n_rotors": res["hover"]["n_rotors"],
                     "diameter_m": res["hover"]["diameter_m"], "disk_loading_N_m2": res["hover"]["disk_loading_N_m2"],
                     "P_hover_kW": res["hover"]["P_hover_shaft_W"] / 1e3, "P_cruise_kW": res["cruise"]["P_shaft_W"] / 1e3,
                     "energy_Wh": res["energy_Wh"], "battery_mass_kg": res["battery_mass_kg"],
                     "battery_mass_fraction": res["battery_mass_fraction"],
                     "battery_limiting": res["battery_limiting"], "feasible": res["feasible"]})
    best = min(rows, key=lambda x: x["battery_mass_kg"])["architecture"]
    return {"rows": rows, "lightest_battery": best, "results": results, "citations": CITATIONS,
            "note": "L0 compare at fixed mass; architecture-specific structural/propulsion mass not modelled "
                    "(lift rotors, tilt mechanism) — see deferred."}
