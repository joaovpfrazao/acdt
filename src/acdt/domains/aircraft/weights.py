"""First-estimate take-off weight sizing (Raymer 6th ed., Ch. 3; Roskam Part I Ch. 2).

Weight equation (Raymer Eq. 3.4):
    W0 = (W_crew + W_payload) / (1 - Wf/W0 - We/W0)

* Empty-weight fraction (initial value of the weight loop): statistical
  regression We/W0 = A * W0^C * Kvs (Raymer Table 3.1, W0 in lb), Nicolai &
  Carichner (2010) Table 5.1 UAV classes, or a fixed fraction from the
  designer's own statistics (``FIXED_EMPTY_FRACTION``, each with its source). Raymer (Sec. 3.3)
  recommends replacing these with the designer's own statistics when
  available -> ``EmptyWeightModel`` accepts a user regression or a fixed
  fraction from company data. The sizing loop then replaces the statistical
  value with the component build-up (``weights_detailed``) and iterates.
* Fuel fraction: mission-segment weight fractions (Raymer Table 3.2 for
  warm-up/take-off, climb, landing), Breguet range/endurance for cruise
  and loiter (Raymer Eqs. 3.5–3.8), 6 % reserve+trapped (Raymer Eq. 3.11).
* Electric aircraft (no weight change in flight): battery mass fraction from
  the electric range/endurance equations of Hepperle, "Electric Flight –
  Potential and Limitations", NATO STO-MP-AVT-209 (2012), Eqs. (5)–(7):
  R = E* eta_tot (1/g) (L/D) (m_bat/m).  Usable energy = DoD * E_nominal.
  Take-off + climb energy: first pass m g h / eta_tot (potential energy only, Hepperle Sec. 3);
  inside the sizing loop it is replaced by the *segment* energy of :func:`performance.takeoff_climb_energy`
  (1 min at take-off power + climb at V_y with climb power, integrated — the same model as the Phase-2
  segment mission), so that sizing and the mission verification use one energy model (Phase 3 fix).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from acdt import G0

LB = 0.45359237

# Raymer 6th ed. Table 3.1: We/W0 = A W0^C Kvs   (W0 in lb)
RAYMER_EMPTY_WEIGHT: dict[str, tuple[float, float]] = {
    "sailplane_unpowered": (0.86, -0.05),
    "sailplane_powered": (0.91, -0.05),
    "homebuilt_metal_wood": (1.19, -0.09),
    "homebuilt_composite": (1.15, -0.09),
    "ga_single_engine": (2.36, -0.18),
    "ga_twin_engine": (1.51, -0.10),
    "agricultural": (0.74, -0.03),
    "twin_turboprop": (0.96, -0.05),
    "flying_boat": (1.09, -0.05),
    "jet_trainer": (1.59, -0.10),
    "jet_fighter": (2.34, -0.13),
    "military_cargo_bomber": (0.93, -0.07),
    "jet_transport": (1.02, -0.06),
    "uav_tactical_recce_ucav": (1.67, -0.16),
    "uav_high_altitude": (2.75, -0.18),
    "uav_small": (0.97, -0.06),
}

# Raymer 6th ed. Table 3.2 historical mission-segment weight fractions
SEGMENT_FRACTIONS = {"warmup_takeoff": 0.970, "climb": 0.985, "landing": 0.995}

# Nicolai & Carichner, *Fundamentals of Aircraft and Airship Design* Vol. I, AIAA 2010, Table 5.1:
# We = A W0^B (both in lb)  ->  We/W0 = A W0^(B-1).
NICOLAI_EMPTY_WEIGHT: dict[str, tuple[float, float]] = {
    "nicolai_uav_prop_endurance_gt12h": (1.66, 0.815),
    "nicolai_uav_prop_endurance_lt12h": (2.18, 0.815),
    "nicolai_uav_turbine_isr": (2.78, 0.815),
    "nicolai_uav_turbine_ucav": (3.53, 0.815),
    "nicolai_cruise_missile_target": (1.78, 0.815),
    "nicolai_light_ga": (0.911, 0.947),
}

# Fixed statistical fractions from the designer's own data (Raymer Sec. 3.3: "use your own statistics when
# available"). Empty by default: acdt ships no unpublished fraction. Each entry the user adds must carry
# ``fraction``, ``range_kg`` (validity, kg) and ``source``.
FIXED_EMPTY_FRACTION: dict[str, dict] = {}

# Former fixed-fraction class names, kept so existing specs still load. Each one now resolves to a published
# regression (Raymer 6th ed. Table 3.1) and its source says so. The fixed value they carried was not
# published and has been removed; to use company statistics, set ``fixed_fraction`` (PRESSUPOSTO, with source)
# or register a ``FIXED_EMPTY_FRACTION`` entry.
EMPTY_FRACTION_ALIASES: dict[str, str] = {
    "uav_gasoline": "uav_tactical_recce_ucav",
    "uav_small_electric": "uav_small",
}

STATISTICAL_SOURCES = {
    "raymer": "Raymer 6th ed. Table 3.1 (We/W0 = A W0^C, W0 in lb)",
    "nicolai": "Nicolai & Carichner (AIAA 2010) Table 5.1 (We = A W0^B, lb)",
}


def statistical_fraction(key: str, W0_kg: float) -> float:
    """We/W0 from any registered statistical class (Raymer, Nicolai, alias, or a user-registered fixed fraction)."""
    W0_lb = W0_kg / LB
    key = EMPTY_FRACTION_ALIASES.get(key, key)
    if key in RAYMER_EMPTY_WEIGHT:
        A, C = RAYMER_EMPTY_WEIGHT[key]
        return A * W0_lb ** C
    if key in NICOLAI_EMPTY_WEIGHT:
        A, B = NICOLAI_EMPTY_WEIGHT[key]
        return A * W0_lb ** (B - 1)
    if key in FIXED_EMPTY_FRACTION:
        return FIXED_EMPTY_FRACTION[key]["fraction"]
    raise KeyError(f"unknown statistical empty-weight class '{key}'")


def statistical_source(key: str) -> str:
    if key in EMPTY_FRACTION_ALIASES:
        target = EMPTY_FRACTION_ALIASES[key]
        return f"{statistical_source(target)} (class '{key}' is an alias of '{target}')"
    if key in RAYMER_EMPTY_WEIGHT:
        return f"{STATISTICAL_SOURCES['raymer']} '{key}'"
    if key in NICOLAI_EMPTY_WEIGHT:
        return f"{STATISTICAL_SOURCES['nicolai']} '{key}'"
    return FIXED_EMPTY_FRACTION[key]["source"]


def statistical_bracket(W0_kg: float, keys: list[str]) -> list[dict]:
    """We/W0 of several statistical classes at the same W0 — for the cross-check table in the report."""
    out = []
    for k in keys:
        f = statistical_fraction(k, W0_kg)
        rng = FIXED_EMPTY_FRACTION.get(k, {}).get("range_kg")
        out.append({"class": k, "We/W0": f, "We_kg": f * W0_kg, "source": statistical_source(k),
                    "in_range": None if rng is None else rng[0] <= W0_kg <= rng[1]})
    return out


# Classes compared in the report for each family (cross-check, not used for sizing)
CROSS_CHECK_CLASSES = {
    "uav": ["uav_small", "uav_tactical_recce_ucav", "nicolai_uav_prop_endurance_lt12h",
            "nicolai_uav_prop_endurance_gt12h"],
    "ga": ["ga_single_engine", "homebuilt_composite", "nicolai_light_ga"],
}

# Raymer 6th ed. Sec. 3.3: empty weight fraction for advanced-composite aircraft ≈ 0.95 x metal statistics
# (applied by the user through ``tech_factor``).


@dataclass
class EmptyWeightModel:
    """We/W0 model. Either a statistical class (Raymer Table 3.1, Nicolai Table 5.1 or a user-registered
    fixed fraction), a user (A, C) regression (W0 in lb, Raymer form) or a fixed
    fraction from the designer's own data."""

    aircraft_class: str = "ga_single_engine"
    A: float | None = None
    C: float | None = None
    fixed_fraction: float | None = None
    Kvs: float = 1.0  # 1.04 variable sweep (Raymer Table 3.1)
    tech_factor: float = 1.0  # user calibration factor (e.g. composites), documented by the user
    label: str | None = None  # overrides source() (e.g. "component build-up, iteration k")
    empty_mass_kg: float | None = None  # We from the component build-up (Class II iteration, Raymer Ch. 15)

    def fraction(self, W0_kg: float) -> float:
        if self.empty_mass_kg is not None:
            # W0 = (Wcrew + Wpayload + We) / (1 - Wf/W0) with We held at the build-up value
            return self.empty_mass_kg / W0_kg
        if self.fixed_fraction is not None:
            return self.fixed_fraction * self.tech_factor
        if self.A is not None:
            return self.A * (W0_kg / LB) ** self.C * self.Kvs * self.tech_factor
        return statistical_fraction(self.aircraft_class, W0_kg) * self.Kvs * self.tech_factor

    def source(self) -> str:
        if self.label:
            return self.label
        if self.fixed_fraction is not None:
            return f"fixed We/W0 = {self.fixed_fraction:.3f} (designer statistics, Raymer Sec. 3.3)"
        if self.A is not None:
            return f"user regression We/W0 = {self.A} W0^{self.C} (Raymer Sec. 3.3 form)"
        return statistical_source(self.aircraft_class)


