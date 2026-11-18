# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Deterministic force balances, failure reporting and optional jet sizing checks."""
import copy
import json
import math
import os
from pathlib import Path
import subprocess
import sys

import pytest
from acdt import G0
from acdt.ai import jet as J
from acdt.domains.aircraft.jet.performance import (ground_run, steady_climb, screen_performance,
                                                   validate_performance, REFERENCES)
from acdt.domains.aircraft.jet.sizing import size_jet

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT/"examples/jet/performance_l0.yaml"


@pytest.fixture
def spec(): return J.load_spec(EX)


@pytest.fixture(autouse=True)
def runs(tmp_path, monkeypatch): monkeypatch.setenv("ACDT_RUNS_DIR", str(tmp_path/"runs"))


def test_ground_constant_force_analytic():
    # Newton: s=m V²/(2 T), t=m V/T, no aerodynamic or rolling resistance.
    r = ground_run(1000, 30, 1.225, 10, 0, 0, 0, 0, lambda v: 4000)
    assert r["status"] == "assessed"
    assert r["distance_m"] == pytest.approx(112.5)
    assert r["time_s"] == pytest.approx(7.5)
    assert r["min_sampled_net_force_N"] == 4000


def test_ground_raymer_constant_thrust_closed_form():
    # Raymer 17.102–104 / public takeoff transcription: integrate F=a-bV².
    mass, speed, rho, area, cd, mu, thrust = 1000, 40, 1.225, 10, .025, .02, 4000
    a, b = thrust-mu*mass*G0, .5*rho*area*cd
    distance = -mass/(2*b)*math.log(1-b*speed**2/a)
    elapsed = mass/math.sqrt(a*b)*math.atanh(speed*math.sqrt(b/a))
    r = ground_run(mass, speed, rho, area, cd, 0, 0, mu, lambda v: thrust)
    assert r["distance_m"] == pytest.approx(distance, abs=.002)
    assert r["time_s"] == pytest.approx(elapsed, abs=.001)


def test_ground_failures_are_not_clipped():
    stopped = ground_run(1000, 30, 1.225, 10, 0, 0, 0, .02, lambda v: .02*1000*G0)
    premature = ground_run(1000, 60, 1.225, 10, 0, 0, 2, 0, lambda v: 4000)
    numerical = ground_run(1000, 30, 1.225, 10, 0, 0, 0, 0, lambda v: 4000/(1+.01*v**4), steps=2, max_steps=4)
    for result in (stopped, premature, numerical):
        assert result["distance_m"] is result["time_s"] is None
        assert result["status"] != "assessed"
        json.dumps(result, allow_nan=False)
    assert stopped["failed_point"]["net_force_N"] == pytest.approx(0, abs=1e-10)
    assert premature["failed_point"]["wheel_load_N"] < 0
    assert numerical["status"] == "integration_not_converged"


def test_steady_exact_equilibrium_and_negative_climb():
    mass, speed, rho, area, cd0, k, gamma = 1000, 50, 1.225, 20, .02, .04, .05
    qS = .5*rho*speed**2*area
    cl = mass*G0*math.cos(gamma)/qS
    thrust = qS*(cd0+k*cl*cl)+mass*G0*math.sin(gamma)
    r = steady_climb(mass, speed, rho, area, cd0, k, 1.5, thrust)
    assert r["gradient"] == pytest.approx(math.tan(gamma))
    assert r["ROC_m_s"] == pytest.approx(speed*math.sin(gamma))
    assert abs(r["force_residual_N"]) < 1e-8
    glide = steady_climb(mass, speed, rho, area, cd0, k, 1.5, 0)
    assert glide["gradient"] < 0 and glide["ROC_m_s"] < 0
    assert abs(glide["force_residual_N"]) < 1e-8
    stall = steady_climb(mass, 10, rho, area, cd0, k, 1.5, thrust)
    assert stall["status"] == "insufficient_lift" and stall["gradient"] is None
    invalid = steady_climb(mass, speed, rho, area, 0, 0, 1.5, 2*mass*G0)
    assert invalid["gradient"] is None


def test_optional_schema_preserves_legacy_mass_and_checks(spec):
    original = copy.deepcopy(spec)
    prior = copy.deepcopy(spec)
    prior.pop("performance")
    old, new = size_jet(prior), size_jet(spec)
    assert spec == original
    for key in ("converged", "feasible", "mtow_kg", "weights", "cruise", "solver", "checks", "issues"):
        assert old[key] == new[key]
    assert "performance" not in old and "combined_requested_checks_passed" not in old
    assert new["combined_requested_checks_passed"]
    performance = new["performance"]
    assert performance["schema_version"] == "1.0"
    assert performance["regulatory_compliance"] == "unassessed"
    assert performance["ground"]["full_takeoff_distance_m"] is None
    assert performance["ground"]["distance_m"] > 0
    assert performance["ground"]["idealized_straight_climb_distance_m"] > 0
    assert performance["climb_points"][0]["mass_kg"] == new["mtow_kg"]
    json.dumps(new, allow_nan=False)


