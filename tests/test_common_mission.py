# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Common jet/VTOL mission judge: pointmass / energy timeline, opt-in fleet."""
from copy import deepcopy
from pathlib import Path
import pytest
from acdt.ai.jet import load_spec
from acdt.ai.mission_fleet import mission_fleet_study
from acdt.domains.aircraft.jet.sizing import size_jet
from acdt.domains.aircraft.vtol.size import size_vtol
from acdt.domains.aircraft.flightsim.common_mission import (
    simulate_common_mission, plant_from_jet_size, build_jet_segments)

ROOT = Path(__file__).resolve().parents[1]


def test_jet_plant_uses_engine_point_thrust():
    spec = load_spec(ROOT / "examples/jet/coupled_size.yaml")
    size = size_jet(deepcopy(spec))
    plant = plant_from_jet_size(size, spec)
    assert plant.kind == "jet" and plant._thrust_fn is not None
    T, flow = plant._thrust_fn(230.0, spec["altitude_m"], 1.0)
    assert T > 0 and flow > 0
    T0, f0 = plant._thrust_fn(230.0, spec["altitude_m"], 0.0)
    assert T0 == 0.0 and f0 == 0.0


def test_jet_airborne_common_completes_with_residual():
    spec = load_spec(ROOT / "examples/jet/coupled_size.yaml")
    size = size_jet(deepcopy(spec))
    sample = dict(distance_km=300, speed_m_s=230, on_station_h=0.5, payload_kg=15000)
    common = dict(enabled=True, source="PRESSUPOSTO",
                  phases=["transit_out", "station", "transit_back"],
                  pointmass_dt=10, altitude_m=spec["altitude_m"], speed_m_s=230)
    r = simulate_common_mission(model="jet", size_out=size, spec=spec, sample=sample, common=common)
    assert r["status"] == "assessed"
    assert r["mission_result"]["aborted"] is None
    assert r["fuel_used_kg"] > 0 and r["residual_fuel_kg"] > 0
    assert r["checks"][0]["passed"] is True
    assert r["unassessed_phases"] == []


def test_jet_taxi_requested_stays_unassessed_not_pass():
    spec = load_spec(ROOT / "examples/jet/coupled_size.yaml")
    size = size_jet(deepcopy(spec))
    sample = dict(distance_km=50, speed_m_s=230, on_station_h=0.1, payload_kg=15000)
    common = dict(enabled=True, source="PRESSUPOSTO",
                  phases=["taxi_out", "transit_out", "station", "transit_back", "taxi_in"],
                  pointmass_dt=10, altitude_m=spec["altitude_m"], speed_m_s=230)
    r = simulate_common_mission(model="jet", size_out=size, spec=spec, sample=sample, common=common)
    assert "taxi_out" in r["unassessed_phases"] or r["phase_coverage"]["phases"]["taxi_out"]["state"] == "not_modeled"
    assert r["checks"][1]["passed"] is None  # requested_phases_modeled unassessed


def test_vtol_common_energy_and_descent_unassessed():
    spec = load_spec(ROOT / "examples/vtol/quadrotor_closure.yaml")
    size = size_vtol(deepcopy(spec))
    sample = dict(distance_km=1, speed_m_s=15, on_station_h=0.05, payload_kg=2)
    common = dict(enabled=True, source="PRESSUPOSTO",
                  phases=["takeoff", "transit_out", "station", "transit_back", "landing", "descent"],
                  speed_m_s=15)
    r = simulate_common_mission(model="vtol", size_out=size, sample=sample, common=common)
    assert r["energy_Wh"] > 0
    assert "descent" in r["unassessed_phases"]
    assert r["checks"][1]["passed"] is None


def test_fleet_common_sim_opt_in_jet_and_baseline_unchanged():
    base = mission_fleet_study(ROOT / "examples/fleet/jet.yaml", record=False)
    assert base["rows"][0]["n1"]["coverage_class"] == "range_equivalent_jet_with_supplied_phases"
    assert "common_sim" not in base["rows"][0]["n1"]
    cs = mission_fleet_study(ROOT / "examples/fleet/jet_common_sim.yaml", record=False)
    n1 = cs["rows"][0]["n1"]
    assert n1["status"] == "assessed_in_scope"
    assert n1["coverage_class"] == "common_pointmass_jet"
    assert n1["common_sim"]["fuel_used_kg"] == pytest.approx(n1["metrics"]["mission_fuel_kg"])
    assert n1["common_sim"]["residual_fuel_kg"] > 0


def test_fleet_common_sim_vtol():
    vs = mission_fleet_study(ROOT / "examples/fleet/vtol_common_sim.yaml", record=False)
    n1 = vs["rows"][0]["n1"]
    assert n1["coverage_class"] == "common_energy_timeline_vtol"
    assert n1["common_sim"]["energy_Wh"] == pytest.approx(n1["metrics"]["mission_energy_Wh"])


def test_airborne_only_starts_at_cruise_altitude():
    ms, phases, _, notes, _ = build_jet_segments(
        dict(phases=["transit_out", "station"], pointmass_dt=5, altitude_m=10000, speed_m_s=200),
        dict(distance_km=10, speed_m_s=200, on_station_h=0.1), 10000, 200)
    assert ms["initial"]["altitude_m"] == 10000
    assert any("cruise altitude" in n for n in notes)
