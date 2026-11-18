"""Take-off of a tailless (flying-wing) tricycle: nose-wheel lift-off by elevon vs a nose-up fly-off stance.

Rotation criterion (Sadraey 2012, *Aircraft Design: A Systems Engineering Approach*, Sec. 9.6.2): at the onset of
rotation, moments about the main-gear contact point (Eq. 9.38/9.52, I_yy,mg θ̈ = Σ M, I_yy,mg by the parallel-axis
theorem, Eq. 9.53) must give a pitch acceleration θ̈ at least the value of Table 9.6 (normal light GA 8–10 °/s²;
UAV not listed → lower bound 8 °/s², PRESSUPOSTO) at a rotation speed V_R = 1.1–1.3 V_S (Eq. 9.35), at the
critical loading. The horizontal forces (T − D − m a = F_f = μN, Eq. 9.36/9.40) act at the CG height, so together
they give −μN h_cg about the contact. A tailless aeroplane has no tail lift: the elevon's own lift change (download,
C_Lδe) is part of N, so its net nose-up power about the main wheels is q̄S(c̄ C_mδe + C_Lδe (d + μh)) per radian.

Fly-off stance (the exception Sadraey Sec. 9.6.2 names, aircraft that do not rotate, e.g. the B-52): the nose strut
holds the aeroplane at its lift-off attitude θ_g (``gear.ground_attitude_deg``), the elevon trims C_m = 0 at that
attitude, and the aeroplane leaves the ground on all wheels at V_LOF = √(2W/(ρ S C_L,trim)), which must be ≥ 1.1 V_S
(Raymer 2018 Sec. 17.8, V_TO = 1.1 V_stall). Ground roll: ∫ m V dV / (T cos θ_g − D − μ(W − L − T sin θ_g)) with
the propulsion model of the 6-DOF (full throttle) and μ = 0.04 (Raymer Table 17.1 / Sadraey Table 9.7, dry
concrete/asphalt 0.03–0.05); no ground effect (conservative, PRESSUPOSTO).
"""
from __future__ import annotations

import math

SOURCE = ("Sadraey 2012 Sec. 9.6.2 (Eq. 9.35 V_R = 1.1–1.3 V_S; Eq. 9.52–9.53 momentos no contacto do trem "
          "principal; Table 9.6 θ̈ 8–10 °/s² para GA ligeira normal, UAV não listado → 8 °/s² PRESSUPOSTO); "
          "atitude de descolagem sem rotação: exceção da mesma secção (B-52); V_LOF ≥ 1,1 V_S (Raymer 2018 "
          "Sec. 17.8); μ 0,04 (Raymer Table 17.1)")
THETA_DD_REQ_DEG_S2 = 8.0
MU_ROLL = 0.04
G0 = 9.80665


def _coeffs(a, alpha, de, x_cg):
    return a.coefficients(alpha, 0.0, 0.0, 0.0, 0.0, 0.0, de, 0.0, 0.0, 0.0, x_cg)


def _rotation(fm, d_g, h_g, thg, k, rho, thdd_req):
    a, m = fm.aero, fm.mass.m
    W = m * G0
    Vs = math.sqrt(2 * W / (rho * a.S * a.CLmax[0]))
    dmax = math.radians(a.limits["elevator"])
    cmde = a._interp("Cmde", thg, 0.0)
    de_up = -dmax if cmde < 0 else dmax
    V = k * Vs
    q = 0.5 * rho * V * V
    T, _ = fm.prop.thrust(V, 0.0, 1.0)
    c = _coeffs(a, thg, de_up, fm.mass.x_cg)
    N = W - q * a.S * c["CL"] - T * math.sin(thg)
    Iy = fm.mass.Iyy + m * (d_g * d_g + h_g * h_g)
    M = q * a.S * a.c * c["Cm"] - N * d_g - MU_ROLL * N * h_g
    out = {"V_R_m_s": V, "k": k, "theta_dd_deg_s2": math.degrees(M / Iy), "N_N": N, "de_deg": math.degrees(de_up),
           "Cm": c["Cm"], "CL": c["CL"]}
    # largest d (ground frame) that still gives θ̈_req: −mθ̈ d² − N d + (A − μNh − (I + m h²)θ̈) = 0
    A = q * a.S * a.c * c["Cm"]
    th = math.radians(thdd_req)
    cc = A - MU_ROLL * N * h_g - (fm.mass.Iyy + m * h_g * h_g) * th
    aa, bb = -m * th, -N
    disc = bb * bb - 4 * aa * cc
    out["d_max_m"] = ((-bb - math.sqrt(disc)) / (2 * aa)) if disc >= 0 and cc >= 0 else None
    # elevon deflection that would be needed (linear in δe) at this d
    clde = a._interp("CLde", thg, 0.0)
    c0 = _coeffs(a, thg, 0.0, fm.mass.x_cg)
    eff = q * a.S * (a.c * cmde + clde * (d_g + MU_ROLL * h_g))   # dM/dδe
    rhs = Iy * th - (q * a.S * a.c * c0["Cm"] - (W - q * a.S * c0["CL"] - T * math.sin(thg)) * (d_g + MU_ROLL * h_g))
    de_req = rhs / eff if abs(eff) > 1e-9 else None
    out["de_required_deg"] = math.degrees(de_req) if de_req is not None and de_req * de_up > 0 else None
    out["elevon_net_power_per_rad"] = eff / (q * a.S)
    return out


