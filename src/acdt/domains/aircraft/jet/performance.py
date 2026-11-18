# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""L0 jet ground acceleration and steady AEO/OEI climb screening, not certification.

Classical force balances: m*dV/dt=T-D-mu*(W-L) on a level, still-air runway;
T-D=W*sin(gamma), L=W*cos(gamma) in rectilinear unaccelerated flight,
CD=CD0+delta_CD+K*CL², K=1/(pi*AR*e). Sources opened 2026-11-07:
ERAU online textbook, Introduction to Aerospace Flight Vehicles, Takeoff &
Landing Performance, Takeoff Analysis Eqs. 1–8, and Climbing, Ceiling &
Gliding, Climbing Flight Eqs. 3–4 (thrust aligned with flight path):
https://eaglepubs.erau.edu/introductiontoaerospaceflightvehicles/chapter/takeoff-landing-performance/
https://eaglepubs.erau.edu/introductiontoaerospaceflightvehicles/chapter/climbing-ceiling-gliding/
Raymer Sec. 17.8 ground-roll context, public worked transcription:
https://computationaldesignlab.github.io/aircraft-design/performance/takeoff.html

14 CFR 25.121(a)–(d) gradient tables, consulted 2026-11-07:
https://www.law.cornell.edu/cfr/text/14/25.121
These are NUMERICAL REFERENCES ONLY: VLOF/V2/VFTO, critical engine, rating,
configuration history and icing conditions have not been established. Regulatory
passed is always None. 25.111/.113/.115 path/distance/net-path rules unassessed.
Optional performance.field adds accelerate-stop / accelerate-go / BFL screening.
Without field: no balanced field, V1/VR/VMC, rotation/transition. Hot-day,
slope/wind/ground-effect and failure transients remain out of scope.

