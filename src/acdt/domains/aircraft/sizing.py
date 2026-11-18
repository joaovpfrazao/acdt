"""Phase-1 pipeline: requirements -> weight sizing -> constraint diagram ->
design point -> first-cut geometry -> component drag build-up, iterated as a
fixed-point multidisciplinary analysis (MDA) until W0 and CD0 converge.

This is the classical conceptual-design loop of Raymer (6th ed.) Ch. 2–3, 5–7,
12, 15 and 19 ("sizing and trade studies"), with Gudmundsson (2014) Ch. 3
constraint equations. Weight loop (``weights.method: components``): the
statistical We/W0 is only the initial value; after each geometry update the
component build-up (Raymer Ch. 15 group weights + selected systems,
``weights_detailed``) gives a new We, whose fraction is used to re-size W0 in
the next iteration, until W0, We and CD0 converge. No new methods are introduced here: this module only
wires the cited methods together and records provenance.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from acdt import G0
from .aero.drag import ROUGHNESS, DragPolar, component_buildup, cd0_equivalent_skin_friction, oswald_raymer
from .aero.lift import HighLiftDevice, HighLiftSummary, high_lift_summary, lift_curve_slope
from acdt.core.atmosphere import isa
from .constraints import (AeroContext, Constraint, ConstraintContext, DesignPoint, PropContext, _cruise_tw,
                          build_constraints, design_point)
from .cost import EastlakeInputs, eastlake_unit_cost, piston_engine_cost
from .geometry import (RAYMER_FUSELAGE_LENGTH, RAYMER_TAIL_VOLUME, Configuration, Fuselage, TrapezoidalWing,
                       size_tails)
from .mission import MissionSpec
from .propulsion import is_propeller
from acdt.core.requirements import Issue, Requirement, handlers, register_handler
from .requirement_types import CATEGORY_LIMITS
from .weights import EmptyWeightModel, MissionLeg, PropulsionData, SizingResult, size_takeoff_weight
from acdt.core.pipeline import InfeasibleError  # noqa: F401  (re-exported)



@dataclass
class CheckResult:
    key: str
    ok: bool | None  # None = not evaluated
    message: str


VERIFICATION_PREFIXES = ("perf:", "hq:", "aeroel:")
# Weight-and-balance and landing-gear checks are reported. They do not change Phase-1 feasibility
# and they do not enter the segment-mission `verified` flag.
# ``lr:`` (opt-in catapult / belly landing, launch_recovery.py) is reported the same way.
LAYOUT_PREFIXES = ("wb:", "gear:", "asm:", "lr:")


@dataclass
class DesignResult:
    spec: MissionSpec
    sizing: SizingResult
    design_point: DesignPoint
    constraints: list[Constraint]
    polar: DragPolar
    config: Configuration | None
    highlift: object
    CLalpha: float
    buildup: object | None
    legs: list[MissionLeg]
    cruise_speed: float
    cruise_altitude: float
    iterations: int
    converged: bool
    issues: list[Issue] = field(default_factory=list)
    checks: list[CheckResult] = field(default_factory=list)
    cost: object | None = None
    history: list[dict] = field(default_factory=list)
    systems: object | None = None
    weights: object | None = None  # weights_detailed.WeightBreakdown (component build-up)
    weight_initial_source: str = ""
    weight_cross_check: list[dict] = field(default_factory=list)
    # Phase 2
    lowfi: object | None = None        # aero.lowfi.LowFiAero (aero.fidelity: lowfi)
    structures: object | None = None   # structures.StructuresResult (V-n, Schrenk loads, wing box)
    structures_avl: object | None = None  # same with AVL span loading (stability stage)
    stability: object | None = None    # stability.StabilityResult
    performance: object | None = None  # performance.PerformanceResult
    avl: object | None = None          # aero.avl.AVLResult at trimmed cruise
    # Phase 3
    dynamics: object | None = None     # dict: scissor, modes, handling qualities (stability.py)
    aeroelastic: object | None = None  # aeroelasticity.AeroelasticResult
    propeller_calibration: dict | None = None  # propeller.calibrated_etas history (fixed-pitch map)
    weight_balance: object | None = None  # weight_balance.WeightBalanceResult (operational loading)
    landing_gear: object | None = None    # landing_gear.LandingGearResult
    structures_l1: object | None = None   # structures_l1.StructuresL1 (masses, deflections, elastic correction)
    launch_recovery: dict | None = None   # opt-in catapult / belly landing (launch_recovery.py)
    gear_drag: dict | None = None         # opt-in gear drag in the polar (aero/gear_drag.py)
    assembly_loop: dict | None = None     # P1b: assembly inside the W0 loop (scale, drag band, parts, history)
    assembly: object | None = None        # {"result": assembly.sizing.AssemblySizing, "comparison": {...}} (P1b)
    onboard_bridge: dict | None = None    # auto-close report when mission had onboard (PR #36 / size cycle)

    @property
    def feasible(self) -> bool:
        """Sizing feasibility (Phase-1 definition). Verification checks of later phases (keys ``perf:*``,
        ``hq:*``, ``aeroel:*``) are reported separately in :attr:`verified`."""
        skip = VERIFICATION_PREFIXES + LAYOUT_PREFIXES
        return (self.sizing.converged and self.design_point.feasible
                and not any(c.ok is False for c in self.checks if not c.key.startswith(skip))
                and not any(i.severity == "error" for i in self.issues))

    @property
    def verified(self) -> bool | None:
        """True if every Phase-2 segment-mission check passes; None if the stage did not run."""
        pc = [c for c in self.checks if c.key.startswith(VERIFICATION_PREFIXES)]
        if not pc:
            return None
        return self.feasible and all(c.ok is not False for c in pc)

    @property
    def S(self) -> float:
        return self.sizing.W0 * G0 / self.design_point.ws

    @property
    def power_sl(self) -> float | None:
        dp = self.design_point
        return dp.value * self.sizing.W0 * G0 if dp.metric == "P/W" else None

    @property
    def thrust_sl(self) -> float | None:
        dp = self.design_point
        return dp.value * self.sizing.W0 * G0 if dp.metric == "T/W" else None

    def cruise_power_required(self) -> float:
        """Shaft power at cruise: P = D V / eta_p (Anderson APD Ch. 5)."""
        rho = isa(self.cruise_altitude).rho
        V = self.cruise_speed
        W = self.sizing.W0 * G0
        CL = W / (0.5 * rho * V**2 * self.S)
        D = 0.5 * rho * V**2 * self.S * float(self.polar.CD(CL))
        eta = self.spec.assumptions["propulsion"]["eta_cruise"]
        return D * V / eta


# ---- checks registered against requirement keys -----------------------------
@register_handler("check", "mtow")
def _chk_mtow(r: Requirement, res: DesignResult):
    W0 = res.sizing.W0
    if r.sense == "max":
        return CheckResult(r.key, W0 <= r.value, f"W0 = {W0:.1f} kg vs max {r.value:.1f} kg")
    return CheckResult(r.key, abs(W0 - r.value) / r.value < 0.1, f"W0 = {W0:.1f} kg vs target {r.value:.1f} kg (±10%)")


@register_handler("check", "wing_span")
def _chk_span(r, res):
    b = res.config.wing.span
    return CheckResult(r.key, b <= r.value, f"b = {b:.2f} m vs max {r.value:.2f} m")


@register_handler("check", "power_available")
def _chk_power(r, res):
    P = res.power_sl
    if P is None:
        return CheckResult(r.key, None, "not applicable (jet)")
    return CheckResult(r.key, P <= r.value, f"P_SL required {P / 1e3:.2f} kW vs available {r.value / 1e3:.2f} kW")


@register_handler("check", "thrust_available")
def _chk_thrust(r, res):
    T = res.thrust_sl
    if T is None:
        return CheckResult(r.key, None, "not applicable (propeller)")
    return CheckResult(r.key, T <= r.value, f"T_SL required {T:.0f} N vs available {r.value:.0f} N")


@register_handler("check", "unit_cost")
def _chk_cost(r, res):
    if res.cost is None:
        return CheckResult(r.key, None, "cost model not evaluated")
    if r.sense == "objective":
        return CheckResult(r.key, None, f"objective {r.value}: unit cost {res.cost.unit_cost:,.0f} (report)")
    return CheckResult(r.key, res.cost.unit_cost <= r.value,
                       f"unit cost {res.cost.unit_cost:,.0f} vs max {r.value:,.0f}")


@register_handler("check", "regulatory_category")
def _chk_cat(r, res):
    lim = CATEGORY_LIMITS.get(r.value, {})
    W0 = res.sizing.W0
    msgs, ok = [], True
    if "mtow_max" in lim:
        ok &= W0 <= lim["mtow_max"]
        msgs.append(f"W0 {W0:.1f} kg <= {lim['mtow_max']:g} kg")
    if "mtow_min" in lim:
        ok &= W0 >= lim["mtow_min"]
        msgs.append(f"W0 >= {lim['mtow_min']:g} kg")
    return CheckResult(r.key, ok if msgs else None, f"{r.value}: " + ("; ".join(msgs) or "no numeric limit"))


@register_handler("check", "noise")
def _chk_noise(r, res):
    return CheckResult(r.key, None, f"not evaluated — foreseen: {r.type.reference}")


# ---- pipeline ---------------------------------------------------------------
def _empty_model(spec: MissionSpec) -> EmptyWeightModel:
    """Initial (statistical) empty-weight model: Raymer Table 3.1 / Nicolai Table 5.1 / fixed
    user-registered fixed class, a user regression, or a fixed designer fraction."""
    w = spec.assumptions["weights"]
    cls = w.get("initial_class") or spec.aircraft_class
    return EmptyWeightModel(cls if w["A"] is None else "custom", w["A"], w["C"],
                            w["fixed_fraction"], w["Kvs"], w["tech_factor"])


def _prop_data(spec: MissionSpec) -> PropulsionData:
    p, kind = spec.assumptions["propulsion"], spec.propulsion_kind
    from acdt.core.energy_storage import number
    for k in ("onboard_power_W","auxiliary_fuel_flow_kg_s","auxiliary_shaft_W","auxiliary_pre_s","auxiliary_post_s"):
        number(k,p.get(k,0.))
    if kind not in ("piston_prop","turboprop") and (p.get("auxiliary_fuel_flow_kg_s",0) or p.get("auxiliary_shaft_W",0)):
        raise ValueError("generator auxiliary hooks require thermal prop; jet uses dedicated jet_size")
    if p.get("onboard_power_W",0) and kind!="electric": raise ValueError("main battery hotel load requires electric prop")
    if bool(p.get("auxiliary_fuel_flow_kg_s",0)) != bool(p.get("auxiliary_shaft_W",0)):
        raise ValueError("thermal generator needs BOTH incremental fuel flow and shaft extraction")
    if p.get("auxiliary_shaft_W",0) and p.get("propeller"): raise ValueError("fixed-pitch generator extraction unimplemented")
    c_p = None if p["bsfc_lb_hp_h"] is None else p["bsfc_lb_hp_h"] * 0.45359237 / (745.69987 * 3600)
    return PropulsionData(kind, p["eta_cruise"], c_p, p["tsfc_1_h"] / 3600 / G0, p["battery_Wh_kg"] * 3600,
                          p["eta_total"], p["dod"], p["energy_reserve"], p["systems_power_W"]+p.get("onboard_power_W",0.0),
                          auxiliary_fuel_flow_kg_s=p.get("auxiliary_fuel_flow_kg_s",0.0),
                          auxiliary_pre_s=p.get("auxiliary_pre_s",0.0),auxiliary_post_s=p.get("auxiliary_post_s",0.0))


def _legs(spec: MissionSpec, polar: DragPolar, ws: float | None, CLmax_clean: float, h_cruise: float):
    """Mission legs with flight-condition rules (Raymer Sec. 3.4 / Anderson APD Ch. 5):
    prop cruise at (L/D)max, prop loiter at min-power (0.866 L/Dmax); jet cruise at
    0.866 (L/D)max, jet loiter at (L/D)max. A required speed overrides the optimum, and
    the L/D is then evaluated from the polar at that speed. Loiter speed >= 1.2 Vs (clean)."""
    reqs, kind = spec.requirements, spec.propulsion_kind
    prop = is_propeller(kind)
    out = []
    rng, end, Vc = reqs.get("range"), reqs.get("endurance"), reqs.value("cruise_speed")

    def leg(kind_leg, value, h, V_req):
        rho = isa(h).rho
        if kind_leg == "cruise":
            CL_opt = polar.CL_LDmax if prop else polar.CL_LDmax / math.sqrt(3)
        else:
            CL_opt = polar.CL_min_power if prop else polar.CL_LDmax
        Vs = math.sqrt(2 * ws / (rho * CLmax_clean))
        V = V_req if V_req else max(polar.speed_for_CL(CL_opt, ws, rho), 1.2 * Vs)
        CL = 2 * ws / (rho * V**2)
        return MissionLeg(kind_leg, value, V, CL / float(polar.CD(CL)), h)

    if rng:
        out.append(leg("cruise", rng.value, rng.params.get("altitude", h_cruise), Vc))
    if end:
        Vl = spec.assumptions["propulsion"].get("loiter_speed_m_s")
        if Vl is None and not rng:
            Vl = Vc  # endurance-only mission flown at the required cruise speed, if any
        out.append(leg("loiter", end.value, end.params.get("altitude", h_cruise), Vl))
    if not out:
        out.append(leg("loiter", 1800.0, h_cruise, Vc))
    return out


def structures_inputs(spec: MissionSpec, W0: float, config, CLmax: float, CLa: float, V_cruise: float,
                      h_cruise: float, wing_mass_raymer: float | None, uas: bool, cm0: float = 0.0,
                      avl_strips=None) -> dict:
    """Inputs of :func:`structures.wing_structure` from the spec (Phase 2 structures stage)."""
    from .weights_detailed import _merge_opts, limit_load_factor
    A = spec.assumptions
    sa = A["structures"]
    wo = _merge_opts(A["weights"].get("components"))
    cat = wo["structural_category"]
    reg = sa["regulation"]
    if reg == "auto":
        reg = "stanag_4671" if uas else "cs_23"
    mat = sa["material"]
    if mat == "auto":
        mat = "cfrp" if wo["material"] == "composite" else "al2024_t3"
    return dict(wing=config.wing, W0=W0, CLmax=CLmax, CLalpha=CLa,
                V_cruise_eas=V_cruise * math.sqrt(isa(h_cruise).sigma), category=cat, regulation=reg,
                altitude=h_cruise, n_pos=wo["limit_load_factor"] or limit_load_factor(W0, cat),
                wing_mass_raymer=wing_mass_raymer, material=mat, cm0=cm0, avl_strips=avl_strips,
                VH_eas=sa["VH_eas_m_s"], areal_density_floor=wo["min_areal_density_kg_m2"] or 0.0,
                fuselage_width=config.fuselage.max_diameter, nonoptimum_factor=sa["nonoptimum_factor"],
                elastic_axis=sa.get("elastic_axis", "section"), le_cell=sa.get("le_cell", True))


def build_configuration(spec: MissionSpec, W0: float, ws: float, AR: float | None = None) -> Configuration:
    """Geometry from (W0, W/S, AR): trapezoidal wing, Raymer Table 6.3 fuselage (or user), tails by volume
    coefficients (Raymer Eqs. 6.28–6.29). Shared by the fixed-point MDA and the OpenMDAO model (mdo.py)."""
    aero_a, geo_a = spec.assumptions["aero"], spec.assumptions["geometry"]
    AR = aero_a["AR"] if AR is None else AR
    dih = geo_a.get("dihedral_deg")
    dih_rad = math.radians(3.0 if dih is None else float(dih))
    wing_ = TrapezoidalWing(W0 * G0 / ws, AR, aero_a["taper"], math.radians(aero_a["sweep_c4_deg"]),
                            aero_a["tc_root"], aero_a["tc_tip"], aero_a["xc_max_t"], dihedral=dih_rad,
                            airfoil=aero_a["airfoil"])
    if geo_a["fuselage_length_m"]:
        fus_ = Fuselage(geo_a["fuselage_length_m"], geo_a["fuselage_diameter_m"]
                        or geo_a["fuselage_length_m"] / geo_a["fuselage_fineness"])
    else:
        fc = geo_a["fuselage_class"] or spec.aircraft_class
        if fc not in RAYMER_FUSELAGE_LENGTH:
            raise InfeasibleError(f"No Raymer Table 6.3 fuselage statistics for '{fc}': give "
                                  "assumptions.geometry.fuselage_length_m (and diameter)")
        fus_ = Fuselage.from_raymer(W0, fc, geo_a["fuselage_fineness"])
    tc_key = geo_a["tail_class"] or spec.aircraft_class
    c_ht, c_vt = (geo_a["c_ht"], geo_a["c_vt"]) if geo_a["c_ht"] else RAYMER_TAIL_VOLUME.get(
        tc_key, RAYMER_TAIL_VOLUME["ga_single_engine"])
    ht_, vt_ = size_tails(wing_, geo_a["tail_arm_fraction"] * fus_.length, c_ht, c_vt, geo_a["ar_h"],
                          geo_a["ar_v"])
    return Configuration(wing_, fus_, ht_, vt_, dict(aero_a["extra_drag_areas_m2"]))


def constraint_requirements(spec: MissionSpec):
    """Requirement set for the constraint diagram, including category-implied limits (CS-VLA/LSA stall)."""
    from acdt.core.requirements import RequirementSet as _RS
    reqs = spec.requirements
    cat = reqs.value("regulatory_category")
    lim = CATEGORY_LIMITS.get(cat or "", {})
    extra, notes = [], []
    if "stall_speed_max" in lim:
        vs = reqs.value("stall_speed")
        if vs is None or vs > lim["stall_speed_max"]:
            extra.append(Requirement("stall_speed", "max", lim["stall_speed_max"], "m/s",
                                     round(lim["stall_speed_max"], 2)))
            notes.append(f"stall_speed max {lim['stall_speed_max']:.1f} m/s imposed by {cat}")
    return _RS(list(reqs) + extra, domain="aircraft"), notes


def flap_system_items(o: dict, flap_area_m2: float | None, label: str) -> list:
    """Flap-system mass items from user/datasheet values only (no default masses are invented):
    ``actuators`` × ``actuator_mass_kg`` and ``surface_mass_kg_m2`` × flap area (hinges, fittings, ribs)."""
    out = []
    n, ma = o.get("actuators"), o.get("actuator_mass_kg")
    if n and ma:
        out.append({"name": f"{label}: {int(n)} atuador(es) × {ma:g} kg", "mass_kg": int(n) * float(ma),
                    "group": "equipment"})
    if o.get("surface_mass_kg_m2") and flap_area_m2:
        out.append({"name": f"{label}: ferragens/charneiras {o['surface_mass_kg_m2']:g} kg/m² × {flap_area_m2:.2f} m²",
                    "mass_kg": float(o["surface_mass_kg_m2"]) * flap_area_m2, "group": "structure"})
    return out


def unit_cost_estimate(spec: MissionSpec, We: float, P_sl: float | None, Vc: float):
    """Modified Eastlake unit cost (Gudmundsson 2014 Ch. 2) from empty mass and installed power."""
    A, reqs = spec.assumptions, spec.requirements
    kind = spec.propulsion_kind
    ca = A.get("cost", {})
    P_bhp = (P_sl or 0) / 745.69987
    vmax = reqs.value("max_speed") or Vc
    eng = piston_engine_cost(P_bhp, A["propulsion"]["n_engines"], ca.get("cpi", 1.0)) if kind == "piston_prop" \
        else ca.get("engine_cost", 0.0)
    if "f_comp" not in ca and "F_COMP" not in ca:
        # composite fraction of the airframe from the weights material (Gudmundsson 2014 f_comp; 1 = all composite)
        mat = ((A.get("weights") or {}).get("components") or {}).get("material", "metal")
        ca = {**ca, "f_comp": 1.0 if mat == "composite" else 0.0}
    fl_ = A["aero"].get("flap") or {}
    cam_ = A["aero"].get("camber_flap") or {}
    act_cost = sum(float(o_.get("actuator_cost_usd") or 0.0) * int(o_.get("actuators") or 0) for o_ in (fl_, cam_))
    if cam_ and "actuators" not in cam_ and cam_.get("actuator_cost_usd"):
        from .aero.camber_flap import resolve as _cr
        act_cost += float(cam_["actuator_cost_usd"]) * _cr(cam_)["actuators"]
    if act_cost:
        ca = {**ca, "extra_unit_cost": ca.get("extra_unit_cost", 0.0) + act_cost}
    ei = EastlakeInputs(W_airframe_kg=ca.get("airframe_fraction_of_empty", 0.65) * We,
                        V_H_kt=vmax / 0.514444, engine_cost=eng,
                        **{k: v for k, v in ca.items() if k in EastlakeInputs.__dataclass_fields__
                           and k not in ("W_airframe_kg", "V_H_kt", "engine_cost")})
    return eastlake_unit_cost(ei)


def _attach_onboard_bridge(res: DesignResult, spec: MissionSpec) -> None:
    """Surface the automatic onboard → size coupling on the result (mass + fuel/energy hotel)."""
    ob = (spec.assumptions or {}).get("onboard_bridge")
    if not isinstance(ob, dict) or not ob.get("applied"):
        return
    res.onboard_bridge = ob
    load = ob.get("load_average_W")
    ff = ob.get("fuel_flow_kg_s")
    bat = ob.get("main_battery_average_W")
    bits = [f"model={ob.get('model')}"]
    if load is not None:
        bits.append(f"hotel {load:g} W")
    if ff:
        bits.append(f"aux fuel {ff:g} kg/s")
    if bat:
        bits.append(f"pack hotel {bat:g} W")
    bits.append(f"+payload {ob.get('incremental_payload_kg', 0)} kg")
    bits.append(f"+equip {ob.get('incremental_equipment_kg', 0)} kg")
    res.issues.append(Issue(
        "info",
        "onboard auto-closed inside size (no separate onboard_size step): " + "; ".join(str(b) for b in bits)
        + f" — {ob.get('method', 'onboard_bridge')}"))



def run(spec: MissionSpec, strict: bool = False, systems=None) -> DesignResult:
    """:func:`_run_calibrated` plus, with a generic assembly in the loop (``assumptions.assembly``), the check
    ``asm:closes_pessimistic_cd0``: the design is re-sized on the pessimistic CD0 of the drag band (P1b) and the
    check says whether it still closes (converged and feasible). ``assembly.options.close_on: pessimistic``
    sizes on the pessimistic CD0 directly (then the check is the run itself).

    When the mission YAML carried an ``onboard`` block, :meth:`MissionSpec.from_dict` already mapped it into
    native hotel/extraction hooks (``onboard_bridge``). That report is attached here so ``acdt size`` /
    ``result.json`` show the automatic close — no separate ``onboard_size`` step required for mass/fuel/energy.
    """
    import copy
    res = _run_calibrated(spec, strict, systems)
    _attach_onboard_bridge(res, spec)
    lp = res.assembly_loop
    if not lp:
        return res
    from .assembly.tailless_trim import clmax_trimmed_requested, close_trimmed_clmax
    if clmax_trimmed_requested(lp):
        res, spec = close_trimmed_clmax(res, spec, lambda sp: _run_calibrated(sp, strict, systems))
        _attach_onboard_bridge(res, spec)
        lp = res.assembly_loop
        if not lp:
            return res
    o = lp["options"]
    if o["close_on"] == "pessimistic":
        ok = bool(res.feasible)
        msg = (f"dimensionado com o CD0 pessimista {lp['drag']['CD0_pessimistic']:.5f} (nominal "
               f"{lp['drag']['CD0_nominal']:.5f}): {'fecha' if ok else 'não fecha'}, W0 {res.sizing.W0:.1f} kg")
    elif o.get("check_pessimistic", True):
        sp = copy.deepcopy(spec)
        sp.assumptions["assembly"] = {**lp["spec"], "options": {**(lp["spec"].get("options") or {}),
                                                               "close_on": "pessimistic",
                                                               "check_pessimistic": False}}
        try:
            r2 = _run_calibrated(sp, strict, systems)
            ok = bool(r2.feasible)
            W2 = r2.sizing.W0
            lp["pessimistic"] = {"W0": W2, "feasible": ok, "CD0": r2.polar.CD0 if r2.polar else None,
                                 "S": r2.S if r2.sizing.converged else None}
            msg = (f"com o CD0 pessimista ({lp['drag']['CD0_pessimistic']:.5f} contra nominal "
                   f"{lp['drag']['CD0_nominal']:.5f}) o projeto {'fecha' if ok else 'NÃO fecha'}: W0 {W2:.1f} kg "
                   f"contra {res.sizing.W0:.1f} kg nominal")
        except InfeasibleError as ex:
            ok, msg = False, f"com o CD0 pessimista o dimensionamento não fecha: {ex}"
    else:
        return res
    res.checks.append(CheckResult("asm:closes_pessimistic_cd0", ok, msg))
    return res


def _run_calibrated(spec: MissionSpec, strict: bool = False, systems=None) -> DesignResult:
    """Phase-1 MDA (:func:`_run_once`) plus, when ``assumptions.propulsion.propeller`` is given, the progressive
    calibration of the constant propeller efficiencies (eta_takeoff / eta_climb / eta_cruise) against the
    fixed-pitch propeller map (propeller.py): re-run until the efficiencies change < 0.005 (max 5 passes)."""
    import copy
    from .propeller import calibrated_etas
    res = _run_once(spec, strict, systems)
    if not (spec.assumptions["propulsion"].get("propeller") and is_propeller(spec.propulsion_kind)):
        return res
    hist, sp = [], spec
    keys = ("eta_takeoff", "eta_climb", "eta_cruise")
    for _ in range(5):
        if not res.sizing.converged or res.power_sl is None or not math.isfinite(res.power_sl):
            break
        et = calibrated_etas(res)
        p = sp.assumptions["propulsion"]
        hist.append({**{k: p[k] for k in keys}, **{f"{k} (hélice)": et[k] for k in keys},
                     "P_sl kW": res.power_sl / 1e3, "W0": res.sizing.W0})
        if max(abs(et[k] - p[k]) for k in keys) < 0.005:
            break
        sp = copy.deepcopy(sp)
        q = sp.assumptions["propulsion"]
        if sp.propulsion_kind == "electric":  # keep the battery→shaft chain, swap the propeller part
            q["eta_total"] = q["eta_total"] * et["eta_cruise"] / q["eta_cruise"]
        for k in keys:
            q[k] = float(et[k])
        res = _run_once(sp, strict, systems)
    if hist:
        last = calibrated_etas(res) if res.sizing.converged and res.power_sl else {}
        res.propeller_calibration = {"history": hist, "final": last}
        from .propeller import propeller_for
        pr = propeller_for(res.spec, res.power_sl) if res.power_sl else None
        if pr is not None:
            res.issues += [Issue("info", "Hélice: " + n) for n in pr.notes]
            res.issues.append(Issue("info", "Eficiências da hélice calibradas no mapa (passo fixo): " + ", ".join(
                f"{k} {res.spec.assumptions['propulsion'][k]:.3f}" for k in keys)
                + " (valores iniciais " + ", ".join("%.2f" % spec.assumptions["propulsion"][k] for k in keys) + ")"))
    return res


def _run_once(spec: MissionSpec, strict: bool = False, systems=None) -> DesignResult:
    """:func:`_run_mda` plus, with ``assumptions.assembly.options.balance``, the outer balance loop (P1b): the
    assembly's static margin (x_np AVL without bodies + Torenbeek App. E) and the gear re-placed from the CG feed
    back into the drawing (wing shift, gear masses at their legs) and the MDA is re-run with them until the
    shift settles (≤ 3 outer passes, |Δx| < 1 mm)."""
    import copy as _copy
    res = _run_mda(spec, strict, systems)
    lp = res.assembly_loop
    obj = getattr(res, "_asm_loop", None)
    if not lp or obj is None or not obj.options.get("balance") or not res.sizing.converged:
        return res
    from .assembly.sizing import flight_from_design
    recs = []
    for _ in range(3):
        dx_old = obj.dx_balance
        try:
            rec = obj.balance(res.S, flight_from_design(res), AR=obj.options.get("AR"))
        except Exception as ex:                    # pragma: no cover - AVL runtime failure
            res.issues.append(Issue("warning", f"Balanceamento da montagem falhou: {ex}"))
            break
        recs.append(rec)
        if "note" in rec:
            res.issues.append(Issue("warning", "Balanceamento: " + rec["note"]))
            break
        sp = _copy.deepcopy(spec)
        sp.assumptions["assembly"] = {**lp["spec"], "options": {**obj.options, "_dx": obj.dx_balance,
                                                               "_gear_masses": obj.gear_masses}}
        res = _run_mda(sp, strict, systems)
        if not res.sizing.converged or res.assembly_loop is None:
            break
        obj = res._asm_loop
        if abs(obj.dx_balance - dx_old) < 1e-3 and len(recs) > 1:
            break
    if res.assembly_loop is not None and recs and res.sizing.converged and "note" not in recs[-1]:
        # The MDA just closed on the shift chosen for the previous masses. Place the wing once more
        # on these masses and publish that drawing. No further W0 loop: the last correction is a few
        # millimetres and does not reopen the drag closure (Raymer Sec. 16.3, same balance).
        try:
            rec = obj.balance(res.S, flight_from_design(res), AR=obj.options.get("AR"))
            recs.append(rec)
            if "note" not in rec:
                sp, _ = obj.scaled(res.S)
                res.assembly_loop["spec_scaled"] = sp
        except Exception as ex:                    # pragma: no cover - AVL runtime failure
            res.issues.append(Issue("warning", f"Balanceamento final da montagem falhou: {ex}"))
    if res.assembly_loop is not None and recs:
        res.assembly_loop["balance"] = {"passes": recs, "dx_m": obj.dx_balance, "gear_masses": obj.gear_masses}
        last = recs[-1]
        res.issues.append(Issue("info", f"Montagem balanceada: {', '.join(last['move'])} deslocada "
                                f"{obj.dx_balance:+.3f} m em x; margem estática mínima {last.get('SM_min', math.nan):.1%} "
                                f"(alvo {last['target_static_margin']:.0%}, Raymer Sec. 16.3); trem re-posicionado "
                                "pelo CG"))
    return res


def _run_mda(spec: MissionSpec, strict: bool = False, systems=None) -> DesignResult:
    """Run the Phase-1 MDA. ``systems`` (optional SystemsResult from a previous closure iteration)
    supplies selected-component masses and the sized harness to the component weight build-up."""
    A = spec.assumptions
    # Named configuration shortcuts → generic assembly drawing (opt-in; never overwrite a supplied one).
    if isinstance(A, dict) and not A.get("assembly"):
        from .assembly.shortcuts import resolve_assembly_shortcut
        try:
            drawing, note = resolve_assembly_shortcut(spec)
        except ValueError as ex:
            raise InfeasibleError(str(ex)) from ex
        if drawing is not None:
            A["assembly"] = drawing
            # keep a breadcrumb for reports / tests
            A.setdefault("_shortcut_note", note)
    asm_loop, asm_issue = None, None
    if isinstance(A, dict) and A.get("assembly"):
        # P1b: the generic assembly inside the W0 loop (rescaled to the sized wing each pass)
        import copy as _copy
        from .assembly.loop import AssemblyLoop
        try:
            asm_loop = AssemblyLoop.from_mission(spec)
        except Exception as ex:
            asm_issue = Issue("warning", f"Montagem genérica fora do ciclo (não carregou: {ex})")
        if asm_loop is not None:
            spec = _copy.deepcopy(spec)
            A = spec.assumptions
            A["aero"].update(asm_loop.planform())
    from .aero import gear_drag as _GD
    gear_drag_rep = None
    if isinstance(A, dict) and _GD.requested(A):
        # opt-in (16 nov 2026): scaled fixed-gear area / retracted gear (aero/gear_drag.py) — on a copy of the spec
        if not isinstance((A.get("aero") or {}).get(_GD.MARK), dict):
            import copy as _copy
            spec = _copy.deepcopy(spec)
            A = spec.assumptions
        gear_drag_rep = _GD.prepare(A)
    reqs = spec.requirements
    issues = reqs.validate()
    if asm_issue is not None:
        issues.append(asm_issue)
    if strict and any(i.severity == "error" for i in issues):
        raise InfeasibleError("; ".join(i.message for i in issues if i.severity == "error"))
    if any(i.severity == "error" for i in issues):
        # cannot proceed meaningfully
        raise InfeasibleError("Requirement set inconsistent: " + "; ".join(i.message for i in issues
                                                                           if i.severity == "error"))
    kind = spec.propulsion_kind
    aero_a, geo_a, con_a = A["aero"], A["geometry"], A["constraints"]
    h_cruise = reqs.value("cruise_altitude", con_a["default_cruise_altitude_m"])

    # category-implied stall limit becomes a constraint if stricter (CS-VLA/LSA)
    creqs, cnotes = constraint_requirements(spec)
    issues += [Issue("info", n) for n in cnotes]

    AR, taper = aero_a["AR"], aero_a["taper"]
    sweep = math.radians(aero_a["sweep_c4_deg"])
    fl = aero_a.get("flap") or {"kind": "none"}
    flap = HighLiftDevice(fl.get("kind", "plain"), fl.get("flapped_area_ratio", 0.6), fl.get("chord_extension", 1.0))
    hl = high_lift_summary(aero_a["clmax_airfoil"], sweep, flap)
    # opt-in (tailless trim, 10 nov 2026): CLmax of the drawn tailless wing trimmed with its elevon (no flap),
    # set by :func:`run` from the assembly (assembly.tailless_trim) — replaces clean / take-off / landing CLmax
    _clt = aero_a.get("CLmax_trimmed")

    def _hl_ovr(h):
        return HighLiftSummary(float(_clt), float(_clt), float(_clt)) if _clt else h
    hl = _hl_ovr(hl)

    from .aero.camber_flap import resolve as _cam_resolve
    cam_o, sched = _cam_resolve(aero_a.get("camber_flap")), None
    cam_Re = [None, None]
    # flap-system masses (actuators, hinge increments) when the user gives them (Phase 9 options study)
    cam_items = []
    hl_items = flap_system_items(fl, None, "flap " + fl.get("kind", "plain")) if fl.get("kind", "none") != "none" else []
    e = aero_a["oswald"] or oswald_raymer(AR, sweep)  # refined with sweep_LE after geometry
    CD0 = cd0_equivalent_skin_friction(aero_a["cfe"], aero_a["swet_sref"])
    polar = DragPolar.from_oswald(CD0, AR, e)
    ew, pdata = _empty_model(spec), _prop_data(spec)
    ew_initial = ew
    wmethod = A["weights"].get("method", "components")
    if wmethod == "components" and kind == "jet":
        wmethod = "statistical"
        issues.append(Issue("info", "Component weights: Raymer GA equations not applicable to jets — "
                                    "statistical We/W0 kept (fighter/transport groups: Phase 3)"))
    from .systems_integration import is_uas
    uas = is_uas(spec)
    bd = None
    payload = reqs.value("payload_mass", 0.0)
    crew = reqs.value("crew_mass", 0.0)
    pctx = PropContext(kind, A["propulsion"]["eta_cruise"], A["propulsion"]["eta_climb"],
                       A["propulsion"]["eta_takeoff"])

    # objectives -> design-point criterion (registry 'trade' stage)
    criterion = con_a.get("criterion")
    if criterion is None:
        if any(o.key in ("unit_cost", "mtow_objective") for o in reqs.objectives()):
            criterion = "min_weight" if wmethod == "components" else "min_power"
        else:
            criterion = "max_wing_loading"
    from .structures import v_n_diagram, wing_structure
    fidelity = aero_a.get("fidelity", "handbook")
    if fidelity not in ("handbook", "lowfi"):
        raise InfeasibleError(f"aero.fidelity '{fidelity}' unknown (handbook | lowfi)")
    lowfi_active = False  # handbook loop first; low-fi aero switched on once it converges
    lf = None
    wopts = dict(A["weights"].get("components") or {})
    user_n = wopts.get("limit_load_factor")
    vn_feed = A["structures"]["load_factor_from_vn"] and not user_n and wmethod == "components"
    wing_method = wopts.pop("wing_method", "raymer")
    if wing_method not in ("raymer", "box"):
        raise InfeasibleError(f"weights.components.wing_method '{wing_method}' unknown (raymer | box)")
    n_vn = None
    sres = None
    w_raymer = None
    ws = None
    from .hifi.calibration import load as _load_cal
    from .structures_l1 import (analyse_design, apply_beam_masses, component_masses, flex_requested,
                                mass_kwargs_from_spec, wing_elastic)
    flex_on = flex_requested(A)
    mass_loop = bool(A["structures"].get("mass_in_loop"))
    l1_kw = mass_kwargs_from_spec(spec, uas)
    try:
        _fac = _load_cal(A)
    except (OSError, ValueError, KeyError):
        _fac = {}
    k_EI, k_GJ = float(_fac.get("k_EI", 1.0)), float(_fac.get("k_GJ", 1.0))
    history = []
    config = buildup = None
    converged = False
    W0_prev, CD0_prev = None, None
    K_rigid_last = None
    th_prev = None
    asm_drag = asm_parts = asm_K = None
    asm_mat = (wopts.get("material") or "metal")
    climb_alt = max([L for L in [h_cruise] + [r.params.get("altitude", 0) for r in reqs]], default=0.0)
    for it in range(1, max(A["mda"]["max_iter"], 60 if wmethod == "components" else 0) + 1):
        # first pass: historical W/S guess (Raymer Table 5.5, e.g. GA single 17 psf)
        legs = _legs(spec, polar, ws if ws is not None else con_a["ws_initial_psf"] * 47.88026,
                     hl.CLmax_clean, h_cruise)
        sz = size_takeoff_weight(payload, crew, legs, pdata, ew, climb_alt,
                                 fixed_mass=A["weights"]["fixed_mass_kg"])
        near_singular = sz.converged and sz.empty_fraction + sz.Wf / sz.W0 > 0.98  # growth factor > 50 (seed W0 absurd)
        if (not sz.converged or near_singular) and wmethod == "components" and it == 1 \
                and ew.fixed_fraction != 0.30:
            # the statistical starting value does not close (or closes only near the singularity
            # We/W0 + Wf/W0 → 1, i.e. an absurd W0 seed that sends the component loop into the wrong basin):
            # restart the build-up from a low guess so that the components decide feasibility, not the seed
            issues.append(Issue("info", f"Valor inicial estatístico We/W0 = {sz.empty_fraction:.2f} não fecha "
                                "(We/W0 + Wf/W0 > 0.98); iteração por componentes reiniciada com We/W0 = 0.30."))
            ew = EmptyWeightModel(fixed_fraction=0.30, label="restart guess 0.30 (component loop)")
            sz = size_takeoff_weight(payload, crew, legs, pdata, ew, climb_alt,
                                     fixed_mass=A["weights"]["fixed_mass_kg"])
        if not sz.converged:
            break
        Vc = reqs.value("cruise_speed") or max(L.V for L in legs)
        # gear-down ΔC_D0 of a retracted gear on the previous pass's wing (aero/gear_drag.py; 0 for fixed gear)
        S_gd = sz.W0 * G0 / (ws if ws is not None else con_a["ws_initial_psf"] * 47.88026)
        actx = AeroContext(polar.CD0, polar.K, hl.CLmax_clean, hl.CLmax_takeoff, hl.CLmax_landing,
                           aero_a["CL_ground"], _GD.dcd0_takeoff(aero_a, S_gd), aero_a["mu_roll"], polar.camber)
        ctx = ConstraintContext(actx, pctx, h_cruise, Vc, con_a["cruise_weight_fraction"],
                                con_a["landing_weight_fraction"], con_a["approach_distance_ft"])
        cons = build_constraints(creqs, ctx)
        if not any(c.key == "cruise_speed" for c in cons):
            rho_c = isa(h_cruise).rho
            cons.append(Constraint(f"Cruzeiro implícito {Vc:.0f} m/s", "implied_cruise", "curve",
                                   lambda w, rho_c=rho_c, Vc=Vc, a=actx: _cruise_tw(w, rho_c, Vc, a),
                                   lambda w, Vc=Vc: w * 0 + Vc, h_cruise, pctx.eta_cruise,
                                   note="speed derived from mission-leg rules"))
        def build_config(ws_, W0_=sz.W0):
            return build_configuration(spec, W0_, ws_, AR)

        at = isa(h_cruise)
        n_eng = int(A["propulsion"].get("n_engines", 1))

        def wopts_it():
            o_ = {**wopts, "limit_load_factor": n_vn} if (vn_feed and n_vn) else dict(wopts)
            if cam_items or hl_items:
                o_["items"] = list(wopts.get("items") or []) + hl_items + cam_items
            return o_

        def _box_struct(cfg_, W0_, wing_raymer):
            CLa_ = lf.avl_CLa if (lf is not None and lf.avl_CLa) else lift_curve_slope(
                AR, Vc / at.a, cfg_.wing.sweep_at(cfg_.wing.xc_max_t),
                S_exp_over_S_ref=cfg_.wing.exposed_area(cfg_.fuselage.max_diameter) / cfg_.wing.S,
                fuselage_diameter=cfg_.fuselage.max_diameter, span=cfg_.wing.span)
            return wing_structure(structures_inputs(spec, W0_, cfg_, hl.CLmax_clean, CLa_, Vc, h_cruise, wing_raymer,
                                                    uas, lf.cm0 if lf is not None else 0.0))

        def _apply_box(bd_, cfg_, W0_):
            it_ = [i for i in bd_.items if i.key == "wing"][0]
            sr_ = _box_struct(cfg_, W0_, it_.mass)
            it_.method = (f"caixão da asa (Megson/Bruhn, structures.py) {sr_.box.mass:.2f} kg; Raymer Eq. 15.46 "
                          f"teria {it_.mass:.2f} kg")
            it_.mass = sr_.box.mass
            return sr_

        def empty_mass(ws_, value_):
            from .weights_detailed import component_weights
            P_ = value_ * sz.W0 * G0 if is_propeller(kind) else None
            cfg_ = build_config(ws_)
            bd_ = component_weights(sz.W0, sz.Wf, kind, cfg_, 0.5 * at.rho * Vc**2, Vc / at.a, P_,
                                    wopts_it(), uas, systems, n_eng, payload + crew)
            if wing_method == "box":
                _apply_box(bd_, cfg_, sz.W0)
            if mass_loop:
                CLa_m = lift_curve_slope(
                    AR, Vc / at.a, cfg_.wing.sweep_at(cfg_.wing.xc_max_t),
                    S_exp_over_S_ref=cfg_.wing.exposed_area(cfg_.fuselage.max_diameter) / cfg_.wing.S,
                    fuselage_diameter=cfg_.fuselage.max_diameter, span=cfg_.wing.span)
                eng = next((i.mass for i in bd_.items if i.key in ("engine_installed", "motor_esc")), 0.0)
                apply_beam_masses(bd_, component_masses(
                    cfg_, sz.W0, Vc, hl.CLmax_clean, CLa_m, 0.5 * at.rho * Vc ** 2, engine_mass_kg=eng,
                    altitude=h_cruise, **l1_kw))
            if asm_loop is not None:
                asm_loop.apply_masses(bd_, sz.W0 * G0 / ws_, sz.W0, 0.5 * at.rho * Vc ** 2, asm_mat)
            return bd_.empty

        dp = design_point(cons, pctx, (con_a["ws_min"], con_a["ws_max"]), margin=con_a["margin"],
                          criterion=criterion, weight_fn=empty_mass if wmethod == "components" else None,
                          ws_fixed=con_a.get("ws_fixed"), value_fixed=con_a.get("value_fixed"))
        if not math.isfinite(dp.ws):
            break
        ws = dp.ws
        S = sz.W0 * G0 / ws
        config = build_config(ws)
        wing, fus = config.wing, config.fuselage
        buildup = component_buildup(config, Vc, at.rho, at.mu, at.a, aero_a["laminar"],
                                    ROUGHNESS[aero_a["roughness"]], aero_a["Q"], aero_a["lp_fraction"])
        e = aero_a["oswald"] or oswald_raymer(AR, wing.sweep_at(0.0))
        polar = DragPolar.from_oswald(buildup.CD0, AR, e)
        if lowfi_active:
            from .aero.interfaces import ToolNotAvailable
            from .hifi.calibration import load as _load_cal
            cal_factors = _load_cal(spec.assumptions)
            from .aero.lowfi import lowfi_aero
            Vs_ = math.sqrt(2 * sz.W0 * G0 / (isa(0).rho * S * hl.CLmax_clean))
            try:
                lf = lowfi_aero(config, buildup, Vc, at.rho, at.mu, at.a, AR, aero_a["laminar"].get("wing", 0.1),
                                (aero_a["Q"] or {}).get("wing", 1.0), aero_a["lp_fraction"], hl.CLmax_clean, Vs_, e,
                                prefer=aero_a.get("airfoil_solver", "xfoil"), calibration=cal_factors)
                polar = DragPolar(lf.CD0, lf.K)
                hl = high_lift_summary(lf.clmax_airfoil, sweep, flap)
                hl = _hl_ovr(hl)
            except (ToolNotAvailable, RuntimeError, ImportError) as ex:
                issues.append(Issue("warning", f"aero.fidelity lowfi indisponível ({ex}); mantido o método de manual"))
                fidelity, lowfi_active, lf = "handbook", False, None
        if asm_loop is not None:
            # P1b: zero-lift drag of the assembly rescaled to this pass's wing (nominal or pessimistic CD0)
            asm_drag = asm_loop.drag(S, Vc, at.rho, at.mu, at.a, aero_a.get("extra_drag_areas_m2"))
            cd0_a = asm_loop.cd0(asm_drag)
            K_a, asm_K = asm_loop.K(S, Vc / at.a, cd0_a, polar.K)
            polar = DragPolar(cd0_a, K_a, getattr(polar, "camber", None))
        if cam_o:
            # Phase 9: camber-flap option → envelope polar ΔCD(CL) ≤ 0 and ΔCLmax at the largest deflection
            from .aero.camber_flap import wing_camber_schedule
            from .aero.interfaces import ToolNotAvailable as _TNA
            # base high lift recomputed every pass (no accumulation of ΔCLmax across iterations)
            hl = high_lift_summary(lf.clmax_airfoil if lf is not None else aero_a["clmax_airfoil"], sweep, flap)
            hl = _hl_ovr(hl)
            Vs_c = math.sqrt(2 * sz.W0 * G0 / (isa(0).rho * S * hl.CLmax_clean))
            Re_now = at.rho * Vc * config.wing.mac / at.mu
            try:
                # hysteresis: keep the schedule while Re stays within ±8 % of the one it was built at (a polar
                # rebuilt at every W/S flicker would make the MDA oscillate between two Re bins)
                if sched is None or abs(Re_now / cam_Re[0] - 1) > 0.08 or cam_Re[1] != lowfi_active:
                    cam_Re[:] = [Re_now, lowfi_active]
                    sched = wing_camber_schedule(config, cam_o, Vc, at.rho, at.mu, at.a,
                                                 aero_a["laminar"].get("wing", 0.1), (aero_a["Q"] or {}).get("wing", 1.0),
                                                 aero_a["lp_fraction"], Vs_c, hl.CLmax_clean,
                                                 prefer=aero_a.get("airfoil_solver", "xfoil"), sweep=sweep)
                polar = DragPolar(polar.CD0, polar.K, sched)
                if getattr(sched, "trim_drag_status", "omitted") == "unassessed":
                    issues.append(Issue("warning", "camber flap trim drag unassessed — "
                                        + str((sched.trim_meta or {}).get("reason")
                                              or "missing HT/cm0; not treated as zero")))
                if getattr(sched, "gap_drag_status", "omitted") == "unassessed":
                    issues.append(Issue("warning", "camber flap gap drag unassessed — "
                                        + str((sched.gap_meta or {}).get("note")
                                              or "provide gap.dCD with source or gap.sealed")))
                land = hl.CLmax_landing + sched.dCLmax
                if cam_o.get("landing_deflection", True):
                    # the camber flap is a plain flap: deflected to its landing position it gives at least the
                    # Raymer plain-flap increment (Table 12.2, Eq. 12.21) on its own flapped area — sailplane
                    # practice (Thomas 1999 Ch. 5: camber flaps double as landing flaps). PRESSUPOSTO, switch off
                    # with camber_flap.landing_deflection: false (e.g. flaperons kept for roll on approach)
                    hp = high_lift_summary(lf.clmax_airfoil if lf is not None else aero_a["clmax_airfoil"], sweep,
                                           HighLiftDevice("plain", sched.flapped_area_ratio, 1.0))
                    land = max(land, hp.CLmax_landing)
                hl = HighLiftSummary(hl.CLmax_clean, land, max(hl.CLmax_clean, 0.8 * land))  # Raymer Sec. 5.3
                hl = _hl_ovr(hl)
                cam_items[:] = flap_system_items(cam_o, sched.flap_area_m2, "camber flap " + cam_o["kind"])
            except (_TNA, RuntimeError, ImportError, ValueError) as ex:
                issues.append(Issue("warning", f"camber flap: polares indisponíveis ({ex}); opção ignorada"))
                cam_o, sched = None, None
        # One scale of the rigid polar. The next iteration's constraints, and this iteration's
        # electric energy, see K_flex = K_rigid · CDi_flex/CDi_rigid. Not compounded.
        dth = 0.0
        th_now = kr_now = None
        if flex_on and config is not None and math.isfinite(sz.W0) and config.wing.S > 0:
            dth = 1.0
            try:
                box_now = _box_struct(config, sz.W0, w_raymer)
                q_c = 0.5 * at.rho * Vc ** 2
                CL_c = sz.W0 * G0 / (q_c * config.wing.S)
                corr = wing_elastic(config.wing, box_now.box, q_c, CL_c, k_EI=k_EI, k_GJ=k_GJ,
                                    cm0=(lf.cm0 if lf is not None else 0.0),
                                    y_clamp=config.fuselage.max_diameter / 2.0)
                K_rigid_last = polar.K
                if corr.K_ratio and math.isfinite(corr.K_ratio) and corr.K_ratio > 0:
                    polar = DragPolar(polar.CD0, K_rigid_last * corr.K_ratio, getattr(polar, "camber", None))
                    kr_now = corr.K_ratio
                th_now = corr.tip_twist_deg
                dth = abs(th_now - th_prev) if th_prev is not None else 1.0
                th_prev = th_now
            except Exception as ex:
                issues.append(Issue("warning", f"Torção elástica L1 indisponível nesta iteração: {ex}"))
        h = {"iter": it, "W0": sz.W0, "We/W0 usado": sz.empty_fraction, "We": sz.We, "Wf": sz.Wf}
        dE = 0.0
        if kind == "electric" and dp.metric == "P/W":
            # Phase 3 fix: take-off + climb energy from the same segment model as the mission verification
            from .performance import PerfModel, takeoff_climb_energy
            pm_ = PerfModel.from_state(spec, S, polar, hl, dp.value * sz.W0 * G0, None)
            tce = takeoff_climb_energy(pm_, sz.W0, h_cruise)
            e_new = tce["total"] / sz.W0
            e_old = pdata.takeoff_climb_J_per_kg
            dE = abs(e_new / e_old - 1) if e_old else 1.0
            pdata.takeoff_climb_J_per_kg = e_new
            h.update({"E descolagem+subida [Wh]": tce["total"] / 3600})
            if not tce["complete"]:
                issues.append(Issue("warning", f"Subida (segmentos) não atinge {h_cruise:.0f} m (pára a "
                                    f"{tce['h_reached']:.0f} m): energia de subida subestimada"))
        dWe = 0.0
        if wmethod == "components":
            from .weights_detailed import component_weights
            P_sl = dp.value * sz.W0 * G0 if dp.metric == "P/W" else None
            bd = component_weights(sz.W0, sz.Wf, kind, config, 0.5 * at.rho * Vc**2, Vc / at.a, P_sl,
                                   wopts_it(), uas, systems, n_eng, payload + crew)
            w_raymer = [i.mass for i in bd.items if i.key == "wing"][0]
            if wing_method == "box":
                sres = _apply_box(bd, config, sz.W0)
            else:
                sres = _box_struct(config, sz.W0, w_raymer)
            if mass_loop:
                eng = next((i.mass for i in bd.items if i.key in ("engine_installed", "motor_esc")), 0.0)
                CLa_m = lift_curve_slope(
                    AR, Vc / at.a, config.wing.sweep_at(config.wing.xc_max_t),
                    S_exp_over_S_ref=config.wing.exposed_area(config.fuselage.max_diameter) / config.wing.S,
                    fuselage_diameter=config.fuselage.max_diameter, span=config.wing.span)
                apply_beam_masses(bd, component_masses(
                    config, sz.W0, Vc, hl.CLmax_clean, CLa_m, 0.5 * at.rho * Vc ** 2,
                    engine_mass_kg=eng, altitude=h_cruise, **l1_kw))
            if asm_loop is not None:
                asm_parts = asm_loop.apply_masses(bd, S, sz.W0, 0.5 * at.rho * Vc ** 2, asm_mat)
            n_new = sres.vn.n_limit_pos
            h.update({"n_lim (V-n)": n_new, "asa Raymer [kg]": w_raymer, "asa caixão [kg]": sres.box.mass})
            relax = A["weights"].get("relaxation", 1.0)
            We_new = (1 - relax) * sz.We + relax * bd.empty
            dWe = abs(bd.empty / sz.We - 1)
            h.update({"We_comp": bd.empty, "We_comp/W0": bd.empty / sz.W0})
            ew = EmptyWeightModel(empty_mass_kg=We_new, label=f"component build-up (iteration {it})")
        h.update({"CD0": polar.CD0, "W/S": ws, dp.metric: dp.value, "L/D_max": polar.LD_max,
                  "aero": "lowfi" if lowfi_active else "manual"})
        if th_now is not None:
            h.update({"torção ponta [deg]": th_now, "K_flex/K_rigido": kr_now})
        if asm_drag is not None:
            h.update({"montagem k": asm_loop.k(S), "CD0 montagem nominal": asm_drag["CD0_nominal"],
                      "CD0 montagem pessimista": asm_drag["CD0_pessimistic"]})
            if asm_parts is not None:
                h["estrutura montagem [kg]"] = sum(p.mass_kg for p in asm_parts)
        history.append(h)
        tol = A["mda"]["tol"]
        if lowfi_active:
            # AVL/XFOIL outputs carry 4–5 significant figures (and the section-polar cache is on a Mach grid of
            # 0.01): the fixed point cannot be resolved below ~1e-4 — documented low-fi tolerance
            tol = max(tol, A["mda"].get("tol_lowfi", 2e-4))
        dn = 0.0
        if wmethod == "components" and vn_feed:
            dn = abs(n_new / n_vn - 1) if n_vn else 1.0
            n_vn = n_new
        if (W0_prev and abs(sz.W0 / W0_prev - 1) < tol and abs(polar.CD0 / CD0_prev - 1) < tol
                and dWe < 10 * tol and dn < 10 * tol and dE < 10 * tol and dth < 0.02):
            if fidelity == "lowfi" and not lowfi_active:
                lowfi_active = True  # switch to low-fi aero and re-converge
                W0_prev = None
                continue
            converged = True
            break
        W0_prev, CD0_prev = sz.W0, polar.CD0

    if not sz.converged:
        dp = DesignPoint(math.nan, math.nan, "P/W" if is_propeller(kind) else "T/W", False, message=sz.message)
        res = DesignResult(spec, sz, dp, [], polar, None, hl, math.nan, None, legs, math.nan, h_cruise, it, False,
                           issues, history=history)
        res.issues.append(Issue("error", sz.message))
        return res

    CLa = lift_curve_slope(AR, Vc / isa(h_cruise).a, config.wing.sweep_at(config.wing.xc_max_t),
                           S_exp_over_S_ref=config.wing.exposed_area(fus.max_diameter) / config.wing.S,
                           fuselage_diameter=fus.max_diameter, span=config.wing.span)
    res = DesignResult(spec, sz, dp, cons, polar, config, hl, CLa, buildup, legs, Vc, h_cruise, it, converged,
                       issues, history=history, weights=bd, weight_initial_source=ew_initial.source(), lowfi=lf)
    if asm_loop is not None and asm_drag is not None:
        from .assembly.loop import LOOP_ASSUMPTIONS
        sp_final, _ = asm_loop.scaled(S)
        res._asm_loop = asm_loop
        res.assembly_loop = {"options": asm_loop.options, "spec": asm_loop.spec, "spec_scaled": sp_final,
                             "scaling": sp_final.get("_scaling"), "K": asm_K, "K_notes": asm_loop.K_notes,
                             "k": asm_loop.k(S), "S_drawn_m2": asm_loop.S0, "S_sized_m2": S, "drag": asm_drag,
                             "parts": [p.__dict__ for p in (asm_parts or [])], "iterations": it,
                             "converged": converged, "assumptions": LOOP_ASSUMPTIONS,
                             "flying_wing": getattr(asm_loop, "flying_wing_report", None)}
        issues.append(Issue("info", f"Montagem genérica no ciclo W0: k = {asm_loop.k(S):.4f} (S {asm_loop.S0:.3f} → "
                            f"{S:.3f} m²), CD0 {asm_drag['CD0_nominal']:.5f} nominal / {asm_drag['CD0_pessimistic']:.5f} "
                            f"pessimista (usado: {asm_loop.options['close_on']}), {it} iterações"
                            + ("" if converged else " (não convergiu)")))
        if wmethod != "components":
            issues.append(Issue("warning", "Montagem no ciclo: weights.method não é 'components' — só o CD0 da "
                                "montagem entra (as massas por peça precisam do caminho por componentes)"))
    if gear_drag_rep is not None:
        res.gear_drag = _GD.summary(gear_drag_rep, S, polar.CD0)
        _r = _GD.row(res.gear_drag)
        if _r:
            res.checks.append(CheckResult(*_r))
    if sched is not None:
        sm = sched.summary()
        issues.append(Issue("info", f"Camber flap ({sched.kind}): ΔCD mín {sm['dCD_min']:+.5f} a CL {sm['CL_at_dCD_min']:.2f}, "
                            f"ΔCLmax {sched.dCLmax:+.3f} (δ {sched.delta_max:+g}°), L/D max {polar.LD_max:.2f} vs "
                            f"{DragPolar(polar.CD0, polar.K).LD_max:.2f} sem flap. " + "; ".join(sched.notes)))
        # Opt-in trim/gap: assessed → pass; unassessed → ok=None (never a silent pass); omitted → no check
        ts, gs = sched.trim_drag_status, sched.gap_drag_status
        if ts == "assessed":
            res.checks.append(CheckResult(
                "aero:camber_trim_drag", True,
                f"HT induced trim ΔCD from Δcm0(δ*) assessed (max {float((sched.trim_meta or {}).get('dCD_trim_max', float('nan'))):.5f}); "
                f"Nelson/Etkin V_H balance"))
        elif ts == "unassessed":
            res.checks.append(CheckResult(
                "aero:camber_trim_drag", None,
                "camber trim drag unassessed — " + str((sched.trim_meta or {}).get("reason")
                                                       or "missing data; not treated as zero")))
        if gs == "assessed":
            res.checks.append(CheckResult(
                "aero:camber_gap_drag", True,
                f"gap ΔCD={sched.dCD_gap} ({(sched.gap_meta or {}).get('source') or (sched.gap_meta or {}).get('note')})"))
        elif gs == "unassessed":
            res.checks.append(CheckResult(
                "aero:camber_gap_drag", None,
                "camber gap drag unassessed — " + str((sched.gap_meta or {}).get("note")
                                                      or "provide gap.dCD+source or gap.sealed")))
    # structures stage result on the final design (Schrenk loading; AVL loading added by the stability stage)
    try:
        res.structures = wing_structure(structures_inputs(spec, sz.W0, config, hl.CLmax_clean,
                                                          lf.avl_CLa if (lf and lf.avl_CLa) else CLa, Vc, h_cruise,
                                                          w_raymer, uas, lf.cm0 if lf else 0.0))
        vn = res.structures.vn
        if vn_feed:
            issues.append(Issue("info", f"Nz das equações de massa = 1.5 × n_lim do diagrama V-n ({vn.n_limit_pos:.2f}, "
                                f"{vn.governing}; {vn.regulation})"))
        for nt in vn.notes:
            issues.append(Issue("warning", nt))
        r = res.structures.box.mass / w_raymer if w_raymer else None
        if r is not None:
            issues.append(Issue("info", f"Massa do caixão da asa (Megson/Bruhn) = {res.structures.box.mass:.2f} kg vs "
                                f"Raymer Eq. 15.46 {w_raymer:.2f} kg (razão {r:.2f}); usado: "
                                f"{'caixão' if wing_method == 'box' else 'Raymer'}"))
    except Exception as ex:  # pragma: no cover - keep sizing usable
        issues.append(Issue("warning", f"Estágio de estruturas falhou: {ex}"))
    # L1 beam on the converged design, even when flex is off (masses and deflections in result.json).
    # The polar is rescaled once from the last rigid K, so the reported K matches elastic.K_ratio.
    try:
        res.structures_l1 = analyse_design(res, k_EI, k_GJ, elastic=True)
        el = res.structures_l1.elastic
        if (flex_on and el is not None and el.K_ratio and math.isfinite(el.K_ratio) and el.K_ratio > 0
                and K_rigid_last is not None):
            el.applied = True
            res.polar = DragPolar(res.polar.CD0, K_rigid_last * el.K_ratio, getattr(res.polar, "camber", None))
            issues.append(Issue(
                "info",
                f"Correção elástica L1 no ciclo: K_flex/K_rígido = {el.K_ratio:.4f}, "
                f"torção de ponta em cruzeiro {el.tip_twist_deg:.3f}°. "
                f"CLα de manual mantido ({res.CLalpha:.3f} /rad); CLα flexível {el.CLa_flex:.3f} /rad."))
        ratio = res.structures_l1.masses.get("fuselage_over_raymer")
        if ratio is not None and math.isfinite(ratio):
            msg = (f"Massa da fuselagem L1 / Raymer Eq. 15.49 = {ratio:.2f} "
                   f"({res.structures_l1.masses['fuselage_kg']:.1f} kg vs "
                   f"{res.structures_l1.masses['fuselage_raymer_kg']:.1f} kg).")
            issues.append(Issue("info" if 0.75 <= ratio <= 1.25 else "warning", msg))
    except Exception as ex:
        issues.append(Issue("warning", f"Modelo estrutural L1 falhou: {ex}"))
    if kind == "electric" and pdata.takeoff_climb_J_per_kg is not None:
        issues.append(Issue("info", f"Energia de descolagem + subida no dimensionamento = "
                            f"{pdata.takeoff_climb_J_per_kg * sz.W0 / 3600:.1f} Wh (modelo de segmentos: 1 min à "
                            "potência de descolagem + subida integrada a V_y — o mesmo da verificação; Hepperle só "
                            f"energia potencial daria {sz.W0 * G0 * h_cruise / pdata.eta_tot / 3600:.1f} Wh)"))
    from .weights import CROSS_CHECK_CLASSES, statistical_bracket
    res.weight_cross_check = statistical_bracket(sz.W0, CROSS_CHECK_CLASSES["uav" if uas else "ga"])
    if bd is not None:
        res.issues += [Issue("info", n) for n in bd.notes]
        fr = bd.empty / sz.W0
        stats = [r["We/W0"] for r in res.weight_cross_check if r["in_range"] is not False and r["We/W0"] < 1.0]
        if stats and not (0.85 * min(stats) <= fr <= 1.15 * max(stats)):
            res.issues.append(Issue("warning", f"We/W0 por componentes = {fr:.3f} fora da banda estatística "
                                    f"[{min(stats):.2f}, {max(stats):.2f}] (±15 %) — "
                                    + ("rever itens em falta (recuperação, suportes, pintura, cablagem de sinal) "
                                       "ou calibrar com dados próprios." if fr < min(stats) else
                                       "requisitos exigentes (potência instalada/estrutura) ou pressupostos "
                                       "conservadores — rever massa do motor, categoria estrutural e "
                                       "o requisito ativo.")))
    if not dp.feasible and dp.message:
        res.issues.append(Issue("error", dp.message))

    # cost (trade/check stage) when requested
    if reqs.get("unit_cost"):
        res.cost = unit_cost_estimate(spec, sz.We, res.power_sl, Vc)
        if spec.aircraft_class.startswith("uav"):
            res.issues.append(Issue("warning", "Eastlake cost model calibrated on GA aircraft; UAV cost is outside "
                                    "its validity (use for relative trades only)"))

    lr = (spec.assumptions or {}).get("launch_recovery")
    if lr:   # opt-in catapult / belly landing (first order); absent → nothing runs
        from .launch_recovery import launch_recovery_stage
        try:
            launch_recovery_stage(res, lr)
        except Exception as ex:  # noqa: BLE001 — reported, never a silent pass
            res.checks.append(CheckResult("lr:launch_recovery", None, f"lançamento/recuperação não avaliado: {ex}"))
    hs = handlers("check")
    for r in reqs.by_stage("check"):
        if r.key in hs:
            res.checks.append(hs[r.key](r, res))
    if not converged:
        res.issues.append(Issue("warning", f"MDA not converged in {it} iterations"))
    return res
