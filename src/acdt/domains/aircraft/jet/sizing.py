# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Coupled fixed-geometry jet mass closure, not a full transport MDA.

Raymer (2018), Aircraft Design, Ch. 3 Eqs. 3.4/3.5/3.11 and Tables 3.1/3.2:
m0 = m_empty(m0) + payload + crew + (1+reserve)*trip_burn.
Cruise integrates the differential jet Breguet equation
    dm/dx = -TSFC * D(m) / V, CL = m*g/(q*S),
using the parabolic polar (Anderson 2017, Introduction to Flight) plus
Korn–Mason/Lock wave drag and Mattingly/Ihme turbofan correlations from the
jet L0 modules. Constant L/D reduces to the existing exponential Breguet law.
Numerics: classical fourth-order Runge–Kutta, step doubling / Richardson
error estimate |m_end(2N)-m_end(N)|/15; sign-bracketed bisection for m0.
See Hairer, Norsett & Wanner (1993), Solving ODEs I, Ch. II (RK methods).

PRESSUPOSTO: constant cruise altitude/Mach, thrust balances drag; default maximum-rating
Mattingly/Ihme TSFC, or an opt-in supplied/corrected engine.map (no cycle code); CD0/e and
wing strip technology held fixed. Raymer historical takeoff/climb/landing
fractions and reserve (extra fuel mass, not reserve range). Statistical We
is not OEW, an engine/component build-up, fuel-volume closure or certification.
Opt-in weights.mode=components replaces statistical We with the explicitly
covered partial Raymer transport wing/HT/VT + supplied inventory (jet.weights);
all mass-dependent terms are recalculated per root trial. No unknown residual.
A caller supplies ONE candidate and a mass bracket; no architecture selection,
GA fallback, takeoff/climb thrust sizing, automatic wing/engine resizing or
simulator/MDO integration. A bracketed root is not a uniqueness/optimality claim.
"""
from __future__ import annotations

import math
from copy import deepcopy
from typing import Callable

from acdt import G0
from acdt.core.atmosphere import isa
from acdt.domains.aircraft.weights import statistical_fraction, statistical_source, SEGMENT_FRACTIONS
from ._validation import bounded
from .wave_drag import wave_drag
from .engine_map import engine_point
from .turbofan import turbofan_point  # default correlation; engine_point wraps maps

PHYSICAL_DEFAULTS = {"cd0": 0.020, "oswald": 0.82, "reserve_fraction": 0.06}
WAVE_DEFAULTS = {"thickness_ratio": 0.12, "sweep_deg": 25.0, "technology_factor": 0.95}
ENGINE_DEFAULTS = {"installation_factor": 0.97, "throttle_ratio": 1.05, "tsfc_multiplier": 1.0, "map": None}
SOLVER_DEFAULTS = {"mass_atol_kg": 0.01, "mass_rtol": 1e-7, "max_iterations": 80,
                   "cruise_steps": 32, "max_cruise_steps": 1024}


class IntegrationError(ValueError):
    """Numerical cruise integration did not reach its requested accuracy."""


def integrate_cruise(start_mass_kg: float, range_m: float, speed_m_s: float,
                     tsfc_kg_N_s: float, drag: Callable[[float], float], *,
                     mass_tolerance_kg: float = 0.001, steps: int = 32,
                     max_steps: int = 1024, auxiliary_fuel_flow_kg_s: float = 0.0) -> dict:
    """Differential Breguet at constant V/TSFC with mass-dependent drag [N].

    Refinement tolerance refers to end mass, NOT physical model accuracy.
    A failed/invalid step is never clipped to zero fuel/mass or a default L/D.
    """
    for name, value in (("start_mass_kg", start_mass_kg), ("speed_m_s", speed_m_s),
                        ("tsfc_kg_N_s", tsfc_kg_N_s), ("mass_tolerance_kg", mass_tolerance_kg)):
        bounded(name, value, 0, 1e12, open_lower=True)
    bounded("auxiliary_fuel_flow_kg_s", auxiliary_fuel_flow_kg_s, 0, 1e3)
    bounded("range_m", range_m, 0, 2e7)
    _integer("steps", steps, 1, 2048)
    _integer("max_steps", max_steps, 2*steps, 4096)

    def derivative(m):
        if not math.isfinite(m) or m <= 0:
            raise ValueError("cruise exhausted positive mass; range/step outside model domain")
        thrust = drag(m)
        if not math.isfinite(thrust) or thrust <= 0:
            raise ValueError("cruise drag must be finite and positive")
        return -(tsfc_kg_N_s*thrust+auxiliary_fuel_flow_kg_s)/speed_m_s

    def integrate(n):
        dx, m = range_m/n, start_mass_kg
        masses = [m]
        for _ in range(n):
            k1 = derivative(m)
            k2 = derivative(m+dx*k1/2)
            k3 = derivative(m+dx*k2/2)
            k4 = derivative(m+dx*k3)
            m += dx*(k1+2*k2+2*k3+k4)/6
            derivative(m)  # validate the accepted state too
            masses.append(m)
        return masses

    if range_m == 0:
        derivative(start_mass_kg)
        return {"end_mass_kg": start_mass_kg, "error_estimate_kg": 0.0, "steps": 0,
                "masses_kg": [start_mass_kg]}
    n = steps
    coarse = integrate(n)
    while 2*n <= max_steps:
        fine = integrate(2*n)
        error = abs(fine[-1]-coarse[-1])/15
        if error <= mass_tolerance_kg:
            return {"end_mass_kg": fine[-1], "error_estimate_kg": error,
                    "steps": 2*n, "masses_kg": fine}
        coarse, n = fine, 2*n
    raise IntegrationError(f"cruise step refinement failed at {n} steps (end-mass tolerance {mass_tolerance_kg:g} kg)")


def _integer(name, value, lower, upper):
    if isinstance(value, bool) or not isinstance(value, int) or not lower <= value <= upper:
        raise ValueError(f"{name} must be an integer in [{lower},{upper}]")


def _options(spec, key, defaults):
    opts = spec.get(key, {})
    if not isinstance(opts, dict) or set(opts)-set(defaults):
        raise ValueError(f"{key}: expected mapping with keys {sorted(defaults)}")
    return {**defaults, **opts}


def size_jet(spec: dict) -> dict:
    """Close one explicitly declared jet_transport candidate in user mass_bounds_kg.

    Required: configuration_id, aircraft_class='jet_transport', payload_kg,
    crew_kg, wing_area_m2, aspect_ratio, mach, altitude_m, range_m,
    thrust_sl_N per engine (uninstalled), n_engines and mass_bounds_kg=[lo,hi].
    Optional: cd0/oswald/reserve_fraction, wave, engine, solver, mtow_limit_kg,
    assumption_sources (provenance metadata). No prescribed mission L/D.
    Invalid syntax raises ValueError; unbracketed/domain/numerical failures are
    explicit JSON-safe non-converged results, never a fallback or a fake mass.
    """
    if not isinstance(spec, dict):
        raise ValueError("jet sizing spec must be a mapping")
    onboard_bridge_report = None
    if "onboard" in spec:
        from acdt.domains.aircraft.onboard_bridge import apply_onboard_to_jet_spec
        spec, onboard_bridge_report = apply_onboard_to_jet_spec(spec)
    required = {"configuration_id", "aircraft_class", "payload_kg", "crew_kg", "wing_area_m2",
                "aspect_ratio", "mach", "altitude_m", "range_m", "thrust_sl_N", "n_engines", "mass_bounds_kg"}
    allowed = required | set(PHYSICAL_DEFAULTS) | {"wave", "engine", "solver", "mtow_limit_kg", "assumption_sources", "performance", "storage", "weights", "auxiliary", "pressurization", "onboard_bridge", "duration"}
    if required-set(spec):
        raise ValueError(f"missing jet sizing inputs: {sorted(required-set(spec))}")
    if set(spec)-allowed:
        bad = sorted(set(spec)-allowed)
        tip = "; for transversal payload/electrical use onboard (consumed into auxiliary) or acdt onboard size" if "onboard" in bad or "closure" in bad else ""
        raise ValueError(f"unsupported jet sizing inputs: {bad}; no fixed mission L/D or GA fallback{tip}")
    if not isinstance(spec["configuration_id"], str) or not spec["configuration_id"].strip():
        raise ValueError("configuration_id must identify the supplied candidate (no automatic architecture choice)")
    if spec["aircraft_class"] != "jet_transport":
        raise ValueError("only explicit jet_transport statistics supported; no GA/unconventional fallback")
    for key, lo, hi in [("payload_kg", 0, 1e6), ("crew_kg", 0, 1e6), ("wing_area_m2", 1, 2000),
                         ("aspect_ratio", 2, 20), ("mach", .1, .9), ("altitude_m", 0, 15000),
                         ("range_m", 0, 2e7), ("thrust_sl_N", 1, 1e7)]:
        bounded(key, spec[key], lo, hi)
    _integer("n_engines", spec["n_engines"], 1, 8)
    fixed = spec["payload_kg"]+spec["crew_kg"]
    if fixed <= 0:
        raise ValueError("payload+crew must be positive for a meaningful mass closure")
    bounds = spec["mass_bounds_kg"]
    if not isinstance(bounds, (list, tuple)) or len(bounds) != 2:
        raise ValueError("mass_bounds_kg must be [lo,hi]")
    lo, hi = (bounded("mass bound", v, max(1000, fixed), 1e6) for v in bounds)
    if lo >= hi:
        raise ValueError("mass bounds must be strictly increasing")
    if "mtow_limit_kg" in spec:
        bounded("mtow_limit_kg", spec["mtow_limit_kg"], 1, 1e6)
    physical = {k: spec.get(k, v) for k, v in PHYSICAL_DEFAULTS.items()}
    for k, low, high in (("cd0", .001, .2), ("oswald", .1, 1), ("reserve_fraction", 0, .5)):
        bounded(k, physical[k], low, high)
    wave, engine = _options(spec, "wave", WAVE_DEFAULTS), _options(spec, "engine", ENGINE_DEFAULTS)
    solver = _options(spec, "solver", SOLVER_DEFAULTS)
    bounded("mass_atol_kg", solver["mass_atol_kg"], 1e-8, 100)
    bounded("mass_rtol", solver["mass_rtol"], 1e-12, .001)
    _integer("max_iterations", solver["max_iterations"], 1, 200)
    _integer("cruise_steps", solver["cruise_steps"], 1, 2048)
    _integer("max_cruise_steps", solver["max_cruise_steps"], 2*solver["cruise_steps"], 4096)
    if "performance" in spec:
        from .performance import validate_performance
        validate_performance(spec["performance"])
    if "storage" in spec:
        from acdt.core.energy_storage import validate_storage
        validate_storage(spec["storage"])
    aux = _options(spec, "auxiliary", {"fuel_flow_kg_s":0.0,"thrust_penalty_N":0.0,
                                      "pre_duration_s":0.0,"post_duration_s":0.0,"empty_mass_kg":0.0})
    for key,value in aux.items(): bounded("auxiliary."+key,value,0,1e6)
    pressurization_report = None
    if "pressurization" in spec:
        from .pressurization import assess_extraction
        pressurization_report = assess_extraction(spec["pressurization"])
        inc = pressurization_report.get("auxiliary_increments") or {}
        if inc:
            aux = dict(aux)
            aux["fuel_flow_kg_s"] = aux["fuel_flow_kg_s"] + inc["fuel_flow_kg_s"]
            aux["thrust_penalty_N"] = aux["thrust_penalty_N"] + inc["thrust_penalty_N"]
    from .weights import validate_weights, transport_weights
    weight_settings = spec.get("weights", {"mode": "statistical"})
    validate_weights(weight_settings)
    component_mode = weight_settings["mode"] == "components"
    if component_mode and aux["empty_mass_kg"]:
        raise ValueError("component mode owns its inventory: supply extra equipment as explicit covered weight items")
    last_weight_build = None
    class WeightCoverageError(ValueError): pass
    atm = isa(spec["altitude_m"])
    speed, area = spec["mach"]*atm.a, spec["wing_area_m2"]
    qS = .5*atm.rho*speed**2*area
    # Validate all engine and wing options BEFORE the root search; no fallback.
    deck = engine_point(spec["mach"], spec["altitude_m"], spec["thrust_sl_N"], throttle=1.0, **engine)
    if deck.get("status") == "unassessed":
        raise ValueError("engine map unassessed at cruise (outside domain); unknown ≠ zero thrust/TSFC")
    for key, low, high in (("thickness_ratio", .04, .2), ("sweep_deg", 0, 45),
                           ("technology_factor", .8, .96)):
        bounded(key, wave[key], low, high)
    tsfc = deck["TSFC_kg_N_s"]
    thrust = deck["thrust_installed_N"]*spec["n_engines"]
    thrust -= aux["thrust_penalty_N"]
    reserve = physical["reserve_fraction"]
    pre = SEGMENT_FRACTIONS["warmup_takeoff"]*SEGMENT_FRACTIONS["climb"]
    landing = SEGMENT_FRACTIONS["landing"]
    history = []

    def aero(m):
        cl = m*G0/qS
        wr = wave_drag(spec["mach"], cl=cl, **wave)
        cd = physical["cd0"]+cl*cl/(math.pi*spec["aspect_ratio"]*physical["oswald"])+wr["CD_wave"]
        return {"mass_kg": m, "CL": cl, "CD": cd, "CD_wave": wr["CD_wave"],
                "M_dd": wr["M_dd"], "L_D": cl/cd, "drag_N": qS*cd}

    def evaluate(m0):
        nonlocal last_weight_build
        if component_mode:
            last_weight_build = transport_weights(m0, spec["wing_area_m2"], spec["aspect_ratio"], weight_settings)
            if not last_weight_build["coverage"]["complete"]:
                raise WeightCoverageError("incomplete or out-of-domain component coverage: "+str(last_weight_build["coverage"]["missing"]))
            empty = last_weight_build["empty_mass_kg"]
            if empty <= 0: raise ValueError("nonpositive empty inventory is not an aircraft weight model")
        else:
            empty = m0*statistical_fraction("jet_transport", m0)
        empty += aux["empty_mass_kg"]
        start = m0*pre-aux["fuel_flow_kg_s"]*aux["pre_duration_s"]
        tol = max(solver["mass_atol_kg"], solver["mass_rtol"]*m0)
        integ = integrate_cruise(start, spec["range_m"], speed, tsfc,
                                 lambda m: aero(m)["drag_N"], mass_tolerance_kg=.1*tol/((1+reserve)*landing),
                                 steps=solver["cruise_steps"], max_steps=solver["max_cruise_steps"],
                                 auxiliary_fuel_flow_kg_s=aux["fuel_flow_kg_s"])
        landing_mass = integ["end_mass_kg"]*landing-aux["fuel_flow_kg_s"]*aux["post_duration_s"]
        if landing_mass <= 0: raise ValueError("auxiliary fuel exhausts mass")
        trip = m0-landing_mass
        fuel = (1+reserve)*trip
        residual = m0-empty-fixed-fuel
        trajectory = [dict(distance_m=(spec["range_m"]*i/integ["steps"] if integ["steps"] else 0), **aero(m))
                      for i, m in enumerate(integ["masses_kg"])]
        result = {"mtow_kg": m0, "residual_kg": residual, "tolerance_kg": tol,
                  "weights": {"empty_mass_kg": empty, "payload_kg": spec["payload_kg"],
                              "crew_kg": spec["crew_kg"], "trip_burn_kg": trip,
                              "reserve_fuel_kg": reserve*trip, "fuel_mass_kg": fuel,
                              "landing_mass_kg": landing_mass, "empty_fraction": empty/m0,
                              "fuel_fraction": fuel/m0, "source": ("Declared component sum (see build_up.items); no statistical fallback or OEW claim" if component_mode else statistical_source("jet_transport"))},
                  "cruise": {"start_mass_kg": start, "end_mass_kg": integ["end_mass_kg"],
                             "burn_kg": start-integ["end_mass_kg"], "speed_tas_m_s": speed,
                             "thrust_available_N": thrust, "max_drag_N": max(p["drag_N"] for p in trajectory),
                             "TSFC_kg_N_s": tsfc, "integration_steps": integ["steps"],
                             "integration_error_estimate_kg": integ["error_estimate_kg"], "trajectory": trajectory}}
        if component_mode:
            result["weights"]["build_up"] = deepcopy(last_weight_build)
        history.append({"mtow_kg": m0, "residual_kg": residual, "tolerance_kg": tol,
                        "integration_steps": integ["steps"], "integration_error_estimate_kg": integ["error_estimate_kg"]})
        if component_mode:
            history[-1]["empty_mass_kg"] = empty
            history[-1]["modeled_empty_mass_kg"] = last_weight_build["coverage"]["known_mass_modeled_kg"]
        return result

    status, solution, last, iterations, failed = "max_iterations", None, None, 0, None
    trial = lo
    try:
        left = last = evaluate(lo)
        if abs(left["residual_kg"]) <= left["tolerance_kg"]:
            solution, status = left, "converged"
        else:
            trial = hi
            right = last = evaluate(hi)
            if abs(right["residual_kg"]) <= right["tolerance_kg"]:
                solution, status = right, "converged"
        if solution is None:
            if left["residual_kg"]*right["residual_kg"] > 0:
                status = "not_bracketed"
            else:
                for iterations in range(1, solver["max_iterations"]+1):
                    trial = (lo+hi)/2
                    last = evaluate(trial)
                    if abs(last["residual_kg"]) <= last["tolerance_kg"]:
                        solution, status = last, "converged"
                        break
                    if left["residual_kg"]*last["residual_kg"] <= 0:
                        hi, right = trial, last
                    else:
                        lo, left = trial, last
    except WeightCoverageError as exc:
        status, failed = "incomplete_weight_build_up", {"mtow_kg": trial, "reason": str(exc)}
    except IntegrationError as exc:
        status, failed = "integration_not_converged", {"mtow_kg": trial, "reason": str(exc)}
    except ValueError as exc:
        status, failed = "outside_model_domain", {"mtow_kg": trial, "reason": str(exc)}
    converged = solution is not None
    checks = [{"name": "mass_closure", "passed": converged,
               "margin_kg": solution["tolerance_kg"]-abs(solution["residual_kg"]) if converged else None}]
    if converged:
        margin = thrust-solution["cruise"]["max_drag_N"]
        checks.append({"name": "cruise_thrust", "passed": margin >= 0, "margin_N": margin})
        if "mtow_limit_kg" in spec:
            margin = spec["mtow_limit_kg"]-solution["mtow_kg"]
            checks.append({"name": "mtow_limit", "passed": margin >= 0, "margin_kg": margin})
    assumptions = []
    for prefix, values, supplied in (("", physical, spec), ("wave.", wave, spec.get("wave", {})),
                                      ("engine.", engine, spec.get("engine", {})),
                                      ("solver.", solver, spec.get("solver", {}))):
        assumptions += [{"path": prefix+k, "value": v,
                         "source": "user" if k in supplied else "PRESSUPOSTO (acdt default)"} for k, v in values.items()]
    assumptions += [{"path": "segment_fractions", "value": dict(SEGMENT_FRACTIONS), "source": "Raymer 2018 Table 3.2"},
                    {"path": "cruise_model", "value": "constant Mach/altitude, max-rating TSFC at required thrust",
                     "source": "PRESSUPOSTO; no part-throttle deck"}]
    chosen = solution or last
    out = {"level": "L0", "method": "Raymer mass equation + differential jet Breguet + Korn–Mason/Mattingly/Ihme",
            "validity": "One supplied jet_transport candidate, fixed wing/engines, ISA cruise; not full transport MDA or CS-25 compliance.",
            "feasibility_scope": "Mass residual, cruise thrust and optional MTOW limit only.",
            "limitations": ["Statistical We, not OEW or component/engine weights; geometry changes affect aero, not a structural build-up.",
                            "Fixed wing and engine rating; no automatic component/architecture selection.",
                            "Constant Mach/altitude and maximum-rating TSFC at required thrust; no part-throttle map.",
                            "No takeoff/climb/OEI thrust, fuel volume, regulatory reserves or simulator verification."],
            "configuration_id": spec["configuration_id"], "inputs": deepcopy(spec),
            "converged": converged, "feasible": converged and all(c["passed"] for c in checks),
            "mtow_kg": solution["mtow_kg"] if converged else None,
            "weights": solution["weights"] if converged else None,
            "cruise": solution["cruise"] if converged else None, "turbofan_per_engine": deck,
            "solver": {"status": status, "iterations": iterations, "evaluations": len(history)+(1 if failed else 0),
                       "successful_evaluations": len(history),
                       "residual_kg": chosen["residual_kg"] if chosen else None,
                       "relative_residual": chosen["residual_kg"]/chosen["mtow_kg"] if chosen else None,
                       "last_trial_mass_kg": chosen["mtow_kg"] if chosen else None,
                       "requested_bounds_kg": list(bounds), "final_bounds_kg": [lo, hi],
                       "history": history, "failed_evaluation": failed,
                       "note": "Sign-bracketed root only; no sign change is not proof of global infeasibility or uniqueness."},
            "assumptions": assumptions, "checks": checks,
            "issues": ([status] if not converged else [c["name"] for c in checks if not c["passed"]])}

    if "auxiliary" in spec:
        out["auxiliary"] = dict(aux, scope="incremental constant loads; cruise plus explicit pre/post durations")
        out["assumptions"].append({"path":"auxiliary","value":deepcopy(aux),"source":"explicit incremental inputs; no engine penalty estimated"})
    if onboard_bridge_report and onboard_bridge_report.get("applied"):
        out["onboard_bridge"] = onboard_bridge_report
        out["assumptions"].append({"path":"onboard_bridge","value":deepcopy(onboard_bridge_report),
                                   "source":"opt-in onboard → auxiliary hotel/extraction"})
    if component_mode:
        out["empty_weight_mode"] = "components"
        out["weight_build_up"] = (solution["weights"]["build_up"] if converged else deepcopy(last_weight_build))
        out["limitations"][0] = "Partial transport regression build-up with explicit remaining masses; declared coverage, not certified OEW or independently validated component accuracy."
        out["limitations"].append("Component empty excludes ALL fuel and crew/payload. Closure fuel is trip + reserve; unusable fuel declared in storage is not fed back into MTOW.")
        out["assumptions"] += [{"path": "weights", "value": deepcopy(weight_settings), "source": "explicit component methods/masses; PRESSUPOSTO unless substantiated"}]
    elif "weights" in spec:
        out["empty_weight_mode"] = "statistical"
    if "performance" in spec:
        from .performance import screen_performance, UNASSESSED
        if aux["fuel_flow_kg_s"] or aux["thrust_penalty_N"]:
            performance = {"status":"unassessed_onboard_extraction", "reason":"takeoff/OEI generator availability and extraction model not implemented",
                           "requested_checks_passed":None,"regulatory_compliance":"unassessed","checks":[],
                           "issues":["onboard_takeoff_OEI_extraction_unassessed"],"unassessed":list(UNASSESSED),
                           "ground":None,"climb_points":[],"assumptions":[]}
        elif converged:
            performance = screen_performance(solution["mtow_kg"], spec, spec["performance"])
        else:
            performance = {"status": "unassessed", "reason": "jet mass closure did not converge",
                           "requested_checks_passed": None, "regulatory_compliance": "unassessed",
                           "checks": [], "issues": ["mass_not_converged"], "unassessed": list(UNASSESSED),
                           "ground": None, "climb_points": [], "assumptions": []}
        performance["schema_version"] = "1.0"
        out["performance"] = performance
        out["combined_requested_checks_passed"] = out["feasible"] and performance["requested_checks_passed"] is True
        out["screening_issues"] = list(performance["issues"])
        out["assumptions"] += performance["assumptions"]
        out["feasibility_scope"] += " Legacy feasible excludes optional performance; see combined_requested_checks_passed (not compliance)."
        out["limitations"][3] = "No continuous takeoff/OEI failure path, fuel volume, regulatory reserves or simulator verification."
    if "storage" in spec:
        from acdt.domains.aircraft.storage import aircraft_storage
        out["storage"] = aircraft_storage(spec["storage"], "jet_size", out)
        out["assumptions"] += out["storage"]["assumptions"]
        out["limitations"] = [s.replace("fuel volume", "fuel-volume/mass feedback") for s in out["limitations"]]
        out["limitations"].append("Optional storage is a separate capacity/volume post-check; legacy feasible excludes it.")
    if pressurization_report is not None:
        out["pressurization"] = pressurization_report
        out["assumptions"].append({"path": "pressurization", "value": deepcopy(spec["pressurization"]),
                                   "source": spec["pressurization"]["source"]})
        out["checks"] = list(out["checks"]) + list(pressurization_report["checks"])
        out["issues"] = list(out["issues"]) + list(pressurization_report.get("issues") or [])
        # unassessed extraction must not silently pass overall requested checks
        if pressurization_report["status"] == "unassessed":
            # Mass closure may still converge; extraction remains unassessed (unknown≠pass).
            if "combined_requested_checks_passed" in out:
                out["combined_requested_checks_passed"] = False
            out["limitations"].append("Pressurization cabin declared without supplied extraction: extraction unassessed (unknown≠pass).")
        elif pressurization_report["status"] == "assessed_supplied_auxiliary":
            out["limitations"].append("Pressurization extraction is a user-supplied constant auxiliary offtake, not an ECS pack / bleed map.")
    return out


def fixed_design_burn(spec: dict, mtow_kg: float, range_m: float) -> dict:
    """Trip burn of an ALREADY SIZED jet at fixed MTOW for another cruise range.

    Same terms as :func:`size_jet` (Raymer 2018 Table 3.2 fractions, differential
    Breguet with the same polar/wave/deck and explicit auxiliary flows); only the
    MTOW is held instead of solved. Used to derive the design-fuel range/endurance
    of the sized aircraft (bisection outside). Consistency with ``size_jet`` is a
    regression test: at the design range it reproduces ``trip_burn_kg``.
    Not a tank-capacity, step-climb, part-throttle or reserve-mission model.
    """
    bounded("mtow_kg", mtow_kg, 1, 1e6, open_lower=True)
    bounded("range_m", range_m, 0, 2e7)
    physical = {k: spec.get(k, v) for k, v in PHYSICAL_DEFAULTS.items()}
    wave, engine = _options(spec, "wave", WAVE_DEFAULTS), _options(spec, "engine", ENGINE_DEFAULTS)
    solver = _options(spec, "solver", SOLVER_DEFAULTS)
    aux = _options(spec, "auxiliary", {"fuel_flow_kg_s":0.0,"thrust_penalty_N":0.0,
                                      "pre_duration_s":0.0,"post_duration_s":0.0,"empty_mass_kg":0.0})
    atm = isa(spec["altitude_m"])
    speed, area = spec["mach"]*atm.a, spec["wing_area_m2"]
    qS = .5*atm.rho*speed**2*area
    _deck = engine_point(spec["mach"], spec["altitude_m"], spec["thrust_sl_N"], throttle=1.0, **engine)
    if _deck.get("status") == "unassessed" or _deck.get("TSFC_kg_N_s") is None:
        raise ValueError("engine map unassessed at cruise TSFC query")
    tsfc = _deck["TSFC_kg_N_s"]
    reserve = physical["reserve_fraction"]
    pre = SEGMENT_FRACTIONS["warmup_takeoff"]*SEGMENT_FRACTIONS["climb"]
    landing = SEGMENT_FRACTIONS["landing"]

    def drag(m):
        cl = m*G0/qS
        cd = physical["cd0"]+cl*cl/(math.pi*spec["aspect_ratio"]*physical["oswald"])+wave_drag(spec["mach"], cl=cl, **wave)["CD_wave"]
        return qS*cd

    tol = max(solver["mass_atol_kg"], solver["mass_rtol"]*mtow_kg)
    start = mtow_kg*pre-aux["fuel_flow_kg_s"]*aux["pre_duration_s"]
    integ = integrate_cruise(start, range_m, speed, tsfc, drag, mass_tolerance_kg=.1*tol/((1+reserve)*landing),
                             steps=solver["cruise_steps"], max_steps=solver["max_cruise_steps"],
                             auxiliary_fuel_flow_kg_s=aux["fuel_flow_kg_s"])
    landing_mass = integ["end_mass_kg"]*landing-aux["fuel_flow_kg_s"]*aux["post_duration_s"]
    if landing_mass <= 0:
        raise ValueError("auxiliary fuel exhausts mass")
    return {"trip_burn_kg": mtow_kg-landing_mass, "cruise_time_s": range_m/speed, "speed_tas_m_s": speed,
            "integration_error_estimate_kg": integ["error_estimate_kg"],
            "method": "fixed-MTOW differential Breguet, same terms as size_jet"}
