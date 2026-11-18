# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Custo de produção em série (disciplina ``custo_serie``, L0; docs/CUSTO_SERIE.md).

Compõe o que já existia em :mod:`.costing` (DAPCA IV, Eastlake modificado, curvas de aprendizagem) — não há CER
nova aqui:

* **Varrimento em quantidade** de uma CER (Eastlake, Gudmundsson 2014 Cap. 2; DAPCA IV, Raymer 2018 Cap. 18):
  a CER é avaliada em cada N (as horas e o material das CER já dependem de N — a aprendizagem está *embutida* nos
  expoentes de quantidade, por isso **não** se aplica uma curva de aprendizagem por cima). Separação RDT&E /
  produção: RDT&E = engenharia + apoio ao desenvolvimento + ensaios em voo; produção não recorrente = ferramentas;
  produção recorrente = fabrico + controlo de qualidade + materiais + itens por aeronave (motor, hélice, aviónica,
  extras). PRESSUPOSTO: é a classificação fixo/variável de Gudmundsson (2014) Cap. 2 já usada em
  ``CostBreakdown.fixed``, com as ferramentas atribuídas à produção (não recorrente).
* **Amortização das ferramentas** e do RDT&E por unidade: C_ferramentas(N)/N e C_RDT&E(N)/N.
* **Custo unitário de saída de fábrica (flyaway)** = recorrente(N)/N + itens por aeronave; **custo unitário médio**
  = custo do programa(N)/N (o da CER, com a fração de responsabilidade civil/lucro declarada).
* **Lote**: custo recorrente incremental entre N₁ e N₂ = rec(N₂) − rec(N₁) (CER) ou soma da curva de aprendizagem
  (rota de baixo para cima: primeira unidade T1 declarada ou do plano de fabrico).
* **Ponto de equilíbrio**: menor N com receita P·N ≥ custo do programa(N) (definição; estrutura custos fixos /
  variáveis de Gudmundsson 2014 Cap. 2). Se não for atingido até ``n_max`` → ``None`` (não atingido ≠ zero).
* **Efeito de cadência**: só o que a CER de Eastlake já tem (horas de ferramentas ∝ Q_m^0,066, Gudmundsson 2014
  Cap. 2, Eq. 2.2–2.13); nenhum outro modelo de cadência (sem fonte verificável).
