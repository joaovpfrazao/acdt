"""Control-surface sizing by performance requirements (Fase 8, passo A).

Replaces the historical control-surface fractions (Raymer Sec. 6.5) by checks of what each surface must
*do*, evaluated with AVL (vortex lattice, external process) on the parametric geometry. Every candidate
layout is re-run in AVL (≈0.3 s per case), so the derivatives always belong to the geometry being sized.

Methods (classical, cited)
--------------------------
* **Aileron — roll performance.** Single-degree-of-freedom roll with roll damping (Sadraey, *Aircraft Design: A
  Systems Engineering Approach*, 2012, Sec. 12.4.2, Eqs. 12.34–12.50; Nelson, *Flight Stability and Automatic
  Control*, 2nd ed., Sec. 5.2): L_p = C_lp q S b²/(2 I_xx V), L_δa = C_lδa q S b / I_xx, τ = −1/L_p,
  p_ss = −L_δa δa / L_p, φ(t) = p_ss [t − τ (1 − e^{−t/τ})] (step aileron, actuator lag neglected).
  C_lp and C_lδa from AVL at the flight condition. Requirements: MIL-F-8785C Table IXa (Class I, Levels 1–3:
  Cat. B 60° in 1.7/2.5/3.4 s; Cat. C 30° in 1.3/1.8/2.6 s) and 14 CFR 23.157 (pre-Amdt 23-64; same text in
  CS-23 Amdt 4 23.157): 30°→30° reversal (60°) in 5 s at take-off (1.2 V_S1, take-off flaps) and 4 s on
  approach (V_REF = 1.3 V_S0, landing flaps) for W ≤ 6000 lb, (W+500)/1300 ≤ 10 s and (W+2800)/2200 ≤ 7 s above.
  For UAVs the MIL-F-8785C Class I values are used as *guidance* (indicative).
* **Elevator — take-off rotation** (Sadraey Sec. 12.6.3, Eqs. 12.55–12.73): moment balance about the main-gear
  contact point at V_R = 1.1 V_S,TO (lower bound of Eq. 12.54), most-forward CG, take-off flaps:
  I_yy,mg θ̈ = q S c̄ (C_m,mg + C_mδe δe) − W (x_mg − x_cg) − T h_T + D h_D + m a h_cg, with C_m,mg from AVL
  about the gear station (wing-body *and* tail lift), I_yy,mg = I_yy + m (Δx² + h_cg²), a = (T − D − μ (W − L))/m.
  θ̈ target 12 deg/s² (Sadraey Table 12.9: GA 10–15 deg/s²). Tricycle gear only.
* **Elevator — trim over CG range / flaps / speeds** (Sadraey Eqs. 12.84–12.90; Etkin & Reid Sec. 2.4):
  2×2 linear trim (C_L, C_m about the CG) from one AVL case per flap setting; the C_m about another CG is
  transferred with C_L (x_cg − x_ref)/c̄; the handbook fuselage neutral-point shift (Raymer Eq. 16.22–16.23,
  ``stability.dx_fus``) is added because AVL has no fuselage. Tail lift coefficient checked against
  0.9 c_l,max,tail cos Λ (Raymer Eq. 12.15) — indicative tail-stall check.
  If c_e/c_h > 0.5 is needed, Sadraey recommends an all-moving tail.
* **Rudder — crosswind landing.** Steady straight sideslip with the nose aligned with the runway (Etkin & Reid
  Sec. 4.? steady sideslip; Roskam, *Airplane Flight Dynamics* Part I, Sec. 4.2): C_Yβ β + C_Yδa δa + C_Yδr δr +
  C_L sin φ = 0, C_lβ β + C_lδa δa + C_lδr δr = 0, C_nβ β + C_nδa δa + C_nδr δr = 0, β = atan(V_w/U) at
  U = 1.1 V_S0 (Sadraey Sec. 12.6.2.3). Cross-check: Sadraey crabbed-landing Eqs. 12.105–12.115 (side area by
  Swet/π for the fuselage, C_Dy = 0.6 — Sadraey range 0.5–0.8). Requirement: 90° crosswind ≥ 0.2 V_S0 (14 CFR
  23.233(a), pre-Amdt 23-64) or the user value (``crosswind_kt``). C_nβ adds the fuselage term of Raymer Eq. 16.47.
* **Rudder — OEI** (multi-engine, Sadraey Eq. 12.102): T y_T + q S b C_nδr δr = 0 at V_MC (default 1.13 V_S,
  Sadraey/14 CFR 25.149 — override for CS-23 aircraft).
* **Spin recovery** — not evaluated (rudder power for spin recovery needs spin-tunnel data or the tail-damping
  power factor criterion, Raymer 6th ed. Ch. 16) — reported as a note.
* **Flaps** — C_L,max required by the stall-speed and landing-distance requirements (Raymer Sec. 17.9, the
  existing :func:`performance.landing_distance`), flapped-area ratio by inverting Raymer Eq. 12.21 and compared
  with the span left inboard of the aileron.
* **Hinge moments** — AVL ``HM`` (inviscid, sealed plain flap, no aerodynamic balance): C_h,α, C_h,δ by finite
  differences; H = q S_ref c_ref (C_h0 + C_hα α + C_hδ δ) at V_A with full deflection and at V_D with one third
  of it (deflection schedule of 14 CFR 23.455(a)(2), pre-Amdt 64, applied to all surfaces — ASSUMPTION for
  elevator/rudder). Servo torque = |H| × linkage × FoS → :func:`acdt.core.systems.servos.select_servo`.
  Inviscid VLM hinge moments are first estimates: gaps, balance and boundary layer change them strongly —
  calibrate with test data.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np

from acdt import G0
from acdt.core.atmosphere import isa
from acdt.domains.aircraft.weights_detailed import DEFAULT_MAIN_GEAR_LENGTH_M

from ..aero.avl import ControlLayout, avl_available, run_avl_case, wing_x_ac
from ..aero.interfaces import ToolNotAvailable
from ..aero.lift import FLAP_DCLMAX

LB = 0.45359237 * G0  # N per lbf

# MIL-F-8785C Table IXa (Class I): time [s] to achieve the bank-angle change, Levels 1/2/3.
MIL_8785C_ROLL_CLASS_I = {"A": (60.0, (1.3, 1.7, 2.6)), "B": (60.0, (1.7, 2.5, 3.4)), "C": (30.0, (1.3, 1.8, 2.6))}

DEFAULTS = {
    # layout of the current design (stability defaults; Raymer Sec. 6.5 typical values)
    "aileron_span_fraction": 0.35, "aileron_cf_c": 0.25, "flap_cf_c": 0.25, "elevator_cf_c": 0.30,
    "rudder_cf_c": 0.35,
    # deflection limits [deg] (Sadraey Sec. 12.4.4 step 10: aileron ±25 typical, stall above 20–25;
    # elevator −25 (TE up) Sadraey Sec. 12.6; rudder ±30 Sadraey Examples 12.2/12.3)
    "aileron_max_deg": 25.0, "elevator_max_deg": 25.0, "rudder_max_deg": 30.0,
    # flap settings [deg] — ASSUMPTIONS (C172: 0–30° per POH); replace with the design values
    "flap_takeoff_deg": 10.0, "flap_landing_deg": 30.0,
    # take-off rotation (Sadraey Sec. 12.6.3)
    "rotation_pitch_accel_deg_s2": 12.0, "rotation_speed_factor": 1.1, "cg_height_m": None,
    "thrust_line_z_m": 0.0, "alpha_ground_deg": 0.0,
    # trim map
    "flap_speed_factor": 1.4,  # flaps-extended speed range up to 1.4 V_S,flap (ASSUMPTION — placard V_FE)
    "tail_clmax_airfoil": 1.6,  # NACA 0012 at Re ≈ 6e6 (Abbott & von Doenhoff, App. IV) — lower at low Re
    # crosswind
    "crosswind_kt": None, "crosswind_speed_factor": 1.1, "side_drag_coefficient": 0.6,
    # OEI
    "engine_y_m": None, "vmc_factor": 1.13,
    # sizing candidate ranges
    "aileron_span_candidates": [0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6],
    "elevator_cf_candidates": [0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5],
    "rudder_cf_candidates": [0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5],
    "roll_level": 1,
    # hinge moments / servos
    "linkage_ratio": 1.0, "factor_of_safety": 1.5, "v_servo": 8.4,
}


@dataclass
class ControlSizingResult:
    aileron: dict
    elevator: dict
    rudder: dict
    flap: dict
    hinge: dict
    layout_current: dict
    layout_sized: dict
    notes: list[str] = field(default_factory=list)
    plots: dict = field(default_factory=dict)

    def summary(self) -> dict:
        def clean(o):
            if isinstance(o, dict):
                return {k: clean(v) for k, v in o.items() if not k.startswith("_")}
            if isinstance(o, (list, tuple)):
                return [clean(v) for v in o]
            if isinstance(o, (np.floating, np.integer)):
                return o.item()
            if isinstance(o, np.ndarray):
                return o.tolist()
            return o
        return clean({"aileron": self.aileron, "elevator": self.elevator, "rudder": self.rudder, "flap": self.flap,
                      "hinge_moments": self.hinge, "layout_current": self.layout_current,
                      "layout_sized": self.layout_sized, "notes": self.notes,
                      "plots": {k: str(v) for k, v in self.plots.items()}})


# ------------------------------------------------------------------ pure functions (unit-tested)
def roll_response(Clp: float, Clda: float, delta_rad: float, V: float, rho: float, S: float, b: float,
                  Ixx: float) -> dict:
    """Single-DOF roll (Sadraey Eqs. 12.34–12.46): steady roll rate, time constant, roll-rate derivatives."""
    q = 0.5 * rho * V**2
    Lp = Clp * q * S * b**2 / (2 * Ixx * V)
    Lda = Clda * q * S * b / Ixx
    tau = -1.0 / Lp
    p_ss = -Lda * delta_rad / Lp
    return {"Lp": Lp, "Lda": Lda, "tau": tau, "p_ss": p_ss, "pb_2V": p_ss * b / (2 * V)}


def bank_angle(t, p_ss: float, tau: float):
    """φ(t) for a step aileron input from wings level: p_ss [t − τ (1 − e^{−t/τ})] [rad]."""
    t = np.asarray(t, dtype=float)
    return p_ss * (t - tau * (1 - np.exp(-t / tau)))


def time_to_bank(dphi_rad: float, p_ss: float, tau: float) -> float:
    """Time to change bank by ``dphi`` after a step input (Newton on the closed-form φ(t))."""
    p = abs(p_ss)
    if p <= 0:
        return float("inf")
    t = dphi_rad / p + tau
    for _ in range(50):
        f = p * (t - tau * (1 - math.exp(-t / tau))) - dphi_rad
        df = p * (1 - math.exp(-t / tau))
        dt = f / max(df, 1e-12)
        t -= dt
        t = max(t, 1e-6)
        if abs(dt) < 1e-10:
            break
    return t


def roll_requirements(W_N: float, regulation: str, uav: bool, level: int = 1) -> list[dict]:
    """List of roll requirements: MIL-F-8785C Table IXa Class I and 14 CFR / CS 23.157."""
    out = []
    for cat, cond in (("B", "cruise"), ("C", "approach")):
        dphi, ts = MIL_8785C_ROLL_CLASS_I[cat]
        out.append({"name": f"MIL-F-8785C IXa Classe I Cat. {cat} (Nível {level})", "dphi_deg": dphi,
                    "t_max": ts[level - 1], "condition": cond, "levels": ts,
                    "source": "MIL-F-8785C Table IXa", "indicative": uav})
    if not uav and regulation in ("cs_23", "far_23", "cs23", "far23", "lsa", "cs_vla"):
        W_lb = W_N / LB
        t_to = 5.0 if W_lb <= 6000 else min((W_lb + 500) / 1300, 10.0)
        t_ap = 4.0 if W_lb <= 6000 else min((W_lb + 2800) / 2200, 7.0)
        out.append({"name": "14 CFR/CS 23.157(a) descolagem", "dphi_deg": 60.0, "t_max": t_to, "condition": "takeoff",
                    "source": "14 CFR 23.157(a) (pré-Amdt 64) / CS-23 Amdt 4", "indicative": False})
        out.append({"name": "14 CFR/CS 23.157(c) aproximação", "dphi_deg": 60.0, "t_max": t_ap,
                    "condition": "approach_far", "source": "14 CFR 23.157(c) (pré-Amdt 64) / CS-23 Amdt 4",
                    "indicative": False})
    return out


def steady_sideslip(beta: float, CL: float, d: dict) -> dict:
    """Solve the steady straight sideslip (nose on the runway) for δa, δr, φ (Roskam AFD Part I Sec. 4.2).

    ``d`` keys: CYb, Clb, Cnb, CYda, Clda, Cnda, CYdr, Cldr, Cndr (per rad, any consistent sign convention)."""
    A = np.array([[d["CYda"], d["CYdr"], CL], [d["Clda"], d["Cldr"], 0.0], [d["Cnda"], d["Cndr"], 0.0]])
    rhs = -beta * np.array([d["CYb"], d["Clb"], d["Cnb"]])
    da, dr, sphi = np.linalg.solve(A, rhs)
    return {"delta_a": float(da), "delta_r": float(dr), "phi": float(math.asin(max(-1.0, min(1.0, sphi))))}


def sadraey_crab(Vw: float, U: float, rho: float, S: float, b: float, Ss: float, dc: float, CDy: float,
                 Cnb: float, CYb: float, Cndr: float, CYdr: float) -> dict:
    """Sadraey Eqs. 12.105–12.115 (crabbed landing): unknowns rudder δr and crab angle σ (standard signs:
    C_nβ > 0, C_Yβ < 0, C_nδr < 0, C_Yδr > 0)."""
    from scipy.optimize import fsolve
    beta = math.atan2(Vw, U)
    VT = math.hypot(U, Vw)
    qT = 0.5 * rho * VT**2
    Fw = 0.5 * rho * Vw**2 * Ss * CDy

    def f(x):
        dr, sg = x
        return [qT * S * b * (Cnb * (beta - sg) + Cndr * dr) + Fw * dc * math.cos(sg),
                Fw - qT * S * (CYb * (beta - sg) + CYdr * dr)]
    (dr, sg), info, ier, _ = fsolve(f, [0.0, 0.0], full_output=True)
    return {"delta_r": float(dr), "crab": float(sg), "beta": beta, "Fw": Fw, "converged": ier == 1}


def flapped_ratio_required(CLmax_req: float, CLmax_clean: float, kind: str, sweep_hl: float = 0.0,
                           chord_extension: float = 1.0) -> float:
    """Invert Raymer Eq. 12.21: S_flapped/S = (CLmax,req − CLmax,clean) / (0.9 Δc_l,max cos Λ_HL)."""
    dcl, scaled = FLAP_DCLMAX[kind]
    if scaled:
        dcl *= chord_extension
    if dcl <= 0:
        return float("inf")
    return max(0.0, (CLmax_req - CLmax_clean) / (0.9 * dcl * math.cos(sweep_hl)))


# ------------------------------------------------------------------ AVL helper
class _AVL:
    """AVL runs on the design geometry in the AVL frame (origin at the wing-root LE; x_abs = x_avl + x_apex)."""

    def __init__(self, res):
        if not avl_available():
            raise ToolNotAvailable("size_controls requer o AVL no PATH (ver docs/ARCHITECTURE.md §6)")
        self.cfg = res.config
        self.x_apex = res.stability.x_wing_apex
        self.runs = 0

    def __call__(self, layout: ControlLayout, *, alpha=None, CL=None, x_ref_abs: float, defl=None, hinge=False):
        self.runs += 1
        return run_avl_case(self.cfg, CL=CL, alpha_deg=alpha, x_ref=x_ref_abs - self.x_apex, deflections=defl,
                            controls=layout, hinge_moments=hinge)


def _layout(o: dict) -> ControlLayout:
    return ControlLayout(aileron_span_fraction=o["aileron_span_fraction"], aileron_hinge_xc=1 - o["aileron_cf_c"],
                         flap_hinge_xc=1 - o["flap_cf_c"], elevator_hinge_xc=1 - o["elevator_cf_c"],
                         rudder_hinge_xc=1 - o["rudder_cf_c"])


def _layout_dict(L: ControlLayout) -> dict:
    return {"aileron_span_fraction": L.aileron_span_fraction, "aileron_cf_c": 1 - L.aileron_hinge_xc,
            "flap_cf_c": 1 - L.flap_hinge_xc, "elevator_cf_c": 1 - L.elevator_hinge_xc,
            "rudder_cf_c": 1 - L.rudder_hinge_xc}


# ------------------------------------------------------------------ context
def _context(res, o: dict) -> dict:
    from ..performance import PerfModel
    from ..stability import inertias
    from ..systems_integration import is_uas
    st, w = res.stability, res.config.wing
    if st is None:
        raise ValueError("size_controls requer o estágio de estabilidade (resultado completo do pipeline)")
    W = res.sizing.W0 * G0
    rho0 = isa(0.0).rho
    S, b, c = w.S, w.span, w.mac
    hl = res.highlift
    Vs = lambda CLm, WW=W: math.sqrt(2 * WW / (rho0 * S * CLm))  # noqa: E731
    I = inertias(res, st, res.spec.assumptions["stability"].get("stations"))
    stations = {s["item"]: s["x_m"] for s in st.stations}
    fwd = max(st.cases, key=lambda k: k.SM)
    aft = min(st.cases, key=lambda k: k.SM)
    comp = res.spec.assumptions["weights"].get("components", {})
    gear = comp.get("landing_gear", "tricycle")
    h_mg = comp.get("main_gear_length_m", DEFAULT_MAIN_GEAR_LENGTH_M)
    vn = res.structures.vn if res.structures is not None else None
    regulation = (res.spec.requirements.value("regulatory_category") or "cs_23")
    return {"W": W, "rho0": rho0, "S": S, "b": b, "c": c, "I": I, "fwd": fwd, "aft": aft, "stations": stations,
            "Vs1": Vs(hl.CLmax_clean), "Vs_to": Vs(hl.CLmax_takeoff), "Vs0": Vs(hl.CLmax_landing),
            "CLmax": {"clean": hl.CLmax_clean, "takeoff": hl.CLmax_takeoff, "landing": hl.CLmax_landing},
            "pm": PerfModel.from_result(res), "gear": gear,
            "h_cg": o["cg_height_m"] if o["cg_height_m"] is not None else h_mg + 0.5 * res.config.fuselage.max_diameter,
            "uav": is_uas(res.spec), "regulation": str(regulation).lower(), "vn": vn,
            "V_cruise": res.cruise_speed, "rho_cruise": isa(res.cruise_altitude).rho,
            "VA": vn.VA if vn else 1.5 * Vs(hl.CLmax_clean), "VD": vn.VD if vn else 1.25 * 1.4 * res.cruise_speed,
            "n_engines": int(res.spec.assumptions["propulsion"].get("n_engines", 1)),
            "dx_fus": st.dx_fus}


# ------------------------------------------------------------------ aileron
def _roll_conditions(ctx, o):
    """Flight conditions per requirement kind: (V, rho, flap_deg)."""
    return {"cruise": (ctx["V_cruise"], ctx["rho_cruise"], 0.0),
            "approach": (1.3 * ctx["Vs0"], ctx["rho0"], o["flap_landing_deg"]),
            "approach_far": (1.3 * ctx["Vs0"], ctx["rho0"], o["flap_landing_deg"]),
            "takeoff": (1.2 * ctx["Vs1"], ctx["rho0"], o["flap_takeoff_deg"])}


def _evaluate_aileron(avl, layout, ctx, o, reqs):
    conds = _roll_conditions(ctx, o)
    dmax = math.radians(o["aileron_max_deg"])
    rows, cache = [], {}
    for r in reqs:
        V, rho, flap = conds[r["condition"]]
        key = (round(V, 3), flap)
        if key not in cache:
            CL = ctx["W"] / (0.5 * rho * V**2 * ctx["S"])
            a = avl(layout, CL=CL, x_ref_abs=ctx["aft"].x_cg, defl={"flap": flap})
            cache[key] = a
        a = cache[key]
        Clp = a.derivatives["Clp"]
        Clda = abs(a.controls["aileron"]["Cl"])
        rr = roll_response(Clp, Clda, dmax, V, rho, ctx["S"], ctx["b"], ctx["I"]["Ixx"])
        dphi = math.radians(r["dphi_deg"])
        t = time_to_bank(dphi, rr["p_ss"], rr["tau"])
        # deflection needed to just meet the requirement (φ linear in δa)
        phi_at_t = float(bank_angle(r["t_max"], rr["p_ss"], rr["tau"]))
        d_req = dmax * dphi / phi_at_t if phi_at_t > 0 else float("inf")
        lvl = None
        if "levels" in r:
            lvl = next((i + 1 for i, tl in enumerate(r["levels"]) if t <= tl), 4)
        rows.append({"requisito": r["name"], "V_m_s": V, "flap_deg": flap, "dphi_deg": r["dphi_deg"],
                     "t_max_s": r["t_max"], "t_s": t, "ok": t <= r["t_max"], "nivel": lvl,
                     "p_ss_deg_s": math.degrees(rr["p_ss"]), "pb_2V": rr["pb_2V"], "tau_s": rr["tau"],
                     "Clp": Clp, "Clda_per_rad": Clda, "Cnda_per_rad": a.controls["aileron"].get("Cn"),
                     "delta_a_req_deg": math.degrees(d_req), "margin_deg": o["aileron_max_deg"] - math.degrees(d_req),
                     "indicative": r["indicative"], "fonte": r["source"], "_rr": rr})
    return rows


def size_aileron(avl, ctx, o, base: ControlLayout) -> dict:
    reqs = roll_requirements(ctx["W"], ctx["regulation"], ctx["uav"], o["roll_level"])
    cur = _evaluate_aileron(avl, base, ctx, o, reqs)
    sized, chosen = None, None
    for f in o["aileron_span_candidates"]:
        rows = _evaluate_aileron(avl, replace(base, aileron_span_fraction=f), ctx, o, reqs)
        if all(r["ok"] for r in rows):
            sized, chosen = rows, f
            break
    return {"requirements": reqs, "current": cur, "current_span_fraction": base.aileron_span_fraction,
            "sized_span_fraction": chosen, "sized": sized, "cf_c": 1 - base.aileron_hinge_xc,
            "ok_current": all(r["ok"] for r in cur),
            "note": None if chosen else "nenhum candidato de envergadura cumpre todos os requisitos — aumentar a "
                                        "corda do aileron, a deflexão ou usar spoilers"}


# ------------------------------------------------------------------ elevator
def _lin_long(avl, layout, flap, x_ref_abs, alpha_ref=2.0):
    a = avl(layout, alpha=alpha_ref, x_ref_abs=x_ref_abs, defl={"flap": flap, "elevator": 0.0})
    e = a.controls["elevator"]
    return {"alpha_ref": math.radians(alpha_ref), "CL0": a.CL, "Cm0": a.Cm, "CLa": a.derivatives["CLa"],
            "Cma": a.derivatives["Cma"], "CLde": e["CL"], "Cmde": e["Cm"], "x_ref": x_ref_abs, "flap": flap}


def trim_point(lin: dict, CL_req: float, x_cg: float, c: float, dx_fus: float, dCm_thrust: float = 0.0) -> dict:
    """Linear trim (α, δe) for C_L = CL_req and C_m,cg = 0 (Etkin & Reid Sec. 2.4; Sadraey Eq. 12.88)."""
    k = (x_cg - lin["x_ref"]) / c - dx_fus
    CLa, CLde = lin["CLa"], lin["CLde"]
    Cma = lin["Cma"] + CLa * k
    Cmde = lin["Cmde"] + CLde * k
    Cm0 = lin["Cm0"] + lin["CL0"] * k + dCm_thrust
    A = np.array([[CLa, CLde], [Cma, Cmde]])
    da, de = np.linalg.solve(A, [CL_req - lin["CL0"], -Cm0])
    return {"alpha_deg": math.degrees(lin["alpha_ref"] + da), "delta_e_deg": math.degrees(de), "Cma_cg": Cma,
            "Cmde_cg": Cmde}


def _trim_map(avl, layout, ctx, o):
    c, W = ctx["c"], ctx["W"]
    flaps = {"limpo": 0.0, "descolagem": o["flap_takeoff_deg"], "aterragem": o["flap_landing_deg"]}
    vmax = {"limpo": ctx["VD"]}
    rows = []
    lins = {}
    for nm, fl in flaps.items():
        lin = _lin_long(avl, layout, fl, ctx["aft"].x_cg)
        lins[nm] = lin
        CLm = ctx["CLmax"]["clean" if fl == 0 else ("takeoff" if nm == "descolagem" else "landing")]
        for case in (ctx["fwd"], ctx["aft"]):
            Wc = case.mass * G0
            Vs = math.sqrt(2 * Wc / (ctx["rho0"] * ctx["S"] * CLm))
            Vhi = vmax.get(nm, o["flap_speed_factor"] * Vs)
            for V in np.linspace(Vs, Vhi, 9):
                CL = Wc / (0.5 * ctx["rho0"] * V**2 * ctx["S"])
                tp = trim_point(lin, CL, case.x_cg, c, ctx["dx_fus"])
                rows.append({"flap": nm, "flap_deg": fl, "cg": case.name, "x_cg": case.x_cg, "V_m_s": float(V),
                             "V_Vs": float(V / Vs), "CL": CL, **tp,
                             "ok": abs(tp["delta_e_deg"]) <= o["elevator_max_deg"]})
    return rows, lins


def _rotation(avl, layout, ctx, o) -> dict | None:
    if ctx["gear"] != "tricycle" or "main_gear" not in ctx["stations"]:
        return None
    pm, fwd = ctx["pm"], ctx["fwd"]
    m = fwd.mass
    W = m * G0
    x_mg = ctx["stations"]["main_gear"]
    rho = ctx["rho0"]
    Vs_to = math.sqrt(2 * W / (rho * ctx["S"] * ctx["CLmax"]["takeoff"]))
    VR = o["rotation_speed_factor"] * Vs_to
    q = 0.5 * rho * VR**2
    a = avl(layout, alpha=o["alpha_ground_deg"], x_ref_abs=x_mg, defl={"flap": o["flap_takeoff_deg"],
                                                                      "elevator": 0.0})
    CL = a.CL
    Cm_mg = a.Cm - ctx["dx_fus"] * CL
    Cmde = a.controls["elevator"]["Cm"]
    L = q * ctx["S"] * CL
    D = q * ctx["S"] * (pm.CD0 + pm.dCD0_to + pm.K * CL**2)
    if pm.P_sl:
        T = pm.eta_takeoff * pm.P_sl / VR
    else:
        T = pm.T_sl or 0.0
    acc = (T - D - pm.mu_roll * max(W - L, 0.0)) / m
    h = ctx["h_cg"]
    hT = h + o["thrust_line_z_m"]
    I = ctx["I"]
    dx = x_mg - fwd.x_cg
    Iyy_mg = I["Iyy"] * m / I["m"] + m * (dx**2 + h**2)
    thdd = math.radians(o["rotation_pitch_accel_deg_s2"])
    M_req = Iyy_mg * thdd + W * dx + T * hT - D * h - m * acc * h
    de = (M_req / (q * ctx["S"] * ctx["c"]) - Cm_mg) / Cmde
    return {"V_R_m_s": VR, "V_R_Vs": o["rotation_speed_factor"], "x_main_gear": x_mg, "x_cg_fwd": fwd.x_cg,
            "h_cg_m": h, "CL_ground": CL, "Cm_about_gear": Cm_mg, "Cmde_about_gear": Cmde, "T_N": T, "D_N": D,
            "L_N": L, "accel_m_s2": acc, "Iyy_mg": Iyy_mg, "theta_ddot_deg_s2": o["rotation_pitch_accel_deg_s2"],
            "delta_e_deg": math.degrees(de), "ok": abs(math.degrees(de)) <= o["elevator_max_deg"],
            "margin_deg": o["elevator_max_deg"] - abs(math.degrees(de)),
            "fonte": "Sadraey Sec. 12.6.3 Eqs. 12.55–12.73 (C_m sobre o trem principal pelo AVL)"}


def _tail_check(avl, layout, rows, ctx, o, res):
    """Indicative tail-stall check: tail C_L (on its own area, AVL surface forces, linear in α and δe) at every
    trim point vs C_L,max,h = 0.9 c_l,max,tail cos Λ (Raymer Eq. 12.15)."""
    ht = res.config.htail
    clmax_h = 0.9 * o["tail_clmax_airfoil"] * math.cos(ht.sweep_c4)
    tl = {}
    for fl in dict.fromkeys(r["flap_deg"] for r in rows):
        base = dict(x_ref_abs=ctx["aft"].x_cg)
        a0 = avl(layout, alpha=2.0, defl={"flap": fl, "elevator": 0.0}, **base)
        a1 = avl(layout, alpha=4.0, defl={"flap": fl, "elevator": 0.0}, **base)
        a2 = avl(layout, alpha=2.0, defl={"flap": fl, "elevator": 5.0}, **base)
        c0 = a0.surfaces["Htail"]["CL_surf"]
        tl[fl] = (c0, (a1.surfaces["Htail"]["CL_surf"] - c0) / 2.0, (a2.surfaces["Htail"]["CL_surf"] - c0) / 5.0)
    worst = 0.0
    for r in rows:
        c0, ca, cd = tl[r["flap_deg"]]
        r["CL_h"] = c0 + ca * (r["alpha_deg"] - 2.0) + cd * r["delta_e_deg"]
        worst = max(worst, abs(r["CL_h"]))
    return {"CLh_max": clmax_h, "CLh_worst": worst, "ok": worst <= clmax_h,
            "fonte": "AVL (C_L da empenagem) vs 0.9 c_l,max cos Λ (Raymer Eq. 12.15); c_l,max NACA 0012 ≈ 1.6 "
                     "(Abbott & von Doenhoff, Re 6e6) — PRESSUPOSTO, menor a baixo Re"}


def size_elevator(avl, ctx, o, base: ControlLayout, res) -> dict:
    def evaluate(L):
        rows, lins = _trim_map(avl, L, ctx, o)
        rot = _rotation(avl, L, ctx, o)
        ok = all(r["ok"] for r in rows) and (rot is None or rot["ok"])
        return rows, lins, rot, ok

    rows, lins, rot, ok = evaluate(base)
    tail = _tail_check(avl, base, rows, ctx, o, res)
    worst = max(rows, key=lambda r: abs(r["delta_e_deg"]))
    out = {"current_cf_c": 1 - base.elevator_hinge_xc, "trim_map": rows, "rotation": rot, "ok_current": ok,
           "worst_trim": worst, "margin_trim_deg": o["elevator_max_deg"] - abs(worst["delta_e_deg"]),
           "tail_stall": tail, "lin": lins}
    chosen, srow, srot = None, None, None
    for cf in o["elevator_cf_candidates"]:
        L = replace(base, elevator_hinge_xc=1 - cf)
        r2, _, rot2, ok2 = evaluate(L)
        if ok2:
            chosen, srow, srot = cf, max(r2, key=lambda r: abs(r["delta_e_deg"])), rot2
            break
    out.update({"sized_cf_c": chosen, "sized_worst_trim": srow, "sized_rotation": srot})
    if chosen is None:
        out["note"] = ("c_e/c_h até 0.5 não cumpre — Sadraey: considerar empenagem monobloco (all-moving), aumentar "
                       "S_h/braço ou restringir o CG dianteiro")
    elif chosen > 0.5:
        out["note"] = "c_e/c_h > 0.5 — Sadraey recomenda empenagem monobloco"
    return out


# ------------------------------------------------------------------ rudder
def _side_area(res, ctx):
    cfg = res.config
    fus = cfg.fuselage
    S_f = fus.wetted_area() / math.pi  # projected side area of a body of revolution ≈ Swet/π (exact for a cylinder)
    vt = cfg.vtail
    x_ac_w = res.stability.x_wing_apex + wing_x_ac(cfg.wing)
    x_v = x_ac_w + vt.arm  # vtail quarter-MAC station
    xs = (S_f * 0.5 * fus.length + vt.S * x_v) / (S_f + vt.S)  # fuselage side-area centroid at 0.5 L (ASSUMPTION)
    return S_f + vt.S, xs


def _lat_derivs(avl, layout, ctx, o, V, flap, res):
    CL = ctx["W"] / (0.5 * ctx["rho0"] * V**2 * ctx["S"])
    a = avl(layout, CL=CL, x_ref_abs=ctx["aft"].x_cg, defl={"flap": flap})
    d = a.derivatives
    fus = res.config.fuselage
    Cnb_f = -1.3 * (fus.wetted_area() * fus.max_diameter / 4) / (ctx["S"] * ctx["b"])  # Raymer Eq. 16.47
    ca, cr = a.controls["aileron"], a.controls["rudder"]
    # standard rudder sign (positive = TE left → C_nδr < 0): AVL hinge vector +z gives the opposite sign
    return CL, {"CYb": d["CYb"], "Clb": d["Clb"], "Cnb": d["Cnb"] + Cnb_f, "Cnb_fus": Cnb_f,
                "CYda": ca.get("CY", 0.0), "Clda": ca.get("Cl", 0.0), "Cnda": ca.get("Cn", 0.0),
                "CYdr": -cr.get("CY", 0.0), "Cldr": -cr.get("Cl", 0.0), "Cndr": -cr.get("Cn", 0.0)}


def _crosswind(avl, layout, ctx, o, res):
    V = o["crosswind_speed_factor"] * ctx["Vs0"]
    CL, d = _lat_derivs(avl, layout, ctx, o, V, o["flap_landing_deg"], res)
    req_kt = o["crosswind_kt"]
    req = req_kt * 0.514444 if req_kt is not None else 0.2 * ctx["Vs0"]
    src = "utilizador" if req_kt is not None else "14 CFR 23.233(a) (pré-Amdt 64): ≥ 0.2 V_S0"
    beta = math.atan2(req, V)
    ss = steady_sideslip(beta, CL, d)
    ratio = max(abs(math.degrees(ss["delta_r"])) / o["rudder_max_deg"],
                abs(math.degrees(ss["delta_a"])) / o["aileron_max_deg"])
    beta_lim = beta / ratio if ratio > 0 else float("inf")
    Vw_max = V * math.tan(min(beta_lim, math.radians(80)))
    Ss, x_ca = _side_area(res, ctx)
    sad = sadraey_crab(req, V, ctx["rho0"], ctx["S"], ctx["b"], Ss, x_ca - ctx["aft"].x_cg,
                       o["side_drag_coefficient"], d["Cnb"], d["CYb"], d["Cndr"], d["CYdr"])
    dr = math.degrees(ss["delta_r"])
    return {"U_m_s": V, "crosswind_req_m_s": req, "crosswind_req_kt": req / 0.514444, "fonte": src,
            "beta_deg": math.degrees(beta), "delta_r_deg": dr, "delta_a_deg": math.degrees(ss["delta_a"]),
            "bank_deg": math.degrees(ss["phi"]), "ok": ratio <= 1.0, "margin_deg": o["rudder_max_deg"] - abs(dr),
            "crosswind_max_kt": Vw_max / 0.514444, "limited_by": "leme" if abs(dr) / o["rudder_max_deg"] >=
            abs(math.degrees(ss["delta_a"])) / o["aileron_max_deg"] else "aileron",
            "derivatives": d, "sadraey_crab": {"delta_r_deg": math.degrees(sad["delta_r"]),
                                               "crab_deg": math.degrees(sad["crab"]), "side_area_m2": Ss,
                                               "dc_m": x_ca - ctx["aft"].x_cg, "converged": sad["converged"]}}


def _oei(avl, layout, ctx, o, res):
    if ctx["n_engines"] < 2:
        return {"applicable": False, "note": "monomotor (tração no eixo) — OEI não aplicável (Sadraey 12.6.2.2)"}
    if o["engine_y_m"] is None:
        return {"applicable": True, "ok": None, "note": "multimotor: indicar engine_y_m (posição lateral do motor)"}
    pm = ctx["pm"]
    Vmc = o["vmc_factor"] * ctx["Vs_to"]
    q = 0.5 * ctx["rho0"] * Vmc**2
    T1 = (pm.eta_takeoff * pm.P_sl / Vmc if pm.P_sl else (pm.T_sl or 0.0)) / ctx["n_engines"]
    _, d = _lat_derivs(avl, layout, ctx, o, Vmc, o["flap_takeoff_deg"], res)
    dr = -T1 * o["engine_y_m"] / (q * ctx["S"] * ctx["b"] * d["Cndr"])
    return {"applicable": True, "V_MC_m_s": Vmc, "T_engine_N": T1, "delta_r_deg": math.degrees(dr),
            "ok": abs(math.degrees(dr)) <= o["rudder_max_deg"], "fonte": "Sadraey Eq. 12.102"}


def size_rudder(avl, ctx, o, base: ControlLayout, res) -> dict:
    cw = _crosswind(avl, base, ctx, o, res)
    oei = _oei(avl, base, ctx, o, res)
    out = {"current_cf_c": 1 - base.rudder_hinge_xc, "crosswind": cw, "oei": oei,
           "ok_current": cw["ok"] and oei.get("ok") is not False,
           "spin": "recuperação de vrille NÃO avaliada (requer dados de túnel de vrille ou critério TDPF — Raymer "
                   "6th ed. Cap. 16); obrigatória para aviões 'spinnable' (CS 23.221)"}
    chosen, scw = None, None
    for cf in o["rudder_cf_candidates"]:
        L = replace(base, rudder_hinge_xc=1 - cf)
        c2 = _crosswind(avl, L, ctx, o, res)
        o2 = _oei(avl, L, ctx, o, res)
        if c2["ok"] and o2.get("ok") is not False:
            chosen, scw = cf, c2
            break
    out.update({"sized_cf_c": chosen, "sized_crosswind": scw})
    return out


# ------------------------------------------------------------------ flaps
def size_flaps(res, ctx, o, base: ControlLayout) -> dict:
    from ..performance import landing_distance
    w = res.config.wing
    pm = ctx["pm"]
    W = ctx["W"]
    reqs = res.spec.requirements
    out = {"CLmax_landing_current": ctx["CLmax"]["landing"], "CLmax_clean": ctx["CLmax"]["clean"]}
    need = []
    vs_req = reqs.value("stall_speed")
    if vs_req:
        need.append(("stall_speed", 2 * W / (ctx["rho0"] * ctx["S"] * vs_req**2)))
    ld_req = reqs.value("landing_distance")
    if ld_req:
        def dist(CLm):
            return landing_distance(replace(pm, CLmax_land=CLm), W)["total_50ft"]
        lo, hi = ctx["CLmax"]["clean"], 6.0
        if dist(hi) > ld_req:
            need.append(("landing_distance", float("inf")))
        elif dist(lo) <= ld_req:
            need.append(("landing_distance", lo))
        else:
            for _ in range(50):
                mid = 0.5 * (lo + hi)
                lo, hi = (lo, mid) if dist(mid) <= ld_req else (mid, hi)
            need.append(("landing_distance", hi))
    flap_cfg = res.spec.assumptions["aero"].get("flap") or {}
    kind = flap_cfg.get("kind", "plain")
    CLreq = max([v for _, v in need], default=ctx["CLmax"]["landing"])
    ratio = flapped_ratio_required(CLreq, ctx["CLmax"]["clean"], kind, 0.0, flap_cfg.get("chord_extension", 1.0))
    # flapped area available between the fuselage side and the aileron (both sides)
    b2 = w.span / 2
    y0 = 0.5 * res.config.fuselage.max_diameter
    y1 = (1 - base.aileron_span_fraction) * b2
    yy = np.linspace(y0, y1, 50)
    cc = w.c_root + (w.c_tip - w.c_root) * yy / b2
    avail = 2 * float(np.trapezoid(cc, yy)) / w.S if y1 > y0 else 0.0
    out.update({"requirements": [{"requisito": k, "CLmax_req": v} for k, v in need], "CLmax_required": CLreq,
                "flap_kind": kind, "flapped_area_ratio_required": ratio,
                "flapped_area_ratio_current": flap_cfg.get("flapped_area_ratio"),
                "flapped_area_ratio_available": avail, "ok": ratio <= avail,
                "fonte": "Raymer Eq. 12.21 invertida; distância de aterragem Raymer Sec. 17.9"})
    if ld_req and ratio > avail:
        ld = landing_distance(pm, W)
        out["note"] = (f"Requisito de aterragem não alcançável só com flaps: a aproximação desde 50 ft "
                       f"({ld['approach']:.0f} m a γ = {ld['gamma_deg']:.0f}°) pesa {ld['approach'] / ld['total_50ft']:.0%} "
                       f"dos {ld['total_50ft']:.0f} m — rever o ângulo de aproximação, travagem (μ) ou o requisito.")
    return out


# ------------------------------------------------------------------ hinge moments
def _surface_geometry(res, L: ControlLayout) -> dict:
    cfg = res.config
    w, ht, vt = cfg.wing, cfg.htail.as_wing(), cfg.vtail.as_wing()
    b2 = w.span / 2
    y = np.linspace((1 - L.aileron_span_fraction) * b2, b2, 50)
    c = w.c_root + (w.c_tip - w.c_root) * y / b2
    cfa = 1 - L.aileron_hinge_xc
    Sa = float(np.trapezoid(cfa * c, y))
    cfe, cfr = 1 - L.elevator_hinge_xc, 1 - L.rudder_hinge_xc
    return {"aileron": (Sa, Sa / (y[-1] - y[0]), 2), "elevator": (cfe * cfg.htail.S, cfe * ht.mac, 1),
            "rudder": (cfr * cfg.vtail.S, cfr * vt.mac, 1)}


def hinge_moments(avl, res, ctx, o, L: ControlLayout) -> dict:
    x_ref = ctx["aft"].x_cg
    names = ("aileron", "elevator", "rudder", "flap")
    a0 = avl(L, alpha=0.0, x_ref_abs=x_ref, defl={n: 0.0 for n in names}, hinge=True)
    a5 = avl(L, alpha=5.0, x_ref_abs=x_ref, defl={n: 0.0 for n in names}, hinge=True)
    CLa = a0.derivatives["CLa"]
    aL0 = -a0.CL / CLa
    geo = _surface_geometry(res, L)
    S, c = ctx["S"], ctx["c"]
    maxdef = {"aileron": o["aileron_max_deg"], "elevator": o["elevator_max_deg"], "rudder": o["rudder_max_deg"]}
    out = {}
    from acdt.core.systems.database import load_default_db
    from acdt.core.systems.servos import select_servo
    sysspec = res.spec.systems or {}
    db = load_default_db().merged(sysspec.get("components"))
    sv = sysspec.get("servos", {})
    linkage = sv.get("linkage_ratio", o["linkage_ratio"])
    fos = sv.get("factor_of_safety", o["factor_of_safety"])
    vbus = sv.get("v_bus", o["v_servo"])
    for n in ("aileron", "elevator", "rudder"):
        ad = avl(L, alpha=0.0, x_ref_abs=x_ref, defl={**{k: 0.0 for k in names}, n: 10.0}, hinge=True)
        Ch0 = a0.hinge.get(n, 0.0)
        Cha = (a5.hinge.get(n, 0.0) - Ch0) / math.radians(5.0)
        Chd = (ad.hinge.get(n, 0.0) - Ch0) / math.radians(10.0)
        Sc, cc, nsurf = geo[n]
        k = S * c / (Sc * cc * nsurf)  # convert to the surface reference (per surface)
        conds = []
        for nm, V, frac in (("V_A, deflexão total", ctx["VA"], 1.0), ("V_D, 1/3 da deflexão", ctx["VD"], 1 / 3)):
            q = 0.5 * ctx["rho0"] * V**2
            CL = ctx["W"] / (q * S)
            alpha = aL0 + CL / CLa
            dl = math.radians(maxdef[n]) * frac
            H = q * S * c * (Ch0 + (Cha * alpha if n != "rudder" else 0.0) + Chd * dl) / nsurf
            conds.append({"condição": nm, "V_m_s": V, "delta_deg": math.degrees(dl), "H_Nm": H})
        Hmax = max(abs(x["H_Nm"]) for x in conds)
        T = Hmax * linkage * fos
        servo = select_servo(db.servos, T, vbus) if ctx["uav"] else None
        out[n] = {"Ch_alpha_ref": Cha, "Ch_delta_ref": Chd, "Ch_alpha_surface": Cha * k, "Ch_delta_surface": Chd * k,
                  "S_surface_m2": Sc, "c_surface_m": cc, "n_surfaces": nsurf, "conditions": conds,
                  "H_max_Nm": Hmax, "torque_required_Nm": T,
                  "servo": servo if ctx["uav"] else "avião tripulado: comandos manuais — verificar forças no manche "
                                                   "(CS 23.143) com H e a relação de transmissão",
                  "fonte": "AVL HM (invíscido) + 14 CFR 23.455(a)(2) (V_A total, V_D 1/3)"}
    return out


# ------------------------------------------------------------------ plots
def plot_roll(ail: dict, path, title=""):
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(7, 4.2))
    styles = ["-", "--", "-.", ":"]
    for i, r in enumerate(ail["current"]):
        rr = r["_rr"]
        t = np.linspace(0, max(r["t_max_s"] * 1.2, 1.0), 200)
        ln, = ax.plot(t, np.degrees(bank_angle(t, rr["p_ss"], rr["tau"])), styles[i % 4],
                      label=f"{r['requisito']} (t = {r['t_s']:.2f} s)")
        ax.plot([r["t_max_s"]], [r["dphi_deg"]], "o", color=ln.get_color())
    ax.set_ylim(0, 2.0 * max(r["dphi_deg"] for r in ail["current"]))
    ax.set_xlabel("t [s]")
    ax.set_ylabel("Δφ [deg] (aileron máximo, degrau)")
    ax.set_title(title or "Resposta em rolamento vs requisitos (pontos = Δφ exigido no tempo máximo)")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def plot_trim(el: dict, path, emax: float, title=""):
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(7, 4.2))
    rows = el["trim_map"]
    for fl in dict.fromkeys(r["flap"] for r in rows):
        for cg, ls in (("fwd", "-"), ("aft", "--")):
            sel = [r for r in rows if r["flap"] == fl]
            cgs = list(dict.fromkeys(r["cg"] for r in sel))
            name = cgs[0] if cg == "fwd" else cgs[-1]
            pts = [r for r in sel if r["cg"] == name]
            ax.plot([p["V_m_s"] for p in pts], [p["delta_e_deg"] for p in pts], ls, label=f"{fl} / {name}")
    if el.get("rotation"):
        ax.plot([el["rotation"]["V_R_m_s"]], [el["rotation"]["delta_e_deg"]], "k*", ms=11, label="rotação (V_R)")
    ax.axhline(-emax, color="r", lw=0.8)
    ax.axhline(emax, color="r", lw=0.8)
    ax.set_xlabel("V [m/s] EAS")
    ax.set_ylabel("δe de compensação [deg] (+ = bordo de fuga em baixo)")
    ax.set_title(title or "Mapa de compensação do profundor")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


# ------------------------------------------------------------------ driver
def size_controls(res, opts: dict | None = None, out_dir: str | Path | None = None) -> ControlSizingResult:
    """Size aileron / elevator / rudder / flaps of a converged design by performance requirements.

    ``opts`` override :data:`DEFAULTS` (also read from ``assumptions.stability.controls`` of the spec)."""
    o = {**DEFAULTS, **(res.spec.assumptions.get("stability", {}).get("controls") or {}), **(opts or {})}
    stab = res.spec.assumptions.get("stability", {})
    for k in ("aileron_span_fraction", "aileron_cf_c", "elevator_cf_c", "rudder_cf_c", "elevator_max_deg"):
        if k in stab and k not in (opts or {}) and k not in (stab.get("controls") or {}):
            o[k] = stab[k]
    avl = _AVL(res)
    ctx = _context(res, o)
    base = _layout(o)
    notes = []
    ail = size_aileron(avl, ctx, o, base)
    el = size_elevator(avl, ctx, o, base, res)
    rud = size_rudder(avl, ctx, o, base, res)
    fl = size_flaps(res, ctx, o, base)
    sized = replace(base,
                    aileron_span_fraction=ail["sized_span_fraction"] or base.aileron_span_fraction,
                    elevator_hinge_xc=1 - (el["sized_cf_c"] or (1 - base.elevator_hinge_xc)),
                    rudder_hinge_xc=1 - (rud["sized_cf_c"] or (1 - base.rudder_hinge_xc)))
    hm = hinge_moments(avl, res, ctx, o, sized)
    if el["rotation"] is None:
        notes.append(f"Rotação na descolagem não avaliada (trem '{ctx['gear']}': só triciclo implementado; "
                     "lançamento por catapulta/sem trem não requer rotação).")
    if ctx["uav"]:
        notes.append("UAV: requisitos de rolamento MIL-F-8785C Classe I usados como orientação (indicativos).")
    notes.append(f"AVL sem fuselagem: C_nβ inclui o termo de fuselagem de Raymer Eq. 16.47; C_m inclui o desvio do "
                 f"ponto neutro por fuselagem (dx_fus = {ctx['dx_fus']:+.3f} c̄). Efeito de solo e de hélice ignorados.")
    notes.append(f"Flaps: descolagem {o['flap_takeoff_deg']:g}°, aterragem {o['flap_landing_deg']:g}° (PRESSUPOSTO "
                 "— indicar os valores do projeto em assumptions.stability.controls).")
    notes.append(f"Inércias por soma de componentes (Ixx {ctx['I']['Ixx']:.0f}, Iyy {ctx['I']['Iyy']:.0f}, "
                 f"Izz {ctx['I']['Izz']:.0f} kg m²); altura do CG ao solo {ctx['h_cg']:.2f} m (PRESSUPOSTO se não dada).")
    notes.append(f"AVL: {avl.runs} casos corridos.")
    r = ControlSizingResult(ail, el, rud, fl, hm, _layout_dict(base), _layout_dict(sized), notes)
    if out_dir is not None:
        od = Path(out_dir)
        od.mkdir(parents=True, exist_ok=True)
        plot_roll(ail, od / "controls_roll.png")
        plot_trim(el, od / "controls_trim.png", o["elevator_max_deg"])
        r.plots = {"roll": od / "controls_roll.png", "trim": od / "controls_trim.png"}
    return r
