# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""L0 onboard thermal/CG/spatial/FOV closure: identities, unknown≠pass, coupling."""
from copy import deepcopy
from pathlib import Path
import math
import pytest
from acdt.ai.jet import load_spec
from acdt.core.onboard import analyse_onboard
from acdt.core.onboard_closure import analyse_closure, _ray_aabb
from acdt.domains.aircraft.onboard import size_onboard

ROOT = Path(__file__).resolve().parents[1]


def recipe():
    r = deepcopy(load_spec(ROOT / "examples/onboard/closure_electric.yaml"))
    if isinstance(r["aircraft"], str):
        r["aircraft"] = load_spec(ROOT / "examples/onboard" / r["aircraft"])
    return r


def test_ray_aabb_hit_and_miss():
    assert _ray_aabb([0, 0, 0], [1, 0, 0], [2, -1, -1], [3, 1, 1]) == pytest.approx(2)
    assert math.isinf(_ray_aabb([0, 0, 0], [0, 1, 0], [2, -1, -1], [3, 1, 1]))


def test_thermal_declared_plus_conversion_hand_numbers():
    r = recipe()
    a = analyse_onboard(r["onboard"], "electric", 1800)
    # loads: 50*0.5 + 30*1 = 55 W average at loads; delivery 0.9 → terminal 55/0.9
    # conversion distribution heat = 55*(1/0.9 - 1) = 55/9
    # declared heat = 20+15 = 35
    c = analyse_closure(r["onboard"], r["closure"], analyse=a)
    th = c["sections"]["thermal"]
    assert th["declared_heat_W"] == pytest.approx(35)
    assert th["conversion_heat_W"] == pytest.approx(55 * (1 / 0.9 - 1))
    assert th["heat_load_W"] == pytest.approx(35 + 55 * (1 / 0.9 - 1))
    # sinks: 0.004*1004*15 + 10 = 60.24 + 10 = 70.24
    assert th["available_rejection_W"] == pytest.approx(0.004 * 1004 * 15 + 10)
    assert th["margin_W"] > 0
    assert {x["name"]: x["passed"] for x in c["checks"]}["thermal_balance"] is True


def test_thermal_missing_sink_unassessed_not_pass():
    r = recipe()
    r["closure"]["thermal"]["sinks"] = []
    a = analyse_onboard(r["onboard"], "electric", 1800)
    c = analyse_closure(r["onboard"], r["closure"], analyse=a)
    assert {x["name"]: x["passed"] for x in c["checks"]}["thermal_balance"] is None


def test_cg_shift_and_envelope():
    r = recipe()
    c = analyse_closure(r["onboard"], r["closure"], analyse=analyse_onboard(r["onboard"], "electric", 100))
    cg = c["sections"]["cg"]
    base_m = r["closure"]["cg"]["base"]["mass_kg"]
    base_x = r["closure"]["cg"]["base"]["cg_m"][0]
    M = base_m + 1 + 0.8
    x = (base_m * base_x + 1 * 0.35 + 0.8 * 0.70) / M
    assert cg["cg_m"][0] == pytest.approx(x)
    assert cg["margins"]["x_m"]["ok"] is True
    assert {x["name"]: x["passed"] for x in c["checks"]}["CG"] is True
    r["closure"]["cg"]["envelope"]["x_m"] = {"min": 0.0, "max": 0.4}
    bad = analyse_closure(r["onboard"], r["closure"], analyse=analyse_onboard(r["onboard"], "electric", 100))
    assert {x["name"]: x["passed"] for x in bad["checks"]}["CG"] is False


def test_cg_missing_placement_unassessed():
    r = recipe()
    del r["closure"]["cg"]["placements"]["avionics"]
    c = analyse_closure(r["onboard"], r["closure"], analyse=analyse_onboard(r["onboard"], "electric", 100))
    assert {x["name"]: x["passed"] for x in c["checks"]}["CG"] is None


