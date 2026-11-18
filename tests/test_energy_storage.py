# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Analytic inventory balances and existing-producer adapter regressions, no new flight model."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from acdt.core.energy_storage import check_storage, aggregate
from acdt.domains.aircraft.storage import aircraft_storage, demand_from_result
from acdt.domains.aircraft.jet.sizing import size_jet
from acdt.domains.aircraft.vtol.size import size_vtol
from acdt.ai.jet import load_spec
from acdt.ai.storage import storage_check

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def runs(tmp_path, monkeypatch): monkeypatch.setenv("ACDT_RUNS_DIR", str(tmp_path/"runs"))


@pytest.fixture
def fuel(): return load_spec(ROOT/"examples/storage/fuel_prop.yaml")["storage"]


@pytest.fixture
def battery():
    return {"battery": {"nominal_Wh": 1250, "dod": .8, "pack_Wh_kg": 200,
                        "pack_Wh_L": 250, "available_volume_m3": .005}}


def test_fuel_balance_reserve_unusable_and_fill_once(fuel):
    demand = {"fuel": {"trip_kg": 70, "reserve_kg": 8}}
    r = check_storage(demand, fuel)
    assert r["storage_feasible"]
    f = r["carriers"]["fuel"]
    assert f["capacity_from_volume_kg"] == pytest.approx(720*.12*.95)
    assert f["usable_loaded_kg"] == 78
    assert f["required_loaded_mass_kg"] == 80  # reserve 8 + unusable 2, each once
    assert f["loaded_liquid_volume_m3"] == pytest.approx(80/720)
    assert f["installed_envelope_volume_m3"] == .13  # NOT just liquid or internal volume
    assert r["inventory_total_mass_kg"] is None  # dry tank unknown, no invented 0
    fuel["fuel"]["loaded_mass_kg"] = 79
    assert check_storage(demand, fuel)["storage_feasible"] is False


def test_pack_nominal_dod_mass_and_nist_litre_conversion(battery):
    # SP 811 App B.8: 1 L = .001 m³; pack volume = 1250/250 L = .005 m³.
    r = check_storage({"battery": {"trip_Wh": 800, "reserve_Wh": 200}}, battery)
    assert r["storage_feasible"]
    b = r["carriers"]["battery"]
    assert b["usable_Wh"] == 1000 and b["required_nominal_Wh"] == 1250
    assert b["inventory_mass_kg"] == 6.25
    assert b["installed_envelope_volume_m3"] == pytest.approx(.005)
    assert r["inventory_total_mass_kg"] == 6.25
    assert "battery:peak_power" in r["unassessed"]  # energy pass is not a power claim
    battery["battery"]["dod"] = .79
    assert check_storage({"battery": {"trip_Wh": 800, "reserve_Wh": 200}}, battery)["storage_feasible"] is False


@pytest.mark.parametrize("dod,trip,reserve,expected", [(0,1,0,False),(0,0,0,True),(1,1250,0,True),(1,1250,1,False)])
def test_dod_and_zero_reserve_boundaries(battery, dod, trip, reserve, expected):
    battery["battery"]["dod"] = dod
    r = check_storage({"battery": {"trip_Wh": trip, "reserve_Wh": reserve}}, battery)
    assert r["storage_feasible"] is expected
    json.dumps(r, allow_nan=False)


@pytest.mark.parametrize("missing", ["nominal_Wh", "dod", "available_volume_m3", "pack_Wh_L"])
def test_missing_capacity_or_volume_is_unassessed(battery, missing):
    del battery["battery"][missing]
    r = check_storage({"battery": {"trip_Wh": 1, "reserve_Wh": 0}}, battery)
    assert r["storage_feasible"] is None and r["unassessed"]