def _flyoff(fm, thg, rho, req_m=None):
    a, m = fm.aero, fm.mass.m
    W = m * G0
    Vs = math.sqrt(2 * W / (rho * a.S * a.CLmax[0]))
    c0 = _coeffs(a, thg, 0.0, fm.mass.x_cg)
    cmde = a._interp("Cmde", thg, 0.0)
    de = -c0["Cm"] / cmde
    lim = math.radians(a.limits["elevator"])
    c = _coeffs(a, thg, de, fm.mass.x_cg)
    out = {"de_trim_deg": math.degrees(de), "de_within_limit": bool(abs(de) <= lim + 1e-9), "CL_trim": float(c["CL"]),
           "alpha_stall_deg": math.degrees(a.alpha_stall(0.0)[0])}
    if c["CL"] <= 0:
        out.update({"V_LOF_m_s": None, "ok": False})
        return out
    Vlof = math.sqrt(2 * W / (rho * a.S * c["CL"]))
    V, x, dt = 0.5, 0.0, 0.01
    while V < Vlof:
        q = 0.5 * rho * V * V
        T, _ = fm.prop.thrust(V, 0.0, 1.0)
        acc = (T * math.cos(thg) - q * a.S * c["CD"] - MU_ROLL * max(W - q * a.S * c["CL"] - T * math.sin(thg), 0.0)) / m
        if acc <= 1e-3:
            x = math.inf
            break
        V += acc * dt
        x += V * dt
    out.update({"V_LOF_m_s": Vlof, "V_S_m_s": Vs, "VLOF_over_VS": Vlof / Vs, "ground_roll_m": float(x),
                "stall_margin_deg": out["alpha_stall_deg"] - math.degrees(thg)})
    out["ok"] = bool(out["de_within_limit"] and Vlof / Vs >= 1.1 - 1e-9
                     and (req_m is None or x <= req_m * (1 + 1e-3)))
    return out


