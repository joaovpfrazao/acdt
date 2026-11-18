"""Toolkit wrappers for P4: electrical architecture / power budget and payload catalog trade."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from acdt.core.systems.electrical import (
    ElectricalArchitecture, analyse, flight_hour_cost, loads_from_dicts,
)
from acdt.core.systems.payload_trade import load_electrical_catalog, load_payload_catalog, trade


def electrical_catalog(path: str | None = None) -> dict:
    return load_electrical_catalog(path)


def electrical_analyse(architecture: dict, catalog_path: str | None = None) -> dict[str, Any]:
    """Analyse one architecture. ``architecture`` keys: id, generation_ids, battery_ids,
    loads (list of {name, power_w, duty?, peak_w?, bus?}), buses?, margins?, endurance_h?,
    or inline generation/batteries rows (dicts with mass/power fields).
    """
    cat = load_electrical_catalog(catalog_path)
    gens_by = {g["id"]: g for g in cat["generators"]}
    bats_by = {b["id"]: b for b in cat["batteries_avionics"]}
    generation = list(architecture.get("generation") or [])
    for gid in architecture.get("generation_ids") or []:
        if gid not in gens_by:
            raise ValueError(f"generator id desconhecido: {gid}")
        generation.append(gens_by[gid])
    batteries = list(architecture.get("batteries") or [])
    for bid in architecture.get("battery_ids") or []:
        if bid not in bats_by:
            raise ValueError(f"battery id desconhecido: {bid}")
        batteries.append(bats_by[bid])
    loads = loads_from_dicts(architecture.get("loads") or [])
    # optional: pull payload power from catalog ids
    payloads_by = {p["id"]: p for p in cat["payloads"]}
    for pid in architecture.get("payload_ids") or []:
        p = payloads_by.get(pid)
        if not p:
            raise ValueError(f"payload id desconhecido: {pid}")
        loads.append(loads_from_dicts([{
            "name": p["id"], "power_w": float(p["power_w_avg"]),
            "duty": float(architecture.get("payload_duty", 1.0)),
            "peak_w": float(p.get("power_w_peak") or p["power_w_avg"]),
            "bus": "payload",
        }])[0])
    arch = ElectricalArchitecture(
        id=str(architecture.get("id") or "arch"),
        generation=generation,
        batteries=batteries,
        buses=list(architecture.get("buses") or ["avionics", "servo", "payload"]),
        loads=loads,
        margin_generation=float(architecture.get("margin_generation", 1.25)),
        margin_battery_wh=float(architecture.get("margin_battery_wh", 1.20)),
        endurance_h=float(architecture.get("endurance_h", 1.0)),
    )
    return analyse(arch)


def payload_catalog(path: str | None = None, extra: list[dict] | None = None) -> list[dict]:
    return load_payload_catalog(path, extra=extra)


def payload_trade(payloads: list[dict] | None = None, catalog_path: str | None = None,
                  extra: list[dict] | None = None, objectives: dict | None = None,
                  constraints: dict | None = None, kinds: list[str] | None = None) -> dict:
    rows = payloads if payloads is not None else load_payload_catalog(catalog_path, extra=extra)
    if payloads is None and extra:
        rows = load_payload_catalog(catalog_path, extra=extra)
    return trade(rows, objectives=objectives, constraints=constraints, kinds=kinds)


def cost_per_flight_hour(fuel_or_energy_per_h: float, unit_price: float,
                         maintenance_per_h: float = 0.0, other_per_h: float = 0.0) -> dict:
    return flight_hour_cost(fuel_or_energy_per_h, unit_price, maintenance_per_h, other_per_h)


def operational_cost(operating: dict) -> dict:
    """Eastlake/CER → DOC per flight hour (Raymer 2018 Ch. 18 element structure).

    ``operating`` may include ``eastlake`` / ``dapca4`` to fill ``unit_price`` from a cited CER
    (Gudmundsson 2014 Ch. 2 / Raymer 2018 Ch. 18). Missing activated rates → status unassessed/partial
    (never a silent zero). Does not invent L2 vendor quotes. Legacy ``cost_per_flight_hour`` remains
    for direct aggregation of user prices.
    """
    from acdt.domains.aircraft.manufacturing.costing import operational_cost_from_dict
    return operational_cost_from_dict(operating)