@pytest.mark.parametrize("missing", ["loaded_mass_kg", "unusable_mass_kg", "density_kg_m3", "fill_fraction"])
def test_missing_fuel_data_is_unassessed(fuel, missing):
    del fuel["fuel"][missing]
    assert check_storage({"fuel": {"trip_kg": 1, "reserve_kg": 0}}, fuel)["storage_feasible"] is None


def test_missing_demand_or_reserve_is_not_an_empty_pass(battery):
    assert check_storage({}, battery)["storage_feasible"] is None
    assert check_storage({"battery": {"trip_Wh": 10}}, battery)["storage_feasible"] is None
    with pytest.raises(ValueError): check_storage({}, {})
    assert aggregate([]) is None and aggregate([True,None]) is None
    assert aggregate([False,None]) is False


def test_independent_capacity_and_packaging_failure(fuel):
    d = {"fuel": {"trip_kg": 70, "reserve_kg": 8}}
    fuel["fuel"]["available_volume_m3"] = .1
    r = check_storage(d, fuel)
    assert r["capacity_feasible"] and r["packaging_feasible"] is False
    fuel["fuel"]["capacity_kg"] = 100  # inconsistent with supplied internal volume/density/fill
    assert "fuel:capacity_vs_internal_volume" in check_storage(d, fuel)["issues"]
    fuel["fuel"]["tank_external_volume_m3"] = .01
    assert "fuel:external_vs_internal_volume" in check_storage(d, fuel)["issues"]


def test_shared_volume_does_not_count_the_same_space_twice(fuel, battery):
    d = {"fuel": {"trip_kg": 70, "reserve_kg": 8}, "battery": {"trip_Wh": 800, "reserve_Wh": 200}}
    s = {**fuel, **battery, "shared_available_volume_m3": .134}
    del s["fuel"]["available_volume_m3"]; del s["battery"]["available_volume_m3"]
    r = check_storage(d, s)
    assert r["storage_feasible"] is False
    assert "storage:shared_allocated_volume" in r["issues"]
    s["shared_available_volume_m3"] = .135
    r = check_storage(d, s)
    assert r["storage_feasible"] and "unimplemented" in r["hybrid_dispatch"]


@pytest.mark.parametrize("key,val", [("dod",float("nan")),("nominal_Wh",float("inf")),("pack_Wh_L",0),
    ("pack_Wh_kg",-1),("dod",1.1),("nominal_Wh",True),("cell_Wh_L",500),("trip_J",1000),
    ("pack_mass_kg",3),("pack_volume_m3",.01)])
def test_invalid_or_ambiguous_storage(battery, key, val):
    battery["battery"][key] = val
    with pytest.raises(ValueError): check_storage({"battery": {"trip_Wh": 1,"reserve_Wh":0}}, battery)


def test_numerical_overflow_and_incompatible_units(battery):
    battery["battery"]["pack_Wh_L"] = 1e-310
    with pytest.raises(ValueError): check_storage({"battery": {"trip_Wh":1,"reserve_Wh":0}}, battery)
    with pytest.raises(ValueError): demand_from_result("mission", {"aborted":None,"unit":"J","total_used":3600}, 0)
    with pytest.raises(ValueError): check_storage({"battery": {"trip_J":3600,"reserve_Wh":0}}, {})


def test_peak_power_and_existing_mass_allocation(battery):
    d = {"battery": {"trip_Wh":800,"reserve_Wh":200,"peak_W":5000}}
    assert check_storage(d,battery)["storage_feasible"] is None
    battery["battery"]["max_continuous_power_W"] = 4000
    assert check_storage(d,battery)["storage_feasible"] is False
    battery["battery"]["max_continuous_power_W"] = 5000
    assert check_storage(d,battery,{"battery":6.25})["storage_feasible"]
    r = check_storage(d,battery,{"battery":6})
    assert "battery:existing_mass_allocation" in r["issues"]
    assert r["inventory_total_mass_kg"] == 6.25  # NOT 6 + 6.25


