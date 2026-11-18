# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Options to close a take-off ground-roll requirement the 6-DOF mission misses (16 nov 2026).

No silent fix: each option is evaluated with the same integrated ground roll and reported with what it buys, what it
costs and whether it closes. The aeroplane in the result is never changed here.

Ground roll (point mass): m dV/dt = T cos θ − D − μ (W − L − T sin θ) integrated from rest to lift-off (Raymer 2018
Sec. 17.8 force balance; μ = 0.04 dry concrete/asphalt, Raymer Table 17.1), with the forces of the
flight model (AVL tables, propeller map at full throttle). Two lift-off rules, the same as the mission:

* fly-off stance (``gear.ground_attitude_deg`` > 0): the roll is at the stance attitude θ_g with the elevon trimming
  C_m = 0; lift-off at V_LOF = √(2W/(ρ S C_L,trim)) (Sadraey 2012 Sec. 9.6.2, exception of aircraft that do not
  rotate; :mod:`.tailless_takeoff`);
* rotation: roll at θ = 0 with δe = 0; lift-off at V_LOF = 1.1 V_S (Raymer 2018 Sec. 17.8).

Wind along the runway: aerodynamic forces and thrust use the airspeed V_a = V_g + V_hw, the distance is ∫ V_g dt
(PRESSUPOSTO de método: vento uniforme, sem gradiente junto ao solo).

Transfer to the 6-DOF: the 6-DOF ground roll differs from the point mass (throttle ramp, steering and split/rudder
drag in crosswind, gear dynamics). Each option's 6-DOF roll is estimated as the point-mass roll of the option times
the measured ratio k = S_6DOF / S_massa_pontual at the mission's own wind (PRESSUPOSTO: k constant across options).
When a re-run callable is given, the still-air 6-DOF roll is flown, and the headwind and thrust options are re-flown
on the 6-DOF (take-off alone) with the ratio corrected by each measured roll until the 6-DOF closes (≤ 4 flights);
their verdict is then the 6-DOF one. Wing area and mass stay point-mass estimates through k.

Options (all generic):

* ``a_vento_de_frente`` — runway heading / wind component: headwind V_hw needed; with the mission wind V_w this sets
  the angle χ between wind and runway (cos χ = V_hw/V_w) and the crosswind left (V_w sin χ). Operational: the 90°
  crosswind capability of 14 CFR 23.233(a) (≥ 0.2 V_S0) is still demonstrated separately.
* ``b_tracao`` — installed thrust factor needed (same integration); engine mass growth
  not iterated (PRESSUPOSTO, reported).
* ``c_carga_alar`` — wing area factor (W/S down at the same mass): aerodynamic forces ∝ S; wing mass/drag growth not
  iterated (PRESSUPOSTO).
* ``d_massa`` — take-off mass reduction at the same S and thrust (W/S and T/W together).
* ``e_atitude`` — larger stance attitude θ_g (higher C_L at lift-off): limited by the elevon trim, V_LOF ≥ 1.1 V_S
  (Raymer 17.8) and the aft clearance of the mission (α_C, Sadraey 2012 Sec. 9.5.1.3) — fly-off only.
* ``f_catapulta`` — no ground roll; closes only if the opt-in ``launch_recovery.catapult`` was assessed with the
  end speed met (Fahlstrom, Gleason & Sadraey 2022 Ch. 17), otherwise unassessed.
* ``g_vento_cruzado_menor`` — demonstrating less crosswind: not admissible below 0.2 V_S0 (14 CFR 23.233(a),
  pré-Amdt 64); the still-air roll is shown for context only.
