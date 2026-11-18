"""Design point -> systems selection, with mass/energy closure back to sizing.

Flow (classical 'iterate sizing with refined component data', Raymer 6th ed.
Ch. 19; Gundlach, *Designing Unmanned Aircraft Systems*, AIAA):
1. P_SL from the design point -> propeller -> motor Kv/power -> ESC.
2. Battery energy from the sizing energy equations -> S/P pack -> C-rate check.
3. Hinge moments at V_D -> servos.  4. Autopilot by requirement filter.
5. Power budget (avionics + payload + servos) -> regulators, harness gauges.
6. Pack-level specific energy and avionics power are fed back to the sizing
   assumptions, and the selected-component masses + sized harness feed the
   component weight build-up (``weights_detailed``); the aircraft is re-sized
   until battery, systems power, systems mass and W0 stop changing (fixed point).
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field

from acdt import G0
from acdt.core.atmosphere import isa
from acdt.core.systems.avionics import AutopilotRequirements, Load, PowerBudget, select_autopilot
from acdt.core.systems.battery import BatteryPack, best_pack
from acdt.core.systems.compliance import checklist_markdown
from acdt.core.systems.database import ComponentDB, load_default_db
from acdt.core.systems.electric_propulsion import MotorChoice, PropellerSizing, select_motor_esc, size_propeller
from acdt.core.systems.motor_deck import assess_motor
from acdt.core.systems.harness import Connector, Harness, Wire
from acdt.core.systems.mass import MassItem
from acdt.core.systems.servos import SurfaceLoad, size_control_surfaces

UAS_CATEGORIES = {"easa_open", "easa_specific", "easa_certified", "stanag_4703", "stanag_4671"}


@dataclass
class SystemsResult:
    propeller: PropellerSizing | None = None
    motor: MotorChoice | None = None
    battery: BatteryPack | None = None
    servos: list[SurfaceLoad] = field(default_factory=list)
    autopilot: dict | None = None
    autopilot_rejected: list[str] = field(default_factory=list)
    power_budget: PowerBudget | None = None
    harness: Harness | None = None
    gauges: dict = field(default_factory=dict)
    checklist_md: str = ""
    masses: list[MassItem] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    closure_history: list[dict] = field(default_factory=list)
    pinned_ok: bool = True  # False when a pinned motor, ESC or cell misses its rating

    @property
    def systems_mass(self) -> float:
        return sum(m.mass for m in self.masses if m.name != "battery")


def is_uas(spec) -> bool:
    return (spec.aircraft_class.startswith("uav") or spec.requirements.value("regulatory_category") in UAS_CATEGORIES
            or (spec.systems or {}).get("uas", False))


def select_systems(res, sysspec: dict | None = None, db: ComponentDB | None = None) -> SystemsResult:
    spec = res.spec
    ss = sysspec if sysspec is not None else (spec.systems or {})
    db = (db or load_default_db()).merged(ss.get("components"))
    out = SystemsResult()
    kind = spec.propulsion_kind
    W0 = res.sizing.W0
    at_sl = isa(0.0)
    at_c = isa(res.cruise_altitude)
    electric = kind == "electric"
    S_series = int(ss.get("bus_cells_series", 12))
    chem = ss.get("cell_chemistry")
    v_bus_nom = None

    # ---- propulsion ----
    if electric and res.power_sl:
        n_mot = int(ss.get("n_motors", 1))
        P_m = res.power_sl / n_mot
        pr = ss.get("propeller", {})
        method = str(pr.get("method") or "raymer").lower()
        if method == "bemt":
            from acdt.domains.aircraft.systems_bemt import size_propeller_bemt
            out.propeller = size_propeller_bemt(pr, P_m, res.cruise_speed, res.cruise_altitude or 0.0, kind)
            if out.propeller.status != "ok":
                out.messages.append(out.propeller.note or "BEMT unassessed")
        else:
            out.propeller = size_propeller(P_m, res.cruise_speed, at_sl.rho, at_sl.a, pr.get("blades", 2),
                                           pr.get("D_max_m"), pr.get("cp_static", 0.05), pr.get("J_cruise", 0.7),
                                           pr.get("tip_mach_limit", 0.7))
        cells = [c for c in db.cells if chem in (None, c["chemistry"])]
        ref_cell = cells[0]
        v_bus_nom = S_series * ref_cell["v_nom"]
        v_bus_max = S_series * ref_cell["v_max"]
        mo = ss.get("motor", {})
        prop_ok = out.propeller is not None and getattr(out.propeller, "status", "ok") == "ok"
        if not prop_ok:
            out.messages.append("motor/ESC não selecionados: hélice BEMT unassessed (unassessed≠pass)")
        else:
            out.motor = select_motor_esc(db, P_m, out.propeller.rpm_max, v_bus_nom, v_bus_max,
                                         mo.get("power_margin", 1.2), mo.get("kv_tolerance", 0.25),
                                         mo.get("load_ratio", 0.85), mo.get("eta_motor", 0.85), mo.get("esc_margin", 1.2),
                                         motor_id=mo.get("id"), esc_id=ss.get("esc_id"))
            out.messages += out.motor.messages
            if mo.get("deck") is not None:
                deck = assess_motor(mo["deck"], V_V=v_bus_nom, rpm=out.propeller.rpm_max)
                out.motor.deck = deck
                if deck.get("status") == "ok" and deck.get("I_A") is not None:
                    out.motor.i_max = float(deck["I_A"])
                    out.messages.append(
                        f"deck Drela 2007 aplicado (fonte: {deck.get('source')}): "
                        f"I={deck['I_A']:.2f} A, η={deck['efficiency']}")
                else:
                    out.messages.append(
                        "deck de motor unassessed — η/load_ratio constantes não são um resultado de deck "
                        f"({', '.join(deck.get('unassessed_terms') or deck.get('issues') or ['incomplete'])})")
            if out.motor.motor:
                out.masses.append(MassItem("motor(s)", n_mot * out.motor.motor["mass"]))
            if out.motor.esc:
                out.masses.append(MassItem("ESC(s)", n_mot * out.motor.esc["mass"]))

    # ---- servos ----
    sv = ss.get("servos", {})
    vmax = spec.requirements.value("max_speed") or res.cruise_speed
    V_D = sv.get("V_dive_m_s") or 1.25 * vmax
    out.servos = size_control_surfaces(res.config, V_D, at_sl.rho, db.servos, sv.get("v_bus", 8.4),
                                       sv.get("Ch_alpha", -0.25), sv.get("Ch_delta", -0.60), sv.get("alpha_deg", 8.0),
                                       sv.get("delta_deg", 25.0), sv.get("aileron_span_frac", 0.35),
                                       sv.get("aileron_chord_frac", 0.25), sv.get("elevator_chord_frac", 0.35),
                                       sv.get("rudder_chord_frac", 0.35), sv.get("linkage_ratio", 1.0),
                                       sv.get("factor_of_safety", 1.5))
    for s in out.servos:
        if s.servo is None:
            out.messages.append(f"No servo for {s.name}: required {s.torque_required:.2f} N·m — use a linkage "
                                "ratio, split the surface or add a stronger servo to the DB")
        else:
            out.masses.append(MassItem(f"servo {s.name}", s.n_servos * s.servo["mass"]))

    # ---- autopilot ----
    ap = ss.get("autopilot", {})
    out.autopilot, out.autopilot_rejected = select_autopilot(db.autopilots, AutopilotRequirements(
        ap.get("min_imu", 1), ap.get("min_baro", 1), ap.get("min_can", 0), ap.get("ethernet", False),
        ap.get("firmware"), ap.get("max_mass")))
    if out.autopilot:
        out.masses.append(MassItem(f"autopilot {out.autopilot['id']}", out.autopilot["mass"]))
    else:
        out.messages.append("No autopilot satisfies the requirements: " + "; ".join(out.autopilot_rejected))

    # ---- power budget ----
    pb = PowerBudget(regulator_margin=ss.get("regulator_margin", 1.5))
    if out.autopilot:
        pb.loads.append(Load(f"autopilot {out.autopilot['id']}", out.autopilot["power_w"]))
    for L in ss.get("loads", []):
        pb.loads.append(Load(L["name"], L["power_w"], L.get("duty", 1.0), L.get("peak_w"), L.get("bus", "avionics")))
    for s in out.servos:
        if s.servo:
            v = sv.get("v_bus", 8.4)
            pb.loads.append(Load(f"servo {s.name} x{s.n_servos}", s.n_servos * sv.get("avg_power_w", 1.0),
                                 1.0, s.n_servos * s.servo["i_stall"] * v, "servo"))
    for m in ss.get("extra_masses", []):
        out.masses.append(MassItem(m["name"], m["mass"], m.get("x")))
    out.power_budget = pb

    # ---- battery ----
    if electric and res.sizing.energy_J:
        i_peak = (out.motor.i_max * int(ss.get("n_motors", 1)) if out.motor else 0) + pb.peak_w / (v_bus_nom or 1)
        cells = [c for c in db.cells if chem in (None, c["chemistry"])]
        if ss.get("cell_id"):
            cells = [c for c in cells if c["id"] == ss["cell_id"]] or cells
        out.battery = best_pack(cells, res.sizing.energy_J, i_peak, lambda c: S_series,
                                ss.get("pack_overhead", 1.20), chem)
        out.masses.append(MassItem("battery", out.battery.mass))
        if not out.battery.current_ok:
            out.messages.append("Battery C-rate exceeded")

    # ---- harness (power distribution) ----
    if electric and out.motor:
        hl = ss.get("harness", {})
        h = Harness(f"{spec.name} power harness")
        h.add_connector(Connector("BAT", ["+", "-"], "XT90-class"))
        h.add_connector(Connector("ESC", ["+", "-"], ""))
        h.add_connector(Connector("PDB", ["+", "-", "5V", "GND", "SERVO+", "SERVO-"], "power distribution board"))
        h.add_connector(Connector("AP", ["5V", "GND"], out.autopilot["id"] if out.autopilot else "autopilot"))
        h.add_connector(Connector("SRV", ["+", "-"], "servo rail"))
        Lb = hl.get("battery_to_esc_m", 0.5)
        h.connect(Wire("W1", ("BAT", "+"), ("ESC", "+"), "VBAT", out.motor.i_max, Lb, v_bus_nom, color="RD"))
        h.connect(Wire("W2", ("BAT", "-"), ("ESC", "-"), "GND", out.motor.i_max, Lb, v_bus_nom, color="BK"))
        i_av = pb.bus_peak("avionics") / 5.0
        La = hl.get("pdb_to_autopilot_m", 0.3)
        h.connect(Wire("W3", ("PDB", "5V"), ("AP", "5V"), "5V_AV", i_av, La, 5.0, color="RD"))
        h.connect(Wire("W4", ("PDB", "GND"), ("AP", "GND"), "GND_AV", i_av, La, 5.0, color="BK"))
        i_sv = pb.bus_peak("servo") / sv.get("v_bus", 8.4)
        Ls = hl.get("pdb_to_servo_rail_m", 1.0)
        h.connect(Wire("W5", ("PDB", "SERVO+"), ("SRV", "+"), "VSERVO", i_sv, Ls, sv.get("v_bus", 8.4), color="RD"))
        h.connect(Wire("W6", ("PDB", "SERVO-"), ("SRV", "-"), "GND_SRV", i_sv, Ls, sv.get("v_bus", 8.4), color="BK"))
        out.gauges = h.size_wires(hl.get("max_drop_fraction", 0.03), hl.get("temp_c", 60.0))
        out.harness = h

    mo = ss.get("motor") or {}
    if mo.get("id") and (out.motor is None or out.motor.motor is None or not out.motor.feasible):
        out.pinned_ok = False
    if ss.get("esc_id") and (out.motor is None or out.motor.esc is None or not out.motor.esc_feasible):
        out.pinned_ok = False
    if ss.get("cell_id") and (out.battery is None or not out.battery.current_ok):
        out.pinned_ok = False
    feats = {"li_battery"} if electric else set()
    out.checklist_md = checklist_markdown(spec.requirements.value("regulatory_category"), W0, is_uas(spec), feats)
    return out


def catalog_ids(systems) -> dict:
    """Motor, ESC and cell ids of a systems result. Missing components are None.

    The propeller is not in this set: default ``size_propeller`` is Raymer's continuous diameter (Sec. 10.3);
    opt-in BEMT (``systems.propeller.method: bemt``) is also geometry, not a catalogue.
    ``components.yaml`` has no propeller catalogue.
    """
    motor = esc = cell = None
    if systems is not None and getattr(systems, "motor", None) is not None:
        if systems.motor.motor:
            motor = systems.motor.motor.get("id")
        if systems.motor.esc:
            esc = systems.motor.esc.get("id")
    if systems is not None and getattr(systems, "battery", None) is not None:
        cell = systems.battery.cell.get("id")
    return {"motor_id": motor, "esc_id": esc, "cell_id": cell}


def apply_catalog_pin(spec, ids: dict, *, cell_fixed: bool = False):
    """Write the catalog assignment onto ``spec.systems`` so the next closure cannot switch it."""
    ss = dict(spec.systems or {})
    motor = dict(ss.get("motor") or {})
    if ids.get("motor_id"):
        motor["id"] = ids["motor_id"]
    else:
        motor.pop("id", None)
    ss["motor"] = motor
    if ids.get("esc_id"):
        ss["esc_id"] = ids["esc_id"]
    else:
        ss.pop("esc_id", None)
    if not cell_fixed:
        if ids.get("cell_id"):
            ss["cell_id"] = ids["cell_id"]
        else:
            ss.pop("cell_id", None)
    spec.systems = ss
    return spec


def clear_catalog_pin(spec, *, keep_cell: bool = False):
    """Drop a catalog pin so selection can run again. A user-set cell id can be kept."""
    ss = dict(spec.systems or {})
    motor = dict(ss.get("motor") or {})
    motor.pop("id", None)
    ss["motor"] = motor
    ss.pop("esc_id", None)
    if not keep_cell:
        ss.pop("cell_id", None)
    spec.systems = ss
    return spec


def run_with_systems(spec, max_iter: int = 15, tol: float = 0.01):
    """Re-size the aircraft with the pack-level specific energy and power budget from
    the selected systems until both stop changing (closure)."""
    from .sizing import run

    spec = copy.deepcopy(spec)
    hist = []
    res = sysres = None
    W0_prev = msys_prev = None
    for k in range(max_iter):
        res = run(spec, systems=sysres)  # selected-component masses feed the weight build-up
        if not res.sizing.converged or not math.isfinite(res.design_point.ws):
            return res, None
        sysres = select_systems(res)
        res.systems = sysres
        pa = spec.assumptions["propulsion"]
        avg = sysres.power_budget.average_w if sysres.power_budget else 0.0
        e_pack = pa["battery_Wh_kg"]
        if sysres.battery:
            c = sysres.battery.cell
            # intrinsic pack-level specific energy of the chosen cell (independent of P rounding)
            e_pack = c["v_nom"] * c["capacity_ah"] / (c["mass"] * spec.systems.get("pack_overhead", 1.20))
            spec.systems = {**spec.systems, "cell_id": c["id"]}  # freeze the cell type -> fixed point
        msys = sysres.systems_mass
        hist.append({"iter": k + 1, "W0": res.sizing.W0, "We": res.sizing.We, "systems_kg": msys,
                     "battery_Wh_kg": pa["battery_Wh_kg"],
                     "pack_Wh_kg": e_pack, "systems_power_W": pa["systems_power_W"], "budget_W": avg,
                     "battery_mass_alloc": res.sizing.Wf,
                     "battery_mass_sel": sysres.battery.mass if sysres.battery else None})
        if not (spec.systems or {}).get("close_loop", True):
            break
        electric = spec.propulsion_kind == "electric"
        de = abs(e_pack / pa["battery_Wh_kg"] - 1) if electric else 0.0
        dp = abs(avg - pa["systems_power_W"]) / max(avg, 1.0) if electric else 0.0
        dw = abs(res.sizing.W0 / W0_prev - 1) if W0_prev else 1.0
        dm = abs(msys - msys_prev) / max(msys, 1e-6) if msys_prev is not None else 1.0
        uses_masses = spec.assumptions["weights"].get("method", "components") == "components"
        if de < tol and dp < tol and (not uses_masses or (dw < tol and dm < tol)):
            break
        W0_prev, msys_prev = res.sizing.W0, msys
        if electric:
            pa["battery_Wh_kg"], pa["systems_power_W"] = e_pack, avg
    sysres.closure_history = hist
    return res, sysres
