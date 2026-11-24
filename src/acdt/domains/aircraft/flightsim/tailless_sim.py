# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""6-DOF hook of the tailless split-aileron flying wing (10 nov 2026).

The fixed-type flight model (:func:`.aeromodel.build_flight_model`) is built from the parametric geometry with a
fin and a rudder; a tailless assembly has neither. Here the tabulated :class:`.aeromodel.FlightModel` is built
from the **assembly** instead (AVL α sweep with the elevon as elevator — symmetric — and as aileron —
antisymmetric —, :func:`..assembly.tailless.avl_elevon_point`) and the rudder channel carries the split-aileron
yaw moment directly: C_nδr = 1, C_Yδr = C_lδr = 0 (Löchert et al. 2019: ΔC_Y, ΔC_l ≈ 0 in attached flow) and the
profile drag ΔC_D = (b/ȳ_f)·|ΔC_n| (McCormick 1995 Eq. 3.45, :mod:`..assembly.tailless`). The same tables are
exported to JSBSim (separate process, LGPL) with a ``D_drag_rudder`` drag function.

:func:`lateral_test` flies the in-house 6-DOF (:mod:`.sixdof`) trimmed in cruise and applies the 14 CFR 23.443
lateral 1−cos gust, bare airframe vs SAS through the split-aileron actuator model (delay, lag, rate limit,
sin² law, :class:`..assembly.tailless_actuation.SplitActuator`), with elevon bank hold (Beard & McLain 2012
Sec. 6.3.1) and elevator/throttle held at trim. The mission autopilot (:mod:`.autopilot`) closes a rudder
sideslip loop through C_Yδr, which a drag rudder does not have → the 6-DOF *mission* of a tailless design is
not flown (reported as not implemented).

PRESSUPOSTOS: C_Lα̇ = C_mα̇ = 0 (no tail), polar C_D0/K of the sizing, inertias per loading case from the
assembly, split-aileron ΔC_m from the drag off the CG height neglected in the 6-DOF.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from acdt import G0
from acdt.core.atmosphere import isa

from .aeromodel import TABLE_KEYS, AeroModel, FlightModel, MassModel, Propulsion, _prop_per_engine


def tailless_spec(res) -> dict | None:
    """The assembly spec of ``res`` (rescaled one in the W0 loop) when it uses ``yaw_control: split_aileron``."""
    from ..assembly import tailless as T
    a = res.spec.assumptions.get("assembly") if isinstance(res.spec.assumptions, dict) else None
    if not a or not getattr(res, "assembly", None):
        return None
    lp = getattr(res, "assembly_loop", None)
    if lp and isinstance(lp.get("spec_scaled"), dict):
        spec = lp["spec_scaled"]
    else:
        from ..assembly.loop import load_spec
        spec = load_spec(res.spec, a)
    return spec if T.options(spec) is not None else None


def pick_case(res, tl: dict) -> str | None:
    """Loading case whose cruise trims within the elevon limit (smallest |δe|), from the approach-consistency
    assessment; None when no case trims."""
    cases = ((tl or {}).get("approach_consistency") or {}).get("cases") or {}
    ok = [(abs(v["cruise"]["elevon_deg"]), k) for k, v in cases.items() if (v.get("cruise") or {}).get("ok")]
    return min(ok)[1] if ok else None


def trimmable_cases(tl: dict) -> list:
    """Loading cases whose cruise trims within the elevon limit (approach-consistency assessment)."""
    cases = ((tl or {}).get("approach_consistency") or {}).get("cases") or {}
    return [k for k, v in cases.items() if (v.get("cruise") or {}).get("ok")]


WASHOUT_S = 4.2
WASHOUT_SOURCE = ("MIT 16.333 Aircraft Stability and Control (How, 2004), Lecture 12 'Aircraft Lateral Autopilots': "
                  "amortecedor de guinada com washout H_w = τs/(τs + 1), τ = 4,2 s, para não contrariar a viragem "
                  "estabilizada (PRESSUPOSTO para este UAV)")


