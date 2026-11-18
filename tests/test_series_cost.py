# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Disciplina custo de série (docs/CUSTO_SERIE.md): V&V FAA Pricing Handbook Cap. 18, varrimento das CER em N,
RDT&E vs produção, amortização, aprendizagem, ponto de equilíbrio, desconhecidos, API e pipeline."""
from __future__ import annotations

import math
from pathlib import Path

import pytest

EX = Path(__file__).resolve().parents[1] / "examples"


# ------------------------------------------------------------------------------------------ V&V (FAA Cap. 18)
def test_faa18_slope_and_two_units():
    from acdt.domains.aircraft.manufacturing.costing import learning_b, learning_lot

    assert learning_b(0.9) == pytest.approx(-0.15200, abs=5e-5)
    assert learning_lot(100.0, 1, 2, 0.9, "crawford") == pytest.approx(190.0)
    assert learning_lot(100.0, 1, 2, 0.9, "wright") == pytest.approx(180.0)


def test_faa18_case_18_2():
    from acdt.domains.aircraft.manufacturing.costing import learning_lot, lot_midpoint, learning_unit

    assert learning_lot(103.45, 11, 15, 2 ** -0.04, "wright") == pytest.approx(449.0, abs=1.0)
    s = 2 ** -0.15
    assert learning_lot(102.73, 1, 2, s, "crawford", "approx") == pytest.approx(196.0, abs=0.5)
    assert learning_lot(102.73, 11, 15, s, "crawford", "approx") == pytest.approx(350.0, abs=0.5)
    ex = learning_lot(102.73, 11, 15, s, "crawford", "exact")
    assert ex == pytest.approx(350.0, abs=0.5)
    # ponto médio: a unidade cujo custo iguala a média do lote
    x = lot_midpoint(11, 15, s)
    assert 11 < x < 13 and learning_unit(102.73, x, s) == pytest.approx(ex / 5, rel=1e-12)


def test_vv_cases_registered_and_pass():
    from acdt.core import vv

    r = vv.run(disciplines=["custo_serie"])
    st = {c["id"]: c["status"] for c in r["cases"]}
    assert len(st) == 3 and set(st.values()) == {"passa"}


def test_wright_unit_consistency_and_validation():
    from acdt.domains.aircraft.manufacturing.costing import learning_lot, wright_unit

    tot = sum(wright_unit(50.0, n, 0.85) for n in range(1, 21))
    assert tot == pytest.approx(learning_lot(50.0, 1, 20, 0.85, "wright"), rel=1e-12)
    with pytest.raises(ValueError):
        learning_lot(1.0, 5, 4)
    with pytest.raises(ValueError):
        learning_lot(1.0, 1, 4, 0.85, "boeing")
    with pytest.raises(ValueError):
        learning_lot(1.0, 1, 4, 1.2)


# ------------------------------------------------------------------------------------------ CER em função de N
EAST = {"W_airframe_kg": 500.0, "V_H_kt": 150.0, "engine_cost": 30000.0, "avionics_cost": 15000.0}


def test_eastlake_split_reproduces_unit_cost():
    from acdt.domains.aircraft.cost import EastlakeInputs, eastlake_unit_cost
    from acdt.domains.aircraft.manufacturing.series import cer_point

    p = cer_point("eastlake", EAST, 300)
    ref = eastlake_unit_cost(EastlakeInputs(**EAST, N=300))
    assert p["average_unit_cost_USD"] == pytest.approx(ref.unit_cost, rel=1e-12)
    assert p["rdte_USD"] + p["tooling_USD"] + p["recurring_USD"] == pytest.approx(ref.unit_cost * 300, rel=1e-12)
    assert p["tooling_USD"] == pytest.approx(ref.tooling)
    assert p["flyaway_unit_cost_USD"] == pytest.approx(ref.variable_per_unit, rel=1e-12)
    assert p["tooling_amortisation_USD"] == pytest.approx(ref.tooling / 300)


def test_dapca_split_reproduces_programme():
    from acdt.domains.aircraft.manufacturing.costing import DapcaInputs, dapca4
    from acdt.domains.aircraft.manufacturing.series import cer_point

    inp = {"We_kg": 2000.0, "V_kt": 250.0, "engine_cost": 200000.0, "avionics_cost": 50000.0}
    p = cer_point("dapca4", inp, 100)
    r = dapca4(DapcaInputs(**inp, Q=100))
    assert p["rdte_USD"] + p["tooling_USD"] == pytest.approx(r["non_recurring"], rel=1e-12)
    assert p["recurring_USD"] == pytest.approx(r["recurring"], rel=1e-12)
    assert p["flyaway_unit_cost_USD"] == pytest.approx(r["flyaway_per_unit"], rel=1e-12)


def test_sweep_trends_and_batches():
    from acdt.domains.aircraft.manufacturing.series import quantity_sweep

    rows = quantity_sweep("eastlake", EAST, [10, 100, 1000, 100])
    assert [r["N"] for r in rows] == [10, 100, 1000]
    avg = [r["average_unit_cost_USD"] for r in rows]
    fly = [r["flyaway_unit_cost_USD"] for r in rows]
    assert avg[0] > avg[1] > avg[2] and fly[0] > fly[1] > fly[2]  # expoentes de N < 1 nas horas de fabrico
    assert all(r["average_unit_cost_USD"] > r["flyaway_unit_cost_USD"] for r in rows)
    b = rows[1]["batch"]
    assert b["from"] == 11 and b["to"] == 100
    assert b["recurring_USD"] == pytest.approx(rows[1]["recurring_USD"] - rows[0]["recurring_USD"])


def test_break_even_cer_and_unreached():
    from acdt.domains.aircraft.manufacturing.series import analyse, cer_point

    r = analyse({"method": "eastlake", "inputs": EAST, "quantity": 500, "price": 400000.0,
                 "prices": [100000.0, 10.0e6], "n_max": 3000})
    n = r["break_even_quantity"]
    assert n is not None
    assert 400000.0 * n >= cer_point("eastlake", EAST, n)["total_program_USD"]
    assert 400000.0 * (n - 1) < cer_point("eastlake", EAST, n - 1)["total_program_USD"]
    tab = {b["price_USD"]: b for b in r["break_even"]}
    assert tab[100000.0]["break_even_quantity"] is None and "não atingido" in tab[100000.0]["status"]
    assert tab[10.0e6]["break_even_quantity"] < n
    r2 = analyse({"method": "eastlake", "inputs": EAST, "quantity": 50})
    assert r2["break_even_quantity"] is None and any("preço" in x for x in r2["notes"])


def test_learning_route_lots_and_unknown_nre():
    from acdt.domains.aircraft.manufacturing.series import analyse

    r = analyse({"method": "learning", "quantity": 10, "price": 90.0,
                 "learning": {"T1": 100.0, "slope": 0.85, "nre": 1000.0, "lots": [2, 3, 5], "slope_source": "x"}})
    at = r["at_quantity"]
    assert sum(lot["recurring_USD"] for lot in at["lots"]) == pytest.approx(at["recurring_USD"])
    assert at["average_unit_cost_USD"] == pytest.approx((1000 + at["recurring_USD"]) / 10)
    n = r["break_even_quantity"]
    assert n is not None and n > 10
    # Wright: forma fechada
    rw = analyse({"method": "learning", "quantity": 8,
                  "learning": {"T1": 100.0, "slope": 0.8, "theory": "wright", "nre": 0.0}})
    assert rw["at_quantity"]["flyaway_unit_cost_USD"] == pytest.approx(100 * 0.8 ** 3)
    # sem NRE declarado: limites inferiores, nunca um equilíbrio «atingido»
    ru = analyse({"method": "learning", "quantity": 10, "price": 90.0, "learning": {"T1": 100.0}})
    assert ru["break_even_quantity"] is None and ru["break_even"][0]["lower_bound_quantity"] is not None
    assert any("PRESSUPOSTO" in x for x in ru["notes"])
    with pytest.raises(ValueError):
        analyse({"method": "learning", "quantity": 10, "learning": {}})
    with pytest.raises(ValueError):
        analyse({"method": "rand", "quantity": 10})


def test_api():
    from acdt import api

    assert tuple(int(x) for x in api.API_VERSION.split(".")) >= (1, 6, 0)
    r = api.series_cost({"method": "eastlake", "inputs": EAST, "quantity": 100})
    assert r["evaluated"] and r["average_unit_cost_USD"] > r["flyaway_cost_USD"] > 0
    c = api.learning_curve(102.73, 2 ** -0.15, 11, 15, method="approx")
    assert c["lot_total"] == pytest.approx(350.0, abs=0.5) and 11 < c["lot_midpoint"] < 15


# ------------------------------------------------------------------------------------------ pipeline
def _mission():
    import yaml

    d = yaml.safe_load((EX / "uav_endurance_payload.yaml").read_text(encoding="utf-8"))
    d.setdefault("assumptions", {}).setdefault("aero", {})["fidelity"] = "handbook"
    d["assumptions"].setdefault("stability", {})["use_avl"] = False
    d.pop("systems", None)
    return d


@pytest.mark.slow
def test_series_cost_stage_requirements_and_db():
    """UAV de exemplo (só teste; o projeto não muda): sem pedido → não avaliada; com pedido, requisitos na matriz
    de verificação (quantidade do qualificador) e no design.json."""
    from acdt.core.pipeline import run_pipeline
    from acdt.domains.aircraft.mission import MissionSpec

    d = _mission()
    st = run_pipeline("aircraft", MissionSpec.from_dict(d, EX / "uav_endurance_payload.yaml"))
    assert st["result"].series_cost["evaluated"] is False
    d["assumptions"]["series_cost"] = {"quantity": 200, "price": 150000.0, "prices": [50000.0]}
    d["requirements"]["unit_cost_at_quantity"] = {"max": 1e6, "quantity": 100, "id": "SC-01"}
    d["requirements"]["flyaway_cost"] = {"max": 1.0, "id": "SC-02"}
    d["requirements"]["break_even_quantity"] = {"max": 1000, "id": "SC-03"}
    st2 = run_pipeline("aircraft", MissionSpec.from_dict(d, EX / "uav_endurance_payload.yaml"))
    sc = st2["result"].series_cost
    assert sc["evaluated"] and sc["at_requirement"]["unit_cost_at_quantity"]["quantity"] == 100
    assert sc["unit_cost_at_quantity_USD"] > sc["average_unit_cost_USD"]  # N = 100 < 200
    assert any("extrapolação" in n for n in sc["adapter_notes"])
    rows = {r["id"]: r for r in st2["verification"]["rows"]}
    assert rows["SC-01"]["status"] == "passa" and rows["SC-02"]["status"] == "falha"
    assert rows["SC-03"]["status"] == "passa"
    q = st2["design"]["results"]["custo_serie"]["L0"]["quantities"]
    assert q["series_cost.average_unit_cost_USD"]["unit"] == "USD_acdt"
    # sem preço o requisito de equilíbrio fica desconhecido (nunca passa)
    d["assumptions"]["series_cost"].pop("price")
    st3 = run_pipeline("aircraft", MissionSpec.from_dict(d, EX / "uav_endurance_payload.yaml"))
    rows3 = {r["id"]: r for r in st3["verification"]["rows"]}
    assert rows3["SC-03"]["status"] == "desconhecido"
    assert not math.isnan(st3["result"].series_cost["flyaway_cost_USD"])
