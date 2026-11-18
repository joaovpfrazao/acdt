# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Opt-in VTOL / eVTOL L0 MTOW mass closure from component masses.

Solves  m = sum_i m_i(m)  for ONE supplied architecture inside user ``mass_bounds_kg``
by sign-bracketed bisection (Burden & Faires, *Numerical Analysis*, 9th ed. 2011,
Sec. 2.1), the same solver pattern and reporting as ``jet.sizing.size_jet``.
Every mass-dependent term (hover state, rotor size when disk loading is given,
peak power, battery) is recomputed per trial with the native ``size_vtol``.

Component models (each one explicit; there is NO silent default component):

* ``rotors`` — ``AFDD00`` blade + hub-hinge regression, Johnson, NDARC Theory
  Manual, NASA/TP-2015-218751, 2015, Ch. 27-2 (Rotor Group), lb/ft/ft·s⁻¹ units:
  w_blade = 0.0024419 f_tilt N_rotor N_blade^0.53479 R^1.74231 c^0.77291 V_tip^0.87562 ν_blade^2.51048,
  w_hub = 0.0061182 N_rotor N_blade^0.20373 R^0.60406 V_tip^0.52803 ν_hub^1.00218 (W_blade/N_rotor)^0.87127,
  f_tilt = 1.17940 for tilting rotors (architecture ``tilt_rotor``), else 1.0; W = χ w.
  Reported average error 7.9 % blade / 12.2 % hub over 51 rotorcraft. The database is
  legacy helicopters/tiltrotors: use on small electric rotors is EXTRAPOLATION and
  is always flagged (calibrate χ with sourced measured masses). Or ``supplied``.
* ``motors`` — ``NASA15`` (NDARC Ch. 22-4): W_one = 0.5382 f_design Q^0.8129 lb,
  Q = P_peak/N (ft·lb), f_design = 1.0 for high torque-to-weight (Q/W > 3.5 ft·lb/lb)
  else 2.5606 (64 motors, 27.5 % avg error); or the high-torque-only fit
  W_one = 0.3928 Q^0.8587 (25 motors, 21.8 %). The class is checked against the
  result. P_peak = native peak shaft power per rotor (T/W_max); N = V_tip/R × gear
  ratio (gear_ratio PRESSUPOSTO 1.0 = direct drive). Or ``supplied``.
* ``controllers`` (ESC/inverters) — ``fraction_of_motor`` with a user source (NDARC
  Ch. 22-1 quotes 10–30 %, up to 70 % for small motors: outside → note, not a
  default) or ``supplied``.
* ``rotor_support`` (booms/pylons) — NDARC Ch. 27-2 form W_supt = χ f_supt W_MTO
  with a SUPPLIED sourced f_supt, or ``supplied``.
* ``airframe`` (fuselage, wing, gear, …) — ``fraction_of_mtow`` or ``supplied``,
  sourced; no cited small-UAV correlation is implemented.
* ``tilt_mechanism`` (required for ``tilt_rotor``) and ``cruise_propulsor``
  (required for ``lift_cruise``) — ``fraction_of_mtow`` or ``supplied``.
* ``other`` — list of sourced fixed masses (avionics, wiring, …).
* Battery — native ``size_vtol`` energy/power battery at the trial mass
  (Hepperle 2012; reserve, DoD, C-rate as the native model).
* Fixed items — payload/onboard items passed in ``fixed_items`` (onboard adapter).