def _assembly_gear(asm, out, cs: dict, w) -> dict:
    """Gear of the assembly (``gear_layout``) for the 6-DOF ground model, plus wing-tip bumpers (tip strike)."""
    g = out.gear or {}
    if g.get("type") != "tricycle" or g.get("x_main") is None:
        return {"kind": "none", "h_cg": 0.3, "note": "sem trem triciclo na montagem"}
    x_cg, z_cg = float(cs["cg"][0]), float(cs["cg"][2])
    zg = float(g["ground_z"])
    half = g.get("half_track") or g.get("half_track_min")
    V, _ = w.mesh()
    ymax = float(np.max(np.abs(V[:, 1])))
    tip = V[np.abs(V[:, 1]) >= 0.98 * ymax]
    k = int(np.argmin(tip[:, 2]))
    xt, zt = float(tip[k, 0]), float(tip[k, 2])
    bump = [{"name": f"tip_{s}", "r_body": [-(xt - x_cg), sgn * ymax, -(zt - z_cg)]} for s, sgn in (("L", -1), ("R", 1))]
    fc = g.get("rotation_first_contact")
    if fc:   # first aft point to touch in rotation (propeller / trailing edge): strike detector
        bump.append({"name": "aft_strike", "r_body": [-(float(fc[0]) - x_cg), float(fc[1]), -(float(fc[2]) - z_cg)]})
    thg = float(g.get("ground_attitude_deg") or 0.0)
    out_g = {"kind": "tricycle", "x_main": float(g["x_main"]), "x_nose": g.get("x_nose"), "h_cg": z_cg - zg,
             "track": 2 * float(half), "track_source": ("half_track da montagem" if g.get("half_track") else
                                                         "meia-via mínima de capotamento (Raymer Cap. 11, 63°) — PRESSUPOSTO"),
             "bumpers": bump, "tip_clearance_angle_deg": math.degrees(math.atan2(zt - zg, ymax)),
             # Torenbeek 1982 / CS 25.149 basis: angle from the main wheel to the lowest tip point (≥ 5°)
             "tip_clearance_angle_about_wheel_deg": math.degrees(math.atan2(zt - zg, ymax - float(half)))}
    if thg:
        xm = float(g["x_main"])
        t_ = math.radians(thg)
        zt_s = (zt - zg) * math.cos(t_) - (xt - xm) * math.sin(t_)   # tip height in the nose-up static attitude
        out_g["tip_clearance_angle_about_wheel_static_deg"] = math.degrees(math.atan2(zt_s, ymax - float(half)))
        out_g.update({"ground_attitude_deg": thg, "nose_extension_m": float(g.get("nose_strut_extension_m") or 0.0),
                      "h_cg_static": (z_cg - zg) * math.cos(math.radians(thg))
                      + (xm - x_cg) * math.sin(math.radians(thg))})
    if g.get("side_load_factor"):   # legs designed to k × 23.485 (gear.side_load_factor, opt-in)
        out_g["side_load_factor"] = float(g["side_load_factor"])
    # Designed tip skids (Raymer Ch. 11 / Currey energy): contact is a sized event, not a structural strike.
    sk = g.get("tip_skids")
    if sk and sk.get("status") == "assessed":
        out_g["tip_skids"] = sk
        for bp in bump:
            if str(bp.get("name", "")).startswith("tip_"):
                bp["kind"] = "skid"
    return out_g


