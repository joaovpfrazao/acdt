# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Custo do ciclo de vida (LCC) L0 de um programa de aeronaves.

Categorias (OSD CAPE, *Operating and Support Cost-Estimating Guide*, 2020, §2.1): (1) RDT&E, (2) investimento
(produção), (3) operação e apoio (O&S), (4) abate (*disposal*), menos o valor residual. Atualização: modelo geral
de NIST Handbook 135 (1995) Eq. 5.1, LCC = Σ_t C_t / (1+d)^t, montantes no fim de cada ano (Tabela 3-1), em dólares
constantes com taxa de atualização **real** d declarada; escalada real e dos custos anuais de O&S com
A_t = A_0 (1+e)^t (Eq. 3.9).

Calendário (PRESSUPOSTOS, declarados na saída): RDT&E repartido por igual pelos anos 1..``rdte_years``; produção a
``production_rate_per_year`` aeronaves/ano a partir do ano seguinte; cada aeronave entregue no ano y opera nos anos
y+1..y+L (L = vida útil) e é abatida no fim do ano y+L (custo de abate menos valor residual).

Intervalos: cada entrada pode ser ``{lo, hi}``; o resultado é o mínimo/máximo sobre os cantos das entradas em
intervalo e uma grelha da taxa de atualização. Entrada de custo desconhecida (``None``) → essa categoria só tem
minorante 0 e o majorante do total fica **desconhecido** (nunca zero).
"""
from __future__ import annotations

import itertools
import math
from typing import Any, Mapping

from .discount import spv

CATEGORIES = ("rdte", "production", "operation_support", "disposal", "residual")
RANGE_KEYS = ("rdte_USD", "unit_production_cost_USD", "cost_per_fh_USD", "fh_per_aircraft_per_year",
              "disposal_per_aircraft_USD", "residual_per_aircraft_USD", "discount_rate", "escalation_os")
SOURCES = {
    "categories": "OSD CAPE, Operating and Support Cost-Estimating Guide (2020) §2.1: LCC = RDT&E + investimento + "
                  "O&S + abate",
    "discounting": "NIST Handbook 135 (Fuller & Petersen, 1995 ed.) Eq. 5.1 e Tabela 3-1 (SPV, UPV, UPV*)",
}


def rng(v: Any) -> tuple[float | None, float | None]:
    """``x`` | ``{lo, hi}`` | ``{value}`` | ``None`` → (lo, hi); ``None`` = desconhecido."""
    if v is None:
        return None, None
    if isinstance(v, Mapping):
        if "value" in v:
            x = float(v["value"])
            return x, x
        lo, hi = v.get("lo"), v.get("hi")
        return (None if lo is None else float(lo)), (None if hi is None else float(hi))
    x = float(v)
    return x, x


def schedule(n_aircraft: int, rdte_years: int, rate: float, life: int) -> dict[str, Any]:
    if n_aircraft < 1 or rdte_years < 0 or rate <= 0 or life < 1:
        raise ValueError("frota ≥ 1, rdte_years ≥ 0, cadência > 0 e vida útil ≥ 1")
    deliveries: dict[int, int] = {}
    y, left = rdte_years + 1, n_aircraft
    per_year = max(int(math.floor(rate)), 1)
    while left > 0:
        k = min(per_year, left)
        deliveries[y] = k
        left -= k
        y += 1
    last = max(deliveries) + life
    active = {t: sum(k for yd, k in deliveries.items() if yd < t <= yd + life) for t in range(1, last + 1)}
    retire = {yd + life: k for yd, k in deliveries.items()}
    return {"deliveries": deliveries, "active": active, "retirements": retire, "last_year": last}


def flows(p: Mapping[str, float], sch: Mapping[str, Any], rdte_years: int) -> dict[int, dict[str, float]]:
    """Fluxos em dólares constantes por ano e categoria para um conjunto de valores escalares."""
    out: dict[int, dict[str, float]] = {}

    def add(t: int, cat: str, x: float) -> None:
        out.setdefault(t, {c: 0.0 for c in CATEGORIES})[cat] += x

    if rdte_years > 0:
        for t in range(1, rdte_years + 1):
            add(t, "rdte", p["rdte_USD"] / rdte_years)
    else:
        add(0, "rdte", p["rdte_USD"])
    for t, k in sch["deliveries"].items():
        add(t, "production", k * p["unit_production_cost_USD"])
    e = p["escalation_os"]
    for t, n in sch["active"].items():
        if n:
            add(t, "operation_support", n * p["fh_per_aircraft_per_year"] * p["cost_per_fh_USD"] * (1.0 + e) ** t)
    for t, k in sch["retirements"].items():
        add(t, "disposal", k * p["disposal_per_aircraft_USD"])
        add(t, "residual", -k * p["residual_per_aircraft_USD"])
    return out


def _totals(fl: Mapping[int, Mapping[str, float]], d: float | None) -> dict[str, float]:
    tot = {c: 0.0 for c in CATEGORIES}
    for t, row in fl.items():
        f = 1.0 if d is None else spv(t, d)
        for c, x in row.items():
            tot[c] += x * f
    tot["total"] = sum(tot[c] for c in CATEGORIES)
    return tot


def analyse(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Estudo genérico (API ``acdt.api.life_cycle_cost``). ``spec``:

    ``{fleet_size, service_life_years, production_rate_per_year, rdte_years, rdte_USD, unit_production_cost_USD,
    cost_per_fh_USD, fh_per_aircraft_per_year, disposal_per_aircraft_USD, residual_per_aircraft_USD,
    discount_rate (real), escalation_os (real), mission_duration_h, sources: {...}}`` — valores ou ``{lo, hi}``."""
    notes: list[str] = []
    n = int(spec["fleet_size"])
    life = int(spec["service_life_years"])
    rdte_years = int(spec.get("rdte_years", 0))
    rate = float(spec.get("production_rate_per_year") or n)
    sch = schedule(n, rdte_years, rate, life)
    notes.append(f"PRESSUPOSTO calendário: RDT&E uniforme nos anos 1..{rdte_years}; entregas {sch['deliveries']}; "
                 f"operação do ano seguinte à entrega durante {life} anos; abate no fim da vida")
    ranges: dict[str, tuple[float | None, float | None]] = {}
    unknown: list[str] = []
    for k in RANGE_KEYS:
        if k in ("residual_per_aircraft_USD", "escalation_os") and spec.get(k) is None:
            ranges[k] = (0.0, 0.0)
            notes.append("sem valor residual declarado: 0 (conservador)" if k.startswith("residual") else
                         "escalada real do O&S = 0 (dólares constantes, NIST HB 135 §3.3)")
            continue
        if k == "discount_rate" and spec.get(k) is None:
            ranges[k] = (None, None)
            notes.append("taxa de atualização não declarada: valor presente desconhecido (só dólares constantes)")
            continue
        lo, hi = rng(spec.get(k))
        if k == "fh_per_aircraft_per_year" and (lo is None or hi is None):
            raise ValueError("fh_per_aircraft_per_year (utilização) é obrigatória")
        if lo is None or hi is None:
            unknown.append(k)
        ranges[k] = (lo, hi)
    # cantos: entradas desconhecidas entram com 0 no minorante e tornam o majorante desconhecido
    var = [k for k in RANGE_KEYS if k != "discount_rate" and ranges[k][0] is not None and ranges[k][1] is not None
           and ranges[k][0] != ranges[k][1]]
    base = {k: (ranges[k][0] if ranges[k][0] is not None else 0.0) for k in RANGE_KEYS if k != "discount_rate"}
    dlo, dhi = ranges["discount_rate"]
    dgrid: list[float | None] = [None]
    if dlo is not None and dhi is not None:
        dgrid = [dlo + (dhi - dlo) * i / 10 for i in range(11)] if dhi != dlo else [dlo]
    corners = list(itertools.product(*[(ranges[k][0], ranges[k][1]) for k in var])) if len(var) <= 10 else \
        [tuple(ranges[k][0] for k in var), tuple(ranges[k][1] for k in var)]
    const: dict[str, list[float]] = {}
    pv: dict[str, list[float]] = {}
    per_fh: list[float] = []
    fh_tot: list[float] = []
    lo_flows = hi_flows = None
    for c in corners:
        p = dict(base)
        p.update({k: float(v) for k, v in zip(var, c) if v is not None})
        fl = flows(p, sch, rdte_years)
        tc = _totals(fl, None)
        for key, x in tc.items():
            const.setdefault(key, []).append(x)
        fh = sum(sch["active"].values()) * p["fh_per_aircraft_per_year"]
        fh_tot.append(fh)
        per_fh.append(tc["total"] / fh)
        for d in dgrid:
            if d is None:
                continue
            for key, x in _totals(fl, d).items():
                pv.setdefault(key, []).append(x)
        if c == corners[0]:
            lo_flows = fl
        if c == corners[-1]:
            hi_flows = fl
    unk_cat = {"rdte_USD": "rdte", "unit_production_cost_USD": "production", "cost_per_fh_USD": "operation_support",
               "disposal_per_aircraft_USD": "disposal"}
    unknown_cats = {unk_cat[k] for k in unknown if k in unk_cat}

    def band(vals: dict[str, list[float]], key: str) -> dict[str, float | None]:
        if key not in vals:
            return {"lo": None, "hi": None}
        hi_unknown = (key == "total" and unknown_cats) or key in unknown_cats
        return {"lo": min(vals[key]), "hi": None if hi_unknown else max(vals[key])}

    keys = list(CATEGORIES) + ["total"]
    out: dict[str, Any] = {
        "evaluated": True, "schema": "acdt.lcc/1",
        "status": "completo" if not unknown_cats else "parcial",
        "unknown_inputs": unknown,
        "constant_dollar_USD": {k: band(const, k) for k in keys},
        "present_value_USD": {k: band(pv, k) for k in keys},
        "fleet_flight_hours": {"lo": min(fh_tot), "hi": max(fh_tot)},
        "cost_per_flight_hour_USD": {"lo": min(per_fh), "hi": None if unknown_cats else max(per_fh)},
        "schedule": {"deliveries": sch["deliveries"], "last_year": sch["last_year"], "fleet_size": n,
                     "service_life_years": life, "rdte_years": rdte_years},
        "cash_flows_lo": {str(t): r for t, r in sorted((lo_flows or {}).items())},
        "cash_flows_hi": {str(t): r for t, r in sorted((hi_flows or {}).items())},
        "notes": notes, "sources": {**SOURCES, **dict(spec.get("sources") or {})},
    }
    out["life_cycle_cost_USD"] = out["present_value_USD"]["total"] if dgrid != [None] else \
        out["constant_dollar_USD"]["total"]
    out["life_cycle_cost_basis"] = "valor presente" if dgrid != [None] else "dólares constantes (sem atualização)"
    notes.append("custo por hora de voo = LCC em dólares constantes / horas de voo da frota (sem atualizar as horas)")
    t_m = spec.get("mission_duration_h")
    if t_m:
        c = out["cost_per_flight_hour_USD"]
        out["cost_per_mission_USD"] = {"lo": c["lo"] * float(t_m), "hi": None if c["hi"] is None else c["hi"] * float(t_m)}
    for k in unknown:
        notes.append(f"{k} desconhecido: a categoria só tem minorante 0 e o majorante do total fica desconhecido")
    return out