# --- Breguet (fuel-burning) -------------------------------------------------
def breguet_range_fraction_prop(R: float, LD: float, eta_p: float, c_p: float) -> float:
    """Cruise weight fraction Wi/Wi-1 for propeller aircraft (Raymer Eq. 3.6, SI form).

    R [m], c_p power-specific fuel consumption [kg/(W s)] (= BSFC), eta_p propeller efficiency.
    R = eta_p/(c_p g) * L/D * ln(Wi-1/Wi).
    """
    return math.exp(-R * c_p * G0 / (eta_p * LD))


def breguet_range_fraction_jet(R: float, V: float, LD: float, c_t: float) -> float:
    """Jet cruise fraction (Raymer Eq. 3.5): R = V/(c_t g) * L/D * ln(Wi-1/Wi); c_t [kg/(N s)]."""
    return math.exp(-R * c_t * G0 / (V * LD))


def breguet_endurance_fraction_prop(E: float, V: float, LD: float, eta_p: float, c_p: float) -> float:
    """Loiter fraction, propeller (Raymer Eq. 3.8 with c_t = c_p V / eta_p)."""
    return math.exp(-E * V * c_p * G0 / (eta_p * LD))


def breguet_endurance_fraction_jet(E: float, LD: float, c_t: float) -> float:
    """Loiter fraction, jet (Raymer Eq. 3.7): E = (1/(c_t g)) L/D ln(Wi-1/Wi)."""
    return math.exp(-E * c_t * G0 / LD)


