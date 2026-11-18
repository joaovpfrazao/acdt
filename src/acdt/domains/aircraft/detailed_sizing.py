"""Phase 4 detailed sizing: rib schedule (crushing), wing-root joint (bolts/bearing), control surfaces.

Methods (classical, first-cut):

* Rib crushing (Brazier effect; Niu, *Airframe Structural Design* 1988, Ch. 5 "Ribs"; Megson, *Aircraft
  Structures* §23 curvature loads): under bending curvature κ = M/EI the cover membrane force
  N = σ t_e = M (h/2) t_e / I presses on the ribs with p = N κ; over a rib pitch s the crushing load per unit
  chord of one rib is  w = N κ s = M² h t_e s / (2 I · EI)  (both covers, compressive across the rib depth).
  Rib web checked as a wide column of height h, pinned edges: σ_cr = π² E t² / (12 (1−ν²) h²), and against
  Fcy. Lightening holes, flanges and rib-shear (air-load redistribution) are NOT included.
* Wing-root joint (Bruhn, *Analysis and Design of Flight Vehicle Structures* 1973, Ch. D1 "Bolted and riveted
  joints"; fitting factor 1.15, CS 23.625 / 14 CFR 23.625 (legacy) / STANAG 4671 USAR.625): spar-cap load at
  the root rib P = M_u / h × 1.15; steel bolts (Ftu 125 ksi, Fsu 75 ksi — MMPDS typical, e.g. AN/NAS) in double
  shear; fitting-plate bearing P_br = Fbru d t with Fbru(e/D = 2) ≈ 1.8 Ftu (ASSUMPTION — read MMPDS).
* Control surfaces: hinge moments at V_D, H = C_h q S_c c_c (Roskam Part VI Ch. 10) from
  :func:`acdt.core.systems.servos.size_control_surfaces` (C_h derivatives remain user ASSUMPTIONS).
"""
from __future__ import annotations

import math

import numpy as np

from acdt.domains.aircraft.structures import MATERIALS

IN = 0.0254
FSU_STEEL = 75e3 * 6894.757          # [Pa] 125 ksi alloy-steel bolt (MMPDS typical — verify)
FITTING_FACTOR = 1.15                # CS 23.625(a)
BOLTS = {"AN3": 3 / 16, "AN4": 1 / 4, "AN5": 5 / 16, "AN6": 3 / 8, "AN7": 7 / 16, "AN8": 1 / 2}  # [in]
FBRU_RATIO = 1.8                     # Fbru(e/D=2)/Ftu (ASSUMPTION)
CFRP_BEARING = 500e6                 # [Pa] laminate bearing allowable (ASSUMPTION)


def rib_crushing_load(M, h, t_e, s, EI, E):
    """Crushing load per unit chord on one rib [N/m]: w = M² h t_e s E / (2 EI²) (I = EI/E)."""
    return M**2 * h * t_e * s * E / (2 * EI**2)


def rib_web_thickness(w, h, E, nu, Fcy, t_min):
    """Minimum rib-web thickness so that w/t ≤ min(σ_cr(column), Fcy)."""
    t_buck = (12 * (1 - nu**2) * h**2 * w / (math.pi**2 * E)) ** (1 / 3)
    return max(t_buck, w / Fcy, t_min)


