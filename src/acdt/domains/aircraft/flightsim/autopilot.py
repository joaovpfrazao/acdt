"""Classic successive-loop-closure autopilot (Beard & McLain, *Small Unmanned Aircraft*, 2012, Ch. 6 and 10).

Gains come from the transfer-function coefficients of the linearised model at the segment trim point
(Beard & McLain Sec. 5.4), with the *design parameters* below (saturation-based proportional gains, damping
ratios and bandwidth separations — the book's recommended ranges, not aircraft data):

* roll attitude (aileron, PD):  a_φ1 = −½ρV²Sb C_pp b/2V, a_φ2 = ½ρV²Sb C_pδa;
  k_pφ = δa_max/e_φmax·sgn(a_φ2), ω_φ = √(|a_φ2| δa_max/e_φmax), k_dφ = (2ζ_φ ω_φ − a_φ1)/a_φ2  (Eq. 6.7-6.8)
* course (→ φ_c, PI):  ω_χ = ω_φ/W_χ, k_pχ = 2ζ_χ ω_χ V_g/g, k_iχ = ω_χ² V_g/g                    (Eq. 6.12)
* sideslip (rudder, PI):  a_β1 = −ρVS/2m C_Yβ, a_β2 = ρVS/2m C_Yδr                                  (Eq. 6.14-6.15)
* pitch attitude (elevator, PD):  a_θ1 = −ρV²cS/2Iyy C_mq c/2V, a_θ2 = −ρV²cS/2Iyy C_mα, a_θ3 = ρV²cS/2Iyy C_mδe;
  k_pθ = δe_max/e_θmax·sgn(a_θ3), ω_θ = √(a_θ2 + k_pθ a_θ3), k_dθ = (2ζ_θ ω_θ − a_θ1)/a_θ3, K_θDC  (Eq. 6.18-6.21)
* altitude (→ θ_c, PI):  ω_h = ω_θ/W_h, k_ih = ω_h²/(K_θDC V), k_ph = 2ζ_h ω_h/(K_θDC V)             (Eq. 6.24)
* airspeed with pitch (climb/descent, PI):  ω_V2 = ω_θ/W_V2, k_iV2 = −ω_V2²/(K_θDC g),
  k_pV2 = (a_V1 − 2ζ_V2 ω_V2)/(K_θDC g)                                                             (Eq. 6.27)
* airspeed with throttle (PI):  k_pV = (2ζ_V ω_V − a_V1)/a_V2, k_iV = ω_V²/a_V2                    (Eq. 6.30)

a_V1 = (∂D/∂V − ∂T/∂V)/m and a_V2 = (∂T/∂δt)/m are taken by finite differences of the 6-DOF model itself.
Path following: straight line (Eq. 10.8, χ_∞ and k_path) and orbit (Eq. 10.13, k_orbit).
Sign convention: δe > 0 trailing edge down, δa > 0 roll right, δr > 0 trailing edge left (= nose left).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from acdt.core.atmosphere import isa
from .sixdof import Controls, SixDOF

G0 = 9.80665

DESIGN = {  # Beard & McLain (2012) Ch. 6 recommended design choices (bandwidth separation 5-15 etc.)
    "e_phi_max_deg": 30.0, "zeta_phi": 0.9, "W_chi": 8.0, "zeta_chi": 0.9,
    "e_beta_max_deg": 10.0, "zeta_beta": 0.7,
    "e_theta_max_deg": 10.0, "zeta_theta": 0.9, "W_h": 12.0, "zeta_h": 0.9, "W_V2": 10.0, "zeta_V2": 0.9,
    "omega_V_frac": 0.1, "zeta_V": 0.9,           # ω_V = 0.1 ω_θ (PRESSUPOSTO; Beard leaves it free)
    "chi_inf_deg": 60.0, "k_path": 0.01, "k_orbit": 2.0,
    "phi_max_deg": 30.0, "theta_max_deg": 20.0,
    "defl_use": 0.8,                               # fraction of the mechanical limit used by the design
}


def _coeff_derivs(sim: SixDOF, alpha: float, flap: float, de: float, x_cg: float) -> dict:
    """Stability-axis non-dimensional derivatives at the trim α/δe by finite differences of the 6-DOF aero."""
    h = 1e-4

    def C(a=alpha, b=0.0, p=0.0, q=0.0, r=0.0, de_=de, da=0.0, dr=0.0):
        return sim.aero_coeffs(a, b, p, q, r, 0.0, Controls(de=de_, da=da, dr=dr, flap=flap), x_cg)[:6]

    c0 = np.array(C())
    d = {}
    for name, kw in (("a", {"a": alpha + h}), ("b", {"b": h}), ("p", {"p": h}), ("q", {"q": h}), ("r", {"r": h}),
                     ("de", {"de_": de + h}), ("da", {"da": h}), ("dr", {"dr": h})):
        d[name] = (np.array(C(**kw)) - c0) / h
    # index: 0 CL, 1 CD, 2 CY, 3 Cl, 4 Cm, 5 Cn
    return {"CLa": d["a"][0], "CDa": d["a"][1], "Cma": d["a"][4], "Cmq": d["q"][4], "Cmde": d["de"][4],
            "CYb": d["b"][2], "CYdr": d["dr"][2], "Clp": d["p"][3], "Cnp": d["p"][5], "Clda": d["da"][3],
            "Cnda": d["da"][5], "Cldr": d["dr"][3], "Cndr": d["dr"][5], "CL": c0[0], "CD": c0[1]}


def design_gains(sim: SixDOF, tr: dict, flap: float = 0.0, design: dict | None = None) -> dict:
    """Successive-loop-closure gains at the trim ``tr`` (output of :func:`sixdof.trim`)."""
    D = {**DESIGN, **(design or {})}
    fm, a = sim.fm, sim.fm.aero
    V, h = tr["V"], tr["h"]
    rho = isa(h + sim.h_field).rho
    m = sim.mass(tr["x"])
    Ixx, Iyy, Izz, Ixz = fm.mass.Ixx, fm.mass.Iyy, fm.mass.Izz, fm.mass.Ixz
    al, de = math.radians(tr["alpha_deg"]), math.radians(tr["delta_e_deg"])
    cd = _coeff_derivs(sim, al, flap, de, fm.mass.x_cg)
    S, b, c = a.S, a.b, a.c
    lim = {k: math.radians(v) * D["defl_use"] for k, v in a.limits.items()}
    G = Ixx * Izz - Ixz**2
    G3, G4 = Izz / G, Ixz / G
    Cpp = G3 * cd["Clp"] + G4 * cd["Cnp"]
    Cpda = G3 * cd["Clda"] + G4 * cd["Cnda"]
    qS = 0.5 * rho * V**2 * S
    a_phi1 = -qS * b * Cpp * b / (2 * V)
    a_phi2 = qS * b * Cpda
    e_phi = math.radians(D["e_phi_max_deg"])
    kp_phi = lim["aileron"] / e_phi * math.copysign(1.0, a_phi2)
    w_phi = math.sqrt(abs(a_phi2) * lim["aileron"] / e_phi)
    kd_phi = (2 * D["zeta_phi"] * w_phi - a_phi1) / a_phi2
    w_chi = w_phi / D["W_chi"]
    kp_chi = 2 * D["zeta_chi"] * w_chi * V / G0
    ki_chi = w_chi**2 * V / G0
    a_b1 = -rho * V * S / (2 * m) * cd["CYb"]
    a_b2 = rho * V * S / (2 * m) * cd["CYdr"]
    if abs(a_b2) > 1e-9:
        kp_b = lim["rudder"] / math.radians(D["e_beta_max_deg"]) * math.copysign(1.0, a_b2)
        ki_b = ((a_b1 + a_b2 * kp_b) / (2 * D["zeta_beta"]))**2 / a_b2
    else:
        kp_b = ki_b = 0.0
    k = rho * V**2 * c * S / (2 * Iyy)
    a_t1 = -k * cd["Cmq"] * c / (2 * V)
    a_t2 = -k * cd["Cma"]
    a_t3 = k * cd["Cmde"]
    kp_t = lim["elevator"] / math.radians(D["e_theta_max_deg"]) * math.copysign(1.0, a_t3)
    w_t = math.sqrt(max(a_t2 + kp_t * a_t3, 1e-6))
    kd_t = (2 * D["zeta_theta"] * w_t - a_t1) / a_t3
    K_dc = kp_t * a_t3 / (a_t2 + kp_t * a_t3)
    w_h = w_t / D["W_h"]
    ki_h = w_h**2 / (K_dc * V)
    kp_h = 2 * D["zeta_h"] * w_h / (K_dc * V)
    # a_V1, a_V2 from the model: D(V) and T(V, δt)
    th = tr["throttle"]
    def drag(Vx):
        return 0.5 * rho * Vx**2 * S * (a.CD0 + a.flap_drag(flap) + a.K * (2 * m * G0 / (rho * Vx**2 * S))**2)
    T0, _ = fm.prop.thrust(V, h + sim.h_field, th)
    T1, _ = fm.prop.thrust(V + 0.5, h + sim.h_field, th)
    dTdV = (T1 - T0) / 0.5
    Tmax, _ = fm.prop.thrust(V, h + sim.h_field, 1.0)
    Tmin, _ = fm.prop.thrust(V, h + sim.h_field, 0.0)
    a_V1 = ((drag(V + 0.5) - drag(V)) / 0.5 - dTdV) / m
    a_V2 = max((Tmax - Tmin) / m, 1e-6)
    w_V2 = w_t / D["W_V2"]
    ki_V2 = -w_V2**2 / (K_dc * G0)
    kp_V2 = (a_V1 - 2 * D["zeta_V2"] * w_V2) / (K_dc * G0)
    w_V = D["omega_V_frac"] * w_t
    kp_V = (2 * D["zeta_V"] * w_V - a_V1) / a_V2
    ki_V = w_V**2 / a_V2
    return {"kp_phi": kp_phi, "kd_phi": kd_phi, "w_phi": w_phi, "kp_chi": kp_chi, "ki_chi": ki_chi,
            "kp_beta": kp_b, "ki_beta": ki_b, "kp_theta": kp_t, "kd_theta": kd_t, "w_theta": w_t, "K_theta_DC": K_dc,
            "kp_h": kp_h, "ki_h": ki_h, "kp_V2": kp_V2, "ki_V2": ki_V2, "kp_V": kp_V, "ki_V": ki_V,
            "a": {"phi1": a_phi1, "phi2": a_phi2, "theta1": a_t1, "theta2": a_t2, "theta3": a_t3, "V1": a_V1,
                  "V2": a_V2, "beta1": a_b1, "beta2": a_b2},
            "trim": {"de": de, "throttle": th, "theta": al + math.radians(tr.get("gamma_deg", 0.0)), "alpha": al},
            "V": V, "h": h, "flap": flap, "design": D, "derivs": cd,
            "source": "Beard & McLain (2012) Ch. 6, successive loop closure"}


def wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


@dataclass
class PI:
    kp: float
    ki: float
    lo: float
    hi: float
    i: float = 0.0

    def __call__(self, e: float, dt: float, ff: float = 0.0) -> float:
        u_unsat = ff + self.kp * e + self.ki * (self.i + e * dt)
        u = min(max(u_unsat, self.lo), self.hi)
        if u == u_unsat or (u_unsat > self.hi and e * self.ki < 0) or (u_unsat < self.lo and e * self.ki > 0):
            self.i += e * dt  # conditional integration (anti-windup, Beard & McLain Sec. 6.5)
        return u


@dataclass
class Autopilot:
    """Inner loops + mode logic. ``command(...)`` returns :class:`Controls` from the measured state."""
    sim: SixDOF
    gains: dict
    flap: float = 0.0
    loops: dict = field(default_factory=dict)

    def __post_init__(self):
        self.reset_loops()
        self.split = None
        ys = getattr(self.sim.fm.aero, "yaw_sas", None) or {}
        if ys:   # tailless drag rudder: yaw SAS + washout through the split-aileron actuator (state kept on retune)
            from ..assembly.tailless_actuation import SplitActuator
            self.split = SplitActuator(ys["C1"], ys["delta_max_deg"], ys.get("rate_max_deg_s"), ys.get("lag_s", 0.0),
                                       ys.get("delay_s", 0.0), ys["dt"], bias_deg=ys.get("bias_deg", 0.0))
            self.r_lp = 0.0   # low-pass state of the washout τs/(τs + 1)
            self.yaw_log = {"n": 0, "n_sat": 0, "peak_dCn": 0.0, "peak_split_deg": 0.0}

    def yaw(self, m: dict, dt: float, psi_c: float | None = None) -> float:
        """Yaw channel. Conventional: rudder sideslip PI (Beard & McLain Eq. 6.14–6.15). Drag rudder (tailless):
        ΔC_n,c = k_β β − k_r r̂_wo (+ heading PD for the decrab: k_ψ (ψ_c − ψ) − k_dψ r̂, PRESSUPOSTO, same
        saturation-based form as Beard & McLain Eq. 6.7–6.8 on the yaw axis) → split actuator (delay, lag, rate,
        sin² law). Washout r_wo = r − r_lp (MIT 16.333 Lecture 12, How 2004: H_w = τs/(τs + 1), τ 4,2 s)."""
        if self.split is None:
            return self.loops["beta"](-m["beta"], dt)
        ys = self.sim.fm.aero.yaw_sas
        a = self.sim.fm.aero
        tau = float(ys.get("washout_s", 4.2))
        self.r_lp += dt / tau * (m["r"] - self.r_lp)
        Va = max(m["Va"], 1.0)
        rhat = (m["r"] - self.r_lp) * a.b / (2 * Va)
        u = ys["k_beta"] * m["beta"] - ys["k_r"] * rhat
        if psi_c is not None and ys.get("k_psi") is not None:
            e_psi = wrap(psi_c - m["psi"])
            cap_ = math.radians(self.sim.fm.aero.limits["rudder"])
            if ys.get("k_ipsi"):   # integral with clamping anti-windup (Beard & McLain 2012 Sec. 6.5)
                self.psi_i = getattr(self, "psi_i", 0.0) + e_psi * dt
                self.psi_i = max(-cap_ / ys["k_ipsi"], min(cap_ / ys["k_ipsi"], self.psi_i))
                u += ys["k_ipsi"] * self.psi_i
            u += ys["k_psi"] * e_psi - ys["k_dpsi"] * m["r"]
            if ys.get("beta_feedforward", True) and m.get("alpha") is not None:
                # cancel the weathercock moment C_nβ(α)·β of the model's own table so the heading loop has no
                # steady error while the nose is held off the wind (model-based feed-forward, PRESSUPOSTO)
                from .sixdof import IDX
                u -= float(self.sim._tab(m["alpha"], self.flap)[IDX["Cnb"]]) * m["beta"]
        dn = self.split.step(u)
        L = self.yaw_log
        L["n"] += 1
        cap = math.radians(a.limits["rudder"])
        L["n_sat"] += int(abs(u) >= cap)
        L["peak_dCn"] = max(L["peak_dCn"], abs(dn))
        L["peak_split_deg"] = max(L["peak_split_deg"], abs(math.degrees(self.split.s)) + ys.get("bias_deg", 0.0))
        return dn

    def reset_loops(self, keep: dict | None = None):
        g, a = self.gains, self.sim.fm.aero
        D = g["design"]
        th_max = math.radians(D["theta_max_deg"])
        phi_max = math.radians(D["phi_max_deg"])
        old = self.loops
        self.loops = {
            "chi": PI(g["kp_chi"], g["ki_chi"], -phi_max, phi_max),
            "beta": PI(g["kp_beta"], g["ki_beta"], -math.radians(a.limits["rudder"]), math.radians(a.limits["rudder"])),
            "h": PI(g["kp_h"], g["ki_h"], -th_max, th_max),
            "V2": PI(g["kp_V2"], g["ki_V2"], -th_max, th_max),
            "V": PI(g["kp_V"], g["ki_V"], 0.0, 1.0),
        }
        if keep:  # bumpless transfer: carry the integrator states that produce the same output
            for k, v in keep.items():
                if k in self.loops:
                    self.loops[k].i = v

    def retune(self, gains: dict, theta_now: float, throttle_now: float):
        """Gain scheduling at a new trim point with bumpless integrators."""
        self.gains = gains
        self.reset_loops()
        self.loops["h"].i = theta_now / gains["ki_h"] if gains["ki_h"] else 0.0
        self.loops["V2"].i = theta_now / gains["ki_V2"] if gains["ki_V2"] else 0.0
        self.loops["V"].i = throttle_now / gains["ki_V"] if gains["ki_V"] else 0.0

    alpha: float | None = None  # measured α, set by the mission loop for the α-limiter

    def alpha_protect(self) -> float:
        """α limit: 90 % of the blended-lift stall angle for the current flap (envelope protection)."""
        return 0.9 * self.sim.fm.aero.alpha_stall(round(self.flap, 2))[0]

    def pitch(self, theta_c: float, theta: float, q: float) -> float:
        g = self.gains
        lim = math.radians(self.sim.fm.aero.limits["elevator"])
        if self.alpha is not None:  # α-limiter: lower the attitude command by the α excess
            ex = self.alpha - self.alpha_protect()
            if ex > 0:
                theta_c = min(theta_c, theta - 2.0 * ex)
        de = g["trim"]["de"] + g["kp_theta"] * (theta_c - theta) - g["kd_theta"] * q
        return min(max(de, -lim), lim)

    def roll(self, phi_c: float, phi: float, p: float) -> float:
        g = self.gains
        lim = math.radians(self.sim.fm.aero.limits["aileron"])
        da = g["kp_phi"] * (phi_c - phi) - g["kd_phi"] * p
        return min(max(da, -lim), lim)


def line_course(p_ne, r_ne, q_hat, chi, D=DESIGN) -> tuple[float, float]:
    """Straight-line path following (Beard & McLain Eq. 10.8). Returns (χ_c, cross-track error e_py)."""
    chi_q = math.atan2(q_hat[1], q_hat[0])
    while chi_q - chi < -math.pi:
        chi_q += 2 * math.pi
    while chi_q - chi > math.pi:
        chi_q -= 2 * math.pi
    e_py = -math.sin(chi_q) * (p_ne[0] - r_ne[0]) + math.cos(chi_q) * (p_ne[1] - r_ne[1])
    chi_c = chi_q - math.radians(D["chi_inf_deg"]) * 2 / math.pi * math.atan(D["k_path"] * e_py)
    return chi_c, e_py


def orbit_course(p_ne, c_ne, rho, lam, chi, D=DESIGN) -> tuple[float, float]:
    """Orbit following (Beard & McLain Eq. 10.13); λ = +1 clockwise. Returns (χ_c, radial error)."""
    d = math.hypot(p_ne[0] - c_ne[0], p_ne[1] - c_ne[1])
    vp = math.atan2(p_ne[1] - c_ne[1], p_ne[0] - c_ne[0])
    while vp - chi < -math.pi:
        vp += 2 * math.pi
    while vp - chi > math.pi:
        vp -= 2 * math.pi
    chi_c = vp + lam * (math.pi / 2 + math.atan(D["k_orbit"] * (d - rho) / rho))
    return chi_c, d - rho