def build_tailless_flight_model(res, spec: dict, tl: dict, case: str,
                                alphas=(-4.0, 0.0, 4.0, 8.0, 12.0, 16.0), fuel_kg: float = 0.0) -> FlightModel:
    from ..assembly import tailless as T
    from ..assembly.assembly import Assembly
    from ..assembly.handling import body_cnb, inertias
    from ..assembly.sizing import main_wing
    from ..performance import PerfModel
    fw = T.options(spec)
    el = fw["elevon"]
    asm = Assembly.from_dict(spec["assembly"])
    wsurf, gw = main_wing(asm)
    S, b, c = gw["S"], gw["b"], gw["mac"]
    out = res.assembly["result"]
    cs = out.loading["cases"][case]
    m, x_cg, z_cg = float(cs["mass_kg"]), float(cs["cg"][0]), float(cs["cg"][2])
    at = isa(res.cruise_altitude)
    mach = res.cruise_speed / at.a
    cnb_body, _ = body_cnb(asm, S, b)
    tabs = {k: [[0.0] * len(alphas)] for k in TABLE_KEYS}
    sgn_a = None
    for j, al in enumerate(alphas):
        d = T.avl_elevon_point(asm, mach, x_cg, z_cg, el, alpha_deg=al)
        if sgn_a is None:   # δa > 0 rolls right (C_lδa > 0), acdt convention
            sgn_a = -1.0 if d["Clda"] < 0 else 1.0
        vals = {"CL": d["CL"], "Cm": d["Cm"], "CLa": d["CLa"], "Cma": d["Cma"], "CYb": d["CYb"], "Clb": d["Clb"],
                "Cnb": d["Cnb"] + cnb_body, "CLq": d["CLq"], "Cmq": d["Cmq"], "CYp": d["CYp"], "Clp": d["Clp"],
                "Cnp": d["Cnp"], "CYr": d["CYr"], "Clr": d["Clr"], "Cnr": d["Cnr"], "CLde": d["CLde"],
                "Cmde": d["Cmde"], "CYda": sgn_a * d["CYda"], "Clda": sgn_a * d["Clda"], "Cnda": sgn_a * d["Cnda"],
                "CYdr": 0.0, "Cldr": 0.0, "Cndr": 1.0}
        for k in TABLE_KEYS:
            tabs[k][0][j] = float(vals[k])
    sa = tl.get("split_aileron") or {}
    cap = sa.get("capacity_dCn")
    hl = res.highlift
    npd = out.np or {}
    dx_fus = ((npd.get("x_np_torenbeek", npd.get("x_np_no_bodies", 0.0)) - npd.get("x_np_no_bodies", 0.0)) / c
              if npd.get("x_np_no_bodies") is not None else 0.0)
    el_max = float(el.get("max_deg") or T.ELEVON_MAX_DEFAULT_DEG)
    aero = AeroModel(S=S, b=b, c=c, x_ref=x_cg, alpha_deg=list(alphas), flap_deg=[0.0], tables=tabs,
                     CLmax=[hl.CLmax_clean], CD0=res.polar.CD0, K=res.polar.K, flap_dCD0=[0.0], CLad=0.0, Cmad=0.0,
                     dx_fus=dx_fus,
                     limits={"elevator": el_max, "aileron": el_max, "rudder": math.degrees(cap) if cap else 0.0,
                             "flap": 0.0},
                     yaw_drag_per_Cn=(b / sa["y_bar"]) if sa.get("y_bar") else 0.0,
                     notes=[f"montagem sem deriva (AVL, elevon simétrica/antissimétrica, {len(alphas)} casos); canal "
                            "do leme = ΔC_n do split aileron (C_nδr = 1), ΔC_D = (b/ȳ_f)|ΔC_n|",
                            f"C_nβ dos corpos {cnb_body:+.4f}; dx_fus {dx_fus:+.4f} (Torenbeek, montagem)",
                            "C_Lα̇ = C_mα̇ = 0 (sem cauda) — PRESSUPOSTO; polar C_D0/K do dimensionamento"])
    pm = PerfModel.from_result(res)
    I = inertias(asm, out, case)
    mass = MassModel(m=m, x_cg=x_cg, Ixx=I["Ixx"], Iyy=I["Iyy"], Izz=I["Izz"], Ixz=0.0, fuel_kg=fuel_kg, battery_J=0.0,
                     gear=_assembly_gear(asm, out, cs, wsurf))
    sas = tl.get("sas") or {}
    dyn = tl.get("actuator_dynamics") or {}
    if sas.get("status") == "ok" and sa.get("C1") and cap:
        from ..assembly import tailless_actuation as TX
        aero.yaw_sas = {"k_beta": sas["k_beta"], "k_r": sas["k_r"], "washout_s": WASHOUT_S,
                        "washout_source": WASHOUT_SOURCE, "C1": sa["C1"], "delta_max_deg": sa["delta_max_deg"],
                        "rate_max_deg_s": (tl.get("actuators") or {}).get("rate_max_effective_deg_s")
                        or sa.get("rate_max_deg_s"),
                        "lag_s": dyn.get("lag_s", 0.0) or 0.0,
                        "delay_s": dyn.get("delay_s", TX.TIME_DELAY_LIMITS_S[0]),
                        "bias_deg": float((tl.get("lateral_gust") or {}).get("bias_deg") or 0.0),
                        "e_psi_max_deg": 20.0, "ki_frac": 0.5, "dt": 0.02}
    rho0 = isa(0.0).rho
    Vto = 1.1 * math.sqrt(2 * m * G0 / (rho0 * S * pm.CLmax_to))
    pd = res.spec.assumptions["propulsion"]
    n_eng = int(pd.get("n_engines", 1))
    prop = Propulsion(kind=pm.kind, P_sl=pm.P_sl, T_sl=pm.T_sl, eta_cruise=pm.eta_cruise, eta_takeoff=pm.eta_takeoff,
                      V_low=0.7 * Vto, c_p=pm.c_p, c_t=pm.c_t,
                      eta_chain=(pm.eta_tot / pm.eta_cruise) if pm.eta_tot else 1.0, P_sys=pm.P_sys or 0.0,
                      n_engines=n_eng, z_thrust=0.0, prop=_prop_per_engine(pm, n_eng))
    notes = [f"caso de massa '{case}' ({m:.1f} kg, x_cg {x_cg:.3f} m); inércias da montagem nesse caso "
             "(soma de componentes, Roskam Part V Ch. 10), I_xz = 0 (PRESSUPOSTO); massa constante no ensaio lateral"]
    return FlightModel(aero, prop, mass, notes)