def rib_schedule(wing, sr, material: str = "al2024_t3", n_ult: float = 1.5) -> dict:
    m = MATERIALS[material]
    box, beam = sr.box, sr.beam
    s = wing.box.rib_pitch or 0.6 * wing.mac
    y_r = np.arange(0.0, wing.span / 2 + 1e-9, s)
    E = m["E"]
    d = box.details or {}
    if "cover_tbar_upper" in d and np.any(np.asarray(d["cover_tbar_upper"]) > 0) and "E_cap" not in m:
        te = 0.5 * (np.asarray(d["cover_tbar_upper"]) + np.asarray(d["cover_tbar_lower"]))
    else:
        te = np.asarray(box.skin_t) + np.asarray(box.cap_area) / np.maximum(box.w_box, 1e-6)
    rows, mass = [], 0.0
    for yr in y_r:
        M = n_ult * abs(np.interp(yr, beam.y, beam.moment))
        h = float(np.interp(yr, box.y, box.h_box))
        EI = float(np.interp(yr, box.y, box.EI)) if box.EI is not None else None
        t_e = float(np.interp(yr, box.y, te))
        c = wing.c_root + (wing.c_tip - wing.c_root) * yr / (wing.span / 2)
        if not EI or M <= 0:
            w, t = 0.0, m["t_min_web"]
        else:
            w = rib_crushing_load(M, h, t_e, s, EI, E)
            t = rib_web_thickness(w, h, E, m["nu"], m["sigma_cap"], m["t_min_web"])
        rib_mass = 0.685 * wing.tc_mean * c**2 * t * m["rho"]
        mass += rib_mass
        rows.append({"y_m": float(yr), "M_ult_Nm": float(M), "h_m": h, "w_crush_N_per_m": float(w),
                     "t_web_mm": t * 1e3, "governed_by": "t_min" if t <= m["t_min_web"] * 1.0001 else "crushing",
                     "mass_kg": rib_mass})
    return {"pitch_m": s, "n_ribs_per_side": len(y_r), "rows": rows, "mass_both_sides_kg": 2 * mass,
            "phase3_rib_mass_kg": box.masses.get("ribs"),
            "notes": ["Niu Ch. 5 / Brazier: w = M² h t_e s/(2 I EI); coluna larga σ_cr = π²E t²/(12(1−ν²)h²)",
                      "furos de aligeiramento, banzos de nervura e corte de redistribuição NÃO incluídos"]}


def root_joint(sr, material: str = "al2024_t3", n_ult: float = 1.5, max_bolts: int = 6) -> dict:
    """Spar-cap root fitting: number/diameter of bolts (double shear) and fitting-plate thickness (bearing)."""
    m = MATERIALS[material]
    M = n_ult * abs(float(sr.beam.moment[0]))
    h = float(sr.box.h_box[0])
    P = FITTING_FACTOR * M / h
    Fbru = CFRP_BEARING if "E_cap" in m else FBRU_RATIO * m["sigma_tu"]
    choice = None
    for name, d_in in BOLTS.items():
        d = d_in * IN
        P_bolt = 2 * FSU_STEEL * math.pi * d**2 / 4
        n = math.ceil(P / P_bolt)
        if n <= max_bolts:
            n = max(n, 2)
            t_fit = P / n / (Fbru * d)
            choice = {"bolt": name, "d_mm": d * 1e3, "n_bolts_per_cap": n, "P_bolt_double_shear_N": P_bolt,
                      "MS_shear": n * P_bolt / P - 1, "t_fitting_mm": t_fit * 1e3, "e_min_mm": 2 * d * 1e3,
                      "pitch_min_mm": 4 * d * 1e3}
            break
    return {"M_root_ult_Nm": M, "h_root_m": h, "P_cap_with_fitting_factor_N": P, "fitting_factor": FITTING_FACTOR,
            "Fbru_Pa": Fbru, "joint": choice,
            "notes": ["Bruhn D1: corte duplo (2 chapas de ferragem), esmagamento Fbru d t; e/D = 2, passo 4D",
                      "Fbru ≈ 1.8 Ftu (PRESSUPOSTO — usar MMPDS)" if "E_cap" not in m else
                      "esmagamento do laminado 500 MPa (PRESSUPOSTO)",
                      "sem fadiga/concentração (Kt) nem pré-carga — ver Niu Ch. 9 para dimensionamento final"]
                     + ([] if choice else [f"> {max_bolts} parafusos AN8 necessários — rever ferragem"])}


def control_surfaces(design, V_D: float, rho: float = 1.225) -> list[dict]:
    from acdt.core.systems.servos import size_control_surfaces
    out = size_control_surfaces(design.config, V_D, rho, servos=[])
    return [{"surface": x.name, "S_c_m2": x.area, "c_c_m": x.chord, "H_Nm": x.hinge_moment,
             "torque_req_Nm": x.torque_required} for x in out]


def detailed_sizing(design) -> dict:
    sr = design.structures
    mat = "cfrp" if "CFRP" in str(sr.box.material) else "al2024_t3"
    return {"material": mat, "ribs": rib_schedule(design.config.wing, sr, mat),
            "root_joint": root_joint(sr, mat), "control_surfaces": control_surfaces(design, sr.vn.VD)}
