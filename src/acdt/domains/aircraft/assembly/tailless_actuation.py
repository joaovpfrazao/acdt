# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Actuation of a tailless split-aileron flying wing (follow-up to :mod:`.tailless`, 10 nov 2026).

Opt-in through the same ``assumptions.assembly.options.flying_wing`` block (``yaw_control: split_aileron``)::

    flying_wing:
      actuators:
        catalog:                       # vendor datasheets (never invented): rated torque at rated speed
          - {name: "Volz DA 26-30-5024", torque_Nm: 2.7, speed_deg_s: 200, mass_kg: 0.270, source: "..."}
        factor_of_safety: 1.5          # default as flightsim.controls (servo torque = |H| · FoS)
        max_per_surface: 1             # identical servos ganged per leaf / elevon (PRESSUPOSTO load sharing)
        split_rate_required_deg_s: null  # opt-in design surface rate of the split leaves [°/s] (e.g. the lateral
                                         # gust rate); the servo pick uses max(turbulence 3σ rate, this)
        lag_s: null                    # first-order lag of the actuator [s] (unknown → see below)
        delay_s: null                  # pure transport delay of sensor + computer + actuator [s]

Methods (cited)
---------------
* **Split-leaf hinge moment** — wind-tunnel data, NACA TN 690 (Wenzinger & Rogallo 1939, "Résumé of air-load data
  on slats and flaps"), Figs. 17–18: hinge-moment coefficient of 0.15c and 0.25c full-span split flaps on a
  Clark Y wing (data of NACA TN 498), C_hf = H/(q c_f S_f) on the flap chord and flap area, α = −10…20°,
  δ_f = 0…60° (0.15c) / 0…45° (0.25c). The text of TN 690 states the coefficients of the two sizes are
  "practically the same". Here the envelope |C_hf|(δ) over all α of both figures (read from the plots,
  ±0.01) is used. PRESSUPOSTOS: (i) extrapolation to the c_f/c of the design (0.40 in the example, outside the
  tested 0.15–0.25); (ii) the upper leaf (opening into the suction side) gets the same |C_hf| as the lower
  leaf — no data opened for an upper split leaf; (iii) δ > 60° is outside the data → unassessed.
* **Elevon hinge moment** — AVL ``HM`` (inviscid, sealed plain flap, no balance; as
  :func:`..flightsim.controls.hinge_moments`): C_h0, C_hα (symmetric control) and C_hδ (antisymmetric) by
  finite differences.
* **Design conditions** — 14 CFR 23.455(a)(2) (pre-Amdt 23-64) deflection schedule used by the acdt for all
  surfaces: full deflection at V_A, one third at V_D (PRESSUPOSTO for a yaw/drag surface, as for the rudder
  in :mod:`..flightsim.controls`).
* **Servo** — rated torque at rated speed from the vendor datasheet (catalog entries carry their source); with a
  linkage gearing G (surface torque = G·T, surface rate = ω/G) a servo fits when
  G·T_rated ≥ FoS·|H| and ω_rated/G ≥ required rate, i.e. T_rated·ω_rated ≥ FoS·|H|·rate; the lightest
  fitting servo is chosen. Up to ``max_per_surface`` identical servos may be ganged on one leaf/elevon
  (PRESSUPOSTO: equal load sharing, torque × n). Servo travel and back-drive stiffness: unassessed. Four leaves
  (two per side) and two elevons.
* **Actuator dynamics in the SAS loop** — first-order lag 1/(τ_a s + 1) and transport delay e^{−τ_d s}
  (2nd-order Padé) in series with u = k_β β − k_r r̂ (MIL-F-8785C 3.5.3: equivalent time delay of the flight
  control system incl. SAS ≤ 0.10 / 0.20 / 0.25 s for Levels 1/2/3; values as quoted in NASA NTRS 19910005040
  §2.1.1 and AIAA J. Guid. doi:10.2514/3.20149). When τ_a and τ_d are not given, the loop is assessed with a
  pure delay equal to the Level-1 limit (0.10 s, PRESSUPOSTO: everything lumped as an equivalent delay) and
  the delay margin (largest delay keeping Table VI Level 1) is reported. Rate limit and the sin² law of the
  split surface are nonlinear: they are applied in the time-domain gust response (:func:`gust_response`).
* **Lateral discrete gust** — 14 CFR 23.443(a)/(b) (pre-Amdt 23-64): lateral gust of the 23.333(c) value at V_C
  (U_de = 50 ft/s from sea level to 20 000 ft), shape of 23.333(c)(2)(i), U = (U_de/2)(1 − cos 2πs/25c̄), c̄ the
  wing mean geometric chord. 23.443 is a loads requirement for vertical surfaces; with none, it is used here
  as the yaw-control sizing gust (PRESSUPOSTO). U_de is an equivalent airspeed: TAS gust U_de·√(ρ0/ρ). Point
  model (no gust penetration along the span), linear lateral airframe [β, p, r, φ], bank hold by the
  elevon with the successive-loop-closure gains of Beard & McLain 2012 Sec. 6.3 (as
  :mod:`..flightsim.autopilot`), SAS through the actuator model (delay, lag, rate limit, δ_max saturation,
  ΔC_n = 2 C₁ sin²δ). Pass = no deflection saturation and no rate limiting while the SAS demand is applied.
"""
from __future__ import annotations

import math
from collections import deque

import numpy as np

# NACA TN 690 Figs. 17–18 (TN 498 data): envelope of |C_hf| over α = −10…20° for both flap chords, read ±0.01.
SPLIT_CH_DELTA_DEG = (0.0, 15.0, 30.0, 45.0, 60.0)
SPLIT_CH_ABS = (0.135, 0.30, 0.43, 0.555, 0.64)
SPLIT_CH_SOURCE = ("NACA TN 690 (Wenzinger & Rogallo 1939) Figs. 17–18, dados de NACA TN 498: C_hf = H/(q c_f S_f) "
                   "de split flaps 0,15c e 0,25c (Clark Y), envolvente |C_hf| em α −10…20° lida dos gráficos (±0,01)")
TIME_DELAY_LIMITS_S = (0.10, 0.20, 0.25)
TIME_DELAY_SOURCE = ("MIL-F-8785C 3.5.3: atraso equivalente do sistema de comando (inclui SAS) ≤ 0,10/0,20/0,25 s "
                     "Níveis 1/2/3 (citado em NASA NTRS 19910005040 §2.1.1 e AIAA doi:10.2514/3.20149)")
GUST_SOURCE = ("14 CFR 23.443(a)/(b) e 23.333(c) (pré-Amdt 23-64): rajada lateral de 50 ft/s EAS em V_C (até "
               "20 000 ft), forma U = (U_de/2)(1 − cos 2πs/25c̄); 23.443 é de cargas em superfícies verticais — "
               "aqui PRESSUPOSTO como rajada de dimensionamento da guinada")
HINGE_SCHEDULE_SOURCE = "14 CFR 23.455(a)(2) pré-Amdt 64: deflexão total em V_A, 1/3 em V_D (como flightsim.controls)"
U_DE_VC_FPS = 50.0
FT = 0.3048


# ------------------------------------------------------------------------------------------- hinge moments
def split_ch(delta_deg: float) -> float | None:
    """|C_hf| of a split leaf at δ (TN 690 envelope); None beyond the data (δ > 60°)."""
    d = abs(float(delta_deg))
    if d > SPLIT_CH_DELTA_DEG[-1] + 1e-9:
        return None
    return float(np.interp(d, SPLIT_CH_DELTA_DEG, SPLIT_CH_ABS))


def split_leaf_geometry(geom: dict) -> dict:
    """Leaf area and mean leaf chord of one split surface (one side): S_f, c_f = S_f / span."""
    span = (geom["eta_outer"] - geom["eta_inner"]) * geom["semispan"]
    return {"S_leaf": geom["S_f"], "c_leaf": geom["S_f"] / span, "span": span}


def split_hinge(geom: dict, delta_max_deg: float, VA: float, VD: float, rho0: float) -> dict:
    lg = split_leaf_geometry(geom)
    conds = []
    for nm, V, frac in (("V_A, deflexão total", VA, 1.0), ("V_D, 1/3 da deflexão", VD, 1.0 / 3.0)):
        q = 0.5 * rho0 * V**2
        d = delta_max_deg * frac
        ch = split_ch(d)
        conds.append({"condição": nm, "V_m_s": V, "delta_deg": d, "Ch_abs": ch,
                      "H_Nm": (ch * q * lg["S_leaf"] * lg["c_leaf"]) if ch is not None else None})
    hs = [c["H_Nm"] for c in conds]
    return {**lg, "conditions": conds, "H_max_Nm": None if any(h is None for h in hs) else max(hs),
            "source": SPLIT_CH_SOURCE, "schedule": HINGE_SCHEDULE_SOURCE,
            "pressupostos": ["c_f/c extrapolado dos 0,15–0,25c ensaiados", "folha superior = |C_hf| da folha inferior "
                             "(sem dados)", "δ > 60° fora dos dados → unassessed"]}


def elevon_hinge(hm: dict, elevon_geom: dict, S: float, c: float, el_max_deg: float, VA: float, VD: float,
                 rho0: float, W: float, CLa: float, CL0: float) -> dict:
    """Per-side elevon hinge moment from AVL HM coefficients (ref. S·c̄): ``hm`` = {Ch0, Cha, Chd} per side."""
    aL0 = -CL0 / CLa
    conds = []
    for nm, V, frac in (("V_A, deflexão total", VA, 1.0), ("V_D, 1/3 da deflexão", VD, 1.0 / 3.0)):
        q = 0.5 * rho0 * V**2
        alpha = aL0 + W / (q * S) / CLa
        dl = math.radians(el_max_deg) * frac
        H = q * S * c * (hm["Ch0"] + hm["Cha"] * alpha + hm["Chd"] * dl)
        conds.append({"condição": nm, "V_m_s": V, "alpha_deg": math.degrees(alpha), "delta_deg": math.degrees(dl),
                      "H_Nm": H})
    k = S * c / (elevon_geom["S_e"] * elevon_geom["c_e"])
    return {"Ch0_ref": hm["Ch0"], "Ch_alpha_ref": hm["Cha"], "Ch_delta_ref": hm["Chd"],
            "Ch_alpha_surface": hm["Cha"] * k, "Ch_delta_surface": hm["Chd"] * k, **elevon_geom,
            "conditions": conds, "H_max_Nm": max(abs(x["H_Nm"]) for x in conds),
            "source": "AVL HM (invíscido, flap simples selado, sem compensação) — estimativa a calibrar",
            "schedule": HINGE_SCHEDULE_SOURCE}


# ------------------------------------------------------------------------------------------- servo selection
def select_servo(catalog: list[dict], H_sched: float | None, rate_deg_s: float | None, fos: float,
                 H_op: float | None = None, n_max: int = 1, delta_max_deg: float | None = None) -> dict:
    """Lightest catalog servo that (i) holds FoS·|H| of the 23.455 schedule with its peak (stall) torque and
    (ii) moves the operating hinge moment FoS·|H_op| at the required rate with its rated torque at rated speed:
    G = max(FoS·|H|/T_peak, FoS·|H_op|/T_rated), surface rate ω_rated/G ≥ rate. ``H_op`` None → H_sched.
    Servo travel: G·δ_max ≤ ``travel_deg`` (± from neutral) when the datasheet gives it, else unassessed (None);
    a known travel exceedance disqualifies the servo. ``n_max`` identical servos ganged (equal sharing, PRESSUPOSTO)."""
    if H_sched is None:
        return {"status": "unassessed", "ok": None, "issue": "momento de charneira desconhecido"}
    if not catalog:
        return {"status": "unassessed", "ok": None, "issue": "sem catálogo de servos (actuators.catalog) — "
                "nenhum servo inventado"}
    Hh = fos * abs(H_sched)
    Hd = fos * abs(H_op if H_op is not None else H_sched)
    rows = []
    for s in catalog:
        for n in range(1, max(int(n_max), 1) + 1):
            T, w = n * float(s["torque_Nm"]), float(s["speed_deg_s"])
            Tp = n * float(s.get("peak_torque_Nm") or s["torque_Nm"])
            G = max(Hh / Tp, Hd / T)
            rate_at_surface = w / G
            trv = s.get("travel_deg")
            travel_ok = (None if trv is None or delta_max_deg is None
                         else bool(G * abs(delta_max_deg) <= float(trv) + 1e-9))
            ok = (rate_deg_s is None or rate_at_surface >= rate_deg_s) and travel_ok is not False
            rows.append({"travel_required_deg": (G * abs(delta_max_deg) if delta_max_deg is not None else None),
                         "travel_deg": trv, "travel_ok": travel_ok,"name": s["name"], "n_per_surface": n, "unit_mass_kg": float(s["mass_kg"]),
                         "mass_kg": n * float(s["mass_kg"]), "gearing": G,
                         "rate_at_surface_deg_s": rate_at_surface, "fits": ok, "source": s.get("source")})
    fit = [r for r in rows if r["fits"]]
    out = {"torque_hold_required_Nm": Hh, "torque_operating_required_Nm": Hd, "H_schedule_Nm": abs(H_sched),
           "H_operating_Nm": abs(H_op) if H_op is not None else None, "factor_of_safety": fos,
           "rate_required_deg_s": rate_deg_s, "candidates": rows,
           "rule": ("G = max(FoS·|H|/T_pico, FoS·|H_op|/T_nominal); taxa na superfície ω_nominal/G ≥ taxa exigida "
                    "; curso do servo G·δ_max ≤ curso do datasheet quando dado (senão unassessed); rigidez unassessed")}
    if not fit:
        out.update({"status": "assessed", "ok": False, "servo": None,
                    "issue": f"nenhum servo do catálogo segura {Hh:.1f} N·m e move {Hd:.1f} N·m a "
                             f"{rate_deg_s if rate_deg_s is not None else 0:.0f} °/s na superfície"})
        return out
    best = min(fit, key=lambda r: r["mass_kg"])
    out.update({"status": "assessed" if rate_deg_s is not None else "partial",
                "ok": True if rate_deg_s is not None else None, "servo": best})
    if rate_deg_s is None:
        out["issue"] = "taxa exigida desconhecida — só binário verificado (taxa unassessed)"
    return out


def budget_items(items: list[dict] | None) -> list[dict]:
    """Declared mass items that hold servos/actuators (name contains servo/atuador/actuator)."""
    keys = ("servo", "atuador", "actuator")
    return [i for i in (items or []) if any(k in str(i.get("name", "")).lower() for k in keys)]


# ------------------------------------------------------------------------------------------- actuator dynamics
def pade2(tau: float):
    """2nd-order Padé of e^{−τs}: (A, B, C, D)."""
    if tau <= 0:
        return None
    A = np.array([[0.0, 1.0], [-12.0 / tau**2, -6.0 / tau]])
    return A, np.array([[0.0], [1.0]]), np.array([[0.0, -12.0 / tau]]), 1.0


def augmented_loop(A4: np.ndarray, kb: float, kr: float, qSb_Izz: float, b: float, U: float, lag_s: float,
                   delay_s: float) -> np.ndarray:
    """[β, p, r, φ] + delay (Padé 2) + lag states; u_cmd = k_β β − k_r r̂ acts on N through delay and lag."""
    A4 = np.array(A4, float)
    K = np.array([kb, 0.0, -kr * b / (2 * U), 0.0])
    Bu = np.array([0.0, 0.0, qSb_Izz, 0.0])
    pd = pade2(delay_s)
    nd = 0 if pd is None else 2
    nl = 1 if lag_s > 0 else 0
    n = 4 + nd + nl
    M = np.zeros((n, n))
    M[:4, :4] = A4
    # delay output y_d = Cd z + Dd u_cmd
    if pd is not None:
        Ad, Bd, Cd, Dd = pd
        M[4:6, 4:6] = Ad
        M[4:6, :4] = Bd @ K[None, :]
        yd_x, yd_z = Dd * K, Cd[0]
    else:
        yd_x, yd_z = K, np.zeros(0)
    if nl:
        il = 4 + nd
        M[il, :4] += yd_x / lag_s
        if nd:
            M[il, 4:6] += yd_z / lag_s
        M[il, il] = -1.0 / lag_s
        M[:4, il] += Bu
    else:
        M[:4, :4] += np.outer(Bu, yd_x)
        if nd:
            M[:4, 4:6] += np.outer(Bu, yd_z)
    return M


def dr_level(zeta: float, wn: float, cat: str) -> int:
    from ..stability import MIL_F_8785C
    for i, (z, zw, w) in enumerate(MIL_F_8785C["dutch_roll"][cat]):
        if zeta >= z and zeta * wn >= zw and wn >= w:
            return i + 1
    return 4


def dutch_roll_of(M: np.ndarray, ref: complex) -> dict | None:
    """Complex pair of ``M`` closest to the reference Dutch-roll eigenvalue (ideal closed loop)."""
    lam = [l for l in np.linalg.eigvals(M) if l.imag > 1e-9]
    if not lam:
        return None
    l = min(lam, key=lambda x: abs(x - ref))
    wn = abs(l)
    return {"lambda": complex(l), "wn": float(wn), "zeta": float(-l.real / wn)}


def actuator_dynamics(A4, kb, kr, qSb_Izz, b, U, cat: str, lag_s, delay_s) -> dict:
    """Dutch roll with the actuator model; delay margin for Level 1. Unknown lag/delay → 0.10 s equivalent delay."""
    lam_ideal = [l for l in np.linalg.eigvals(augmented_loop(A4, kb, kr, qSb_Izz, b, U, 0.0, 0.0)) if l.imag > 1e-9]
    if not lam_ideal:
        return {"status": "unassessed", "issue": "malha ideal sem rolamento holandês oscilatório"}
    ref = lam_ideal[0]
    known = lag_s is not None or delay_s is not None
    lag = float(lag_s or 0.0)
    dly = float(delay_s) if delay_s is not None else (0.0 if lag_s is not None else TIME_DELAY_LIMITS_S[0])
    dr = dutch_roll_of(augmented_loop(A4, kb, kr, qSb_Izz, b, U, lag, dly), ref)
    lv = dr_level(dr["zeta"], dr["wn"], cat) if dr else 4
    # delay margin (pure delay added to the lag) keeping Level 1
    def lvl(t):
        d = dutch_roll_of(augmented_loop(A4, kb, kr, qSb_Izz, b, U, lag, t), ref)
        return dr_level(d["zeta"], d["wn"], cat) if d else 4
    margin = None
    if lv == 1 or lvl(0.0) == 1:
        lo, hi = 0.0, 1.0
        if lvl(hi) == 1:
            margin = hi
        else:
            for _ in range(40):
                mid = 0.5 * (lo + hi)
                if lvl(mid) == 1:
                    lo = mid
                else:
                    hi = mid
            margin = lo
    stable = bool(np.max(np.linalg.eigvals(augmented_loop(A4, kb, kr, qSb_Izz, b, U, lag, dly)).real) < 0)
    return {"status": "assessed", "lag_s": lag, "delay_s": dly,
            "assumed": None if known else "PRESSUPOSTO: atraso/lag desconhecidos → atraso equivalente puro = limite "
                                          "Nível 1 de MIL-F-8785C 3.5.3 (0,10 s)",
            "dutch_roll": dr, "level": lv, "stable": stable, "delay_margin_level1_s": margin,
            "delay_limits_s": TIME_DELAY_LIMITS_S, "source": TIME_DELAY_SOURCE}


def turbulence_sigma_actuated(A, kb, kr, qSb_Izz, b, U, sigma_v, L_v, lag_s, delay_s) -> dict | None:
    """σ of the actuated ΔC_n (and of its rate) in Dryden lateral turbulence, [β, p, r] + actuator states."""
    from scipy.linalg import solve_continuous_lyapunov
    a = L_v / U
    Ag = np.array([[0.0, 1.0], [-1.0 / a**2, -2.0 / a]])
    Bg = np.array([[0.0], [1.0]])
    Cg = np.array([[1.0 / a**2, math.sqrt(3.0) / a]])
    Pg = solve_continuous_lyapunov(Ag, -Bg @ Bg.T)
    sF = sigma_v / math.sqrt(float((Cg @ Pg @ Cg.T).item()))
    A3 = np.array(A, float)[:3, :3]
    E = -np.array(A, float)[:3, 0]
    Bu = np.array([0.0, 0.0, qSb_Izz])
    Kx = np.array([kb, 0.0, -kr * b / (2 * U)])
    Kg = -kb * sF / U * Cg[0]
    pd = pade2(delay_s)
    nd = 0 if pd is None else 2
    lag = lag_s if lag_s and lag_s > 0 else None
    nl = 1 if lag else 0
    n = 3 + 2 + nd + nl
    M = np.zeros((n, n))
    M[:3, :3] = A3
    M[:3, 3:5] = (E[:, None] * (sF / U)) @ Cg
    M[3:5, 3:5] = Ag
    Kfull = np.concatenate([Kx, Kg])           # u_cmd = Kfull · [x, xg]
    if pd is not None:
        Ad, Bd, Cd, Dd = pd
        M[5:7, 5:7] = Ad
        M[5:7, :5] = Bd @ Kfull[None, :]
        yd = np.zeros(n)
        yd[:5] = Dd * Kfull
        yd[5:7] = Cd[0]
    else:
        yd = np.zeros(n)
        yd[:5] = Kfull
    if nl:
        il = 5 + nd
        M[il, :] += yd / lag
        M[il, il] -= 1.0 / lag
        M[:3, il] += Bu
        cu = np.zeros(n)
        cu[il] = 1.0
        cud = (yd - cu) / lag                       # u̇_act = (y_d − u_act)/τ_a
    else:
        M[:3, :] += np.outer(Bu, yd)
        cu = yd
        cud = cu @ M
    if np.max(np.linalg.eigvals(M).real) >= 0:
        return None
    Bn = np.zeros((n, 1))
    Bn[3:5] = Bg
    P = solve_continuous_lyapunov(M, -Bn @ Bn.T)
    return {"sigma_u": math.sqrt(max(float(cu @ P @ cu), 0.0)), "sigma_udot": math.sqrt(max(float(cud @ P @ cud), 0.0))}


# ------------------------------------------------------------------------------------------- time domain
class SplitActuator:
    """Signed split-aileron deflection s (s > 0: right-side split open). Command ΔC_n → s via ΔC_n = 2C₁ sin²|s|,
    transport delay, first-order lag, rate limit, |s| ≤ δ_max."""

    def __init__(self, C1: float, delta_max_deg: float, rate_max_deg_s: float | None, lag_s: float, delay_s: float,
                 dt: float, bias_deg: float = 0.0):
        self.C1, self.dmax = C1, math.radians(delta_max_deg)
        # symmetric pre-deflection δ0 of both sides; s is then the differential d (right δ0 + d, left δ0 − d, each in
        # [0, δ_max]): ΔC_n = 2C₁[sin²(δ0+d) − sin²(δ0−d)] = 2C₁ sin2δ0 sin2d near d = 0 — linear, so the command
        # rate stays finite through ΔC_n = 0 (Rajput, Zhang & Qu 2014, Appl. Mech. Mater. 643:54; Wang, Wang & Jia
        # 2011, Acta Aeronaut. Astronaut. Sin. 32(8):1392). δ0 = 0 → the previous single-side sin² law.
        self.bias = math.radians(bias_deg or 0.0)
        self.d_lim = self.dmax - self.bias
        self.rate = math.radians(rate_max_deg_s) if rate_max_deg_s else math.inf
        self.lag, self.dt = lag_s, dt
        self.buf = deque([0.0] * max(int(round(delay_s / dt)), 0))
        self.s = 0.0
        self.sat = self.rate_lim = False
        self.peak_rate = 0.0
        self.n_steps = self.n_lim = 0

    @staticmethod
    def s_for(dCn: float, C1: float) -> float:
        x = min(abs(dCn) / (2 * C1), 1.0)
        return math.copysign(math.asin(math.sqrt(x)), dCn)

    def _dcn_biased(self, d: float) -> float:
        r = min(max(self.bias + d, 0.0), self.dmax)
        l_ = min(max(self.bias - d, 0.0), self.dmax)
        return 2 * self.C1 * (math.sin(r) ** 2 - math.sin(l_) ** 2)

    def _d_for_biased(self, dCn: float) -> float:
        """Differential d giving ΔC_n (monotonic on |d| ≤ δ_max − δ0); beyond → ±(δ_max − δ0) + ε (saturation)."""
        lim = self.d_lim
        if abs(dCn) >= abs(self._dcn_biased(lim)):
            return math.copysign(lim * (1 + 1e-9) + 1e-12, dCn)
        lo, hi = (0.0, lim) if dCn >= 0 else (-lim, 0.0)
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            if self._dcn_biased(mid) < dCn:
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi)

    def dCn(self) -> float:
        if self.bias > 0:
            return self._dcn_biased(self.s)
        return math.copysign(2 * self.C1 * math.sin(self.s) ** 2, self.s)

    def step(self, dCn_cmd: float) -> float:
        sc = self._d_for_biased(dCn_cmd) if self.bias > 0 else self.s_for(dCn_cmd, self.C1)
        if self.buf is not None and len(self.buf):
            self.buf.append(sc)
            sc = self.buf.popleft()
        lim_s = self.d_lim if self.bias > 0 else self.dmax
        if abs(sc) > lim_s:
            self.sat = True
            sc = math.copysign(lim_s, sc)
        target = self.s + (sc - self.s) * (1 - math.exp(-self.dt / self.lag)) if self.lag > 0 else sc
        ds = target - self.s
        lim = self.rate * self.dt
        self.n_steps += 1
        if abs(ds) > lim:
            self.rate_lim = True
            self.n_lim += 1
            ds = math.copysign(lim, ds)
        self.peak_rate = max(self.peak_rate, abs(ds) / self.dt)
        self.s += ds
        return self.dCn()


def bank_hold_gains(Lp: float, Lda: float, da_max: float, e_phi_max: float = math.radians(15.0), zeta: float = 0.707):
    """Beard & McLain 2012 Sec. 6.3.1 roll loop: k_pφ = δa_max/e_φ,max·sign(a_φ2), ω_n = √(|a_φ2| δa_max/e_φ,max),
    k_dφ = (2ζω_n − a_φ1)/a_φ2 with a_φ1 = −L_p, a_φ2 = L_δa (PRESSUPOSTO e_φ,max 15°, ζ 0.707)."""
    a1, a2 = -Lp, Lda
    kp = da_max / e_phi_max * math.copysign(1.0, a2)
    wn = math.sqrt(abs(a2) * da_max / e_phi_max)
    kd = (2 * zeta * wn - a1) / a2
    return kp, kd, wn


PITCH_HOLD_SOURCE = ("Beard & McLain 2012 (Small Unmanned Aircraft) Sec. 6.4.1, pitch attitude hold: θ/δe ≈ a_θ3/(s² + "
                     "a_θ1 s + a_θ2), k_pθ = δe_max/e_θ,max·sign(a_θ3), ω_θ = √(a_θ2 + δe_max/e_θ,max |a_θ3|), "
                     "k_dθ = (2ζ_θ ω_θ − a_θ1)/a_θ3; níveis MIL-F-8785C 3.2.1.2 avaliados na malha fechada (como o "
                     "SAS de guinada)")


def pitch_hold_gains(Mq: float, Malpha: float, Mde: float, de_max: float, e_theta_max: float = math.radians(10.0),
                     zeta: float = 0.707):
    """Beard & McLain 2012 Sec. 6.4.1: a_θ1 = −M_q, a_θ2 = −M_α, a_θ3 = M_δe (PRESSUPOSTO e_θ,max 10°, ζ 0,707)."""
    a1, a2, a3 = -Mq, -Malpha, Mde
    kp = de_max / e_theta_max * math.copysign(1.0, a3)
    wn = math.sqrt(max(a2 + de_max / e_theta_max * abs(a3), 0.0))
    kd = (2 * zeta * wn - a1) / a3
    return kp, kd, wn


def pitch_hold_closed_loop(A_lon: np.ndarray, CL: float, K: float, CLde: float, Cmde: float, Cmad: float, qS: float,
                           c: float, m: float, Iyy: float, u0: float, de_max: float,
                           e_theta_max: float = math.radians(10.0)) -> dict:
    """[u, w, q, θ] with δe = −k_pθ θ − k_dθ q (perturbation about trim, θ_c = 0). B_δe: X = −2K C_L C_Lδe q̄S/m
    (induced drag), Z = −C_Lδe q̄S/m, M = C_mδe q̄Sc̄/I_y + M_ẇ Z_δe."""
    A = np.array(A_lon, float)
    Mq = A[2, 2] - (Cmad * (c / (2 * u0)) * qS * c / (Iyy * u0)) * u0
    Mw = A[2, 1]
    Mwd = Cmad * (c / (2 * u0)) * qS * c / (Iyy * u0)
    Malpha = (Mw - Mwd * A[1, 1]) * u0
    Mde_ = Cmde * qS * c / Iyy
    kp, kd, wn = pitch_hold_gains(Mq, Malpha, Mde_, de_max, e_theta_max)
    Zde = -CLde * qS / m
    B = np.array([-2 * K * CL * CLde * qS / m, Zde, Mde_ + Mwd * Zde, 0.0])
    Kfb = np.array([0.0, 0.0, -kd, -kp])
    Acl = A + np.outer(B, Kfb)
    return {"A_cl": Acl, "k_p_theta": kp, "k_d_theta": kd, "wn_theta": wn, "e_theta_max_deg": math.degrees(e_theta_max),
            "de_max_deg": math.degrees(de_max), "source": PITCH_HOLD_SOURCE}


def gust_response(A4: np.ndarray, d: dict, U: float, rho: float, S: float, b: float, m: float, Ixx: float, Izz: float,
                  sas: dict | None, C1: float | None, delta_max_deg: float | None, rate_max_deg_s: float | None,
                  el_max_deg: float, lag_s: float, delay_s: float, vg_peak: float, length_m: float,
                  T: float = 12.0, dt: float = 0.002, bias_deg: float = 0.0) -> dict:
    """1-cos lateral gust on the linear lateral airframe with elevon bank hold and (optional) SAS via the split
    actuator. ``d``: lateral + elevon derivatives (C_Yδa, C_lδa, C_nδa per rad)."""
    A4 = np.array(A4, float)
    qS = 0.5 * rho * U**2 * S
    Ya, La, Na = qS * d["CYda"] / (m * U), qS * b * d["Clda"] / Ixx, qS * b * d["Cnda"] / Izz
    Bda = np.array([Ya, La, Na, 0.0])
    Bdn = np.array([0.0, 0.0, qS * b / Izz, 0.0])
    E = -A4[:, 0].copy()
    E[3] = 0.0
    da_max = math.radians(el_max_deg)
    kp, kd, wn_phi = bank_hold_gains(A4[1, 1], La, da_max)
    act = None
    if sas is not None and C1 is not None and delta_max_deg is not None:
        act = SplitActuator(C1, delta_max_deg, rate_max_deg_s, lag_s, delay_s, dt, bias_deg)
    Tg = length_m / U
    x = np.zeros(4)
    n = int(T / dt)
    rec = {"t": [], "beta_deg": [], "phi_deg": [], "r_deg_s": [], "dCn_cmd": [], "dCn": [], "split_deg": [],
           "elevon_deg": []}
    peak = {"beta_air_deg": 0.0, "phi_deg": 0.0, "dCn_cmd": 0.0, "dCn": 0.0, "split_deg": 0.0, "elevon_deg": 0.0}
    el_sat = False
    dn = 0.0
    da_prev, da_rate_pk = None, 0.0
    for k in range(n):
        t = k * dt
        vg = 0.5 * vg_peak * (1 - math.cos(2 * math.pi * t / Tg)) if t <= Tg else 0.0
        bg = math.atan2(vg, U)
        beta_air = x[0] - bg
        rh = x[2] * b / (2 * U)
        da = -(kp * x[3] + kd * x[1])
        if abs(da) > da_max:
            el_sat = True
            da = math.copysign(da_max, da)
        if da_prev is not None:
            da_rate_pk = max(da_rate_pk, abs(da - da_prev) / dt)
        da_prev = da
        if act is not None:
            u = sas["k_beta"] * beta_air - sas["k_r"] * rh
            peak["dCn_cmd"] = max(peak["dCn_cmd"], abs(u))
            dn = act.step(u)
        xd = A4 @ x + E * bg + Bda * da + Bdn * dn
        x = x + dt * xd
        for kk, v in (("beta_air_deg", math.degrees(beta_air)), ("phi_deg", math.degrees(x[3])), ("dCn", dn),
                      ("split_deg", math.degrees(act.s) if act else 0.0), ("elevon_deg", math.degrees(da))):
            peak[kk] = max(peak[kk], abs(v))
        if k % 10 == 0:
            rec["t"].append(t)
            rec["beta_deg"].append(math.degrees(beta_air))
            rec["phi_deg"].append(math.degrees(x[3]))
            rec["r_deg_s"].append(math.degrees(x[2]))
            rec["dCn_cmd"].append(u if act is not None else 0.0)
            rec["dCn"].append(dn)
            rec["split_deg"].append(math.degrees(act.s) if act else 0.0)
            rec["elevon_deg"].append(math.degrees(da))
    tail = np.abs(np.array(rec["beta_deg"])[int(0.75 * len(rec["t"])):])
    out = {"peak": peak, "final_beta_amp_deg": float(tail.max()) if tail.size else None,
           "bank_hold": {"kp_phi": kp, "kd_phi": kd, "wn_phi": wn_phi, "elevon_saturated": el_sat,
                         "elevon_rate_peak_deg_s": math.degrees(da_rate_pk),
                         "source": "Beard & McLain 2012 Sec. 6.3.1 (PRESSUPOSTO e_φ,max 15°, ζ 0,707)"},
           "gust": {"v_peak_m_s": vg_peak, "length_m": length_m, "duration_s": Tg}, "trace": rec}
    if act is not None:
        out["actuator"] = {"saturated": act.sat, "rate_limited": act.rate_lim, "peak_rate_deg_s": math.degrees(act.peak_rate),
                           "rate_limited_fraction": act.n_lim / max(act.n_steps, 1),
                           "lag_s": lag_s, "delay_s": delay_s}
    return out