def assess(res, spec: dict, tl: dict, gear: dict, cases: dict, models: dict, req_m: float | None = None) -> dict:
    """Rotation (Sadraey Sec. 9.6.2) and fly-off stance per loading case. ``models``: case → FlightModel (assembly
    AVL tables, :func:`.tailless_sim.build_tailless_flight_model`). Unknown gear → unassessed."""
    if gear.get("type") != "tricycle" or gear.get("x_main") is None or gear.get("ground_z") is None:
        return {"status": "unassessed", "source": SOURCE, "issue": "sem trem triciclo colocado"}
    rho = 1.225
    thg = math.radians(float(gear.get("ground_attitude_deg") or 0.0))
    xm, zg = float(gear["x_main"]), float(gear["ground_z"])
    rep = {"status": "assessed", "source": SOURCE, "ground_attitude_deg": math.degrees(thg),
           "theta_dd_req_deg_s2": THETA_DD_REQ_DEG_S2, "mu": MU_ROLL, "requirement_m": req_m, "cases": {}}
    for nm, cs in cases.items():
        fm = models.get(nm)
        if fm is None:
            continue
        x_cg, z_cg = float(cs["cg"][0]), float(cs["cg"][2])
        d, h = xm - x_cg, z_cg - zg
        d_g, h_g = d * math.cos(thg) - h * math.sin(thg), h * math.cos(thg) + d * math.sin(thg)
        rot = {f"{k:.1f}": _rotation(fm, d_g, h_g, thg, k, rho, THETA_DD_REQ_DEG_S2) for k in (1.1, 1.2, 1.3)}
        k_min = None
        for i in range(0, 41):
            k = 1.1 + 0.005 * i
            if _rotation(fm, d_g, h_g, thg, k, rho, THETA_DD_REQ_DEG_S2)["theta_dd_deg_s2"] >= THETA_DD_REQ_DEG_S2:
                k_min = k
                break
        r = {"mass_kg": fm.mass.m, "d_main_aft_of_cg_m": d, "d_static_m": d_g, "h_static_m": h_g,
             "rotation": rot, "k_R_min": k_min, "rotation_ok": k_min is not None}
        if thg > 0:
            r["fly_off"] = _flyoff(fm, thg, rho, req_m)
        rep["cases"][nm] = r
    cs = rep["cases"]
    if not cs:
        return {"status": "unassessed", "source": SOURCE, "issue": "sem modelos de voo por caso de massa"}
    rep["rotation_ok"] = all(v["rotation_ok"] for v in cs.values())
    d_max13 = [v["rotation"]["1.3"]["d_max_m"] for v in cs.values()]
    rep["band_static_m"] = {"tipback_min_d": max(v["d_static_m"] for v in cs.values()),
                            "rotation_max_d_at_1.3VS": (None if any(x is None for x in d_max13) else min(d_max13))}
    worst = max(cs, key=lambda k: cs[k]["mass_kg"])
    rep["worst_case"] = worst
    if thg > 0:
        fo = [v["fly_off"] for v in cs.values()]
        rep["fly_off_ok"] = all(f["ok"] for f in fo)
        rep["ground_roll_worst_m"] = max(f["ground_roll_m"] for f in fo)
        rep["mode"] = "fly_off"
        rep["ok"] = bool(rep["fly_off_ok"])   # the stance is the design: lift-off and ground roll must both close
    else:
        rep["mode"] = "rotation"
        rep["ok"] = rep["rotation_ok"]
        rep["note"] = "corrida de descolagem com rotação não avaliada aqui (ver missão 6-DOF)"
    return rep


def row(tr: dict) -> tuple:
    """``gear:takeoff_rotation`` row (unassessed → None)."""
    if not tr or tr.get("status") != "assessed":
        return ("gear:takeoff_rotation", None, f"descolagem: {(tr or {}).get('issue', 'unassessed')}")
    w = tr["cases"][tr["worst_case"]]
    r13 = w["rotation"]["1.3"]
    band = tr["band_static_m"]
    txt = (f"rotação (Sadraey Sec. 9.6.2): θ̈ a 1,3 V_S no caso {tr['worst_case']} {r13['theta_dd_deg_s2']:+.0f} °/s² "
           f"(mín. {tr['theta_dd_req_deg_s2']:.0f}), elevon {r13['de_deg']:+.0f}°; banda tip-back d ≥ "
           f"{band['tipback_min_d']:.3f} m vs rotação d ≤ "
           + (f"{band['rotation_max_d_at_1.3VS']:.3f} m" if band["rotation_max_d_at_1.3VS"] is not None else "—")
           + (f"; fecha a {w['k_R_min']:.2f} V_S" if w.get("k_R_min") is not None
              else (f"; elevon necessária {r13['de_required_deg']:+.0f}° (limite {abs(r13['de_deg']):.0f}°)"
                    if r13.get("de_required_deg") is not None else "; a elevon não fecha (descarga ≥ momento)")))
    if tr["mode"] == "fly_off":
        f = w["fly_off"]
        txt += (f". Atitude de descolagem θ_g {tr['ground_attitude_deg']:.1f}° sem rotação: δe trim "
                f"{f['de_trim_deg']:+.1f}°, V_LOF {f['V_LOF_m_s']:.1f} m/s = {f['VLOF_over_VS']:.2f} V_S (≥ 1,1), margem "
                f"de perda {f['stall_margin_deg']:.1f}° (informativo; o critério citado é V_LOF/V_S ≥ 1,1, Raymer 2018 Sec. 17.8), corrida {tr['ground_roll_worst_m']:.0f} m"
                + (f" (requisito {tr['requirement_m']:.0f} m)" if tr.get("requirement_m") else ""))
    return ("gear:takeoff_rotation", tr.get("ok"), txt + f" ({tr['source']})")
