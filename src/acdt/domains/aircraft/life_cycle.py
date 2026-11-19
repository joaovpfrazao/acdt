# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Disciplina «ciclo_vida» (L0) do domínio aircraft (docs/CICLO_VIDA.md).

Etapa do pipeline depois do custo de série. Só corre com ``assumptions.life_cycle`` declarado (ou um requisito de
ciclo de vida). Constrói as especificações genéricas de :mod:`acdt.core.lcc` a partir do que já foi calculado:

* **RDT&E e custo de produção por aeronave**: da secção ``series_cost`` (RDT&E; ferramentas + recorrente por
  unidade, sem margem) ou declarados (``rdte_USD``, ``unit_production_cost_USD``); senão desconhecidos;
* **O&S por hora de voo**: ``cost_per_fh_USD`` declarado; senão o custo operacional da fiabilidade
  (``reliability.operating_cost``: ``per_flight_hour`` se ``ok``, minorante se ``partial``); senão um bloco
  ``operating_cost`` avaliado com :func:`manufacturing.costing.operational_cost_from_dict`; senão desconhecido.
  A depreciação do DOC é retirada (a aquisição já está na categoria de produção);
* **frota**: ``fleet_size`` declarado; senão a quantidade do custo de série (PRESSUPOSTO frota = série);
* **utilização**: ``fh_per_aircraft_per_year`` declarado; senão ``flight_hours_per_year`` do custo operacional;
* **energia por hora de voo**: combustível Wf / duração da missão ou energia da bateria / duração (PRESSUPOSTO:
  toda a energia de missão, incluindo reservas, é gasta → majorante); duração como na fiabilidade.
