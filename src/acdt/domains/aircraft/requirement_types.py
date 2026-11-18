"""Aircraft requirement types, regulatory category limits and static validators.

Registered into the domain-agnostic registry (:mod:`acdt.core.requirements`) on import.
"""
from __future__ import annotations

from dataclasses import replace

from acdt.core.requirements import (Issue, RequirementSet, RequirementType, register_requirement,
                                    register_validator)

# --- Aircraft requirement types --------------------------------------------
_P_ALT = ("altitude",)
_BUILTIN = [
    RequirementType("payload_mass", "mass", "Payload mass carried on the design mission", ("sizing",),
                    ("min", "target"), reference="Raymer 6th ed. Ch. 3 (W0 = (Wcrew+Wpayload)/(1-Wf/W0-We/W0))"),
    RequirementType("crew_mass", "mass", "Crew mass (0 for UAV)", ("sizing",), ("target",),
                    reference="Raymer Ch. 3"),
    RequirementType("range", "length", "Design-mission cruise range", ("sizing",), ("min", "target"),
                    params=_P_ALT, reference="Breguet range: Raymer Eq. 3.5/3.6; electric: Hepperle (2012)"),
    RequirementType("endurance", "time", "Design-mission loiter/endurance time", ("sizing",), ("min", "target"),
                    params=_P_ALT, reference="Breguet endurance: Raymer Eq. 3.7/3.8; electric: Hepperle (2012)"),
    RequirementType("cruise_speed", "speed", "Cruise speed (TAS) at cruise altitude", ("constraint", "sizing"),
                    ("min", "target"), params=_P_ALT, reference="Gudmundsson (2014) Sec. 3.2, T/W for cruise"),
    RequirementType("max_speed", "speed", "Maximum level speed (TAS) at full power", ("constraint",),
                    ("min",), params=_P_ALT, reference="Gudmundsson (2014) Sec. 3.2"),
    RequirementType("stall_speed", "speed", "Stall speed, landing configuration, sea level", ("constraint",),
                    ("max",), params=_P_ALT, reference="Raymer Eq. 5.6 (W/S = 0.5 rho Vs^2 CLmax)"),
    RequirementType("cruise_altitude", "length", "Cruise / loiter altitude", ("context",), ("target",)),
    RequirementType("service_ceiling", "length", "Service ceiling (ROC = 0.508 m/s)", ("constraint",), ("min",),
                    reference="Gudmundsson (2014) Sec. 3.2 (service ceiling constraint)"),
    RequirementType("climb_rate", "speed", "Rate of climb at sea level (or given altitude)", ("constraint",),
                    ("min",), params=_P_ALT, reference="Gudmundsson (2014) Sec. 3.2 (T/W for ROC)"),
    RequirementType("load_factor", "dimensionless", "Sustained level-turn load factor n", ("constraint",),
                    ("min",), params=("altitude", "speed"), reference="Gudmundsson (2014) Sec. 3.2 (level constant-velocity turn)"),
    RequirementType("turn_rate", "angular_rate", "Sustained turn rate", ("constraint",), ("min",),
                    params=("altitude", "speed"), reference="n = sqrt(1+(omega V/g)^2), Anderson 'Aircraft Performance and Design' Ch. 6"),
    RequirementType("takeoff_ground_roll", "length", "Take-off ground run", ("constraint",), ("max",),
                    params=_P_ALT, reference="Gudmundsson (2014) Sec. 3.2 (T/W for desired T-O distance)"),
    RequirementType("landing_distance", "length", "Landing distance over 50 ft obstacle", ("constraint",),
                    ("max",), params=_P_ALT, reference="Raymer Eq. 5.11"),
    RequirementType("mtow", "mass", "Maximum take-off mass", ("check",), ("max", "target")),
    RequirementType("wing_span", "length", "Wing span (hangar/transport/launcher limits)", ("check",), ("max",)),
    RequirementType("power_available", "power", "Installed (SL) power limit, prop/electric", ("check",), ("max",)),
    RequirementType("thrust_available", "force", "Installed (SL) static thrust limit, jet", ("check",), ("max",)),
    RequirementType("unit_cost", "currency", "Unit production cost (flyaway)", ("trade", "check"),
                    ("max", "objective"), reference="Gudmundsson (2014) Ch. 2, modified Eastlake model"),
    RequirementType("unit_cost_at_quantity", "currency", "Average unit cost (programme cost / N, RDT&E and tooling "
                    "amortised) at production quantity N (qualifier quantity; default series_cost.quantity)",
                    ("check",), ("max",), params=("quantity",),
                    reference="series_cost.py: Gudmundsson (2014) Ch. 2 Eastlake / Raymer (2018) Ch. 18 DAPCA IV "
                    "(docs/CUSTO_SERIE.md)"),
    RequirementType("flyaway_cost", "currency", "Unit flyaway (recurring production) cost at quantity N (qualifier "
                    "quantity)", ("check",), ("max",), params=("quantity",),
                    reference="series_cost.py: recurring CER elements / N + per-aircraft items (docs/CUSTO_SERIE.md)"),
    RequirementType("break_even_quantity", "dimensionless", "Smallest production quantity at which revenue "
                    "(series_cost.price × N) covers the programme cost", ("check",), ("max",),
                    reference="series_cost.py: break-even definition, fixed/variable split of Gudmundsson (2014) "
                    "Ch. 2 (docs/CUSTO_SERIE.md)"),
    RequirementType("noise", "sound", "Flyover L_A,max at a ground observer below the loiter/cruise track", ("check",),
                    ("max",), reference="Gutin 1936 + Schlegel-King-Mull 1966 (Marte & Kurtz 1970), ISO 9613-1, "
                    "IEC 61672-1 A-weighting (noise.py; docs/RUIDO.md)"),
    RequirementType("aural_detection_range", "length", "Ground distance within which the aircraft is audible "
                    "(ISO 226 threshold; ambient noise optional)", ("check",), ("max",),
                    reference="ISO 226:2003 T_f + noise.py propagation (docs/RUIDO.md)"),
    RequirementType("thermal_margin", "temperature_difference", "Minimum hot-side component temperature margin "
                    "(T_max − T) over the thermal conditions (hot day MIL-HDBK-310)", ("check",), ("min",),
                    reference="thermal.py: Incropera et al. 6th ed. correlations, MIL-HDBK-310 (docs/TERMICA.md)"),
    RequirementType("cold_thermal_margin", "temperature_difference", "Minimum cold-side component temperature margin "
                    "(T − T_min) over the thermal conditions (cold day MIL-HDBK-310)", ("check",), ("min",),
                    reference="thermal.py: Incropera et al. 6th ed. correlations, MIL-HDBK-310 (docs/TERMICA.md)"),
    RequirementType("cooling_drag_area", "area", "Cooling drag area D/q at hot-day cruise (ram air + engine cooling)",
                    ("check",), ("max",), reference="thermal.py: momentum + Bernoulli, NACA RM A8I29 (docs/TERMICA.md)"),
    RequirementType("mission_reliability", "dimensionless", "Probability of completing the design mission without a "
                    "critical failure (mission RBD, constant rates)", ("check",), ("min",),
                    reference="reliability.py: MIL-HDBK-338B Eq. 6.19–6.27, 5.57 (docs/FIABILIDADE.md)"),
    RequirementType("mtbcf", "time", "Mean time between critical failures (mission RBD with redundancy)", ("check",),
                    ("min",), reference="reliability.py: MIL-HDBK-338B Sec. 3, Eq. 5.73 (docs/FIABILIDADE.md)"),
    RequirementType("mtbf", "time", "Basic (logistics) MTBF: every unit in series, maintenance demand", ("check",),
                    ("min",), reference="reliability.py: MIL-HDBK-338B §6.4.2 (docs/FIABILIDADE.md)"),
    RequirementType("operational_availability", "dimensionless", "Operational availability A_o = (MTBM + RT) / "
                    "(MTBM + RT + MDT)", ("check",), ("min",),
                    reference="reliability.py: MIL-HDBK-338B Eq. 10.22 (docs/FIABILIDADE.md)"),
    RequirementType("maintenance_man_hours_per_fh", "dimensionless", "Direct maintenance man-hours per flight hour "
                    "(corrective + preventive)", ("check",), ("max",),
                    reference="reliability.py: MIL-HDBK-338B Sec. 3 DMMH/MA (docs/FIABILIDADE.md)"),
    RequirementType("fleet_size", "dimensionless", "Number of aircraft needed to sustain the declared coverage or "
                    "sortie rate given availability and mission reliability", ("check",), ("max",),
                    reference="reliability.py: fleet_feedback (Ha 2010) / sortie balance, MIL-HDBK-338B Eq. 10.22 "
                    "(docs/FIABILIDADE.md)"),
    RequirementType("ice_protection_power", "power", "Ice-protection power required (thermal anti-ice / "
                    "electro-thermal de-ice) must not exceed the power available for it", ("check",), ("max",),
                    reference="icing.py: Messinger (1953) heat balance via Anderson NASA/CR-2004-212875; 14 CFR 25 "
                    "App. C (docs/GELO.md)"),
    RequirementType("max_ice_thickness", "length", "Maximum stagnation-line ice thickness on unprotected surfaces "
                    "over the design icing encounter (14 CFR 25 App. C)", ("check",), ("max",),
                    reference="icing.py: Langmuir & Blodgett + Messinger via Anderson NASA/CR-2004-212875 (docs/GELO.md)"),
    RequirementType("flight_into_known_icing", "category", "Flight into known icing intended (sim/nao); an L0 "
                    "analysis can only fail or stay unknown, never demonstrate it (14 CFR 25.1419)", ("check",),
                    ("target",), choices=("sim", "nao"), reference="icing.py (docs/GELO.md)"),
    RequirementType("regulatory_category", "category", "Regulatory / certification basis", ("check", "systems"),
                    ("target",), choices=("easa_open", "easa_specific", "easa_certified", "stanag_4703",
                                          "stanag_4671", "cs_23", "cs_vla", "cs_lsa", "far_23")),
    RequirementType("propulsion_type", "category", "Propulsion preference", ("context",), ("target",),
                    choices=("electric", "piston_prop", "turboprop", "jet")),
    RequirementType("mtow_objective", "mass", "Minimise take-off mass (trade objective)", ("trade",), ("objective",)),
]
for _rt in _BUILTIN:
    register_requirement(replace(_rt, domains=("aircraft",)))

