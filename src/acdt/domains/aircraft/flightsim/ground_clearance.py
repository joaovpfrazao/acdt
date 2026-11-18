# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Dynamic aft (tail / propeller / trailing-edge) ground clearance through rotation and flare — any aircraft.

Geometry (Sadraey 2012 Sec. 9.5.1.3, Eq. 9.2–9.3): the aeroplane pivots about the main-gear contact; an aft
point at a horizontal distance AB behind the contact and a height H above it strikes at the clearance angle
α_C = atan(H / AB). Requirement α_C > α_TO, and the same text applies it to the landing at high angle of attack.
Raymer (Ch. 11) uses the same tail-down angle (10–15° typical); the static check is ``asm:gear_rotation``.
Here the 6-DOF measures what the static check cannot: the pitch attitude actually reached near the ground,
strut/tyre compression, sink and pitch rate. 14 CFR 23.925(a)(1) (7 in / 9 in propeller clearance) is stated
for the level take-off and taxi attitudes only (already ``asm:gear_prop_clearance``); it is not applied to
rotation or flare here — a propeller in contact during rotation/flare is reported as a strike.

Options when the clearance is not met (all reported, none applied silently):
* attitude limit for the autopilot (UAV with active autopilot: θ_max near the ground = α_C − margin);
* longer struts (both legs, stance kept): Δh = (c_min − h_min) / cos θ at the worst sample;
* tail bumper / skid sized by energy, E = ½ m_eff v², N_des = n_ult E / (η δ) (Currey 1988; Raymer
  Sec. 18.2; Sadraey 2012 Sec. 9.7 — same method and PRESSUPOSTO constants as the wing-tip skids,
  ``assembly.gear_devices``), m_eff = 1 / (1/m + l²/I_yy) about the CG, v = the 6-DOF peak descent rate of
  the aft point near the ground (PRESSUPOSTO design velocity; not a certification sink rate).