@pytest.mark.parametrize("label", ["prop", "electric"])
def test_real_pointmass_adapter_and_efficiency_once(label):
    from acdt.domains.aircraft.flightsim.pointmass import simulate_pointmass_mission
    result = simulate_pointmass_mission(ROOT/f"examples/storage/{label}_mission.yaml")
    assert result["aborted"] is None
    demand, meta = demand_from_result("mission", result, .15)
    carrier, unit = ("fuel","kg") if label == "prop" else ("battery","Wh")
    assert demand[carrier]["trip_"+unit] == result["total_used_"+unit]
    assert demand[carrier]["reserve_"+unit] == pytest.approx(.15*result["total_used_"+unit])
    assert meta["demand_assessed"] and "adapter only" in meta["coupling"]
    summary = {"aborted":None,"unit":unit,"total_used":result["total_used_"+unit],"fidelity":"pointmass"}
    assert demand_from_result("mission", {"summary":summary}, .15)[0] == demand
    with pytest.raises(ValueError): demand_from_result("mission",result)


def test_jet_closure_storage_adaptor_preserves_mass_semantics():
    spec = load_spec(ROOT/"examples/jet/coupled_size.yaml")
    before = size_jet(spec)
    spec["storage"] = load_spec(ROOT/"examples/storage/jet.yaml")["storage"]
    result = size_jet(spec)
    for key in ("mtow_kg","weights","cruise","checks","issues","feasible"): assert before[key] == result[key]
    assert "storage" not in before and result["storage"]["storage_feasible"]
    d = result["storage"]["demand"]["fuel"]
    assert d["trip_kg"]+d["reserve_kg"] == pytest.approx(before["weights"]["fuel_mass_kg"])
    with pytest.raises(ValueError): demand_from_result("jet_size",before,0)
    spec["storage"]["fuel"]["available_volume_m3"] = 1
    fail = size_jet(spec)
    assert fail["feasible"] and fail["storage"]["storage_feasible"] is False
    spec["storage"]["fuel"]["available_volume_m3"] = 32
    spec["mass_bounds_kg"] = [40000,50000]
    fail = size_jet(spec)
    assert fail["storage"]["storage_feasible"] is None
    assert not fail["storage"]["producer"]["demand_assessed"]


def test_vtol_adapter_uses_terminal_energy_not_nominal_twice():
    spec = {"mass_kg":25}
    before = size_vtol(spec)
    spec["storage"] = load_spec(ROOT/"examples/storage/vtol.yaml")["storage"]
    result = size_vtol(spec)
    for key in ("energy_Wh","energy_nominal_Wh","battery_mass_kg","checks","feasible"): assert before[key] == result[key]
    d = result["storage"]["demand"]["battery"]
    assert d["trip_Wh"] == result["energy_Wh"]
    assert d["trip_Wh"]+d["reserve_Wh"] == pytest.approx(result["energy_nominal_Wh"]*.8)
    assert result["storage"]["storage_feasible"]
    assert result["storage"]["carriers"]["battery"]["inventory_mass_kg"] == pytest.approx(1000/180)
    with pytest.raises(ValueError): demand_from_result("vtol_size",result,0)


@pytest.mark.parametrize("result", [{}, {"converged":False}, {"status":"failed"}, {"weights":None}])
def test_unavailable_jet_demand_not_pass(fuel,result):
    r = aircraft_storage(fuel,"jet_size",result)
    assert r["storage_feasible"] is None


@pytest.mark.parametrize("update", [{"aborted":"budget"},{"unusable":1},{"failures":{"log":["degradation"]}}])
def test_incomplete_or_degraded_mission_not_demand(battery, update):
    producer = {"aborted":None,"unit":"Wh","total_used_Wh":100,**update}
    assert aircraft_storage(battery,"mission",producer,.1)["storage_feasible"] is None


