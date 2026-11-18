# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""L0 accelerate-stop / accelerate-go / balanced-field screening for jets.

Classical force balances on a level, still-air runway (same as performance.ground_run):
m dV/dt = T - D - μ (W - L) while accelerating; braking uses μ_brake with T=0
(no reverse thrust credit unless an explicit positive reverse factor is supplied).
Airborne screen distance uses the steady climb gradient at the declared V2
(ERAU climb force balance already in performance.steady_climb).

Balanced field: search V1 such that ASD(V1) ≈ TOD_OEI(V1) (Krenkel & Salzman 1968 /
Roskam Part I / Torenbeek screening construction; public TAKEOFF2 notes,
Virginia Tech Mason group). CS-25.109/.113 definitions are used as numerical
SCREENING references only — regulatory_compliance stays unassessed.

PRESSUPOSTO: identical engines, fixed mass, ISA, M≤0.3, no hot-day/slope/wind/ground-effect,
no VMCG flight-test model. Opt-in ``include_rotation_transition`` adds a Roskam/Torenbeek
screening rotation + circular transition to screen height; omitting it keeps the PR #25
ground-run + steady-gradient airborne model unchanged. VMC/VR/V2/VLOF must be EXPLICIT when
used; missing data → unassessed (never a silent zero-length airborne segment).
"""
from __future__ import annotations
import math
from copy import deepcopy
from typing import Callable

from acdt import G0
from acdt.core.atmosphere import isa
from ._validation import bounded
from .engine_map import engine_point

SCREEN_FT = 35.0
SCREEN_M = SCREEN_FT * 0.3048  # 10.668 m
CITATIONS = [
    "ERAU Introduction to Aerospace Flight Vehicles — takeoff/landing & climb force balances",
    "Krenkel & Salzman, Journal of Aircraft 5(5):429, 1968 (BFL construction)",
    "Roskam, Airplane Design Part I; Torenbeek, Synthesis of Subsonic Airplane Design (screening BFL)",
    "14 CFR 25.109 / 25.113 numerical definitions as screening references only (compliance unassessed)",
    "Roskam Airplane Design Part I / Torenbeek — rotation time × mean speed; circular transition R=V²/(g(n−1))",
]


def _mapping(value, required, optional, name):
    if not isinstance(value, dict) or required - set(value) or set(value) - required - optional:
        raise ValueError(f"{name}: required {sorted(required)}, optional {sorted(optional)}")


def validate_field(settings: dict, ground: dict) -> None:
    """Field block requires a ground scenario (shared polar/altitude/liftoff)."""
    _mapping(settings, {"v2_m_s", "mu_brake", "recognition_delay_s", "source"},
             {"screen_height_m", "vmc_m_s", "vr_m_s", "v1_m_s", "delta_cd_spoiler",
              "thrust_reverse_factor", "oei_delta_cd_windmilling", "oei_delta_cd_trim",
              "max_field_length_m", "steps", "max_steps", "v1_search_points",
              "include_rotation_transition", "rotation_time_s", "transition_load_factor"},
             "performance.field")
    if not isinstance(settings.get("source"), str) or not settings["source"].strip():
        raise ValueError("field.source required (PRESSUPOSTO or citation)")
    for key in ("v2_m_s", "mu_brake", "recognition_delay_s"):
        bounded(key, settings[key], 0, 1e6, open_lower=(key != "mu_brake"))
    bounded("mu_brake", settings["mu_brake"], 0, 1)
    if settings["recognition_delay_s"] > 10:
        raise ValueError("recognition_delay_s outside numerical domain (0,10] s")
    for key in ("screen_height_m", "vmc_m_s", "vr_m_s", "v1_m_s", "max_field_length_m"):
        if key in settings: bounded(key, settings[key], 0, 1e6, open_lower=True)
    for key in ("delta_cd_spoiler", "thrust_reverse_factor", "oei_delta_cd_windmilling", "oei_delta_cd_trim"):
        if key in settings: bounded(key, settings[key], 0, 1)
    if "thrust_reverse_factor" in settings and settings["thrust_reverse_factor"] > 0.5:
        raise ValueError("thrust_reverse_factor >0.5 outside screening domain")
    vlof = ground["liftoff_speed_m_s"]
    if settings["v2_m_s"] < vlof:
        raise ValueError("v2_m_s must be >= ground.liftoff_speed_m_s for this screening model")
    if "vr_m_s" in settings and not ground.get("liftoff_speed_m_s", 0) >= settings["vr_m_s"] >= settings.get("vmc_m_s", 0):
        if settings["vr_m_s"] > vlof: raise ValueError("vr_m_s must be <= liftoff_speed_m_s")
    if "v1_m_s" in settings and settings["v1_m_s"] > vlof:
        raise ValueError("v1_m_s must be <= liftoff_speed_m_s")
    if "vmc_m_s" in settings and settings["vmc_m_s"] > vlof:
        raise ValueError("vmc_m_s must be <= liftoff_speed_m_s")
    steps, maximum = settings.get("steps", 32), settings.get("max_steps", 1024)
    if isinstance(steps, bool) or not isinstance(steps, int) or steps < 2 or steps % 2:
        raise ValueError("field.steps must be an even integer >=2")
    if isinstance(maximum, bool) or not isinstance(maximum, int) or not 2 * steps <= maximum <= 4096:
        raise ValueError("field.max_steps must be >=2*steps and <=4096")
    n = settings.get("v1_search_points", 21)
    if isinstance(n, bool) or not isinstance(n, int) or not 5 <= n <= 101:
        raise ValueError("v1_search_points must be an odd-ish integer in [5,101]")
    if "include_rotation_transition" in settings and not isinstance(settings["include_rotation_transition"], bool):
        raise ValueError("include_rotation_transition must be a boolean")
    if settings.get("include_rotation_transition"):
        # Data required when the option is on — missing → caller reports unassessed (not silent zero air)
        if "rotation_time_s" in settings:
            bounded("rotation_time_s", settings["rotation_time_s"], 0, 10, open_lower=True)
            if settings["rotation_time_s"] > 5:
                raise ValueError("rotation_time_s outside screening domain (0,5] s")
        if "transition_load_factor" in settings:
            bounded("transition_load_factor", settings["transition_load_factor"], 1, 2, open_lower=True)
        if "vr_m_s" in settings and "vmc_m_s" in settings:
            if not (settings.get("vmc_m_s", 0) <= settings["vr_m_s"] <= ground["liftoff_speed_m_s"]):
                raise ValueError("with rotation/transition require vmc ≤ vr ≤ liftoff_speed")


def ground_between(mass_kg: float, v_start: float, v_end: float, rho: float, wing_area_m2: float,
                   cd0: float, k: float, cl_ground: float, mu: float,
                   thrust: Callable[[float], float], *, steps: int = 32, max_steps: int = 1024,
                   braking: bool = False, reverse_factor: float = 0.0) -> dict:
    """Integrate distance/time from v_start to v_end (v_end>=v_start) with signed force.

    Accelerating: F = T - D - mu*max(W-L,0). Braking: F = -D - mu*(W-L) - reverse_factor*T_ref
    with T_ref evaluated at speed (reverse_factor=0 ⇒ no reverse credit).
    Uses the same Simpson-in-sqrt(V) scheme as ground_run when v_start==0 and not braking.
    """
    for key, val in (("mass_kg", mass_kg), ("rho", rho), ("wing_area_m2", wing_area_m2)):
        bounded(key, val, 0, 1e9, open_lower=True)
    for key, val in (("cd0", cd0), ("k", k), ("cl_ground", cl_ground), ("mu", mu), ("reverse_factor", reverse_factor)):
        bounded(key, val, 0, 10)
    if (not braking) and v_end < v_start: raise ValueError("v_end must be >= v_start when accelerating")
    if braking and v_end > v_start: raise ValueError("braking requires v_end <= v_start")
    if v_end == v_start:
        return {"status": "assessed", "distance_m": 0.0, "time_s": 0.0, "v_start_m_s": v_start, "v_end_m_s": v_end,
                "integration_steps": 0, "distance_error_estimate_m": 0.0, "time_error_estimate_s": 0.0}
    if v_start == 0 and not braking and reverse_factor == 0:
        from .performance import ground_run
        out = ground_run(mass_kg, v_end, rho, wing_area_m2, cd0, k, cl_ground, mu, thrust,
                         steps=steps, max_steps=max_steps)
        out.update(v_start_m_s=0.0, v_end_m_s=v_end)
        return out
    weight = mass_kg * G0
    minimum = math.inf
    failed = None

    def force_at(v):
        nonlocal minimum, failed
        qS = .5 * rho * v * v * wing_area_m2
        lift = qS * cl_ground
        drag = qS * (cd0 + k * cl_ground ** 2)
        normal = weight - lift
        t = thrust(v)
        if braking:
            # Retarding force magnitude; distance integrates against deceleration.
            f = drag + mu * max(normal, 0) + reverse_factor * max(t, 0)
            f = -f  # signed acceleration force
        else:
            f = t - drag - mu * max(normal, 0)
        if not math.isfinite(f):
            raise ValueError("nonfinite ground force")
        minimum = min(minimum, f if not braking else -f)
        if (not braking and (normal < -1e-9 * weight or f <= 0)) or (braking and f >= 0):
            failed = {"speed_m_s": v, "net_force_N": f, "wheel_load_N": normal}
        return f

    def integrate(n):
        nonlocal failed
        failed = None
        distance = elapsed = 0.0
        # Map u in [0,1] → V = v_start + (v_end-v_start)*u^2 for accel; linear for brake
        for i in range(n + 1):
            u = i / n
            if braking:
                v = v_start + (v_end - v_start) * u
                dvdu = (v_end - v_start)
            else:
                v = v_start + (v_end - v_start) * u * u
                dvdu = 2 * (v_end - v_start) * u
            f = force_at(v)
            if failed is not None:
                return None
            factor = 1 if i in (0, n) else (4 if i % 2 else 2)
            # ds = V dV / (F/m) ; dt = dV / (F/m)
            distance += factor * mass_kg * v * dvdu / f
            elapsed += factor * mass_kg * dvdu / f
        return distance / (3 * n), elapsed / (3 * n)

    base = {"status": "unassessed", "distance_m": None, "time_s": None, "v_start_m_s": v_start, "v_end_m_s": v_end,
            "integration_steps": 0, "distance_error_estimate_m": None, "time_error_estimate_s": None}
    n, coarse = steps, integrate(steps)
    while coarse is not None and 2 * n <= max_steps:
        fine = integrate(2 * n)
        if fine is None: break
        ds, dt = abs(fine[0] - coarse[0]) / 15, abs(fine[1] - coarse[1]) / 15
        # For braking, distances are negative in the signed integral — take absolute
        d_abs, t_abs = abs(fine[0]), abs(fine[1])
        if ds <= max(.01, 1e-5 * d_abs) and dt <= max(.001, 1e-5 * t_abs):
            return {**base, "status": "assessed", "distance_m": d_abs, "time_s": t_abs,
                    "integration_steps": 2 * n, "distance_error_estimate_m": ds,
                    "time_error_estimate_s": dt, "min_sampled_net_force_N": minimum}
        n, coarse = 2 * n, fine
    return {**base, "status": "infeasible_ground_force" if failed else "integration_not_converged",
            "integration_steps": n, "failed_point": failed, "min_sampled_net_force_N": minimum}



def airborne_rotation_transition(screen_m: float, vlof_m_s: float, climb_gradient: float,
                                 *, vr_m_s: float | None, rotation_time_s: float | None,
                                 transition_load_factor: float | None) -> dict:
    """Screening rotation + circular transition + residual climb to screen height.

    Roskam *Airplane Design* Part I / Torenbeek screening construction:
    * rotation distance s_R = ½ (V_R + V_LOF) · t_R (mean-speed × supplied rotation time);
    * transition radius R = V_LOF² / (g (n − 1)) with transition load factor n > 1;
    * climb angle θ = atan(γ) from the steady V2 gradient γ;
    * height in transition h_tr = R (1 − cos θ); if h_tr < h_screen continue in steady climb.

    Missing V_R, t_R or n → ``status=unassessed`` (never a zero-length airborne that shortens TOD).
    CS-25.111/.113/.115 path compliance remains unassessed at the caller.
    """
    base = {"status": "unassessed", "rotation_distance_m": None, "transition_distance_m": None,
            "climb_distance_m": None, "airborne_distance_m": None, "transition_height_m": None,
            "transition_radius_m": None, "climb_angle_rad": None}
    missing = [name for name, val in (("vr_m_s", vr_m_s), ("rotation_time_s", rotation_time_s),
                                      ("transition_load_factor", transition_load_factor)) if val is None]
    if missing:
        return {**base, "missing": missing,
                "reason": "rotation/transition opted in but " + ", ".join(missing) + " missing — unassessed"}
    if climb_gradient is None or not math.isfinite(climb_gradient) or climb_gradient <= 0:
        return {**base, "reason": "non-positive climb gradient — cannot close airborne path"}
    if not (0 < vr_m_s <= vlof_m_s):
        return {**base, "reason": "require 0 < vr_m_s ≤ vlof_m_s"}
    if transition_load_factor <= 1.0:
        return {**base, "reason": "transition_load_factor must be > 1"}
    theta = math.atan(climb_gradient)
    R = (vlof_m_s ** 2) / (G0 * (transition_load_factor - 1.0))
    h_tr = R * (1.0 - math.cos(theta))
    s_rot = 0.5 * (vr_m_s + vlof_m_s) * rotation_time_s
    if h_tr >= screen_m:
        # screen reached inside the transition arc: θ_scr = acos(1 - h/R)
        c = 1.0 - screen_m / R
        if c < -1.0 or c > 1.0:
            return {**base, "reason": "screen height incompatible with transition radius"}
        theta_s = math.acos(c)
        s_tr = R * math.sin(theta_s)
        s_cl = 0.0
        h_used = screen_m
    else:
        s_tr = R * math.sin(theta)
        s_cl = (screen_m - h_tr) / climb_gradient
        h_used = h_tr
    air = s_rot + s_tr + s_cl
    return {"status": "assessed", "rotation_distance_m": s_rot, "transition_distance_m": s_tr,
            "climb_distance_m": s_cl, "airborne_distance_m": air, "transition_height_m": h_used,
            "transition_radius_m": R, "climb_angle_rad": theta, "screen_height_m": screen_m,
            "rotation_time_s": rotation_time_s, "transition_load_factor": transition_load_factor,
            "vr_m_s": vr_m_s, "vlof_m_s": vlof_m_s, "climb_gradient": climb_gradient,
            "method": "Roskam/Torenbeek: s_R=½(VR+VLOF)t_R; R=V_LOF²/(g(n−1)); residual climb (h−h_tr)/γ",
            "note": "Screening geometry only — not a 25.111/.115 demonstrated path"}


def screen_field(mass_kg: float, aircraft: dict, ground: dict, field: dict, clean_cd0: float) -> dict:
    """Compute ASD, TOD AEO/OEI and optional balanced V1 for a closed mass."""
    validate_field(field, ground)
    engines = aircraft["n_engines"]
    area = aircraft["wing_area_m2"]
    engine_opts = aircraft.get("engine", {})
    g = ground
    rho = isa(g["altitude_m"]).rho
    k = 1 / (math.pi * aircraft["aspect_ratio"] * g["oswald"])
    cd0_roll = clean_cd0 + g["delta_cd_flaps"] + g["delta_cd_gear"]
    cd0_brake = cd0_roll + field.get("delta_cd_spoiler", 0.0)
    vlof = g["liftoff_speed_m_s"]
    v2 = field["v2_m_s"]
    screen = field.get("screen_height_m", SCREEN_M)
    steps, max_steps = field.get("steps", g.get("steps", 32)), field.get("max_steps", g.get("max_steps", 1024))
    reverse = field.get("thrust_reverse_factor", 0.0)
    windmill = field.get("oei_delta_cd_windmilling", 0.003)
    trim = field.get("oei_delta_cd_trim", 0.002)

    def thrust_n(v, count, factor=None):
        fac = g["thrust_factor"] if factor is None else factor
        r = engine_point(v / isa(g["altitude_m"]).a, g["altitude_m"],
                         aircraft["thrust_sl_N"], throttle=fac, **engine_opts)
        if r.get("status") == "unassessed" or r.get("thrust_installed_N") is None:
            raise ValueError("engine map unassessed at field-takeoff speed")
        return count * r["thrust_installed_N"]

    def accel(v0, v1, count, cd0):
        return ground_between(mass_kg, v0, v1, rho, area, cd0, k, g["cl_ground"], g["mu_roll"],
                              lambda v: thrust_n(v, count), steps=steps, max_steps=max_steps)

    def stop_from(v):
        return ground_between(mass_kg, v, 0.0, rho, area, cd0_brake, k, g["cl_ground"], field["mu_brake"],
                              lambda vv: thrust_n(vv, engines), steps=steps, max_steps=max_steps,
                              braking=True, reverse_factor=reverse)

    # Climb polar at V2: gear-up takeoff flaps for AEO TOD; OEI adds windmill+trim
    def climb_grad(count, failed):
        cd0 = clean_cd0 + g["delta_cd_flaps"]  # gear up after liftoff (PRESSUPOSTO)
        # airborne: gear retracted (delta_cd_gear=0), flaps as ground takeoff flaps
        if failed: cd0 += windmill + trim
        from .performance import steady_climb
        return steady_climb(mass_kg, v2, rho, area, cd0,
                            1 / (math.pi * aircraft["aspect_ratio"] * g["oswald"]), g["cl_max"],
                            thrust_n(v2, count))

    issues = []
    unassessed = []
    vmc = field.get("vmc_m_s")
    vr = field.get("vr_m_s")
    use_rt = bool(field.get("include_rotation_transition", False))
    t_rot = field.get("rotation_time_s")
    n_tr = field.get("transition_load_factor")
    if vmc is None:
        unassessed.append("VMC_not_supplied")
        issues.append("vmc_unassessed_v1_floor")
    if vr is None and not use_rt:
        unassessed.append("VR_not_supplied_rotation_transition_unmodeled")
    if use_rt:
        if vr is None or t_rot is None or n_tr is None:
            # will surface per-TOD as unassessed airborne — never invent zero-length RT
            unassessed.append("rotation_transition_inputs_incomplete")
            issues.append("rotation_transition_unassessed_missing_vr_tR_or_n")

    def asd(v1):
        a = accel(0.0, v1, engines, cd0_roll)
        if a["status"] != "assessed":
            return {**a, "asd_m": None, "recognition_distance_m": None, "brake_distance_m": None}
        # recognition: continue at ~V1 for delay with AEO (screening; 25.109 uses continued accel)
        # distance ≈ V1 * delay (constant-speed PRESSUPOSTO during recognition)
        recog = v1 * field["recognition_delay_s"]
        br = stop_from(v1)
        if br["status"] != "assessed":
            return {**br, "accelerate_distance_m": a["distance_m"], "recognition_distance_m": recog,
                    "brake_distance_m": None, "asd_m": None}
        return {"status": "assessed", "accelerate_distance_m": a["distance_m"], "accelerate_time_s": a["time_s"],
                "recognition_distance_m": recog, "recognition_delay_s": field["recognition_delay_s"],
                "brake_distance_m": br["distance_m"], "brake_time_s": br["time_s"],
                "asd_m": a["distance_m"] + recog + br["distance_m"], "v1_m_s": v1}

    def tod_oei(v1):
        a = accel(0.0, v1, engines, cd0_roll)
        if a["status"] != "assessed":
            return {**a, "tod_m": None}
        # With RT: ground OEI continues to VR (then rotation covers VR→VLOF in distance);
        # without RT: ground OEI to VLOF (legacy PR #25).
        v_g_end = vr if (use_rt and vr is not None and vr >= v1) else vlof
        if use_rt and vr is not None and vr < v1:
            return {"status": "unassessed", "reason": "vr_m_s < v1_m_s — rotation model inapplicable",
                    "accelerate_aeo_m": a["distance_m"], "tod_m": None, "v1_m_s": v1}
        b = accel(v1, v_g_end, engines - 1, cd0_roll + windmill + trim)
        if b["status"] != "assessed":
            return {**b, "accelerate_aeo_m": a["distance_m"], "accelerate_oei_m": None, "tod_m": None}
        cl = climb_grad(engines - 1, True)
        if cl["gradient"] is None or cl["gradient"] <= 0:
            return {"status": "insufficient_oei_climb", "accelerate_aeo_m": a["distance_m"],
                    "accelerate_oei_m": b["distance_m"], "climb": cl, "tod_m": None, "v1_m_s": v1}
        if use_rt:
            air = airborne_rotation_transition(screen, vlof, cl["gradient"], vr_m_s=vr,
                                               rotation_time_s=t_rot, transition_load_factor=n_tr)
            if air["status"] != "assessed":
                return {"status": "unassessed", "accelerate_aeo_m": a["distance_m"],
                        "accelerate_oei_m": b["distance_m"], "climb": cl, "airborne": air,
                        "tod_m": None, "v1_m_s": v1, "note": air.get("reason")}
            tod = a["distance_m"] + b["distance_m"] + air["airborne_distance_m"]
            return {"status": "assessed", "accelerate_aeo_m": a["distance_m"], "accelerate_oei_m": b["distance_m"],
                    "airborne": air, "airborne_distance_m": air["airborne_distance_m"], "climb": cl,
                    "tod_m": tod, "v1_m_s": v1,
                    "note": "OEI TOD with opt-in rotation/transition; gear up after liftoff (PRESSUPOSTO)"}
        air = screen / cl["gradient"]
        return {"status": "assessed", "accelerate_aeo_m": a["distance_m"], "accelerate_oei_m": b["distance_m"],
                "airborne_distance_m": air, "climb": cl, "tod_m": a["distance_m"] + b["distance_m"] + air,
                "v1_m_s": v1, "note": "Gear retracted after liftoff (PRESSUPOSTO); no rotation/transition segment"}

    def tod_aeo():
        v_g_end = vr if (use_rt and vr is not None) else vlof
        a = accel(0.0, v_g_end, engines, cd0_roll)
        if a["status"] != "assessed":
            return {**a, "tod_m": None, "tod_115pct_m": None}
        cl = climb_grad(engines, False)
        if cl["gradient"] is None or cl["gradient"] <= 0:
            return {"status": "insufficient_aeo_climb", "ground_run_m": a["distance_m"], "climb": cl,
                    "tod_m": None, "tod_115pct_m": None}
        if use_rt:
            air = airborne_rotation_transition(screen, vlof, cl["gradient"], vr_m_s=vr,
                                               rotation_time_s=t_rot, transition_load_factor=n_tr)
            if air["status"] != "assessed":
                return {"status": "unassessed", "ground_run_m": a["distance_m"], "climb": cl,
                        "airborne": air, "tod_m": None, "tod_115pct_m": None, "note": air.get("reason")}
            tod = a["distance_m"] + air["airborne_distance_m"]
            return {"status": "assessed", "ground_run_m": a["distance_m"], "ground_run_time_s": a["time_s"],
                    "airborne": air, "airborne_distance_m": air["airborne_distance_m"], "climb": cl,
                    "tod_m": tod, "tod_115pct_m": 1.15 * tod,
                    "note": "AEO TOD with opt-in rotation/transition; 25.113(a)(2) 115% numerical only; compliance unassessed"}
        air = screen / cl["gradient"]
        tod = a["distance_m"] + air
        return {"status": "assessed", "ground_run_m": a["distance_m"], "ground_run_time_s": a["time_s"],
                "airborne_distance_m": air, "climb": cl, "tod_m": tod, "tod_115pct_m": 1.15 * tod,
                "note": "25.113(a)(2) 115% AEO factor applied numerically only; compliance unassessed"}

    aeo = tod_aeo()
    # V1 selection
    v1_user = field.get("v1_m_s")
    v_lo = vmc if vmc is not None else 0.5 * vlof  # if no VMC, search still runs but floor flagged
    history = []
    balanced = None
    if v1_user is not None:
        v1 = v1_user
        if vmc is not None and v1 < vmc:
            issues.append("v1_below_vmc")
        asd_r, tod_r = asd(v1), tod_oei(v1)
        balanced = {"status": "user_v1", "v1_m_s": v1, "asd": asd_r, "tod_oei": tod_r,
                    "field_length_m": None if asd_r.get("asd_m") is None or tod_r.get("tod_m") is None
                    else max(asd_r["asd_m"], tod_r["tod_m"], aeo.get("tod_115pct_m") or 0)}
    else:
        n = field.get("v1_search_points", 21)
        best = None
        for i in range(n):
            v1 = v_lo + (vlof - v_lo) * i / (n - 1)
            asd_r, tod_r = asd(v1), tod_oei(v1)
            row = {"v1_m_s": v1, "asd_m": asd_r.get("asd_m"), "tod_oei_m": tod_r.get("tod_m"),
                   "asd_status": asd_r["status"], "tod_status": tod_r["status"]}
            history.append(row)
            if asd_r.get("asd_m") is None or tod_r.get("tod_m") is None:
                continue
            gap = asd_r["asd_m"] - tod_r["tod_m"]
            row["gap_m"] = gap
            if best is None or abs(gap) < abs(best["gap_m"]):
                best = dict(row, asd=asd_r, tod_oei=tod_r)
        if best is None:
            balanced = {"status": "no_feasible_v1", "history": history, "v1_m_s": None, "field_length_m": None}
            issues.append("balanced_field_no_feasible_v1")
        else:
            # refine by linear interpolation between neighbours if sign change
            bal_v1 = best["v1_m_s"]
            for a, b in zip(history, history[1:]):
                if a.get("gap_m") is None or b.get("gap_m") is None: continue
                if a["gap_m"] == 0:
                    bal_v1 = a["v1_m_s"]; break
                if a["gap_m"] * b["gap_m"] < 0:
                    w = abs(a["gap_m"]) / (abs(a["gap_m"]) + abs(b["gap_m"]))
                    bal_v1 = a["v1_m_s"] + w * (b["v1_m_s"] - a["v1_m_s"])
                    break
            asd_r, tod_r = asd(bal_v1), tod_oei(bal_v1)
            fl = None
            if asd_r.get("asd_m") is not None and tod_r.get("tod_m") is not None:
                fl = max(asd_r["asd_m"], tod_r["tod_m"])
                if aeo.get("tod_115pct_m") is not None:
                    fl = max(fl, aeo["tod_115pct_m"])
            balanced = {"status": "balanced" if asd_r.get("asd_m") and tod_r.get("tod_m") and
                        abs(asd_r["asd_m"] - tod_r["tod_m"]) <= max(5.0, 0.01 * fl) else "nearest_v1",
                        "v1_m_s": bal_v1, "asd": asd_r, "tod_oei": tod_r, "field_length_m": fl,
                        "gap_m": None if asd_r.get("asd_m") is None or tod_r.get("tod_m") is None
                        else asd_r["asd_m"] - tod_r["tod_m"],
                        "history": history,
                        "vmc_floor_m_s": vmc, "vmc_floor_status": "applied" if vmc is not None else "unassessed"}

    checks = []
    def check(name, passed, margin=None, units=None):
        checks.append({"name": name, "passed": passed, "margin": margin, "units": units,
                       "scope": "engineering screen, not certification"})

    check("field_tod_aeo", aeo["status"] == "assessed")
    if use_rt:
        rt_ok = aeo.get("status") == "assessed" and (aeo.get("airborne") or {}).get("status") == "assessed"
        check("field_rotation_transition", True if rt_ok else None)
    if balanced and balanced.get("asd"):
        check("field_asd", balanced["asd"]["status"] == "assessed")
        check("field_tod_oei", balanced["tod_oei"]["status"] == "assessed")
    check("field_vmc_floor", None if vmc is None else True)
    fl = (balanced or {}).get("field_length_m")
    if "max_field_length_m" in field:
        check("field_length_limit", None if fl is None else fl <= field["max_field_length_m"],
              None if fl is None else field["max_field_length_m"] - fl, "m")

    # Regulatory references: numerical only
    regulatory = {
        "25.109_accelerate_stop": {"passed": None, "status": "unassessed",
                                  "reason": "ASD computed as screening distances; wet runway, demonstrated distances, reverse-thrust credit rules unassessed"},
        "25.113_takeoff_distance": {"passed": None, "status": "unassessed",
                                   "reason": "TOD AEO 115% and OEI TOD are numerical only; path 25.111 and configuration schedule unassessed"},
        "source_url": "https://www.law.cornell.edu/cfr/text/14/25.113",
        "retrieved": "2026-11-09",
    }

    return {"status": "screened", "schema_version": "1.0", "mass_kg": mass_kg,
            "screen_height_m": screen, "vlof_m_s": vlof, "v2_m_s": v2, "vmc_m_s": vmc, "vr_m_s": vr,
            "tod_aeo": aeo, "balanced_field": balanced, "checks": checks,
            "requested_checks_passed": all(c["passed"] is True for c in checks),
            "issues": issues + [c["name"] for c in checks if c["passed"] is not True],
            "include_rotation_transition": use_rt,
            "unassessed": unassessed + (
                ["rotation_transition_segment"] if (not use_rt or aeo.get("status") != "assessed"
                                                    or (use_rt and (aeo.get("airborne") or {}).get("status") != "assessed"))
                else []
            ) + ["hot_day_slope_wind_ground_effect", "VMCG_flight_test", "wet_runway_CS25", "CS-25_compliance"],
            "regulatory_compliance": "unassessed", "regulatory_references": regulatory,
            "citations": CITATIONS,
            "assumptions": [{"path": "performance.field", "value": deepcopy(field), "source": field["source"]},
                            {"path": "field_model",
                             "value": "ISA still-air level runway; gear up after liftoff; recognition≈V·Δt; "
                                      "no reverse unless thrust_reverse_factor>0; M<=0.3",
                             "source": "PRESSUPOSTO L0 screening"}],
            "method": ("Ground Simpson + opt-in Roskam/Torenbeek rotation/transition + V2 climb; "
                       "BFL by V1 search (ASD vs TOD_OEI)" if use_rt else
                       "Ground Simpson integration + steady V2 climb gradient; BFL by V1 search (ASD vs TOD_OEI)"),
            "validity": "Engineering screen only — not a certified takeoff path, AFM distance or CS-25 finding."}
