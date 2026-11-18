# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Transport equations: imperial hand checks, declared coverage and coupled closure.

Hand-check inputs are PRESSUPOSTO, not aircraft data. Coefficients/units follow
Raymer cargo/transport Sec.15.3.2, public sources cited in jet.weights. Reference
checks verify the published equations, not predictive accuracy against OEW.
"""
import copy
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import pytest
import yaml
from acdt.domains.aircraft.jet.weights import COVERAGE, transport_weights, validate_weights
from acdt.domains.aircraft.jet.sizing import size_jet
from acdt.domains.aircraft.weights_detailed import LB, FT
from acdt.ai import jet as J

ROOT = Path(__file__).resolve().parents[1]

@pytest.fixture
def spec():
    return yaml.safe_load((ROOT/"examples/jet/coupled_components.yaml").read_text())

@pytest.fixture
def weights(spec):
    return spec["weights"]


def build(weights, mass=70000, area=122.6, ar=9.48):
    return transport_weights(mass, area, ar, weights)


def test_published_transport_equations_imperial_hand_checks(weights):
    # Independent scalar hand results, all lengths ft, areas ft², Wdg=100000 lb.
    wing, ht, vt = weights["items"][:3]
    wing["inputs"].update(control_area_m2=150*FT**2)
    ht["inputs"].update(area_m2=300*FT**2, tail_arm_m=50*FT, pitch_radius_m=15*FT,
                        fuselage_width_m=12*FT, elevator_area_m2=75*FT**2)
    vt["inputs"].update(area_m2=250*FT**2, tail_arm_m=50*FT, yaw_radius_m=50*FT)
    r = build(weights,100000*LB,1000*FT**2,9)
    expected_lb = [7074.6243138095215,928.5178997905168,944.3393737959525]
    assert [i["mass_kg"]/LB for i in r["items"][:3]] == pytest.approx(expected_lb,rel=1e-12)
    assert LB == .45359237 and FT == .3048
    assert all("raymer_cargo_transport" in i["method_source_url"] for i in r["items"][:3])
    assert all("Sec.15.3.2" in i["source"] for i in r["items"][:3])


def test_mass_exponents_and_explicit_load_factor(weights):
    a,b=build(weights),build(weights,140000)
    assert [b["items"][i]["mass_kg"]/a["items"][i]["mass_kg"] for i in range(3)] == pytest.approx([2**.557,2**.639,2**.556])
    weights["ultimate_n"] *= 2
    c=build(weights)
    assert [c["items"][i]["mass_kg"]/a["items"][i]["mass_kg"] for i in range(3)] == pytest.approx([2**.557,2**.1,2**.536])
    assert c["coverage"]["known_mass_supplied_kg"] == a["coverage"]["known_mass_supplied_kg"]


def test_control_geometry_and_all_moving_factor(weights):
    a=build(weights)
    weights["items"][1]["inputs"]["all_moving"]=True
    weights["items"][2]["inputs"]["tail_height_ratio"]=1
    b=build(weights,ar=4*9.48)
    assert b["items"][0]["mass_kg"] == pytest.approx(2*a["items"][0]["mass_kg"])
    assert b["items"][1]["mass_kg"] == pytest.approx(1.143*a["items"][1]["mass_kg"])
    assert b["items"][2]["mass_kg"] == pytest.approx(2**.225*a["items"][2]["mass_kg"])


def test_supplied_lump_counted_once_and_unknown_not_zero(weights):
    weights["items"]=[dict(name="declared complete empty inventory",covers=list(COVERAGE),method="supplied",mass_kg=40000,source="PRESSUPOSTO total inventory, NOT OEW-fit")]
    r=build(weights)
    assert r["empty_mass_kg"] == 40000 and r["known_subtotal_kg"] == 40000
    assert r["group_totals_kg"]["mixed"] == 40000
    assert r["dry_airframe_mass_kg"] is None  # no invented allocation
    weights["items"][0]["mass_kg"]=None
    r=build(weights)
    assert r["empty_mass_kg"] is None and r["dry_airframe_mass_kg"] is None
    assert r["coverage"]["missing"] == sorted(COVERAGE)
    assert r["group_totals_kg"]["mixed"] is None
    assert r["group_totals_kg"]["equipment"] is None
    del weights["items"][0]["mass_kg"]
    assert build(weights)["empty_mass_kg"] is None


def test_missing_group_na_and_open_accounting_groups(weights):
    item=weights["items"].pop()
    r=build(weights)
    assert r["empty_mass_kg"] is None and r["coverage"]["missing"] == [item["covers"][0]]
    weights["items"].append(dict(name="no further empty items",covers=item["covers"],method="not_applicable",reason="PRESSUPOSTO explicit reviewed inventory boundary",source="user"))
    assert build(weights)["empty_mass_kg"] is not None
    weights["additional_required_groups"]=["special_equipment"]
    assert build(weights)["coverage"]["missing"] == ["special_equipment"]
    weights["items"].append(dict(name="special",covers=["special_equipment"],method="supplied",mass_kg=123,source="PRESSUPOSTO"))
    assert build(weights)["group_totals_kg"]["user_defined"] == 123


@pytest.mark.parametrize("alter",[
    lambda w:w["items"].append(copy.deepcopy(w["items"][0])),
    lambda w:w["items"][1].update(covers=["wing_structure"]),
    lambda w:w["items"][0].update(mass_kg=5),
    lambda w:w["items"][0].update(method="raymer_ga_wing"),
    lambda w:w["items"][3].update(covers=["crew"]),
    lambda w:w["items"][3].update(source=""),
    lambda w:w["items"][3].update(mass_kg=-1),
    lambda w:w["items"][3].update(mass_kg=float("nan")),
    lambda w:w["items"][3].update(mass_kg=float("inf")),
    lambda w:w["items"][3].update(mass_kg=True),
    lambda w:w["items"][0]["inputs"].update(sweep_quarter_chord_deg=90),
    lambda w:w["items"][0]["inputs"].update(root_thickness_ratio=0),
    lambda w:w["items"][0]["inputs"].update(control_area_m2=1000),
    lambda w:w["items"][1]["inputs"].update(elevator_area_m2=1000),
    lambda w:w["items"][1]["inputs"].update(all_moving=1),
    lambda w:w["items"][2]["inputs"].update(tail_height_ratio=2),
    lambda w:w.update(ultimate_n=.5),
    lambda w:w.pop("ultimate_n"),
    lambda w:w.pop("conventional_metal_transport"),
    lambda w:w.update(mode="statistical"),
    lambda w:w["items"][0]["inputs"].pop("taper_ratio"),
    lambda w:w.update(additional_required_groups=["wing_structure"]),
    lambda w:w.update(additional_required_groups=["fuel"]),
    lambda w:w.update(additional_required_groups=["Payload"]),
])
def test_invalid_inputs(weights,alter):
    alter(weights)
    with pytest.raises(ValueError): build(weights)


def test_domain_guards_and_overrides(weights):
    weights["conventional_metal_transport"]=False
    r=build(weights)
    assert r["empty_mass_kg"] is None
    assert all(i["status"] == "out_of_domain" for i in r["items"][:3])
    for item in weights["items"][:3]:
        item.pop("inputs")
        item.update(method="supplied",mass_kg=1000,source="PRESSUPOSTO externally supplied total, no transport regression")
    assert build(weights)["empty_mass_kg"] is not None
    with pytest.raises(ValueError): build(weights,mass=0)
    with pytest.raises(ValueError): build(weights,area=float("inf"))


def test_coupled_closure_mass_balance_and_recalculation(spec):
    r=size_jet(spec)
    assert r["converged"] and r["feasible"]
    w=r["weights"]
    assert abs(r["mtow_kg"]-w["empty_mass_kg"]-spec["payload_kg"]-spec["crew_kg"]-w["fuel_mass_kg"]) <= r["solver"]["history"][-1]["tolerance_kg"]
    expected=build(spec["weights"],r["mtow_kg"])
    assert w["empty_mass_kg"] == expected["empty_mass_kg"]
    assert r["weight_build_up"] == w["build_up"] == expected
    assert r["weight_build_up"]["operating_empty_mass_kg"] is None
    for h in r["solver"]["history"]:
        assert h["empty_mass_kg"] == pytest.approx(build(spec["weights"],h["mtow_kg"])["empty_mass_kg"])
    assert len(set(h["empty_mass_kg"] for h in r["solver"]["history"])) > 3
    assert json.loads(json.dumps(r,allow_nan=False)) == r
    spec["weights"]["ultimate_n"] *= 1.1
    assert size_jet(spec)["mtow_kg"] > r["mtow_kg"]


def test_no_fallback_on_incomplete_or_out_of_domain(spec):
    spec["weights"]["items"].pop(3)
    r=size_jet(spec)
    assert not r["converged"] and not r["feasible"]
    assert r["mtow_kg"] is None and r["weights"] is None
    assert r["solver"]["status"] == "incomplete_weight_build_up"
    assert r["weight_build_up"]["coverage"]["missing"] == ["fuselage_structure"]
    assert r["solver"]["successful_evaluations"] == 0
    spec["weights"]["conventional_metal_transport"]=False
    assert "wing_structure" in size_jet(spec)["weight_build_up"]["coverage"]["missing"]


def test_nonconvergence_and_impossible_mass(spec):
    exhausted=size_jet({**spec,"solver":{"max_iterations":1}})
    assert not exhausted["converged"] and exhausted["solver"]["status"] == "max_iterations"
    spec["weights"]["items"][3]["mass_kg"]=900000
    r=size_jet(spec)
    assert not r["converged"] and r["solver"]["status"] == "not_bracketed"
    assert r["weights"] is None


def test_statistical_baseline_unchanged_and_exact_total_supplied(spec):
    baseline=copy.deepcopy(spec); baseline.pop("weights")
    a=size_jet(baseline); b=size_jet({**baseline,"weights":{"mode":"statistical"}})
    assert a["mtow_kg"] == b["mtow_kg"] and a["weights"] == b["weights"]
    assert a["solver"] == b["solver"]
    spec["weights"]["items"]=[dict(name="explicit whole empty",covers=list(COVERAGE),method="supplied",mass_kg=40000,source="PRESSUPOSTO hypothetical mass; crew, payload, mission fuel outside")]
    r=size_jet(spec)
    assert r["converged"] and r["weights"]["empty_mass_kg"] == 40000
    assert r["weight_build_up"]["coverage"]["known_mass_modeled_kg"] == 0


def test_no_storage_or_engine_count_double_accounting(spec):
    a=size_jet(spec)
    spec["storage"]={"fuel":{"capacity_kg":40000,"tank_dry_mass_kg":700}}
    spec["n_engines"]=4 # given engines_dry is TOTAL, not multiplied again
    b=size_jet(spec)
    assert a["mtow_kg"] == b["mtow_kg"] and a["weights"] == b["weights"]
    assert b["storage"] is not None
    assert b["weight_build_up"]["items"][6]["mass_kg"] == 5000
    assert "storage" not in a


def test_ai_registry_cli_mcp_and_catalogue(spec,tmp_path):
    from acdt.ai import registry
    inp=dict(mass_kg=70000,wing_area_m2=122.6,aspect_ratio=9.48,weights=spec["weights"])
    r=J.jet_weights(inp)
    assert json.loads(Path(r["files"]["result"]).read_text()) == r
    rec=registry.load(r["run_id"]).record
    assert rec["status"] == "done" and rec["assumptions"] == r["assumptions"]
    inp["weights"]["items"].pop(3)
    assert registry.load(J.jet_weights(inp)["run_id"]).record["status"] == "incomplete"
    file,out=tmp_path/"in.json",tmp_path/"out.json"
    command=[sys.executable,"-m","acdt.cli","jet","weights","--input",str(file),"-o",str(out)]
    for case,code in [(inp,1),({**inp,"weights":{"mode":"statistical"}},0),({**inp,"mass_kg":-1},2)]:
        file.write_text(json.dumps(case))
        p=subprocess.run(command,env={**os.environ,"PYTHONPATH":str(ROOT/"src")},capture_output=True,text=True)
        assert p.returncode == code,p.stderr+p.stdout
        if code!=2: assert json.loads(p.stdout) == json.loads(out.read_text())
    from acdt.ai.catalogue import methods
    cat=methods()
    assert any("jet_weights" in s["tools"] for s in cat["workflow"])
    assert any(m["module"] == "acdt.domains.aircraft.jet.weights" for m in cat["modules"])
    pytest.importorskip("mcp")
    import anyio
    from mcp import Client
    from acdt.ai.mcp_server import build_server
    async def go():
        async with Client(build_server()) as client:
            r=await client.call_tool("jet_weights",{"spec":inp,"record":False})
            assert not r.is_error
            data=getattr(r,"structured_content",None) or getattr(r,"structuredContent",None)
            assert data["empty_mass_kg"] is None and data["coverage"]["missing"] == ["fuselage_structure"]
    anyio.run(go)


def test_zero_inventory_and_extreme_arithmetic_rejected(spec):
    w=spec["weights"]
    w["items"]=[dict(name="empty",covers=list(COVERAGE),method="supplied",mass_kg=0,source="PRESSUPOSTO impossible inventory")]
    assert "nonpositive_empty_inventory" in build(w)["issues"]
    r=size_jet(spec)
    assert not r["converged"] and r["solver"]["status"] == "outside_model_domain"
    w["items"][0]["mass_kg"]=900000
    assert "empty_not_below_design_mass" in build(w)["issues"]
    other=yaml.safe_load((ROOT/"examples/jet/component_weights.yaml").read_text())["weights"]
    other["items"][1]["inputs"]["tail_arm_m"]=1e-300
    with pytest.raises(ValueError): build(other)


@pytest.mark.parametrize("complete",[True,False])
def test_components_feed_optional_performance_and_storage(spec,complete):
    settings=J.load_spec(ROOT/"examples/jet/performance_l0.yaml")["performance"]
    spec["performance"]=settings
    spec["storage"]={"fuel":{"capacity_kg":40000,"tank_dry_mass_kg":700}}
    if not complete: spec["weights"]["items"].pop(3)
    r=J.jet_performance(spec,record=False)
    assert any("unusable fuel" in s for s in r["limitations"])
    if complete:
        assert r["converged"] and r["performance"]["mass_kg"] == r["mtow_kg"]
        for p,cfg in zip(r["performance"]["climb_points"],settings["climb_points"]):
            assert p["mass_kg"] == pytest.approx(r["mtow_kg"]*cfg["mass_fraction"])
            assert p["regulatory_reference"]["passed"] is None
    else:
        assert not r["converged"] and r["performance"]["status"] == "unassessed"
        assert not r["combined_requested_checks_passed"]


def test_statistical_standalone_invalid_fraction_and_registry_error(tmp_path):
    from acdt.ai import registry
    inp=dict(mass_kg=.01,wing_area_m2=100,aspect_ratio=9,weights={"mode":"statistical"})
    assert "invalid_statistical_empty_fraction" in J.jet_weights(inp,record=False)["issues"]
    inp["mass_kg"]=-1
    with pytest.raises(ValueError): J.jet_weights(inp)
    assert any(registry.load(x["run_id"]).record["status"] == "error" for x in registry.list_runs())
