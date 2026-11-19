"""Fase 2 — desempenho por segmentos (baixa fidelidade).

Methods (classical, cited):

* **Power required / available, climb and ceilings** — Anderson, *Aircraft Performance and
  Design* (1999), Ch. 5: P_R = D V, ROC = (η P_A − D V)/W maximised over V ≥ 1.2 V_S1 (CS 23.65(a)); service ceiling
  at ROC = 100 ft/min (0.508 m/s), absolute ceiling at ROC = 0. Power lapse from
  :mod:`propulsion` (Gagg & Ferrar for pistons; electric constant).
* **Take-off** — Raymer 6th ed. Sec. 17.8: ground roll
  S_G = (1/(2 g K_A)) ln[(K_T + K_A V_TO²)/K_T], K_T = T/W − μ, K_A = ρ/(2 W/S)(μ C_L − C_D0 − K C_L²),
  V_TO = 1.1 V_S, propeller thrust evaluated at 0.7 V_TO (T = η P/V); transition radius
  R = V_TR²/(0.2 g) at V_TR = 1.15 V_S, climb to the 50 ft obstacle.
* **Landing** — Raymer Sec. 17.9: approach angle γ = ``performance.approach_angle_deg`` (documented parameter,
  default 3°). Default per 14 CFR 23.75(a)(1) / CS 23.75(a)(1) (light aeroplanes, landing distance): steady
  approach at ≥ V_REF with a gradient of descent *not greater than 5.2 % (3°)* down to 50 ft; a steeper angle is
  allowed only when demonstrated by flight test, established as an operating limitation and indicated to the pilot
  (23.75(a)(2)) — set it explicitly in that case. Flare at V_f = 1.23 V_S (n = 1.2),
  free roll 3 s at V_TD = 1.15 V_S, braking ground roll with the same K_T/K_A integral
  (μ_brake ASSUMPTION 0.4 within Raymer Table 17.1 range, idle thrust neglected).
* **Mission by segments** — Raymer Ch. 17 / Anderson Ch. 5 numerical time integration:
  warm-up & take-off (Raymer Table 3.2 fraction 0.970, or 1 min at take-off power for electric),
  climb at V_y with climb power (integrated), cruise at the mission speed/altitude and loiter at
  the minimum-power speed (dm/dt = −c_p P/η_p, or battery power = D V/η_tot + P_systems),
  descent at (L/D)max with idle power (range credited, fuel by the Raymer landing fraction 0.995),
  reserves kept as in sizing.
* **Payload–range** — Raymer Sec. 17.2 / Torenbeek 1982 Ch. 11: points A (max payload, no fuel),
  B (max payload at MTOW), C (max fuel at MTOW), D (ferry), integrated with the same mission model.
  Electric: battery mass fixed; payload traded only against take-off mass.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from acdt import G0
from acdt.core._stub import not_implemented
from acdt.core.atmosphere import isa

from .propulsion import is_propeller, lapse
from .weights import SEGMENT_FRACTIONS

ROC_SERVICE = 0.508  # 100 ft/min


@dataclass
class PerfModel:
    kind: str
    S: float
    CD0: float
    K: float
    CLmax: float
    P_sl: float | None        # installed shaft power SL [W] (prop)
    T_sl: float | None        # jet thrust SL [N]
    eta_cruise: float
    eta_climb: float
    eta_takeoff: float
    c_p: float | None         # kg/(W s)
    c_t: float | None         # kg/(N s)
    eta_tot: float            # electric battery→thrust
    P_sys: float              # electric systems power [W]
    CLmax_to: float
    CLmax_land: float
    mu_roll: float = 0.04
    CL_ground: float = 0.5
    dCD0_to: float = 0.01
    prop: object | None = None  # propeller.FixedPitchPropeller (assumptions.propulsion.propeller) or None
    camber: object | None = None  # aero.camber_flap.CamberSchedule (envelope polar) or None

    auxiliary_fuel_flow_kg_s: float = 0.0
    auxiliary_shaft_W: float = 0.0
    onboard_power_W: float = 0.0

    def polar(self):
        from .aero.drag import DragPolar
        return DragPolar(self.CD0, self.K, self.camber)

    @classmethod
    def from_result(cls, res) -> "PerfModel":
        return cls.from_state(res.spec, res.S, res.polar, res.highlift, res.power_sl, res.thrust_sl)

    @classmethod
    def from_state(cls, spec, S, polar, hl, P_sl, T_sl) -> "PerfModel":
        """Model from the sizing-loop state (used inside the MDA and by the OpenMDAO components)."""
        A = spec.assumptions
        p = A["propulsion"]
        from .sizing import _prop_data
        pd = _prop_data(spec)
        from .propeller import propeller_for
        from .aero.gear_drag import dcd0_takeoff   # + retracted gear extended (0 for a fixed gear)
        return cls(spec.propulsion_kind, S, polar.CD0, polar.K, hl.CLmax_clean, P_sl, T_sl, p["eta_cruise"],
                   p["eta_climb"], p["eta_takeoff"], pd.c_p, pd.c_t, pd.eta_tot, pd.systems_power, hl.CLmax_takeoff,
                   hl.CLmax_landing, A["aero"]["mu_roll"], A["aero"]["CL_ground"], dcd0_takeoff(A["aero"], S),
                   propeller_for(spec, P_sl), getattr(polar, "camber", None),
                   p.get("auxiliary_fuel_flow_kg_s",0.0),p.get("auxiliary_shaft_W",0.0),p.get("onboard_power_W",0.0))

    def drag(self, W, V, rho, n=1.0):
        CL = n * W / (0.5 * rho * V**2 * self.S)
        cd = self.CD0 + self.K * CL**2
        if self.camber is not None:
            cd = cd + self.camber.dcd(CL)
        return 0.5 * rho * V**2 * self.S * cd

    def power_avail(self, h, eta, V=None):
        """Thrust power available [W] at altitude h. With a propeller map and a speed V: T(V)·V at full throttle
        on the rpm-matched operating point (fixed pitch), else the constant-efficiency estimate eta·P·lapse."""
        if self.prop is not None and V is not None:
            if np.ndim(V):
                return np.array([self.prop.operating_point(float(v), h)["T"] * float(v) for v in V])
            return self.prop.operating_point(float(V), h)["T"] * float(V)
        sig = isa(h).sigma
        return eta * max(0.0,self.P_sl*lapse(self.kind,sig)-self.auxiliary_shaft_W)

    def shaft_power(self, h, V=None):
        """Shaft power at full throttle [W] (rpm-limited with a fixed-pitch propeller)."""
        if self.prop is not None and V is not None:
            return self.prop.operating_point(float(V), h)["P"]
        return max(0.0,self.P_sl*lapse(self.kind,isa(h).sigma)-self.auxiliary_shaft_W)

    def stall(self, W, rho, CLmax=None):
        return math.sqrt(2 * W / (rho * self.S * (CLmax or self.CLmax)))


# ------------------------------------------------------------------ climb & ceilings
def climb_rate(m: PerfModel, W: float, h: float) -> tuple[float, float]:
    """Max ROC [m/s] and V_y [m/s] at weight W [N], altitude h (Anderson Ch. 5)."""
    rho = isa(h).rho
    Vs = m.stall(W, rho)
    V = np.linspace(1.2 * Vs, 4 * Vs, 300 if m.prop is None else 60)  # CS 23.65(a): climb speed ≥ 1.2 V_S1
    D = m.drag(W, V, rho)
    if is_propeller(m.kind):
        roc = (m.power_avail(h, m.eta_climb, V if m.prop is not None else None) - D * V) / W
    else:
        roc = (m.T_sl * lapse(m.kind, isa(h).sigma) - D) * V / W
    i = int(np.argmax(roc))
    return float(roc[i]), float(V[i])


def flight_envelope(m: PerfModel, W: float, h_max: float = 15000.0, dh: float = 100.0) -> dict:
    """ROC(h), service and absolute ceilings at weight W (Anderson 1999 Ch. 5)."""
    hs = np.arange(0, h_max + dh, dh)
    roc = np.array([climb_rate(m, W, h)[0] for h in hs])
    vy = np.array([climb_rate(m, W, h)[1] for h in hs])

    def ceil(lim):
        idx = np.where(roc < lim)[0]
        if len(idx) == 0:
            return float("inf")
        i = idx[0]
        if i == 0:
            return 0.0
        return float(np.interp(lim, [roc[i], roc[i - 1]], [hs[i], hs[i - 1]]))

    return {"h": hs, "roc": roc, "vy": vy, "service_ceiling": ceil(ROC_SERVICE), "absolute_ceiling": ceil(0.0),
            "roc_sl": float(roc[0])}


# ------------------------------------------------------------------ takeoff & landing
def _ground_roll(KT, KA, V1, V2):
    if abs(KA) < 1e-12:
        return (V2**2 - V1**2) / (2 * G0 * KT)
    return 1 / (2 * G0 * KA) * math.log((KT + KA * V2**2) / (KT + KA * V1**2))


def takeoff_distance_integrated(m: PerfModel, W: float, h: float = 0.0, h_obs: float = 15.24) -> dict:
    """Raymer Sec. 17.8 take-off: ground roll, transition and climb to the obstacle (50 ft)."""
    rho = isa(h).rho
    Vs = m.stall(W, rho, m.CLmax_to)
    Vto = 1.1 * Vs
    if is_propeller(m.kind):
        T = m.power_avail(h, m.eta_takeoff, 0.7 * Vto if m.prop is not None else None) / (0.7 * Vto)
    else:
        T = m.T_sl * lapse(m.kind, isa(h).sigma)
    KT = T / W - m.mu_roll
    CD0 = m.CD0 + m.dCD0_to
    KA = rho / (2 * W / m.S) * (m.mu_roll * m.CL_ground - CD0 - m.K * m.CL_ground**2)
    SG = _ground_roll(KT, KA, 0.0, Vto) if KT > 0 else float("inf")
    Vtr = 1.15 * Vs
    R = Vtr**2 / (0.2 * G0)
    CLtr = W / (0.5 * rho * Vtr**2 * m.S)
    D = 0.5 * rho * Vtr**2 * m.S * (CD0 + m.K * CLtr**2)
    Ttr = m.power_avail(h, m.eta_takeoff, Vtr if m.prop is not None else None) / Vtr if is_propeller(m.kind) else T
    g = math.asin(max(min((Ttr - D) / W, 0.99), 1e-4))
    h_tr = R * (1 - math.cos(g))
    if h_tr >= h_obs:
        S_tr, S_c = math.sqrt(R**2 - (R - h_obs) ** 2), 0.0
    else:
        S_tr, S_c = R * math.sin(g), (h_obs - h_tr) / math.tan(g)
    return {"ground_roll": SG, "transition": S_tr, "climb": S_c, "total_50ft": SG + S_tr + S_c, "V_TO": Vto,
            "gamma_climb_deg": math.degrees(g), "T_N": T}


def landing_distance(m: PerfModel, W: float, h: float = 0.0, h_obs: float = 15.24, mu_brake: float = 0.4,
                     gamma_deg: float = 3.0, t_free: float = 3.0) -> dict:
    """Raymer Sec. 17.9 landing: approach, flare, free roll, braking (idle thrust neglected).
    ``gamma_deg``: approach angle; default 3° = maximum gradient (5.2 %) of 14 CFR / CS 23.75(a)(1)."""
    rho = isa(h).rho
    Vs = m.stall(W, rho, m.CLmax_land)
    Vf, Vtd = 1.23 * Vs, 1.15 * Vs
    R = Vf**2 / (0.2 * G0)
    ga = math.radians(gamma_deg)
    hf = R * (1 - math.cos(ga))
    Sa = (h_obs - hf) / math.tan(ga)
    Sf = R * math.sin(ga)
    Sfr = t_free * Vtd
    KT = -mu_brake
    KA = rho / (2 * W / m.S) * (mu_brake * m.CL_ground - (m.CD0 + m.dCD0_to) - m.K * m.CL_ground**2)
    SB = _ground_roll(KT, KA, Vtd, 0.0)
    return {"approach": Sa, "flare": Sf, "free_roll": Sfr, "braking": SB, "ground_roll": Sfr + SB,
            "total_50ft": Sa + Sf + Sfr + SB, "V_TD": Vtd, "mu_brake": mu_brake,
            "gamma_deg": gamma_deg}


# ------------------------------------------------------------------ mission simulation
@dataclass
class Segment:
    name: str
    t: float = 0.0        # s
    dist: float = 0.0     # m
    burn: float = 0.0     # kg fuel or J battery energy
    h0: float = 0.0
    h1: float = 0.0
    V: float = 0.0
    note: str = ""


@dataclass
class MissionSim:
    segments: list[Segment]
    range_m: float
    endurance_s: float
    fuel_or_energy_used: float
    available: float
    electric: bool
    limited_by: str = ""

    def table(self):
        u = "Wh" if self.electric else "kg"
        f = 1 / 3600 if self.electric else 1.0
        return [{"segmento": s.name, "t [min]": s.t / 60, "dist [km]": s.dist / 1e3, f"consumo [{u}]": s.burn * f,
                 "h [m]": f"{s.h0:.0f}→{s.h1:.0f}", "V [m/s]": s.V, "nota": s.note} for s in self.segments]


def _burn_rate(m: PerfModel, W, V, h):
    """Fuel flow [kg/s] (prop: c_p D V/η; jet: c_t D) or battery power [W] (D V/η_tot + P_sys)."""
    D = m.drag(W, V, isa(h).rho)
    if m.prop is not None and is_propeller(m.kind):  # propeller efficiency from the map at this (V, h, T = D)
        eta = max(m.prop.thrust_for(V, h, D)[1]["eta"], 0.05)
        if m.kind == "electric":
            return D * V / (eta * m.eta_tot / m.eta_cruise) + m.P_sys
        return m.c_p * D * V / eta
    if m.kind == "electric":
        return D * V / m.eta_tot + m.P_sys
    if is_propeller(m.kind):
        return m.c_p * D * V / m.eta_cruise + m.auxiliary_fuel_flow_kg_s
    return m.c_t * D


def simulate_mission(m: PerfModel, W0: float, budget: float, legs: list, h_cruise: float, cruise_V: float,
                     loiter_V: float | None, stop: str = "budget", dt: float = 10.0, takeoff_power_time: float = 60.0
                     ) -> MissionSim:
    """Segment-by-segment mission. ``budget`` is the usable fuel [kg] or battery energy [J] for the mission
    (reserves already removed). ``legs`` (sizing MissionLegs) give the required cruise distance and
    loiter time; ``stop='budget'`` stretches the *last* leg until the budget is exhausted (achieved range or
    endurance), ``stop='legs'`` flies the legs as required."""
    electric = m.kind == "electric"
    W, used, segs = W0 * G0, 0.0, []
    # warm-up/take-off
    if electric:
        e = (m.P_sl * m.eta_takeoff / m.eta_tot + m.onboard_power_W) * takeoff_power_time
        segs.append(Segment("descolagem", takeoff_power_time, 0, e, note="1 min potência de descolagem (PRESSUPOSTO)"))
        used += e
    else:
        b = (1 - SEGMENT_FRACTIONS["warmup_takeoff"]) * W0
        segs.append(Segment("aquecimento + descolagem", 0, 0, b, note="Raymer Table 3.2 (0.970)"))
        used += b
        W -= b * G0
    # climb
    h, t, x, burn, vsum = 0.0, 0.0, 0.0, 0.0, 0.0
    while h < h_cruise and used + burn < budget:
        roc, vy = climb_rate(m, W, h)
        if roc <= 0.05:
            break
        dh = min(50.0, h_cruise - h)
        dtc = dh / roc
        if electric:
            r = (m.shaft_power(h, vy) * m.eta_climb / m.eta_tot if m.prop is None else
                 m.shaft_power(h, vy) * m.eta_cruise / m.eta_tot) + m.P_sys
        elif is_propeller(m.kind):
            r = m.c_p * m.shaft_power(h, vy if m.prop is not None else None) + m.auxiliary_fuel_flow_kg_s
        else:
            r = m.c_t * m.T_sl * lapse(m.kind, isa(h).sigma)
        burn += r * dtc
        if not electric:
            W -= r * dtc * G0
        t += dtc
        x += math.sqrt(max(vy**2 - roc**2, 0)) * dtc
        vsum += vy * dtc
        h += dh
    segs.append(Segment("subida (V_y)", t, x, burn, 0, h, vsum / t if t else 0.0,
                        note="potência de subida, integrado (V médio)"))
    used += burn
    h_c = h
    # descent reserve (computed upfront so that cruise/loiter can stop in time)
    LDmax = m.polar().LD_max
    desc_dist = h_c * LDmax
    desc_burn = 0.0 if electric else (1 - SEGMENT_FRACTIONS["landing"]) * W / G0
    rem_legs = list(legs)
    limited = ""
    for k, L in enumerate(rem_legs):
        last = k == len(rem_legs) - 1
        V = cruise_V if L.kind == "cruise" else (loiter_V or L.V)
        t, x, burn = 0.0, 0.0, 0.0
        target = L.value
        while True:
            if not (stop == "budget" and last):
                if (L.kind == "cruise" and x >= target) or (L.kind != "cruise" and t >= target):
                    break
            r = _burn_rate(m, W, V, h_c)
            if used + burn + r * dt + desc_burn > budget:
                limited = "combustível/energia"
                break
            burn += r * dt
            if not electric:
                W -= r * dt * G0
            t += dt
            x += V * dt
            if t > 3600 * 200:
                break
        segs.append(Segment("cruzeiro" if L.kind == "cruise" else "espera (loiter)", t, x, burn, h_c, h_c, V,
                            note="estendido até esgotar o orçamento" if (stop == "budget" and last) else ""))
        used += burn
    # descent
    Vd = math.sqrt(2 * W / (isa(h_c / 2).rho * m.S * m.polar().CL_LDmax))
    td = desc_dist / Vd
    segs.append(Segment("descida (L/D máx, ralenti) + aterragem", td, desc_dist, desc_burn, h_c, 0, Vd,
                        note="Raymer 0.995 (combustível)" if not electric else "planado, energia ≈ 0"))
    used += desc_burn
    rng = sum(s.dist for s in segs)
    end = sum(s.t for s in segs)
    return MissionSim(segs, rng, end, used, budget, electric, limited)


def takeoff_climb_energy(m: PerfModel, W0: float, h_climb: float, takeoff_power_time: float = 60.0) -> dict:
    """Battery energy [J] (electric) or fuel [kg] of the take-off and climb segments, computed with exactly the
    segment model of :func:`simulate_mission` (used by the sizing loop so that the energy fraction and the
    mission verification agree — Phase 3 fix of the Hepperle potential-energy-only climb)."""
    sim = simulate_mission(m, W0, float("inf"), [], h_climb, 1.0, None, takeoff_power_time=takeoff_power_time)
    to, cl = sim.segments[0], sim.segments[1]
    return {"takeoff": to.burn, "climb": cl.burn, "total": to.burn + cl.burn, "h_reached": cl.h1,
            "complete": cl.h1 >= h_climb - 1e-6, "t_climb": cl.t}


def mission_budget(res) -> tuple[float, str]:
    """Usable mission fuel [kg] / battery energy [J] consistent with the sizing reserves."""
    sz = res.sizing
    p = res.spec.assumptions["propulsion"]
    if res.spec.propulsion_kind == "electric":
        E_nom = sz.energy_J
        return E_nom * p["dod"] / (1 + p["energy_reserve"]), (f"E_nom {E_nom / 3600:.0f} Wh × DoD {p['dod']:g} "
                                                               f"/ (1 + reserva {p['energy_reserve']:g})")
    return sz.Wf / 1.06, "Wf / 1.06 (reserva + não utilizável 6 %, Raymer Eq. 3.11)"


def payload_range(res, m: PerfModel | None = None, fuel_capacity_kg: float | None = None,
                  max_payload_kg: float | None = None) -> dict:
    """Payload–range points A–D (Raymer Sec. 17.2) with the segment mission model."""
    m = m or PerfModel.from_result(res)
    sz = res.sizing
    electric = res.spec.propulsion_kind == "electric"
    OEW = sz.We + sz.crew + res.spec.assumptions["weights"].get("fixed_mass_kg", 0.0)
    MTOW = sz.W0
    PL_max = max_payload_kg if max_payload_kg is not None else sz.payload
    cruise = [L for L in res.legs if L.kind == "cruise"] or res.legs
    V, h = cruise[0].V, cruise[0].altitude
    from .weights import MissionLeg
    leg = [MissionLeg("cruise", 1.0, V, cruise[0].LD, h)]
    pts = []
    if electric:
        budget, _ = mission_budget(res)
        for name, pl in (("A", PL_max), ("B (projeto)", sz.payload), ("D (sem payload)", 0.0)):
            W = OEW + sz.Wf + pl
            sim = simulate_mission(m, W, budget, leg, h, V, None)
            pts.append({"ponto": name, "payload_kg": pl, "massa_kg": W, "range_km": sim.range_m / 1e3,
                        "endurance_h": sim.endurance_s / 3600})
        pts.insert(0, {"ponto": "O", "payload_kg": PL_max, "massa_kg": OEW + sz.Wf + PL_max, "range_km": 0.0,
                       "endurance_h": 0.0})
        note = "elétrico: massa de bateria fixa; menos payload → menor massa → mais alcance"
    else:
        cap = fuel_capacity_kg if fuel_capacity_kg is not None else sz.Wf
        rows = [("A", PL_max, 0.0), ("B", PL_max, min(MTOW - OEW - PL_max, cap)),
                ("C", max(MTOW - OEW - cap, 0.0), cap), ("D (ferry)", 0.0, cap)]
        for name, pl, fuel in rows:
            W = OEW + pl + fuel
            if fuel <= 0:
                pts.append({"ponto": name, "payload_kg": pl, "combustível_kg": 0.0, "massa_kg": W, "range_km": 0.0})
                continue
            sim = simulate_mission(m, W, fuel / 1.06, leg, h, V, None)
            pts.append({"ponto": name, "payload_kg": pl, "combustível_kg": fuel, "massa_kg": W,
                        "range_km": sim.range_m / 1e3})
        note = (f"capacidade de combustível {cap:.1f} kg" + (" (= combustível de projeto, PRESSUPOSTO — dar "
                "performance.fuel_capacity_kg)" if fuel_capacity_kg is None else " (utilizador)"))
    return {"points": pts, "note": note, "V": V, "h": h}


def plot_payload_range(pr: dict, path, title: str = ""):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    pts = sorted(pr["points"], key=lambda p: p["range_km"])
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    ax.plot([p["range_km"] for p in pts], [p["payload_kg"] for p in pts], "b-o")
    for p in pts:
        ax.annotate(p["ponto"], (p["range_km"], p["payload_kg"]), fontsize=8, xytext=(4, 4), textcoords="offset points")
    ax.set_xlabel("alcance [km]")
    ax.set_ylabel("payload [kg]")
    ax.set_title(title or "Payload–alcance")
    ax.grid(alpha=0.3)
    ax.text(0.01, 0.02, pr["note"], transform=ax.transAxes, fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def plot_climb(env: dict, path, title: str = ""):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(env["roc"], env["h"], "b-")
    ax.axvline(ROC_SERVICE, color="r", ls="--", lw=1, label="100 ft/min (teto de serviço)")
    ax.set_xlabel("razão de subida máx. [m/s]")
    ax.set_ylabel("h [m]")
    ax.set_xlim(left=0)
    ax.set_title(title or "Subida e tetos (Anderson Cap. 5)")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


@dataclass
class PerformanceResult:
    mission: MissionSim
    mission_required: MissionSim
    envelope: dict
    takeoff: dict
    landing: dict
    payload_range: dict
    budget_note: str
    requirement_compare: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        env = {k: v for k, v in self.envelope.items() if not isinstance(v, np.ndarray)}
        return {"range_km": self.mission.range_m / 1e3, "endurance_h": self.mission.endurance_s / 3600,
                "segments": self.mission.table(), "required_mission_segments": self.mission_required.table(),
                "required_mission_budget_used_fraction": self.mission_required.fuel_or_energy_used
                / self.mission_required.available, "envelope": env, "takeoff": self.takeoff,
                "landing": self.landing, "payload_range": self.payload_range, "budget": self.budget_note,
                "requirements": self.requirement_compare, "notes": self.notes}


def required_mission(res, m: PerfModel | None = None) -> MissionSim:
    """Missão exigida (pernas pedidas, ``stop='legs'``), a mesma tabela que :func:`performance_analysis` guarda em
    ``mission_required``. Não integra o envelope nem a pista."""
    m = m or PerfModel.from_result(res)
    W0 = res.sizing.W0
    budget, _note = mission_budget(res)
    h_c = res.cruise_altitude
    cruise = [L for L in res.legs if L.kind == "cruise"]
    loiter = [L for L in res.legs if L.kind != "cruise"]
    Vc = cruise[0].V if cruise else res.cruise_speed
    Vl = loiter[0].V if loiter else None
    return simulate_mission(m, W0, budget, res.legs, h_c, Vc, Vl, stop="legs")


def performance_analysis(res, opts: dict | None = None) -> PerformanceResult:
    o = {"fuel_capacity_kg": None, "max_payload_kg": None, "mu_brake": 0.4, "approach_angle_deg": 3.0, **(opts or {})}
    m = PerfModel.from_result(res)
    W0 = res.sizing.W0
    budget, bnote = mission_budget(res)
    h_c = res.cruise_altitude
    cruise = [L for L in res.legs if L.kind == "cruise"]
    loiter = [L for L in res.legs if L.kind != "cruise"]
    Vc = cruise[0].V if cruise else res.cruise_speed
    Vl = loiter[0].V if loiter else None
    sim_req = required_mission(res, m)
    sim = simulate_mission(m, W0, budget, res.legs, h_c, Vc, Vl, stop="budget")
    env = flight_envelope(m, W0 * G0, h_max=max(4 * h_c, 9000.0))
    to = takeoff_distance_integrated(m, W0 * G0)
    ld = landing_distance(m, W0 * G0 * res.spec.assumptions["constraints"]["landing_weight_fraction"],
                          mu_brake=o["mu_brake"], gamma_deg=o["approach_angle_deg"])
    pr = payload_range(res, m, o["fuel_capacity_kg"], o["max_payload_kg"])
    reqs = res.spec.requirements
    cmp = []
    last = res.legs[-1].kind if res.legs else None

    def add(key, label, achieved, required, unit, sense="min"):
        if required is None:
            return
        ok = achieved >= required * (1 - 1e-3) if sense == "min" else achieved <= required * (1 + 1e-3)
        cmp.append({"requisito": key, "grandeza": label, "obtido": achieved, "requerido": required, "unidade": unit,
                    "ok": ok})

    rr = reqs.get("range")
    if rr:
        # achieved cruise distance when the required loiter (if any) is also flown
        seg_c = [s for s in (sim.segments if last == "cruise" else sim_req.segments) if s.name == "cruzeiro"]
        add("range", "distância de cruzeiro (segmentos)", seg_c[0].dist / 1e3 if seg_c else 0.0, rr.value / 1e3, "km")
    er = reqs.get("endurance")
    if er:
        seg_l = [s for s in (sim.segments if last != "cruise" else sim_req.segments) if s.name.startswith("espera")]
        add("endurance", "tempo em espera (segmentos)", seg_l[0].t / 3600 if seg_l else 0.0, er.value / 3600, "h")
    h_top = float(env["h"][-1])
    add("service_ceiling", "teto de serviço (Anderson)" + (f" > {h_top:.0f} m (não atingido)"
        if not math.isfinite(env["service_ceiling"]) else ""), min(env["service_ceiling"], h_top),
        reqs.value("service_ceiling"), "m")
    add("climb_rate", "ROC máx. ao nível do mar", env["roc_sl"], reqs.value("climb_rate"), "m/s")
    if reqs.get("takeoff_ground_roll"):
        add("takeoff_ground_roll", "corrida de descolagem (Raymer 17.8)", to["ground_roll"],
            reqs.value("takeoff_ground_roll"), "m", "max")
    if reqs.get("landing_distance"):
        add("landing_distance", "distância de aterragem (Raymer 17.9, total 50 ft)", ld["total_50ft"],
            reqs.value("landing_distance"), "m", "max")
    notes = ["Os resultados de segmentos usam a mesma polar e reservas do dimensionamento; diferenças face aos "
             "requisitos vêm da subida/descida integradas vs. frações históricas (Raymer Table 3.2)."]
    if sim_req.limited_by:
        notes.append("A missão requerida esgota o orçamento antes do fim (ver segmentos).")
    return PerformanceResult(sim, sim_req, env, to, ld, pr, bnote, cmp, notes)