"""
from __future__ import annotations

import math

import numpy as np

AFT_PREFIXES = ("aft_", "tail_strike")
NEAR_GROUND_M = 0.5        # main-wheel height under which an attitude counts as "near the ground" (PRESSUPOSTO)
SOURCE = ("Sadraey 2012 Sec. 9.5.1.3 Eq. 9.2–9.3 (α_C = atan(H/AB) > α_TO; também na aterragem a α alto); "
          "Raymer 2018 Ch. 11 (ângulo de cauda 10–15°); 6-DOF: atitude, compressão e razão de descida medidas")


def is_aft(name: str) -> bool:
    return str(name).startswith(AFT_PREFIXES)


def aft_geometry(contacts: list) -> list[dict]:
    """Aft points relative to the main-gear contact (body axes: x fwd, z down) and their strike angle α_C
    about the uncompressed main contact. ``contacts`` = GroundModel.contacts."""
    mains = [np.asarray(c[1], float) for c in contacts if str(c[0]).startswith("main")]
    if not mains:
        return []
    rm = np.mean(mains, axis=0)
    out = []
    for c in contacts:
        if not is_aft(c[0]):
            continue
        rb = np.asarray(c[1], float)
        AB = float(rm[0] - rb[0])          # horizontal distance aft of the main contact (> 0 aft)
        H = float(rm[2] - rb[2])           # height above the main contact (z down → main z larger)
        out.append({"name": str(c[0]), "AB_m": AB, "H_m": H, "r_body": [float(v) for v in rb],
                    "alpha_C_deg": math.degrees(math.atan2(H, AB)) if AB > 0 else 90.0})
    return out


class AftMonitor:
    """Per-step sampler of the aft points (6-DOF state x, contacts list)."""

    def __init__(self, contacts: list):
        self.aft = [(str(c[0]), np.asarray(c[1], float)) for c in contacts if is_aft(c[0])]
        self.main = [np.asarray(c[1], float) for c in contacts if str(c[0]).startswith("main")]
        self.min_clear = math.inf
        self.at_min = {}
        self.theta_max_near = -math.inf
        self.v_desc_max_near = 0.0
        self.contact_N = 0.0
        self.compression_max = 0.0
        self.n = 0

    def sample(self, x, R, contact_loads: dict | None = None):
        if not self.aft or not self.main:
            return
        pos, vb, w = x[0:3], x[3:6], x[10:13]
        h_main = min(-(pos + R @ rm)[2] for rm in self.main)
        if h_main > NEAR_GROUND_M:
            return
        self.n += 1
        self.compression_max = max(self.compression_max, -h_main)   # main contact below the ground plane
        th = math.asin(max(-1.0, min(1.0, -R[2, 0])))
        self.theta_max_near = max(self.theta_max_near, th)
        for name, rb in self.aft:
            pc = pos + R @ rb
            clear = float(-pc[2])
            vz = float((R @ (vb + np.cross(w, rb)))[2])   # + down
            if clear < 0.5:
                self.v_desc_max_near = max(self.v_desc_max_near, vz)
            if clear < self.min_clear:
                self.min_clear = clear
                self.at_min = {"point": name, "theta_deg": math.degrees(th), "q_deg_s": math.degrees(float(w[1])),
                               "v_desc_m_s": vz, "h_main_m": h_main}
        for name, N in (contact_loads or {}).items():
            if is_aft(name):
                self.contact_N = max(self.contact_N, float(N))

    def summary(self) -> dict | None:
        if not self.aft:
            return None
        if self.n == 0:
            return {"status": "nao_avaliado", "note": "sem amostras com o trem principal perto do solo"}
        return {"status": "assessed", "min_clearance_m": self.min_clear, "at_min": self.at_min,
                "theta_max_near_ground_deg": math.degrees(self.theta_max_near),
                "v_desc_max_aft_m_s": self.v_desc_max_near, "contact_peak_N": self.contact_N or None,
                "main_compression_max_m": self.compression_max,
                "near_ground_def": f"roda principal < {NEAR_GROUND_M} m (PRESSUPOSTO)"}


def assess_aft_clearance(contacts: list, phases: dict, m_kg: float, Iyy: float, opts: dict | None = None) -> dict:
    """Combine the geometry (α_C) with the 6-DOF phase summaries (``{"takeoff": AftMonitor.summary(), ...}``).

    ``opts`` (from ``gear.aft_clearance``): ``min_clearance_m`` (PRESSUPOSTO default 0.0 — no contact;
    Sadraey quotes ~0.30 m for transports, not scaled here), ``attitude_margin_deg`` (2.0, PRESSUPOSTO),
    ``stroke_m``/``eta``/``n_ult``/``shoe_length_m``/``mass_min_kg`` for the bumper (tip-skid defaults).
    """
    from ..assembly.gear_devices import (SKID_ETA, SKID_MASS_MIN_KG, SKID_NONOPT, SKID_SHOE_LENGTH_M,
                                         SKID_STROKE_M, SKID_SOURCE)
    from ..structures import MATERIALS
    o = opts or {}
    geo = aft_geometry(contacts)
    if not geo:
        return {"status": "nao_avaliado", "issue": "sem ponto traseiro (aft_*/tail_strike) ou sem trem principal"}
    c_min = float(o.get("min_clearance_m", 0.0))
    marg = float(o.get("attitude_margin_deg", 2.0))
    crit = min(geo, key=lambda g: g["alpha_C_deg"])
    ph = {k: v for k, v in phases.items() if v}
    assessed = {k: v for k, v in ph.items() if v.get("status") == "assessed"}
    out = {"status": "assessed" if assessed else "nao_avaliado", "source": SOURCE, "points": geo,
           "alpha_C_deg": crit["alpha_C_deg"], "critical_point": crit["name"], "min_clearance_req_m": c_min,
           "min_clearance_note": ("PRESSUPOSTO: folga mínima exigida 0 m (sem contacto) — Sadraey Sec. 9.5.1.3 cita "
                                  "~30 cm para transportes, não escalado para este tamanho"),
           "phases": ph}
    if not assessed:
        out["ok"] = None
        return out
    worst_k = min(assessed, key=lambda k: assessed[k]["min_clearance_m"])
    w = assessed[worst_k]
    th_max = max(v["theta_max_near_ground_deg"] for v in assessed.values())
    dmax = max(v.get("main_compression_max_m") or 0.0 for v in assessed.values())
    a_eff = math.degrees(math.atan2(crit["H_m"] - dmax, crit["AB_m"])) if crit["AB_m"] > 0 else 90.0
    out.update({"worst_phase": worst_k, "min_clearance_m": w["min_clearance_m"],
                "theta_max_near_ground_deg": th_max,
                "main_compression_max_m": dmax,
                "alpha_C_compressed_deg": a_eff,
                "alpha_C_compressed_note": ("α_C com o contacto principal comprimido pelo máximo do 6-DOF "
                                            "(mola/pneu PRESSUPOSTO do modelo de solo, deflexão estática 0,07 m)"),
                "attitude_margin_deg": a_eff - th_max,
                "ok": bool(w["min_clearance_m"] > c_min)})
    # options (always reported, never applied)
    th_lim = a_eff - marg
    opts_out = {"attitude_limit": {
        "theta_max_near_ground_deg": th_lim,
        "note": f"limite de atitude no piloto automático perto do solo: α_C comprimido − {marg:.1f}° (PRESSUPOSTO margem); "
                "válido para UAV com piloto automático ativo"}}
    th_w = math.radians(w["at_min"].get("theta_deg", th_max))
    dh = max(0.0, c_min - w["min_clearance_m"]) / max(math.cos(th_w), 1e-6)
    opts_out["strut_extension"] = {
        "delta_h_both_legs_m": dh,
        "note": "as duas pernas (principal e nariz) +Δh mantêm a atitude estática; massa/arrasto das pernas a "
                "rever (Raymer Eq. 15.50/15.51); 1.ª ordem, sem nova simulação"}
    # tail bumper (energy method)
    rb = np.asarray(next(c[1] for c in contacts if c[0] == crit["name"]), float)
    l = abs(float(rb[0]))
    m_eff = 1.0 / (1.0 / m_kg + l * l / Iyy) if Iyy and Iyy > 0 else m_kg
    v = max((x.get("v_desc_max_aft_m_s") or 0.0) for x in assessed.values())
    stroke = float(o.get("stroke_m", SKID_STROKE_M))
    eta = float(o.get("eta", SKID_ETA))
    n_ult = float(o.get("n_ult", 1.5))
    L = float(o.get("shoe_length_m", SKID_SHOE_LENGTH_M))
    E = 0.5 * m_eff * v * v
    N_des = n_ult * E / (eta * stroke)
    mat = MATERIALS["al2024_t3"]
    A = N_des / mat["sigma_cap"] if mat["sigma_cap"] else 0.0
    m_b = max(A * L * mat["rho"] * SKID_NONOPT, float(o.get("mass_min_kg", SKID_MASS_MIN_KG)))
    opts_out["tail_bumper"] = {
        "point": crit["name"], "l_from_cg_m": l, "m_eff_kg": m_eff, "v_design_m_s": v,
        "v_note": "PRESSUPOSTO: velocidade de descida de projeto = pico do 6-DOF do ponto traseiro com folga < 0,5 m "
                  "perto do solo (não é uma razão de descida de certificação)",
        "energy_J": E, "P_des_N": N_des, "stroke_m": stroke, "eta": eta, "n_ult": n_ult,
        "mass_kg": m_b, "material": mat["name"], "source": SKID_SOURCE,
        "note": "para-choques/patim de cauda no ponto crítico; massa = secção A = N_des/Fcy × comprimento × ρ × 1,25 "
                "com piso de instalação PRESSUPOSTO (como os patins de ponta)"}
    out["options"] = opts_out
    if not out["ok"]:
        out["issue"] = (f"folga traseira mínima {w['min_clearance_m']:.3f} m ({worst_k}, {w['at_min'].get('point')}) "
                        f"≤ {c_min:.3f} m; θ perto do solo {th_max:.1f}° contra α_C {crit['alpha_C_deg']:.1f}°")
    return out
