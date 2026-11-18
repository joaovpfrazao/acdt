# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Thin demand adapters to existing aircraft models, NOT a common dynamic simulator.

No new consumption equations: jet_size uses its existing Raymer/Breguet closure;
vtol_size uses its momentum/segment power integration; mission uses actual consumed
kg or Wh from the existing pointmass/6-DOF result. Reserve is an explicit additive
allowance once. No generic GA weight fallback, hybrid dispatch or simulator engine
replacement. Classical model references stay in the producer modules.
"""
from copy import deepcopy
from acdt.core.energy_storage import check_storage, validate_storage, number


def demand_from_result(kind, result, reserve_fraction=None):
    """Return canonical terminal-withdrawal demand and provenance, never invent missing data.

    Mission reserve_fraction is REQUIRED (including explicit zero). Producer results
    already containing a reserve reject another reserve_fraction. Failed/incomplete
    results return unassessed demand, not a truncated mission's apparent pass.
    """
    if kind not in {"jet_size", "vtol_size", "mission"}: raise ValueError("source kind must be jet_size, vtol_size or mission")
    if not isinstance(result, dict): raise ValueError("producer result must be a mapping")
    if kind != "mission" and reserve_fraction is not None: raise ValueError("producer reserve already included; no second reserve allowed")
    if kind == "mission": number("reserve_fraction", reserve_fraction, maximum=10)
    meta = {"kind": kind, "run_id": result.get("run_id"), "coupling": "demand adapter only; no simulator/model replacement",
            "source_feasible": result.get("feasible"), "counted_mass_kg": {}, "demand_assessed": False}
    r = result.get("summary", result)
    if not isinstance(r, dict): raise ValueError("producer summary must be a mapping")
    def unavailable(reason): return {}, {**meta, "reason": reason}
    if result.get("status") in {"failed", "error", "not_converged"}: return unavailable("producer failed")
    try:
        if kind == "jet_size":
            if result.get("converged") is not True: return unavailable("jet mass closure not converged")
            w = result["weights"]
            trip, reserve = number("trip_burn_kg", w["trip_burn_kg"]), number("reserve_fuel_kg", w["reserve_fuel_kg"])
            meta["counted_mass_kg"]["fuel"] = number("fuel_mass_kg", w["fuel_mass_kg"])
            demand = {"fuel": {"trip_kg": trip, "reserve_kg": reserve}}
            meta["accounting"] = "jet_size extra reserve fuel retained once; no additional reserve factor. Unusable tank fuel must be separately specified without duplicating a trapped-fuel allowance."
        elif kind == "vtol_size":
            e = result["inputs_resolved"]["electric"]
            trip = number("energy_Wh", result["energy_Wh"])
            reserve = trip*number("VTOL reserve", e["reserve"], maximum=10)
            peak = number("P_elec_W", result["peak"]["P_elec_W"])
            meta["counted_mass_kg"]["battery"] = number("battery_mass_kg", result["battery_mass_kg"])
            demand = {"battery": {"trip_Wh": trip, "reserve_Wh": reserve, "peak_W": peak}}
            meta["accounting"] = "energy_Wh already includes motor/ESC and systems; reserve from resolved producer inputs once; producer nominal_Wh/DoD are NOT used as trip demand."
        else:
            if "aborted" not in r or r["aborted"] is not None: return unavailable("mission incomplete or completion unknown")
            if r.get("unusable", 0) != 0 or r.get("failures"):
                return unavailable("degraded/failure mission requires explicit carrier inventory accounting")
            unit = r["unit"]
            if unit not in {"kg", "Wh"}: raise ValueError("mission consumption unit must be kg or Wh, not shaft J/kWh")
            value = r.get("total_used_"+unit, r.get("total_used"))
            if value is None: return unavailable("missing mission consumption")
            trip = number("total consumed "+unit, value)
            carrier = "fuel" if unit == "kg" else "battery"
            demand = {carrier: {"trip_"+unit: trip, "reserve_"+unit: trip*reserve_fraction}}
            meta["accounting"] = "actual consumed tank kg / battery-terminal Wh, not initial usable budget; caller reserve_fraction once; no new efficiency/DoD conversion"
            meta["fidelity"] = r.get("fidelity", "producer-defined (see provenance)")
    except (KeyError, TypeError) as exc:
        return unavailable("missing producer fields: "+str(exc))
    return demand, {**meta, "demand_assessed": True}


def aircraft_storage(storage, kind="direct", result=None, reserve_fraction=None, demand=None):
    """Common capacity screen with an explicit producer adapter; legacy feasibility untouched."""
    validate_storage(storage)
    if kind == "direct":
        if result is not None or reserve_fraction is not None: raise ValueError("direct demand must explicitly include reserve, not a producer result/factor")
        if not isinstance(demand, dict): raise ValueError("direct demand mapping required")
        meta = {"kind": "direct", "demand_assessed": True, "counted_mass_kg": {},
                "coupling": "user-supplied independent terminal demands; no hybrid dispatch"}
    else:
        if demand is not None: raise ValueError("choose direct demand OR a producer adapter")
        demand, meta = demand_from_result(kind, result, reserve_fraction)
    # A producer with unavailable demand cannot yield a storage pass, even when
    # neither a producer field nor a storage carrier establishes the carrier type.
    if not meta["demand_assessed"] and not ({"fuel", "battery"} & set(storage)):
        return {"schema_version": "1.0", "level": "L0", "storage_feasible": None, "status": "unassessed",
                "producer": meta, "checks": [], "issues": [], "unassessed": [meta["reason"]], "assumptions": [],
                "capacity_feasible": None, "packaging_feasible": None, "inputs": deepcopy(storage),
                "demand": {}, "carriers": {}, "mass_inventory": [], "inventory_total_mass_kg": None,
                "method": "existing producer demand adapter; no substitute demand or mass",
                "validity": "Producer demand unavailable; storage capacity/volume unassessed.",
                "hybrid_dispatch": "unimplemented"}
    out = check_storage(demand, storage, meta["counted_mass_kg"])
    out["producer"] = deepcopy(meta)
    if not meta["demand_assessed"]: out["unassessed"].append(meta["reason"])
    return out