def lateral_test(fm: FlightModel, tl: dict, V: float, h: float, T: float = 12.0, dt: float = 0.005) -> dict:
    """Trim in cruise, then the 14 CFR 23.443 lateral 1−cos gust: bare vs SAS (actuator model) — in-house 6-DOF."""
    from ..assembly import tailless_actuation as TX
    from .sixdof import Controls, SixDOF, euler_from_quat, trim
    sa = tl.get("split_aileron") or {}
    sas = tl.get("sas") or {}
    g = tl.get("lateral_gust") or {}
    dyn = tl.get("actuator_dynamics") or {}
    act_rate = (tl.get("actuators") or {}).get("rate_max_effective_deg_s") or sa.get("rate_max_deg_s")
    vg = g.get("v_peak_TAS_m_s")
    L = g.get("gust_length_m")
    a = fm.aero
    sim0 = SixDOF(fm)
    tr = trim(sim0, V, h)
    out = {"trim": {k: tr[k] for k in ("alpha_deg", "delta_e_deg", "throttle", "residual", "ok")},
           "elevator_within_limit": abs(tr["delta_e_deg"]) <= a.limits["elevator"] + 1e-9}
    if vg is None or L is None:
        out["status"] = "unassessed"
        return out
    Tg = L / V

    def wind(t, pos):  # lateral gust from the right (east, heading north): +y NED
        v = 0.5 * vg * (1 - math.cos(2 * math.pi * t / Tg)) if 0.0 <= t - 1.0 <= Tg else 0.0
        return np.array([0.0, v, 0.0])

    da_max = math.radians(a.limits["aileron"])
    t0 = sim0._tab(math.radians(tr["alpha_deg"]), 0.0)
    from .sixdof import IDX
    qS = 0.5 * isa(h).rho * V**2 * a.S
    Lp = qS * a.b * t0[IDX["Clp"]] * a.b / (2 * V) / fm.mass.Ixx
    Lda = qS * a.b * t0[IDX["Clda"]] / fm.mass.Ixx
    kp, kd, _ = TX.bank_hold_gains(Lp, Lda, da_max)

    def run(with_sas: bool, rate=act_rate):
        sim = SixDOF(fm, wind=wind)
        x = tr["x"].copy()
        c0 = tr["controls"]
        act = None
        if with_sas and sas.get("status") == "ok" and sa.get("C1"):
            act = TX.SplitActuator(sa["C1"], sa["delta_max_deg"], rate, dyn.get("lag_s", 0.0),
                                   dyn.get("delay_s", TX.TIME_DELAY_LIMITS_S[0]), dt,
                                   bias_deg=float((tl.get("lateral_gust") or {}).get("bias_deg") or 0.0))
        t = 0.0
        pk = {"beta_deg": 0.0, "phi_deg": 0.0, "r_deg_s": 0.0, "dCn": 0.0, "split_deg": 0.0, "elevon_deg": 0.0}
        hist = []
        while t <= T + 1e-9:
            info = {}
            sim.derivatives(t, x, Controls(de=c0.de, throttle=c0.throttle), info)
            ph, th, _ = euler_from_quat(x[6:10])
            p, r = x[10], x[12]
            da = max(-da_max, min(da_max, -(kp * ph + kd * p)))
            dn = 0.0
            if act is not None:
                u = sas["k_beta"] * info["beta"] - sas["k_r"] * r * a.b / (2 * info["Va"])
                dn = act.step(u)
            c = Controls(de=c0.de, da=da, dr=dn, throttle=c0.throttle)
            for k_, v_ in (("beta_deg", math.degrees(info["beta"])), ("phi_deg", math.degrees(ph)),
                           ("r_deg_s", math.degrees(r)), ("dCn", dn),
                           ("split_deg", math.degrees(act.s) if act else 0.0), ("elevon_deg", math.degrees(da))):
                pk[k_] = max(pk[k_], abs(v_))
            hist.append((t, math.degrees(info["beta"])))
            x = sim.step(t, x, c, dt)
            t += dt
        tail = [abs(bv) for tt, bv in hist if tt >= 0.75 * T]
        r = {"peak": pk, "final_beta_amp_deg": max(tail) if tail else None, "V_end_m_s": float(np.linalg.norm(x[3:6]))}
        if act is not None:
            r["actuator"] = {"saturated": act.sat, "rate_limited": act.rate_lim,
                             "rate_limited_fraction": act.n_lim / max(act.n_steps, 1),
                             "peak_rate_deg_s": math.degrees(act.peak_rate)}
        return r
    out["bare"] = run(False)
    out["sas"] = run(True)
    out["gust"] = {"v_peak_TAS_m_s": vg, "length_m": L, "t_start_s": 1.0}
    out["bank_hold"] = {"kp_phi": kp, "kd_phi": kd, "source": "Beard & McLain 2012 Sec. 6.3.1"}
    b_end, s_end = out["bare"]["final_beta_amp_deg"], out["sas"]["final_beta_amp_deg"]
    out["sas_damps_better"] = (s_end is not None and b_end is not None and s_end < b_end)
    out["gust_verdict"] = gust_verdict_6dof(out["sas"], act_rate, lambda: run(True, rate=None))
    out["status"] = "assessed"
    return out


