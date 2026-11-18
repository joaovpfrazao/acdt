"""Constraint analysis (T/W or P/W versus W/S) and design-point selection.

Equations (all in terms of local wing loading W/S and dynamic pressure q):

* Level constant-velocity turn, load factor n (Gudmundsson 2014, Sec. 3.2):
  T/W = q [CD0/(W/S) + K (n/q)² (W/S)]
* Desired rate of climb (Gudmundsson Sec. 3.2):
  T/W = V_V/V + q CD0/(W/S) + K (W/S)/q
* Desired take-off ground run S_G (Gudmundsson Sec. 3.2):
  T/W = V_LOF²/(2 g S_G) + q CD_TO/(W/S) + μ (1 − q CL_TO/(W/S)),  q at V_LOF/√2
* Desired cruise / maximum speed (Gudmundsson Sec. 3.2):
  T/W = q CD0/(W/S) + K (W/S)/q
* Service ceiling (Gudmundsson Sec. 3.2): ROC = 0.508 m/s at the best
  climb speed V_Y at ceiling density.
* Stall: W/S = ½ ρ V_S² CLmax (Raymer 6th ed. Eq. 5.6).
* Landing distance (Raymer Eq. 5.11, imperial):
  S_land[ft] = 80 (W/S)[psf]/(σ CLmax) + S_a, S_a = 1000 (airliner), 600 (GA), 450 (STOL).
* Turn rate ω → load factor n = √(1 + (ωV/g)²) (Anderson APD Ch. 6).
* Propeller aircraft: P/W = (T/W)·V/η_p at the constraint speed, referred to
  sea level with the power lapse (Gudmundsson Sec. 3.2 conversion). Jets:
  T_SL/W0 = (T/W)/lapse. Weight fraction β = W/W0 (Mattingly et al.,
  *Aircraft Engine Design*, 2002, Ch. 2 master equation) scales W/S and T/W.
* Best-climb speeds: propeller V_Y ≈ minimum-power speed
  V = √(2(W/S)/ρ · √(K/(3 CD0))); jet ≈ V at (L/D)max (Anderson APD Ch. 5).

Design-point selection criteria:

* ``max_wing_loading`` (default; Raymer 6th ed. Sec. 5.1): the selected W/S is
  the lowest of the W/S limits imposed by the requirements (stall, landing,
  ...), i.e. the highest feasible W/S; the T/W (P/W) is the envelope value there.
  If no W/S limit exists, the envelope minimum is used.
* ``min_power``: lowest required T/W (P/W) in the feasible region, highest W/S
  among equal values (Gudmundsson 2014 Sec. 3.3 reading of the diagram) —
  selected automatically when a cost/mass objective is set, since first-order
  cost and mass scale with installed power at fixed W0.
* ``min_weight``: lowest *empty weight* in the feasible region, evaluated with
  the component weight build-up for the wing/tail geometry and installed power
  implied by each candidate W/S (Raymer 6th ed. Ch. 19 — the minimum-weight
  point of the sizing carpet, here at fixed W0 and fuel fraction; the MDA loop
  then re-sizes). Selected automatically for mass/cost objectives when the
  component weight method is active, because ``min_power`` ignores wing weight
  and can drive W/S (and the wing) to unrealistic sizes.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from acdt import G0
from acdt.core.atmosphere import isa
from .propulsion import is_propeller, lapse
from acdt.core.requirements import Requirement, RequirementSet, handlers, register_handler

PSF = 47.88025898
FT = 0.3048


@dataclass
class AeroContext:
    CD0: float
    K: float
    CLmax_clean: float
    CLmax_takeoff: float
    CLmax_landing: float
    CL_ground: float = 0.5  # CL during ground roll (Gudmundsson Sec. 3.2 example value; user assumption)
    dCD0_takeoff: float = 0.01  # flap/gear increment during T-O (user assumption; Raymer Sec. 12.6 build-up planned for Phase 3)
    mu_roll: float = 0.04  # dry asphalt/concrete, Raymer Table 17.1 range 0.03–0.05
    camber: object | None = None  # Phase 9 camber-flap schedule: CD += ΔCD_env(CL) ≤ 0 (aero.camber_flap)

    def dcd(self, CL):
        return self.camber.dcd(CL) if self.camber is not None else 0.0 * np.asarray(CL, float)

    def CL_opt(self, p: float) -> float:
        """CL maximising CL^p/CD (p = 1.5 min power, 1 max L/D) on the (envelope) polar."""
        from .aero.drag import DragPolar
        pol = DragPolar(self.CD0, self.K, self.camber)
        return pol.CL_min_power if p > 1.2 else pol.CL_LDmax


@dataclass
class PropContext:
    kind: str
    eta_cruise: float = 0.80
    eta_climb: float = 0.75
    eta_takeoff: float = 0.55


@dataclass
class ConstraintContext:
    aero: AeroContext
    prop: PropContext
    cruise_altitude: float = 0.0
    cruise_speed: float | None = None
    cruise_weight_fraction: float = 1.0
    landing_weight_fraction: float = 1.0
    approach_distance_ft: float = 600.0  # Raymer Eq. 5.11 S_a, GA default


@dataclass
class Constraint:
    name: str
    key: str
    kind: str  # "curve" | "ws_max"
    tw: Callable[[np.ndarray], np.ndarray] | None = None  # T/W0 required at the condition (installed thrust)
    V: Callable[[np.ndarray], np.ndarray] | None = None
    altitude: float = 0.0
    eta: float = 0.8
    ws_limit: float | None = None
    note: str = ""

    def required(self, ws: np.ndarray, prop: PropContext) -> np.ndarray:
        """Sea-level referenced T/W0 (jet, -) or P/W0 (prop, W/N)."""
        tw = self.tw(ws)
        lp = lapse(prop.kind, isa(self.altitude).sigma)
        if is_propeller(prop.kind):
            return tw * self.V(ws) / (self.eta * lp)
        return tw / lp


def _cruise_tw(ws, rho, V, aero, beta=1.0, n=1.0):
    """Level flight / sustained turn at load factor n (Gudmundsson 2014 Sec. 3.2;
    Mattingly weight fraction beta):  T/W0 = beta * [ q CD0/(beta W/S) + K n^2 (beta W/S)/q ]."""
    q = 0.5 * rho * V**2
    wsl = beta * ws
    return beta * (q * (aero.CD0 + aero.dcd(n * wsl / q)) / wsl + aero.K * n**2 * wsl / q)


def _vy(ws, rho, aero, prop_kind):
    """Best-climb speed: minimum-power (prop) or max-L/D (jet) speed (Anderson 1999 Ch. 5), not below
    1.2 V_S1 (CS 23.65(a) / 14 CFR 23.65 climb speed floor) — for high-AR wings C_L,mp can exceed CLmax."""
    if getattr(aero, "camber", None) is not None:   # envelope polar: optimum CL found numerically
        v = np.sqrt(2 * ws / (rho * aero.CL_opt(1.5 if is_propeller(prop_kind) else 1.0)))
    elif is_propeller(prop_kind):
        v = np.sqrt(2 * ws / rho * np.sqrt(aero.K / (3 * aero.CD0)))
    else:
        v = np.sqrt(2 * ws / rho * np.sqrt(aero.K / aero.CD0))
    return np.maximum(v, 1.2 * np.sqrt(2 * ws / (rho * aero.CLmax_clean)))


def _climb(name, key, roc, h, ctx: ConstraintContext, V_fixed=None):
    rho, aero = isa(h).rho, ctx.aero

    def V(ws):
        return np.full_like(ws, V_fixed) if V_fixed else _vy(ws, rho, aero, ctx.prop.kind)

    def tw(ws):
        v = V(ws)
        q = 0.5 * rho * v**2
        return roc / v + q * (aero.CD0 + aero.dcd(ws / q)) / ws + aero.K * ws / q

    return Constraint(name, key, "curve", tw, V, h, ctx.prop.eta_climb)


# ---- builders registered against requirement keys --------------------------
@register_handler("constraint", "cruise_speed")
def _c_cruise(r: Requirement, ctx: ConstraintContext):
    h = r.params.get("altitude", ctx.cruise_altitude)
    rho, V = isa(h).rho, r.value
    return [Constraint(f"Cruzeiro {V:.0f} m/s @ {h:.0f} m", r.key, "curve",
                       lambda ws: _cruise_tw(ws, rho, V, ctx.aero, ctx.cruise_weight_fraction),
                       lambda ws: np.full_like(ws, V), h, ctx.prop.eta_cruise)]


@register_handler("constraint", "max_speed")
def _c_vmax(r, ctx):
    h = r.params.get("altitude", ctx.cruise_altitude)
    rho, V = isa(h).rho, r.value
    return [Constraint(f"Vmax {V:.0f} m/s @ {h:.0f} m", r.key, "curve",
                       lambda ws: _cruise_tw(ws, rho, V, ctx.aero, ctx.cruise_weight_fraction),
                       lambda ws: np.full_like(ws, V), h, ctx.prop.eta_cruise)]


@register_handler("constraint", "climb_rate")
def _c_roc(r, ctx):
    h = r.params.get("altitude", 0.0)
    return [_climb(f"RC {r.value:.1f} m/s @ {h:.0f} m", r.key, r.value, h, ctx, r.params.get("speed"))]


@register_handler("constraint", "service_ceiling")
def _c_ceiling(r, ctx):
    return [_climb(f"Teto {r.value:.0f} m", r.key, 0.508, r.value, ctx)]


def _turn(name, key, n, h, V, ctx):
    rho = isa(h).rho
    return Constraint(name, key, "curve", lambda ws: _cruise_tw(ws, rho, V, ctx.aero, 1.0, n),
                      lambda ws: np.full_like(ws, V), h, ctx.prop.eta_cruise)


@register_handler("constraint", "load_factor")
def _c_turn_n(r, ctx):
    h = r.params.get("altitude", ctx.cruise_altitude)
    V = r.params.get("speed") or ctx.cruise_speed
    if V is None:
        raise ValueError("load_factor needs a 'speed' qualifier or a cruise_speed requirement")
    return [_turn(f"Volta n={r.value:.1f} @ {V:.0f} m/s", r.key, r.value, h, V, ctx)]


@register_handler("constraint", "turn_rate")
def _c_turn_rate(r, ctx):
    h = r.params.get("altitude", ctx.cruise_altitude)
    V = r.params.get("speed") or ctx.cruise_speed
    if V is None:
        raise ValueError("turn_rate needs a 'speed' qualifier or a cruise_speed requirement")
    n = math.sqrt(1 + (r.value * V / G0) ** 2)
    return [_turn(f"Volta {math.degrees(r.value):.0f} deg/s (n={n:.2f})", r.key, n, h, V, ctx)]


@register_handler("constraint", "takeoff_ground_roll")
def _c_takeoff(r, ctx):
    h = r.params.get("altitude", 0.0)
    rho, a, SG = isa(h).rho, ctx.aero, r.value

    def vlof(ws):
        return 1.1 * np.sqrt(2 * ws / (rho * a.CLmax_takeoff))

    def V(ws):
        return vlof(ws) / math.sqrt(2)

    def tw(ws):
        q = 0.5 * rho * V(ws) ** 2
        cd_to = a.CD0 + a.dCD0_takeoff + a.K * a.CL_ground**2
        return vlof(ws) ** 2 / (2 * G0 * SG) + q * cd_to / ws + a.mu_roll * (1 - q * a.CL_ground / ws)

    return [Constraint(f"Corrida descolagem {SG:.0f} m", r.key, "curve", tw, V, h, ctx.prop.eta_takeoff)]


@register_handler("constraint", "stall_speed")
def _c_stall(r, ctx):
    h = r.params.get("altitude", 0.0)
    ws = 0.5 * isa(h).rho * r.value**2 * ctx.aero.CLmax_landing / ctx.landing_weight_fraction
    return [Constraint(f"Perda {r.value:.1f} m/s", r.key, "ws_max", ws_limit=ws)]


@register_handler("constraint", "landing_distance")
def _c_landing(r, ctx):
    h = r.params.get("altitude", 0.0)
    sigma = isa(h).sigma
    s_ft = r.value / FT
    ws_psf = (s_ft - ctx.approach_distance_ft) * sigma * ctx.aero.CLmax_landing / 80
    ws = max(ws_psf, 0.0) * PSF / ctx.landing_weight_fraction
    return [Constraint(f"Aterragem {r.value:.0f} m", r.key, "ws_max", ws_limit=ws,
                       note="Raymer Eq. 5.11")]


def build_constraints(reqs: RequirementSet, ctx: ConstraintContext) -> list[Constraint]:
    out: list[Constraint] = []
    hs = handlers("constraint")
    for r in reqs.by_stage("constraint"):
        if r.key in hs:
            out += hs[r.key](r, ctx)
    return out


@dataclass
class DesignPoint:
    ws: float  # W0/S [N/m^2]
    value: float  # T_SL/W0 [-] or P_SL/W0 [W/N]
    metric: str  # "T/W" or "P/W"
    feasible: bool
    active: list[str] = field(default_factory=list)
    ws_max: float = math.inf
    message: str = ""
    ws_grid: np.ndarray | None = None
    envelope: np.ndarray | None = None
    curves: dict[str, np.ndarray] = field(default_factory=dict)


def design_point(constraints: list[Constraint], prop: PropContext, ws_range=(50.0, 3000.0), n=600,
                 value_max: float | None = None, margin: float = 0.0,
                 criterion: str = "max_wing_loading", weight_fn=None, ws_fixed: float | None = None,
                 value_fixed: float | None = None) -> DesignPoint:
    """Design point on the constraint diagram. Criteria: ``max_wing_loading`` (W/S limit), ``min_power``
    (envelope minimum), ``min_weight`` (component empty mass via ``weight_fn``), ``fixed_ws`` (W/S given,
    e.g. by the OpenMDAO optimiser, :mod:`.mdo`). The value is envelope(W/S)·(1+margin), or ``value_fixed``
    if that is larger (an installed power/thrust above the requirement)."""
    metric = "P/W" if is_propeller(prop.kind) else "T/W"
    ws_lines = [c for c in constraints if c.kind == "ws_max"]
    ws_max = min([c.ws_limit for c in ws_lines], default=math.inf)
    hi = min(ws_range[1], ws_max * 1.4) if math.isfinite(ws_max) else ws_range[1]
    grid = np.linspace(ws_range[0], max(hi, ws_range[0] * 2), n)
    curves_c = [c for c in constraints if c.kind == "curve"]
    curves = {c.name: c.required(grid, prop) for c in curves_c}

    def envelope(x):
        x = np.atleast_1d(np.asarray(x, dtype=float))
        return np.max(np.vstack([c.required(x, prop) for c in curves_c]), axis=0) if curves_c else np.zeros_like(x)

    env = envelope(grid)
    if not math.isfinite(ws_max) or ws_max >= ws_range[0]:
        mask = grid <= ws_max
    else:
        mask = np.zeros_like(grid, dtype=bool)
    if not mask.any():
        return DesignPoint(math.nan, math.nan, metric, False, [], ws_max,
                           "No feasible wing loading: W/S limit below the search range", grid, env, curves)
    if criterion == "max_wing_loading" and math.isfinite(ws_max):
        ws_star = ws_max
    elif criterion in ("max_wing_loading", "min_power"):
        feas = np.where(mask, env, np.inf)
        i = int(np.argmin(feas))
        lo_i, hi_i = max(i - 1, 0), min(i + 1, len(grid) - 1)
        loc = np.linspace(grid[lo_i], min(grid[hi_i], ws_max), 401)  # local refinement of the minimum
        e_loc = envelope(loc)
        cand = np.where(e_loc <= e_loc.min() * (1 + 1e-6))[0]
        ws_star = float(loc[cand.max()])
    elif criterion == "min_weight":
        if weight_fn is None:
            raise ValueError("criterion 'min_weight' needs weight_fn(ws, value)")
        cand_ws = np.linspace(grid[mask].min(), grid[mask].max(), 80)
        masses = [weight_fn(float(w), float(envelope(w)[0]) * (1 + margin)) for w in cand_ws]
        i = int(np.argmin(masses))
        lo, hi2 = cand_ws[max(i - 1, 0)], cand_ws[min(i + 1, len(cand_ws) - 1)]
        loc = np.linspace(lo, hi2, 41)
        m_loc = [weight_fn(float(w), float(envelope(w)[0]) * (1 + margin)) for w in loc]
        ws_star = float(loc[int(np.argmin(m_loc))])
    elif criterion == "fixed_ws":
        if ws_fixed is None:
            raise ValueError("criterion 'fixed_ws' needs ws_fixed")
        ws_star = float(ws_fixed)
    else:
        raise ValueError(f"unknown design-point criterion '{criterion}'")
    e_star = float(envelope(ws_star)[0])
    val = e_star * (1 + margin)
    if value_fixed is not None:
        val = max(val, float(value_fixed))
    active = [c.name for c in curves_c if abs(float(c.required(np.array([ws_star]), prop)[0]) - e_star) <= 0.01 * e_star]
    active += [c.name for c in ws_lines if abs(c.ws_limit - ws_star) <= 0.01 * ws_star]
    ok, msg = True, ""
    if criterion == "fixed_ws" and ws_star > ws_max * (1 + 1e-9):
        ok, msg = False, f"Infeasible: fixed W/S {ws_star:.1f} N/m² above the W/S limit {ws_max:.1f}"
    if value_max is not None and val > value_max:
        ok = False
        msg = (f"Infeasible: required {metric} {val:.3g} exceeds available {value_max:.3g} "
               f"(binding: {', '.join(active)})")
    return DesignPoint(float(ws_star), float(val), metric, ok, active, ws_max, msg, grid, env, curves)


def plot_constraint_diagram(dp: DesignPoint, constraints: list[Constraint], path, title: str = "",
                            per_kg: bool = True):
    """Matplotlib constraint diagram. Axes in kg/m² and W/kg (or T/W) for readability."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    xs = dp.ws_grid / G0 if per_kg else dp.ws_grid
    yscale = G0 if (per_kg and dp.metric == "P/W") else 1.0
    fig, ax = plt.subplots(figsize=(8, 5.5))
    for name, cv in dp.curves.items():
        ax.plot(xs, cv * yscale, lw=1.6, label=name)
    ymax = np.nanpercentile(dp.envelope * yscale, 60) * 2.5 if dp.envelope is not None else 1
    ymax = max(ymax, dp.value * yscale * 1.6) if math.isfinite(dp.value) else ymax
    for c in constraints:
        if c.kind == "ws_max":
            x = c.ws_limit / G0 if per_kg else c.ws_limit
            ax.axvline(x, ls="--", lw=1.6, color="k")
            ax.text(x, ymax * 0.95, " " + c.name, rotation=90, va="top", fontsize=8)
    env = dp.envelope * yscale
    feas = dp.ws_grid <= dp.ws_max
    ax.fill_between(xs, env, ymax, where=feas, color="tab:green", alpha=0.12, label="Região viável")
    if math.isfinite(dp.ws):
        ax.plot(dp.ws / G0 if per_kg else dp.ws, dp.value * yscale, "r*", ms=16, label="Design point")
    ax.set_xlim(xs.min(), xs.max())
    ax.set_ylim(0, ymax)
    ax.set_xlabel("W0/S [kg/m²]" if per_kg else "W0/S [N/m²]")
    if dp.metric == "P/W":
        ax.set_ylabel("P_SL/W0 [W/kg]" if per_kg else "P/W [W/N]")
    else:
        ax.set_ylabel("T_SL/W0 [-]")
    ax.set_title(title or "Diagrama de restrições")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, loc="upper right")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path