def test_spatial_within_overlap_packing():
    r = recipe()
    c = analyse_closure(r["onboard"], r["closure"], analyse=analyse_onboard(r["onboard"], "electric", 100))
    assert {x["name"]: x["passed"] for x in c["checks"]}["spatial_fit"] is True
    # force overlap
    r["closure"]["spatial"]["placements"]["avionics"]["position_m"] = [0.35, 0.0, -0.05]
    r["closure"]["spatial"]["placements"]["avionics"]["bay"] = "nose_bay"
    bad = analyse_closure(r["onboard"], r["closure"], analyse=analyse_onboard(r["onboard"], "electric", 100))
    assert {x["name"]: x["passed"] for x in bad["checks"]}["spatial_fit"] is False


def test_fov_blockage_and_clear():
    r = recipe()
    c = analyse_closure(r["onboard"], r["closure"], analyse=analyse_onboard(r["onboard"], "electric", 100))
    assert {x["name"]: x["passed"] for x in c["checks"]}["FOV_3D"] is True
    # enlarge gear into the look-down cone
    r["closure"]["fov"]["blockers"][0]["box"] = {"lo": [0.25, -0.15, -0.50], "hi": [0.50, 0.15, -0.11]}
    bad = analyse_closure(r["onboard"], r["closure"], analyse=analyse_onboard(r["onboard"], "electric", 100))
    assert {x["name"]: x["passed"] for x in bad["checks"]}["FOV_3D"] is False


def test_fov_omitted_unassessed():
    r = recipe()
    del r["closure"]["fov"]
    c = analyse_closure(r["onboard"], r["closure"], analyse=analyse_onboard(r["onboard"], "electric", 100))
    assert {x["name"]: x["passed"] for x in c["checks"]}["FOV_3D"] is None


def test_size_onboard_wires_closure_and_reconciles_cg_base():
    r = recipe()
    out = size_onboard(r)
    assert out["status"] == "evaluated"
    assert "closure" in out
    assert out["closure"]["sections"]["thermal"]["status"] == "assessed"
    # Reconcile CG base to sized MTOW − onboard items and re-run closure expectation
    mtow = out["aircraft_result"]["mtow_kg"]
    item_m = sum(i["mass_kg"] for i in r["onboard"]["items"])
    r2 = recipe()
    r2["closure"]["cg"]["base"]["mass_kg"] = mtow - item_m
    out2 = size_onboard(r2)
    assert out2["closure"]["sections"]["cg"]["total_mass_kg"] == pytest.approx(mtow)
    assert "CG" not in out2["unassessed_checks"] or {c["name"]: c["passed"] for c in out2["onboard"]["checks"]}["CG"] is not None
    assert out2["closure"]["requested_checks_passed"] is not None


def test_native_jet_size_consumes_onboard_or_refuses_incomplete():
    """Native jet_size now bridges opt-in onboard → auxiliary; incomplete → unassessed."""
    from acdt.domains.aircraft.jet.sizing import size_jet
    from acdt.ai.jet import load_spec
    spec = deepcopy(load_spec(ROOT / "examples/jet/coupled_size.yaml"))
    spec["onboard"] = {"schema_version": "1.0"}  # missing source/items/loads
    with pytest.raises(ValueError):
        size_jet(spec)
    # no onboard → still works (backward compatible)
    size_jet(deepcopy(load_spec(ROOT / "examples/jet/coupled_size.yaml")))


def test_omitting_closure_keeps_legacy_unassessed_cg_fov():
    r = load_spec(ROOT / "examples/onboard/electric.yaml")
    if isinstance(r["aircraft"], str):
        r["aircraft"] = load_spec(ROOT / "examples/onboard" / r["aircraft"])
    out = size_onboard(r)
    assert "closure" not in out
    assert "CG" in out["unassessed_checks"] and "FOV_3D" in out["unassessed_checks"]
