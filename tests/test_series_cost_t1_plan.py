# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Custo de série: T1 tirado do plano de fabrico da Fase 7 (sem T1 declarado)."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _with(res, **assumptions):
    r = copy.copy(res)
    r.spec = copy.copy(res.spec)
    r.spec.assumptions = {**copy.deepcopy(res.spec.assumptions), **assumptions}
    return r


@pytest.fixture(scope="module")
def mcfg():
    from acdt.domains.aircraft.manufacturing.study import load_config
    return load_config(ROOT / "examples/manufacturing/cessna172_manufacturing.yaml")["manufacturing"]


@pytest.mark.slow
def test_t1_from_plan_undoes_only_the_learning_factor(c172_result, mcfg):
    from acdt.domains.aircraft.manufacturing.study import study
    from acdt.domains.aircraft.series_cost import analyse_series_cost, t1_from_manufacturing

    t1 = t1_from_manufacturing(c172_result, mcfg)
    pl = study(c172_result, mcfg, out=None, plots=False)["plan"]
    assert t1["T1_USD"] == pytest.approx(pl["totals"]["labour_cost"] / pl["learning_factor"])
    assert t1["non_learning_USD"] == pytest.approx(pl["totals"]["material_cost"] + pl["totals"]["fastener_cost"]
                                                   + pl["totals"]["machine_cost"])
    assert t1["plan_N"] == mcfg["N"] and t1["plan_learning_factor"] < 1.0
    # mesma curva do plano → a média de N unidades da rota learning devolve o custo de mão de obra do plano
    res = _with(c172_result, manufacturing=mcfg,
                series_cost={"method": "learning", "quantity": int(mcfg["N"]), "learning": {"nre": 0.0}})
    sc = analyse_series_cost(res)
    at = sc["at_quantity"]
    rec_avg = at["recurring_USD"] / at["N"] - t1["per_aircraft_items_USD"]
    assert rec_avg == pytest.approx(pl["totals"]["labour_cost"], rel=1e-9)
    assert sc["T1_from_plan"]["T1_USD"] == pytest.approx(t1["T1_USD"]) and "T1" in sc["sources"]
    if t1["final_assembly_USD"] is None:   # montagem final não declarada → limite inferior, nunca valor fechado
        assert t1["complete"] is False and isinstance(sc["flyaway_cost_USD"], dict)
        assert sc["flyaway_cost_USD"]["hi"] is None
    # T1 declarado tem prioridade sobre o plano
    decl = analyse_series_cost(_with(c172_result, manufacturing=mcfg, series_cost={
        "method": "learning", "quantity": 10, "learning": {"T1": 1.0e5, "nre": 0.0}}))
    assert "T1_from_plan" not in decl and decl["at_quantity"]["T1_USD"] == 1.0e5


def test_t1_from_plan_refuses_without_plan_or_with_standard_hours(c172_result, mcfg):
    from acdt.domains.aircraft.series_cost import series_cost_stage, t1_from_manufacturing

    with pytest.raises(ValueError):
        t1_from_manufacturing(c172_result, None)
    with pytest.raises(ValueError, match="standard"):
        t1_from_manufacturing(c172_result, {**mcfg, "hours_basis": "standard"})
    res = _with(c172_result, series_cost={"method": "learning", "quantity": 10,
                                          "learning": {"T1_from": "manufacturing"}})
    res.issues = []
    series_cost_stage(res)
    assert res.series_cost["evaluated"] is False and res.series_cost["average_unit_cost_USD"] is None