# Category implications (documented regulatory thresholds, verify edition):
CATEGORY_LIMITS: dict[str, dict[str, float]] = {
    # EU 2019/947 'open' category: MTOM < 25 kg (Art. 4(1)(b))
    "easa_open": {"mtow_max": 25.0},
    # STANAG 4703 (AEP-83) scope: fixed-wing light UAS, MTOW <= 150 kg
    "stanag_4703": {"mtow_max": 150.0},
    # STANAG 4671 (USAR): fixed-wing UAV 150 kg .. 20 000 kg
    "stanag_4671": {"mtow_min": 150.0, "mtow_max": 20000.0},
    # CS-LSA: MTOM <= 600 kg (landplane); stall VS0 <= 45 KCAS
    "cs_lsa": {"mtow_max": 600.0, "stall_speed_max": 45 * 1852 / 3600},
    # CS-VLA: MTOM <= 750 kg; VS0 <= 45 KCAS
    "cs_vla": {"mtow_max": 750.0, "stall_speed_max": 45 * 1852 / 3600},
    # CS-23 Amdt 5 / 14 CFR Part 23 Amdt 64: MTOM <= 8 618 kg (19 000 lb), max 19 pax (CS 23.2005).
    # Stall-speed limits are now in consensus means of compliance (e.g. ASTM F3179) -> not imposed here.
    "cs_23": {"mtow_max": 8618.0},
    "far_23": {"mtow_max": 8618.0},
}