GUST_6DOF_CRITERION = ("o mesmo critério estrito de hq:lateral_gust (14 CFR 23.443/23.333(c) pré-Amdt 64, rajada "
                       "1−cos): sem saturação, sem limite de taxa e β amortecido (≤ 10 % do pico no último quarto); "
                       "não se encontrou norma citável que admita saturação de taxa breve")


def gust_verdict_6dof(r_sas: dict, rate_avail_deg_s, run_unlimited) -> dict:
    """Strict verdict of the 6-DOF lateral gust with the SAS (same criterion as ``hq:lateral_gust``). When the
    servo rate limit is touched, the gust is re-flown with an unlimited rate and its peak surface rate is the
    rate the strict criterion requires (``rate_required_deg_s``) — reported, nothing is changed in the design."""
    a = r_sas.get("actuator")
    if not a:
        return {"status": "unassessed", "ok": None, "issue": "sem SAS/atuador no ensaio 6-DOF",
                "criterion": GUST_6DOF_CRITERION}
    pk = (r_sas.get("peak") or {}).get("beta_deg") or 0.0
    fin = r_sas.get("final_beta_amp_deg")
    settled = fin is not None and fin <= 0.1 * max(pk, 1e-6)
    v = {"status": "assessed", "criterion": GUST_6DOF_CRITERION, "settled": bool(settled),
         "saturated": bool(a.get("saturated")), "rate_limited": bool(a.get("rate_limited")),
         "rate_limited_fraction": a.get("rate_limited_fraction"), "peak_rate_deg_s": a.get("peak_rate_deg_s"),
         "rate_available_deg_s": rate_avail_deg_s}
    v["ok"] = bool(settled and not v["saturated"] and not v["rate_limited"])
    if v["rate_limited"]:
        ru = (run_unlimited() or {}).get("actuator") or {}
        v["rate_required_deg_s"] = ru.get("peak_rate_deg_s")
        v["unlimited_rate_saturated"] = ru.get("saturated")
        if rate_avail_deg_s and v["rate_required_deg_s"]:
            v["rate_factor_required"] = v["rate_required_deg_s"] / float(rate_avail_deg_s)
        v["issue"] = (f"limite de taxa tocado em {100 * (v['rate_limited_fraction'] or 0):.2f} % do tempo; sem limite o "
                      f"pico seria {v['rate_required_deg_s'] or float('nan'):.0f} °/s contra "
                      f"{rate_avail_deg_s or float('nan'):.0f} °/s disponíveis na superfície — falha pelo critério estrito")
    elif not v["ok"]:
        v["issue"] = "saturação ou β não amortecido no último quarto"
    return v