@pytest.mark.parametrize("engines", [2, 3, 4])
@pytest.mark.parametrize("clause", list(REFERENCES))
def test_oei_engine_count_and_regulatory_reference_never_compliance(spec, engines, clause):
    spec["n_engines"] = engines
    p = copy.deepcopy(spec["performance"]["climb_points"][0])
    p["reference_clause"] = clause
    r = screen_performance(67800, spec, {"climb_points": [p]})
    point = r["climb_points"][0]
    assert point["operating_engines_oei"] == engines-1
    assert point["OEI"]["thrust_N"]/point["AEO"]["thrust_N"] == pytest.approx((engines-1)/engines)
    assert point["OEI"]["gradient"] < point["AEO"]["gradient"]
    ref = point["regulatory_reference"]
    assert ref["threshold_gradient"] == REFERENCES[clause][engines]
    assert ref["passed"] is None and ref["status"] == "unassessed"
    assert ref["margin_gradient"] == pytest.approx(point["OEI"]["gradient"]-ref["threshold_gradient"])
    assert ref["strictly_positive"] == (engines == 2 and clause == "25.121(a)")


def test_unsupported_regulatory_count_and_single_engine_oei(spec):
    spec["n_engines"] = 1
    settings = {"climb_points": [spec["performance"]["climb_points"][0]]}
    r = screen_performance(67800, spec, settings)
    point = r["climb_points"][0]
    assert point["operating_engines_oei"] == 0 and point["OEI"]["thrust_N"] == 0
    assert point["OEI"]["gradient"] < 0
    assert point["regulatory_reference"]["threshold_gradient"] is None
    assert point["regulatory_reference"]["numerical_threshold_met"] is None
    assert not r["requested_checks_passed"]
    assert r["ground"]["status"] == "unassessed"


def test_drag_rating_and_altitude_physics(spec):
    p = copy.deepcopy(spec["performance"]["climb_points"][0])
    def point(update):
        return screen_performance(67800, spec, {"climb_points": [{**p, **update}]})["climb_points"][0]
    base = point({})
    windmill = point({"delta_cd_windmilling": .02})
    gear = point({"delta_cd_gear": .02})
    derated = point({"thrust_factor": .8})
    higher = point({"altitude_m": 1000})
    assert windmill["AEO"] == base["AEO"]
    assert windmill["OEI"]["gradient"] < base["OEI"]["gradient"]
    for changed in (gear, derated, higher):
        assert changed["AEO"]["gradient"] < base["AEO"]["gradient"]
        assert changed["OEI"]["gradient"] < base["OEI"]["gradient"]


def test_negative_oei_is_failure_without_changing_legacy_feasibility(spec):
    spec["performance"]["climb_points"][0]["delta_cd_windmilling"] = .2
    r = size_jet(spec)
    assert r["converged"] and r["feasible"]  # legacy mass/cruise-only scope
    assert not r["combined_requested_checks_passed"]
    assert r["performance"]["climb_points"][0]["OEI"]["gradient"] < 0
    assert r["performance"]["issues"] and r["screening_issues"]
    assert r["performance"]["climb_points"][0]["regulatory_reference"]["passed"] is None


def test_unconverged_mass_and_insufficient_liftoff_remain_unassessed(spec):
    spec["mass_bounds_kg"] = [40000, 50000]
    fail = size_jet(spec)
    assert not fail["converged"] and not fail["combined_requested_checks_passed"]
    assert fail["performance"]["status"] == "unassessed"
    assert fail["performance"]["ground"] is None
    assert fail["performance"]["climb_points"] == []
    spec["mass_bounds_kg"] = [40000, 110000]
    spec["performance"]["ground"]["liftoff_speed_m_s"] = 50
    stall = size_jet(spec)
    assert not stall["combined_requested_checks_passed"]
    assert stall["performance"]["ground"]["idealized_straight_climb_distance_m"] is None
    assert stall["performance"]["ground"]["full_takeoff_distance_m"] is None


@pytest.mark.parametrize("key,value", [("altitude_m", -1), ("speed_m_s", 1e-300), ("speed_m_s", 200), ("mass_fraction", 1.1),
    ("cl_max", 0), ("delta_cd_flaps", -.01), ("delta_cd_gear", float("nan")),
    ("delta_cd_windmilling", -.01), ("delta_cd_oei_trim", float("inf")),
    ("oswald", 0), ("thrust_factor", True), ("min_oei_gradient", -.01), ("reference_clause", "25.999"),
    ("reference_clause", [])])
def test_invalid_climb_inputs(spec, key, value):
    p = spec["performance"]["climb_points"][0]
    p[key] = value
    with pytest.raises(ValueError): validate_performance({"climb_points": [p]})


