"""Electrical architecture and power-source capacity (P4).

Classical load analysis on top of :class:`~acdt.core.systems.avionics.PowerBudget`
(MIL-E-7016F; Moir & Seabridge, *Aircraft Systems*, 3rd ed., Ch. 5): average and peak loads
by bus, generation and battery capacity with margin, and a simple architecture record
(generation → distribution buses → loads).

Does not invent component performance: generators/batteries come from a catalog (example DB
or user datasheets with source + date).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .avionics import Load, PowerBudget

REF = ("MIL-E-7016F Electric load and power source capacity, aircraft, analysis of; "
       "Moir & Seabridge, Aircraft Systems, 3rd ed., Ch. 5")


@dataclass
class ElectricalArchitecture:
    """One candidate architecture: sources + buses + loads."""
    id: str
    generation: list[dict] = field(default_factory=list)   # catalog rows
    batteries: list[dict] = field(default_factory=list)
    buses: list[str] = field(default_factory=lambda: ["avionics", "servo", "payload"])
    loads: list[Load] = field(default_factory=list)
    margin_generation: float = 1.25   # PRESSUPOSTO N1 (MIL-E-7016F uses growth margins)
    margin_battery_wh: float = 1.20   # PRESSUPOSTO: reserve on energy
    endurance_h: float = 1.0          # mission electrical endurance for battery sizing


def budget_of(arch: ElectricalArchitecture) -> PowerBudget:
    return PowerBudget(loads=list(arch.loads))


def analyse(arch: ElectricalArchitecture) -> dict[str, Any]:
    """Return load table, source capacity check, and pass/fail with reasons."""
    pb = budget_of(arch)
    gen_cont = sum(float(g.get("power_w_cont", 0)) for g in arch.generation)
    gen_peak = sum(float(g.get("power_w_peak", g.get("power_w_cont", 0))) for g in arch.generation)
    bat_wh = sum(float(b.get("energy_wh", 0)) for b in arch.batteries)
    bat_w = sum(float(b.get("continuous_w", 0)) for b in arch.batteries)
    need_avg = pb.average_w
    need_peak = pb.peak_w
    need_wh = need_avg * arch.endurance_h * arch.margin_battery_wh
    # Generation covers continuous; battery covers peaks / electric-only
    gen_ok = gen_cont >= need_avg * arch.margin_generation if arch.generation else None
    peak_ok = (gen_peak + bat_w) >= need_peak if (arch.generation or arch.batteries) else None
    energy_ok = bat_wh >= need_wh if arch.batteries else (need_wh <= 0)
    reasons = []
    if arch.generation and gen_ok is False:
        reasons.append(f"geração contínua {gen_cont:.0f} W < carga média×margem "
                       f"{need_avg * arch.margin_generation:.0f} W")
    if peak_ok is False:
        reasons.append(f"pico disponível {gen_peak + bat_w:.0f} W < pico de carga {need_peak:.0f} W")
    if arch.batteries and not energy_ok:
        reasons.append(f"energia bateria {bat_wh:.0f} Wh < necessidade {need_wh:.0f} Wh "
                       f"(endurance {arch.endurance_h} h × margem {arch.margin_battery_wh})")
    if not arch.generation and not arch.batteries:
        reasons.append("sem fontes (geração/bateria) na arquitetura")
    mass = sum(float(g.get("mass_kg", 0)) for g in arch.generation) + sum(
        float(b.get("mass_kg", 0)) for b in arch.batteries)
    return {
        "id": arch.id,
        "ok": not reasons,
        "reasons": reasons,
        "loads": pb.table(),
        "P_avg_W": need_avg,
        "P_peak_W": need_peak,
        "generation_cont_W": gen_cont,
        "generation_peak_W": gen_peak,
        "battery_Wh": bat_wh,
        "battery_cont_W": bat_w,
        "energy_needed_Wh": need_wh,
        "mass_kg": mass,
        "buses": {b: {"peak_W": pb.bus_peak(b), "regulator_W": pb.regulator_rating_w(b)} for b in arch.buses},
        "margins": {"generation": arch.margin_generation, "battery_wh": arch.margin_battery_wh,
                    "endurance_h": arch.endurance_h},
        "pressuposto": "margens N1 generation 1.25 e battery_wh 1.20 (ordem MIL-E-7016F growth)",
        "reference": REF,
    }


def loads_from_dicts(rows: list[dict]) -> list[Load]:
    return [Load(name=r["name"], power_w=float(r["power_w"]), duty=float(r.get("duty", 1.0)),
                 peak_w=(float(r["peak_w"]) if r.get("peak_w") is not None else None),
                 bus=r.get("bus", "avionics")) for r in rows]


def flight_hour_cost(fuel_or_energy_per_h: float, unit_price: float,
                     maintenance_per_h: float = 0.0, other_per_h: float = 0.0) -> dict:
    """Simple cost per flight hour. PRESSUPOSTO: unit_price and maintenance are user inputs.

    fuel_or_energy_per_h in kg/h or kWh/h matching unit_price (€/kg or €/kWh).
    """
    energy = fuel_or_energy_per_h * unit_price
    total = energy + maintenance_per_h + other_per_h
    return {"energy_cost_per_h": energy, "maintenance_per_h": maintenance_per_h,
            "other_per_h": other_per_h, "total_per_h": total,
            "pressuposto": "preços e manutenção são entradas do utilizador; sem base Eastlake aqui",
            "reference": "agregação directa de custos operacionais (sem modelo de depreciação)"}
