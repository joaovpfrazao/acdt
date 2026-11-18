"""Fixed-pitch propeller model: blade-element/momentum theory (BEMT) map C_T(J), C_P(J) and the
rpm-matched operating point of a fixed-pitch propeller on a torque-limited engine.

Sources
-------
* Blade-element / momentum theory with Prandtl tip-loss factor: McCormick, *Aerodynamics,
  Aeronautics and Flight Mechanics*, 2nd ed., 1995, Ch. 6; Glauert, *Airplane Propellers*, in
  Durand (ed.), *Aerodynamic Theory* Vol. IV, 1935.
* Robust one-equation solution in the inflow angle φ (guaranteed bracket): Ning, "A simple
  solution method for the blade element momentum equations with guaranteed convergence",
  *Wind Energy* 17, 2014 (propeller sign convention, residual multiplied through so that the
  static case V = 0 is regular).
* Coefficients C_T = T/(ρn²D⁴), C_P = P/(ρn³D⁵), J = V/(nD), η = J C_T/C_P: McCormick 1995 Ch. 6;
  Gudmundsson, *General Aviation Aircraft Design*, 2014, Ch. 14.
* Automatic geometry (no pitch/chord given): design cl at max cl/cd of the section polar at 0.75 R
  (Adkins & Liebeck, "Design of optimum propellers", *J. Aircraft* 31(2), 1994 — design cl choice);
  pitch such that the propeller absorbs rated power at rated rpm at the design (cruise) speed.
* Fixed pitch ⇒ rpm (and so engine power) is set by the propeller load: the engine runs where
  P_prop(n) = P_engine(n). Static rpm well below rated is the classical consequence (C172S POH:
  2300–2400 static rpm vs 2700 rated).

PRESSUPOSTOS (design choices, documented in the result notes)
--------------------------------------------------------------
* Engine full-throttle power ∝ (n/n_rated)^k with k = 1 (constant torque) below rated rpm,
  scaled by the altitude lapse (propulsion.lapse) and throttle; rpm limited to rated (redline):
  above it the pilot/governor reduces power.
* Section: one polar (default Clark Y, NeuralFoil/XFOIL) at the 0.75 R static Reynolds number,
  Viterna–Corrigan (1982) post-stall extrapolation beyond the table,
  no compressibility, no hub loss (spinner), root cut-out 0.15 R, constant geometric pitch along
  the blade (helical twist), elliptic tip planform (chord constant to 0.6 R, elliptic to tip).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import brentq

from acdt.core.atmosphere import isa

X_HUB = 0.15
N_STATIONS = 24


def chord_shape(x):
    """c(x)/c(0.75R): constant to 0.6 R, elliptic to the tip (PRESSUPOSTO)."""
    x = np.asarray(x, float)
    s = np.where(x <= 0.6, 1.0, np.sqrt(np.clip(1 - ((x - 0.6) / 0.4) ** 2, 0.0, 1.0)))
    return s / math.sqrt(1 - (0.15 / 0.4) ** 2)


@dataclass
class SectionPolar:
    alpha_deg: np.ndarray
    cl: np.ndarray
    cd: np.ndarray
    source: str = ""
    blade_ar: float = 6.0   # for the Viterna C_Dmax; set from the blade geometry by make_propeller

    def __call__(self, a_rad):
        a = math.degrees(a_rad)
        lo, hi = self.alpha_deg[0], self.alpha_deg[-1]
        if a > hi:
            return self._viterna(a_rad, -1)
        if a < lo:
            cl, cd = self._viterna(-a_rad, 0, mirror=True)
            return -cl, cd
        return float(np.interp(a, self.alpha_deg, self.cl)), float(np.interp(a, self.alpha_deg, self.cd))

    def _viterna(self, a, i, mirror=False):
        """Post-stall extrapolation from the last table point (Viterna & Corrigan 1982, NASA CP-2230),
        C_Dmax = 1.11 + 0.018 AR (blade aspect ratio ``blade_ar``)."""
        a_s = math.radians(abs(self.alpha_deg[i]))
        cls, cds = abs(float(self.cl[i])), float(self.cd[i])
        a = min(abs(a), math.radians(89.0))
        cdm = 1.11 + 0.018 * self.blade_ar
        B2 = (cds - cdm * math.sin(a_s) ** 2) / math.cos(a_s)
        A2 = (cls - cdm * math.sin(a_s) * math.cos(a_s)) * math.sin(a_s) / math.cos(a_s) ** 2
        cl = cdm / 2 * math.sin(2 * a) + A2 * math.cos(a) ** 2 / math.sin(a)
        cd = cdm * math.sin(a) ** 2 + B2 * math.cos(a)
        return float(cl), float(cd)

    @classmethod
    def from_airfoil(cls, airfoil: str, Re: float, prefer: str = "neuralfoil"):
        from .aero.airfoil import airfoil_polar
        p = airfoil_polar(airfoil, Re, prefer=prefer)
        return cls(np.asarray(p.alpha, float), np.asarray(p.cl, float), np.asarray(p.cd, float),
                   f"{airfoil} Re {Re:.2g} ({p.source})")

    def design_cl(self):
        """cl at max cl/cd on the attached branch (Adkins & Liebeck 1994 design choice)."""
        m = (self.cl > 0.1) & (self.alpha_deg < self.alpha_deg[int(np.argmax(self.cl))])
        i = int(np.argmax(np.where(m, self.cl / self.cd, -1)))
        return float(self.cl[i]), float(self.alpha_deg[i])


def bemt(J, D, pitch, blades, c075_D, polar: SectionPolar, n_st=N_STATIONS):
    """C_T, C_P at advance ratio J (non-dimensional; independent of n and ρ apart from the polar's Re)."""
    R = D / 2
    xs = np.linspace(X_HUB, 1.0, n_st + 1)
    xm = 0.5 * (xs[1:] + xs[:-1])
    dx = np.diff(xs)
    CT = CP = 0.0
    for x, d in zip(xm, dx):
        r = x * R
        c = c075_D * D * float(chord_shape(x))
        beta = math.atan(pitch / (2 * math.pi * r))
        sig = blades * c / (2 * math.pi * r)
        lam = J / (math.pi * x)  # V/(Ω r)

        def parts(phi):
            cl, cd = polar(beta - phi)
            sp, cp = math.sin(phi), math.cos(phi)
            f = blades / 2 * (1 - x) / (x * max(sp, 1e-9))
            F = 2 / math.pi * math.acos(min(1.0, math.exp(-f)))
            F = max(F, 1e-4)
            cn, ct = cl * cp - cd * sp, cl * sp + cd * cp
            k = sig * cn / (4 * F * sp * sp)
            kp = sig * ct / (4 * F * sp * cp)
            return cn, ct, k, kp

        def res(phi):
            cn, ct, k, kp = parts(phi)
            return math.sin(phi) * (1 - k) - lam * math.cos(phi) * (1 + kp)

        eps = 1e-6
        try:
            phi = brentq(res, eps, math.pi / 2 - eps, xtol=1e-10)
        except ValueError:
            phi = math.atan2(lam, 1.0)  # windmilling / no bracket: undisturbed inflow
        cn, ct, k, kp = parts(phi)
        # W from the tangential side (regular at V = 0): W = Ω r (1 − a')/cos φ, 1 − a' = 1/(1 + k')
        Wn = (math.pi * x) / ((1 + kp) * math.cos(phi))  # W/(nD)
        dCT = blades * 0.5 * Wn ** 2 * (c / D) * cn * (R / D) * d
        dCP = blades * 0.5 * Wn ** 2 * (c / D) * ct * (R / D) * d * 2 * math.pi * x * (R / D)
        CT += dCT
        CP += dCP
    return CT, CP


@dataclass
class FixedPitchPropeller:
    D: float
    pitch: float
    blades: int
    c075_D: float
    rpm_rated: float
    P_rated: float               # shaft power at rated rpm, SL, full throttle [W]
    kind: str = "piston_prop"
    torque_exp: float = 1.0      # P_engine ∝ (n/n_rated)^k at full throttle (PRESSUPOSTO k = 1)
    n_props: int = 1             # identical engine+propeller units; P_rated is the installed total
    J: list = field(default_factory=list)
    CT: list = field(default_factory=list)
    CP: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    polar_source: str = ""

    # ---------------------------------------------------------------- map
    def build_map(self, polar: SectionPolar, J_max=None):
        Jm = J_max or 1.6 * self.pitch / self.D + 0.2
        Js = np.linspace(0.0, Jm, 33)
        ct, cp = zip(*[bemt(j, self.D, self.pitch, self.blades, self.c075_D, polar) for j in Js])
        self.J, self.CT, self.CP = [float(v) for v in Js], [float(v) for v in ct], [float(v) for v in cp]
        self.polar_source = polar.source
        return self

    def coeffs(self, J):
        J = min(max(J, 0.0), self.J[-1])
        return float(np.interp(J, self.J, self.CT)), float(np.interp(J, self.J, self.CP))

    def eta(self, J):
        ct, cp = self.coeffs(J)
        return J * ct / cp if cp > 0 else 0.0

    # ---------------------------------------------------------------- operating point
    def engine_power(self, n, h, throttle=1.0):
        from .propulsion import lapse
        nr = self.rpm_rated / 60
        return throttle * self.P_rated * lapse(self.kind, isa(max(h, 0.0)).sigma) * (n / nr) ** self.torque_exp

    def operating_point(self, V, h, throttle=1.0):
        """Full/partial-throttle equilibrium rpm: C_P ρ n³ D⁵ = P_engine(n); rpm capped at rated (redline).
        Returns dict T [N], P [W] shaft, rpm, J, eta."""
        rho = isa(max(h, 0.0)).rho
        nr = self.rpm_rated / 60
        th = min(max(throttle, 0.0), 1.0)
        if th <= 0:
            return {"T": 0.0, "P": 0.0, "rpm": 0.0, "J": float("inf"), "eta": 0.0}

        def absorbed(n):
            return self.coeffs(V / (n * self.D))[1] * rho * n ** 3 * self.D ** 5

        def g(n):
            return absorbed(n) - self.engine_power(n, h, th) / self.n_props

        n_lo = max(V / (self.D * self.J[-1]) * 1.0001, 0.05 * nr)
        if g(nr) <= 0:  # propeller too light: redline, engine throttled back to what the prop absorbs
            n = nr
        elif g(n_lo) >= 0:
            n = n_lo
        else:
            n = brentq(g, n_lo, nr, xtol=1e-6)
        J = V / (n * self.D)
        ct, cp = self.coeffs(J)
        T = ct * rho * n ** 2 * self.D ** 4 * self.n_props
        P = cp * rho * n ** 3 * self.D ** 5 * self.n_props
        return {"T": float(T), "P": float(P), "rpm": float(n * 60), "J": float(J),
                "eta": float(T * V / P) if P > 0 else 0.0}

    def thrust_for(self, V, h, T_req):
        """Throttle and operating point giving thrust T_req at (V, h) (cruise/loiter: T = D)."""
        full = self.operating_point(V, h, 1.0)
        if T_req >= full["T"]:
            return 1.0, full
        th = brentq(lambda t: self.operating_point(V, h, t)["T"] - T_req, 1e-4, 1.0, xtol=1e-5)
        return th, self.operating_point(V, h, th)

    def eta_effective(self, V, h):
        """T·V / (rated power × lapse) at full throttle — the 'eta' the constant-efficiency formulas expect."""
        op = self.operating_point(V, h, 1.0)
        return op["T"] * V / self.engine_power(self.rpm_rated / 60, h, 1.0)

    def static_rpm(self, h=0.0):
        return self.operating_point(0.0, h, 1.0)["rpm"]

    def to_dict(self):
        return {k: getattr(self, k) for k in ("D", "pitch", "blades", "c075_D", "rpm_rated", "P_rated", "kind",
                                              "torque_exp", "n_props", "J", "CT", "CP", "notes", "polar_source")}

    @classmethod
    def from_dict(cls, d):
        return cls(**d)


# -------------------------------------------------------------------- construction from the spec
def make_propeller(cfg: dict, P_rated: float, kind: str, V_design: float | None = None, h_design: float = 0.0,
                   n_props: int = 1, polar: "SectionPolar | None" = None):
    """Build (and calibrate) the propeller from ``assumptions.propulsion.propeller``.

    Keys: type: fixed_pitch; rpm_rated; blades (2); airfoil ('clarky'); diameter_m or tip_mach (helical tip
    Mach at the design point); pitch_m (geometric, 0.75 R) or 'auto'; chord_075_over_D, or static_rpm
    (calibrate the chord to a measured static rpm), or 'auto' (design cl at max cl/cd)."""
    t = cfg.get("type", "fixed_pitch")
    if t != "fixed_pitch":
        raise ValueError(f"propeller type '{t}' not supported (fixed_pitch)")
    if not cfg.get("rpm_rated"):
        raise ValueError("propulsion.propeller.rpm_rated is required (engine/motor rated rpm)")
    nr = cfg["rpm_rated"] / 60
    B = int(cfg.get("blades", 2))
    notes = []
    D = cfg.get("diameter_m")
    if not D:
        M = cfg.get("tip_mach")
        if not M or V_design is None:
            raise ValueError("propulsion.propeller: give diameter_m, or tip_mach (with a cruise speed)")
        a = isa(h_design).a
        D = math.sqrt(max((M * a) ** 2 - V_design ** 2, 1.0)) / (math.pi * nr)
        notes.append(f"D = {D:.3f} m from helical tip Mach {M} at {V_design:.0f} m/s, {cfg['rpm_rated']:.0f} rpm")
    airfoil = cfg.get("airfoil", "clarky")
    pitch, c075 = cfg.get("pitch_m", "auto"), cfg.get("chord_075_over_D", "auto")
    # section polar at the 0.75 R static Reynolds number (first guess of chord for Re; one update)
    c_guess = float(c075) if isinstance(c075, (int, float)) else 0.08
    mu, rho0 = 1.789e-5, isa(0.0).rho
    notes0 = list(notes)
    for _ in range(2):
        notes = list(notes0)
        Re = rho0 * 0.75 * math.pi * nr * D * c_guess * D / mu
        sec = polar if polar is not None else SectionPolar.from_airfoil(
            airfoil, max(Re, 2e4), prefer=cfg.get("solver", "neuralfoil"))
        sec.blade_ar = (1 - X_HUB) / (2 * c_guess)
        prop = FixedPitchPropeller(D, 0.0, B, c_guess, cfg["rpm_rated"], P_rated, kind,
                                   float(cfg.get("torque_exponent", 1.0)), int(n_props))
        static = cfg.get("static_rpm")
        auto_pitch = pitch in (None, "auto")
        if not auto_pitch:
            prop.pitch = float(pitch)
        if auto_pitch and V_design is None:
            raise ValueError("propeller pitch 'auto' needs a design (cruise) speed")

        def set_pitch_for_chord(c):
            prop.c075_D = c
            if auto_pitch:  # absorb rated power at rated rpm at the design point
                def gp(p):
                    prop.pitch = p
                    cp = bemt(V_design / (nr * D), D, p, B, c, sec)[1]
                    return cp * isa(h_design).rho * nr ** 3 * D ** 5 - prop.engine_power(nr, h_design) / n_props
                prop.pitch = brentq(gp, 0.2 * D, 2.5 * D, xtol=1e-4)

        if isinstance(c075, (int, float)):
            set_pitch_for_chord(float(c075))
        elif static:
            def gs(c):
                set_pitch_for_chord(c)
                prop.build_map(sec)
                return prop.static_rpm() - float(static)
            brentq(gs, 0.02, 0.25, xtol=1e-4)
            notes.append(f"chord c/D(0.75R) = {prop.c075_D:.4f} calibrated to static rpm {static} (measured)")
        else:  # auto chord: section at design cl (max cl/cd) at 0.75 R in the design point
            if V_design is None:
                raise ValueError("propeller chord 'auto' needs a design (cruise) speed")
            cl_d, a_d = sec.design_cl()
            x = 0.75

            def gc(c):
                try:
                    set_pitch_for_chord(c)
                except ValueError:  # chord too small/large to absorb the power at any pitch
                    return math.nan
                return _alpha_at(V_design / (nr * D), D, prop.pitch, B, c, sec, x) - math.radians(a_d)
            grid = np.geomspace(0.02, 0.3, 15)
            vals = [gc(c) for c in grid]
            br = next(((grid[i], grid[i + 1]) for i in range(len(grid) - 1)
                       if math.isfinite(vals[i]) and math.isfinite(vals[i + 1]) and vals[i] * vals[i + 1] <= 0), None)
            if br is None:
                raise ValueError("propeller chord 'auto': no chord in c/D 0.02–0.3 gives the design cl at the "
                                 "design point with rated power — give chord_075_over_D or change D/rpm")
            brentq(gc, *br, xtol=1e-4)
            notes.append(f"chord c/D(0.75R) = {prop.c075_D:.4f}: design cl {cl_d:.2f} (max cl/cd) at 0.75R "
                         "in the design point (Adkins & Liebeck 1994)")
        if abs(prop.c075_D - c_guess) / c_guess < 0.1:
            break
        c_guess = prop.c075_D
    if auto_pitch:
        notes.append(f"pitch {prop.pitch:.3f} m (P/D {prop.pitch / D:.2f}): rated power absorbed at rated rpm at "
                     f"{V_design:.1f} m/s, h {h_design:.0f} m (design choice)")
    prop.build_map(sec)
    prop.notes = notes + [f"BEMT (McCormick 1995 Ch. 6, Prandtl tip loss; Ning 2014 solver), section {sec.source}",
                          f"static rpm {prop.static_rpm():.0f} (rated {cfg['rpm_rated']:.0f}); engine torque law "
                          f"P ∝ n^{prop.torque_exp:g} at full throttle (PRESSUPOSTO)"]
    return prop


def _alpha_at(J, D, pitch, B, c075_D, polar, x):
    """Section angle of attack at station x from the BEMT solution (for the design-cl chord rule)."""
    R = D / 2
    r = x * R
    c = c075_D * D * float(chord_shape(x))
    beta = math.atan(pitch / (2 * math.pi * r))
    sig = B * c / (2 * math.pi * r)
    lam = J / (math.pi * x)

    def res(phi):
        cl, cd = polar(beta - phi)
        sp, cp = math.sin(phi), math.cos(phi)
        F = max(2 / math.pi * math.acos(min(1.0, math.exp(-B / 2 * (1 - x) / (x * sp)))), 1e-4)
        k = sig * (cl * cp - cd * sp) / (4 * F * sp * sp)
        kp = sig * (cl * sp + cd * cp) / (4 * F * sp * cp)
        return sp * (1 - k) - lam * cp * (1 + kp)
    phi = brentq(res, 1e-6, math.pi / 2 - 1e-6, xtol=1e-10)
    return beta - phi


# -------------------------------------------------------------------- spec helpers (cached)
_CACHE: dict = {}


def _design_point(spec):
    cfg = spec.assumptions["propulsion"].get("propeller") or {}
    reqs = spec.requirements
    V = cfg.get("design_speed_m_s") or reqs.value("cruise_speed")
    h = cfg.get("design_altitude_m")
    if h is None:
        h = reqs.value("cruise_altitude", spec.assumptions["constraints"]["default_cruise_altitude_m"])
    return V, h


def propeller_for(spec, P_sl):
    """Propeller of ``assumptions.propulsion.propeller`` matched to shaft power P_sl (None if not configured).
    Cached on (config, P to 3 significant figures, design point)."""
    from .propulsion import is_propeller
    cfg = spec.assumptions["propulsion"].get("propeller")
    if not cfg or not P_sl or not is_propeller(spec.propulsion_kind) or not math.isfinite(P_sl):
        return None
    V, h = _design_point(spec)
    key = (repr(sorted(cfg.items())), float(f"{P_sl:.3g}"), spec.propulsion_kind, V, h,
           spec.assumptions["propulsion"].get("n_engines", 1))
    if key not in _CACHE:
        _CACHE[key] = make_propeller(cfg, float(f"{P_sl:.3g}"), spec.propulsion_kind, V, h or 0.0,
                                     int(spec.assumptions["propulsion"].get("n_engines", 1) or 1))
    return _CACHE[key]


def calibrated_etas(res) -> dict:
    """Constant-efficiency inputs that reproduce the propeller map at the sizing conditions (progressive
    calibration of the constraint diagram / Breguet): eta_takeoff at 0.7 V_TO (SL, full throttle; Raymer 17.8
    average-thrust point), eta_climb at V_y (SL, full throttle), both as T·V / rated power; eta_cruise =
    propeller efficiency at the cruise point (T = D)."""
    from .performance import PerfModel, climb_rate
    from acdt import G0
    pm = PerfModel.from_result(res)
    prop = pm.prop
    if prop is None:
        return {}
    W = res.sizing.W0 * G0
    Vto = 1.1 * pm.stall(W, isa(0.0).rho, pm.CLmax_to)
    roc, vy = climb_rate(pm, W, 0.0)
    P = prop.P_rated
    h, Vc = res.cruise_altitude, res.cruise_speed
    D = pm.drag(W, Vc, isa(h).rho)
    th, op = prop.thrust_for(Vc, h, D)
    out = {"eta_takeoff": prop.operating_point(0.7 * Vto, 0.0)["T"] * 0.7 * Vto / P,
           "eta_climb": prop.operating_point(vy, 0.0)["T"] * vy / P,
           "eta_cruise": op["eta"],
           "_V_y": vy, "_roc": roc, "_cruise_throttle": th, "_cruise_rpm": op["rpm"],
           "_static_rpm": prop.static_rpm(), "_V_TO": Vto}
    return out
