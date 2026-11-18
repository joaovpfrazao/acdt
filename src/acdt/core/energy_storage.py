# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Common L0 storage balances, not a propulsion or mission model.

Definitions: rho=m/V; pack specific energy=E/m; volumetric energy=E/V.
NIST SP 811 (2008), Appendix B.8: 1 L=1e-3 m³, 1 Wh=3600 J:
https://www.nist.gov/pml/special-publication-811/nist-guide-si-appendix-b-conversion-factors/nist-guide-si-appendix-b8
Hepperle (2012), Electric Flight — Potential and Limitations, Sec. 3.2,
energy chains and battery systems (context, NOT a reserve/DoD rule):
https://elib.dlr.de/78726/1/MP-AVT-209-09.pdf
Sources consulted 2026-11-07. No empirical density or usable-volume defaults.

PRESSUPOSTO accounting convention: demand is withdrawal at the tank/pack terminals,
trip + separately stated usable reserve. Fuel unusable mass is an absolute mass,
not another reserve fraction. Battery nominal energy times DoD is deliverable at
pack terminals; motor/ESC/propeller losses must already be in demand. No extra
chain efficiency is applied here. All pack properties must be PACK-level.
Available volume is explicitly allocated net installation space, never gross OML.
Volume inequalities are necessary scalar screens, not 3-D fit/CG/safety proof.
"""
from __future__ import annotations
from copy import deepcopy
import json
import math


def number(name, value, *, positive=False, maximum=1e15):
    """Finite bounded SI scalar; bounds are numerical safeguards, not design data."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if value < 0 or (positive and value == 0) or value > maximum:
        raise ValueError(f"{name} outside numerical domain")
    return float(value)


def mapping(value, allowed, name):
    if not isinstance(value, dict) or set(value)-set(allowed):
        raise ValueError(f"{name}: expected mapping with keys {sorted(allowed)}")


def aggregate(values):
    """Three-state AND: known failure beats missing information; empty is unassessed."""
    vals = list(values)
    return False if False in vals else (True if vals and all(x is True for x in vals) else None)


FUEL_KEYS = {"capacity_kg", "loaded_mass_kg", "unusable_mass_kg", "density_kg_m3",
             "tank_internal_volume_m3", "fill_fraction", "tank_external_volume_m3",
             "available_volume_m3", "tank_dry_mass_kg"}
BATTERY_KEYS = {"nominal_Wh", "dod", "pack_mass_kg", "pack_Wh_kg", "pack_volume_m3",
                "pack_Wh_L", "available_volume_m3", "max_continuous_power_W"}


def validate_storage(storage):
    """Validate present fields, allowing genuinely missing data to remain unassessed."""
    mapping(storage, {"fuel", "battery", "assumption_sources", "shared_available_volume_m3"}, "storage")
    if storage.get("shared_available_volume_m3") is not None: number("shared_available_volume_m3", storage["shared_available_volume_m3"])
    for carrier, keys in (("fuel", FUEL_KEYS), ("battery", BATTERY_KEYS)):
        if carrier not in storage: continue
        s = storage[carrier]
        mapping(s, keys, "storage."+carrier)
        for k, v in s.items():
            if v is None: continue
            number(k, v, positive=k in {"density_kg_m3", "pack_Wh_kg", "pack_Wh_L", "pack_mass_kg", "pack_volume_m3", "tank_internal_volume_m3", "tank_external_volume_m3"},
                   maximum=1 if k in {"dod", "fill_fraction"} else 1e15)
        for a, b in (("pack_mass_kg", "pack_Wh_kg"), ("pack_volume_m3", "pack_Wh_L")):
            if s.get(a) is not None and s.get(b) is not None: raise ValueError(f"declare {a} OR {b}, not conflicting representations")
    if "assumption_sources" in storage and not isinstance(storage["assumption_sources"], dict):
        raise ValueError("storage.assumption_sources must be a mapping")
    json.dumps(storage, allow_nan=False)


