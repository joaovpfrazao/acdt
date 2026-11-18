import math

import pytest

from acdt.domains.aircraft.cost import EastlakeInputs, eastlake_unit_cost, propeller_cost
from acdt.domains.aircraft.manufacturing import refdata as R
from acdt.domains.aircraft.manufacturing.costing import (DapcaInputs, OperatingInputs, dapca4, learning_cum_avg,
                                                          learning_total, learning_unit, operating_cost,
                                                          operational_cost_from_dict)


def test_cpi_factor_bls():
    assert R.cpi_factor(2025) == pytest.approx(321.943 / 229.594)
    with pytest.raises(KeyError):
        R.cpi_factor(1990)


def test_learning_curves():
    # 85 %: doubling the quantity multiplies unit (Crawford) / cum. average (Wright) by 0.85
    assert learning_unit(100, 2) == pytest.approx(85)
    assert learning_unit(100, 8) == pytest.approx(100 * 0.85**3)
    assert learning_cum_avg(100, 4, theory="wright") == pytest.approx(100 * 0.85**2)
    assert learning_total(100, 2) == pytest.approx(185)
    assert learning_cum_avg(100, 1) == 100


def test_dapca_si_consistency():
    # Raymer gives the same CERs in SI (kg, km/h): H_E 5.18, H_T 7.22, H_M 10.5, C_D 67.4, C_F 1947, C_M 31.2
    We, Vkt, Q = 5000.0, 400.0, 100
    d = dapca4(DapcaInputs(We_kg=We, V_kt=Vkt, Q=Q, FTA=4))
    V = Vkt * 1.852
    si = {"engineering": 5.18 * We**0.777 * V**0.894 * Q**0.163, "tooling": 7.22 * We**0.777 * V**0.696 * Q**0.263,
          "manufacturing": 10.5 * We**0.82 * V**0.484 * Q**0.641}
    for k, v in si.items():
        assert d["hours"][k] == pytest.approx(v, rel=0.02)
    assert d["costs"]["dev_support"] == pytest.approx(67.4 * We**0.630 * V**1.3, rel=0.02)
    assert d["costs"]["flight_test"] == pytest.approx(1947 * We**0.325 * V**0.822 * 4**1.21, rel=0.02)
    assert d["costs"]["materials"] == pytest.approx(31.2 * We**0.921 * V**0.621 * Q**0.799, rel=0.02)


def test_eastlake_labour_factor_and_composite():
    b = eastlake_unit_cost(EastlakeInputs(W_airframe_kg=500, V_H_kt=130, N=500))
    assert b.engineering == pytest.approx(2.0969 * b.hours["engineering"] * 92)
    c = eastlake_unit_cost(EastlakeInputs(W_airframe_kg=500, V_H_kt=130, N=500, f_comp=1.0))
    assert c.hours["manufacturing"] == pytest.approx(1.25 * b.hours["manufacturing"])
    assert c.hours["engineering"] == pytest.approx(2.0 * b.hours["engineering"])
    assert propeller_cost("constant_speed", D_ft=6.5, P_shp=200) == pytest.approx(
        209.66 * 6.5**2 * (200 / 6.5) ** 0.12)


def test_operating_cost_reports_missing():
    o = operating_cost(OperatingInputs(flight_hours_per_year=200, unit_price=1e5, fuel_kg_per_h=30))
    assert "fuel_price_per_kg" in o["missing_inputs"]
    o = operating_cost(OperatingInputs(flight_hours_per_year=200, unit_price=1e5, fuel_kg_per_h=30,
                                       fuel_price_per_kg=2.0, maintenance_mmh_per_fh=0.5, maintenance_rate_per_h=100,
                                       engine_overhaul_cost=40000, engine_tbo_h=2000, depreciation_years=20))
    assert o["per_flight_hour"] == pytest.approx(60 + 50 + 20 + 1e5 / 4000)
    assert not o["missing_inputs"]


def test_operating_cost_unassessed_not_silent_zero():
    o = operating_cost(OperatingInputs(flight_hours_per_year=200, unit_price=1e5, fuel_kg_per_h=30))
    assert o["status"] == "unassessed"
    assert o["per_flight_hour"] is None
    assert o["assessed_sum_per_fh"] == 0.0
    assert "fuel_price_per_kg" in o["unassessed_terms"]
    # wage without mmh
    o2 = operating_cost(OperatingInputs(flight_hours_per_year=200, unit_price=1e5,
                                        maintenance_rate_per_h=100))
    assert o2["status"] == "unassessed"
    assert "maintenance_mmh_per_fh / maintenance_rate_per_h" in o2["unassessed_terms"]
    assert o2["per_flight_hour"] is None


def test_operating_cost_eastlake_cer_chain_complete():
    """Complete Eastlake unit CER → DOC (Raymer Ch. 18) with dated example rates."""
    o = operational_cost_from_dict({
        "flight_hours_per_year": 200,
        "fuel_kg_per_h": 30.0,
        "fuel_price_per_kg": 2.0,
        "maintenance_mmh_per_fh": 0.5,
        "maintenance_rate_per_h": 100.0,
        "engine_overhaul_cost": 40000.0,
        "engine_tbo_h": 2000.0,
        "depreciation_years": 20.0,
        "profile": "full",
        "eastlake": {"W_airframe_kg": 500.0, "V_H_kt": 130.0, "N": 500},
        "sources": {
            "fuel_price_per_kg": "EXAMPLE Jet-A 2 USD/kg illustrative (not a vendor quote)",
            "maintenance_rate_per_h": "EXAMPLE shop rate 100 USD/h illustrative",
        },
    })
    assert o["status"] == "ok"
    assert o["acquisition_cer"]["unit_cost"] > 1e5
    uc = o["unit_price"]
    expected = 60.0 + 50.0 + 20.0 + uc / (20.0 * 200.0)
    assert o["per_flight_hour"] == pytest.approx(expected)
    assert o["items_per_fh"]["fuel"] == pytest.approx(60.0)


def test_operating_cost_partial_fuel_ok_maint_unassessed_full():
    o = operational_cost_from_dict({
        "flight_hours_per_year": 200,
        "unit_price": 1e5,
        "fuel_kg_per_h": 30.0,
        "fuel_price_per_kg": 2.0,
        "profile": "full",
        "sources": {"fuel_price_per_kg": "EXAMPLE"},
    })
    assert o["status"] == "partial"
    assert o["per_flight_hour"] is None
    assert o["assessed_sum_per_fh"] == pytest.approx(60.0)
    assert "depreciation_years" in o["unassessed_terms"]
    assert "maintenance_mmh_per_fh / maintenance_rate_per_h" in o["unassessed_terms"]