def test_missing_explicit_inputs_empty_and_duplicate_cases(spec):
    p = spec["performance"]["climb_points"][0]
    del p["delta_cd_windmilling"]
    with pytest.raises(ValueError): size_jet(spec)
    with pytest.raises(ValueError): validate_performance({})
    with pytest.raises(ValueError): validate_performance({"climb_points": []})
    with pytest.raises(ValueError): validate_performance({"ground": {}})
    spec = J.load_spec(EX)
    points = spec["performance"]["climb_points"]
    with pytest.raises(ValueError): validate_performance({"climb_points": [points[0], points[0]]})
    ground = spec["performance"]["ground"]
    for update in ({"mu_roll": -1}, {"steps": True}, {"max_steps": 32}, {"obstacle_height_m": 0}):
        with pytest.raises(ValueError): validate_performance({"ground": {**ground, **update}})
    with pytest.raises(ValueError): J.jet_performance(J.load_spec(ROOT/"examples/jet/coupled_size.yaml"), record=False)


def test_cli_registry_and_json(spec, tmp_path):
    from acdt.ai import registry
    path, output = tmp_path/"spec.json", tmp_path/"result.json"
    command = [sys.executable, "-m", "acdt.cli", "jet", "performance", "--input", str(path), "-o", str(output)]
    for failed in (False, True):
        if failed: spec["performance"]["climb_points"][0]["delta_cd_windmilling"] = .2
        path.write_text(json.dumps(spec))
        r = subprocess.run(command, cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT/"src")}, capture_output=True, text=True)
        assert r.returncode == (1 if failed else 0), r.stderr
        data = json.loads(output.read_text())
        assert data == json.loads(r.stdout)
        rec = registry.load(data["run_id"]).record
        assert rec["tool"] == "jet_performance"
        assert rec["status"] == ("infeasible" if failed else "done")
        assert rec["outputs"]["combined_requested_checks_passed"] is (not failed)
        assert rec["assumptions"][-1]["source"] == "PRESSUPOSTO L0"
    assert "run_id" not in J.jet_performance(spec, record=False)


def test_real_mcp_performance_and_catalogue(spec):
    pytest.importorskip("mcp")
    import anyio
    from mcp import Client
    from acdt.ai.mcp_server import build_server
    from acdt.ai.catalogue import methods
    assert any("jet_performance" in s["tools"] for s in methods()["workflow"])
    module = next(m for m in methods()["modules"] if m["module"] == "acdt.domains.aircraft.jet.performance")
    assert any("2026" in x for x in module["references"])
    async def go():
        async with Client(build_server()) as client:
            result = await client.call_tool("jet_performance", {"spec": spec})
            assert not result.is_error
            data = getattr(result, "structured_content", None) or getattr(result, "structuredContent", None)
            assert data["combined_requested_checks_passed"]
            assert data["performance"]["regulatory_compliance"] == "unassessed"
            assert data["performance"]["climb_points"][0]["regulatory_reference"]["passed"] is None
    anyio.run(go)


def test_zero_gradient_strict_reference_is_not_positive(spec, monkeypatch):
    import acdt.domains.aircraft.jet.performance as P
    p = copy.deepcopy(spec["performance"]["climb_points"][0])
    p.update(reference_clause="25.121(a)", delta_cd_windmilling=0, delta_cd_oei_trim=0)
    mass = 67800
    from acdt.core.atmosphere import isa
    qS = .5*isa(p["altitude_m"]).rho*p["speed_m_s"]**2*spec["wing_area_m2"]
    k = 1/(math.pi*spec["aspect_ratio"]*p["oswald"])
    drag = qS*(spec["cd0"]+p["delta_cd_flaps"]+p["delta_cd_gear"]+k*(mass*G0/qS)**2)
    monkeypatch.setattr(P, "engine_point", lambda *a, **kw: {"thrust_installed_N": drag, "status": "assessed"})
    r = P.screen_performance(mass, spec, {"climb_points": [p]})
    ref = r["climb_points"][0]["regulatory_reference"]
    assert r["climb_points"][0]["OEI"]["gradient"] == pytest.approx(0, abs=1e-14)
    assert ref["numerical_threshold_met"] is False
    assert ref["passed"] is None


def test_regulatory_table_against_published_thresholds():
    # 14 CFR 25.121(a)-(d), 2/3/4 engines, Cornell source opened 2026-11-07.
    expected = {"25.121(a)": (0, .003, .005), "25.121(b)": (.024, .027, .030),
                "25.121(c)": (.012, .015, .017), "25.121(d)": (.021, .024, .027)}
    for clause, values in expected.items():
        assert tuple(REFERENCES[clause][n] for n in (2, 3, 4)) == values


def test_ground_only_engineering_limit_and_no_empty_obstacle_claim(spec):
    ground = spec["performance"]["ground"]
    del ground["obstacle_height_m"]
    ground["max_ground_run_m"] = 100
    r = screen_performance(67800, spec, {"ground": ground})
    assert not r["requested_checks_passed"]
    assert "ground_run_only_limit" in r["issues"]
    assert r["climb_points"] == []
    assert r["ground"]["full_takeoff_distance_m"] is None
    assert r["ground"]["idealized_straight_climb_distance_m"] is None
    assert r["regulatory_compliance"] == "unassessed"