# --- Electric (Hepperle 2012) -----------------------------------------------
def electric_energy_cruise(m: float, R: float, LD: float, eta_tot: float) -> float:
    """Battery energy [J] to fly range R at constant L/D: E = m g R / (eta_tot L/D)  (Hepperle Eq. 5)."""
    return m * G0 * R / (eta_tot * LD)


def electric_energy_loiter(m: float, t: float, V: float, LD: float, eta_tot: float) -> float:
    """Battery energy [J] to loiter time t at speed V: P = m g V /(L/D) / eta_tot (Hepperle Eq. 6)."""
    return m * G0 * V * t / (eta_tot * LD)


def electric_energy_climb(m: float, h: float, eta_tot: float) -> float:
    """Potential-energy share of climb to altitude h (Hepperle Sec. 3)."""
    return m * G0 * h / eta_tot


@dataclass
class MissionLeg:
    kind: str  # "cruise" | "loiter"
    value: float  # range [m] or time [s]
    V: float  # TAS [m/s]
    LD: float
    altitude: float = 0.0


@dataclass
class PropulsionData:
    kind: str = "piston_prop"  # electric | piston_prop | turboprop | jet
    eta_p: float = 0.80  # cruise propeller efficiency (Raymer Sec. 3.4: ~0.8)
    c_p: float | None = None  # BSFC [kg/(W s)]; default 0.4 lb/(hp h) piston cruise, 0.5 turboprop (Raymer Table 3.4)
    c_t: float = 0.5 / 3600 / G0  # jet TSFC [kg/(N s)]
    # electric chain
    e_spec: float = 200 * 3600  # pack specific energy [J/kg]
    eta_tot: float = 0.70  # battery->thrust (eta_bat*eta_esc*eta_motor*eta_prop)
    dod: float = 0.80  # usable depth of discharge
    energy_reserve: float = 0.20  # fraction of mission energy kept as reserve
    systems_power: float = 0.0  # avionics + payload electric power drawn from the main battery [W]
    # take-off + climb battery energy per kg of take-off mass [J/kg] from the segment model
    # (performance.takeoff_climb_energy); None -> Hepperle potential-energy estimate m g h / eta_tot
    takeoff_climb_J_per_kg: float | None = None

    auxiliary_fuel_flow_kg_s: float = 0.0
    auxiliary_pre_s: float = 0.0
    auxiliary_post_s: float = 0.0

    def __post_init__(self):
        for k in ("auxiliary_fuel_flow_kg_s","auxiliary_pre_s","auxiliary_post_s"):
            v=getattr(self,k)
            if not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) or v<0: raise ValueError(k+" must be finite nonnegative")
        if self.auxiliary_fuel_flow_kg_s and self.kind not in ("piston_prop","turboprop"):
            raise ValueError("auxiliary fuel hook requires thermal prop")
        if self.c_p is None:
            bsfc = 0.5 if self.kind == "turboprop" else 0.4  # lb/(hp h), Raymer Table 3.4 cruise
            self.c_p = bsfc * LB / (745.69987 * 3600)


