# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Catapult launch and belly landing — first-order, opt-in checks for any fixed-wing UAV.

Enabled only by ``assumptions.launch_recovery`` (absent → nothing runs, no check is added).

Catapult (``launch_recovery.catapult``) — Fahlstrom, Gleason & Sadraey, *Introduction to UAV Systems*, 5th ed.
(Wiley 2022), Ch. 17 Launch Systems (17.3 Basic Considerations): stroke at constant acceleration
L = V² / (2a); launch energy ΔE_launcher + ΔE_propulsion − ΔE_losses = W·ΔV²/(2g) + W·Δh (+ stored energy);
shuttle force F = (W + W_shuttle)(a/g + sin θ_rail). PRESSUPOSTO (preliminary design, as in the same text):
ΔE_propulsion = 0 and ΔE_losses = 0 — the launcher supplies all the kinetic energy (conservative for the
launcher). Required end (release) airspeed V_end ≥ k·V_S, k = 1.1 by default — PRESSUPOSTO analogue of the
lift-off criterion V_LOF ≥ 1.1 V_S (Raymer 2018 Sec. 17.8); a headwind counts towards airspeed. The
longitudinal load factor n_x = a/g is checked against airframe / payload limits only when given (no limit →
unassessed, never a pass). Post-release sink and pitch-up are not assessed.

