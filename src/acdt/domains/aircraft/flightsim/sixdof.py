"""Simulador 6-DOF próprio (terra plana, corpo rígido, quaterniões) — fallback do JSBSim.

Equações de Stevens, Lewis & Johnson (2016) *Aircraft Control and Simulation* 3rd ed., Sec. 1.7 (flat-Earth,
body axes, quaternion kinematics Eq. 1.8-15) e Beard & McLain (2012) Cap. 3–4 (forças aerodinâmicas em eixos de
estabilidade: f_x = −C_D cosα + C_L sinα, f_z = −C_D sinα − C_L cosα, Eq. 4.18-4.19), estendidas a β ≠ 0 com a
rotação vento → corpo (C_D, C_Y, C_L em eixos do vento, como o JSBSim — 11 nov 2026). Integração RK4 de passo
fixo; a norma do quaternião é reposta a cada passo.

Estado (14): [p_N, p_E, p_D, u, v, w, e0, e1, e2, e3, p, q, r, consumo] — consumo = combustível [kg] ou energia de
bateria [J] gastos. Comandos: δe, δa, δr [rad], manete [0–1], flap [deg], travão [0–1].

Solo (modelo de rodas tipo JSBSim, mola-amortecedor por ponto de contacto): k por roda tal que a deflexão
estática total seja ``static_deflection_m`` (PRESSUPOSTO 0.07 m), amortecimento ζ = 0.7, atrito de rolamento
μ = 0.04 (Raymer Table 17.1, betão), travagem μ = 0.4, atrito lateral μ = 0.8 saturado; roda de nariz/cauda
orientável com o leme (±``steer_max_deg``). Trem 'none': patins na fuselagem (μ 0.3, PRESSUPOSTO) para aterragem
de barriga / recuperação. Efeito de solo ignorado."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from acdt import G0
from acdt.core.atmosphere import isa

from .aeromodel import TABLE_KEYS, FlightModel

IDX = {k: i for i, k in enumerate(TABLE_KEYS)}


# ------------------------------------------------------------------ rotations
def quat_from_euler(phi: float, theta: float, psi: float) -> np.ndarray:
    cph, sph = math.cos(phi / 2), math.sin(phi / 2)
    cth, sth = math.cos(theta / 2), math.sin(theta / 2)
    cps, sps = math.cos(psi / 2), math.sin(psi / 2)
    return np.array([cps * cth * cph + sps * sth * sph, cps * cth * sph - sps * sth * cph,
                     cps * sth * cph + sps * cth * sph, sps * cth * cph - cps * sth * sph])


def euler_from_quat(e) -> tuple[float, float, float]:
    e0, e1, e2, e3 = e
    phi = math.atan2(2 * (e0 * e1 + e2 * e3), e0**2 + e3**2 - e1**2 - e2**2)
    theta = math.asin(max(-1.0, min(1.0, 2 * (e0 * e2 - e1 * e3))))
    psi = math.atan2(2 * (e0 * e3 + e1 * e2), e0**2 + e1**2 - e2**2 - e3**2)
    return phi, theta, psi


def dcm_body_to_ned(e) -> np.ndarray:
    e0, e1, e2, e3 = e
    return np.array([[e1**2 + e0**2 - e2**2 - e3**2, 2 * (e1 * e2 - e3 * e0), 2 * (e1 * e3 + e2 * e0)],
                     [2 * (e1 * e2 + e3 * e0), e2**2 + e0**2 - e1**2 - e3**2, 2 * (e2 * e3 - e1 * e0)],
                     [2 * (e1 * e3 - e2 * e0), 2 * (e2 * e3 + e1 * e0), e3**2 + e0**2 - e1**2 - e2**2]])


@dataclass
class Controls:
    de: float = 0.0
    da: float = 0.0
    dr: float = 0.0
    throttle: float = 0.0
    flap: float = 0.0
    brake: float = 0.0


@dataclass
class GroundModel:
    contacts: list            # [(name, r_body (3,), k, c, steerable, mu_roll or None)]
    mu_roll: float = 0.04
    mu_brake: float = 0.4
    mu_side: float = 0.8
    steer_max_deg: float = 20.0
    v_eps: float = 0.5        # friction saturation speed [m/s]
    h_cg: float = 1.0         # CG height above the ground at static contact [m]
    steer_ref: float = 0.5    # |δr| [rad] that gives full nose-wheel steering
    steer_sign: float = -1.0  # conventional rudder: δr > 0 = nose left; drag rudder (ΔC_n > 0 = nose right): +1

    @classmethod
    def from_model(cls, fm: FlightModel, static_deflection_m: float = 0.07, zeta: float = 0.7) -> "GroundModel":
        g = fm.mass.gear
        m, xcg = fm.mass.m, fm.mass.x_cg
        h, tr = g.get("h_cg", 1.0), g.get("track", 2.0)
        kind = g.get("kind", "tricycle")
        W = m * G0
        if kind in ("tricycle", "taildragger") and g.get("x_main") is not None:
            xm = g["x_main"]
            if kind == "tricycle":
                xo = g.get("x_nose") if g.get("x_nose") is not None else xcg - 2.5 * (xm - xcg)
            else:
                xo = xcg + 4.0 * (xcg - xm)  # tail wheel (PRESSUPOSTO se a estação não for dada)
            share_other = (xm - xcg) / (xm - xo)
            pts = [("main_L", xm, -tr / 2, (1 - share_other) / 2, False), ("main_R", xm, tr / 2, (1 - share_other) / 2, False),
                   ("nose" if kind == "tricycle" else "tail", xo, 0.0, share_other, True)]
            mu_roll = 0.04
        else:  # belly skids on the fuselage bottom (CG on the fuselage axis, PRESSUPOSTO)
            if g.get("fuselage_diameter"):
                h = 0.5 * g["fuselage_diameter"]
            L = 0.3 * fm.aero.b
            pts = [("skid_F", xcg - 0.3 * L, 0.0, 0.5, True), ("skid_L", xcg + 0.2 * L, -0.2 * L, 0.25, False),
                   ("skid_R", xcg + 0.2 * L, 0.2 * L, 0.25, False)]
            mu_roll = 0.3
        contacts = []
        ext = float(g.get("nose_extension_m") or 0.0)   # nose-up stance: the nose contact sits lower (body z down)
        for name, x, y, share, steer in pts:
            k = share * W / static_deflection_m
            c = 2 * zeta * math.sqrt(k * share * m)
            contacts.append((name, np.array([-(x - xcg), y, h + (ext if name == "nose" else 0.0)]), k, c, steer, None))
        # tail-strike bumper at the fuselage end, 0.25 D below the axis (PRESSUPOSTO), stiff, μ 0.5
        if g.get("fuselage_length") and kind != "taildragger":
            d = g.get("fuselage_diameter", 1.0)
            k = W / 0.02
            contacts.append(("tail_strike", np.array([-(g["fuselage_length"] - xcg), 0.0, 0.25 * d]), k,
                             2 * zeta * math.sqrt(k * m), False, 0.5))
        # stiff bumpers (e.g. flying-wing tips, ``gear['bumpers']``: name, r_body relative to the CG, x fwd, z down)
        # Numerical choice (PRESSUPOSTO): the bumper only detects a strike; its stiffness is capped so that the
        # contact frequency on the effective mass m_eff = 1/(1/m + y²/I_x + x²/I_y) stays ≤ 25 rad/s (explicit RK4
        # at the mission step), damping ratio 0.7 on m_eff.
        for bp in g.get("bumpers") or []:
            rb = np.asarray(bp["r_body"], float)
            m_eff = 1.0 / (1.0 / m + rb[1] ** 2 / max(fm.mass.Ixx, 1e-9) + rb[0] ** 2 / max(fm.mass.Iyy, 1e-9))
            k = min(W / 0.02, m_eff * 25.0 ** 2)
            contacts.append((bp["name"], rb, k, 2 * zeta * math.sqrt(k * m_eff), False, 0.5))
        gm = cls(contacts=contacts, mu_roll=mu_roll, h_cg=h)
        if getattr(fm.aero, "yaw_drag_per_Cn", 0.0) and fm.aero.limits.get("rudder"):
            gm.steer_ref, gm.steer_sign = math.radians(fm.aero.limits["rudder"]), 1.0
        return gm


def friction_sensitivity(td: dict, *, mu_side_nom: float = 0.8, v_eps: float = 0.5,
                         mu_side=(0.6, 0.8, 1.0), mu_brake_nom: float = 0.4,
                         mu_brake=(0.30, 0.40, 0.50)) -> dict:
    """First-order sensitivity of recorded touchdown side loads to the 6-DOF friction model.

    The ground model is f_y = −μ_side N tanh(v_y / v_ε). At the *recorded* drift and peak
    vertical load (frozen kinematics — not a 6-DOF re-run) the side force, and so the
    14 CFR 23.485 ratios, scale with μ_side. The μ_side band around the model default 0.8
    is PRESSUPOSTO (no cited side-friction envelope in this model). μ_brake follows Raymer
    2018 Table 17.1 (typical dry ~0.4; 0.3–0.5 is the neighbourhood used here) and is
    reported only as context for braking (no frozen-state side-load effect).
    """
    import math
    W = td.get("W_N")
    drift = td.get("drift_m_s")
    ib = td.get("inboard_ratio")
    ob = td.get("outboard_ratio")
    if W is None or ib is None or ob is None:
        return {"status": "unassessed", "issue": "relatório de toque sem W ou rácios 23.485"}
    tanh = math.tanh(float(drift or 0.0) / v_eps) if v_eps else 1.0
    rows = []
    for mu in mu_side:
        s = mu / mu_side_nom if mu_side_nom else float("nan")
        rows.append({"mu_side": mu, "scale": s, "inboard_ratio": ib * s, "outboard_ratio": ob * s,
                     "side_load_ok": bool(ib * s <= 1.0 and ob * s <= 1.0)})
    return {
        "status": "assessed",
        "method": "primeira ordem, cinemática congelada: f_y ∝ μ_side (tanh(v_y/v_ε) e N do toque registado)",
        "mu_side_nominal": mu_side_nom, "v_eps_m_s": v_eps, "drift_m_s": drift, "tanh": tanh,
        "mu_side_band_note": "banda em torno de 0,8 PRESSUPOSTO (o modelo não cita um envelope de μ lateral)",
        "mu_brake": {"nominal": mu_brake_nom, "range": list(mu_brake),
                     "source": "Raymer 2018 Table 17.1 (seca típica ~0,4; vizinhança 0,3–0,5)"},
        "cases": rows,
        "any_exceeds_23_485": any(not r["side_load_ok"] for r in rows),
    }

@dataclass
class SixDOF:
    fm: FlightModel
    ground: GroundModel | None = None
    wind: object = None                     # callable(t, pos_ned) -> (3,) NED wind [m/s]
    h_field: float = 0.0                    # runway elevation [m]
    _cache: dict = field(default_factory=dict)

    def __post_init__(self):
        a = self.fm.aero
        self.T = np.array([np.asarray(a.tables[k], dtype=float) for k in TABLE_KEYS])  # (nk, nf, na)
        self.al = np.radians(np.asarray(a.alpha_deg, dtype=float))
        self.fl = np.asarray(a.flap_deg, dtype=float)
        if self.ground is None:
            self.ground = GroundModel.from_model(self.fm)

    # -------------------------------------------------------------- aero tables (vectorised)
    def _tab(self, alpha: float, flap: float) -> np.ndarray:
        key = round(flap, 2)
        F = self._cache.get(key)
        if F is None:
            f = self.fl
            if len(f) == 1:
                F = self.T[:, 0, :]
            else:
                fc = min(max(flap, f[0]), f[-1])
                i = min(int(np.searchsorted(f, fc, side="right")) - 1, len(f) - 2)
                w = (fc - f[i]) / (f[i + 1] - f[i])
                F = (1 - w) * self.T[:, i, :] + w * self.T[:, i + 1, :]
            self._cache[key] = F
        al = self.al
        if alpha <= al[0]:
            i, w = 0, (alpha - al[0]) / (al[1] - al[0])
        elif alpha >= al[-1]:
            i, w = len(al) - 2, 1 + (alpha - al[-1]) / (al[-1] - al[-2])
        else:
            i = int(np.searchsorted(al, alpha, side="right")) - 1
            w = (alpha - al[i]) / (al[i + 1] - al[i])
        return (1 - w) * F[:, i] + w * F[:, i + 1]

    def aero_coeffs(self, alpha, beta, ph, qh, rh, adh, c: Controls, x_cg):
        a = self.fm.aero
        t = self._tab(alpha, c.flap)
        g = lambda k: t[IDX[k]]  # noqa: E731
        CL_lin = g("CL") + g("CLq") * qh + a.CLad * adh + g("CLde") * c.de
        s = a.sigma(alpha, round(c.flap, 2))
        sa = math.sin(alpha)
        CL = (1 - s) * CL_lin + s * 2 * sa * abs(sa) * math.cos(alpha)
        CD = (1 - s) * (a.CD0 + a.flap_drag(c.flap) + a.K * CL_lin**2) + s * (a.CD0 + 2 * abs(sa) ** 3)
        if a.yaw_drag_per_Cn:  # drag rudder (tailless split ailerons): ΔC_D = k |ΔC_n|
            CD += a.yaw_drag_per_Cn * abs(g("Cndr") * c.dr)
        CY = g("CYb") * beta + g("CYp") * ph + g("CYr") * rh + g("CYda") * c.da + g("CYdr") * c.dr
        k = (x_cg - a.x_ref) / a.c - a.dx_fus
        Cm = g("Cm") + g("Cmq") * qh + a.Cmad * adh + g("Cmde") * c.de + (CL * math.cos(alpha) + CD * sa) * k
        Cl = g("Clb") * beta + g("Clp") * ph + g("Clr") * rh + g("Clda") * c.da + g("Cldr") * c.dr
        Cn = g("Cnb") * beta + g("Cnp") * ph + g("Cnr") * rh + g("Cnda") * c.da + g("Cndr") * c.dr \
            + CY * (x_cg - a.x_ref) / a.b
        return CL, CD, CY, Cl, Cm, Cn, s

    # -------------------------------------------------------------- dynamics
    def mass(self, x) -> float:
        fm = self.fm
        return fm.mass.m - (x[13] if fm.prop.kind != "electric" else 0.0)

    def derivatives(self, t: float, x: np.ndarray, c: Controls, out: dict | None = None) -> np.ndarray:
        fm, a = self.fm, self.fm.aero
        m = self.mass(x)
        Ixx, Iyy, Izz, Ixz = fm.mass.Ixx, fm.mass.Iyy, fm.mass.Izz, fm.mass.Ixz
        pos, vb, e, w = x[0:3], x[3:6], x[6:10], x[10:13]
        R = dcm_body_to_ned(e)
        h = -pos[2]
        atm = isa(max(h, 0.0) + self.h_field)
        wind = np.zeros(3) if self.wind is None else np.asarray(self.wind(t, pos), dtype=float)
        vr = vb - R.T @ wind
        ur, vv, wr = vr
        Va = max(float(np.linalg.norm(vr)), 1e-3)
        alpha = math.atan2(wr, ur)
        beta = math.asin(max(-1.0, min(1.0, vv / Va)))
        p, q, r = w
        ca, sa = math.cos(alpha), math.sin(alpha)
        ps, rs = p * ca + r * sa, -p * sa + r * ca
        qbar = 0.5 * atm.rho * Va**2
        S, b, cb = a.S, a.b, a.c
        T, flow = fm.prop.thrust(Va, h + self.h_field, c.throttle)
        if fm.prop.kind == "electric" and x[13] >= fm.mass.battery_J > 0:
            T, flow = 0.0, 0.0
        if fm.prop.kind != "electric" and x[13] >= fm.mass.fuel_kg > 0:
            T, flow = 0.0, 0.0
        grav = R.T @ np.array([0.0, 0.0, m * G0])
        x_cg = fm.mass.x_cg
        Fg, Mg, gear_load = self._ground(x, R, c)

        def forces(adh):
            CL, CD, CY, Cl, Cm, Cn, s = self.aero_coeffs(alpha, beta, ps * b / (2 * Va), q * cb / (2 * Va),
                                                         rs * b / (2 * Va), adh, c, x_cg)
            # wind axes → body (11 nov 2026): C_D, C_Y, C_L in wind axes as in JSBSim (Reference Manual, "Frames of
            # reference": wind frame rotated by −β about z_W then by α about y_A; DRAG/SIDE/LIFT are wind axes),
            # so the drag has a body side component −D sinβ. At β = 0 this is the stability-axis form of Beard &
            # McLain Eq. 4.18-4.19. It matters when C_Yβ is small next to C_D (flying wing without fins).
            cb_, sb_ = math.cos(beta), math.sin(beta)
            Fa = qbar * S * np.array([-CD * ca * cb_ - CY * ca * sb_ + CL * sa,
                                      -CD * sb_ + CY * cb_,
                                      -CD * sa * cb_ - CY * sa * sb_ - CL * ca])
            Clb, Cnb = Cl * ca - Cn * sa, Cl * sa + Cn * ca
            Ma = qbar * S * np.array([b * Clb, cb * Cm, b * Cnb])
            F = Fa + grav + np.array([T, 0.0, 0.0]) + Fg
            M = Ma + np.array([0.0, fm.prop.z_thrust * T, 0.0]) + Mg
            return F, M, (CL, CD, CY, Cl, Cm, Cn, s)

        F, M, co = forces(0.0)
        vdot = F / m - np.cross(w, vb)
        if a.CLad or a.Cmad:  # α̇ from the first pass (Stevens & Lewis Sec. 3.4 handle α̇ the same way)
            udot_r, wdot_r = vdot[0], vdot[2]
            adot = (ur * wdot_r - wr * udot_r) / max(ur**2 + wr**2, 1e-6)
            F, M, co = forces(adot * cb / (2 * Va))
            vdot = F / m - np.cross(w, vb)
        G = Ixx * Izz - Ixz**2
        L_, M_, N_ = M
        pdot = (Izz * L_ + Ixz * N_ - (Ixz * (Iyy - Ixx - Izz) * p + (Ixz**2 + Izz * (Izz - Iyy)) * r) * q) / G
        qdot = (M_ - (Ixx - Izz) * p * r - Ixz * (p**2 - r**2)) / Iyy
        rdot = (Ixz * L_ + Ixx * N_ + (Ixz * (Iyy - Ixx - Izz) * r + (Ixz**2 + Ixx * (Ixx - Iyy)) * p) * q) / G
        e0, e1, e2, e3 = e
        lam = 1.0 - (e0**2 + e1**2 + e2**2 + e3**2)
        k = 1.0
        edot = 0.5 * np.array([-p * e1 - q * e2 - r * e3, p * e0 + r * e2 - q * e3,
                               q * e0 - r * e1 + p * e3, r * e0 + q * e1 - p * e2]) + k * lam * e
        xdot = np.empty(14)
        xdot[0:3] = R @ vb
        xdot[3:6] = vdot
        xdot[6:10] = edot
        xdot[10:13] = (pdot, qdot, rdot)
        xdot[13] = flow
        if out is not None:
            CL, CD, CY, Cl, Cm, Cn, s = co
            out.update({"Va": Va, "alpha": alpha, "beta": beta, "qbar": qbar, "T": T, "flow": flow, "CL": CL, "CD": CD,
                        "CY": CY, "sigma": s, "n_z": -(F[2] - grav[2]) / (m * G0), "n_y": (F[1] - grav[1]) / (m * G0),
                        "gear_load": gear_load, "contacts": dict(self.contact_loads), "rho": atm.rho, "wind": wind, "m": m})
        return xdot

    def _ground(self, x, R, c: Controls):
        Fg, Mg = np.zeros(3), np.zeros(3)
        gl = 0.0
        pos, vb, w = x[0:3], x[3:6], x[10:13]
        self.contact_loads = {}
        self.contact_side = {}
        if -pos[2] > 30.0 or self.ground is None:  # far above the runway
            return Fg, Mg, gl
        gm = self.ground
        loads = {}
        side = {}
        for name, rb, k, cdamp, steer, mu_c in gm.contacts:
            pc = pos + R @ rb
            pen = pc[2]  # NED down: ground at 0
            if pen <= 0:
                continue
            vc_b = vb + np.cross(w, rb)
            vc = R @ vc_b
            N = max(k * pen + cdamp * vc[2], 0.0)
            gl += N
            loads[name] = N
            # wheel frame: heading of the body x-axis projected on the ground (+ steering)
            psi = math.atan2(R[1, 0], R[0, 0])
            if steer:
                psi += max(-1.0, min(1.0, c.dr / gm.steer_ref)) * math.radians(gm.steer_max_deg) * gm.steer_sign
            ex, ey = np.array([math.cos(psi), math.sin(psi), 0.0]), np.array([-math.sin(psi), math.cos(psi), 0.0])
            vx, vy = vc @ ex, vc @ ey
            mu_x = mu_c if mu_c is not None else gm.mu_roll + (gm.mu_brake - gm.mu_roll) * c.brake * (0 if steer else 1)
            fx = -mu_x * N * math.tanh(vx / gm.v_eps)
            fy = -gm.mu_side * N * math.tanh(vy / gm.v_eps)
            side[name] = fy
            Fn = fx * ex + fy * ey + np.array([0.0, 0.0, -N])
            Fb = R.T @ Fn
            Fg += Fb
            Mg += np.cross(rb, Fb)
        self.contact_loads = loads
        self.contact_side = side
        return Fg, Mg, gl

    def step(self, t, x, c: Controls, dt: float) -> np.ndarray:
        k1 = self.derivatives(t, x, c)
        k2 = self.derivatives(t + dt / 2, x + dt / 2 * k1, c)
        k3 = self.derivatives(t + dt / 2, x + dt / 2 * k2, c)
        k4 = self.derivatives(t + dt, x + dt * k3, c)
        xn = x + dt / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
        xn[6:10] /= np.linalg.norm(xn[6:10])
        return xn


# ------------------------------------------------------------------ initial state, trim, linearisation
def state(pos_ned=(0.0, 0.0, 0.0), V=0.0, alpha=0.0, beta=0.0, phi=0.0, theta=0.0, psi=0.0, pqr=(0.0, 0.0, 0.0),
          used=0.0) -> np.ndarray:
    x = np.zeros(14)
    x[0:3] = pos_ned
    x[3:6] = V * np.array([math.cos(alpha) * math.cos(beta), math.sin(beta), math.sin(alpha) * math.cos(beta)])
    x[6:10] = quat_from_euler(phi, theta, psi)
    x[10:13] = pqr
    x[13] = used
    return x


def trim(sim: SixDOF, V: float, h: float, gamma: float = 0.0, flap: float = 0.0, psi: float = 0.0) -> dict:
    """Wings-level steady trim: solve (α, δe, manete) so that u̇ = ẇ = q̇ = 0 at air speed V and flight-path γ
    (Stevens & Lewis Sec. 3.6). Returns the state, controls and residuals."""
    from scipy.optimize import least_squares

    def make(z):
        al, de, th = z
        x = state((0.0, 0.0, -h), V, al, 0.0, 0.0, al + gamma, psi)
        return x, Controls(de=de, throttle=th, flap=flap)

    def res(z):
        x, c = make(z)
        d = sim.derivatives(0.0, x, c)
        return [d[3] / G0, d[5] / G0, d[11]]

    # coarse (α, δe) grid on the normal-force and pitch residuals, then Newton-type refinement; avoids the
    # spurious minima at the δe bound that a fixed initial guess falls into with flaps down
    best, z0 = None, [0.05, 0.0, 0.5]
    for al in np.radians(np.arange(-4.0, 15.0, 1.0)):
        for de in np.radians(np.arange(-24.0, 25.0, 4.0)):
            r = res([al, de, 0.5])
            m = r[1] ** 2 + (r[2] / 5.0) ** 2
            if best is None or m < best:
                best, z0 = m, [al, de, 0.5]
    sol = least_squares(res, z0, bounds=([-0.3, -0.6, 0.0], [0.4, 0.6, 1.0]), xtol=1e-12, ftol=1e-12)
    x, c = make(sol.x)
    info = {}
    sim.derivatives(0.0, x, c, info)
    return {"x": x, "controls": c, "alpha_deg": math.degrees(sol.x[0]), "delta_e_deg": math.degrees(sol.x[1]),
            "throttle": float(sol.x[2]), "residual": float(np.max(np.abs(sol.fun))), "ok": bool(np.max(np.abs(sol.fun)) < 1e-4),
            "T_N": info["T"], "CL": info["CL"], "CD": info["CD"], "V": V, "h": h, "gamma_deg": math.degrees(gamma)}


def linearise(sim: SixDOF, x0: np.ndarray, c0: Controls, eps: float = 1e-5) -> dict:
    """Numerical Jacobian of the 6-DOF about a trim point and its modes (state [u w q θ] / [v p r φ])."""
    def f_e(xe):  # Euler-angle state: [u v w p q r φ θ ψ]
        x = x0.copy()
        x[3:6] = xe[0:3]
        x[10:13] = xe[3:6]
        x[6:10] = quat_from_euler(*xe[6:9])
        d = sim.derivatives(0.0, x, c0)
        phi, th, _ = xe[6:9]
        p, q, r = xe[3:6]
        phid = p + (q * math.sin(phi) + r * math.cos(phi)) * math.tan(th)
        thd = q * math.cos(phi) - r * math.sin(phi)
        psid = (q * math.sin(phi) + r * math.cos(phi)) / math.cos(th)
        return np.concatenate([d[3:6], d[10:13], [phid, thd, psid]])
    xe0 = np.concatenate([x0[3:6], x0[10:13], euler_from_quat(x0[6:10])])
    n = 9
    A = np.zeros((n, n))
    for j in range(n):
        dx = np.zeros(n)
        dx[j] = eps * max(1.0, abs(xe0[j]))
        A[:, j] = (f_e(xe0 + dx) - f_e(xe0 - dx)) / (2 * dx[j])
    lon_i, lat_i = [0, 2, 4, 7], [1, 3, 5, 6]
    Alon, Alat = A[np.ix_(lon_i, lon_i)], A[np.ix_(lat_i, lat_i)]
    return {"A": A, "A_lon": Alon, "A_lat": Alat, "modes": modes(Alon, Alat, float(np.linalg.norm(x0[3:6])))}


def _pair(lam):
    wn = abs(lam)
    return {"wn": float(wn), "zeta": float(-lam.real / wn), "period_s": float(2 * math.pi / abs(lam.imag))}


def modes(Alon, Alat, V) -> dict:
    out = {}
    ll = np.linalg.eigvals(Alon)
    cp = sorted([z for z in ll if z.imag > 1e-9], key=abs)
    if len(cp) == 2:
        out["phugoid"], out["short_period"] = _pair(cp[0]), _pair(cp[1])
    elif len(cp) == 1:
        out["phugoid" if abs(cp[0]) < 0.5 else "short_period"] = _pair(cp[0])
    la = np.linalg.eigvals(Alat)
    cp = [z for z in la if z.imag > 1e-9]
    re = sorted([z.real for z in la if abs(z.imag) <= 1e-9], key=abs)
    if cp:
        out["dutch_roll"] = _pair(cp[0])
    if len(re) >= 2:
        out["spiral"] = {"lambda": float(re[0]), "T_half_s": math.log(2) / -re[0] if re[0] < 0 else math.inf,
                         "T2_s": math.log(2) / re[0] if re[0] > 0 else math.inf}
        out["roll"] = {"lambda": float(re[-1]), "tau_s": -1.0 / re[-1] if re[-1] < 0 else math.inf}
    return out