@dataclass
class SizingResult:
    W0: float  # kg
    We: float
    Wf: float  # fuel or battery mass
    payload: float
    crew: float
    empty_fraction: float
    fuel_fraction: float
    converged: bool
    message: str = ""
    energy_J: float | None = None
    legs: list = field(default_factory=list)


class AuxiliaryFuelExhausted(ValueError):
    """Trial mass cannot survive the supplied constant accessory fuel demand."""


def fuel_fraction(legs: list[MissionLeg], prop: PropulsionData, reserve: float = 0.06, initial_mass_kg: float | None = None) -> float:
    """Wf/W0 for fuel-burning aircraft: product of segment fractions (Raymer Sec. 3.4),
    plus 6 % reserve/trapped (Raymer Eq. 3.11)."""
    if prop.auxiliary_fuel_flow_kg_s:
        # Raymer/Breguet dm/dt=-a*m-b; exact linear ODE for explicit constant
        # auxiliary flow b. No empirical engine formula: b is supplied BSFC*shaft
        # extraction. Pre/post phase durations are explicit user inputs.
        if initial_mass_kg is None or initial_mass_kg<=0: raise ValueError("auxiliary fuel needs positive initial mass")
        b=prop.auxiliary_fuel_flow_kg_s
        mass=initial_mass_kg*SEGMENT_FRACTIONS["warmup_takeoff"]*SEGMENT_FRACTIONS["climb"]-b*prop.auxiliary_pre_s
        for leg in legs:
            dt=leg.value/leg.V if leg.kind=="cruise" else leg.value
            a=G0*leg.V*prop.c_p/(prop.eta_p*leg.LD)
            mass=mass*math.exp(-a*dt)-b*(-math.expm1(-a*dt))/a if a else mass-b*dt
        mass=mass*SEGMENT_FRACTIONS["landing"]-b*prop.auxiliary_post_s
        if mass<=0: raise AuxiliaryFuelExhausted("auxiliary fuel exhausts positive mass")
        return (1+reserve)*(1-mass/initial_mass_kg)
    f = SEGMENT_FRACTIONS["warmup_takeoff"] * SEGMENT_FRACTIONS["climb"]
    for L in legs:
        if L.kind == "cruise":
            if prop.kind == "jet":
                f *= breguet_range_fraction_jet(L.value, L.V, L.LD, prop.c_t)
            else:
                f *= breguet_range_fraction_prop(L.value, L.LD, prop.eta_p, prop.c_p)
        else:
            if prop.kind == "jet":
                f *= breguet_endurance_fraction_jet(L.value, L.LD, prop.c_t)
            else:
                f *= breguet_endurance_fraction_prop(L.value, L.V, L.LD, prop.eta_p, prop.c_p)
    f *= SEGMENT_FRACTIONS["landing"]
    return (1 + reserve) * (1 - f)