def bare_modes(fm: FlightModel, V: float, h: float) -> dict:
    """Eigenvalues of the in-house 6-DOF linearised (finite differences) at the cruise trim: unstable roots and
    their time to double (ln 2 / σ)."""
    from .sixdof import SixDOF, trim
    sim = SixDOF(fm)
    tr = trim(sim, V, h)
    x0, c = tr["x"], tr["controls"]
    n = 13
    f0 = sim.derivatives(0.0, x0, c)[:n]
    J = np.zeros((n, n))
    for i in range(3, n):
        x = x0.copy()
        x[i] += 1e-6
        J[:, i] = (sim.derivatives(0.0, x, c)[:n] - f0) / 1e-6
    ev = np.linalg.eigvals(J[3:n, 3:n])
    ev = [complex(z) for z in ev if abs(z) > 1e-4]
    uns = sorted([z for z in ev if z.real > 1e-4 and z.imag >= 0], key=lambda z: -z.real)
    return {"eigenvalues": [[z.real, z.imag] for z in sorted(ev, key=lambda z: -z.real)],
            "unstable": [{"sigma": z.real, "omega": z.imag, "t_double_s": math.log(2) / z.real} for z in uns],
            "alpha_trim_deg": tr["alpha_deg"]}


JSBSIM_DOUBLET_FRACTION = 0.03   # of the split capacity ΔC_n: keeps |β| ≲ 2–3° (linear AVL tables)


