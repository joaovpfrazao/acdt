"""P4 Eastlake/CER operational cost + morph evaluate opt-in hook."""
from __future__ import annotations

from pathlib import Path

import pytest

from acdt.domains.aircraft.manufacturing.costing import operational_cost_from_dict
from acdt.domains.aircraft.morphology.evaluate import attach_operating_cost, evaluate_architectures
from acdt.domains.aircraft.morphology.prune import prune_set_based

ROOT = Path(__file__).resolve().parents[1]


def test_attach_operating_cost_ok_and_unassessed():
    row: dict = {"id": "A", "notes": [], "metrics": {}}
    attach_operating_cost(row, {
        "flight_hours_per_year": 200,
        "unit_price": 100000.0,
        "fuel_kg_per_h": 30.0,
        "fuel_price_per_kg": 2.0,
        "maintenance_mmh_per_fh": 0.5,
        "maintenance_rate_per_h": 100.0,
        "depreciation_years": 20.0,
        "profile": "full",
        "sources": {"fuel_price_per_kg": "EXAMPLE"},
    })
    assert row["operating_cost"]["status"] == "ok"
    assert row["metrics"]["cost_per_fh"] == pytest.approx(60 + 50 + 100000 / 4000)

    row2: dict = {"id": "B", "notes": [], "metrics": {}}
    attach_operating_cost(row2, {
        "flight_hours_per_year": 200,
        "unit_price": 100000.0,
        "fuel_kg_per_h": 30.0,
        # no fuel_price → unassessed
        "profile": "elements",
    })
    assert row2["operating_cost"]["status"] == "unassessed"
    assert "cost_per_fh" not in row2["metrics"]
    assert row2["operating_cost"]["per_flight_hour"] is None


def test_attach_operating_cost_unit_price_from_size():
    row: dict = {"id": "C", "notes": [], "metrics": {}}
    attach_operating_cost(row, {
        "flight_hours_per_year": 200,
        "unit_price_from": "size",
        "fuel_kg_per_h": 10.0,
        "fuel_price_per_kg": 2.5,
        "sources": {"fuel_price_per_kg": "EXAMPLE"},
    }, sized_unit_cost=80000.0)
    assert row["operating_cost"]["status"] == "ok"
    assert row["metrics"]["cost_per_fh"] == pytest.approx(25.0)
    assert row["operating_cost"]["unit_price"] == 80000.0

    row_miss: dict = {"id": "D", "notes": [], "metrics": {}}
    attach_operating_cost(row_miss, {
        "flight_hours_per_year": 200,
        "unit_price_from": "size",
        "fuel_kg_per_h": 10.0,
        "fuel_price_per_kg": 2.5,
    }, sized_unit_cost=None)
    assert row_miss["operating_cost"]["status"] == "unassessed"
    assert "cost_per_fh" not in row_miss["metrics"]


def test_morph_evaluate_attaches_ops_cost_when_inputs_present():
    arches = [
        {"id": "A0001", "choices": {"propulsion_kind": "electric", "landing_gear": "none",
                                    "launch_recovery": "catapult", "energy": "battery"}},
    ]
    # Eastlake unit CER supplies acquisition; energy rate is complete → attach cost_per_fh
    op = {
        "flight_hours_per_year": 300,
        "energy_kWh_per_h": 5.0,
        "electricity_price_per_kWh": 0.20,
        "profile": "elements",
        "eastlake": {"W_airframe_kg": 12.0, "V_H_kt": 45.0, "N": 50},
        "sources": {
            "electricity_price_per_kWh": "EXAMPLE grid 0.20 USD/kWh illustrative",
            "eastlake": "Gudmundsson 2014 Ch. 2 CER (illustrative; UAV is outside the GA database)",
        },
    }
    out = evaluate_architectures(
        arches, ROOT / "examples/uav_endurance_payload.yaml",
        sim_path=None, level="L0", run_mission=False, limit=1,
        operating_cost=op,
    )
    row = out["rows"][0]
    assert row.get("evaluable")
    assert row["operating_cost"]["status"] == "ok"
    assert row["metrics"]["cost_per_fh"] == pytest.approx(1.0)  # 5 kWh/h * 0.20
    assert row["operating_cost"]["acquisition_cer"]["unit_cost"] > 0


def test_morph_evaluate_without_ops_cost_unchanged():
    arches = [
        {"id": "A0001", "choices": {"propulsion_kind": "electric", "landing_gear": "none",
                                    "launch_recovery": "catapult", "energy": "battery"}},
    ]
    out = evaluate_architectures(
        arches, ROOT / "examples/uav_endurance_payload.yaml",
        sim_path=None, level="L0", run_mission=False, limit=1,
    )
    assert "operating_cost" not in out["rows"][0]
    assert "cost_per_fh" not in out["rows"][0]["metrics"]


def test_prune_uses_cost_per_fh_when_present():
    rows = [
        {"id": "cheap", "evaluable": True, "metrics": {"W0_kg": 20.0, "cost_per_fh": 40.0}},
        {"id": "pricey", "evaluable": True, "metrics": {"W0_kg": 20.0, "cost_per_fh": 80.0}},
    ]
    out = prune_set_based(rows, band=0.05, keep=2)
    assert "cost_per_fh" in out["objectives"]
    # with same W0, cheaper should dominate pricey under min cost_per_fh
    assert "cheap" in out["alive"]


def test_eastlake_cer_example_numbers_match_cli_shape():
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
        "sources": {"fuel_price_per_kg": "EXAMPLE"},
    })
    assert o["status"] == "ok"
    assert 150 < o["per_flight_hour"] < 200
