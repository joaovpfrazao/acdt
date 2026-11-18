# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Coupled jet sizing: Breguet limits, conservation, failed solves, interfaces."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from acdt import G0
from acdt.ai import jet as J
from acdt.domains.aircraft.jet.sizing import size_jet, integrate_cruise, IntegrationError
from acdt.domains.aircraft.weights import (breguet_range_fraction_jet, size_takeoff_weight,
                                           EmptyWeightModel, PropulsionData, SEGMENT_FRACTIONS)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT/"examples/jet/coupled_size.yaml"


@pytest.fixture
def spec():
    return J.load_spec(EXAMPLE)


@pytest.fixture(autouse=True)
def runs(tmp_path, monkeypatch):
    monkeypatch.setenv("ACDT_RUNS_DIR", str(tmp_path/"runs"))


def test_differential_breguet_constant_ld_analytic():
    # Raymer Eq. 3.5 in its constant-L/D limit: existing implementation is the oracle.
    mass, distance, speed, tsfc, ld = 80000, 5e6, 230, 1.8e-5, 17
    r = integrate_cruise(mass, distance, speed, tsfc, lambda m: m*G0/ld)
    expected = mass*breguet_range_fraction_jet(distance, speed, ld, tsfc)
    assert r["end_mass_kg"] == pytest.approx(expected, abs=1e-5)
    assert r["error_estimate_kg"] <= .001
    assert all(a > b for a, b in zip(r["masses_kg"], r["masses_kg"][1:]))


def test_differential_breguet_constant_drag_and_zero_range():
    r = integrate_cruise(80000, 5e6, 250, 2e-5, lambda m: 40000)
    assert r["end_mass_kg"] == pytest.approx(80000-5e6/250*2e-5*40000)
    zero = integrate_cruise(80000, 0, 250, 2e-5, lambda m: 40000)
    assert zero["steps"] == 0 and zero["end_mass_kg"] == 80000
    with pytest.raises(ValueError, match="positive mass"):
        integrate_cruise(100, 5e6, 250, 2e-5, lambda m: 40000)
    with pytest.raises(IntegrationError):
        integrate_cruise(80000, 5e6, 230, 1.8e-5, lambda m: m*G0/17,
                         steps=1, max_steps=2, mass_tolerance_kg=1e-12)


def test_zero_cruise_matches_existing_raymer_mass_equation(spec):
    spec.update(range_m=0, mass_bounds_kg=[25000, 80000])
    r = size_jet(spec)
    expected = size_takeoff_weight(spec["payload_kg"], spec["crew_kg"], [], PropulsionData(kind="jet"),
                                   EmptyWeightModel(aircraft_class="jet_transport"))
    assert r["converged"] and expected.converged
    assert r["mtow_kg"] == pytest.approx(expected.W0, abs=.04)
    fraction = 1
    for val in SEGMENT_FRACTIONS.values(): fraction *= val
    assert r["weights"]["fuel_fraction"] == pytest.approx(1.06*(1-fraction))


def test_coupled_closure_conserves_mass_and_records_real_polar(spec):
    before = copy.deepcopy(spec)
    r = size_jet(spec)
    assert spec == before
    assert r["converged"] and r["feasible"], r["issues"]
    assert r["solver"]["status"] == "converged"
    assert r["solver"]["evaluations"] == r["solver"]["iterations"]+2
    w, c = r["weights"], r["cruise"]
    closure = r["mtow_kg"]-w["empty_mass_kg"]-w["payload_kg"]-w["crew_kg"]-w["fuel_mass_kg"]
    assert closure == pytest.approx(r["solver"]["residual_kg"])
    assert abs(closure) <= r["solver"]["history"][-1]["tolerance_kg"]
    assert w["reserve_fuel_kg"] == pytest.approx(.06*w["trip_burn_kg"])
    assert w["landing_mass_kg"] == pytest.approx(w["empty_mass_kg"]+15800+w["reserve_fuel_kg"]+closure)
    assert c["trajectory"][0]["CL"] > c["trajectory"][-1]["CL"]
    assert c["trajectory"][0]["CD_wave"] >= c["trajectory"][-1]["CD_wave"]
    assert c["burn_kg"] == pytest.approx(c["start_mass_kg"]-c["end_mass_kg"])
    assert c["max_drag_N"] < c["thrust_available_N"]
    assert json.loads(json.dumps(r, allow_nan=False)) == r
    assert any(a["source"].startswith("PRESSUPOSTO") for a in r["assumptions"])


def test_range_wave_tsfc_and_geometry_are_coupled(spec):
    base = size_jet(spec)
    longer = size_jet({**spec, "range_m": 6e6})
    thicker = size_jet({**spec, "wave": {**spec["wave"], "thickness_ratio": .14}})
    thirstier = size_jet({**spec, "engine": {"tsfc_multiplier": 1.1}})
    higher_ar = size_jet({**spec, "aspect_ratio": 12})
    for r in (longer, thicker, thirstier, higher_ar): assert r["converged"], r["issues"]
    for r in (longer, thicker, thirstier):
        assert r["mtow_kg"] > base["mtow_kg"]
        assert r["weights"]["fuel_mass_kg"] > base["weights"]["fuel_mass_kg"]
    assert higher_ar["mtow_kg"] < base["mtow_kg"]