Belly landing (``launch_recovery.belly_landing``) — Fahlstrom, Gleason & Sadraey 2022 Sec. 18.9 (skid and
belly landing) names the method; the numbers here are the classical gear-energy balance (Currey 1988 §5.3,
:func:`.landing_gear.gear_load_factor`) applied to the belly skid / crush stroke, with the limit descent
velocity of 14 CFR 23.473(d) (pre-Amdt 23-64) and the wing-lift fraction κ ≤ 2/3 of 23.473(e). Slide-out:
the kinetic energy at V_TD = 1.15 V_S (Raymer 2018 Sec. 17.9) is dissipated by sliding friction μ; distance
V_TD²/(2 μ g) with the lift neglected (lower bound on distance, upper bound on deceleration). μ has no cited
default here: without it the slide is unassessed. Abrasion is reported only as friction work and, when the
contact area is given, mean contact pressure (no wear data → no wear verdict). Propeller clearance on the
belly (pusher): the lowest airframe point (gear excluded) is the contact; the disc must stay above that
ground line at each attitude (14 CFR 23.925 is written for a wheeled aeroplane and is not applied).
"""
from __future__ import annotations

import math

import numpy as np

from acdt import G0

SOURCE_CAT = ("Fahlstrom, Gleason & Sadraey 2022 (Introduction to UAV Systems, 5.ª ed.) Cap. 17 (17.3): L = V²/(2a), "
              "balanço de energia, F = (W + W_shuttle)(a/g + sin θ); V_end ≥ k V_S (PRESSUPOSTO, análogo a Raymer 17.8)")
SOURCE_BELLY = ("Fahlstrom, Gleason & Sadraey 2022 Sec. 18.9 (aterragem de ventre/patim); energia Currey 1988 §5.3; "
                "14 CFR 23.473(d)/(e) (pré-Amdt 23-64); V_TD = 1,15 V_S (Raymer 2018 Sec. 17.9)")
BELLY_STROKE_M = 0.025      # PRESSUPOSTO: belly skid / crush stroke (replace with a drawing)
BELLY_ETA = 0.50            # PRESSUPOSTO: solid skid / crushable (Currey solid spring ≈ 0.5, as the tip skids)


def stall_speed(W_N: float, S: float, CLmax: float, rho: float = 1.225) -> float:
    return math.sqrt(2.0 * W_N / (rho * S * CLmax))


def catapult_launch(m_kg: float, V_S: float, opts: dict) -> dict:
    """First-order catapult check. ``opts``: ``speed_margin`` (1.1), ``end_speed_m_s``, ``headwind_m_s`` (0),
    ``accel_g`` or ``stroke_m`` (one is needed for n_x / stroke), ``rail_angle_deg`` (0), ``shuttle_mass_kg``,
    ``stroke_max_m`` (launcher), ``airframe_nx_limit_g``, ``payload_nx_limit_g``."""
    k = float(opts.get("speed_margin", 1.1))
    hw = float(opts.get("headwind_m_s", 0.0))
    V_req_air = k * V_S
    V_req = max(V_req_air - hw, 0.0)                    # ground (rail) speed needed at release
    V_end = float(opts["end_speed_m_s"]) if opts.get("end_speed_m_s") is not None else V_req
    th = math.radians(float(opts.get("rail_angle_deg", 0.0)))
    out = {"status": "assessed", "source": SOURCE_CAT, "V_S_m_s": V_S, "speed_margin": k, "headwind_m_s": hw,
           "V_end_required_m_s": V_req, "V_end_m_s": V_end, "V_end_air_m_s": V_end + hw,
           "speed_ok": bool(V_end + hw >= V_req_air - 1e-9),
           "speed_margin_note": "PRESSUPOSTO k = 1,1 (análogo ao V_LOF ≥ 1,1 V_S de Raymer 2018 Sec. 17.8)",
           "energy_note": "PRESSUPOSTO: ΔE_propulsão = 0 e perdas = 0 (o lançador dá toda a energia cinética)"}
    a = None
    if opts.get("accel_g") is not None:
        a = float(opts["accel_g"]) * G0
        L = V_end ** 2 / (2.0 * a)
    elif opts.get("stroke_m") is not None:
        L = float(opts["stroke_m"])
        a = V_end ** 2 / (2.0 * L) if L > 0 else math.inf
    else:
        L = None
    if a is None:
        out.update({"accel_m_s2": None, "n_x_g": None, "stroke_m": None, "stroke_ok": None,
                    "airframe_g_ok": None, "payload_g_ok": None,
                    "issue": "sem accel_g nem stroke_m: curso e carga de lançamento não avaliados",
                    "stroke_for_g": {f"{g:g} g": V_end ** 2 / (2 * g * G0) for g in (5, 10, 15, 20)}})
        return out
    nx = a / G0
    m_sh = opts.get("shuttle_mass_kg")
    F = (m_kg + float(m_sh or 0.0)) * G0 * (nx + math.sin(th))
    E_k = 0.5 * m_kg * V_end ** 2
    E_p = m_kg * G0 * L * math.sin(th)
    smax = opts.get("stroke_max_m")
    lim_a, lim_p = opts.get("airframe_nx_limit_g"), opts.get("payload_nx_limit_g")
    out.update({"accel_m_s2": a, "n_x_g": nx, "stroke_m": L, "time_s": V_end / a if a > 0 else None,
                "rail_angle_deg": math.degrees(th),
                "energy_kinetic_J": E_k, "energy_potential_J": E_p, "energy_launcher_J": E_k + E_p,
                "shuttle_force_N": F, "peak_power_W": F * V_end,
                "shuttle_note": None if m_sh is not None else "massa do shuttle desconhecida: F só com a aeronave",
                "stroke_ok": None if smax is None else bool(L <= float(smax) + 1e-9),
                "airframe_g_ok": None if lim_a is None else bool(nx <= float(lim_a) + 1e-9),
                "payload_g_ok": None if lim_p is None else bool(nx <= float(lim_p) + 1e-9),
                "limits": {"stroke_max_m": smax, "airframe_nx_limit_g": lim_a, "payload_nx_limit_g": lim_p}})
    return out


def _belly_prop_clearance(asm, attitudes_deg) -> dict | None:
    """Disc clearance above the belly ground line at nose-up attitudes (assembly x aft, z up)."""
    import re
    from .assembly.components import Disc
    discs = [c for c in asm.components if isinstance(c, Disc)]
    if not discs:
        return None
    D = np.concatenate([d.mesh(1)[0] for d in discs])
    Pd = np.concatenate([c.mesh(1)[0] for c in asm.components
                         if not isinstance(c, Disc) and c.role != "item"
                         and not re.search(r"gear|trem|wheel|roda", (c.role or "").lower())])
    rows = {}
    for th_deg in attitudes_deg:
        t = math.radians(th_deg)
        def zrot(V):
            return V[:, 2] * math.cos(t) - V[:, 0] * math.sin(t)
        zg = float(zrot(Pd).min())
        rows[f"{th_deg:g}"] = float(zrot(D).min() - zg)
    worst = min(rows.values())
    opts = None if worst > 0.0 else ("opções (não aplicadas): parar e alinhar a hélice na horizontal antes do "
                                     "toque, hélice dobrável, ou subir o disco / patim de ventre mais alto que a "
                                     f"ponta da pá ({-worst:.3f} m em falta)")
    return {"clearance_by_attitude_m": rows, "min_clearance_m": worst, "ok": bool(worst > 0.0), "options": opts,
            "note": "linha de solo pelo ponto mais baixo da estrutura sem trem (rotação nariz-acima); 14 CFR 23.925 "
                    "não se aplica à aterragem de ventre"}


def belly_landing(m_kg: float, S: float, V_S: float, opts: dict, asm=None) -> dict:
    """First-order belly landing. ``opts``: ``sink_rate_m_s`` (else 14 CFR 23.473(d)), ``stroke_m`` (0.025),
    ``eta`` (0.5), ``wing_lift_fraction`` (2/3, 23.473(e) maximum), ``n_limit`` (airframe ground-reaction limit,
    else unassessed), ``mu_slide`` (no default), ``contact_area_m2``, ``attitudes_deg`` ([0, 5, 10])."""
    from .landing_gear import gear_load_factor, limit_descent_speed_ft_s, wing_loading_psf
    from .weights_detailed import FT
    if opts.get("sink_rate_m_s") is not None:
        v = float(opts["sink_rate_m_s"])
        v_src = "dado"
    else:
        v = limit_descent_speed_ft_s(wing_loading_psf(m_kg, S)) * FT
        v_src = "14 CFR 23.473(d) (pré-Amdt 23-64), V = 4,4 (W/S)^¼ ft/s em [7, 10]"
    stroke = float(opts.get("stroke_m", BELLY_STROKE_M))
    eta = float(opts.get("eta", BELLY_ETA))
    kap = float(opts.get("wing_lift_fraction", 2.0 / 3.0))
    n = gear_load_factor(v, stroke, eta, kap)
    W = m_kg * G0
    V_td = 1.15 * V_S
    out = {"status": "assessed", "source": SOURCE_BELLY, "sink_rate_m_s": v, "sink_source": v_src,
           "stroke_m": stroke, "eta": eta, "wing_lift_fraction": kap,
           "stroke_note": "PRESSUPOSTO: curso do patim/zona de esmagamento 25 mm e η 0,5 (como os patins de ponta)",
           "energy_vertical_J": 0.5 * m_kg * v * v, "n_ground_reaction": n, "N_belly_N": n * W,
           "n_limit": opts.get("n_limit"),
           "load_ok": None if opts.get("n_limit") is None else bool(n <= float(opts["n_limit"]) + 1e-9),
           "V_TD_m_s": V_td, "energy_horizontal_J": 0.5 * m_kg * V_td ** 2}
    mu = opts.get("mu_slide")
    if mu is not None and float(mu) > 0:
        mu = float(mu)
        out.update({"mu_slide": mu, "slide_distance_m": V_td ** 2 / (2 * mu * G0),
                    "slide_decel_g": mu, "friction_peak_N": mu * n * W,
                    "slide_note": "sustentação desprezada: limite inferior da distância, superior da desaceleração"})
        A = opts.get("contact_area_m2")
        if A:
            out["contact_pressure_static_Pa"] = W / float(A)
            out["friction_work_per_area_J_m2"] = out["energy_horizontal_J"] / float(A)
    else:
        out.update({"slide_distance_m": None, "slide_note": "μ de deslizamento não dado — distância não avaliada"})
    out["abrasion"] = "não avaliado (sem dados de desgaste); reporta-se o trabalho de atrito"
    if asm is not None:
        pc = _belly_prop_clearance(asm, opts.get("attitudes_deg") or [0.0, 5.0, 10.0])
        out["prop_clearance"] = pc
        if pc is not None and opts.get("attitudes_deg") is None:
            pc["attitudes_note"] = "PRESSUPOSTO: atitudes 0/5/10° no toque (dar attitudes_deg)"
    return out


def launch_recovery_stage(res, lr: dict) -> dict:
    """Run the opt-in checks on a sized design and append ``lr:*`` checks (reported, not Phase-1 feasibility)."""
    from .sizing import CheckResult
    m = float(res.sizing.W0)
    S = float(res.S)
    hl = res.highlift
    out = {"schema": "launch_recovery"}
    if lr.get("catapult"):
        o = lr["catapult"] if isinstance(lr["catapult"], dict) else {}
        CL = float(getattr(hl, "CLmax_takeoff", None) or hl.CLmax_clean)
        Vs = stall_speed(m * G0, S, CL)
        c = catapult_launch(m, Vs, o)
        c["CLmax_used"] = CL
        out["catapult"] = c
        res.checks.append(CheckResult("lr:catapult_speed", c["speed_ok"],
                                      f"catapulta: V_fim {c['V_end_air_m_s']:.1f} m/s (ar) contra {c['speed_margin']:.2f} V_S "
                                      f"= {c['speed_margin'] * Vs:.1f} m/s ({SOURCE_CAT})"))
        if c.get("n_x_g") is None:
            res.checks.append(CheckResult("lr:catapult_stroke", None, "catapulta: " + c["issue"]))
        else:
            res.checks.append(CheckResult("lr:catapult_stroke", c["stroke_ok"],
                                          f"curso {c['stroke_m']:.2f} m a {c['n_x_g']:.1f} g"
                                          + ("" if c["stroke_ok"] is not None else " (sem curso máximo do lançador: não avaliado)")))
            res.checks.append(CheckResult("lr:catapult_airframe_g", c["airframe_g_ok"],
                                          f"n_x {c['n_x_g']:.1f} g contra a célula"
                                          + ("" if c["airframe_g_ok"] is not None else " (limite não dado: não avaliado)")))
            res.checks.append(CheckResult("lr:catapult_payload_g", c["payload_g_ok"],
                                          f"n_x {c['n_x_g']:.1f} g contra a carga útil"
                                          + ("" if c["payload_g_ok"] is not None else " (limite não dado: não avaliado)")))
    if lr.get("belly_landing"):
        o = lr["belly_landing"] if isinstance(lr["belly_landing"], dict) else {}
        CL = float(getattr(hl, "CLmax_landing", None) or hl.CLmax_clean)
        Vs = stall_speed(m * G0, S, CL)
        asm = None
        al = getattr(res, "assembly_loop", None)
        if isinstance(al, dict) and (al.get("spec_scaled") or {}).get("assembly"):
            from .assembly import Assembly
            asm = Assembly.from_dict(al["spec_scaled"]["assembly"])
        b = belly_landing(m, S, Vs, o, asm)
        b["CLmax_used"] = CL
        out["belly_landing"] = b
        res.checks.append(CheckResult("lr:belly_load", b["load_ok"],
                                      f"ventre: descida {b['sink_rate_m_s']:.2f} m/s, n {b['n_ground_reaction']:.1f}"
                                      + ("" if b["load_ok"] is not None else " (limite da célula não dado: não avaliado)")))
        pc = b.get("prop_clearance")
        if pc is not None:
            res.checks.append(CheckResult("lr:belly_prop_clearance", pc["ok"],
                                          f"hélice sobre a linha do ventre: mínimo {pc['min_clearance_m']:.3f} m "
                                          f"({pc['clearance_by_attitude_m']})"))
    res.launch_recovery = out
    return out
