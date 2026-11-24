# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Follow-up assessments of the tailless split-aileron option (10 nov 2026): actuator dynamics in the SAS loop,
hinge moments / servos / actuator mass, lateral discrete gust, approach trim consistency and crosswind fix
options. Called at the end of :func:`.tailless.evaluate`; methods and sources in :mod:`.tailless_actuation` and
:mod:`.tailless_approach`. Missing inputs → unassessed (never a pass)."""
from __future__ import annotations

import math

import numpy as np

from . import tailless as T
from . import tailless_actuation as TX
from . import tailless_approach as TA


def _strip_trace(g: dict) -> dict:
    return {k: v for k, v in g.items() if k != "trace"}


def extend(rep: dict, res, spec: dict, md: dict, asm, ctx: dict) -> None:
    from acdt.core.atmosphere import isa
    from acdt import G0
    fw, sa, el = ctx["fw"], ctx["sa"] or {}, ctx["el"]
    C1, dmax, geom = ctx["C1"], ctx["dmax"], ctx["geom"]
    S, b = ctx["S"], ctx["b"]
    m, Ixx, Izz = ctx["m"], ctx["Ixx"], ctx["Izz"]
    act_cfg = fw.get("actuators") if isinstance(fw.get("actuators"), dict) else {}
    lag = act_cfg.get("lag_s")
    dly = act_cfg.get("delay_s")
    rate_max = sa.get("rate_max_deg_s")
    sas = rep.get("sas") or {}
    ap, A_ap, A_cr, cr = ctx["ap"], ctx["A_ap"], ctx["A_cr"], ctx["cr"]
    rho0 = isa(0.0).rho
    # ---------------------------------------------------------------- 1. actuator dynamics in the SAS loop
    if rep.get("sas_enabled") and sas.get("status") == "ok":
        kb, kr = sas["k_beta"], sas["k_r"]
        dyn = {"cruise": TX.actuator_dynamics(A_cr, kb, kr, cr["qSb_Izz"], b, cr["u0"], ctx["cat_cruise"], lag, dly)}
        if A_ap is not None:
            dyn["approach"] = TX.actuator_dynamics(A_ap, kb, kr, ap["qSb_Izz"], b, ap["u0"], "C", lag, dly)
        lag_e, dly_e = dyn["cruise"].get("lag_s", 0.0), dyn["cruise"].get("delay_s", 0.0)
        dyn["lag_s"], dyn["delay_s"] = lag_e, dly_e
        mgs = [d.get("delay_margin_level1_s") for d in dyn.values() if isinstance(d, dict) and "level" in d]
        dyn["delay_margin_level1_s"] = None if (not mgs or any(v is None for v in mgs)) else min(mgs)
        lv = [d.get("level", 4) for d in dyn.values() if isinstance(d, dict) and "level" in d]
        dyn["level_worst"] = max(lv) if lv else None
        dyn["ok"] = bool(lv) and max(lv) == 1 and all(d.get("stable", False) for d in dyn.values()
                                                      if isinstance(d, dict) and "level" in d)
        rep["actuator_dynamics"] = dyn
        # authority re-checked with the actuator (σ of the actuated ΔC_n)
        a = rep.get("authority") or {}
        turb = rep.get("turbulence")
        if A_ap is not None and turb and C1 is not None and dmax is not None:
            sg = TX.turbulence_sigma_actuated(A_ap, kb, kr, ap["qSb_Izz"], b, ap["u0"], turb["sigma_v"], turb["L_v_m"],
                                              lag_e, dly_e)
            if sg is None:
                wa = {"ok": False, "issue": "malha com atuador instável em turbulência"}
            else:
                three = 3 * sg["sigma_u"]
                cap = T.capacity(C1, dmax)
                d3 = T.deflection_for(three, C1)
                wd = ((dyn.get("approach") or {}).get("dutch_roll") or {}).get("wn")
                rate = math.degrees(math.radians(d3) * wd) if (d3 is not None and wd) else None
                wa = {"sigma_u": sg["sigma_u"], "dCn_3sigma": three, "capacity_dCn": cap, "delta_3sigma_deg": d3,
                      "omega_d_approach": wd, "rate_required_deg_s": rate, "rate_max_deg_s": rate_max,
                      "authority_ok": three <= cap,
                      "rate_ok": (rate is not None and rate <= rate_max) if rate_max is not None else None}
                wa["ok"] = (bool(wa["authority_ok"] and wa["rate_ok"]) if wa["rate_ok"] is not None
                            else (False if not wa["authority_ok"] else None))
            a["with_actuator"] = wa
            if a.get("ok") is True and wa.get("ok") is not True:
                a["ok"] = wa.get("ok")
            rep["authority"] = a
    # ---------------------------------------------------------------- 2. hinge moments, servos, actuator mass
    vn = getattr(getattr(res, "structures", None), "vn", None)
    catalog = act_cfg.get("catalog") or []
    fos = float(act_cfg.get("factor_of_safety", 1.5))
    nmax = int(act_cfg.get("max_per_surface", 1))
    actrep = {"factor_of_safety": fos, "catalog": [c.get("name") for c in catalog], "issues": []}
    if vn is None:
        actrep["status"] = "unassessed"
        actrep["issues"].append("sem diagrama V-n (V_A, V_D) — momentos de charneira unassessed")
    else:
        actrep["VA_m_s"], actrep["VD_m_s"] = vn.VA, vn.VD
        if geom is not None:
            sh = TX.split_hinge(geom, dmax, vn.VA, vn.VD, rho0)
            a = rep.get("authority") or {}
            wa = a.get("with_actuator") or {}
            d_op = wa.get("delta_3sigma_deg", a.get("delta_3sigma_deg"))
            rate_req = wa.get("rate_required_deg_s", a.get("rate_required_deg_s"))
            # opt-in (24 nov 2026): taxa de projeto do split imposta pelo projetista (p.ex. a taxa exigida pela
            # rajada lateral 23.443 no 6-DOF); a escolha do servo usa a maior das duas. None → sem efeito.
            rr_design = act_cfg.get("split_rate_required_deg_s")
            if rr_design is not None:
                actrep["split_rate_required_design_deg_s"] = float(rr_design)
                rate_req = float(rr_design) if rate_req is None else max(float(rate_req), float(rr_design))
            H_op = None
            if d_op is not None and ap is not None:
                ch = TX.split_ch(d_op)
                if ch is not None:
                    H_op = ch * 0.5 * rho0 * ap["U"] ** 2 * sh["S_leaf"] * sh["c_leaf"]
            sh["H_operating_Nm"] = H_op
            sh["operating_point"] = {"delta_deg": d_op, "U_m_s": ap["U"] if ap else None,
                                     "note": "3σ do SAS em turbulência na aproximação (com atuador)"}
            sh["servo"] = TX.select_servo(catalog, sh["H_max_Nm"], rate_req, fos, H_op, nmax, dmax)
            sh["n_actuators"] = 4
            actrep["split_aileron"] = sh
            pick = (sh["servo"] or {}).get("servo")
            if pick:
                # the surface rate is the selected servo's through its gearing (supersedes rate_max_deg_s)
                rate_max = pick["rate_at_surface_deg_s"]
                actrep["rate_max_effective_deg_s"] = rate_max
                a = rep.get("authority") or {}
                for blk in (a, a.get("with_actuator") or {}):
                    rr = blk.get("rate_required_deg_s")
                    if rr is not None:
                        blk["rate_max_deg_s"] = rate_max
                        blk["rate_source"] = f"{pick['name']} com engrenagem G = {pick['gearing']:.2f} (catálogo)"
                        blk["rate_ok"] = bool(rr <= rate_max)
                wa = a.get("with_actuator") or {}
                if wa.get("authority_ok") is not None and wa.get("rate_ok") is not None:
                    wa["ok"] = bool(wa["authority_ok"] and wa["rate_ok"])
                    a["ok"] = bool(a.get("authority_ok", True) and wa["ok"])
        else:
            actrep["issues"].append("geometria do split aileron em falta — charneira unassessed")
        if ctx["d_cr"] is not None:
            try:
                xr, zr, mach = ctx["x_cg"], ctx["z_cg"], ctx["mach_cr"]
                h0 = T.avl_elevon_point(asm, mach, xr, zr, el, alpha_deg=0.0, hinge=True)
                h5 = T.avl_elevon_point(asm, mach, xr, zr, el, alpha_deg=5.0, hinge=True)
                hd = T.avl_elevon_point(asm, mach, xr, zr, el, alpha_deg=0.0, anti_deg=10.0, hinge=True)
                hm = {"Ch0": h0["hinge"]["elevsym"] / 2,
                      "Cha": (h5["hinge"]["elevsym"] - h0["hinge"]["elevsym"]) / 2 / math.radians(5.0),
                      "Chd": (hd["hinge"]["elevon"] - h0["hinge"]["elevon"]) / 2 / math.radians(10.0)}
                eg = T.split_geometry(asm, float(el["eta_inner"]), float(el["eta_outer"]), float(el["cf_c"]))
                span_e = (eg["eta_outer"] - eg["eta_inner"]) * eg["semispan"]
                eh = TX.elevon_hinge(hm, {"S_e": eg["S_f"], "c_e": eg["S_f"] / span_e}, S, ctx["c"], ctx["el_max"],
                                     vn.VA, vn.VD, rho0, m * G0, h0["CLa"], h0["CL"])
                eh["servo"] = TX.select_servo(catalog, eh["H_max_Nm"], el.get("rate_required_deg_s"), fos, None, nmax,
                                               ctx["el_max"])
                eh["n_actuators"] = 2
                actrep["elevon"] = eh
            except Exception as ex:  # pragma: no cover - AVL failure
                actrep["issues"].append(f"charneira da elevon (AVL HM) falhou: {ex}")
        # masses
        parts, unknown = [], []
        for k in ("split_aileron", "elevon"):
            blk = actrep.get(k)
            sv = (blk or {}).get("servo") or {}
            if sv.get("servo"):
                n = blk["n_actuators"] * sv["servo"]["n_per_surface"]
                parts.append({"surface": k, "n": n, "servo": sv["servo"]["name"],
                              "unit_mass_kg": sv["servo"]["unit_mass_kg"], "mass_kg": n * sv["servo"]["unit_mass_kg"]})
            else:
                unknown.append(k)
        items = ((res.spec.assumptions.get("weights") or {}).get("components") or {}).get("items")
        bud = TX.budget_items(items)
        declared = sum(float(i.get("mass_kg", 0.0)) for i in bud) if bud else None
        tot = sum(p["mass_kg"] for p in parts)
        actrep["mass"] = {"parts": parts, "unknown_surfaces": unknown, "total_known_kg": tot,
                          "budget_items": [i.get("name") for i in bud], "budget_declared_kg": declared,
                          "within_budget": (None if unknown or declared is None else tot <= declared + 1e-9),
                          "note": "massas do datasheet do servo (sem hastes/suportes); orçamento = itens de "
                                  "weights.components.items com 'servo'/'atuador' no nome"}
        sv_ok = [((actrep.get(k) or {}).get("servo") or {}).get("ok") for k in ("split_aileron", "elevon")]
        actrep["ok"] = False if any(v is False for v in sv_ok) else (True if all(v is True for v in sv_ok) else None)
        actrep["status"] = "assessed"
    rep["actuators"] = actrep
    rep["mass_note"] = None
    # ---------------------------------------------------------------- 3. lateral discrete gust (14 CFR 23.443)
    if ctx["d_cr"] is not None:
        rho_cr = ctx["rho_cr"]
        u0 = cr["u0"]
        vg = TX.U_DE_VC_FPS * TX.FT * math.sqrt(rho0 / rho_cr)
        mgc = S / b
        L = 25.0 * mgc
        g = {"source": TX.GUST_SOURCE, "U_de_m_s_EAS": TX.U_DE_VC_FPS * TX.FT, "v_peak_TAS_m_s": vg,
             "gust_length_m": L, "condition": f"cruzeiro {u0:.1f} m/s TAS (EAS {u0 * math.sqrt(rho_cr / rho0):.1f} m/s)"}
        if vn is not None:
            g["VC_EAS_m_s"] = vn.VC
            if abs(u0 * math.sqrt(rho_cr / rho0) - vn.VC) > 0.05 * vn.VC:
                g["note"] = "PRESSUPOSTO: caso corrido à velocidade de cruzeiro, ≠ V_C em EAS (> 5 %)"
        dly_e = (rep.get("actuator_dynamics") or {}).get("delay_s", TX.TIME_DELAY_LIMITS_S[0])
        lag_e = (rep.get("actuator_dynamics") or {}).get("lag_s", 0.0)
        bare = TX.gust_response(A_cr, ctx["d_cr"], u0, rho_cr, S, b, m, Ixx, Izz, None, C1, dmax, rate_max,
                                ctx["el_max"], lag_e, dly_e, vg, L)
        g["bare"] = _strip_trace(bare)
        if rep.get("sas_enabled") and sas.get("status") == "ok" and C1 is not None:
            b0 = T.bias_deg(spec)   # opt-in split pre-deflection as the design (drag in the sizing polar)
            wsas = TX.gust_response(A_cr, ctx["d_cr"], u0, rho_cr, S, b, m, Ixx, Izz, sas, C1, dmax, rate_max,
                                    ctx["el_max"], lag_e, dly_e, vg, L, bias_deg=b0)
            if b0 > 0:
                g["bias_deg"] = b0
                g["bias_source"] = T.BIAS_SOURCE
                g["bias_drag"] = T.bias_drag(spec, asm)
            g["sas"] = _strip_trace(wsas)
            g["trace_sas"] = wsas["trace"]
            ac = wsas.get("actuator") or {}
            settled = (wsas["final_beta_amp_deg"] is not None
                       and wsas["final_beta_amp_deg"] <= 0.1 * max(wsas["peak"]["beta_air_deg"], 1e-6))
            g["settled"] = settled
            g["ok"] = (bool(not ac.get("saturated") and not ac.get("rate_limited") and settled)
                       if rate_max is not None else None)
            g["status"] = "assessed"
            _elevon_rate_from_gust(rep, wsas, el)
            if g["ok"] is False and ac.get("rate_limited") and rate_max is not None:
                g["options"] = gust_options(A_cr, ctx, u0, rho_cr, S, b, m, Ixx, Izz, sas, C1, dmax, rate_max, lag_e,
                                            dly_e, vg, L, geom, getattr(res.polar, "CD0", None))
        else:
            g["ok"] = None
            g["status"] = "unassessed" if C1 is None else "bare_only"
        rep["lateral_gust"] = g
    else:
        rep["lateral_gust"] = {"status": "unassessed", "ok": None, "issues": ["falta elevon (bank hold)"]}
    # ---------------------------------------------------------------- 4. approach trim consistency
    if ctx["d_cr"] is not None:
        try:
            rep["approach_consistency"] = TA.approach_consistency(
                asm, res, res.assembly["result"], fw, el, ctx["mach_ap"] or ctx["mach_cr"], m * G0, S,
                ap["CL"] if ap else None, md["derivatives"]["CL"], (ap or {}).get("alpha_deg"))
            apc = rep["approach_consistency"]
            sms = [v["static_margin"] for v in apc.get("cases", {}).values() if v.get("static_margin") is not None]
            if sms:
                from . import tailless_trim as TT
                apc["washout_check"] = TT.washout_check(asm, md["derivatives"]["CL"], min(sms))
        except Exception as ex:  # pragma: no cover
            rep["approach_consistency"] = {"status": "error", "error": str(ex), "ok": None}
    # ---------------------------------------------------------------- 4a. packaging of the load lumped at the CG
    _ao = ((res.spec.assumptions.get("assembly") or {}).get("options") or {}) if isinstance(res.spec.assumptions, dict) else {}
    if _ao.get("useful_load_at") == "empty_cg":
        from . import tailless_trim as TT
        try:
            rep["cg_packaging"] = TT.cg_packaging(asm, res.assembly["result"])
        except Exception as ex:  # pragma: no cover
            rep["cg_packaging"] = {"status": "error", "error": str(ex)}
        try:
            rep["fine_packaging"] = TT.fine_packaging(asm, res.assembly["result"])
        except Exception as ex:  # pragma: no cover
            rep["fine_packaging"] = {"status": "error", "error": str(ex)}
    # ---------------------------------------------------------------- 4b. phugoid with pitch-attitude hold (UAV autopilot)
    rep["pitch_hold"] = _pitch_hold(rep, res, md, ctx)
    # ---------------------------------------------------------------- 4c. take-off: rotation vs fly-off stance (opt-in)
    gsp = spec.get("gear") or {}
    if fw.get("takeoff_rotation") or gsp.get("ground_attitude_deg"):
        rep["takeoff_rotation"] = _takeoff_rotation(rep, res, spec)
    # ---------------------------------------------------------------- 5. crosswind fix options
    cw = rep.get("crosswind") or {}
    if cw.get("status") == "assessed" and cw.get("ok") is False and ctx["d_ap"] is not None:
        n_eng = int((res.spec.assumptions.get("propulsion") or {}).get("n_engines", 1))
        rep["crosswind_options"] = TA.crosswind_options(
            asm, ctx["d_ap"], ap, cw, geom, C1, dmax, el, ctx["el_max"], ctx["K_f"], ctx["mach_ap"], ctx["x_cg"],
            ctx["z_cg"], ctx["cnb_body"], n_eng, fw.get("gear_side_load"))


def _takeoff_rotation(rep: dict, res, spec: dict) -> dict:
    """Sadraey 2012 Sec. 9.6.2 rotation / fly-off stance per loading case (flightsim.tailless_takeoff)."""
    from ..flightsim import tailless_takeoff as TO
    from ..flightsim.tailless_sim import build_tailless_flight_model
    try:
        out = res.assembly["result"]
        cases = out.loading["cases"]
        models = {k: build_tailless_flight_model(res, spec, rep, k) for k in cases}
        req = res.spec.requirements.value("takeoff_ground_roll") if res.spec.requirements.get("takeoff_ground_roll") \
            else None
        return TO.assess(res, spec, rep, out.gear or {}, cases, models, req)
    except Exception as ex:  # pragma: no cover
        return {"status": "error", "issue": f"avaliação da descolagem falhou: {ex}", "source": TO.SOURCE}


def _pitch_hold(rep: dict, res, md: dict, ctx: dict) -> dict:
    """Bare vs pitch-attitude-hold phugoid (active autopilot = UAV base hypothesis). Elevon authority for the loop =
    elevon limit − largest |δe| of cruise trim over the loading cases (PRESSUPOSTO)."""
    from acdt.core.atmosphere import isa
    from ..stability import MIL_F_8785C, _modes_long
    if not rep.get("sas_enabled"):
        return {"status": "not_applicable", "ok": None, "note": "piloto automático não assumido (sas: false)"}
    apc = rep.get("approach_consistency") or {}
    cases = apc.get("cases") or {}
    hq_case = (md.get("inertia") or {}).get("case", "cheio")
    cc = cases.get(hq_case) or {}
    A = md.get("A_lon")
    if A is None or cc.get("CLde") is None or cc.get("Cmde") is None:
        return {"status": "unassessed", "ok": None, "issues": ["falta A_lon ou C_Lδe/C_mδe do caso de massa"]}
    trims = [abs(v["cruise"]["elevon_deg"]) for v in cases.values() if (v.get("cruise") or {}).get("elevon_deg") is not None]
    de_auth = ctx["el_max"] - (max(trims) if trims else 0.0)
    if de_auth <= 0:
        return {"status": "unassessed", "ok": None, "issues": ["sem autoridade de elevon além do equilíbrio"]}
    I = md["inertia"]
    u0 = float(md["u0"])
    qS = 0.5 * isa(res.cruise_altitude).rho * u0**2 * ctx["S"]
    dv = md["derivatives"]
    cl = TX.pitch_hold_closed_loop(A, dv["CL"], res.polar.K, cc["CLde"], cc["Cmde"], dv.get("Cmad", 0.0) or 0.0, qS,
                                   ctx["c"], I["m"], I["Iyy"], u0, math.radians(de_auth))
    lon = _modes_long(cl["A_cl"], u0, qS, dv["CLa"], I["m"], I)
    eig = np.linalg.eigvals(cl["A_cl"])
    stable = bool(np.all(eig.real < 0))
    ph = lon.get("phugoid") or {}
    z = ph.get("zeta")
    zmin = MIL_F_8785C["phugoid_zeta_min"][0]
    if z is None or z != z:   # no oscillatory phugoid left: aperiodic roots
        lvl = 1 if stable else 4
    else:
        lvl = 1 if z >= zmin else (2 if z >= 0 else 3)
    sp = lon.get("short_period") or {}
    bare = (md.get("longitudinal") or {}).get("phugoid") or {}
    out = {"status": "assessed", "case": hq_case, "elevon_authority_deg": de_auth, **{k: v for k, v in cl.items() if k != "A_cl"},
           "eig": [[float(e.real), float(e.imag)] for e in eig], "stable": stable,
           "phugoid": {k: ([float(x) for x in ph[k]] if k == "real_roots" else ph.get(k))
                       for k in ("zeta", "wn", "period_s", "real_roots") if k in ph},
           "short_period": {k: sp.get(k) for k in ("zeta", "wn") if k in sp}, "level": lvl,
           "bare_phugoid_zeta": bare.get("zeta"), "ok": stable and lvl == 1,
           "note": "malha fechada linear (sem saturação, sem atraso do atuador da elevon); manete fixa"}
    return out


def _elevon_rate_from_gust(rep: dict, wsas: dict, el: dict) -> None:
    """Required elevon rate = peak |dδa/dt| of the bank-hold loop in the 14 CFR 23.443 lateral gust (with SAS) — the
    elevon's design rate case here (PRESSUPOSTO: bank-hold gains of Beard & McLain 2012 Sec. 6.3.1). A rate given
    in ``elevon.rate_required_deg_s`` takes precedence. The selected elevon servo is checked against it (no
    re-selection, so the mass budget stays as selected)."""
    blk = ((rep.get("actuators") or {}).get("elevon") or {}).get("servo") or {}
    pick = blk.get("servo")
    rr_user = el.get("rate_required_deg_s")
    rr = rr_user if rr_user is not None else (wsas.get("bank_hold") or {}).get("elevon_rate_peak_deg_s")
    if not pick or rr is None:
        return
    blk["rate_required_deg_s"] = rr
    blk["rate_required_source"] = ("elevon.rate_required_deg_s (utilizador)" if rr_user is not None else
                                   "pico |dδa/dt| do bank hold na rajada lateral 14 CFR 23.443 com SAS (Beard & McLain "
                                   "2012 Sec. 6.3.1, ganhos PRESSUPOSTO)")
    blk["rate_ok"] = bool(pick["rate_at_surface_deg_s"] >= rr)
    if pick.get("travel_ok") is not False:   # same rule as select_servo: unknown travel does not disqualify
        blk["ok"] = bool(blk["rate_ok"])
        blk["status"] = "assessed"
    blk["issue"] = (f"taxa exigida {rr:.0f} °/s ({'rajada lateral, bank hold' if rr_user is None else 'utilizador'}) "
                    f"{'≤' if blk['rate_ok'] else '>'} {pick['rate_at_surface_deg_s']:.0f} °/s na superfície")
    ac = rep["actuators"]
    sv_ok = [((ac.get(k) or {}).get("servo") or {}).get("ok") for k in ("split_aileron", "elevon")]
    ac["ok"] = False if any(v is False for v in sv_ok) else (True if all(v is True for v in sv_ok) else None)


GUST_BIAS_SOURCE = ("Rajput, Zhang & Qu 2014, 'A Differential Configuration of Split Drag-Rudders with Variable Bias "
                    "for Directional Control of Flying-Wing', Appl. Mech. Mater. 643:54–59 (diferencial em torno de "
                    "uma pré-deflexão: lineariza C_n vs deflexão); Wang, Wang & Jia 2011, Acta Aeronaut. Astronaut. "
                    "Sin. 32(8):1392 (manter pequena deflexão nas fases sem requisito de assinatura para ter "
                    "eficácia imediata)")


def gust_options(A_cr, ctx, u0, rho, S, b, m, Ixx, Izz, sas, C1, dmax, rate_max, lag, dly, vg, L, geom,
                 CD0) -> dict:
    """When the lateral gust fails only on the rate limit: (a) faster split servo, (b) symmetric pre-deflection
    (bias) of both splits — linear ΔC_n near zero — with its cruise drag cost (McCormick 1995 Eq. 3.45 per leaf).
    The strict criterion (no saturation, no rate limit, settled) is kept: no cited standard allowing a brief rate
    saturation was found."""
    def run(rate, bias):
        r = TX.gust_response(A_cr, ctx["d_cr"], u0, rho, S, b, m, Ixx, Izz, sas, C1, dmax, rate, ctx["el_max"], lag,
                             dly, vg, L, bias_deg=bias)
        a = r.get("actuator") or {}
        settled = (r["final_beta_amp_deg"] is not None
                   and r["final_beta_amp_deg"] <= 0.1 * max(r["peak"]["beta_air_deg"], 1e-6))
        return {"ok": bool(not a.get("saturated") and not a.get("rate_limited") and settled),
                "rate_limited_fraction": a.get("rate_limited_fraction"), "saturated": a.get("saturated"),
                "peak_rate_deg_s": a.get("peak_rate_deg_s"), "settled": settled,
                "split_peak_deg": r["peak"]["split_deg"]}
    servo = {f"x{k:g}": {"rate_deg_s": rate_max * k, **run(rate_max * k, 0.0)} for k in (2, 5, 10)}
    bias = {}
    for b0 in (2.0, 4.0, 6.0, 8.0, 10.0):
        if 2 * b0 > dmax:
            continue
        rb = run(rate_max, b0)
        dcd = 2 * T.side_effects(geom, C1, b0, ctx["z_cg"])["dCD"] if geom else None
        rb.update({"bias_deg": b0, "dCD_cruise": dcd,
                   "dCD_over_CD0_pct": (100 * dcd / CD0) if (dcd is not None and CD0) else None,
                   "capacity_unchanged": 2 * b0 <= dmax})
        bias[f"{b0:g}"] = rb
    closes = [v for v in bias.values() if v["ok"]]
    best = min(closes, key=lambda v: v["bias_deg"]) if closes else None
    return {"servo_faster": servo, "bias": bias, "smallest_bias_that_closes_deg": best["bias_deg"] if best else None,
            "smallest_bias_dCD_over_CD0_pct": best["dCD_over_CD0_pct"] if best else None,
            "note": ("lei sin² sem pré-deflexão: dδ/dΔC_n → ∞ em ΔC_n = 0, por isso qualquer servo de taxa finita toca "
                     "no limite ao trocar de lado; com pré-deflexão δ0 a lei fica 2C₁ sin2δ0 sin2d (linear). O custo "
                     "de arrasto da pré-deflexão no cruzeiro NÃO está no polar de dimensionamento (seria aplicada só "
                     "em turbulência/rajada; PRESSUPOSTO) — critério estrito mantido"),
            "source": GUST_BIAS_SOURCE}


def rows(tl: dict) -> list:
    """hq:* / asm:* rows of the follow-up assessments (unknown → None)."""
    out = []
    if tl.get("takeoff_rotation"):
        from ..flightsim import tailless_takeoff as TO
        out.append(TO.row(tl["takeoff_rotation"]))
    dyn = tl.get("actuator_dynamics")
    if dyn:
        c = dyn.get("cruise") or {}
        a = dyn.get("approach") or {}
        def _dr(d):
            dr = d.get("dutch_roll") or {}
            return (f"ζ {dr.get('zeta', float('nan')):.3f}, ω {dr.get('wn', float('nan')):.2f} rad/s → Nível "
                    f"{d.get('level') if d.get('level', 4) < 4 else '>3'}")
        mg = dyn.get("delay_margin_level1_s")
        out.append(("hq:sas_time_delay", dyn.get("ok"),
                    f"SAS com atuador (lag {dyn['lag_s']:.3f} s, atraso {dyn['delay_s']:.3f} s"
                    + (f"; {c['assumed']}" if c.get("assumed") else "") + f"): cruzeiro {_dr(c)}"
                    + (f"; aproximação {_dr(a)}" if a else "")
                    + (f"; margem de atraso p/ Nível 1 {mg:.3f} s" if mg is not None else "; sem margem de atraso")
                    + f" ({TX.TIME_DELAY_SOURCE})"))
    g = tl.get("lateral_gust") or {}
    if g.get("status") == "assessed":
        s = g["sas"]
        ac = s.get("actuator") or {}
        out.append(("hq:lateral_gust", g.get("ok"),
                    f"rajada lateral 1−cos {g['v_peak_TAS_m_s']:.1f} m/s TAS, {g['gust_length_m']:.1f} m ({g['source']}): "
                    f"com SAS β_ar pico {s['peak']['beta_air_deg']:.1f}°, ΔC_n pico {s['peak']['dCn']:.4f} "
                    f"(comando {s['peak']['dCn_cmd']:.4f}), split {s['peak']['split_deg']:.1f}°, taxa "
                    f"{ac.get('peak_rate_deg_s', float('nan')):.0f} °/s, saturação {'sim' if ac.get('saturated') else 'não'}, "
                    f"limite de taxa {'sim (%.1f %% do tempo — lei sin² junto de δ = 0)' % (100 * ac.get('rate_limited_fraction', 0)) if ac.get('rate_limited') else 'não'}, elevon {s['peak']['elevon_deg']:.1f}°; "
                    f"célula nua β_ar pico {g['bare']['peak']['beta_air_deg']:.1f}°" + _bias_txt(g) + _gust_opt_txt(g)))
    elif g:
        out.append(("hq:lateral_gust", None, "rajada lateral unassessed — " + "; ".join(g.get("issues") or [g.get("status", "")])))
    pk = tl.get("cg_packaging") or {}
    if pk.get("status") == "assessed":
        if pk.get("fuel_fits"):
            dn = pk.get("payload_density_needed") or {}
            k0 = next(iter(dn), None)
            dtxt = (f"; a carga não posicionada ({pk['payload_unpositioned_kg']:.1f} kg) precisaria de densidade média "
                    + ", ".join(f"{v['payload_density_needed_kg_L']:.2f} kg/L a ±{k} m" for k, v in dn.items()
                                if v.get("payload_density_needed_kg_L") is not None)
                    + " — volume da carga unassessed") if k0 and pk.get("payload_unpositioned_kg") else ""
            msg = (f"combustível {pk['fuel_kg']:.1f} kg = {pk['fuel_volume_m3'] * 1e3:.1f} L (com 2 % de expansão) cabe "
                   f"em volume bruto a ±{pk['slab_half_width_m']:.2f} m do CG vazio "
                   f"({', '.join(f'{k} {v * 1e3:.0f} L' for k, v in pk['slab_by_component_m3'].items())}; centróide "
                   f"{pk['slab_centroid_offset_m'] * 1e3:+.0f} mm do CG){_bo_txt(pk)}{dtxt}. {pk['note']}")
            out.append(("asm:useful_load_packaging", None, msg))
        else:
            out.append(("asm:useful_load_packaging", False, pk.get("issue", "não cabe") + ". " + pk["note"]))
    fp = tl.get("fine_packaging") or {}
    if fp.get("status") == "assessed":
        fu = fp.get("fuel") or {}
        py = fp.get("payload") or {}
        dx = (fp.get("cases") or {}).get("cheio", {}).get("dx_vs_lumped_m")
        sm = fp.get("static_margin_packed") or {}
        smt = (", SM empacotada " + ", ".join(f"{k} {v:.3f}" for k, v in sm.items())
               if sm else "")
        out.append(("asm:fine_packaging", fp.get("ok"),
                    ("combustível empacotado no volume bruto, centróide "
                     f"{fu.get('offset_from_empty_cg_m', float('nan'))*1e3:+.0f} mm do CG vazio"
                     + (f" (asa {fu['volume_in_wing_m3']*1e3:.0f} L, corpo {fu['volume_in_bodies_m3']*1e3:.0f} L)"
                        if fu.get("volume_in_wing_m3") is not None else "")
                     + (f"; carga candidata {py.get('offset_from_empty_cg_m', 0)*1e3:+.0f} mm"
                        if py.get("candidate_centroid_m") else "")
                     + (f"; CG cheio vs lumping no CG vazio {dx*1e3:+.0f} mm" if dx is not None else "")
                     + smt + (f". {fp['issue']}" if fp.get("issue") else "")
                     + f". {fp.get('note', '')}")))
    elif fp.get("status") == "unassessed":
        out.append(("asm:fine_packaging", None, "packaging fino unassessed — " + "; ".join(fp.get("issues") or [])))
    elif fp.get("status") == "error":
        out.append(("asm:fine_packaging", None, f"packaging fino erro: {fp.get('error')}"))
    ph = tl.get("pitch_hold") or {}
    if ph.get("status") == "assessed":
        p_ = ph["phugoid"]
        zt = (f"ζ {p_['zeta']:.3f}, ω {p_['wn']:.3f} rad/s" if p_.get("zeta") == p_.get("zeta") and p_.get("zeta") is not None
              else "raízes reais " + ", ".join(f"{float(r_):.3f}" for r_ in (p_.get("real_roots") or [])) + " 1/s")
        out.append(("hq:phugoid_autopilot", ph["ok"],
                    f"fugóide com manutenção de atitude de picada (piloto automático, caso '{ph['case']}'): {zt} → Nível "
                    f"{ph['level'] if ph['level'] < 4 else '>3'} (N1 ζ ≥ 0,04); célula nua ζ {ph.get('bare_phugoid_zeta', float('nan')):.4f}; "
                    f"k_pθ {ph['k_p_theta']:.3f}, k_dθ {ph['k_d_theta']:.3f} s (autoridade da elevon {ph['elevon_authority_deg']:.1f}°, "
                    f"e_θ,max {ph['e_theta_max_deg']:.0f}° PRESSUPOSTO); período curto em malha fechada ζ "
                    f"{(ph['short_period'] or {}).get('zeta', float('nan')):.3f} ({ph['source'].split(';')[0]})"))
    elif ph.get("status") == "unassessed":
        out.append(("hq:phugoid_autopilot", None, "fugóide com piloto automático unassessed — " + "; ".join(ph.get("issues") or [])))
    ac = tl.get("actuators") or {}
    if ac.get("status") == "assessed":
        parts = []
        for k, nm in (("split_aileron", "split (por folha)"), ("elevon", "elevon")):
            blk = ac.get(k)
            if not blk:
                parts.append(f"{nm}: unassessed")
                continue
            sv = blk.get("servo") or {}
            sp = sv.get("servo") or {}
            pick = (f"{sp['n_per_surface']}× {sp['name']} (G {sp['gearing']:.2f}, {sp['rate_at_surface_deg_s']:.0f} °/s)"
                    if sp else ("NENHUM" if sv.get("ok") is False else "unassessed"))
            parts.append(f"{nm}: |H| {blk['H_max_Nm']:.1f} N·m (23.455), servo {pick}"
                         + (f" — {sv['issue']}" if sv.get("issue") else ""))
        out.append(("hq:actuators", ac.get("ok"), "; ".join(parts)))
        ms = ac.get("mass") or {}
        out.append(("asm:actuator_mass", ms.get("within_budget"),
                    f"atuadores {ms.get('total_known_kg', 0):.2f} kg conhecidos"
                    + (f" (falta {ms['unknown_surfaces']})" if ms.get("unknown_surfaces") else "")
                    + f" vs orçamento declarado {ms.get('budget_declared_kg')} kg ({ms.get('budget_items')})"))
    elif ac:
        out.append(("hq:actuators", None, "atuadores unassessed — " + "; ".join(ac.get("issues") or [])))
    apc = tl.get("approach_consistency") or {}
    if apc.get("cases"):
        worst = apc.get("CLmax_trimmed_min")
        out.append(("hq:pitch_trim_tailless", apc.get("ok"),
                    "equilíbrio de picada com elevon: " + "; ".join(apc.get("issues") or ["ok"])
                    + (f" (C_L máx. equilibrado mín. {worst:.2f})" if worst is not None else "")
                    + _sm_wash_txt(apc)))
    co = tl.get("crosswind_options")
    if co and co.get("status") == "assessed":
        o = co["options"]
        c = o["c_aproximacao_mais_rapida"]
        fc = c.get("first_closing")
        d = o["d_crab_decrab"]
        out.append(("asm:crosswind_options", co.get("any_closes"),
                    f"vento cruzado {co['crosswind_kt']:.1f} kt: (a) split c_f/c→{o['a_split_maior']['cf_c_required_same_span']:.2f} "
                    f"fecha a guinada{'' if o['a_split_maior']['closes'] else ' (elevon continua a falhar)'}; (b) elevon maior: "
                    f"{o['b_elevon_maior'].get('closes')}; (c) aproximação mais rápida: "
                    + (f"fecha a {fc['k']:.1f} V_S0 ({fc['U_m_s']:.1f} m/s, rolagem ×{fc['ground_roll_factor']:.2f})" if fc else "não fecha até 1,6 V_S0")
                    + f"; (d) crab + decrab: resíduo {d['residual_crab_at_touchdown_deg'] if d['residual_crab_at_touchdown_deg'] is not None else float('nan'):.1f}° "
                      f"({d['status']}); (e) tração diferencial: {o['e_tracao_diferencial']['note']}"))
    return out


def _bo_txt(pk) -> str:
    bo = pk.get("bodies_only") or {}
    if bo.get("fits"):
        return f"; só no corpo central: ±{bo['slab_half_width_m']:.2f} m"
    if bo:
        return (f"; só no corpo central NÃO cabe ({bo['volume_within_a_max_m3'] * 1e3:.1f} L a ±{bo['a_max_m']:.2f} m) "
                "— exige tanques nas raízes da asa")
    return ""


def _bias_txt(g: dict) -> str:
    if not g.get("bias_deg"):
        return ""
    bd = g.get("bias_drag") or {}
    dcd = bd.get("dCD0")
    return (f"; pré-deflexão δ0 = {g['bias_deg']:g}° como opção de projeto"
            + (f" (ΔC_D0 {dcd:+.5f} no polar de dimensionamento)" if dcd is not None else " (ΔC_D0 unassessed)")
            + f" — {g.get('bias_source', '')}")


def _gust_opt_txt(g: dict) -> str:
    o = g.get("options")
    if not o:
        return ""
    sv = "; ".join(f"servo {k} ({v['rate_deg_s']:.0f} °/s): {'fecha' if v['ok'] else 'não fecha (%.1f %%)' % (100 * (v['rate_limited_fraction'] or 0))}"
                   for k, v in o["servo_faster"].items())
    bb = o.get("smallest_bias_that_closes_deg")
    bt = (f"pré-deflexão simétrica δ0 = {bb:g}° fecha (ΔC_D cruzeiro +{o['smallest_bias_dCD_over_CD0_pct']:.1f} % de C_D0, "
          "não incluído no dimensionamento)" if bb is not None else "nenhuma pré-deflexão até 10° fecha")
    return f". Opções: {sv}; {bt} ({o['source'].split(',')[0]} et al.)"


def _sm_wash_txt(apc: dict) -> str:
    t = ""
    sb = apc.get("static_margin_band") or {}
    if sb.get("cases"):
        t += ("; margem estática " + ", ".join(f"{k} {v:.3f}" for k, v in sb["cases"].items())
              + " (banda 0,02–0,08 de NACA TR-796)")
    for k, v in (apc.get("cases") or {}).items():
        if (v.get("cruise") or {}).get("elevon_deg") is not None:
            t += f"; δe cruzeiro {k} {v['cruise']['elevon_deg']:+.1f}°"
    wc = apc.get("washout_check") or {}
    pk = wc.get("panknin") or {}
    if pk.get("status") == "assessed":
        t += (f"; torção desenhada {wc['twist_tip_minus_root_deg']:+.1f}° vs Panknin {pk['total_deg']:+.1f}° "
              f"(C_L {wc['CL']:.2f}, σ {wc['static_margin_wing']:.3f})")
    if apc.get("bodies_in_main_trim"):
        t += ("; C_m dos corpos (Torenbeek) no equilíbrio principal"
              + (f" (k = {apc['k_body']:+.4f} c̄)" if apc.get("k_body") is not None else ""))
        av = {k: v["avl_wing"] for k, v in (apc.get("cases") or {}).items() if v.get("avl_wing")}
        if av:
            t += ("; só asa AVL (sensibilidade): δe cruzeiro "
                  + ", ".join(f"{k} {v['cruise_elevon_deg']:+.1f}°" for k, v in av.items())
                  + ", C_L equilibrado (limite da elevon) mín. "
                  + f"{min(v['trimmed_CL_max_elevon_limit'] for v in av.values()):.2f}")
    else:
        wb = {k: v["with_bodies"] for k, v in (apc.get("cases") or {}).items() if v.get("with_bodies")}
        if wb:
            t += ("; com C_m dos corpos (Torenbeek, sensibilidade): δe cruzeiro "
                  + ", ".join(f"{k} {v['cruise_elevon_deg']:+.1f}°" for k, v in wb.items())
                  + ", C_L equilibrado (limite da elevon) mín. "
                  + f"{min(v['trimmed_CL_max_elevon_limit'] for v in wb.values()):.2f}")
    return t
