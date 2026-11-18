"""Component (group) weight build-up — "Class II" estimate that closes the weight loop.

The statistical We/W0 (``weights.EmptyWeightModel``) is only the *initial* value.
Once the MDA loop has a geometry, every group is estimated here and the new
empty weight replaces the statistical one; the aircraft is re-sized until W0,
We and CD0 stop changing (``sizing.run``). Classical methods only:

* Structure and propulsion/equipment groups: Raymer, *Aircraft Design: A
  Conceptual Approach*, 6th ed., Sec. 15.3.3 "General aviation weights",
  Eqs. 15.46–15.59 (imperial units: lb, ft, ft², lb/ft², gal). Implemented in
  the ``raymer_ga_*`` functions exactly as published; conversion to SI is done
  only at the interface.
* Advanced-composite reduction factors: Raymer 6th ed. Sec. 15.4 (Table 15.4):
  wing 0.85–0.90, tails 0.83–0.88, fuselage/nacelle 0.90–0.95, landing gear
  0.95–1.00. The *mean* of each range is applied when ``material: composite``.
* Ultimate load factor Nz = 1.5 x limit (Raymer Sec. 14.2 / CS-23 safety factor).
  Default limit load factor: CS-23 / 14 CFR 23.337 (pre-amendment 23-64) normal
  category n = 2.1 + 24000/(W+10000) (W in lb), need not exceed 3.8; utility 4.4;
  aerobatic 6.0.
* UAV adaptations (where the GA equations do not apply): propulsion, servos,
  autopilot/avionics and harness come from the *selected systems* (Phase 1E,
  ``systems_integration``) — real component masses from the database — and
  the power-harness mass from the sized wire gauges (copper density IEC 60028).
  Raymer's furnishings, hydraulics, electrical and air-conditioning equations
  are switched off for UAVs (they are correlations for manned cabins).
* User-listed items (recovery parachute, payload mount, paint, signal wiring...)
  and a growth/integration allowance are explicit, labelled assumptions.
* Per-group ``calibration`` factors let the designer fit the build-up to
  company data (Raymer Sec. 15.4: "fudge factors").

Limitations (also printed in the report): Raymer's GA equations are
regressions of manned aircraft (~1000–8000 lb); applied to a 25 kg UAV they are
an extrapolation. Gundlach, *Designing Unmanned Aircraft Systems* (AIAA, 2nd
ed. 2014) gives UAV-specific mass methods, but the book was not available to
verify coefficients, so none are implemented (no un-verified equations).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


LB = 0.45359237
FT = 0.3048
GAL = 3.785411784e-3  # m^3 (US gallon)
PSF = 47.880259  # Pa

# Raymer 6th ed. Sec. 15.4 (Table 15.4), advanced composites: (low, high) of the range
COMPOSITE_FACTORS: dict[str, tuple[float, float]] = {
    "wing": (0.85, 0.90), "htail": (0.83, 0.88), "vtail": (0.83, 0.88),
    "fuselage": (0.90, 0.95), "landing_gear": (0.95, 1.00), "nacelle": (0.90, 0.95),
}

STRUCTURAL_LIMIT_N = {"utility": 4.4, "aerobatic": 6.0}

# PRESSUPOSTO: Raymer Eq. 15.50 takes the strut length as an input and does not give this default.
DEFAULT_MAIN_GEAR_LENGTH_M = 0.60

DEFAULT_COMPONENT_OPTIONS: dict = {
    "structural_category": "normal",   # normal | utility | aerobatic (CS-23 / 14 CFR 23.337)
    "limit_load_factor": None,         # overrides the category value
    "material": "metal",               # metal | composite (Raymer Table 15.4 factors)
    "min_areal_density_kg_m2": None,  # minimum-gauge floor for skins: m >= Swet x areal density of the
                                       #   lightest buildable laminate/sandwich (USER, from the layup)
    "landing_gear": "tricycle",        # tricycle | taildragger | none (catapult/parachute/net)
    "gear_load_factor": 3.0,           # Ngear (Raymer Table 11.5, GA); Nl = 1.5 Ngear
    "main_gear_length_m": DEFAULT_MAIN_GEAR_LENGTH_M,  # PRESSUPOSTO, see above
    "nose_gear_length_m": 0.50,
    "landing_weight_fraction": 0.95,   # Wl / W0 (assumption)
    "fuel_in_wing_fraction": 1.0,      # share of fuel in wing tanks (Wfw)
    "fuel_density_kg_L": 0.72,         # avgas typical (assumption)
    "integral_tank_fraction": 0.0,     # Vi/Vt (Raymer Eq. 15.53)
    "n_tanks": 2,
    "engine_dry_mass_kg": None,        # from engine datasheet / TCDS (preferred)
    "engine_kW_per_kg": 1.0,           # fallback: dry piston engine specific power (ASSUMPTION)
    "electric_kW_per_kg": 3.0,         # fallback without systems: motor+ESC specific power (ASSUMPTION)
    "propeller_mass_kg": None,         # electric/UAV propeller (datasheet); None -> not counted
    "avionics_uninstalled_kg": None,   # Wuav for Raymer Eq. 15.57 (manned); None -> 15 kg (ASSUMPTION)
    "n_occupants": None,               # Np for Eq. 15.58; None -> from crew+payload/90 kg
    "include": {},                     # override group switches: furnishings, hydraulics, electrical,
                                       #   air_conditioning_anti_ice, flight_controls, fuel_system
    "hydraulics_Kh": 0.013,            # Raymer Eq. 15.55: 0.013 light plane, hydraulic brakes only
    "harness_insulation_factor": 1.3,  # ASSUMPTION (wire datasheet)
    "connector_mass_kg": 0.01,         # ASSUMPTION per connector (datasheet)
    "items": [],                       # [{name, mass_kg, group}] user-listed equipment
    "growth_allowance": 0.0,           # fraction of the computed empty weight (ASSUMPTION, labelled)
    "calibration": {},                 # {item_key: factor} fitted to company data
}


# ---- Raymer 6th ed. Eqs. 15.46–15.59 (GA), imperial units ------------------------------------
def raymer_ga_wing(Sw, Wfw, A, sweep, q, taper, tc, Nz, Wdg):
    """Eq. 15.46 [lb]. Sw ft², Wfw lb (if 0, Wfw^0.0035 := 1), sweep rad (c/4), q psf."""
    c = math.cos(sweep)
    fw = Wfw ** 0.0035 if Wfw > 0 else 1.0
    return (0.036 * Sw**0.758 * fw * (A / c**2) ** 0.6 * q**0.006 * taper**0.04
            * (100 * tc / c) ** -0.3 * (Nz * Wdg) ** 0.49)


def raymer_ga_htail(Sht, A_ht, sweep_ht, q, taper_ht, tc, Nz, Wdg):
    """Eq. 15.47 [lb]. A is taken as the tail's own aspect ratio (as in SUAVE's implementation)."""
    c = math.cos(sweep_ht)
    return (0.016 * (Nz * Wdg) ** 0.414 * q**0.168 * Sht**0.896 * (100 * tc / c) ** -0.12
            * (A_ht / c**2) ** 0.043 * taper_ht**-0.02)


def raymer_ga_vtail(Svt, A_vt, sweep_vt, q, taper_vt, tc, Nz, Wdg, Ht_Hv=0.0):
    """Eq. 15.48 [lb]. Ht/Hv = 0 conventional tail, 1 T-tail."""
    c = math.cos(sweep_vt)
    return (0.073 * (1 + 0.2 * Ht_Hv) * (Nz * Wdg) ** 0.376 * q**0.122 * Svt**0.873
            * (100 * tc / c) ** -0.49 * (A_vt / c**2) ** 0.357 * taper_vt**0.039)


def raymer_ga_fuselage(Sf, Nz, Wdg, Lt, L, D, q, W_press=0.0):
    """Eq. 15.49 [lb]. Sf wetted ft², Lt tail arm ft, L structural length ft, D depth ft."""
    return 0.052 * Sf**1.086 * (Nz * Wdg) ** 0.177 * Lt**-0.051 * (L / D) ** -0.072 * q**0.241 + W_press


def raymer_ga_main_gear(Nl, Wl, Lm_in):
    """Eq. 15.50 [lb]. Lm main-gear length in inches."""
    return 0.095 * (Nl * Wl) ** 0.768 * (Lm_in / 12) ** 0.409


def raymer_ga_nose_gear(Nl, Wl, Ln_in):
    """Eq. 15.51 [lb]."""
    return 0.125 * (Nl * Wl) ** 0.566 * (Ln_in / 12) ** 0.845


def raymer_ga_installed_engine(Wen, Nen=1):
    """Eq. 15.52 [lb]: engine + propeller + mounts/cowl/accessories. Wen = dry engine weight lb (each)."""
    return 2.575 * Wen**0.922 * Nen


def raymer_ga_fuel_system(Vt, Vi, Nt, Nen=1):
    """Eq. 15.53 [lb]. Vt total, Vi integral tank volume [US gal]."""
    if Vt <= 0:
        return 0.0
    return 2.49 * Vt**0.726 * (1 / (1 + Vi / Vt)) ** 0.363 * Nt**0.242 * Nen**0.157


def raymer_ga_flight_controls(L, B, Nz, Wdg):
    """Eq. 15.54 [lb]. L fuselage length ft, B span ft."""
    return 0.053 * L**1.536 * B**0.371 * (Nz * Wdg * 1e-4) ** 0.80


def raymer_ga_hydraulics(Kh, Wdg, M):
    """Eq. 15.55 [lb]: Kh = 0.05 low subsonic (brakes+retracts), 0.11 medium subsonic (flaps),
    0.12 high subsonic (hydraulic flight controls), 0.013 light plane with hydraulic brakes (use M = 0.1)."""
    return Kh * Wdg**0.8 * M**0.5


def raymer_ga_electrical(W_fuel_sys, W_avionics):
    """Eq. 15.56 [lb]."""
    return 12.57 * (W_fuel_sys + W_avionics) ** 0.51


def raymer_ga_avionics(W_uav):
    """Eq. 15.57 [lb]: installed avionics from uninstalled avionics weight W_uav [lb]."""
    return 2.117 * W_uav**0.933


def raymer_ga_air_conditioning(Wdg, Np, W_av, M):
    """Eq. 15.58 [lb]: air conditioning and anti-icing."""
    return 0.265 * Wdg**0.52 * Np**0.68 * W_av**0.17 * M**0.08


def raymer_ga_furnishings(Wdg):
    """Eq. 15.59 [lb]."""
    return max(0.0582 * Wdg - 65, 0.0)


def limit_load_factor(W0_kg: float, category: str = "normal") -> float:
    """CS-23 / 14 CFR 23.337 (pre-amdt 23-64): normal n = 2.1 + 24000/(W+10000) <= 3.8 (W lb, need not
    exceed 3.8); utility 4.4; aerobatic 6.0."""
    if category in STRUCTURAL_LIMIT_N:
        return STRUCTURAL_LIMIT_N[category]
    W = W0_kg / LB
    return min(2.1 + 24000 / (W + 10000), 3.8)


# ---- data model ------------------------------------------------------------------------------
@dataclass
class WeightItem:
    key: str
    group: str  # structure | propulsion | equipment | user_items | allowance
    name: str
    mass: float  # kg
    method: str


@dataclass
class WeightBreakdown:
    W0: float
    items: list[WeightItem] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    Nz: float = math.nan

    @property
    def empty(self) -> float:
        return sum(i.mass for i in self.items)

    def group_total(self, group: str) -> float:
        return sum(i.mass for i in self.items if i.group == group)

    @property
    def groups(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for i in self.items:
            out[i.group] = out.get(i.group, 0.0) + i.mass
        return out

    def table(self) -> list[dict]:
        return [{"grupo": i.group, "item": i.name, "kg": i.mass, "% W0": 100 * i.mass / self.W0,
                 "método": i.method} for i in self.items]


def _merge_opts(opts: dict | None) -> dict:
    o = {**DEFAULT_COMPONENT_OPTIONS, **(opts or {})}
    o["include"] = {**(opts or {}).get("include", {})}
    return o


def component_weights(W0: float, Wf: float, kind: str, config, q_cruise_Pa: float, mach: float,
                      power_sl_W: float | None, opts: dict | None = None, uas: bool = False,
                      systems=None, n_engines: int = 1, occupants_mass: float = 0.0) -> WeightBreakdown:
    """Empty-weight build-up [kg] for take-off mass W0 [kg] and fuel/battery mass Wf [kg].

    ``systems`` (optional) is a ``systems_integration.SystemsResult`` from the previous closure
    iteration: its selected motor/ESC/servo/autopilot masses and the sized harness replace the
    statistical equipment equations.
    """
    o = _merge_opts(opts)
    inc = {"furnishings": not uas, "hydraulics": not uas, "electrical": not uas,
           "air_conditioning_anti_ice": False, "flight_controls": True, "fuel_system": kind != "electric",
           **o["include"]}
    cal = o["calibration"]
    bd = WeightBreakdown(W0)
    composite = o["material"] == "composite"

    rho_min = o["min_areal_density_kg_m2"]

    def add(key, group, name, mass_kg, method, comp_key=None, swet=None):
        f = cal.get(key, 1.0)
        if rho_min and swet:
            floor = rho_min * swet
            if floor > mass_kg * f * (0.5 * sum(COMPOSITE_FACTORS[comp_key]) if composite and comp_key else 1):
                bd.items.append(WeightItem(key, group, name, floor,
                                           f"minimum gauge: Swet {swet:.3f} m² x {rho_min:g} kg/m² (user layup) "
                                           f"> {method}"))
                return
        if composite and comp_key:
            lo, hi = COMPOSITE_FACTORS[comp_key]
            f *= 0.5 * (lo + hi)
            method += f"; composite x{0.5 * (lo + hi):.3f} (Raymer Table 15.4)"
        if key in cal:
            method += f"; calibration x{cal[key]:g} (user)"
        bd.items.append(WeightItem(key, group, name, mass_kg * f, method))

    n_lim = o["limit_load_factor"] or limit_load_factor(W0, o["structural_category"])
    Nz = 1.5 * n_lim
    bd.Nz = Nz
    Wdg = W0 / LB
    q = q_cruise_Pa / PSF
    w, fus, ht, vt = config.wing, config.fuselage, config.htail, config.vtail
    Wfw = (Wf / LB) * o["fuel_in_wing_fraction"] if kind != "electric" else 0.0

    # ---- structure ----
    add("wing", "structure", "asa", LB * raymer_ga_wing(w.S / FT**2, Wfw, w.AR, w.sweep_c4, q, w.taper,
                                                       w.tc_mean, Nz, Wdg), "Raymer Eq. 15.46", "wing",
        w.wetted_area(fus.max_diameter))
    add("htail", "structure", "empenagem horizontal",
        LB * raymer_ga_htail(ht.S / FT**2, ht.AR, ht.sweep_c4, q, ht.taper, ht.tc, Nz, Wdg),
        "Raymer Eq. 15.47", "htail", ht.as_wing().wetted_area())
    add("vtail", "structure", "empenagem vertical",
        LB * raymer_ga_vtail(vt.S / FT**2, vt.AR, vt.sweep_c4, q, vt.taper, vt.tc, Nz, Wdg),
        "Raymer Eq. 15.48", "vtail", vt.as_wing().wetted_area())
    add("fuselage", "structure", "fuselagem",
        LB * raymer_ga_fuselage(fus.wetted_area() / FT**2, Nz, Wdg, ht.arm / FT, fus.length / FT,
                                fus.max_diameter / FT, q), "Raymer Eq. 15.49 (unpressurized)", "fuselage",
        fus.wetted_area())
    gear = o["landing_gear"]
    if gear != "none":
        Nl = 1.5 * o["gear_load_factor"]
        Wl = o["landing_weight_fraction"] * Wdg
        add("main_gear", "structure", "trem principal",
            LB * raymer_ga_main_gear(Nl, Wl, o["main_gear_length_m"] / 0.0254), "Raymer Eq. 15.50", "landing_gear")
        add("nose_gear", "structure", "trem de nariz" if gear == "tricycle" else "roda de cauda",
            LB * raymer_ga_nose_gear(Nl, Wl, o["nose_gear_length_m"] / 0.0254)
            * (1.0 if gear == "tricycle" else 0.5),
            "Raymer Eq. 15.51" + ("" if gear == "tricycle" else " x0.5 tailwheel (ASSUMPTION)"), "landing_gear")
    else:
        bd.notes.append("Sem trem de aterragem (landing_gear: none) — lançamento/recuperação como itens do utilizador.")

    # ---- propulsion ----
    sys_items = {m.name: m.mass for m in (systems.masses if systems is not None else [])}
    W_fuel_sys_lb = 0.0
    if kind == "electric":
        mot = sum(v for k, v in sys_items.items() if k.startswith(("motor", "ESC")))
        if mot > 0:
            add("motor_esc", "propulsion", "motor(es) + ESC(s)", mot, "selected components (Phase 1E database)")
        elif power_sl_W:
            add("motor_esc", "propulsion", "motor(es) + ESC(s)", power_sl_W / 1e3 / o["electric_kW_per_kg"],
                f"P_SL / {o['electric_kW_per_kg']} kW/kg (ASSUMPTION — run systems selection)")
        if o["propeller_mass_kg"]:
            add("propeller", "propulsion", "hélice(s)", o["propeller_mass_kg"] * n_engines, "user (datasheet)")
        else:
            bd.notes.append("Massa da hélice não incluída (propeller_mass_kg não definido).")
    elif kind in ("piston_prop", "turboprop"):
        Wen = o["engine_dry_mass_kg"]
        meth = "Raymer Eq. 15.52, Wen from engine datasheet (user)"
        if Wen is None:
            Wen = (power_sl_W or 0) / n_engines / 1e3 / o["engine_kW_per_kg"]
            meth = f"Raymer Eq. 15.52, Wen = P/{o['engine_kW_per_kg']} kW/kg (ASSUMPTION — give engine_dry_mass_kg)"
        add("engine_installed", "propulsion", "motor instalado (+hélice, berço, capota)",
            LB * raymer_ga_installed_engine(Wen / LB, n_engines), meth)
        if inc["fuel_system"] and Wf > 0:
            Vt = Wf / o["fuel_density_kg_L"] / 1e3 / GAL
            W_fuel_sys_lb = raymer_ga_fuel_system(Vt, o["integral_tank_fraction"] * Vt, o["n_tanks"], n_engines)
            add("fuel_system", "propulsion", "sistema de combustível", LB * W_fuel_sys_lb, "Raymer Eq. 15.53")
    else:
        bd.notes.append(f"Propulsão '{kind}': equações GA não aplicáveis — usar estatística (Fase 3: Raymer 15.3.1).")

    # ---- equipment ----
    if inc["flight_controls"]:
        add("flight_controls", "equipment", "comandos de voo (cabos/hastes)" if not uas else "comandos (hastes/charneiras)",
            LB * raymer_ga_flight_controls(fus.length / FT, w.span / FT, Nz, Wdg), "Raymer Eq. 15.54")
    servo = sum(v for k, v in sys_items.items() if k.startswith("servo"))
    if servo:
        add("servos", "equipment", "servos", servo, "selected components (Phase 1E)")
    if inc["hydraulics"]:
        add("hydraulics", "equipment", "hidráulica", LB * raymer_ga_hydraulics(o["hydraulics_Kh"], Wdg, 0.1),
            f"Raymer Eq. 15.55 (Kh={o['hydraulics_Kh']}, M=0.1)")
    W_av_lb = 0.0
    if uas:
        av = sum(v for k, v in sys_items.items()
                 if not k.startswith(("motor", "ESC", "servo", "battery")))
        if av:
            add("avionics", "equipment", "autopiloto + aviónica + extras", av, "selected components / user list")
        elif o["avionics_uninstalled_kg"] is not None:
            add("avionics", "equipment", "aviónica (piloto automático, datalink, ...)", o["avionics_uninstalled_kg"],
                "user (uninstalled mass; installation items listed separately)")
        else:
            bd.notes.append("Aviónica do UAV não modelada (correr seleção de sistemas ou listar em items).")
    else:
        Wuav = o["avionics_uninstalled_kg"] if o["avionics_uninstalled_kg"] is not None else 15.0
        W_av_lb = raymer_ga_avionics(Wuav / LB)
        add("avionics", "equipment", "aviónica instalada", LB * W_av_lb,
            "Raymer Eq. 15.57, Wuav " + (f"{Wuav:g} kg (user)" if o["avionics_uninstalled_kg"] is not None
                                         else "15 kg (ASSUMPTION — basic VFR panel)"))
    if inc["electrical"]:
        add("electrical", "equipment", "sistema elétrico", LB * raymer_ga_electrical(W_fuel_sys_lb, W_av_lb),
            "Raymer Eq. 15.56")
    if systems is not None and getattr(systems, "harness", None) is not None:
        hm = systems.harness.mass(o["harness_insulation_factor"], o["connector_mass_kg"])
        add("harness", "equipment", "cablagem de potência", hm,
            f"sized wire gauges x length x ρCu (IEC 60028) x{o['harness_insulation_factor']} insulation "
            f"+ {len(systems.harness.connectors)} connectors x {o['connector_mass_kg']} kg (ASSUMPTIONS)")
    if inc["air_conditioning_anti_ice"]:
        Np = o["n_occupants"] or max(1, round(occupants_mass / 90))
        add("air_conditioning", "equipment", "ar condicionado / anti-gelo",
            LB * raymer_ga_air_conditioning(Wdg, Np, max(W_av_lb, 1.0), mach), "Raymer Eq. 15.58")
    if inc["furnishings"]:
        add("furnishings", "equipment", "interiores (bancos, cintos...)", LB * raymer_ga_furnishings(Wdg),
            "Raymer Eq. 15.59")

    # ---- user items + allowance ----
    for it in o["items"]:
        add(f"item:{it['name']}", it.get("group", "user_items"), it["name"], float(it["mass_kg"]),
            it.get("source", "user-listed item"))
    if o["growth_allowance"]:
        base = bd.empty
        bd.items.append(WeightItem("growth", "allowance", "margem de crescimento/integração",
                                   o["growth_allowance"] * base,
                                   f"{o['growth_allowance']:.0%} of the build-up (ASSUMPTION, labelled)"))
    if W0 < 1000 * LB:
        bd.notes.append(f"W0 = {W0:.0f} kg está abaixo da base de dados das equações GA de Raymer (~1000–8000 lb): "
                        "extrapolação — calibrar com dados próprios (calibration).")
    return bd


def raymer_component_weights_ga(*args, **kwargs):
    """Backward-compatible name for :func:`component_weights` (Raymer 6th ed. Eqs. 15.46–15.59)."""
    return component_weights(*args, **kwargs)


def roskam_usaf_wing(W_to_lb, n_ult, A, sweep_c4, S_ft2, taper, tc, VH_kt):
    """USAF method, light/utility airplanes ≤ ~300 kt (Roskam Part V Eq. 5.4, as printed: (A/cos Λ¼)^0.57) [lb].
    V_H = max level speed at sea level [kt]."""
    return 96.948 * ((W_to_lb * n_ult / 1e5) ** 0.65 * (A / math.cos(sweep_c4)) ** 0.57 * (S_ft2 / 100) ** 0.61
                     * ((1 + taper) / (2 * tc)) ** 0.36 * (1 + VH_kt / 500) ** 0.5) ** 0.993


def roskam_cessna_wing(W_to_lb, n_ult, A, S_ft2):
    """Cessna method, cantilever wing, V_max < 200 kt (Roskam Part V Eq. 5.2; includes tip fairing and control
    surfaces, excludes fuel tanks and carry-through) [lb]."""
    return 0.04674 * W_to_lb**0.397 * S_ft2**0.360 * n_ult**0.397 * A**1.712


def roskam_usaf_htail(W_to_lb, n_ult, Sh_ft2, lh_ft, bh_ft, trh_ft):
    """USAF method (Roskam Part V Eq. 5.14); l_h tail arm, b_h span, t_rh max root thickness [ft] → [lb]."""
    return 127 * ((W_to_lb * n_ult / 1e5) ** 0.87 * (Sh_ft2 / 100) ** 1.2 * 0.289 * (lh_ft / 10) ** 0.483
                  * (bh_ft / trh_ft) ** 0.5) ** 0.458


def roskam_usaf_vtail(W_to_lb, n_ult, Sv_ft2, bv_ft, trv_ft):
    """USAF method (Roskam Part V Eq. 5.15); b_v fin height, t_rv max root thickness [ft] → [lb]."""
    return 98.5 * ((W_to_lb * n_ult / 1e5) ** 0.87 * (Sv_ft2 / 100) ** 1.2 * 0.289 * (bv_ft / trv_ft) ** 0.5) ** 0.458


def roskam_cessna_htail(W_to_lb, Sh_ft2, Ah, trh_ft):
    """Cessna method, V_max < 200 kt (Roskam Part V Eq. 5.12) [lb]."""
    return 3.184 * W_to_lb**0.887 * Sh_ft2**0.101 * Ah**0.138 / (57.5 * trh_ft**0.223)


def roskam_cessna_vtail(W_to_lb, Sv_ft2, Av, trv_ft, sweep_c4_v):
    """Cessna method, V_max < 200 kt (Roskam Part V Eq. 5.13) [lb]."""
    return 1.68 * W_to_lb**0.567 * Sv_ft2**1.249 * Av**0.482 / (15.6 * trv_ft**0.747 * math.cos(sweep_c4_v) ** 0.882)


def roskam_usaf_fuselage(W_to_lb, n_ult, lf_ft, wf_ft, hf_ft, VC_kt):
    """USAF method (Roskam Part V Eq. 5.25); V_C design cruise speed [KEAS] → [lb]."""
    return 200 * ((W_to_lb * n_ult / 1e5) ** 0.286 * (lf_ft / 10) ** 0.857 * ((wf_ft + hf_ft) / 10)
                  * (VC_kt / 100) ** 0.338) ** 1.1


ROSKAM_REF = ("Roskam, Airplane Design Part V (DARcorporation), §5.1–5.3: Cessna method (Eqs. 5.2, 5.12, 5.13; "
              "V_max < 200 kt) and USAF method (Eqs. 5.4, 5.14, 5.15, 5.25; light/utility ≤ ~300 kt)")


def roskam_class_ii(design) -> dict:
    """Class II structural group weights (Roskam Part V, USAF method + Cessna wing) as an independent
    cross-check of the Raymer component build-up (Raymer Eqs. 15.46–15.49). Structure groups only (wing,
    tails, fuselage); the other groups are not re-estimated. Not fed back into the sizing loop.

    Validity: GA/utility airplanes (Cessna: V_max < 200 kt; USAF: ≤ ~300 kt); for a small UAV the result is
    extrapolated and only indicative. Coefficients checked against the Roskam Part V text (pp. 67–76)."""
    cfg, sr = design.config, design.structures
    W = design.sizing.W0 / LB
    n_ult = 1.5 * (sr.vn.n_limit_pos if sr is not None else 3.8)
    w, ht, vt, fu = cfg.wing, cfg.htail, cfg.vtail, cfg.fuselage
    KT = 0.514444
    VH = (sr.vn.VC if sr is not None else design.cruise_speed) / KT * 1.1   # V_H ≈ 1.1 V_C (ASSUMPTION)
    VC = (sr.vn.VC if sr is not None else design.cruise_speed) / KT
    hw, vw = ht.as_wing(), vt.as_wing()
    m = {
        "wing (USAF)": roskam_usaf_wing(W, n_ult, w.AR, w.sweep_c4, w.S / FT**2, w.taper, w.tc_root, VH),
        "wing (Cessna)": roskam_cessna_wing(W, n_ult, w.AR, w.S / FT**2),
        "htail (USAF)": roskam_usaf_htail(W, n_ult, ht.S / FT**2, ht.arm / FT, hw.span / FT, ht.tc * hw.c_root / FT),
        "htail (Cessna)": roskam_cessna_htail(W, ht.S / FT**2, ht.AR, ht.tc * hw.c_root / FT),
        "vtail (USAF)": roskam_usaf_vtail(W, n_ult, vt.S / FT**2, vw.span / FT, vt.tc * vw.c_root / FT),
        "vtail (Cessna)": roskam_cessna_vtail(W, vt.S / FT**2, vt.AR, vt.tc * vw.c_root / FT, vt.sweep_c4),
        "fuselage (USAF)": roskam_usaf_fuselage(W, n_ult, fu.length / FT, fu.max_diameter / FT, fu.max_diameter / FT, VC),
    }
    raymer = {}
    if getattr(design, "weights", None) is not None:
        for it in design.weights.items:
            if it.key in ("wing", "htail", "vtail", "fuselage"):
                raymer[it.key] = it.mass
    rows = []
    for k, lb in m.items():
        key = k.split()[0]
        r = raymer.get(key)
        rows.append({"item": k, "roskam_kg": lb * LB, "raymer_kg": r, "ratio": lb * LB / r if r else None,
                     "used": "Cessna" not in k or (key == "wing" and W >= 1000)})
    notes = ["V_H ≈ 1.1 V_C (PRESSUPOSTO); altura da deriva b_v = √(A_v S_v); n_ult = 1.5 n_lim; equações verificadas no texto de Roskam Parte V (págs. 67–76)",
             "Cessna (asa): inclui comandos e carenagem de ponta; exclui tanques e carry-through"]
    notes.append("Cessna Eqs. 5.12–5.13 (empenagem) mostradas só por transparência e EXCLUÍDAS da comparação: dão "
                 "valores implausíveis (para o C172 várias vezes o peso real da empenagem) — possível erro de impressão; "
                 "não corrigidas por ajuste")
    if W < 1000:
        notes.append(f"W_TO = {W:.0f} lb: fora da base estatística (aviação geral) — extrapolação, só indicativo; "
                     "Cessna (asa, ∝ A^1.712) excluída")
    return {"rows": rows, "n_ult": n_ult, "W_to_lb": W, "ref": ROSKAM_REF, "notes": notes}
