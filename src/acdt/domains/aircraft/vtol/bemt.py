# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Opt-in lightweight axial BEMT for a VTOL / eVTOL rotor (hover and climb).

Reuses the McCormick / Ning propeller BEMT already in
:mod:`acdt.domains.aircraft.propeller` (Prandtl tip loss). Coefficients are
reported in both propeller form (C_T = T/(ρ n² D⁴)) and rotor form
C_T = T/(ρ A (ΩR)²) (Leishman 2006 Sec. 2.4; Johnson 1980 Ch. 2).
Figure of merit is FM = P_ideal / P_shaft with P_ideal from momentum theory
(Leishman 2006 Eq. 2.16).

Default VTOL sizing stays momentum theory + a supplied FM. This module is
opt-in (``rotors.bemt`` or ``acdt bemt rotor``). Missing diameter, blades,
chord, pitch or a thrust target, rpm or tip speed, or a sourced section
polar → unassessed; the default FM is never presented as a BEMT result.
No rotor–rotor interference, no yawed / forward-flight BEMT, no CFD.
"""
from __future__ import annotations

import math
from typing import Any

from acdt.core.atmosphere import isa
from acdt.domains.aircraft.propeller import bemt
from acdt.domains.aircraft.systems_bemt import BEMT_SOURCE, section_polar_from_cfg
from acdt.domains.aircraft.vtol.momentum import ideal_hover_power

# C_T,rotor = 4 C_T,prop / π³   (see module tests)
_CT_PROP_TO_ROTOR = 4.0 / (math.pi ** 3)
# CP_r = P / (ρ A (ΩR)³) = CP_p ρ n³ D⁵ / (ρ π R² (2π n R)³)
# D=2R, D⁵=32 R⁵; (2π n R)³ = 8 π³ n³ R³
# denom = π R² * 8 π³ n³ R³ = 8 π⁴ n³ R⁵
# CP_r = CP_p * 32 R⁵ n³ / (8 π⁴ n³ R⁵) = 4 CP_p / π⁴
# wait I had 2/π⁴ — let me recalc in code comments and use 4/π⁴


def _cp_prop_to_rotor(cp_p: float) -> float:
    return 4.0 * cp_p / (math.pi ** 4)


def _ct_prop_to_rotor(ct_p: float) -> float:
    return 4.0 * ct_p / (math.pi ** 3)


def assess_rotor_bemt(cfg: dict, *, thrust_per_rotor_N: float | None = None,
                      V_axial_m_s: float = 0.0, altitude_m: float = 0.0,
                      rho: float | None = None) -> dict[str, Any]:
    """Axial (hover if V=0) BEMT for one rotor. ``cfg`` keys: diameter_m, blades, pitch_m or
    collective to be solved for ``thrust_per_rotor_N``, chord_075_over_D, rpm or tip_speed_m_s,
    airfoil or sourced ``section`` table.
    """
    src = BEMT_SOURCE + "; Leishman 2006 Sec. 2.4 / Eq. 2.16 (rotor C_T, FM)"
    out: dict[str, Any] = {"status": "unassessed", "source": src, "unassessed_terms": [], "notes": [],
                           "requested": True, "V_axial_m_s": V_axial_m_s}
    cfg = dict(cfg or {})
    un = out["unassessed_terms"]
    D = cfg.get("diameter_m")
    if not isinstance(D, (int, float)) or D <= 0:
        un.append("diameter_m")
    B = cfg.get("blades", cfg.get("n_blades"))
    if not isinstance(B, (int, float)) or int(B) < 2:
        un.append("blades (>=2)")
    c075 = cfg.get("chord_075_over_D")
    if not isinstance(c075, (int, float)) or c075 <= 0:
        un.append("chord_075_over_D")
    rpm = cfg.get("rpm")
    tip = cfg.get("tip_speed_m_s")
    if rpm is None and tip is None:
        un.append("rpm or tip_speed_m_s")
    polar, notes, pu = section_polar_from_cfg(cfg)
    out["notes"] += notes
    un += pu
    pitch = cfg.get("pitch_m")
    if pitch is None and thrust_per_rotor_N is None:
        un.append("pitch_m or thrust_per_rotor_N (to solve collective)")
    if un:
        out["notes"].append("BEMT de rotor pedido mas inputs em falta — FM/potência L0 não são um resultado BEMT")
        return out
    D, B, c075 = float(D), int(B), float(c075)
    R = D / 2.0
    at = isa(altitude_m or 0.0)
    rho = float(rho if rho is not None else at.rho)
    if rpm is not None:
        n = float(rpm) / 60.0
    else:
        n = float(tip) / (2 * math.pi * R)
    rpm = n * 60.0
    V = float(V_axial_m_s or 0.0)
    J = V / (n * D) if n * D > 0 else 0.0

    def coeffs(p):
        return bemt(J, D, p, B, c075, polar)

    if pitch is None:
        T_req = float(thrust_per_rotor_N)
        from scipy.optimize import brentq

        def g(p):
            ct, _ = coeffs(p)
            return ct * rho * n ** 2 * D ** 4 - T_req
        try:
            pitch = brentq(g, 0.05 * D, 2.5 * D, xtol=1e-4)
            out["notes"].append(f"passo geométrico {pitch:.4f} m resolvido para T={T_req:.2f} N (Ning 2014 / BEMT)")
        except ValueError:
            un.append("no pitch in 0.05D–2.5D matches the required thrust at this rpm")
            out["notes"].append("não foi possível casar o empuxo pedido — unassessed, não se usa FM L0 no seu lugar")
            return out
    else:
        pitch = float(pitch)

    polar.blade_ar = (1 - 0.15) / (2 * c075)
    ct_p, cp_p = coeffs(pitch)
    T = ct_p * rho * n ** 2 * D ** 4
    P = cp_p * rho * n ** 3 * D ** 5
    A = math.pi * R * R
    CT_r = _ct_prop_to_rotor(ct_p)
    CP_r = _cp_prop_to_rotor(cp_p)
    # also from dimensional definitions (sanity)
    omega = 2 * math.pi * n
    CT_r_dim = T / (rho * A * (omega * R) ** 2) if T else 0.0
    CP_r_dim = P / (rho * A * (omega * R) ** 3) if P else 0.0
    P_ideal = ideal_hover_power(max(T, 1e-12), rho, A) if V == 0.0 else None
    if V == 0.0 and P > 0:
        FM = P_ideal / P
    elif P > 0 and T > 0:
        # axial: momentum ideal P = T (V/2 + sqrt((V/2)^2 + v_h^2))
        vh = math.sqrt(T / (2 * rho * A))
        P_ideal = T * (0.5 * V + math.sqrt((0.5 * V) ** 2 + vh ** 2))
        FM = P_ideal / P
    else:
        FM = None
    tip_m = math.sqrt((omega * R) ** 2 + V ** 2)
    tip_mach = tip_m / at.a
    if tip_mach > 0.6:
        notes = out.setdefault("notes", [])
        notes.append(f"tip Mach {tip_mach:.3f} > 0.6 (limite convencional L0, PRESSUPOSTO) — assinalado, rpm não é recortado")
    out.update({
        "status": "ok", "diameter_m": D, "blades": B, "chord_075_over_D": c075, "pitch_m": float(pitch),
        "rpm": float(rpm), "J": float(J), "rho_kg_m3": float(rho),
        "thrust_N": float(T), "P_shaft_W": float(P),
        "FM": None if FM is None else float(FM),
        "P_ideal_W": None if P_ideal is None else float(P_ideal),
        "CT_prop": float(ct_p), "CP_prop": float(cp_p), "CT_rotor": float(CT_r), "CP_rotor": float(CP_r),
        "CT_rotor_dimensional": float(CT_r_dim), "CP_rotor_dimensional": float(CP_r_dim),
        "tip_speed_m_s": float(tip_m), "tip_mach": float(tip_mach),
        "polar_source": polar.source,
        "unassessed_terms": [],
    })
    if thrust_per_rotor_N is not None and abs(T - float(thrust_per_rotor_N)) / max(abs(float(thrust_per_rotor_N)), 1e-9) > 0.05:
        out["notes"].append(
            f"T BEMT={T:.2f} N vs pedido {thrust_per_rotor_N:.2f} N (>5 %) — reportado, não forçado")
    return out


def attach_to_hover(hp: dict, bemt_cfg: dict | None) -> dict:
    """Attach an opt-in BEMT report to a momentum ``hover_point`` result.

    Assessed BEMT replaces shaft power and FM. Unassessed BEMT leaves the
    momentum numbers in place but marks ``power_source`` and overall status so
    they are not presented as a BEMT close-out (unassessed≠pass).
    """
    hp = dict(hp)
    if not bemt_cfg:
        hp.setdefault("power_source", "momentum")
        return hp
    cfg = dict(bemt_cfg)
    cfg.setdefault("diameter_m", hp.get("diameter_m"))
    b = assess_rotor_bemt(cfg, thrust_per_rotor_N=hp.get("thrust_per_rotor_N"),
                          V_axial_m_s=0.0, rho=hp.get("rho_kg_m3"))
    n = int(hp.get("n_rotors") or 1)
    hp["bemt"] = b
    if b.get("status") == "ok":
        hp["P_per_rotor_W"] = b["P_shaft_W"]
        hp["P_hover_shaft_W"] = b["P_shaft_W"] * n
        hp["P_ideal_W"] = (b["P_ideal_W"] or 0.0) * n
        hp["FM"] = b["FM"]
        hp["power_loading_N_W"] = hp["thrust_total_N"] / hp["P_hover_shaft_W"] if hp["P_hover_shaft_W"] else None
        hp["rpm_bemt"] = b["rpm"]
        hp["power_source"] = "bemt"
        hp["status"] = "ok"
    else:
        hp["power_source"] = "momentum"  # L0 numbers retained, not a BEMT result
        hp["status"] = "unassessed"
        hp.setdefault("notes", []).append(
            "BEMT de rotor unassessed — potência de quantidade de movimento retida e marcada; unassessed≠pass")
    return hp