def jsbsim_crosscheck(fm: FlightModel, tl: dict, V: float, h: float, work_dir, T: float = 8.0, plot=None) -> dict:
    """Open-loop ΔC_n doublet (0.5 s + 0.5 s) in JSBSim (separate process) and in the in-house 6-DOF, same tables.

    11 nov 2026 — the earlier check used 30 % of the split capacity: the bare airframe departed (|β| 40–80°,
    p ≈ 1000 °/s) far outside the linear AVL tables, so the two integrators were compared on a tumbling
    trajectory. The doublet is now 3 % of the capacity (linear regime). The bare tailless airframe can be
    directionally divergent (C_nβ < 0 at the trim α), so a residual difference grows with time; it is put in
    context by the in-house model's own sensitivity: the same 6-DOF re-trimmed at the JSBSim trim α (mass scaled
    so that ΔC_L = C_Lα Δα) and compared with itself (``self_sensitivity_nrms``)."""
    from .jsbsim_runner import compare_with_jsbsim
    from .sixdof import IDX, Controls, SixDOF, trim
    cap = float((tl.get("split_aileron") or {}).get("capacity_dCn") or 0.01)
    k = JSBSIM_DOUBLET_FRACTION * cap
    inputs = [{"t0": 0.5, "t1": 1.0, "dr": k}, {"t0": 1.0, "t1": 1.5, "dr": -k}]
    c = compare_with_jsbsim(fm, V, h, inputs=inputs, T=T, work_dir=work_dir, plot=plot)
    keys = ("beta", "p", "r", "phi", "V")
    out = {"input": f"doublet de ΔC_n ±{k:.5f} ({JSBSIM_DOUBLET_FRACTION:.0%} da capacidade do split), 0,5 s + 0,5 s, "
                    f"malha aberta, {T:.0f} s",
           "nrms": {kk: c["errors"][kk]["nrms"] for kk in keys},
           "range": {kk: c["errors"][kk]["range"] for kk in keys},
           "trim_ours": c["trim_ours"], "trim_jsbsim": c["trim_jsbsim"], "plot": c.get("plot")}
    # own sensitivity to the trim-α offset between the two integrators
    dal = math.radians(c["trim_jsbsim"]["alpha_deg"] - c["trim_ours"]["alpha_deg"])
    sim = SixDOF(fm)
    t0 = sim._tab(math.radians(c["trim_ours"]["alpha_deg"]), 0.0)
    CL, CLa = t0[IDX["CL"]], t0[IDX["CLa"]]

    def beta_run(model):
        s_ = SixDOF(model)
        tr = trim(s_, V, h)
        x, c0, t, bs = tr["x"].copy(), tr["controls"], 0.0, []
        while t <= T + 1e-9:
            dr = sum(i["dr"] for i in inputs if i["t0"] <= t < i["t1"])
            cc = Controls(de=c0.de, dr=dr, throttle=c0.throttle)
            info = {}
            s_.derivatives(t, x, cc, info)
            bs.append(info["beta"])
            x = s_.step(t, x, cc, 0.01)
            t += 0.01
        return np.array(bs)
    if CL > 0 and abs(dal) > 0:
        import copy as _copy
        fm2 = _copy.deepcopy(fm)
        fm2.mass.m *= 1.0 + CLa * dal / CL
        b1, b2 = beta_run(fm), beta_run(fm2)
        out["self_sensitivity_nrms_beta"] = float(np.sqrt(np.mean((b1 - b2) ** 2)) / max(np.ptp(b1), 1e-12))
        out["trim_alpha_offset_deg"] = math.degrees(dal)
    out["bare_modes"] = bare_modes(fm, V, h)
    return out


def tailless_mission(res, spec: dict, tl: dict, mission, out_dir, log=print) -> dict:
    """6-DOF mission of a tailless split-aileron design (11 nov 2026): flight model of the 'cheio' (MTOW) case with
    the sizing fuel burnable (the useful load sits on the empty CG, so the CG does not move — ``useful_load_at``),
    the assembly's tricycle gear and wing-tip bumpers, and the mission autopilot's yaw channel through the split
    aileron: yaw SAS k_β β − k_r r̂ with washout (MIT 16.333 L12) via the split actuator model; decrab in the flare
    by a heading loop on the same channel; touchdown side loads vs 14 CFR 23.485."""
    from .mission import simulate_mission_6dof
    cases = (((tl.get("approach_consistency") or {}).get("cases")) or {})
    case = "cheio" if "cheio" in cases else pick_case(res, tl)
    if case is None:
        return {"status": "unassessed", "issues": ["nenhum caso de massa equilibra — missão não corrida"]}
    fuel = float(res.sizing.Wf) if case == "cheio" else 0.0
    fm = build_tailless_flight_model(res, spec, tl, case, fuel_kg=fuel)
    if not fm.aero.yaw_sas:
        return {"status": "unassessed", "case": case,
                "issues": ["SAS de guinada sem estado 'ok' ou split sem C₁/capacidade — canal de guinada indefinido"]}
    log(f"missão 6-DOF da asa sem deriva (caso '{case}', guinada pelo split aileron)…")
    r = simulate_mission_6dof(fm, mission, res=res, out_dir=Path(out_dir) / "mission")
    r["case"] = case
    r["yaw_channel"] = {k: v for k, v in fm.aero.yaw_sas.items() if k != "dt"}
    r["gear"] = {k: v for k, v in (fm.mass.gear or {}).items() if k != "bumpers"}
    r["status"] = "assessed" if not r.get("aborted") else "aborted"
    td = None
    for s in r.get("segments") or []:
        if s.get("type") == "landing" and s.get("touchdown"):
            td = s["touchdown"]
            break
    if td:
        from .sixdof import friction_sensitivity, GroundModel
        gm = GroundModel.from_model(fm)
        r["friction_sensitivity"] = friction_sensitivity(
            td, mu_side_nom=gm.mu_side, v_eps=gm.v_eps, mu_brake_nom=gm.mu_brake)
    return r


