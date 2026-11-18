# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Schema 1.2: L0 hybrid rule-based dispatch + common mission phase coverage."""
import copy
import pathlib

import pytest
import yaml

from acdt.domains.aircraft import hybrid_dispatch as HD
from acdt.domains.aircraft.mission_phases import coverage, required_check, CANONICAL
from acdt.domains.aircraft.mission_fleet import evaluate_study, validate_study

EX = pathlib.Path(__file__).resolve().parents[1] / "examples" / "fleet"


@pytest.fixture(scope="module")
def spec():
    return yaml.safe_load(open(EX / "hybrid_dispatch.yaml"))


def H(spec, i=0):
    return copy.deepcopy(spec["candidates"][i]["recipe"]["aircraft"]["hybrid"])


def test_phase_powers_cited_forms(spec):
    h = H(spec); W = 25 * HD.G0
    plan = {p[0]: p for p in HD.phase_plan(h, 10, 30, 0.25)}
    assert plan["station"][1] == pytest.approx(W * 30 / (12 * 0.75))
    assert plan["climb"][1] == pytest.approx(W * (25 / 12 + 2) / 0.75) and plan["climb"][2] == pytest.approx(300 / 2 / 3600)
    assert plan["descent"][1] == pytest.approx(max(0, W * (25 / 12 - 2) / 0.75))
    assert plan["transit_out"][2] == pytest.approx(10000 / 30 / 3600)


def test_series_energy_balance_and_thermostat(spec):
    h = H(spec); r = HD.evaluate(h, 10, 30, 0.25)
    # fuel = bsfc * engine energy; generator always at set-point when on
    on_h = r["fuel_kg"] / (0.6 * 1.2 / 0.9)
    assert 0 < on_h < r["flight_h"]
    # battery: net SOC change equals discharge/eta_d - charge*eta_c
    b = h["battery"]
    dsoc = (r["battery_discharged_Wh"] / b["discharge_efficiency"] - r["battery_charged_in_flight_Wh"] * b["charge_efficiency"]) / b["capacity_Wh"]
    assert b["soc_initial"] - r["soc_final"] == pytest.approx(dsoc)
    assert r["soc_min_seen"] >= h["dispatch"]["soc_on"] - 0.01 and r["feasible"]
    assert r["ground_recharge_Wh"] == pytest.approx((0.9 - r["soc_final"]) * 300)


def test_load_following_and_parallel(spec):
    h = H(spec); h["dispatch"] = {"rule": "load_following", "source": "t"}
    r = HD.evaluate(h, 10, 30, 0.25)
    assert r["battery_charged_in_flight_Wh"] == 0 and r["peaks"]["engine_W"] <= 1500
    p = H(spec, 1); r = HD.evaluate(p, 10, 30, 0.25)
    taxi = [x for x in r["phases"] if x["phase"] in ("taxi_out", "taxi_in")]
    assert all(x["fuel_kg"] == 0 for x in taxi) and r["peaks"]["engine_W"] == 1000
    assert r["degree_of_hybridisation_power"] == pytest.approx(0.5)


def test_limits_fail_not_pass(spec):
    h = H(spec); h["battery"]["c_rate_max"] = 5.0
    r = HD.evaluate(h, 10, 30, 0.25)
    assert {c["name"]: c["passed"] for c in r["checks"]}["battery_c_rate"] is False and not r["feasible"]
    h = H(spec); h["fuel"]["capacity_kg"] = 0.1
    assert {c["name"]: c["passed"] for c in HD.evaluate(h, 10, 30, 0.25)["checks"]}["fuel_capacity"] is False


def test_validation(spec):
    h = H(spec); h["dispatch"]["rule"] = "power_split"
    with pytest.raises(ValueError, match="dispatch rule"): HD.validate_hybrid(h)
    h = H(spec); h["dispatch"]["soc_on"] = 0.9
    with pytest.raises(ValueError, match="soc_on"): HD.validate_hybrid(h)
    h = H(spec, 1); h["generator"] = {"efficiency": 0.9, "source": "x"}
    with pytest.raises(ValueError, match="generator"): HD.validate_hybrid(h)
    h = H(spec); h["engine"].pop("source")
    with pytest.raises(ValueError, match="source"): HD.validate_hybrid(h)
    d = copy.deepcopy(spec); d["mission"]["required_phases"] = ["warp"]
    with pytest.raises(ValueError, match="required_phases"): validate_study(d)


def test_study_hybrid_assessed_and_phases(spec):
    r = evaluate_study(copy.deepcopy(spec))
    n = {x["candidate_id"]: x["n1"] for x in r["rows"]}
    s = n["híbrido-série"]
    assert s["status"] == "assessed_in_scope" and s["metrics"]["fleet_required"] == 5
    assert s["metrics"]["mission_fuel_kg"] == pytest.approx(0.317, abs=1e-3)
    acts = {a["id"]: a for a in s["operations_by_dwell"]["requested"]["ground_activities"]}
    assert acts["refuel"]["duration_h"] == pytest.approx(s["metrics"]["mission_fuel_kg"] / 30)
    assert acts["charge"]["duration_h"] == pytest.approx(s["metrics"]["mission_energy_Wh"] / (0.9 * 500))
    assert all(v["state"] == "flown" for k, v in s["mission_phases"]["phases"].items() if k != "reserve")
    assert n["híbrido-paralelo"]["status"] == "assessed_in_scope"
    el = n["elétrico"]
    assert el["status"] == "unassessed" and "required_phases_represented" in el["issues"]
    chk = [c for c in el["checks"] if c["name"] == "required_phases_represented"][0]
    assert set(chk["unrepresented"]) == {"taxi_out", "descent", "landing", "taxi_in"}


def test_hybrid_without_data_stays_unassessed(spec):
    d = copy.deepcopy(spec)
    d["candidates"].append({"id": "híbrido-aberto", "architecture": "x", "source": "s",
                            "n0": {"endurance_h": [1, 2], "turnaround_h": [0.1, 0.2], "source": "s"},
                            "recipe": {"schema_version": "1.0", "model": "hybrid", "aircraft": {}}})
    n = evaluate_study(d)["rows"][-1]["n1"]
    assert n["status"] == "unassessed" and "unsupported_N1_adapter_or_hybrid_dispatch" in n["issues"]
    d11 = yaml.safe_load(open(EX / "iter_prop_native_reserve.yaml"))
    n = evaluate_study(d11)["rows"][2]["n1"]
    assert n["status"] == "unassessed"


def test_coverage_contract():
    for model, kind in (("prop", "electric"), ("prop", "prop"), ("jet", None), ("vtol", None)):
        c = coverage(model, kind)
        assert set(c["phases"]) == set(CANONICAL)
        assert c["phases"]["station"]["state"] == "flown"
    assert coverage("vtol")["phases"]["taxi_out"]["state"] == "not_applicable"
    assert required_check(coverage("jet"), ["descent", "taxi_in"])["passed"] is True  # lumped in Raymer landing fraction
    assert required_check(coverage("vtol"), ["descent"])["passed"] is None