@register_validator("aircraft")
def validate_aircraft(rs: RequirementSet) -> list[Issue]:
    """Aircraft static checks (orderings and category thresholds only; physics downstream)."""
    issues: list[Issue] = []
    vs = rs.value("stall_speed")
    for k in ("cruise_speed", "max_speed"):
        v = rs.value(k)
        if vs is not None and v is not None and v <= 1.2 * vs:
            issues.append(Issue("error", f"{k} ({v:.1f} m/s) must exceed 1.2x stall_speed ({vs:.1f} m/s)",
                                (k, "stall_speed")))
    vc, vm = rs.value("cruise_speed"), rs.value("max_speed")
    if vc is not None and vm is not None and vc > vm:
        issues.append(Issue("error", "cruise_speed > max_speed", ("cruise_speed", "max_speed")))
    if rs.get("range") is None and rs.get("endurance") is None:
        issues.append(Issue("warning", "No range/endurance given: fuel/energy fraction from "
                            "a 30 min loiter default (assumption)", ("range", "endurance")))
    if rs.get("payload_mass") is None:
        issues.append(Issue("error", "payload_mass is required to close the weight equation "
                            "(Raymer Eq. 3.4)", ("payload_mass",)))
    cat = rs.value("regulatory_category")
    lim = CATEGORY_LIMITS.get(cat or "", {})
    mt = rs.get("mtow", "max")
    if lim.get("mtow_max") and mt and mt.value > lim["mtow_max"]:
        issues.append(Issue("warning", f"mtow max {mt.value:g} kg exceeds category {cat} limit "
                            f"{lim['mtow_max']:g} kg; category limit will govern", ("mtow", "regulatory_category")))
    sv = rs.get("stall_speed")
    if lim.get("stall_speed_max") and sv and sv.value > lim["stall_speed_max"]:
        issues.append(Issue("warning", f"stall_speed {sv.value:.1f} m/s above {cat} limit "
                            f"{lim['stall_speed_max']:.1f} m/s; category limit will govern",
                            ("stall_speed", "regulatory_category")))
    pay, mtmax = rs.value("payload_mass"), rs.value("mtow", sense="max")
    if pay is not None and mtmax is not None and pay >= mtmax:
        issues.append(Issue("error", "payload_mass >= mtow max", ("payload_mass", "mtow")))
    if rs.value("propulsion_type") == "jet" and rs.get("power_available"):
        issues.append(Issue("warning", "power_available ignored for jet; use thrust_available"))
    return issues