def test_mutation_provenance_cli_and_json(battery,tmp_path):
    from acdt.ai import registry
    spec = {"storage":battery,"demand":{"battery":{"trip_Wh":800,"reserve_Wh":200}}}
    original = copy.deepcopy(spec)
    r = storage_check(spec)
    assert spec == original
    record = registry.load(r["run_id"]).record
    assert record["tool"] == "storage_check" and record["status"] == "done"
    assert record["assumptions"] == r["assumptions"]
    assert json.loads(Path(r["files"]["result"]).read_text()) == r
    path,out = tmp_path/"input.json", tmp_path/"result.json"
    for state, code in (("pass",0),("fail",1),("missing",3),("invalid",2)):
        s=copy.deepcopy(spec)
        if state=="fail": s["storage"]["battery"]["dod"] = .5
        if state=="missing": del s["storage"]["battery"]["dod"]
        if state=="invalid": s["storage"]["battery"]["dod"] = -1
        path.write_text(json.dumps(s))
        proc=subprocess.run([sys.executable,"-m","acdt.cli","storage","check","--input",str(path),"-o",str(out)],
                            cwd=ROOT,env={**os.environ,"PYTHONPATH":str(ROOT/"src")},capture_output=True,text=True)
        assert proc.returncode == code, proc.stderr
        if code!=2: assert json.loads(out.read_text()) == json.loads(proc.stdout)


def test_real_mcp_and_catalogue(battery):
    pytest.importorskip("mcp")
    import anyio
    from mcp import Client
    from acdt.ai.mcp_server import build_server
    from acdt.ai.catalogue import methods
    assert any("storage_check" in s["tools"] for s in methods()["workflow"])
    async def go():
        async with Client(build_server()) as client:
            result=await client.call_tool("storage_check",{"spec":{"storage":battery,"demand":{"battery":{"trip_Wh":800,"reserve_Wh":200}}}})
            assert not result.is_error
            d=getattr(result,"structured_content",None) or getattr(result,"structuredContent",None)
            assert d["storage_feasible"]
    anyio.run(go)


def test_existing_systems_pack_keeps_component_mass_and_wh_units():
    from acdt.core.systems.battery import size_battery
    cell = {"v_nom":3.6,"v_max":4.2,"capacity_ah":3,"mass":.05,"i_cont":10}
    pack = size_battery(cell,1000*3600,20,10,k_pack=1.2)
    r = check_storage({"battery":{"trip_Wh":600,"reserve_Wh":100}},
                      {"battery":{"nominal_Wh":pack.energy_nom_J/3600,"dod":.8,
                                  "pack_mass_kg":pack.mass,"pack_volume_m3":.006,"available_volume_m3":.007}})
    assert r["storage_feasible"]
    assert pack.energy_nom_J/3600 == pytest.approx(1080)  # SP 811 Wh -> J
    assert r["inventory_total_mass_kg"] == pack.mass == 6  # no second packaging overhead


def test_declared_mass_capacity_still_has_to_fit_liquid_volume():
    s = {"fuel":{"capacity_kg":80,"loaded_mass_kg":80,"unusable_mass_kg":0,
                 "density_kg_m3":800,"tank_external_volume_m3":.05,"available_volume_m3":.2}}
    r = check_storage({"fuel":{"trip_kg":70,"reserve_kg":10}},s)
    assert r["capacity_feasible"]
    assert "fuel:liquid_within_envelope" in r["issues"]
    assert r["storage_feasible"] is False


def test_explicit_nulls_are_missing_data_not_passes(battery, fuel):
    battery["battery"]["dod"] = None
    assert check_storage({"battery":{"trip_Wh":100,"reserve_Wh":0}},battery)["storage_feasible"] is None
    fuel["fuel"]["unusable_mass_kg"] = None
    assert check_storage({"fuel":{"trip_kg":1,"reserve_kg":0}},fuel)["storage_feasible"] is None
    r = aircraft_storage(battery,"mission",{"unit":"Wh","aborted":None,"total_used_Wh":None},0)
    assert r["storage_feasible"] is None