"""
from __future__ import annotations

import math
from typing import Any, Callable, Mapping, Sequence

from ..cost import EastlakeInputs, eastlake_unit_cost
from .costing import DapcaInputs, dapca4, learning_b, learning_lot, learning_unit, wright_unit

CER_METHODS = ("eastlake", "dapca4")
REFS = {
    "eastlake": "Gudmundsson (2014) General Aviation Aircraft Design, Cap. 2 (Eastlake modificado, Eq. 2.2–2.13)",
    "dapca4": "Raymer (2018) Aircraft Design: A Conceptual Approach, 6.ª ed., Cap. 18 (DAPCA IV)",
    "learning": "Wright (1936) J. Aeronaut. Sci. 3(4); Crawford (1944); FAA Pricing Handbook (1998) Cap. 18 "
                "Eq. 18-7/18-9/18-10",
}


def cer_point(method: str, inputs: Mapping[str, Any], N: int) -> dict[str, Any]:
    """Uma CER avaliada à quantidade N, decomposta em RDT&E / ferramentas / recorrente."""
    N = int(N)
    if N < 1:
        raise ValueError("N ≥ 1")
    if method == "eastlake":
        x = EastlakeInputs(**{**dict(inputs), "N": N})
        cb = eastlake_unit_cost(x)
        rdte = cb.engineering + cb.dev_support + cb.flight_test
        tooling = cb.tooling
        rec_body = cb.manufacturing + cb.quality + cb.materials
        per_ac = cb.per_unit_variable
        markup = x.liability_fraction
        unit = cb.unit_cost
    elif method == "dapca4":
        d = dict(inputs)
        d["Q"] = N
        r = dapca4(DapcaInputs(**d))
        c = r["costs"]
        rdte = c["engineering"] + c["dev_support"] + c["flight_test"]
        tooling = c["tooling"]
        rec_body = c["manufacturing"] + c["quality"] + c["materials"]
        per_ac = c["engines_per_aircraft"] + c["avionics_per_aircraft"]
        markup = float(d.get("profit_fraction", 0.0))
        unit = r["unit_cost"]
    else:
        raise ValueError(f"método {method!r} não está em {CER_METHODS}")
    recurring = rec_body + per_ac * N
    flyaway = recurring / N
    total = unit * N
    return {"N": N, "rdte_USD": rdte, "tooling_USD": tooling, "recurring_USD": recurring,
            "per_aircraft_items_USD": per_ac,
            "flyaway_unit_cost_USD": flyaway, "rdte_amortisation_USD": rdte / N, "tooling_amortisation_USD": tooling / N,
            "markup_fraction": markup, "average_unit_cost_USD": unit, "total_program_USD": total}


def quantity_sweep(method: str, inputs: Mapping[str, Any], quantities: Sequence[int]) -> list[dict[str, Any]]:
    rows = [cer_point(method, inputs, int(n)) for n in sorted({int(q) for q in quantities if int(q) >= 1})]
    prev: dict[str, Any] | None = None
    for r in rows:  # lote incremental (custo recorrente) desde a quantidade anterior do varrimento
        if prev is not None:
            dn = r["N"] - prev["N"]
            r["batch"] = {"from": prev["N"] + 1, "to": r["N"],
                          "recurring_USD": r["recurring_USD"] - prev["recurring_USD"],
                          "average_recurring_per_unit_USD": (r["recurring_USD"] - prev["recurring_USD"]) / dn}
        prev = r
    return rows


def learning_program(T1: float, slope: float, theory: str, N: int, *, nre: float = 0.0,
                     per_aircraft_items: float = 0.0, lots: Sequence[int] | None = None) -> dict[str, Any]:
    """Rota de baixo para cima: custo recorrente da 1.ª unidade T1 (p. ex. o plano de fabrico) com uma curva de
    aprendizagem; ``nre`` = não recorrente declarado (RDT&E + ferramentas)."""
    N = int(N)
    total_rec = learning_lot(T1, 1, N, slope, theory)
    last = learning_unit(T1, N, slope) if theory == "crawford" else wright_unit(T1, N, slope)
    out: dict[str, Any] = {
        "T1_USD": T1, "slope": slope, "b": learning_b(slope), "theory": theory, "N": N,
        "recurring_USD": total_rec + per_aircraft_items * N, "unit_N_cost_USD": last + per_aircraft_items,
        "flyaway_unit_cost_USD": total_rec / N + per_aircraft_items, "nre_USD": nre, "nre_amortisation_USD": nre / N,
        "average_unit_cost_USD": (nre + total_rec) / N + per_aircraft_items,
        "total_program_USD": nre + total_rec + per_aircraft_items * N}
    if lots:
        rows, first = [], 1
        for size in lots:
            last_u = first + int(size) - 1
            c = learning_lot(T1, first, last_u, slope, theory)
            rows.append({"first": first, "last": last_u, "size": int(size), "recurring_USD": c,
                         "average_per_unit_USD": c / int(size) + per_aircraft_items})
            first = last_u + 1
        out["lots"] = rows
    return out


def break_even(price: float, total_cost: Callable[[int], float], n_max: int = 10000) -> int | None:
    """Menor N (1..n_max) com P·N ≥ custo total do programa(N); ``None`` se não for atingido (≠ zero)."""
    for n in range(1, int(n_max) + 1):
        if price * n >= total_cost(n):
            return n
    return None


def learning_total_cost_fn(T1: float, slope: float, theory: str, nre: float,
                           per_aircraft_items: float) -> Callable[[int], float]:
    """Custo total do programa(N) para a rota da curva de aprendizagem, incremental (O(1) por chamada sequencial)."""
    cache: dict[int, float] = {0: 0.0}
    b = learning_b(slope)

    def f(n: int) -> float:
        if theory == "wright":
            rec = T1 * n ** (1 + b)
        else:
            k = max(cache)
            s = cache[k]
            while k < n:
                k += 1
                s += T1 * k ** b
                cache[k] = s
            rec = cache[n]
        return float(nre + rec + per_aircraft_items * n)
    return f


def analyse(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Estudo genérico (API ``acdt.api.series_cost``).

    ``spec``: ``{method: eastlake|dapca4|learning, inputs: {...CER...}, quantity: N, quantities: [..],
    price: P (preço de venda nominal), prices: [P..] (tabela N_equilíbrio vs preço), n_max,
    learning: {T1, slope, slope_source, theory, nre, per_aircraft_items, lots: [..]}}``. Moeda: USD (CER: 2012 ×
    cpi; ``learning``: declare T1/NRE em USD)."""
    method = str(spec.get("method", "eastlake"))
    N = int(spec.get("quantity") or 0) or None
    quantities = [int(q) for q in (spec.get("quantities") or [])]
    if N is not None:
        quantities.append(N)
    n_max = int(spec.get("n_max", 10000))
    price = spec.get("price")
    prices = [float(p) for p in (spec.get("prices") or [])]
    if price is not None:
        prices.append(float(price))
    out: dict[str, Any] = {"evaluated": True, "method": method, "notes": [], "sources": {}}
    if method in CER_METHODS:
        inputs = dict(spec.get("inputs") or {})
        if not quantities:
            raise ValueError("dê quantity ou quantities")
        rows = quantity_sweep(method, inputs, quantities)
        out["sweep"] = rows
        out["sources"]["cer"] = REFS[method]
        out["notes"].append("a CER já inclui o efeito de quantidade (aprendizagem embutida): sem curva por cima")

        def tot(n: int) -> float:
            return float(cer_point(method, inputs, n)["total_program_USD"])
        cost_fn: Callable[[int], float] = tot
        at = cer_point(method, inputs, N) if N is not None else None
    elif method == "learning":
        lc = dict(spec.get("learning") or {})
        if lc.get("T1") is None:
            raise ValueError("learning.T1 (custo recorrente da 1.ª unidade) em falta")
        T1, slope, theory = float(lc["T1"]), float(lc.get("slope", 0.85)), str(lc.get("theory", "crawford"))
        nre, pa = float(lc.get("nre", 0.0)), float(lc.get("per_aircraft_items", 0.0))
        if lc.get("nre") is None:
            out["notes"].append("learning.nre não declarado: custo não recorrente desconhecido — o custo médio e o "
                                "ponto de equilíbrio são limites inferiores")
            out["nre_declared"] = False
        if not quantities:
            raise ValueError("dê quantity ou quantities")
        out["sweep"] = [learning_program(T1, slope, theory, n, nre=nre, per_aircraft_items=pa)
                        for n in sorted(set(quantities))]
        out["sources"]["learning"] = REFS["learning"]
        if "slope_source" in lc:
            out["sources"]["slope"] = lc["slope_source"]
        else:
            out["notes"].append(f"PRESSUPOSTO: declive {slope:g} sem fonte declarada (learning.slope_source)")
        at = learning_program(T1, slope, theory, N, nre=nre, per_aircraft_items=pa,
                              lots=lc.get("lots")) if N is not None else None
        cost_fn = learning_total_cost_fn(T1, slope, theory, nre, pa)
    else:
        raise ValueError(f"método {method!r} desconhecido (eastlake, dapca4, learning)")
    if at is not None:
        out["at_quantity"] = at
        out["quantity"] = N
        out["average_unit_cost_USD"] = at["average_unit_cost_USD"]
        out["flyaway_cost_USD"] = at["flyaway_unit_cost_USD"]
        out["total_program_USD"] = at["total_program_USD"]
    be = []
    for p in sorted(set(prices)):
        n_be = break_even(p, cost_fn, n_max)
        be.append({"price_USD": p, "break_even_quantity": n_be,
                   "status": "atingido" if n_be is not None else f"não atingido até N={n_max}"})
    out["break_even"] = be
    out["price_USD"] = None if price is None else float(price)
    out["break_even_quantity"] = None if price is None else \
        next(r["break_even_quantity"] for r in be if r["price_USD"] == float(price))
    if not prices:
        out["notes"].append("sem preço de venda declarado: ponto de equilíbrio desconhecido")
    if out.get("nre_declared") is False:
        out["break_even_quantity"] = None
        for r in be:
            r["lower_bound_quantity"] = r.pop("break_even_quantity")
            r["status"] = "limite inferior (NRE desconhecido)"
    return out


def finite(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x))