"""
from __future__ import annotations

import math

from .tailless_takeoff import MU_ROLL, _coeffs

G0 = 9.80665
SOURCE = ("Raymer 2018 Sec. 17.8 (V_TO = 1,1 V_S, μ Table 17.1); Sadraey 2012 Sec. 9.6.2 (atitude de "
          "descolagem sem rotação) e Sec. 9.5.1.3 (folga traseira); 14 CFR 23.233(a) pré-Amdt 64 (vento cruzado "
          "≥ 0,2 V_S0); Fahlstrom, Gleason & Sadraey 2022 Ch. 17 (catapulta)")
FACTOR_SOURCE = ("PRESSUPOSTO: razão 6-DOF/massa pontual medida no vento da missão, mantida constante entre opções")


def wind_components(wind: dict | None, heading_deg: float) -> tuple[float, float]:
    """(headwind, crosswind) [m/s] of a wind ``{speed_m_s, from_deg}`` on a runway heading."""
    if not wind:
        return 0.0, 0.0
    V = float(wind.get("speed_m_s", 0.0) or 0.0)
    d = math.radians(float(wind.get("from_deg", 0.0) or 0.0) - float(heading_deg))
    hw, cw = V * math.cos(d), abs(V * math.sin(d))
    return (0.0 if abs(hw) < 1e-9 else hw), (0.0 if cw < 1e-9 else cw)


def ground_roll(fm, *, theta_deg: float = 0.0, fly_off: bool = True, rho: float = 1.225, thrust_factor: float = 1.0,
                S_factor: float = 1.0, mass_factor: float = 1.0, headwind: float = 0.0, mu: float = MU_ROLL,
                dt: float = 0.01) -> dict:
    """Point-mass ground roll of the flight model ``fm`` (see module docstring). Returns distance, V_LOF, V_S."""
    a, m = fm.aero, fm.mass.m * mass_factor
    W = m * G0
    S = a.S * S_factor
    th = math.radians(theta_deg)
    Vs = math.sqrt(2 * W / (rho * S * a.CLmax[0]))
    if fly_off:
        c0 = _coeffs(a, th, 0.0, fm.mass.x_cg)
        cmde = a._interp("Cmde", th, 0.0)
        de = -c0["Cm"] / cmde if abs(cmde) > 1e-12 else 0.0
        c = _coeffs(a, th, de, fm.mass.x_cg)
        if c["CL"] <= 0:
            return {"ground_roll_m": math.inf, "V_LOF_m_s": None, "V_S_m_s": Vs, "de_trim_deg": math.degrees(de)}
        Vlof = math.sqrt(2 * W / (rho * S * c["CL"]))
    else:
        de = 0.0
        c = _coeffs(a, th, 0.0, fm.mass.x_cg)
        Vlof = 1.1 * Vs
    Vg, x = 0.0, 0.0
    t = 0.0
    while Vg + headwind < Vlof:
        Va = max(Vg + headwind, 0.0)
        q = 0.5 * rho * Va * Va
        T, _ = fm.prop.thrust(Va, 0.0, 1.0)
        T *= thrust_factor
        N = max(W - q * S * c["CL"] - T * math.sin(th), 0.0)
        acc = (T * math.cos(th) - q * S * c["CD"] - mu * N) / m
        if acc <= 1e-3:
            return {"ground_roll_m": math.inf, "V_LOF_m_s": Vlof, "V_S_m_s": Vs, "de_trim_deg": math.degrees(de)}
        Vg += acc * dt
        x += Vg * dt
        t += dt
        if t > 600:
            return {"ground_roll_m": math.inf, "V_LOF_m_s": Vlof, "V_S_m_s": Vs, "de_trim_deg": math.degrees(de)}
    return {"ground_roll_m": float(x), "V_LOF_m_s": float(Vlof), "V_S_m_s": float(Vs), "VLOF_over_VS": Vlof / Vs,
            "de_trim_deg": math.degrees(de), "CL_LOF": float(c["CL"]), "t_s": t}


def _solve(f, lo: float, hi: float, target: float, n: int = 40) -> float | None:
    """Smallest x in [lo, hi] with f(x) ≤ target, f decreasing in x (bisection). None when f(hi) > target."""
    if f(hi) > target:
        return None
    if f(lo) <= target:
        return lo
    for _ in range(n):
        mid = 0.5 * (lo + hi)
        if f(mid) <= target:
            hi = mid
        else:
            lo = mid
    return hi


def _verify_6dof(pm, lo: float, hi: float, x0: float, req_m: float, run6, n: int = 4) -> dict:
    """Re-fly the option on the 6-DOF and correct the transfer ratio with the measured roll: x_{i+1} solves
    pm(x) ≤ req / k_i with k_i = S_6DOF(x_i) / pm(x_i) (at most ``n`` flights). Returns the history and the
    first 6-DOF-verified value (None when it does not close inside [lo, hi])."""
    hist, x = [], x0
    for _ in range(n):
        s6 = run6(x)
        p_ = pm(x)
        hist.append({"x": x, "ground_roll_6dof_m": s6, "point_mass_m": p_})
        if s6 is None or not math.isfinite(p_) or p_ <= 0:
            return {"history": hist, "x_closing": None, "closes": None}
        if s6 <= req_m:
            return {"history": hist, "x_closing": x, "closes": True, "ground_roll_6dof_m": s6}
        x_new = _solve(pm, lo, hi, req_m / (s6 / p_))
        if x_new is None or abs(x_new - x) < 1e-6:
            break
        x = x_new
    return {"history": hist, "x_closing": None, "closes": False}


def assess(fm, seg: dict, req_m: float, *, wind: dict | None = None, heading_deg: float = 0.0,
           aft: dict | None = None, catapult: dict | None = None, rerun=None) -> dict:
    """Options table for a 6-DOF take-off segment ``seg`` (metrics of :meth:`MissionRunner.seg_takeoff`) that misses
    ``req_m``. ``aft``: mission ``aft_clearance`` (α_C limit), ``catapult``: ``res.launch_recovery['catapult']``,
    ``rerun(heading_deg, wind) -> ground_roll_m``: optional 6-DOF re-flight of the take-off alone."""
    gear = fm.mass.gear or {}
    th0 = float(gear.get("ground_attitude_deg") or 0.0)
    fly = th0 > 0.0
    s6 = seg.get("ground_roll_m")
    out = {"schema": "takeoff_options", "source": SOURCE, "requirement_m": float(req_m), "mode":
           "fly_off" if fly else "rotation", "ground_attitude_deg": th0, "options": {}}
    if s6 is None or not math.isfinite(s6):
        out.update({"status": "unassessed", "issue": "corrida 6-DOF sem descolagem"})
        return out
    hw, cw = wind_components(wind, heading_deg)
    kw = dict(theta_deg=th0, fly_off=fly)
    base = ground_roll(fm, headwind=hw, **kw)
    still = ground_roll(fm, **kw)
    if not math.isfinite(base["ground_roll_m"]) or base["ground_roll_m"] <= 0:
        out.update({"status": "unassessed", "issue": "corrida de massa pontual não fecha"})
        return out
    k = float(s6) / base["ground_roll_m"]
    target = float(req_m) / k          # point-mass roll that maps onto the requirement
    out.update({"status": "assessed", "ground_roll_6dof_m": float(s6), "gap_m": float(s6) - float(req_m),
                "wind_headwind_m_s": hw, "wind_crosswind_m_s": cw,
                "point_mass": {"mission_wind_m": base["ground_roll_m"], "still_air_m": still["ground_roll_m"],
                               "V_LOF_m_s": base["V_LOF_m_s"], "V_S_m_s": base["V_S_m_s"]},
                "k_6dof_over_point_mass": k, "k_source": FACTOR_SOURCE,
                "point_mass_target_m": target})
    if rerun is not None:
        try:
            s_still = rerun(heading_deg, None)
            out["ground_roll_6dof_still_air_m"] = s_still
            if s_still:
                out["crosswind_penalty_m"] = float(s6) - s_still
        except Exception as ex:  # pragma: no cover
            out["rerun_issue"] = f"6-DOF em ar calmo falhou: {ex}"
    O = out["options"]
    # (a) headwind component (runway heading)
    f_hw = lambda v: ground_roll(fm, headwind=v, **kw)["ground_roll_m"]   # noqa: E731
    v_need = _solve(f_hw, hw, hw + 15.0, target)
    a_ = {"headwind_required_m_s": v_need, "source": "Raymer 2018 Sec. 17.8 com V_ar = V_solo + V_frente (PRESSUPOSTO)",
          "note": ("operacional: escolha da pista face ao vento; a capacidade de 90° de 14 CFR 23.233(a) continua a "
                   "ser demonstrada à parte")}
    Vw = float((wind or {}).get("speed_m_s", 0.0) or 0.0)
    if v_need is not None:
        S_pm = f_hw(v_need)
        a_["ground_roll_est_m"] = S_pm * k
        if Vw > 0 and v_need <= Vw + 1e-9:
            chi = math.degrees(math.acos(max(-1.0, min(1.0, v_need / Vw))))
            a_.update({"wind_to_runway_angle_max_deg": chi, "crosswind_left_m_s": Vw * math.sin(math.radians(chi))})
            a_["closes"] = True
            if rerun is not None and wind:
                frm = float(wind.get("from_deg", 0.0))

                def run_hw(v):
                    c_ = max(-1.0, min(1.0, v / Vw))
                    return rerun(frm - math.degrees(math.acos(c_)), wind)
                try:
                    vr = _verify_6dof(f_hw, hw, Vw, v_need, req_m, run_hw)
                    a_["check_6dof"] = vr
                    a_["closes"] = vr["closes"]
                    if vr["closes"]:
                        v6 = vr["x_closing"]
                        chi6 = math.degrees(math.acos(max(-1.0, min(1.0, v6 / Vw))))
                        a_.update({"headwind_required_6dof_m_s": v6, "wind_to_runway_angle_max_6dof_deg": chi6,
                                   "heading_deg_6dof": frm - chi6,
                                   "crosswind_left_6dof_m_s": Vw * math.sin(math.radians(chi6))})
                except Exception as ex:  # pragma: no cover
                    a_["check_6dof"] = {"issue": str(ex)}
        else:
            a_["closes"] = None if Vw <= 0 else False
            a_["note"] += ("; o vento da missão não chega a esse componente" if Vw > 0 else
                           "; sem vento na missão — depende do vento do local (unassessed)")
    else:
        a_["closes"] = False
    O["a_vento_de_frente"] = a_
    # (b) thrust
    f_t = lambda x: ground_roll(fm, headwind=hw, thrust_factor=x, **kw)["ground_roll_m"]   # noqa: E731
    x_t = _solve(f_t, 1.0, 2.0, target)
    O["b_tracao"] = {"thrust_factor_required": x_t, "closes": x_t is not None,
                     "ground_roll_est_m": (f_t(x_t) * k) if x_t else None,
                     "cost": "massa do motor/hélice e consumo não iterados (PRESSUPOSTO) — novo ciclo W0 necessário",
                     "source": "Raymer 2018 Sec. 17.8"}
    if rerun is not None and x_t is not None:
        try:
            vr = _verify_6dof(f_t, 1.0, 2.0, x_t, req_m, lambda x: rerun(heading_deg, wind, thrust_factor=x))
            O["b_tracao"]["check_6dof"] = vr
            O["b_tracao"]["closes"] = vr["closes"]
            if vr["closes"]:
                O["b_tracao"]["thrust_factor_required_6dof"] = vr["x_closing"]
        except Exception as ex:  # pragma: no cover
            O["b_tracao"]["check_6dof"] = {"issue": str(ex)}
    # (c) wing loading (S up, same mass)
    f_s = lambda x: ground_roll(fm, headwind=hw, S_factor=x, **kw)["ground_roll_m"]   # noqa: E731
    x_s = _solve(f_s, 1.0, 1.6, target)
    O["c_carga_alar"] = {"S_factor_required": x_s, "WS_factor": (1.0 / x_s) if x_s else None, "closes": x_s is not None,
                         "ground_roll_est_m": (f_s(x_s) * k) if x_s else None,
                         "cost": "massa e arrasto da asa maiores não iterados (PRESSUPOSTO); C_L de cruzeiro desce",
                         "source": "Raymer 2018 Sec. 17.8"}
    # (d) take-off mass
    f_m = lambda x: ground_roll(fm, headwind=hw, mass_factor=x, **kw)["ground_roll_m"]   # noqa: E731
    lo_m = 0.6
    x_m = None
    if f_m(lo_m) <= target:
        hi_, lo_ = 1.0, lo_m        # f increases with mass: largest mass factor that closes
        for _ in range(40):
            mid = 0.5 * (hi_ + lo_)
            if f_m(mid) <= target:
                lo_ = mid
            else:
                hi_ = mid
        x_m = lo_
    O["d_massa"] = {"mass_factor_max": x_m, "mass_reduction_kg": (fm.mass.m * (1 - x_m)) if x_m else None,
                    "closes": x_m is not None, "ground_roll_est_m": (f_m(x_m) * k) if x_m else None,
                    "cost": "menos combustível/carga útil → menos autonomia ou payload (requisito)",
                    "source": "Raymer 2018 Sec. 17.8"}
    # (e) stance attitude
    if fly:
        a = fm.aero
        lim = math.degrees(a.limits["elevator"])
        a_st = math.degrees(a.alpha_stall(0.0)[0])
        a_c = None
        if aft and aft.get("status") == "assessed":
            a_c = aft.get("alpha_C_compressed_deg", aft.get("alpha_C_deg"))
        rows, first = [], None
        th = th0
        while th <= th0 + 6.0 + 1e-9:
            r = ground_roll(fm, headwind=hw, theta_deg=th, fly_off=True)
            ok_de = abs(r["de_trim_deg"]) <= lim + 1e-9
            ok_v = (r.get("VLOF_over_VS") or 0.0) >= 1.1 - 1e-9
            ok_c = None if a_c is None else bool(th < a_c)
            row = {"theta_deg": th, "ground_roll_est_m": r["ground_roll_m"] * k, "VLOF_over_VS": r.get("VLOF_over_VS"),
                   "de_trim_deg": r["de_trim_deg"], "stall_margin_deg": a_st - th,
                   "elevon_ok": ok_de, "vlof_ok": ok_v, "aft_ok": ok_c}
            rows.append(row)
            if first is None and row["ground_roll_est_m"] <= req_m and ok_de and ok_v and ok_c is not False:
                first = row
            th = round(th + 0.5, 6)
        O["e_atitude"] = {"sweep": rows, "first_closing": first,
                          "closes": (None if first is not None and first["aft_ok"] is None else first is not None),
                          "alpha_C_deg": a_c,
                          "cost": "perna do nariz mais longa (massa, Raymer Eq. 15.51); folga traseira e hélice menores",
                          "source": "Sadraey 2012 Sec. 9.6.2 / 9.5.1.3; Raymer 2018 Sec. 17.8 (V_LOF ≥ 1,1 V_S)"}
    else:
        O["e_atitude"] = {"closes": None, "note": "modo com rotação: C_L de descolagem pela rotação, não pela atitude"}
    # (f) catapult
    cat = catapult or {}
    if cat:
        ok = cat.get("speed_ok")
        O["f_catapulta"] = {"closes": True if ok else (None if ok is None else False), "ground_roll_m": 0.0,
                            "stroke_m": cat.get("stroke_m"), "n_x_g": cat.get("n_x_g"),
                            "cost": "lançador no solo, cargas de lançamento na célula; muda o conceito de operação",
                            "source": "Fahlstrom, Gleason & Sadraey 2022 Ch. 17 (launch_recovery.py)"}
    else:
        O["f_catapulta"] = {"closes": None, "status": "unassessed",
                            "note": "assumptions.launch_recovery.catapult ausente — opção não avaliada (≠ passa)"}
    # (g) less demonstrated crosswind
    O["g_vento_cruzado_menor"] = {"closes": False, "admissible": False,
                                  "still_air_point_mass_m": still["ground_roll_m"],
                                  "still_air_6dof_m": out.get("ground_roll_6dof_still_air_m"),
                                  "note": "abaixo de 0,2 V_S0 falha 14 CFR 23.233(a) (pré-Amdt 64) — não relaxado",
                                  "source": "14 CFR 23.233(a)"}
    out["closing"] = [k_ for k_, v in O.items() if v.get("closes") is True]
    out["any_closes"] = bool(out["closing"])
    return out


def row(rep: dict | None) -> tuple | None:
    """``perf:takeoff_options`` text (reported, layout-type: it does not change feasibility)."""
    if not rep:
        return None
    if rep.get("status") != "assessed":
        return ("gear:takeoff_options", None, f"opções da corrida unassessed: {rep.get('issue')}")
    O = rep["options"]
    bits = []
    a = O["a_vento_de_frente"]
    if a.get("headwind_required_m_s") is not None:
        bits.append(f"vento de frente ≥ {a['headwind_required_m_s']:.1f} m/s"
                    + (f" (vento a ≤ {a['wind_to_runway_angle_max_deg']:.0f}° da pista)" if a.get(
                        "wind_to_runway_angle_max_deg") is not None else ""))
    if O["b_tracao"].get("thrust_factor_required"):
        bits.append(f"tração ×{O['b_tracao']['thrust_factor_required']:.3f}")
    if O["c_carga_alar"].get("S_factor_required"):
        bits.append(f"S ×{O['c_carga_alar']['S_factor_required']:.3f}")
    if O["d_massa"].get("mass_reduction_kg") is not None:
        bits.append(f"massa −{O['d_massa']['mass_reduction_kg']:.1f} kg")
    e = O.get("e_atitude") or {}
    if e.get("first_closing"):
        bits.append(f"atitude {e['first_closing']['theta_deg']:.1f}°")
    txt = (f"corrida 6-DOF {rep['ground_roll_6dof_m']:.0f} m contra {rep['requirement_m']:.0f} m "
           f"(k 6-DOF/massa pontual {rep['k_6dof_over_point_mass']:.3f}); fecham: "
           + (", ".join(rep["closing"]) or "nenhuma") + ("; " + "; ".join(bits) if bits else ""))
    return ("gear:takeoff_options", True if rep["any_closes"] else False, txt + f" ({rep['source']})")


def _min_att(e: dict) -> str:
    fin = [r for r in e.get("sweep") or [] if math.isfinite(r["ground_roll_est_m"])]
    if not fin:
        return "nenhuma atitude descola"
    m = min(fin, key=lambda r: r["ground_roll_est_m"])
    return (f"nenhuma fecha: mínimo {m['ground_roll_est_m']:.1f} m a θ_g {m['theta_deg']:.1f}° (C_D cresce com θ; "
            f"perda a θ ≈ {m['theta_deg'] + m['stall_margin_deg']:.1f}°)")


def to_markdown(rep: dict) -> str:
    """Options table in pt-PT (example output)."""
    if not rep or rep.get("status") != "assessed":
        return f"Opções da corrida: {(rep or {}).get('issue', 'unassessed')}\n"
    O = rep["options"]
    pm = rep["point_mass"]

    def f(v, fmt="{:.1f}"):
        return "—" if v is None else fmt.format(v)

    def c(v):
        return {True: "sim", False: "não", None: "unassessed"}[v]
    L = [f"# Opções da corrida de descolagem ({rep['mode']})", "",
         f"* Requisito: {rep['requirement_m']:.0f} m. 6-DOF na missão: {rep['ground_roll_6dof_m']:.1f} m "
         f"(vento de frente {rep['wind_headwind_m_s']:.1f} m/s, cruzado {rep['wind_crosswind_m_s']:.1f} m/s).",
         f"* 6-DOF em ar calmo: {f(rep.get('ground_roll_6dof_still_air_m'))} m; penalização do vento cruzado "
         f"{f(rep.get('crosswind_penalty_m'))} m.",
         f"* Massa pontual: {pm['mission_wind_m']:.1f} m no vento da missão, {pm['still_air_m']:.1f} m em ar calmo; "
         f"k = 6-DOF/massa pontual {rep['k_6dof_over_point_mass']:.3f} ({rep['k_source']}).", "",
         "| Opção | O que é preciso | Corrida estimada [m] | Fecha | Custo / nota |", "|---|---|---|---|---|"]
    a = O["a_vento_de_frente"]
    need = f"vento de frente ≥ {f(a.get('headwind_required_m_s'))} m/s"
    if a.get("wind_to_runway_angle_max_deg") is not None:
        need += (f" (vento a ≤ {a['wind_to_runway_angle_max_deg']:.0f}° da pista, cruzado restante "
                 f"{a['crosswind_left_m_s']:.1f} m/s)")
    chk = a.get("check_6dof") or {}
    est = f(a.get("ground_roll_est_m"))
    if chk.get("history"):
        est += " (6-DOF " + " → ".join(f"{h['ground_roll_6dof_m']:.1f}" for h in chk["history"]
                                       if h.get("ground_roll_6dof_m") is not None) + ")"
    if a.get("headwind_required_6dof_m_s") is not None:
        need += (f"; no 6-DOF ≥ {a['headwind_required_6dof_m_s']:.2f} m/s (rumo {a['heading_deg_6dof'] % 360:.0f}°, "
                 f"vento a ≤ {a['wind_to_runway_angle_max_6dof_deg']:.0f}° da pista)")
    L.append(f"| a. vento de frente / rumo da pista | {need} | {est} | {c(a.get('closes'))} | {a['note']} |")
    b = O["b_tracao"]
    bn = f"×{f(b.get('thrust_factor_required'), '{:.3f}')}"
    if b.get("thrust_factor_required_6dof") is not None:
        bn += f" (6-DOF ×{b['thrust_factor_required_6dof']:.3f})"
    be = f(b.get("ground_roll_est_m"))
    if (b.get("check_6dof") or {}).get("history"):
        be += " (6-DOF " + " → ".join(f"{h['ground_roll_6dof_m']:.1f}" for h in b["check_6dof"]["history"]
                                      if h.get("ground_roll_6dof_m") is not None) + ")"
    L.append(f"| b. tração | {bn} | {be} | {c(b.get('closes'))} | {b['cost']} |")
    s_ = O["c_carga_alar"]
    L.append(f"| c. carga alar (S maior) | S ×{f(s_.get('S_factor_required'), '{:.3f}')} | "
             f"{f(s_.get('ground_roll_est_m'))} | {c(s_.get('closes'))} | {s_['cost']} |")
    d = O["d_massa"]
    L.append(f"| d. massa de descolagem | −{f(d.get('mass_reduction_kg'))} kg | {f(d.get('ground_roll_est_m'))} | "
             f"{c(d.get('closes'))} | {d['cost']} |")
    e = O.get("e_atitude") or {}
    fc = e.get("first_closing")
    if "sweep" in e:
        L.append(f"| e. atitude de descolagem | "
                 + (f"θ_g {fc['theta_deg']:.1f}° (V_LOF/V_S {fc['VLOF_over_VS']:.2f}, δe {fc['de_trim_deg']:+.1f}°, "
                    f"margem de perda {fc['stall_margin_deg']:.1f}°)" if fc else _min_att(e))
                 + f" | {f(fc['ground_roll_est_m']) if fc else '—'} | {c(e.get('closes'))} | {e['cost']}"
                 + (f"; α_C {e['alpha_C_deg']:.1f}°" if e.get("alpha_C_deg") is not None else "") + " |")
    else:
        L.append(f"| e. atitude de descolagem | — | — | {c(e.get('closes'))} | {e.get('note', '')} |")
    k_ = O["f_catapulta"]
    L.append(f"| f. catapulta | " + (f"curso {f(k_.get('stroke_m'), '{:.2f}')} m a {f(k_.get('n_x_g'))} g" if
                                     k_.get("status") != "unassessed" else "bloco launch_recovery.catapult")
             + f" | {'0' if k_.get('status') != 'unassessed' else '—'} | {c(k_.get('closes'))} | "
             f"{k_.get('cost') or k_.get('note')} |")
    g = O["g_vento_cruzado_menor"]
    L.append(f"| g. vento cruzado demonstrado menor | não admissível | ar calmo 6-DOF {f(g.get('still_air_6dof_m'))} | "
             f"{c(g.get('closes'))} | {g['note']} |")
    L += ["", "Fecham: " + (", ".join(rep["closing"]) or "nenhuma") + ".", "", f"Fontes: {rep['source']}.", ""]
    return "\n".join(L)
