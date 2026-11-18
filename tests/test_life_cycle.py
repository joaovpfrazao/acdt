# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Disciplina ciclo de vida (docs/CICLO_VIDA.md): V&V NIST Handbook 135 e CORSIA, LCC por categorias com
calendário, intervalos e desconhecidos, CO₂e, API e pipeline."""
from __future__ import annotations

from pathlib import Path

import pytest

EX = Path(__file__).resolve().parents[1] / "examples"


# ------------------------------------------------------------------------------------------ V&V
def test_nist135_factors():
    from acdt.core.lcc.discount import spv, upv, upv_star

    assert spv(15, 0.03) == pytest.approx(0.642, abs=5e-4)
    assert upv(15, 0.03) == pytest.approx(11.94, abs=5e-3)
    assert upv_star(15, 0.03, 0.02) == pytest.approx(13.89, abs=5e-3)
    assert 1000 * spv(5, 0.03) == pytest.approx(862.61, abs=5e-3)
    assert 100 * upv(5, 0.03) == pytest.approx(457.97, abs=5e-3)
    assert 100 * upv_star(5, 0.03, 0.02) == pytest.approx(485.62, abs=5e-3)
    # formas fechadas = somas
    assert upv(20, 0.05) == pytest.approx(sum(spv(t, 0.05) for t in range(1, 21)))
    assert upv_star(7, 0.04, 0.04) == pytest.approx(7.0) and upv(9, 0.0) == 9.0


def test_nist135_rates():
    from acdt.core.lcc.discount import nominal_rate, real_rate

    assert real_rate(0.07, 0.04) == pytest.approx(0.02885, abs=5e-6)
    assert nominal_rate(0.03, 0.04) == pytest.approx(0.0712, abs=5e-5)


def test_nist135_example_5_1a():
    from acdt.core.lcc.lcc import present_value

    items = [{"amount": 103000.0, "year": 0}, {"amount": 12000.0, "year": 12}, {"amount": -3500.0, "year": 20},
             {"amount": 20000.0, "factor": 15.13}, {"amount": 7000.0, "annual": [1, 20]}]
    assert present_value(items, 0.03) == pytest.approx(516233.0, rel=1e-4)


def test_corsia_fcf():
    from acdt.core.lcc.environment import analyse

    r = analyse({"fuel_kg_per_fh": 1000.0, "fuel": "jet_a"})
    assert r["per_flight_hour_kgCO2e"]["fuel_combustion_CO2"]["lo"] == pytest.approx(3160.0)
    r = analyse({"fuel_kg_per_fh": 1000.0, "fuel": "avgas", "lhv_MJ_kg": 43.5})
    p = r["per_flight_hour_kgCO2e"]
    assert p["fuel_combustion_CO2"]["hi"] == pytest.approx(3100.0)
    assert p["fuel_well_to_wake_CO2e"]["lo"] == pytest.approx(1000 * 43.5 * 0.095)
    assert r["operation_per_fh_kgCO2e"]["lo"] == pytest.approx(1000 * 43.5 * 0.095)  # WTW inclui a combustão


def test_vv_cases_registered_and_pass():
    from acdt.core import vv

    r = vv.run(disciplines=["ciclo_vida"])
    st = {c["id"]: c["status"] for c in r["cases"]}
    assert len(st) == 4 and set(st.values()) == {"passa"}


# ------------------------------------------------------------------------------------------ LCC
BASE = {"fleet_size": 10, "service_life_years": 10, "production_rate_per_year": 5, "rdte_years": 2,
        "rdte_USD": 1e6, "unit_production_cost_USD": 2e4, "cost_per_fh_USD": 50.0, "fh_per_aircraft_per_year": 300,
        "disposal_per_aircraft_USD": 500.0, "discount_rate": 0.05}


def test_lcc_hand_calculation():
    from acdt.core.lcc.discount import spv
    from acdt.core.lcc.lcc import analyse

    r = analyse(BASE)
    assert r["status"] == "completo" and r["schedule"]["deliveries"] == {3: 5, 4: 5}
    c = r["constant_dollar_USD"]
    assert c["rdte"]["lo"] == 1e6 and c["production"]["lo"] == 2e5
    assert c["operation_support"]["lo"] == pytest.approx(10 * 10 * 300 * 50.0)
    assert c["disposal"]["lo"] == pytest.approx(5000.0)
    pv_hand = (5e5 * (spv(1, .05) + spv(2, .05)) + 1e5 * (spv(3, .05) + spv(4, .05))
               + sum(5 * 300 * 50 * spv(t, .05) for t in range(4, 14))
               + sum(5 * 300 * 50 * spv(t, .05) for t in range(5, 15))
               + 2500 * (spv(13, .05) + spv(14, .05)))
    assert r["present_value_USD"]["total"]["lo"] == pytest.approx(pv_hand, rel=1e-12)
    assert r["life_cycle_cost_USD"]["hi"] == pytest.approx(pv_hand, rel=1e-12)
    assert r["cost_per_flight_hour_USD"]["lo"] == pytest.approx(c["total"]["lo"] / 30000.0)
    assert r["fleet_flight_hours"]["lo"] == 30000.0


def test_lcc_ranges_unknowns_and_escalation():
    from acdt.core.lcc.lcc import analyse

    r = analyse({**BASE, "cost_per_fh_USD": {"lo": 40.0, "hi": 60.0}, "discount_rate": {"lo": 0.03, "hi": 0.07}})
    t = r["present_value_USD"]["total"]
    assert t["lo"] < t["hi"]
    r2 = analyse({**BASE, "disposal_per_aircraft_USD": None})
    assert r2["status"] == "parcial" and r2["life_cycle_cost_USD"]["hi"] is None
    assert r2["life_cycle_cost_USD"]["lo"] is not None and r2["cost_per_flight_hour_USD"]["hi"] is None
    r3 = analyse({**BASE, "discount_rate": None})
    assert r3["present_value_USD"]["total"]["lo"] is None and "dólares constantes" in r3["life_cycle_cost_basis"]
    r4 = analyse({**BASE, "escalation_os": 0.02})
    assert r4["constant_dollar_USD"]["operation_support"]["lo"] > r["constant_dollar_USD"]["operation_support"]["lo"]
    r5 = analyse({**BASE, "residual_per_aircraft_USD": 1000.0})
    assert r5["constant_dollar_USD"]["residual"]["lo"] == pytest.approx(-10000.0)
    with pytest.raises(ValueError):
        analyse({**BASE, "fh_per_aircraft_per_year": None})


def test_environment_electric_unknowns_and_battery():
    from acdt.core.lcc.environment import analyse

    r = analyse({"battery_kWh_per_fh": 1.0})
    assert r["status"] == "parcial" and r["operation_per_fh_kgCO2e"]["hi"] is None
    r = analyse({"battery_kWh_per_fh": 1.0, "charge_efficiency": 0.9,
                 "grid_intensity_kgCO2e_per_kWh": {"lo": 0.1, "hi": 0.3, "source": "teste"},
                 "battery_capacity_kWh": 2.0, "battery_cycle_life": 500, "flights_per_fh": 0.25,
                 "battery_footprint": "ivl_c444_2019", "aircraft_flight_hours": 3000.0})
    assert r["operation_per_fh_kgCO2e"]["lo"] == pytest.approx(0.1 / 0.9)
    assert r["battery_packs_per_aircraft"]["lo"] == 2.0  # 750 ciclos / 500
    assert r["battery_manufacturing_per_aircraft_kgCO2e"]["lo"] == pytest.approx(2 * 2.0 * 61.0)
    assert r["battery_manufacturing_per_aircraft_kgCO2e"]["hi"] == pytest.approx(2 * 2.0 * 106.0)
    r = analyse({"battery_kWh_per_fh": 1.0, "charge_efficiency": 0.9, "grid_intensity_kgCO2e_per_kWh": 0.2,
                 "battery_capacity_kWh": 2.0, "aircraft_flight_hours": 3000.0})
    assert r["status"] == "parcial" and r["battery_manufacturing_per_aircraft_kgCO2e"]["lo"] is None
    assert r["life_per_aircraft_kgCO2e"]["hi"] is None
    r = analyse({"fuel_kg_per_fh": 5.0, "fuel": "biofuel"})
    assert r["status"] == "parcial"


def test_api():
    from acdt import api

    assert tuple(int(x) for x in api.API_VERSION.split(".")) >= (1, 7, 0)
    assert api.life_cycle_cost(BASE)["status"] == "completo"
    assert api.life_cycle_emissions({"fuel_kg_per_fh": 1.0, "fuel": "jet_a"})["status"] == "completo"
    assert api.present_value([{"amount": 1000.0, "year": 5}], 0.03) == pytest.approx(862.61, abs=5e-3)


# ------------------------------------------------------------------------------------------ pipeline
def _mission(name: str = "uav_endurance_payload.yaml"):
    import yaml

    d = yaml.safe_load((EX / name).read_text(encoding="utf-8"))
    d.setdefault("assumptions", {}).setdefault("aero", {})["fidelity"] = "handbook"
    d["assumptions"].setdefault("stability", {})["use_avl"] = False
    d.pop("systems", None)
    return d


@pytest.mark.slow
def test_life_cycle_stage_electric_requirements_and_db():
    """UAV elétrico de exemplo (só teste; o projeto não muda)."""
    from acdt.core.pipeline import run_pipeline
    from acdt.domains.aircraft.mission import MissionSpec

    d = _mission()
    st = run_pipeline("aircraft", MissionSpec.from_dict(d, EX / "uav_endurance_payload.yaml"))
    assert st["result"].life_cycle["evaluated"] is False
    d["assumptions"]["series_cost"] = {"quantity": 50, "price": 60000}
    d["assumptions"]["life_cycle"] = {
        "service_life_years": 10, "production_rate_per_year": 20, "rdte_years": 2,
        "fh_per_aircraft_per_year": {"lo": 300, "hi": 500}, "cost_per_fh_USD": {"lo": 40, "hi": 90},
        "disposal_per_aircraft_USD": None, "discount_rate": 0.05,
        "environment": {"grid_intensity_kgCO2e_per_kWh": {"lo": 0.1, "hi": 0.4, "source": "teste"},
                        "charge_efficiency": 0.9, "battery_footprint": "ivl_c444_2019", "battery_cycle_life": 400,
                        "flights_per_fh": 0.25}}
    d["requirements"]["life_cycle_cost"] = {"max": 1e12, "id": "LC-01"}
    d["requirements"]["co2e_per_flight_hour"] = {"max": 5, "id": "LC-02"}
    d["requirements"]["life_cycle_cost_per_fh"] = {"max": 1.0, "id": "LC-03"}
    st2 = run_pipeline("aircraft", MissionSpec.from_dict(d, EX / "uav_endurance_payload.yaml"))
    lc = st2["result"].life_cycle
    assert lc["evaluated"] and lc["status"] == "parcial"  # abate desconhecido
    assert any("custo de série" in n for n in lc["adapter_notes"])
    rows = {r["id"]: r for r in st2["verification"]["rows"]}
    assert rows["LC-01"]["status"] == "desconhecido"  # majorante desconhecido nunca passa
    assert rows["LC-02"]["status"] == "passa"
    assert rows["LC-03"]["status"] == "falha"  # o minorante já excede
    assert "L0" in st2["design"]["results"]["ciclo_vida"]


@pytest.mark.slow
def test_life_cycle_stage_fuel_from_reliability_operating_cost():
    from acdt.core.pipeline import run_pipeline
    from acdt.domains.aircraft.mission import MissionSpec

    d = _mission("uav_gasoline_150kg.yaml")
    d["assumptions"]["life_cycle"] = {
        "fleet_size": 12, "service_life_years": 8, "fh_per_aircraft_per_year": 400, "rdte_USD": 2e6,
        "unit_production_cost_USD": 1.5e5, "disposal_per_aircraft_USD": 0.0, "discount_rate": 0.04,
        "operating_cost": {"flight_hours_per_year": 400, "unit_price": 1.5e5, "fuel_kg_per_h": 6.0,
                           "fuel_price_per_kg": 2.0, "depreciation_years": 8}}
    st = run_pipeline("aircraft", MissionSpec.from_dict(d, EX / "uav_gasoline_150kg.yaml"))
    lc = st["result"].life_cycle
    assert lc["evaluated"], lc.get("reason")
    assert any("depreciação retirada" in n for n in lc["adapter_notes"])
    assert lc["cost_per_flight_hour_USD"]["lo"] > 12.0
    co2 = lc["environment"]["per_flight_hour_kgCO2e"]["fuel_combustion_CO2"]["lo"]
    assert co2 > 0 and lc["environment"]["status"] == "completo"