def tailless_simulation_study(res, out_dir, *, jsbsim_check: bool = False, log=print, mission=None) -> dict:
    """`acdt simulate --fidelity 6dof` for a tailless split-aileron design: flight model from the assembly, lateral
    gust test (bare vs SAS), optional JSBSim cross-check of an open-loop ΔC_n doublet and, when ``mission`` has
    segments, the 6-DOF mission (:func:`tailless_mission`)."""
    import json
    spec = tailless_spec(res)
    tl = (getattr(res, "dynamics", None) or {}).get("tailless") or {}
    od = Path(out_dir)
    od.mkdir(parents=True, exist_ok=True)
    out = {"name": "tailless_lateral_test", "notes": [], "files": {}}
    case = pick_case(res, tl)
    if case is None:
        out["status"] = "unassessed"
        out["notes"].append("nenhum caso de massa equilibra o cruzeiro com a elevon dentro do limite — 6-DOF não corrido")
        return out
    V, h = float(res.cruise_speed), float(res.cruise_altitude)
    cases = trimmable_cases(tl)
    out["lateral_tests"] = {}
    fm = None
    for cn in cases:
        log(f"modelo de voo da montagem sem deriva (caso '{cn}') + ensaio lateral 6-DOF (rajada 14 CFR 23.443)…")
        fm_c = build_tailless_flight_model(res, spec, tl, cn)
        out["lateral_tests"][cn] = lateral_test(fm_c, tl, V, h)
        if cn == case:
            fm = fm_c
            out["files"]["flight_model_json"] = str(fm.save(od))
    untrimmed = sorted(set(((tl.get("approach_consistency") or {}).get("cases") or {})) - set(cases))
    if untrimmed:
        out["notes"].append(f"casos sem equilíbrio de cruzeiro com a elevon (6-DOF não corrido): {untrimmed}")
    out["lateral_test"] = out["lateral_tests"][case]
    out["case"] = case
    gv = {cn: (lt.get("gust_verdict") or {}) for cn, lt in out["lateral_tests"].items()}
    oks = [v.get("ok") for v in gv.values()]
    out["lateral_gust_6dof"] = {
        "criterion": GUST_6DOF_CRITERION,
        "ok": False if any(o is False for o in oks) else (True if oks and all(o is True for o in oks) else None),
        "failing_cases": sorted(cn for cn, v in gv.items() if v.get("ok") is False),
        "rate_required_deg_s": max((v["rate_required_deg_s"] for v in gv.values()
                                    if v.get("rate_required_deg_s") is not None), default=None),
        "cases": gv}
    ms = None
    if mission:
        from .mission import load_mission
        ms = load_mission(mission)
    if ms and ms.get("segments"):
        try:
            out["mission"] = tailless_mission(res, spec, tl, ms, od, log)
        except Exception as ex:  # noqa: BLE001
            out["mission"] = {"status": "error", "error": str(ex)}
    else:
        out["notes"].append("sem missão (segments) — só o ensaio lateral")
    if jsbsim_check:
        from .jsbsim_runner import jsbsim_available
        if not jsbsim_available():
            out["jsbsim"] = {"error": "JSBSim indisponível"}
        else:
            out["jsbsim_cases"] = {}
            for cn in cases:
                log(f"JSBSim vs 6-DOF próprio (caso '{cn}')…")
                fm_c = build_tailless_flight_model(res, spec, tl, cn)
                out["jsbsim_cases"][cn] = jsbsim_crosscheck(
                    fm_c, tl, V, h, od / "jsbsim" / cn, plot=(od / "jsbsim_lateral.png") if cn == case else None)
            out["jsbsim"] = out["jsbsim_cases"][case]
    (od / "tailless_sim_summary.json").write_text(json.dumps(out, indent=1, default=float, ensure_ascii=False))
    out["files"]["summary_json"] = str(od / "tailless_sim_summary.json")
    return out