Limits: L0 regression/fraction build-up, no structural sizing, no CG, no
certification. A bracketed root is not uniqueness/optimality; no sign change is
not proof of infeasibility.
"""
from __future__ import annotations

import copy
import math
from typing import Any

FT = 0.3048
LB = 0.45359237
FTLB = FT * LB * 9.80665  # N·m per ft·lb (1.3558 N·m)

CITATIONS = [
    "Johnson, W., NDARC — NASA Design and Analysis of Rotorcraft, Theory, NASA/TP-2015-218751, April 2015, "
    "Ch. 27-2 Rotor Group (AFDD00 blade/hub weight, rotor support form) and Ch. 22-1/22-4 Motor Model "
    "(NASA15 motor weight, controller fraction range).",
    "Hepperle, M., Electric Flight — Potential and Limitations, NATO STO-MP-AVT-209, 2012 — battery energy.",
    "Burden, R.L., Faires, J.D., Numerical Analysis, 9th ed., Brooks/Cole, 2011, Sec. 2.1 — bisection.",
]

SOLVER_DEFAULTS = {"mass_atol_kg": 1e-4, "mass_rtol": 1e-7, "max_iterations": 100}
TILT_FACTOR = 1.17940
COMPONENT_KEYS = {"rotors", "motors", "controllers", "rotor_support", "airframe", "tilt_mechanism",
                  "cruise_propulsor", "other"}
REQUIRED = ("rotors", "motors", "controllers", "rotor_support", "airframe")
EXTRAPOLATION_NOTE = ("NDARC regression database (legacy helicopters/tiltrotors, conventional motors); its range "
                      "is not stated in the consulted text — application to small electric VTOL is extrapolation, "
                      "calibrate χ with sourced measured masses")


def _num(name, v, lo=0.0, hi=None, strict=False):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ValueError(f"{name} must be a finite number")
    if v < lo or (strict and v == lo) or (hi is not None and v > hi):
        raise ValueError(f"{name}={v} outside [{lo}, {hi}]")
    return float(v)


def _source(name, c):
    if not isinstance(c.get("source"), str) or not c["source"].strip():
        raise ValueError(f"{name}.source required (cited data or PRESSUPOSTO statement)")


def _keys(name, c, allowed):
    if not isinstance(c, dict):
        raise ValueError(f"{name} must be a mapping")
    bad = set(c) - set(allowed)
    if bad:
        raise ValueError(f"unsupported {name} keys {sorted(bad)}")


def validate_closure(spec: dict) -> dict:
    """Validate the opt-in ``closure`` block (syntax only; missing coverage is a result status)."""
    cl = spec.get("closure")
    _keys("closure", cl, {"mass_bounds_kg", "components", "fixed_items", "solver", "mtow_limit_kg", "source"})
    if "mass_kg" in spec:
        raise ValueError("closure solves MTOW: do not also supply mass_kg")
    b = cl.get("mass_bounds_kg")
    if not isinstance(b, (list, tuple)) or len(b) != 2:
        raise ValueError("closure.mass_bounds_kg must be [lo, hi]")
    lo, hi = (_num("mass bound", v, 0.0, 1e5, strict=True) for v in b)
    if lo >= hi:
        raise ValueError("closure mass bounds must be strictly increasing")
    if "mtow_limit_kg" in cl:
        _num("mtow_limit_kg", cl["mtow_limit_kg"], 0.0, 1e5, strict=True)
    solver = dict(SOLVER_DEFAULTS, **(cl.get("solver") or {}))
    _keys("closure.solver", cl.get("solver") or {}, SOLVER_DEFAULTS)
    _num("mass_atol_kg", solver["mass_atol_kg"], 1e-9, 10, strict=True)
    _num("mass_rtol", solver["mass_rtol"], 1e-12, 1e-3, strict=True)
    if isinstance(solver["max_iterations"], bool) or not isinstance(solver["max_iterations"], int) \
            or not 1 <= solver["max_iterations"] <= 400:
        raise ValueError("max_iterations must be an integer in [1, 400]")
    for i, it in enumerate(cl.get("fixed_items") or []):
        _keys(f"fixed_items[{i}]", it, {"id", "mass_kg", "source", "role"})
        if not isinstance(it.get("id"), str) or not it["id"]:
            raise ValueError("fixed item id required")
        _num(f"fixed_items[{i}].mass_kg", it.get("mass_kg"))
        _source(f"fixed_items[{i}]", it)
    comps = cl.get("components") or {}
    _keys("closure.components", comps, COMPONENT_KEYS)
    for k, c in comps.items():
        if k == "other":
            if not isinstance(c, list):
                raise ValueError("components.other must be a list")
            for j, it in enumerate(c):
                _keys(f"other[{j}]", it, {"id", "mass_kg", "source"})
                _num(f"other[{j}].mass_kg", it.get("mass_kg"))
                _source(f"other[{j}]", it)
                if not isinstance(it.get("id"), str) or not it["id"]:
                    raise ValueError("other item id required")
            continue
        if not isinstance(c, dict):
            raise ValueError(f"components.{k} must be a mapping")
        m = c.get("method")
        allowed_methods = {"rotors": {"AFDD00", "supplied"}, "motors": {"NASA15", "supplied"},
                           "controllers": {"fraction_of_motor", "supplied"},
                           "rotor_support": {"fraction_of_mtow", "supplied"}}.get(k, {"fraction_of_mtow", "supplied"})
        if m not in allowed_methods:
            raise ValueError(f"components.{k}.method must be one of {sorted(allowed_methods)}")
        if m == "supplied":
            _keys(f"components.{k}", c, {"method", "mass_kg", "source"})
            _num(f"{k}.mass_kg", c.get("mass_kg")); _source(k, c)
        elif m in ("fraction_of_mtow", "fraction_of_motor"):
            _keys(f"components.{k}", c, {"method", "fraction", "source"})
            _num(f"{k}.fraction", c.get("fraction"), 0.0, 1.0 if m == "fraction_of_motor" else 0.9); _source(k, c)
        elif m == "AFDD00":
            _keys("components.rotors", c, {"method", "n_blades", "flap_frequency_per_rev", "flap_frequency_hub_per_rev",
                                           "chi_blade", "chi_hub", "source"})
            nb = c.get("n_blades")
            if isinstance(nb, bool) or not isinstance(nb, int) or not 2 <= nb <= 12:
                raise ValueError("rotors.n_blades must be an integer in [2, 12]")
            _num("flap_frequency_per_rev", c.get("flap_frequency_per_rev"), 0.5, 3.0, strict=True)
            if "flap_frequency_hub_per_rev" in c:
                _num("flap_frequency_hub_per_rev", c["flap_frequency_hub_per_rev"], 0.5, 3.0, strict=True)
            for x in ("chi_blade", "chi_hub"):
                if x in c:
                    _num(x, c[x], 0.0, 5.0, strict=True)
            _source("rotors", c)
        elif m == "NASA15":
            _keys("components.motors", c, {"method", "torque_class", "gear_ratio", "chi", "source"})
            if c.get("torque_class") not in ("high_torque", "other", "high_torque_only_fit"):
                raise ValueError("motors.torque_class must be high_torque | other | high_torque_only_fit (explicit)")
            if "gear_ratio" in c:
                _num("gear_ratio", c["gear_ratio"], 0.0, 50.0, strict=True)
            if "chi" in c:
                _num("motors.chi", c["chi"], 0.0, 5.0, strict=True)
            _source("motors", c)
    return {"bounds": [lo, hi], "solver": solver}


def _afdd00(c, n_rot, R_m, sigma, Vtip_m_s, tilting):
    nb = c["n_blades"]
    R = R_m / FT
    chord = sigma * math.pi * R / nb  # mean geometric chord from solidity σ = N_b c/(π R)
    V = Vtip_m_s / FT
    nu_b = c["flap_frequency_per_rev"]
    nu_h = c.get("flap_frequency_hub_per_rev", nu_b)
    f_tilt = TILT_FACTOR if tilting else 1.0
    w_blade = 0.0024419 * f_tilt * n_rot * nb ** 0.53479 * R ** 1.74231 * chord ** 0.77291 * V ** 0.87562 * nu_b ** 2.51048
    W_blade = c.get("chi_blade", 1.0) * w_blade
    w_hub = 0.0061182 * n_rot * nb ** 0.20373 * R ** 0.60406 * V ** 0.52803 * nu_h ** 1.00218 * (W_blade / n_rot) ** 0.87127
    W_hub = c.get("chi_hub", 1.0) * w_hub
    return {"mass_kg": (W_blade + W_hub) * LB, "blade_mass_kg": W_blade * LB, "hub_mass_kg": W_hub * LB,
            "radius_ft": R, "chord_ft": chord, "tip_speed_ft_s": V, "f_tilt": f_tilt,
            "nu_blade": nu_b, "nu_hub": nu_h, "nu_hub_source": "user" if "flap_frequency_hub_per_rev" in c
            else "PRESSUPOSTO ν_hub = ν_blade (single flap frequency supplied)",
            "chi_blade": c.get("chi_blade", 1.0), "chi_hub": c.get("chi_hub", 1.0),
            "method": "NDARC AFDD00 blade + hub (actual blade weight), Ch. 27-2",
            "reported_average_error": {"blade": 0.079, "hub": 0.122, "n_aircraft": 51},
            "extrapolation": True, "validity": EXTRAPOLATION_NOTE}


def _nasa15(c, n_rot, P_per_rotor_W, omega_rad_s):
    gear = c.get("gear_ratio", 1.0)
    N = omega_rad_s * gear
    Q = P_per_rotor_W / N / FTLB  # ft·lb
    cls = c["torque_class"]
    if cls == "high_torque_only_fit":
        w = 0.3928 * Q ** 0.8587; err = {"average": 0.218, "n_motors": 25}
    else:
        w = 0.5382 * (1.0 if cls == "high_torque" else 2.5606) * Q ** 0.8129; err = {"average": 0.275, "n_motors": 64}
    W = c.get("chi", 1.0) * w
    q_w = Q / W if W > 0 else None
    consistent = (q_w > 3.5) if cls in ("high_torque", "high_torque_only_fit") else (q_w <= 3.5)
    return {"mass_kg": n_rot * W * LB, "per_motor_kg": W * LB, "n_motors": n_rot, "peak_torque_ft_lb": Q,
            "peak_torque_N_m": Q * FTLB, "motor_speed_rpm": N * 60 / (2 * math.pi), "torque_to_weight_ft_lb_lb": q_w,
            "torque_class": cls, "torque_class_consistent": consistent, "gear_ratio": gear,
            "gear_ratio_source": "user" if "gear_ratio" in c else "PRESSUPOSTO 1.0 (direct drive)",
            "chi": c.get("chi", 1.0), "method": "NDARC NASA15 motor weight vs peak torque, Ch. 22-4",
            "reported_average_error": err, "extrapolation": True, "validity": EXTRAPOLATION_NOTE}


def close_vtol(spec: dict) -> dict[str, Any]:
    """Solve VTOL MTOW from component masses (opt-in ``closure`` block). See module docstring."""
    from .size import size_vtol, resolve_inputs
    cfg = validate_closure(spec)
    cl = spec["closure"]
    comps = cl.get("components") or {}
    arch = spec.get("architecture", "multirotor")
    required = list(REQUIRED) + (["tilt_mechanism"] if arch == "tilt_rotor" else []) \
        + (["cruise_propulsor"] if arch == "lift_cruise" else [])
    missing = [k for k in required if k not in comps]
    base = {k: v for k, v in spec.items() if k != "closure"}
    fixed_items = copy.deepcopy(cl.get("fixed_items") or [])
    fixed = sum(i["mass_kg"] for i in fixed_items) + sum(i["mass_kg"] for i in comps.get("other", []))
    lo, hi = cfg["bounds"]
    solver = cfg["solver"]
    history: list[dict] = []

    def evaluate(m):
        s = dict(copy.deepcopy(base), mass_kg=m)
        r = size_vtol(s)
        hp = r["hover"]
        n_rot = hp["n_rotors"]
        R = hp["diameter_m"] / 2
        sigma = r["inputs_resolved"]["rotors"]["solidity"]
        Vtip = hp["tip_speed_max_m_s"]
        parts: dict[str, dict] = {}
        rc = comps["rotors"]
        parts["rotors"] = _afdd00(rc, n_rot, R, sigma, Vtip, arch == "tilt_rotor") if rc["method"] == "AFDD00" \
            else {"mass_kg": rc["mass_kg"], "method": "supplied", "source": rc["source"]}
        mc = comps["motors"]
        parts["motors"] = _nasa15(mc, n_rot, r["peak"]["P_per_rotor_W"], Vtip / R) if mc["method"] == "NASA15" \
            else {"mass_kg": mc["mass_kg"], "method": "supplied", "source": mc["source"]}
        ec = comps["controllers"]
        if ec["method"] == "fraction_of_motor":
            parts["controllers"] = {"mass_kg": ec["fraction"] * parts["motors"]["mass_kg"], "fraction": ec["fraction"],
                                    "method": "fraction of motor mass (user-sourced)", "source": ec["source"],
                                    "within_NDARC_quoted_range_0.10_0.70": 0.10 <= ec["fraction"] <= 0.70}
        else:
            parts["controllers"] = {"mass_kg": ec["mass_kg"], "method": "supplied", "source": ec["source"]}
        for k in ("rotor_support", "airframe", "tilt_mechanism", "cruise_propulsor"):
            c = comps.get(k)
            if c is None:
                continue
            if c["method"] == "fraction_of_mtow":
                parts[k] = {"mass_kg": c["fraction"] * m, "fraction": c["fraction"], "source": c["source"],
                            "method": ("NDARC Ch. 27-2 W_supt = f_supt W_MTO, f_supt user-supplied" if k == "rotor_support"
                                       else "fraction of MTOW (user-sourced)")}
            else:
                parts[k] = {"mass_kg": c["mass_kg"], "method": "supplied", "source": c["source"]}
        parts["battery"] = {"mass_kg": r["battery_mass_kg"], "method": "native size_vtol energy/power battery (Hepperle 2012)",
                            "limiting": r["battery_limiting"]}
        total = fixed + sum(p["mass_kg"] for p in parts.values())
        residual = m - total
        tol = max(solver["mass_atol_kg"], solver["mass_rtol"] * m)
        history.append({"mtow_kg": m, "residual_kg": residual, "tolerance_kg": tol, "battery_mass_kg": r["battery_mass_kg"],
                        "component_sum_kg": total})
        return {"mtow_kg": m, "residual_kg": residual, "tolerance_kg": tol, "parts": parts, "native": r}

    status, solution, last, iterations, failed = "max_iterations", None, None, 0, None
    if missing:
        status = "incomplete_component_coverage"
    else:
        trial = lo
        try:
            left = last = evaluate(lo)
            right = None
            if abs(left["residual_kg"]) <= left["tolerance_kg"]:
                solution, status = left, "converged"
            else:
                trial = hi
                right = last = evaluate(hi)
                if abs(right["residual_kg"]) <= right["tolerance_kg"]:
                    solution, status = right, "converged"
            if solution is None:
                if left["residual_kg"] * right["residual_kg"] > 0:
                    status = "not_bracketed"
                else:
                    a, b = lo, hi
                    for iterations in range(1, solver["max_iterations"] + 1):
                        trial = (a + b) / 2
                        last = evaluate(trial)
                        if abs(last["residual_kg"]) <= last["tolerance_kg"]:
                            solution, status = last, "converged"
                            break
                        if left["residual_kg"] * last["residual_kg"] <= 0:
                            b = trial
                        else:
                            a, left = trial, last
        except ValueError as exc:
            status, failed = "outside_model_domain", {"mtow_kg": trial, "reason": str(exc)}
    converged = solution is not None
    checks = [{"name": "mass_closure", "passed": converged,
               "margin_kg": solution["tolerance_kg"] - abs(solution["residual_kg"]) if converged else None}]
    if converged:
        nat = solution["native"]
        for k, v in nat["checks"].items():
            checks.append({"name": "native_" + k, "passed": bool(v["ok"]), "value": v["value"], "max": v["max"]})
        mot = solution["parts"]["motors"]
        if "torque_class_consistent" in mot:
            checks.append({"name": "motor_torque_class_consistent", "passed": bool(mot["torque_class_consistent"]),
                           "torque_to_weight_ft_lb_lb": mot["torque_to_weight_ft_lb_lb"], "threshold": 3.5})
        if "mtow_limit_kg" in cl:
            mg = cl["mtow_limit_kg"] - solution["mtow_kg"]
            checks.append({"name": "mtow_limit", "passed": mg >= 0, "margin_kg": mg})
    chosen = solution or last
    assumptions = [{"path": "closure.solver." + k, "value": v,
                    "source": "user" if k in (cl.get("solver") or {}) else "PRESSUPOSTO (acdt default)"}
                   for k, v in solver.items()]
    assumptions.append({"path": "rotor_tip_speed", "value": "hover tip speed = native tip-speed limit (mach_tip_max·a)",
                        "source": "PRESSUPOSTO, same as the native blade-loading check"})
    assumptions.append({"path": "motors_per_rotor", "value": 1, "source": "PRESSUPOSTO one motor per lift rotor"})
    closure = {
        "status": status, "converged": converged, "mtow_kg": solution["mtow_kg"] if converged else None,
        "architecture": arch, "required_components": required, "missing_components": missing,
        "breakdown": ({"fixed_items": fixed_items, "other": copy.deepcopy(comps.get("other", [])),
                       "fixed_items_kg": sum(i["mass_kg"] for i in fixed_items),
                       "other_kg": sum(i["mass_kg"] for i in comps.get("other", [])),
                       **copy.deepcopy(solution["parts"])} if converged else None),
        "solver": {"status": status, "iterations": iterations, "evaluations": len(history) + (1 if failed else 0),
                   "successful_evaluations": len(history),
                   "residual_kg": chosen["residual_kg"] if chosen else None,
                   "relative_residual": chosen["residual_kg"] / chosen["mtow_kg"] if chosen else None,
                   "last_trial_mass_kg": chosen["mtow_kg"] if chosen else None,
                   "requested_bounds_kg": [lo, hi], "history": history, "failed_evaluation": failed,
                   "method": "sign-bracketed bisection (Burden & Faires 2011 Sec. 2.1)",
                   "note": "Sign-bracketed root only; no sign change is not proof of global infeasibility or uniqueness."},
        "checks": checks, "assumptions": assumptions, "citations": CITATIONS, "source": cl.get("source"),
        "validity": "L0 component build-up for ONE supplied architecture; NDARC regressions are extrapolated to small "
                    "electric VTOL (flagged); fractions/supplied masses are user-owned. Not structural sizing or CG.",
        "limitations": ["No wing/fuselage/landing-gear correlation for small UAV: airframe is a sourced fraction or mass.",
                        "Motors sized at native peak shaft power per rotor (T/W_max) and hover tip speed; no thermal/"
                        "continuous rating split.", "Cruise propulsor (lift+cruise) and tilt mechanism are supplied, "
                        "not scaled by a correlation unless given as a fraction of MTOW."],
    }
    if converged:
        out = copy.deepcopy(solution["native"])
    else:
        out = {"architecture": arch, "name": spec.get("name"), "level": "L0", "mass_kg": None, "feasible": False,
               "checks": {}, "pressupostos": [], "citations": CITATIONS}
        try:
            out["inputs_resolved"] = resolve_inputs(dict(base, mass_kg=1.0))[0]
            out["inputs_resolved"].pop("mass_kg", None)
        except ValueError:
            pass
    out["mtow_kg"] = closure["mtow_kg"]
    out["converged"] = converged
    out["closure"] = closure
    out["feasible"] = bool(converged and all(c["passed"] for c in checks))
    out["deferred"] = [d for d in out.get("deferred", []) if d != "W0 closure / full size MDA"]
    out["issues"] = [status] if not converged else [c["name"] for c in checks if not c["passed"]]
    return out