def battery_energy(m: float, legs: list[MissionLeg], prop: PropulsionData, climb_alt: float) -> float:
    """Nominal battery energy [J] incl. reserve and DoD (Hepperle 2012 Eqs. 5–7). Take-off + climb from the
    segment model when ``prop.takeoff_climb_J_per_kg`` is set, else the potential-energy estimate."""
    if prop.takeoff_climb_J_per_kg is not None:
        E = m * prop.takeoff_climb_J_per_kg
    else:
        E = electric_energy_climb(m, climb_alt, prop.eta_tot)
    t_total = 0.0
    for L in legs:
        if L.kind == "cruise":
            E += electric_energy_cruise(m, L.value, L.LD, prop.eta_tot)
            t_total += L.value / L.V
        else:
            E += electric_energy_loiter(m, L.value, L.V, L.LD, prop.eta_tot)
            t_total += L.value
    E += prop.systems_power * t_total  # avionics/payload drawn from the same pack (power budget)
    return E * (1 + prop.energy_reserve) / prop.dod


def size_takeoff_weight(payload: float, crew: float, legs: list[MissionLeg], prop: PropulsionData,
                        ew: EmptyWeightModel, climb_alt: float = 0.0, W0_guess: float | None = None,
                        fixed_mass: float = 0.0) -> SizingResult:
    """Solve Raymer Eq. 3.4 for W0 [kg] by bisection on the residual
    W0 - (payload+crew+fixed)/(1 - We/W0 - Wf/W0)."""

    def fractions(W0):
        we = ew.fraction(W0)
        if prop.kind == "none":         # sem propulsão (planador): sem combustível nem bateria de propulsão
            return we, 0.0, None
        if prop.kind == "electric":
            wf = battery_energy(W0, legs, prop, climb_alt) / prop.e_spec / W0
            E = wf * W0 * prop.e_spec
        else:
            try:
                wf = fuel_fraction(legs, prop, initial_mass_kg=W0)
            except AuxiliaryFuelExhausted:
                # Root-domain sentinel ONLY: this trial is below the physical
                # domain. Let bisection move upward; never return it as a mass.
                wf = math.inf
            E = None
        return we, wf, E

    def residual(W0):
        we, wf, _ = fractions(W0)
        den = 1 - we - wf
        if den <= 0:
            return -1e12
        return W0 - (payload + crew + fixed_mass) / den

    lo, hi = max(payload + crew + fixed_mass, 1e-3) * 1.0001, 1e6
    if residual(hi) < 0:
        we, wf, _ = fractions(hi)
        return SizingResult(math.nan, math.nan, math.nan, payload, crew, we, wf, False,
                            f"No closure: We/W0 ({we:.3f}) + Wf/W0 ({wf:.3f}) >= 1 — requirements infeasible "
                            "with current technology assumptions (energy/fuel or empty-weight fraction too high).")
    for _ in range(200):
        mid = math.sqrt(lo * hi)
        if residual(mid) < 0:
            lo = mid
        else:
            hi = mid
        if hi / lo - 1 < 1e-10:
            break
    W0 = hi
    we, wf, E = fractions(W0)
    return SizingResult(W0, we * W0, wf * W0, payload, crew, we, wf, True, "", E, legs)