def test_converged_does_not_mean_feasible_or_auto_resize(spec):
    base = size_jet(spec)
    weak = size_jet({**spec, "thrust_sl_N": 1000})
    assert weak["converged"] and not weak["feasible"]
    assert weak["mtow_kg"] == base["mtow_kg"]  # no invented engine mass/throttle law
    assert weak["issues"] == ["cruise_thrust"]
    limited = size_jet({**spec, "mtow_limit_kg": 60000})
    assert limited["converged"] and not limited["feasible"]
    assert limited["issues"] == ["mtow_limit"]


def test_unbracketed_domain_and_iteration_failures_are_explicit(spec):
    unbracketed = size_jet({**spec, "mass_bounds_kg": [40000, 50000]})
    domain = size_jet({**spec, "mass_bounds_kg": [40000, 200000]})
    exhausted = size_jet({**spec, "solver": {"max_iterations": 1}})
    numerical = size_jet({**spec, "solver": {"cruise_steps": 1, "max_cruise_steps": 2,
                                           "mass_atol_kg": 1e-8, "mass_rtol": 1e-12}})
    for r, status in ((unbracketed, "not_bracketed"), (domain, "outside_model_domain"),
                       (exhausted, "max_iterations"), (numerical, "integration_not_converged")):
        assert r["solver"]["status"] == status
        assert not r["converged"] and not r["feasible"]
        assert r["mtow_kg"] is r["weights"] is r["cruise"] is None
        json.dumps(r, allow_nan=False)
    assert domain["solver"]["failed_evaluation"]["mtow_kg"] == 200000
    assert unbracketed["solver"]["history"][0]["residual_kg"] < 0
    assert exhausted["solver"]["residual_kg"] is not None


def test_endpoint_root_with_unusable_other_endpoint(spec):
    # Algebraically construct payload from the zero-range Raymer mass balance at m0=40000.
    from acdt.domains.aircraft.weights import statistical_fraction
    mass = 40000
    product = 1
    for val in SEGMENT_FRACTIONS.values(): product *= val
    payload = mass*(1-statistical_fraction("jet_transport", mass)-1.06*(1-product))-spec["crew_kg"]
    r = size_jet({**spec, "range_m": 0, "payload_kg": payload, "mass_bounds_kg": [mass, 200000]})
    assert r["converged"] and r["mtow_kg"] == mass
    assert r["solver"]["evaluations"] == 1


@pytest.mark.parametrize("update", [
    {"aircraft_class": "ga_single_engine"}, {"mission_ld": 17}, {"mtow_kg": 77000},
    {"payload_kg": -1}, {"range_m": float("nan")}, {"n_engines": 2.0},
    {"mass_bounds_kg": [100000, 40000]}, {"mass_bounds_kg": [40000]},
    {"mass_bounds_kg": [40000, float("inf")]}, {"configuration_id": ""},
    {"wave": {"cl": .5}}, {"engine": {"installation_factor": 0}},
    {"solver": {"max_iterations": True}}, {"solver": {"cruise_steps": 64, "max_cruise_steps": 64}},
])
def test_invalid_specs_never_fall_back(spec, update):
    with pytest.raises(ValueError): size_jet({**spec, **update})


def test_registry_json_and_assumption_provenance(spec):
    from acdt.ai import registry
    r = J.jet_size(spec)
    record = registry.load(r["run_id"]).record
    assert record["status"] == "done" and record["git"]["commit"]
    assert record["inputs"]["spec"] == spec
    assert record["assumptions"] == r["assumptions"]
    assert json.loads(Path(r["files"]["result"]).read_text()) == r
    assert {a["path"]: a["source"] for a in record["assumptions"]}["cd0"] == "user"
    unbracketed = J.jet_size({**spec, "mass_bounds_kg": [40000, 50000]})
    assert registry.load(unbracketed["run_id"]).record["status"] == "not_converged"
    with pytest.raises(ValueError): J.jet_size({**spec, "aircraft_class": "ga_single_engine"})
    assert any(registry.load(item["run_id"]).record["status"] == "error" for item in registry.list_runs())
    assert "run_id" not in J.jet_size(spec, record=False)


def test_cli_size_and_failure_codes(spec, tmp_path):
    env = {**os.environ, "PYTHONPATH": str(ROOT/"src")}
    path, output = tmp_path/"spec.json", tmp_path/"out.json"
    command = [sys.executable, "-m", "acdt.cli", "jet", "size", "--input", str(path), "-o", str(output)]
    for case, code in ((spec, 0), ({**spec, "mass_bounds_kg": [40000, 50000]}, 1),
                        ({**spec, "mission_ld": 17}, 2)):
        path.write_text(json.dumps(case))
        run = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
        assert run.returncode == code, run.stderr+run.stdout
        if code != 2:
            assert json.loads(run.stdout) == json.loads(output.read_text())


def test_mcp_jet_size_and_catalogue(spec):
    pytest.importorskip("mcp")
    import anyio
    from mcp import Client
    from acdt.ai.mcp_server import build_server
    from acdt.ai.catalogue import methods
    cat = methods()
    assert any("jet_size" in stage["tools"] for stage in cat["workflow"])
    module = next(m for m in cat["modules"] if m["module"] == "acdt.domains.aircraft.jet.sizing")
    assert any("2018" in r for r in module["references"])
    async def go():
        async with Client(build_server()) as client:
            r = await client.call_tool("jet_size", {"spec": spec})
            assert not r.is_error
            data = getattr(r, "structured_content", None) or getattr(r, "structuredContent", None)
            assert data["converged"] and data["run_id"]
    anyio.run(go)