PRESSUPOSTO: identical engines, fixed mass at each supplied point, ISA, M<=0.3
(incompressible polar; Korn cruise model is NOT extrapolated to high takeoff CL).
Flap/gear/windmilling/OEI-trim drag, CLmax, e, friction, speeds, mass fractions
and thrust rating factors must be EXPLICIT inputs; zero is not filled silently.
Steady climb uses the exact regular quadratic force-balance branch, retaining
negative gradients. No negative climb or acceleration is clamped into a pass.
"""
from __future__ import annotations
import math
from copy import deepcopy
from typing import Callable

from acdt import G0
from acdt.core.atmosphere import isa
from ._validation import bounded
from .engine_map import engine_point
from .turbofan import turbofan_point

REFERENCES = {
    "25.121(a)": {2: 0.0, 3: .003, 4: .005},
    "25.121(b)": {2: .024, 3: .027, 4: .030},
    "25.121(c)": {2: .012, 3: .015, 4: .017},
    "25.121(d)": {2: .021, 3: .024, 4: .027},
}
UNASSESSED = ["validated AFM V-speeds (declared VLOF/V2/VMC/VR may be screened via performance.field)", "critical-engine/asymmetric controllability and failure transients",
              "rotation, transition and continuous takeoff path (25.111)",
              "wet/contaminated field length and CS-25.113 compliance (dry BFL screen is opt-in via performance.field)",
              "net takeoff flight path (25.115)", "25.121 compliance, including ratings/configuration/icing conditions"]


def steady_climb(mass_kg: float, speed_m_s: float, rho: float, wing_area_m2: float,
                 cd0: float, k: float, cl_max: float, thrust_N: float) -> dict:
    """Exact steady-force regular branch; gradient=tan(gamma), ROC=V*sin(gamma).

    A*s²-W*s+(T-D_level)=0, A=K*W²/(qS), s=sin(gamma).
    Stable root: 2*(T-D_level)/(W+sqrt(W²-4*A*(T-D_level))).
    A conservative level-flight stall check is enforced; no certified VSR.
    """
    for key, val in (("mass_kg", mass_kg), ("speed_m_s", speed_m_s), ("rho", rho),
                     ("wing_area_m2", wing_area_m2), ("cl_max", cl_max)):
        bounded(key, val, 0, 1e9, open_lower=True)
    for key, val in (("cd0", cd0), ("k", k), ("thrust_N", thrust_N)):
        bounded(key, val, 0, 1e9)
    weight, qS = mass_kg*G0, .5*rho*speed_m_s**2*wing_area_m2
    lift_scale = rho*wing_area_m2*cl_max
    if not math.isfinite(qS) or qS <= 0 or lift_scale <= 0:
        raise ValueError("dynamic pressure / lift scale outside numerical domain")
    vs_squared = 2*weight/lift_scale
    if not math.isfinite(vs_squared):
        raise ValueError("stall speed outside numerical domain")
    vs = math.sqrt(vs_squared)
    out = {"status": "assessed", "stall_screen_speed_m_s": vs, "speed_m_s": speed_m_s,
           "thrust_N": thrust_N, "gradient": None, "ROC_m_s": None, "gamma_deg": None,
           "CL": None, "drag_N": None, "force_residual_N": None}
    if speed_m_s < vs:
        return {**out, "status": "insufficient_lift"}
    induced = k*weight**2/qS
    excess = thrust_N-qS*cd0-induced
    discriminant = weight**2-4*induced*excess
    if discriminant < 0:
        return {**out, "status": "no_regular_steady_solution"}
    s = 2*excess/(weight+math.sqrt(discriminant))
    if abs(s) >= 1:
        return {**out, "status": "outside_steady_domain"}
    cosine = math.sqrt(1-s*s)
    cl = weight*cosine/qS
    drag = qS*(cd0+k*cl*cl)
    return {**out, "gradient": s/cosine, "ROC_m_s": speed_m_s*s,
            "gamma_deg": math.degrees(math.asin(s)), "CL": cl, "drag_N": drag,
            "force_residual_N": thrust_N-drag-weight*s}


def ground_run(mass_kg: float, speed_m_s: float, rho: float, wing_area_m2: float,
               cd0: float, k: float, cl_ground: float, mu_roll: float,
               thrust: Callable[[float], float], *, steps: int = 32, max_steps: int = 1024) -> dict:
    """Integrate ds/dV=mV/F and dt/dV=m/F, with positive wheel load and force.

    Composite Simpson in u=sqrt(V/V_target) regularizes the deck's sqrt(M).
    Step doubling: distance error <=max(.01 m,1e-5*distance), time <=max(.001 s,1e-5*time).
    Numerical controls/tolerances are PRESSUPOSTO, not physical accuracy guarantees.
    """
    for key, val in (("mass_kg", mass_kg), ("speed_m_s", speed_m_s), ("rho", rho), ("wing_area_m2", wing_area_m2)):
        bounded(key, val, 0, 1e9, open_lower=True)
    for key, val in (("cd0", cd0), ("k", k), ("cl_ground", cl_ground), ("mu_roll", mu_roll)):
        bounded(key, val, 0, 10)
    if isinstance(steps, bool) or not isinstance(steps, int) or steps < 2 or steps % 2:
        raise ValueError("ground steps must be a positive even integer >=2")
    if isinstance(max_steps, bool) or not isinstance(max_steps, int) or not 2*steps <= max_steps <= 4096:
        raise ValueError("max ground steps must be >=2*steps and <=4096")
    weight = mass_kg*G0
    if .5*rho*speed_m_s**2*wing_area_m2 <= 0:
        raise ValueError("target dynamic pressure outside numerical domain")
    minimum = math.inf
    failed = None
    def integrate(n):
        nonlocal minimum, failed
        distance, elapsed = 0.0, 0.0
        for i in range(n+1):
            u = i/n
            v = speed_m_s*u*u
            qS = .5*rho*v*v*wing_area_m2
            normal = weight-qS*cl_ground
            force = thrust(v)-qS*(cd0+k*cl_ground**2)-mu_roll*max(normal, 0)
            if not math.isfinite(force):
                raise ValueError("nonfinite ground force")
            minimum = min(minimum, force)
            if normal < -1e-9*weight or force <= 0:
                failed = {"speed_m_s": v, "net_force_N": force, "wheel_load_N": normal}
                return None
            factor = 1 if i in (0, n) else (4 if i % 2 else 2)
            dvdu = 2*speed_m_s*u
            distance += factor*mass_kg*v*dvdu/force
            elapsed += factor*mass_kg*dvdu/force
        return distance/(3*n), elapsed/(3*n)
    base = {"status": "unassessed", "distance_m": None, "time_s": None,
            "integration_steps": 0, "distance_error_estimate_m": None, "time_error_estimate_s": None}
    n, coarse = steps, integrate(steps)
    while coarse is not None and 2*n <= max_steps:
        fine = integrate(2*n)
        if fine is None: break
        ds, dt = abs(fine[0]-coarse[0])/15, abs(fine[1]-coarse[1])/15
        if ds <= max(.01, 1e-5*fine[0]) and dt <= max(.001, 1e-5*fine[1]):
            return {**base, "status": "assessed", "distance_m": fine[0], "time_s": fine[1],
                    "integration_steps": 2*n, "distance_error_estimate_m": ds,
                    "time_error_estimate_s": dt, "min_sampled_net_force_N": minimum}
        n, coarse = 2*n, fine
    return {**base, "status": "infeasible_ground_force" if failed else "integration_not_converged",
            "integration_steps": n, "failed_point": failed, "min_sampled_net_force_N": minimum}


def _mapping(value, required, optional, name):
    if not isinstance(value, dict) or required-set(value) or set(value)-required-optional:
        raise ValueError(f"{name}: required {sorted(required)}, optional {sorted(optional)}")


def validate_performance(settings: dict) -> None:
    """Validate explicit configuration inputs independently of mass convergence."""
    _mapping(settings, set(), {"ground", "climb_points", "field", "assumption_sources"}, "performance")
    if not settings.get("ground") and not settings.get("climb_points") and not settings.get("field"):
        raise ValueError("performance needs ground, climb_points and/or field (not an empty pass)")
    if "field" in settings:
        if "ground" not in settings:
            raise ValueError("performance.field requires performance.ground (shared polar/liftoff)")
        from .field_takeoff import validate_field
        validate_field(settings["field"], settings["ground"])
    common = {"altitude_m", "cl_max", "oswald", "delta_cd_flaps", "delta_cd_gear", "thrust_factor"}
    if "ground" in settings:
        g = settings["ground"]
        _mapping(g, common | {"liftoff_speed_m_s", "cl_ground", "mu_roll"},
                 {"obstacle_height_m", "max_ground_run_m", "steps", "max_steps"}, "performance.ground")
        _validate_point(g, "liftoff_speed_m_s")
        bounded("cl_ground", g["cl_ground"], 0, g["cl_max"])
        bounded("mu_roll", g["mu_roll"], 0, 1)
        for key in ("obstacle_height_m", "max_ground_run_m"):
            if key in g: bounded(key, g[key], 0, 1e6, open_lower=True)
        steps, maximum = g.get("steps", 32), g.get("max_steps", 1024)
        if isinstance(steps, bool) or not isinstance(steps, int) or steps < 2 or steps % 2:
            raise ValueError("ground.steps must be an even integer >=2")
        if isinstance(maximum, bool) or not isinstance(maximum, int) or not 2*steps <= maximum <= 4096:
            raise ValueError("ground.max_steps must be >=2*steps and <=4096")
    points = settings.get("climb_points", [])
    if not isinstance(points, list) or len(points) > 40:
        raise ValueError("climb_points must be a list with <=40 explicit operating points")
    names = set()
    for p in points:
        _mapping(p, common | {"name", "speed_m_s", "mass_fraction", "delta_cd_windmilling", "delta_cd_oei_trim"},
                 {"min_aeo_gradient", "min_oei_gradient", "reference_clause"}, "performance.climb_points")
        if not isinstance(p["name"], str) or not p["name"].strip() or p["name"] in names:
            raise ValueError("climb point names must be nonempty and unique")
        names.add(p["name"])
        _validate_point(p, "speed_m_s")
        bounded("mass_fraction", p["mass_fraction"], .1, 1)
        for key in ("delta_cd_windmilling", "delta_cd_oei_trim"):
            bounded(key, p[key], 0, 1)
        for key in ("min_aeo_gradient", "min_oei_gradient"):
            if key in p: bounded(key, p[key], 0, 1)
        if "reference_clause" in p and (not isinstance(p["reference_clause"], str) or p["reference_clause"] not in REFERENCES):
            raise ValueError("reference_clause must be one of 25.121(a), (b), (c), (d)")


def _validate_point(point, speed_key):
    bounded("altitude_m", point["altitude_m"], 0, 15000)
    bounded(speed_key, point[speed_key], 0, .3*isa(point["altitude_m"]).a, open_lower=True)
    if .5*isa(point["altitude_m"]).rho*point[speed_key]**2 <= 0:
        raise ValueError("target dynamic pressure outside numerical domain")
    bounded("cl_max", point["cl_max"], 0, 4, open_lower=True)
    bounded("oswald", point["oswald"], .1, 1)
    bounded("thrust_factor", point["thrust_factor"], 0, 1, open_lower=True)
    for key in ("delta_cd_flaps", "delta_cd_gear"):
        bounded(key, point[key], 0, 1)


def screen_performance(mass_kg: float, aircraft: dict, settings: dict) -> dict:
    """Screen a given converged mass; public wrapper jet_performance closes mass first.

    aircraft supplies wing_area_m2, aspect_ratio, thrust_sl_N, n_engines;
    clean cd0/engine options are inherited from jet_size, not GA methods.
    """
    validate_performance(settings)
    bounded("mass_kg", mass_kg, 0, 1e6, open_lower=True)
    for key, lo, hi in (("wing_area_m2", 1, 2000), ("aspect_ratio", 2, 20), ("thrust_sl_N", 1, 1e7)):
        bounded(key, aircraft[key], lo, hi)
    engines = aircraft["n_engines"]
    if isinstance(engines, bool) or not isinstance(engines, int) or not 1 <= engines <= 8:
        raise ValueError("n_engines must be an integer in [1,8]")
    clean_cd0 = aircraft.get("cd0", .020)
    bounded("cd0", clean_cd0, .001, .2)
    area = aircraft["wing_area_m2"]
    engine_opts = aircraft.get("engine", {})
    # Validate even if a requested lift condition later fails.
    engine_point(0, 0, aircraft["thrust_sl_N"], throttle=1.0, **engine_opts)
    checks, points = [], []
    def check(name, passed, margin=None, units=None):
        checks.append({"name": name, "passed": passed, "margin": margin, "units": units,
                       "scope": "engineering screen, not certification"})
    def thrust(v, p, count):
        r = engine_point(v/isa(p["altitude_m"]).a, p["altitude_m"], aircraft["thrust_sl_N"],
                         throttle=p["thrust_factor"], **engine_opts)
        if r.get("status") == "unassessed" or r.get("thrust_installed_N") is None:
            raise ValueError("engine map unassessed at performance point (outside domain)")
        return count*r["thrust_installed_N"]
    def climb(m, v, p, count, failed):
        cd0 = clean_cd0+p["delta_cd_flaps"]+p["delta_cd_gear"]
        if failed: cd0 += p["delta_cd_windmilling"]+p["delta_cd_oei_trim"]
        return steady_climb(m, v, isa(p["altitude_m"]).rho, area, cd0,
                            1/(math.pi*aircraft["aspect_ratio"]*p["oswald"]), p["cl_max"], thrust(v, p, count))
    ground = {"status": "unassessed", "reason": "no ground scenario supplied"}
    if "ground" in settings:
        g = settings["ground"]
        rho, v = isa(g["altitude_m"]).rho, g["liftoff_speed_m_s"]
        k = 1/(math.pi*aircraft["aspect_ratio"]*g["oswald"])
        ground = ground_run(mass_kg, v, rho, area, clean_cd0+g["delta_cd_flaps"]+g["delta_cd_gear"], k,
                            g["cl_ground"], g["mu_roll"], lambda speed: thrust(speed, g, engines),
                            steps=g.get("steps", 32), max_steps=g.get("max_steps", 1024))
        required_cl = mass_kg*G0/(.5*rho*v*v*area)
        ground.update({"mass_kg": mass_kg, "declared_liftoff_speed_m_s": v, "required_level_CL": required_cl,
                       "full_takeoff_distance_m": None, "idealized_straight_climb_distance_m": None,
                       "note": "Ground acceleration only, no rotation/transition. Straight-climb distance is NOT takeoff distance."})
        check("ground_integration", ground["status"] == "assessed")
        check("ground_liftoff_lift_capacity", required_cl <= g["cl_max"], g["cl_max"]-required_cl, "CL")
        if "max_ground_run_m" in g:
            distance = ground["distance_m"]
            check("ground_run_only_limit", None if distance is None else distance <= g["max_ground_run_m"],
                  None if distance is None else g["max_ground_run_m"]-distance, "m")
        if "obstacle_height_m" in g:
            initial = climb(mass_kg, v, g, engines, False)
            ground["idealized_initial_aeo_climb"] = initial
            gradient = initial["gradient"]
            if gradient is not None and gradient > 0 and ground["status"] == "assessed":
                ground["idealized_straight_climb_distance_m"] = g["obstacle_height_m"]/gradient
            check("idealized_obstacle_positive_climb", gradient is not None and gradient > 0, gradient, "gradient")
    field_report = None
    if "field" in settings:
        if "ground" not in settings or ground.get("status") == "unassessed":
            field_report = {"status": "unassessed", "reason": "field requires an assessed ground scenario",
                            "checks": [{"name": "field_requires_ground", "passed": None}],
                            "requested_checks_passed": None, "issues": ["field_requires_ground"],
                            "regulatory_compliance": "unassessed", "unassessed": list(UNASSESSED),
                            "assumptions": []}
        elif ground.get("status") != "assessed":
            field_report = {"status": "unassessed", "reason": "ground run not assessed; field distances withheld",
                            "checks": [{"name": "field_ground_assessed", "passed": False}],
                            "requested_checks_passed": False, "issues": ["field_ground_not_assessed"],
                            "regulatory_compliance": "unassessed", "unassessed": list(UNASSESSED),
                            "assumptions": []}
        else:
            from .field_takeoff import screen_field
            field_report = screen_field(mass_kg, aircraft, settings["ground"], settings["field"], clean_cd0)
            checks.extend(field_report["checks"])
            # populate full takeoff distance on ground block when AEO TOD exists
            tod = (field_report.get("tod_aeo") or {}).get("tod_m")
            if tod is not None:
                ground["full_takeoff_distance_m"] = tod
                ground["note"] = ("Ground acceleration plus optional field TOD/ASD/BFL screening; "
                                  "rotation/transition still unmodeled; CS-25 compliance unassessed")
    for p in settings.get("climb_points", []):
        m, v = mass_kg*p["mass_fraction"], p["speed_m_s"]
        aeo, oei = climb(m, v, p, engines, False), climb(m, v, p, engines-1, True)
        for label, result in (("aeo", aeo), ("oei", oei)):
            gradient = result["gradient"]
            check(p["name"]+":"+label+"_positive_climb", gradient is not None and gradient > 0, gradient, "gradient")
            key = "min_"+label+"_gradient"
            if key in p:
                margin = gradient-p[key] if gradient is not None else None
                check(p["name"]+":"+label+"_target", None if margin is None else margin >= 0, margin, "gradient")
        reference = {"passed": None, "status": "unassessed", "reason": "no reference clause requested"}
        if "reference_clause" in p:
            clause = p["reference_clause"]
            threshold = REFERENCES[clause].get(engines)
            gradient = oei["gradient"]
            strict = clause == "25.121(a)" and engines == 2
            margin = gradient-threshold if gradient is not None and threshold is not None else None
            reference = {"clause": clause, "threshold_gradient": threshold, "strictly_positive": strict,
                         "margin_gradient": margin,
                         "numerical_threshold_met": None if margin is None else (margin > 0 if strict else margin >= 0),
                         "passed": None, "status": "unassessed",
                         "reason": "Numerical comparison only; speed/rating/configuration/critical-engine/icing prerequisites unassessed.",
                         "source_url": "https://www.law.cornell.edu/cfr/text/14/25.121", "retrieved": "2026-11-07"}
        points.append({"name": p["name"], "mass_kg": m, "operating_engines_aeo": engines,
                       "operating_engines_oei": engines-1, "AEO": aeo, "OEI": oei, "regulatory_reference": reference})
    passed = all(c["passed"] is True for c in checks)
    unassessed = list(UNASSESSED)
    assumptions = [{"path": "performance", "value": deepcopy(settings), "source": "explicit user inputs / PRESSUPOSTO unless substantiated"},
                   {"path": "performance_model", "value": "ISA, still air, level runway, fixed point masses, identical engines; no ground-effect credit; M<=0.3",
                    "source": "PRESSUPOSTO L0"}]
    method = "Newton ground acceleration + steady force equilibrium; parabolic polar and existing turbofan lapse"
    if field_report is not None:
        unassessed = sorted(set(unassessed) - {"wet/contaminated field length and CS-25.113 compliance (dry BFL screen is opt-in via performance.field)",
                                               "validated AFM V-speeds (declared VLOF/V2/VMC/VR may be screened via performance.field)"} |
                            set(field_report.get("unassessed") or []))
        # keep VMC/VR nuances from field; still not validated AFM speeds
        assumptions += field_report.get("assumptions") or []
        method += "; optional field ASD/TOD/BFL screening"
    out = {"level": "L0", "status": "screened", "mass_kg": mass_kg, "inputs": deepcopy(settings),
           "ground": ground, "climb_points": points, "checks": checks,
           "requested_checks_passed": passed,
           "issues": [c["name"] for c in checks if c["passed"] is not True],
           "regulatory_compliance": "unassessed", "unassessed": unassessed,
           "assumptions": assumptions, "method": method,
           "validity": "Selected engineering points / optional BFL screen only, not a certified takeoff path or full transport MDA."}
    if field_report is not None:
        out["field"] = field_report
    return out
