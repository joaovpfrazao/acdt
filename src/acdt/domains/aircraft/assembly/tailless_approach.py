# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Approach consistency and crosswind fix options of a tailless split-aileron flying wing (follow-up to
:mod:`.tailless`, 10 nov 2026). Nothing here relaxes a requirement: every option is reported with what closes,
what does not and its cost; unknowns stay unassessed.

Methods (cited)
---------------
* **Trim with the elevon (pitch)** — linear trim of the AVL derivatives about each loading-case CG (Etkin & Reid
  1996 Sec. 2.4, the same 2×2 trim as :mod:`..flightsim.controls`): [C_Lα C_Lδe; C_mα C_mδe]·[α; δe] =
  [C_L − C_L0; −C_m0], symmetric elevon = AVL ``CONTROL`` SgnDup +1 on the elevon hinge. Largest trimmed C_L
  with |δe| ≤ δe,max is the end point of the (linear) trimmed C_L(δe).
* **Local stall** — critical-section method (first strip reaching the section c_l,max; Phillips & Alley 2007,
  as in :mod:`..wingbox.optimize`) on the AVL strip c_l at the trimmed point, scaled linearly to the first
  strip at ``clmax_airfoil`` (the user's section value — PRESSUPOSTO linear lift up to it).
* **Flap consistency** — ``CLmax_landing`` of the fixed-type model includes the flap of ``assumptions.aero.flap``
  (Raymer Sec. 12.4); a tailless drawing without a flap surface cannot deliver that increment → flagged.
* **Crosswind** — steady straight sideslip of :func:`.tailless.crosswind_case` (Roskam AFD I Sec. 4.2;
  14 CFR 23.233(a) pré-Amdt 64: "demonstrated to be safe for taxiing, takeoff and landing", ≥ 0,2 V_S0 — the
  rule does not prescribe the sideslip technique). Options:
  (a) bigger split surface: C₁ ∝ (c_f/c)^2.38 at fixed span (McCormick Eq. 3.45 with S_f ∝ c_f) and the span
      fraction of :func:`.tailless.span_required`;
  (b) bigger elevon (roll balance of C_lβ·β), AVL re-run with the elevon extended inboard;
  (c) faster approach U = k·V_S0 (β = atan(V_w/U) drops; AVL re-run at the new C_L); cost: ground roll
      ∝ V_TD² (Raymer 2018 Sec. 17.9, constant mean deceleration — PRESSUPOSTO) and the 14 CFR 23.73 (pré-64)
      reference V_REF ≥ 1,3 V_S0 as context;
  (d) crab approach with the autopilot (β ≈ 0 in the air; UAV — active autopilot is the base hypothesis) and a
      partial decrab limited by the steady-sideslip authority: residual crab at touchdown = β_req − β_max.
      Gear side-load capability and decrab dynamics are not modelled → unassessed (not a pass);
  (e) differential thrust: needs ≥ 2 engines.
"""
from __future__ import annotations

import math

import numpy as np

from . import tailless as T

KT = T.KT
SM_TAILLESS = (0.02, 0.08)
SM_TAILLESS_SOURCE = ("NACA TR-796 (Donlan 1944, 'An interim report on the stability and control of tailless "
                      "airplanes'): margem estática 0,02–0,08 razoável para aviões sem cauda; CG nunca atrás do "
                      "centro aerodinâmico")


def linear_trim(d0: dict, CL: float) -> tuple[float, float]:
    """(α [rad], δe [rad]) for C_L and C_m = 0 from the AVL derivatives at α = 0, δe = 0."""
    M = np.array([[d0["CLa"], d0["CLde"]], [d0["Cma"], d0["Cmde"]]])
    rhs = np.array([CL - d0["CL"], -d0["Cm"]])
    a, de = np.linalg.solve(M, rhs)
    return float(a), float(de)


def body_cm_derivatives(d0: dict, k_body: float) -> dict:
    """Torenbeek fuselage shift of the NP as a moment about the CG: C_m += C_N k, k = −ΔX_np/c̄.

    C_m0 of the bodies: 0 by default (PRESSUPOSTO); the Multhopp estimate (:mod:`.body_moment`) is always
    reported and enters the main trim with ``flying_wing.body_cm0: multhopp``. Same term as the 6-DOF model.
    """
    return {**d0, "Cm": d0["Cm"] + d0["CL"] * k_body, "Cma": d0["Cma"] + d0["CLa"] * k_body,
            "Cmde": d0["Cmde"] + d0["CLde"] * k_body}


def _bodies_cm0_block(asm, d0: dict) -> dict:
    """Multhopp C_m0 of the bodies (:mod:`.body_moment`) with α_0L,f = −C_L0/C_Lα of the AVL wing at δe = 0
    (AVL α is measured from the geometry x axis = the bodies' reference line)."""
    from .body_moment import bodies_cm0
    if not d0.get("CLa"):
        return {"status": "unassessed", "Cm0": None, "issue": "C_Lα do AVL em falta"}
    try:
        return bodies_cm0(asm, math.degrees(-d0["CL"] / d0["CLa"]))
    except Exception as ex:  # pragma: no cover - geometry without bodies / wing
        return {"status": "unassessed", "Cm0": None, "issue": str(ex)}


def trimmed_clmax(d0: dict, de_max: float) -> dict:
    """Largest trimmed C_L with |δe| ≤ δe,max (linear trimmed C_L(δe))."""
    best = None
    for de in (-de_max, de_max):
        a = -(d0["Cm"] + d0["Cmde"] * de) / d0["Cma"]
        cl = d0["CL"] + d0["CLa"] * a + d0["CLde"] * de
        if best is None or cl > best["CL"]:
            best = {"CL": cl, "alpha_deg": math.degrees(a), "elevon_deg": math.degrees(de)}
    return best


def approach_consistency(asm, res, out, spec_fw: dict, el: dict, mach: float, W: float, S: float,
                         CL_approach: float | None, CL_cruise: float, approach_alpha_deg: float | None,
                         *, include_bodies: bool = True) -> dict:
    """Per loading case: elevon to trim cruise and approach C_L, largest trimmed C_L and its critical-section
    limit; flap consistency of CLmax_landing.

    ``include_bodies`` (default True) puts the Torenbeek body Cm term into the *reported* main trim.
    The W0 trimmed-CLmax loop calls this with ``include_bodies=False``: C_m0 of the bodies is 0
    (PRESSUPOSTO), so that term is not taken as a CLmax credit that would shrink the wing.
    """
    from acdt.core.atmosphere import isa
    from acdt import G0
    el_max = float(el.get("max_deg") or T.ELEVON_MAX_DEFAULT_DEG)
    clmax_sec = (res.spec.assumptions.get("aero") or {}).get("clmax_airfoil")
    rep = {"method": "trim linear AVL com elevon simétrico (Etkin & Reid 2.4) + secção crítica (Phillips & Alley "
                     "2007) com clmax_airfoil do utilizador", "issues": [], "cases": {}}
    flap = (res.spec.assumptions.get("aero") or {}).get("flap")
    clt = (res.spec.assumptions.get("aero") or {}).get("CLmax_trimmed")
    if isinstance(flap, dict) and str(flap.get("kind", "plain")).lower() == "none":
        flap = None
    hl = getattr(res, "highlift", None)
    if clt:
        rep["CLmax_trimmed_used"] = float(clt)
        rep["flap_note"] = (f"CLmax de dimensionamento = CLmax equilibrado {float(clt):.3f} (flying_wing.clmax: trimmed); "
                            "o flap de assumptions.aero não entra")
    elif flap and hl is not None:
        rep["flap_note"] = (f"CLmax_landing {hl.CLmax_landing:.2f} (tipo fixo) inclui o flap {flap} de assumptions.aero; "
                            "o desenho sem deriva não tem flap (só elevons e split ailerons) — esse incremento não "
                            "existe na asa desenhada")
        rep["issues"].append("CLmax_landing inclui um flap que o desenho não tem — V_S0 e o caso de aproximação são "
                             "otimistas (usar o C_L máximo equilibrado)")
    if approach_alpha_deg is not None:
        rep["approach_alpha_untrimmed_deg"] = approach_alpha_deg
    cases = ((out.loading or {}).get("cases") or {}) if hasattr(out, "loading") else {}
    rho0 = isa(0.0).rho
    npd = getattr(out, "np", None) or {}
    k_body = None
    try:
        from .sizing import main_wing
        mac = main_wing(asm)[1]["mac"]
        if npd.get("x_np_no_bodies") is not None and npd.get("x_np_torenbeek") is not None and mac:
            k_body = -(npd["x_np_torenbeek"] - npd["x_np_no_bodies"]) / mac
    except Exception:  # pragma: no cover
        k_body = None
    if k_body is not None:
        rep["k_body"] = k_body
        if include_bodies:
            rep["bodies_note"] = ("C_m dos corpos no equilíbrio principal: desvio Torenbeek do ponto neutro "
                                  f"(k = {k_body:+.4f} c̄, C_m += C_N k; o mesmo termo da margem estática e do 6-DOF); "
                                  "C_m0 dos corpos = 0 (PRESSUPOSTO). O trim só com a asa AVL fica em 'avl_wing' "
                                  "(sensibilidade). O laço W0 do CLmax equilibrado não usa este termo como crédito "
                                  "(sem ele a asa encolhia e a rolagem de descolagem excedia 300 m).")
            rep["bodies_in_main_trim"] = True
        else:
            rep["bodies_note"] = ("C_m dos corpos omitido neste cálculo (laço W0 do CLmax): C_m0 = 0 PRESSUPOSTO, "
                                  "sem crédito de CLmax")
            rep["bodies_in_main_trim"] = False
    else:
        rep["bodies_in_main_trim"] = False
    cm0_mode = str((spec_fw or {}).get("body_cm0", "zero")).lower()
    if cm0_mode not in ("zero", "multhopp"):
        raise ValueError("flying_wing.body_cm0: 'zero' (PRESSUPOSTO, omissão) ou 'multhopp'")
    cm0_blk: dict | None = None
    for name, cs in cases.items():
        xcg, zcg = float(cs["cg"][0]), float(cs["cg"][2])
        m = float(cs["mass_kg"])
        try:
            d0 = T.avl_elevon_point(asm, mach, xcg, zcg, el, alpha_deg=0.0)
        except Exception as ex:  # pragma: no cover - AVL failure
            rep["cases"][name] = {"status": "error", "error": str(ex)}
            continue
        Wc = m * G0
        use_bodies = include_bodies and k_body is not None
        d_main = body_cm_derivatives(d0, k_body) if use_bodies else d0
        if cm0_blk is None and include_bodies:
            cm0_blk = _bodies_cm0_block(asm, d0)
            rep["bodies_cm0"] = cm0_blk
        cm0_b = (cm0_blk or {}).get("Cm0")
        cm0_in_trim = bool(use_bodies and cm0_mode == "multhopp" and cm0_b is not None)
        if cm0_in_trim:
            d_main = {**d_main, "Cm": d_main["Cm"] + cm0_b}
        row = {"mass_kg": m, "x_cg": xcg,
               "static_margin": (d_main["CLa"] and -d_main["Cma"] / d_main["CLa"]),
               "CL0": d_main["CL"], "Cm0": d_main["Cm"], "CLde": d_main["CLde"], "Cmde": d_main["Cmde"],
               "bodies_in_trim": use_bodies, "bodies_cm0_in_trim": cm0_in_trim}
        a_c, de_c = linear_trim(d_main, CL_cruise * Wc / W)
        row["cruise"] = {"CL": CL_cruise * Wc / W, "alpha_deg": math.degrees(a_c), "elevon_deg": math.degrees(de_c),
                         "ok": abs(math.degrees(de_c)) <= el_max}
        if CL_approach is not None:
            CLa_ = CL_approach * Wc / W
            a_a, de_a = linear_trim(d_main, CLa_)
            row["approach"] = {"CL": CLa_, "alpha_deg": math.degrees(a_a), "elevon_deg": math.degrees(de_a),
                               "ok": abs(math.degrees(de_a)) <= el_max}
        tm = trimmed_clmax(d_main, math.radians(el_max))
        if clmax_sec:
            try:
                dp = T.avl_elevon_point(asm, mach, xcg, zcg, el, alpha_deg=tm["alpha_deg"], sym_deg=tm["elevon_deg"],
                                        strips=True)
                cl_peak = max(s["cl"] for s in dp["strips"])
                tm["strip_cl_peak"] = cl_peak
                if cl_peak > float(clmax_sec) and dp["CL"] > 0:
                    # first strip at clmax: scale the untrimmed-by-α part linearly (PRESSUPOSTO)
                    tm["CL_critical_section"] = dp["CL"] * float(clmax_sec) / cl_peak
                else:
                    tm["CL_critical_section"] = dp["CL"]
            except Exception as ex:  # pragma: no cover
                tm["critical_section_error"] = str(ex)
        cl_eff = min(tm["CL"], tm.get("CL_critical_section", tm["CL"]))
        tm["CL_max_effective"] = cl_eff
        tm["V_min_trimmed_m_s"] = math.sqrt(2 * Wc / (rho0 * S * cl_eff)) if cl_eff > 0 else None
        row["trimmed_max"] = tm
        if include_bodies and k_body is not None:
            # Main trim already includes bodies. Keep the AVL-wing-only trim as a sensitivity.
            wb = {"k": k_body, "in_main_trim": True,
                  "cruise_elevon_deg": row["cruise"]["elevon_deg"]}
            if "approach" in row:
                wb["approach_elevon_deg"] = row["approach"]["elevon_deg"]
            wb["trimmed_CL_max_elevon_limit"] = tm["CL"]
            a_w, de_w = linear_trim(d0, CL_cruise * Wc / W)
            av = {"cruise_elevon_deg": math.degrees(de_w),
                  "trimmed_CL_max_elevon_limit": trimmed_clmax(d0, math.radians(el_max))["CL"]}
            if CL_approach is not None:
                av["approach_elevon_deg"] = math.degrees(linear_trim(d0, CL_approach * Wc / W)[1])
            row["with_bodies"] = wb
            row["avl_wing"] = av
            if cm0_b is not None:
                # sensitivity: the other choice of body C_m0 (Multhopp if the main trim uses 0, and vice-versa)
                d_alt = {**d_main, "Cm": d_main["Cm"] + (-cm0_b if cm0_in_trim else cm0_b)}
                alt = {"body_cm0": 0.0 if cm0_in_trim else cm0_b,
                       "cruise_elevon_deg": math.degrees(linear_trim(d_alt, CL_cruise * Wc / W)[1]),
                       "trimmed_CL_max_elevon_limit": trimmed_clmax(d_alt, math.radians(el_max))["CL"]}
                if CL_approach is not None:
                    alt["approach_elevon_deg"] = math.degrees(linear_trim(d_alt, CL_approach * Wc / W)[1])
                    alt["approach_ok"] = abs(alt["approach_elevon_deg"]) <= el_max
                alt["cruise_ok"] = abs(alt["cruise_elevon_deg"]) <= el_max
                row["body_cm0_alternative"] = alt
        rep["cases"][name] = row
    if cm0_blk is not None:
        cm0_blk["mode"] = cm0_mode
        cm0_blk["in_main_trim"] = bool(include_bodies and k_body is not None and cm0_mode == "multhopp"
                                       and cm0_blk.get("Cm0") is not None)
        if not cm0_blk["in_main_trim"]:
            cm0_blk["note"] = ("C_m0 dos corpos de Multhopp reportado como sensibilidade ('body_cm0_alternative' por "
                               "caso); o equilíbrio principal usa C_m0 = 0 (PRESSUPOSTO). flying_wing.body_cm0: "
                               "multhopp usa-o no equilíbrio principal")
        else:
            cm0_blk["note"] = ("C_m0 dos corpos de Multhopp no equilíbrio principal; a sensibilidade com C_m0 = 0 "
                               "fica em 'body_cm0_alternative'. O laço W0 do CLmax continua sem termo dos corpos")
    bad_cr = [k for k, v in rep["cases"].items() if v.get("cruise") and not v["cruise"]["ok"]]
    bad_ap = [k for k, v in rep["cases"].items() if v.get("approach") and not v["approach"]["ok"]]
    if bad_cr:
        rep["issues"].append(f"cruzeiro NÃO equilibrável com elevon ≤ {el_max:.0f}° nos casos {bad_cr} (margem estática "
                             "da montagem nesses casos) — rever centragem/reflexo antes de confiar nas derivadas laterais")
    if bad_ap:
        rep["issues"].append(f"aproximação (C_L do CLmax_landing/1,21) NÃO equilibrável com elevon ≤ {el_max:.0f}° nos "
                             f"casos {bad_ap}")
    # static-margin band of tailless aeroplanes (NACA TR-796, Donlan 1944: "a range of ultimate static margin
    # from 0.02 to 0.08 appears to be reasonable"; never negative) — information next to the trim result
    sm = dict(getattr(out, "static_margin", None) or {})
    if sm:
        outside = {k: v for k, v in sm.items() if not (SM_TAILLESS[0] - 1e-3 <= v <= SM_TAILLESS[1] + 1e-3)}
        rep["static_margin_band"] = {"cases": sm, "band": list(SM_TAILLESS), "outside": outside,
                                     "source": SM_TAILLESS_SOURCE}
        if outside:
            rep["issues"].append("margem estática fora da banda 0,02–0,08 de NACA TR-796 nos casos "
                                 + ", ".join(f"{k} {v:.2f}" for k, v in outside.items()))
    hlm = hl.CLmax_landing if hl is not None else None
    worst = [v["trimmed_max"]["CL_max_effective"] for v in rep["cases"].values() if v.get("trimmed_max")]
    if hlm and worst:
        rep["CLmax_landing_declared"] = hlm
        rep["CLmax_trimmed_min"] = min(worst)
        if min(worst) < hlm - 0.01:
            rep["issues"].append(f"C_L máximo equilibrado (mín. {min(worst):.2f}) < CLmax_landing {hlm:.2f}: o α ≈ "
                                 f"{approach_alpha_deg or float('nan'):.0f}° da aproximação é o sintoma — pede C_L "
                                 "que a asa equilibrada não dá")
    rep["ok"] = not (bad_cr or bad_ap or (hlm and worst and min(worst) < hlm - 0.01))
    return rep


def crosswind_options(asm, d_ap: dict, ap: dict, cw: dict, geom: dict | None, C1: float | None, dmax: float | None,
                      el: dict, el_max: float, K_f: float, mach: float, x_cg: float, z_cg: float, cnb_body: float,
                      n_engines: int, gear_side_load: dict | None = None) -> dict:
    """Fix options for a failing steady-sideslip crosswind case (see module docstring)."""
    out = {"requirement": cw.get("fonte"), "crosswind_kt": cw.get("crosswind_kt"), "options": {}}
    if cw.get("status") != "assessed" or C1 is None or geom is None:
        out["status"] = "unassessed"
        return out
    req = abs(cw["dCn_required"])
    s2 = math.sin(math.radians(dmax)) ** 2
    # (a) bigger split surface
    C1_req = req / (2 * s2)
    cf_req = geom["cf_c"] * (C1_req / C1) ** (1 / 2.38) if C1_req > C1 else geom["cf_c"]
    sr = T.span_required(asm, req, geom["eta_outer"], geom["cf_c"], dmax, K_f)
    out["options"]["a_split_maior"] = {
        "cf_c_required_same_span": cf_req, "span_fraction_required_same_cf": sr,
        "eta_inner_required": (geom["eta_outer"] - sr) if sr is not None else None,
        "overlaps_elevon": (sr is not None and geom["eta_outer"] - sr < float(el["eta_outer"]) - 1e-9),
        "closes_yaw": True, "closes": bool(cw.get("elevon_ok")),
        "note": "fecha a guinada; não resolve a elevon (rolamento) se esta também falha",
        "cost": f"C₁ ∝ (c_f/c)^2,38: c_f/c {geom['cf_c']:.2f} → {cf_req:.2f}; massa/charneira crescem com S_f·c_f "
                "(ver actuators)", "source": "McCormick 1995 Eq. 3.45 (S_f ∝ c_f)"}
    # (b) bigger elevon: extend inboard to the root region
    da_need = abs(cw["delta_a_deg"])
    b_opt = {"delta_a_required_deg": da_need, "elevon_max_deg": el_max, "closes": None}
    if da_need > el_max:
        el2 = dict(el)
        el2["eta_inner"] = max(0.05, float(el["eta_inner"]) - 0.15)
        try:
            d2 = T.avl_with_elevon(asm, ap["CL"], mach, x_cg, z_cg, el2)
            d2["Cnb"] += cnb_body
            c2 = T.crosswind_case(d2, ap["CL"], ap["U"], cw["crosswind_m_s"], C1, dmax, el_max)
            b_opt.update({"elevon_tested": {k: el2[k] for k in ("eta_inner", "eta_outer", "cf_c")},
                          "delta_a_deg": c2["delta_a_deg"], "delta_split_deg": c2.get("delta_split_deg"),
                          "closes_roll": c2["elevon_ok"], "closes": bool(c2.get("ok")),
                          "source": "AVL (elevon prolongada para dentro) + Roskam AFD I 4.2"})
        except Exception as ex:  # pragma: no cover
            b_opt["error"] = str(ex)
    else:
        b_opt["closes"] = True
    out["options"]["b_elevon_maior"] = b_opt
    # (c) faster approach
    sweep = []
    closes_k = None
    for k in (1.1, 1.2, 1.3, 1.4, 1.5, 1.6):
        U = k * ap["V_S0"]
        CL = ap["CL"] * (ap["U"] / U) ** 2
        try:
            dk = T.avl_with_elevon(asm, CL, mach * U / ap["U"], x_cg, z_cg, el)
        except Exception as ex:  # pragma: no cover
            sweep.append({"k": k, "error": str(ex)})
            continue
        dk["Cnb"] += cnb_body
        ck = T.crosswind_case(dk, CL, U, cw["crosswind_m_s"], C1, dmax, el_max)
        row = {"k": k, "U_m_s": U, "CL": CL, "alpha_deg": dk["alpha_deg"], "beta_deg": ck["beta_deg"],
               "delta_split_deg": ck.get("delta_split_deg"), "delta_a_deg": ck["delta_a_deg"], "ok": ck["ok"],
               "ground_roll_factor": (k / 1.1) ** 2,
               "within_side_effect_envelope": dk["alpha_deg"] <= T.ATTACHED_FLOW_ALPHA_MAX_DEG
               and ck["beta_deg"] <= 10.0}
        sweep.append(row)
        if ck["ok"] and closes_k is None:
            closes_k = row
    out["options"]["c_aproximacao_mais_rapida"] = {
        "sweep": sweep, "closes": closes_k is not None, "first_closing": closes_k,
        "cost": ("rolagem no solo ∝ V_TD² (Raymer 2018 Sec. 17.9, desaceleração média constante — PRESSUPOSTO); "
                 "14 CFR 23.73 (pré-64): V_REF ≥ 1,3 V_S0 como contexto"),
        "note": "derivadas AVL à mesma CG e sem equilíbrio de picada (ver approach_consistency)"}
    # (d) crab + partial decrab
    bmax = math.degrees(math.atan2(cw["crosswind_max_kt"] * KT, ap["U"])) if cw.get("crosswind_max_kt") else None
    resid = (cw["beta_deg"] - bmax) if bmax is not None else None
    gs = gear_side_load or {}
    out["options"]["d_crab_decrab"] = {
        "crab_angle_deg": cw["beta_deg"], "beta_max_steady_deg": bmax,
        "residual_crab_at_touchdown_deg": max(resid, 0.0) if resid is not None else None,
        "gear_side_load_limit": gs or None,
        "closes": None if resid is not None and resid > 0 else True,
        "status": "unassessed" if resid is not None and resid > 0 else "assessed",
        "note": ("aproximação em crab com piloto automático (UAV: hipótese base): β ≈ 0 no ar, sem exigência de "
                 "guinada até ao toque; decrab parcial até β_max da derrapagem estabilizada. Resíduo de crab no toque "
                 "→ carga lateral no trem e dinâmica do decrab não modeladas → unassessed (≠ pass)"),
        "source": "14 CFR 23.233(a) não impõe a técnica (derrapagem vs crab); Roskam AFD I 4.2 para β_max"}
    out["options"]["e_tracao_diferencial"] = {
        "closes": False if n_engines < 2 else None,
        "note": "um só motor — não aplicável" if n_engines < 2 else "≥ 2 motores: C_n por tração diferencial unassessed"}
    out["status"] = "assessed"
    out["any_closes"] = any(o.get("closes") is True for o in out["options"].values())
    return out
