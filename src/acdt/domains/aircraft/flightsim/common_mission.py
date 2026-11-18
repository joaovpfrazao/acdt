# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Common operational-phase mission judge for jet and VTOL (L0 pointmass / energy).

Reuses the existing quasi-steady pointmass integrator (Anderson 1999 Ch. 3/5,
Raymer 2018 Ch. 17) for jets, with thrust/TSFC from ``engine_point`` (Mattingly/
Ihme or opt-in table — never a cycle deck). VTOL uses the *same canonical phase
set* but native momentum/segment energy from ``size_vtol`` (Leishman / NDARC-
style L0 already in vtol.size) — not a new 6-DOF or CFD transition model.

Unsupported required phases stay ``unassessed`` / ``not_modeled``; they are never
silently counted as flown. Default fleet 1.0/1.1/1.2 paths stay unchanged until
``common_sim.enabled`` is opted in.

PRESSUPOSTO: ISA, still air unless the mission supplies wind, quasi-steady
equilibrium (no V̇/γ̇), jet idle = zero residual fuel flow, VTOL taxi N/A.
"""
from __future__ import annotations
import math
from copy import deepcopy
from acdt import G0
from acdt.core.atmosphere import isa
from acdt.core.energy_storage import mapping, number, aggregate
from .pointmass import Plant, PointMassMission, simulate_pointmass_mission
from ..mission_phases import CANONICAL, coverage as phase_coverage, required_check

METHOD_JET = ("Anderson 1999 Ch.3/5 pointmass + Raymer 2018 Ch.17 segments; "
              "propulsion via jet.engine_point (Mattingly 2002 / Ihme 2025 or supplied map)")
METHOD_VTOL = ("Canonical phase energy from native size_vtol hover/climb/transition/cruise "
               "segments (Leishman momentum / existing VTOL L0); not a 3-DOF aerodynamic VTOL model")


def validate_common_sim(cs):
    mapping(cs, {"enabled", "source", "phases", "pointmass_dt", "include_field_phases",
                 "reserve_h", "altitude_m", "speed_m_s"}, "common_sim")
    if not isinstance(cs.get("enabled"), bool):
        raise ValueError("common_sim.enabled must be bool")
    if not isinstance(cs.get("source"), str) or not cs["source"].strip():
        raise ValueError("common_sim.source required")
    if "phases" in cs:
        ph = cs["phases"]
        if not isinstance(ph, list) or not ph or set(ph) - set(CANONICAL) or len(set(ph)) != len(ph):
            raise ValueError("common_sim.phases must be distinct names from " + str(CANONICAL))
    for k in ("pointmass_dt", "reserve_h", "altitude_m", "speed_m_s"):
        if k in cs:
            number(k, cs[k], positive=k != "reserve_h", maximum=1e7 if k != "pointmass_dt" else 3600)
    if "include_field_phases" in cs and not isinstance(cs["include_field_phases"], bool):
        raise ValueError("include_field_phases must be bool")


def _jet_thrust_fn(spec, n_engines):
    from ..jet.engine_map import engine_point
    engine = dict(spec.get("engine") or {})
    thrust_sl = float(spec["thrust_sl_N"])

    def fn(V, h, throttle):
        th = float(throttle)
        if th <= 1e-9:
            return 0.0, 0.0  # PRESSUPOSTO: idle residual fuel unmodeled
        atm = isa(max(h, 0.0))
        M = min(max(V, 0.0) / atm.a, 0.95) if atm.a > 0 else 0.0
        r = engine_point(M, max(h, 0.0), thrust_sl, throttle=min(th, 1.0), **engine)
        if r.get("status") == "unassessed" or r.get("thrust_installed_N") is None:
            raise ValueError("engine map unassessed during common mission (outside domain)")
        T = r["thrust_installed_N"] * n_engines
        flow = r["fuel_flow_kg_s"] * n_engines
        return T, flow

    return fn


def plant_from_jet_size(size_out, spec):
    """Build a pointmass Plant from a converged ``size_jet`` result + original spec."""
    if not size_out.get("converged"):
        raise ValueError("plant_from_jet_size needs a converged size_jet result")
    for key in ("wing_area_m2", "aspect_ratio", "thrust_sl_N", "n_engines", "cd0", "oswald", "mach", "altitude_m"):
        if key not in spec and key not in ("cd0", "oswald"):
            raise ValueError(f"jet spec missing {key}")
    cd0 = float(spec.get("cd0", 0.020))
    e = float(spec.get("oswald", 0.82))
    AR = float(spec["aspect_ratio"])
    K = 1.0 / (math.pi * AR * e)
    S = float(spec["wing_area_m2"])
    n_eng = int(spec["n_engines"])
    mtow = float(size_out["mtow_kg"])
    fuel = float(size_out["weights"]["fuel_mass_kg"])
    # cruise TSFC as placeholder c_t; thrust_fn overrides flow
    tsfc = float(size_out["turbofan_per_engine"]["TSFC_kg_N_s"])
    T_sl = float(spec["thrust_sl_N"])
    plant = Plant(
        kind="jet", S=S, CD0=cd0, K=K, CLmax=float(spec.get("CLmax", 1.5)),
        CLmax_to=float(spec.get("CLmax_takeoff", spec.get("CLmax", 1.5))),
        CLmax_land=float(spec.get("CLmax_landing", spec.get("CLmax", 1.5))),
        P_sl=None, T_sl=T_sl, eta_cruise=1.0, eta_climb=1.0, eta_takeoff=1.0,
        c_p=None, c_t=tsfc, eta_tot=1.0, eta_chain=1.0, P_sys=0.0, payload_power_W=0.0,
        generator_efficiency=None, n_engines=n_eng, mu_roll=float(spec.get("mu_roll", 0.02)),
        CL_ground=float(spec.get("CL_ground", 0.5)), dCD0_to=float(spec.get("dCD0_takeoff", 0.02)),
        mu_brake=float(spec.get("mu_brake", 0.4)), mass_kg=mtow, budget=fuel, electric=False,
        source="jet_size", notes=[
            "Plant from size_jet: polar cd0/oswald of the closure; thrust/TSFC from engine_point",
            "Idle residual jet fuel flow = 0 (PRESSUPOSTO)",
        ],
    )
    plant._thrust_fn = _jet_thrust_fn(spec, n_eng)
    plant._eta_takeoff_missing = False
    plant.source_text = "jet_size+" + str(size_out["turbofan_per_engine"].get("map_mode", "correlation"))
    if size_out.get("inputs", {}).get("auxiliary") or spec.get("auxiliary"):
        aux = spec.get("auxiliary") or {}
        plant.auxiliary_fuel_flow_kg_s = float(aux.get("fuel_flow_kg_s", 0.0))
    return plant


def build_jet_segments(common, sample, cruise_alt_m, cruise_speed_m_s):
    """Map requested canonical phases to pointmass segments; list unassessed gaps."""
    phases = list(common.get("phases") or (
        ["takeoff", "climb", "transit_out", "station", "transit_back", "descent", "landing"]
        if common.get("include_field_phases", True) else
        ["transit_out", "station", "transit_back"]
    ))
    dt = float(common.get("pointmass_dt", 5.0))
    reserve_h = float(common.get("reserve_h", sample.get("reserve_h", 0.0) or 0.0))
    dist_km = float(sample["distance_km"])
    V = float(common.get("speed_m_s", sample["speed_m_s"]))
    alt = float(common.get("altitude_m", cruise_alt_m))
    on_h = float(sample["on_station_h"])
    leg_h = (dist_km * 1000.0) / V / 3600.0
    segs = []
    unassessed = []
    notes = []
    for ph in phases:
        if ph == "taxi_out":
            unassessed.append(dict(phase=ph, reason="jet taxi fuel/time not modeled in pointmass common sim"))
        elif ph == "takeoff":
            segs.append(dict(type="takeoff", name="takeoff"))
        elif ph == "climb":
            segs.append(dict(type="climb", name="climb", to_altitude_m=alt, speed_m_s=min(V, cruise_speed_m_s)))
        elif ph == "transit_out":
            if leg_h > 0:
                segs.append(dict(type="cruise", name="transit_out", time_min=leg_h * 60, speed_m_s=V, altitude_m=alt))
        elif ph == "station":
            if on_h > 0:
                segs.append(dict(type="cruise", name="station", time_min=on_h * 60, speed_m_s=V, altitude_m=alt, on_station=True))
        elif ph == "transit_back":
            if leg_h > 0:
                segs.append(dict(type="cruise", name="transit_back", time_min=leg_h * 60, speed_m_s=V, altitude_m=alt))
        elif ph == "descent":
            segs.append(dict(type="descent", name="descent", to_altitude_m=0, speed_m_s=min(V, cruise_speed_m_s)))
        elif ph == "landing":
            segs.append(dict(type="landing", name="landing"))
        elif ph == "taxi_in":
            unassessed.append(dict(phase=ph, reason="jet taxi-in not modeled in pointmass common sim"))
        elif ph == "reserve":
            if reserve_h > 0:
                segs.append(dict(type="cruise", name="operational_reserve", time_min=reserve_h * 60, speed_m_s=V, altitude_m=alt))
            else:
                notes.append("reserve phase requested but reserve_h=0; no reserve segment flown")
        else:
            unassessed.append(dict(phase=ph, reason="unknown phase"))
    total_h = sum(s.get("time_min", 0) for s in segs) / 60.0
    field = any(p in phases for p in ("takeoff", "climb", "descent", "landing"))
    # Airborne-only profiles start at cruise altitude (PRESSUPOSTO: no climb fuel in this mode).
    # Field profiles start on the ground and must include climb to reach cruise.
    h0 = 0.0 if field else alt
    if not field:
        notes.append("airborne-only common jet profile starts at cruise altitude_m (no climb segment flown)")
    return dict(name="common_jet_pointmass", pointmass_dt=dt,
                initial=dict(altitude_m=h0, heading_deg=0, speed_m_s=V),
                segments=segs), phases, unassessed, notes, total_h


def simulate_jet_common(size_out, spec, sample, common):
    """Fly opt-in common phases with pointmass + engine_point propulsion."""
    validate_common_sim(common)
    if not common.get("enabled"):
        raise ValueError("simulate_jet_common requires common_sim.enabled true")
    plant = plant_from_jet_size(size_out, spec)
    atm = isa(float(spec["altitude_m"]))
    V_cruise = float(spec["mach"]) * atm.a
    ms, phases, unassessed, notes, _ = build_jet_segments(common, sample, float(spec["altitude_m"]), V_cruise)
    sim = PointMassMission(plant, ms)
    result = sim.run()
    result.pop("_samples", None)
    fuel_used = result.get("total_used_kg")
    budget = plant.budget
    residual = (budget - fuel_used) if (budget is not None and fuel_used is not None) else None
    cov = phase_coverage("jet", jet_durations=True)
    # mark flown phases that we actually put in the segment list
    flown = {s.get("name") for s in ms["segments"]}
    phase_report = {}
    for p in CANONICAL:
        if p in ("transit_out", "station", "transit_back", "reserve") and p in flown:
            phase_report[p] = dict(state="flown", method=METHOD_JET)
        elif p in ("takeoff", "climb", "descent", "landing") and p in flown:
            phase_report[p] = dict(state="flown", method=METHOD_JET + " (Raymer field segments)")
        elif p in ("taxi_out", "taxi_in"):
            phase_report[p] = dict(state="not_modeled", method="common jet pointmass has no taxi fuel model")
        else:
            phase_report[p] = cov["phases"][p]
    for u in unassessed:
        phase_report[u["phase"]] = dict(state="not_modeled", method=u["reason"])
    req = common.get("phases") or list(phases)
    miss = [p for p in req if phase_report.get(p, {}).get("state") in ("not_modeled",)]
    return dict(
        schema_version="1.0", model="jet", level="L0",
        status="assessed" if result.get("aborted") is None and not miss else ("aborted" if result.get("aborted") else "partial"),
        mission_result=result,
        flight_duration_h=result["total_time_min"] / 60.0,
        fuel_used_kg=fuel_used,
        fuel_budget_kg=budget,
        residual_fuel_kg=residual,
        energy_Wh=None,
        phases_requested=req,
        phase_coverage=dict(model="jet", phases=phase_report, contract="common_sim opt-in"),
        unassessed_phases=miss,
        checks=[
            dict(name="common_mission_completed", passed=result.get("aborted") is None),
            dict(name="requested_phases_modeled", passed=None if miss else True, missing=miss),
            dict(name="fuel_within_budget",
                 passed=(residual is not None and residual >= 0) if residual is not None else None,
                 residual_kg=residual),
        ],
        method=METHOD_JET,
        notes=notes + list(result.get("notes") or []) + plant.notes,
        limitations=[
            "Quasi-steady pointmass, not 6-DOF; taxi phases unassessed; idle fuel = 0",
            "Not certification; engine maps are correlation/table only (no pyCycle)",
        ],
    )


def simulate_vtol_common(size_out, sample, common):
    """Sequence native VTOL segment powers over the canonical phase set (energy judge)."""
    validate_common_sim(common)
    if not common.get("enabled"):
        raise ValueError("simulate_vtol_common requires common_sim.enabled true")
    if size_out.get("converged") is False:
        raise ValueError("VTOL size result not converged")
    phases = list(common.get("phases") or
                  ["takeoff", "climb", "transit_out", "station", "transit_back", "landing"])
    V = float(common.get("speed_m_s", sample["speed_m_s"]))
    dist_km = float(sample["distance_km"])
    on_h = float(sample["on_station_h"])
    reserve_h = float(common.get("reserve_h", 0.0))
    segs = {s["segment"]: s for s in size_out.get("segments", [])}
    # Rebuild power levels from size_out summary when segment list present
    hover = size_out.get("hover") or {}
    cruise = size_out.get("cruise") or {}
    eta = float(size_out.get("eta_chain") or 1.0)
    P_hover = segs.get("hover", {}).get("P_elec_W") or hover.get("P_hover_elec_W")
    if P_hover is None and hover.get("P_hover_shaft_W") is not None:
        P_hover = hover["P_hover_shaft_W"] / max(eta, 1e-9)
    P_cruise = segs.get("cruise", {}).get("P_elec_W") or cruise.get("P_elec_W")
    if P_hover is None or P_cruise is None:
        raise ValueError("VTOL size result missing hover/cruise electric power for common sim")
    P_climb = segs.get("climb", {}).get("P_elec_W")
    t_climb = segs.get("climb", {}).get("t_s", 0.0)
    P_trans = segs.get("transition", {}).get("P_elec_W")
    t_trans = segs.get("transition", {}).get("t_s", 0.0)
    t_hover_to = float((size_out.get("mission") or {}).get("t_hover_s", segs.get("hover", {}).get("t_s", 60.0))) / 2.0
    rows = []
    unassessed = []
    E = 0.0
    t_total = 0.0
    for ph in phases:
        if ph == "taxi_out" or ph == "taxi_in":
            rows.append(dict(phase=ph, state="not_applicable", E_Wh=0.0, t_s=0.0, method="VTOL vertical; no taxi"))
        elif ph == "takeoff":
            ts = t_hover_to
            Pe = P_hover
            E += Pe * ts / 3600
            t_total += ts
            rows.append(dict(phase=ph, state="flown", E_Wh=Pe * ts / 3600, t_s=ts, P_elec_W=Pe, method=METHOD_VTOL))
        elif ph == "climb":
            if P_climb is None or t_climb <= 0:
                unassessed.append(ph)
                rows.append(dict(phase=ph, state="not_modeled", E_Wh=None, t_s=None,
                                 method="no climb segment in size_vtol result"))
            else:
                E += P_climb * t_climb / 3600
                t_total += t_climb
                if t_trans > 0 and P_trans is not None:
                    E += P_trans * t_trans / 3600
                    t_total += t_trans
                rows.append(dict(phase=ph, state="flown", E_Wh=P_climb * t_climb / 3600 + (P_trans or 0) * t_trans / 3600,
                                 t_s=t_climb + t_trans, method=METHOD_VTOL))
        elif ph in ("transit_out", "transit_back"):
            ts = dist_km * 1000.0 / V
            E += P_cruise * ts / 3600
            t_total += ts
            rows.append(dict(phase=ph, state="flown", E_Wh=P_cruise * ts / 3600, t_s=ts, P_elec_W=P_cruise, method=METHOD_VTOL))
        elif ph == "station":
            ts = on_h * 3600
            E += P_cruise * ts / 3600
            t_total += ts
            rows.append(dict(phase=ph, state="flown", E_Wh=P_cruise * ts / 3600, t_s=ts, P_elec_W=P_cruise, method=METHOD_VTOL))
        elif ph == "descent":
            unassessed.append(ph)
            rows.append(dict(phase=ph, state="not_modeled", E_Wh=None, t_s=None,
                             method="VTOL size_vtol has no descent segment"))
        elif ph == "landing":
            ts = t_hover_to
            E += P_hover * ts / 3600
            t_total += ts
            rows.append(dict(phase=ph, state="flown", E_Wh=P_hover * ts / 3600, t_s=ts, P_elec_W=P_hover, method=METHOD_VTOL))
        elif ph == "reserve":
            if reserve_h > 0:
                ts = reserve_h * 3600
                E += P_cruise * ts / 3600
                t_total += ts
                rows.append(dict(phase=ph, state="flown", E_Wh=P_cruise * ts / 3600, t_s=ts, method=METHOD_VTOL))
            else:
                rows.append(dict(phase=ph, state="not_modeled", method="reserve_h=0"))
                unassessed.append(ph)
        else:
            unassessed.append(ph)
            rows.append(dict(phase=ph, state="not_modeled", method="unsupported"))
    budget = size_out.get("energy_Wh") or size_out.get("energy_nominal_Wh")
    # usable energy after reserve/DoD if reported
    if budget is None and size_out.get("battery_mass_kg") is not None:
        budget = None  # unknown ≠ invent Wh
    residual = (budget - E) if budget is not None else None
    miss = [r["phase"] for r in rows if r["state"] == "not_modeled" and r["phase"] in phases]
    phase_map = {r["phase"]: dict(state=r["state"], method=r.get("method", "")) for r in rows}
    for p in CANONICAL:
        phase_map.setdefault(p, dict(state="not_modeled", method="not requested"))
    return dict(
        schema_version="1.0", model="vtol", level="L0",
        status="assessed" if not miss else "partial",
        flight_duration_h=t_total / 3600.0,
        fuel_used_kg=None,
        energy_Wh=E,
        energy_budget_Wh=budget,
        residual_energy_Wh=residual,
        phase_rows=rows,
        phases_requested=phases,
        phase_coverage=dict(model="vtol", phases=phase_map, contract="common_sim opt-in energy timeline"),
        unassessed_phases=miss,
        checks=[
            dict(name="common_mission_completed", passed=True),
            dict(name="requested_phases_modeled", passed=None if miss else True, missing=miss),
            dict(name="energy_within_budget",
                 passed=(residual is not None and residual >= 0) if residual is not None else None,
                 residual_Wh=residual),
        ],
        method=METHOD_VTOL,
        notes=[f"eta_chain={eta} used only as reported by size_vtol; powers are electric when available"],
        limitations=[
            "VTOL common sim is segment energy sequencing, not a 3-DOF aerodynamic / transition CFD model",
            "Descent and taxi remain not_modeled/not_applicable; required ones stay unassessed",
        ],
    )


def simulate_common_mission(*, model, size_out, spec=None, sample, common):
    """Dispatch jet pointmass or VTOL energy timeline."""
    if model == "jet":
        if spec is None:
            raise ValueError("jet common sim needs the original aircraft spec")
        return simulate_jet_common(size_out, spec, sample, common)
    if model == "vtol":
        return simulate_vtol_common(size_out, sample, common)
    raise ValueError("common_sim currently supports model jet|vtol (prop already uses pointmass)")