"""
from __future__ import annotations

import copy
from typing import Any

from acdt.core.lcc import environment as env
from acdt.core.lcc import lcc

LEVEL = "L0"
REQ_KEYS = ("life_cycle_cost", "life_cycle_cost_per_fh", "co2e_per_flight_hour", "life_cycle_co2e")
DEFAULTS: dict[str, Any] = {
    "enabled": True, "fleet_size": None, "service_life_years": None, "production_rate_per_year": None,
    "rdte_years": 0, "rdte_USD": None, "unit_production_cost_USD": None, "cost_per_fh_USD": None,
    "fh_per_aircraft_per_year": None, "disposal_per_aircraft_USD": None, "residual_per_aircraft_USD": None,
    "discount_rate": None, "escalation_os": None, "operating_cost": None, "environment": None, "sources": None,
}


def _opts(spec: Any) -> tuple[dict[str, Any], bool]:
    o = copy.deepcopy(DEFAULTS)
    user = spec.assumptions.get("life_cycle") if isinstance(spec.assumptions, dict) else None
    if isinstance(user, dict):
        o.update(user)
    return o, isinstance(user, dict)


def _requested(spec: Any) -> list[Any]:
    try:
        return [r for r in spec.requirements if r.key in REQ_KEYS]
    except TypeError:
        return []


def _not_evaluated(reason: str) -> dict[str, Any]:
    return {"evaluated": False, "level": LEVEL, "reason": reason, "life_cycle_cost_USD": {"lo": None, "hi": None}}


def _os_cost(res: Any, o: dict[str, Any], notes: list[str]) -> tuple[Any, float | None]:
    """(custo O&S por FH sem depreciação, horas de voo/ano do bloco DOC)."""
    if o.get("cost_per_fh_USD") is not None:
        notes.append("O&S/FH: declarado (life_cycle.cost_per_fh_USD)")
        return o["cost_per_fh_USD"], None
    doc = None
    rl = getattr(res, "reliability", None)
    if isinstance(rl, dict) and isinstance(rl.get("operating_cost"), dict):
        doc = rl["operating_cost"]
        notes.append("O&S/FH: custo operacional da fiabilidade (manutenção MIL-HDBK-338B na estrutura DOC de Raymer)")
    elif isinstance(o.get("operating_cost"), dict):
        from .manufacturing.costing import operational_cost_from_dict

        blk = dict(o["operating_cost"])
        sc = getattr(res, "series_cost", None)
        override = None
        if "unit_price" not in blk and isinstance(sc, dict) and sc.get("evaluated"):
            a = sc.get("average_unit_cost_USD")
            override = a.get("lo") if isinstance(a, dict) else a
        doc = operational_cost_from_dict(blk, unit_price_override=override)
        notes.append("O&S/FH: life_cycle.operating_cost (manufacturing.costing.operating_cost, Raymer 2018 Cap. 18)")
    if doc is None:
        notes.append("O&S/FH desconhecido (declare cost_per_fh_USD, reliability.operating_cost ou "
                     "life_cycle.operating_cost)")
        return None, None
    items = dict(doc.get("items_per_fh") or {})
    dep = float(items.get("depreciation", 0.0))
    if dep:
        notes.append("depreciação retirada do DOC (a aquisição está na categoria produção)")
    fh_y = doc.get("flight_hours_per_year")
    if doc.get("status") == "ok":
        return float(doc["per_flight_hour"]) - dep, fh_y
    notes.append(f"custo operacional {doc.get('status')}: só minorante (termos em falta: {doc.get('unassessed_terms')})")
    return {"lo": float(doc.get("assessed_sum_per_fh") or 0.0) - dep, "hi": None}, fh_y


def build_specs(res: Any, o: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    from .reliability import mission_duration_h

    notes: list[str] = []
    sc_raw = getattr(res, "series_cost", None)
    sc: dict[str, Any] = sc_raw if isinstance(sc_raw, dict) else {}
    sc_ok = bool(sc.get("evaluated")) and isinstance(sc.get("at_quantity"), dict)
    n = o.get("fleet_size")
    if n is None and sc_ok:
        n = int(sc["quantity"])
        notes.append(f"frota = quantidade do custo de série ({n}) (PRESSUPOSTO)")
    if n is None:
        raise ValueError("life_cycle.fleet_size em falta (nem series_cost.quantity)")
    if o.get("service_life_years") is None:
        raise ValueError("life_cycle.service_life_years em falta")
    rdte, unit = o.get("rdte_USD"), o.get("unit_production_cost_USD")
    if sc_ok:
        at = sc["at_quantity"]
        if rdte is None and "rdte_USD" in at:
            rdte = at["rdte_USD"]
            notes.append("RDT&E ← custo de série")
        if unit is None:
            if "tooling_USD" in at:
                unit = (at["tooling_USD"] + at["recurring_USD"]) / at["N"]
            elif "nre_USD" in at and sc.get("nre_declared") is not False:
                unit = at["recurring_USD"] / at["N"]
                if rdte is None:
                    rdte = at["nre_USD"]
            if unit is not None:
                notes.append("produção/aeronave ← custo de série (ferramentas + recorrente, sem margem)")
            if int(at["N"]) != int(n):
                notes.append(f"custo de série avaliado a N = {at['N']} ≠ frota {n} (PRESSUPOSTO: mesmo custo unitário)")
    cpfh, fh_doc = _os_cost(res, o, notes)
    fh = o.get("fh_per_aircraft_per_year") if o.get("fh_per_aircraft_per_year") is not None else fh_doc
    if fh is None:
        raise ValueError("life_cycle.fh_per_aircraft_per_year em falta (nem flight_hours_per_year do custo operacional)")
    t, t_src = mission_duration_h(res, o)
    notes.append(f"duração da missão: {'?' if t is None else f'{t:.3g} h'} ({t_src})")
    lspec: dict[str, Any] = {k: o.get(k) for k in ("service_life_years", "production_rate_per_year", "rdte_years",
                                                    "disposal_per_aircraft_USD", "residual_per_aircraft_USD",
                                                    "discount_rate", "escalation_os")}
    lspec.update({"fleet_size": int(n), "rdte_USD": rdte, "unit_production_cost_USD": unit, "cost_per_fh_USD": cpfh,
                  "fh_per_aircraft_per_year": fh, "mission_duration_h": t, "sources": o.get("sources") or {}})
    lspec["rdte_years"] = int(lspec.get("rdte_years") or 0)
    # ambiente
    e_o = dict(o.get("environment") or {})
    espec: dict[str, Any] = {k: v for k, v in e_o.items()}
    sz = res.sizing
    kind = res.spec.propulsion_kind
    if t and t > 0:
        if kind == "electric":
            if "battery_kWh_per_fh" not in espec and getattr(sz, "energy_J", None):
                espec["battery_kWh_per_fh"] = float(sz.energy_J) / 3.6e6 / t
                notes.append("energia/FH = energia da bateria do dimensionamento / duração da missão (PRESSUPOSTO: "
                             "toda gasta → majorante)")
            if not espec.get("battery_capacity_kWh") and getattr(sz, "energy_J", None):
                espec["battery_capacity_kWh"] = float(sz.energy_J) / 3.6e6
                notes.append("capacidade da bateria = energia de missão do dimensionamento (declare "
                             "environment.battery_capacity_kWh)")
        elif "fuel_kg_per_fh" not in espec and getattr(sz, "Wf", None):
            espec["fuel_kg_per_fh"] = float(sz.Wf) / t
            notes.append("combustível/FH = Wf / duração da missão (PRESSUPOSTO: inclui reservas → majorante)")
    if "fuel_kg_per_fh" in espec:
        from acdt.core.thermal.sources import LHV_MJ_KG, LHV_REF

        espec.setdefault("fuel", "avgas" if kind == "piston_prop" else "jet_a")
        if espec.get("lhv_MJ_kg") is None and espec["fuel"] in LHV_MJ_KG:
            espec["lhv_MJ_kg"] = LHV_MJ_KG[espec["fuel"]]
            espec["lhv_source"] = LHV_REF[espec["fuel"]] + " (PRESSUPOSTO: mínimo da norma)"
    espec["mission_duration_h"] = t
    espec["fleet_size"] = int(n)
    from .native_disciplines import fold_life_cycle_energy
    fold_life_cycle_energy(espec, notes, res.spec, kind)
    return lspec, espec, notes


def analyse_life_cycle(res: Any) -> dict[str, Any]:
    o, _ = _opts(res.spec)
    lspec, espec, notes = build_specs(res, o)
    out = lcc.analyse(lspec)
    life_h = out["fleet_flight_hours"]
    n = lspec["fleet_size"]
    espec.setdefault("fleet_flight_hours", life_h)
    espec.setdefault("aircraft_flight_hours", {"lo": life_h["lo"] / n, "hi": life_h["hi"] / n})
    out["environment"] = env.analyse(espec)
    e = out["environment"]
    out["co2e_per_flight_hour_kg"] = e.get("per_flight_hour_total_kgCO2e", e["operation_per_fh_kgCO2e"])
    out["life_cycle_co2e_kg"] = e.get("life_cycle_fleet_kgCO2e", {"lo": None, "hi": None})
    if e["unknown"]:
        for k in ("co2e_per_flight_hour_kg", "life_cycle_co2e_kg"):
            out[k] = {"lo": out[k].get("lo"), "hi": None}
    from .native_disciplines import open_unaccounted
    open_unaccounted(out, espec)
    out.update({"level": LEVEL, "adapter_notes": notes})
    return out


def life_cycle_stage(res: Any) -> None:
    from acdt.core.requirements import Issue

    o, declared = _opts(res.spec)
    if not o.get("enabled", True):
        res.life_cycle = _not_evaluated("life_cycle.enabled: false")
        return
    if not declared and not _requested(res.spec):
        res.life_cycle = _not_evaluated("sem assumptions.life_cycle nem requisitos de ciclo de vida")
        return
    if res.sizing is None or not res.sizing.converged:
        res.life_cycle = _not_evaluated("dimensionamento não convergiu")
        return
    try:
        res.life_cycle = analyse_life_cycle(res)
    except Exception as ex:  # noqa: BLE001 — a etapa nunca parte o pipeline; fica desconhecido
        res.life_cycle = _not_evaluated(f"falhou: {type(ex).__name__}: {ex}")
        res.issues.append(Issue("warning", f"ciclo de vida não avaliado: {type(ex).__name__}: {ex}"))