def check_storage(demand: dict, storage: dict, counted_mass_kg: dict | None = None) -> dict:
    """Mass/volume/usable-capacity balance; demand trip + reserve are not multiplied again.

    fuel: trip_kg, reserve_kg. battery: trip_Wh, reserve_Wh, optional peak_W.
    A missing trip/reserve, installed capacity, load, DoD, unusable mass or allocated
    volume produces an unassessed check, NOT a pass. Empty demand is permitted only
    with a nonempty storage candidate, to report missing demand explicitly.
    counted_mass_kg is the EXISTING fuel-load / complete pack allocation, not added
    mass. Dry tank mass is listed separately; inclusion in empty mass is unassessed.
    """
    validate_storage(storage)
    mapping(demand, {"fuel", "battery"}, "demand")
    for carrier, d in demand.items():
        unit = "kg" if carrier == "fuel" else "Wh"
        mapping(d, {"trip_"+unit, "reserve_"+unit} | ({"peak_W"} if carrier == "battery" else set()), "demand."+carrier)
        for key, val in d.items():
            if val is not None: number(key, val)
    counted_mass_kg = {} if counted_mass_kg is None else counted_mass_kg
    mapping(counted_mass_kg, {"fuel", "battery"}, "counted_mass_kg")
    for key, val in counted_mass_kg.items():
        if val is not None: number(key, val)
    carriers = sorted((set(demand) | set(storage)) & {"fuel", "battery"})
    if not carriers: raise ValueError("at least one demanded or installed carrier is required")
    checks, results, inventory = [], {}, []
    def compare(name, available, required, unit, group):
        margin = None if available is None or required is None else available-required
        # Numerical equality only: 1e-12 relative tolerance, not a physical design margin.
        passed = None if margin is None else margin >= -1e-12*max(abs(available), abs(required), 1)
        checks.append({"name": name, "passed": passed, "margin": margin, "unit": unit, "group": group,
                       "status": "unassessed" if passed is None else ("pass" if passed else "fail")})
    for carrier in carriers:
        s, d = storage.get(carrier, {}), demand.get(carrier, {})
        unit = "kg" if carrier == "fuel" else "Wh"
        trip, reserve = d.get("trip_"+unit), d.get("reserve_"+unit)
        required = trip+reserve if trip is not None and reserve is not None else None
        volume = None
        if carrier == "fuel":
            cap = s.get("capacity_kg")
            rho, internal, fill = s.get("density_kg_m3"), s.get("tank_internal_volume_m3"), s.get("fill_fraction")
            derived = rho*internal*fill if all(v is not None for v in (rho, internal, fill)) else None
            if cap is not None and derived is not None:
                compare("fuel:capacity_vs_internal_volume", derived, cap, "kg", "capacity")
            if cap is None: cap = derived
            load, unusable = s.get("loaded_mass_kg"), s.get("unusable_mass_kg")
            usable = load-unusable if load is not None and unusable is not None else None
            compare("fuel:loaded_within_capacity", cap, load, "kg", "capacity")
            compare("fuel:unusable_within_load", load, unusable, "kg", "capacity")
            compare("fuel:usable_demand", usable, required, "kg", "capacity")
            volume = s.get("tank_external_volume_m3")
            if internal is not None:
                compare("fuel:external_vs_internal_volume", volume, internal, "m3", "packaging")
            liquid_bound_mass = cap if cap is not None else load
            if rho is not None and liquid_bound_mass is not None:
                compare("fuel:liquid_within_envelope", volume, liquid_bound_mass/rho, "m3", "packaging")
            mass = load
            inventory.append({"name": "fuel_loaded", "mass_kg": load, "counted_mass_kg": counted_mass_kg.get(carrier)})
            inventory.append({"name": "tank_dry", "mass_kg": s.get("tank_dry_mass_kg"), "counted_mass_kg": None})
            extra = {"capacity_kg": cap, "capacity_from_volume_kg": derived, "usable_loaded_kg": usable,
                     "loaded_liquid_volume_m3": load/rho if load is not None and rho is not None else None,
                     "required_loaded_mass_kg": required+unusable if required is not None and unusable is not None else None}
        else:
            nominal, dod = s.get("nominal_Wh"), s.get("dod")
            usable = nominal*dod if nominal is not None and dod is not None else None
            compare("battery:usable_demand", usable, required, "Wh", "capacity")
            mass = s.get("pack_mass_kg")
            if mass is None and nominal is not None and s.get("pack_Wh_kg") is not None: mass = nominal/s["pack_Wh_kg"]
            volume = s.get("pack_volume_m3")
            if volume is None and nominal is not None and s.get("pack_Wh_L") is not None: volume = nominal/s["pack_Wh_L"]/1000
            compare("battery:peak_power", s.get("max_continuous_power_W"), d.get("peak_W"), "W", "power")
            inventory.append({"name": "battery_pack", "mass_kg": mass, "counted_mass_kg": counted_mass_kg.get(carrier)})
            extra = {"usable_Wh": usable, "nominal_Wh": nominal,
                     "required_nominal_Wh": required/dod if required is not None and dod else None}
        if "available_volume_m3" in s or "shared_available_volume_m3" not in storage:
            compare(carrier+":allocated_volume", s.get("available_volume_m3"), volume, "m3", "packaging")
        if carrier in counted_mass_kg:
            compare(carrier+":existing_mass_allocation", counted_mass_kg[carrier], mass, "kg", "mass_allocation")
        results[carrier] = {"required_usable_"+unit: required, "installed_envelope_volume_m3": volume,
                            "inventory_mass_kg": mass, **extra}
    if "shared_available_volume_m3" in storage:
        volumes = [r["installed_envelope_volume_m3"] for r in results.values()]
        compare("storage:shared_allocated_volume", storage["shared_available_volume_m3"],
                sum(volumes) if all(v is not None for v in volumes) else None, "m3", "packaging")
    # Missing peak demand/rating is reported, but does not turn an energy/volume screen into a power claim.
    required_checks = [c for c in checks if c["group"] != "power" or c["passed"] is not None
                       or demand.get("battery", {}).get("peak_W") is not None]
    feasible = aggregate(c["passed"] for c in required_checks)
    out = {"schema_version": "1.0", "level": "L0", "storage_feasible": feasible,
           "capacity_feasible": aggregate(c["passed"] for c in checks if c["group"] == "capacity"),
           "packaging_feasible": aggregate(c["passed"] for c in checks if c["group"] == "packaging"),
           "status": "unassessed" if feasible is None else ("screened" if feasible else "infeasible"),
           "demand": deepcopy(demand), "inputs": deepcopy(storage), "carriers": results, "checks": checks,
           "issues": [c["name"] for c in checks if c["passed"] is False],
           "unassessed": [c["name"] for c in checks if c["passed"] is None],
           "mass_inventory": inventory,
           "inventory_total_mass_kg": sum(i["mass_kg"] for i in inventory) if all(i["mass_kg"] is not None for i in inventory) else None,
           "mass_accounting": "Inventory only, never add to an already-sized aircraft. Tank inclusion in empty mass and any missing allocations are unassessed; no mass feedback/CG.",
           "assumptions": [{"path": "demand", "value": deepcopy(demand), "source": "explicit user / producer terminal demand, including reserve once"},
                           {"path": "storage", "value": deepcopy(storage), "source": "explicit inputs; PRESSUPOSTO unless substantiated in assumption_sources"},
                           {"path": "accounting", "value": "tank/pack-terminal demand; reserve once; nominal pack energy times DoD; no chain-efficiency multiplier", "source": "PRESSUPOSTO bookkeeping convention"}],
           "hybrid_dispatch": "unimplemented; independently supplied carrier balances only",
           "numerical_comparison": "margin >= -1e-12 * max(abs(available), abs(required), 1 unit); roundoff tolerance, not physical credit",
           "method": "rho=m/V, pack E/m and E/V; trip+reserve versus usable storage; NIST SP 811 (2008)",
           "validity": "Necessary scalar capacity/volume checks only; no 3-D fit, component placement, thermal/electrical safety, certification, complete mission simulation or aircraft mass closure."}
    # Catch arithmetic overflow rather than emitting NaN/Infinity or a false pass.
    try: json.dumps(out, allow_nan=False)
    except ValueError as exc: raise ValueError("storage arithmetic outside finite numerical domain") from exc
    return out
