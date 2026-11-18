# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""L0 field takeoff: ASD/TOD/BFL screening, unknown≠pass, backward compatible."""
import copy
from pathlib import Path
import pytest
import yaml
from acdt.domains.aircraft.jet.field_takeoff import ground_between, screen_field, validate_field, SCREEN_M
from acdt.domains.aircraft.jet.performance import screen_performance, validate_performance, ground_run
from acdt.domains.aircraft.jet.sizing import size_jet
from acdt.ai import jet as J

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples" / "jet" / "performance_field.yaml"


@pytest.fixture
def spec():
    return yaml.safe_load(EX.read_text())


def test_ground_between_matches_ground_run_from_rest():
    thrust = lambda v: 2e5
    a = ground_run(70000, 80, 1.225, 122.6, 0.05, 0.04, 0.6, 0.02, thrust, steps=16, max_steps=512)
    b = ground_between(70000, 0.0, 80, 1.225, 122.6, 0.05, 0.04, 0.6, 0.02, thrust, steps=16, max_steps=512)
    assert a["status"] == b["status"] == "assessed"
    assert b["distance_m"] == pytest.approx(a["distance_m"], rel=1e-9)


def test_brake_stop_positive_distance():
    thrust = lambda v: 1e5
    r = ground_between(70000, 60.0, 0.0, 1.225, 122.6, 0.08, 0.04, 0.3, 0.4, thrust,
                       steps=16, max_steps=512, braking=True, reverse_factor=0.0)
    assert r["status"] == "assessed" and r["distance_m"] > 0 and r["time_s"] > 0


def test_field_validation_requires_ground(spec):
    p = spec["performance"]
    with pytest.raises(ValueError, match="field requires"):
        validate_performance({"field": p["field"]})
    bad = copy.deepcopy(p); bad["field"]["v2_m_s"] = 10
    with pytest.raises(ValueError, match="v2_m_s"): validate_performance(bad)


def test_example_field_screen_numbers(spec):
    r = J.jet_performance(copy.deepcopy(spec), record=False)
    assert r["converged"]
    f = r["performance"]["field"]
    assert f["status"] == "screened"
    assert f["tod_aeo"]["status"] == "assessed"
    assert f["tod_aeo"]["tod_115pct_m"] == pytest.approx(1.15 * f["tod_aeo"]["tod_m"])
    assert f["balanced_field"]["v1_m_s"] is not None
    assert f["balanced_field"]["field_length_m"] > f["tod_aeo"]["tod_m"]
    assert f["regulatory_compliance"] == "unassessed"
    assert all(c["passed"] is None for c in f["regulatory_references"].values() if isinstance(c, dict) and "passed" in c)
    assert r["performance"]["ground"]["full_takeoff_distance_m"] == pytest.approx(f["tod_aeo"]["tod_m"])
    # publish actual numbers
    print("TOD_AEO", f["tod_aeo"]["tod_m"], "BFL", f["balanced_field"]["field_length_m"],
          "V1", f["balanced_field"]["v1_m_s"], "ASD", f["balanced_field"]["asd"]["asd_m"],
          "TOD_OEI", f["balanced_field"]["tod_oei"]["tod_m"])


def test_vmc_missing_unassessed_floor(spec):
    d = copy.deepcopy(spec)
    d["performance"]["field"].pop("vmc_m_s")
    r = J.jet_performance(d, record=False)
    f = r["performance"]["field"]
    assert "VMC_not_supplied" in f["unassessed"]
    assert any(c["name"] == "field_vmc_floor" and c["passed"] is None for c in f["checks"])
    assert f["requested_checks_passed"] is False


def test_legacy_performance_unchanged_without_field():
    base = yaml.safe_load((ROOT / "examples/jet/performance_l0.yaml").read_text())
    r = J.jet_performance(copy.deepcopy(base), record=False)
    assert "field" not in r["performance"]
    assert r["performance"]["ground"]["full_takeoff_distance_m"] is None


def test_airborne_rotation_transition_classical():
    from acdt.domains.aircraft.jet.field_takeoff import airborne_rotation_transition
    from acdt import G0
    r = airborne_rotation_transition(10.668, 80.0, 0.2, vr_m_s=78.0, rotation_time_s=2.0,
                                     transition_load_factor=1.2)
    assert r["status"] == "assessed"
    assert r["rotation_distance_m"] == pytest.approx(0.5 * (78 + 80) * 2.0)
    R = 80.0 ** 2 / (G0 * 0.2)
    assert r["transition_radius_m"] == pytest.approx(R)
    assert r["airborne_distance_m"] == pytest.approx(
        r["rotation_distance_m"] + r["transition_distance_m"] + r["climb_distance_m"])


def test_airborne_missing_inputs_unassessed_not_zero():
    from acdt.domains.aircraft.jet.field_takeoff import airborne_rotation_transition
    r = airborne_rotation_transition(10.668, 80.0, 0.2, vr_m_s=78.0, rotation_time_s=None,
                                     transition_load_factor=1.2)
    assert r["status"] == "unassessed"
    assert r["airborne_distance_m"] is None
    assert "rotation_time_s" in r["missing"]


def test_rotation_transition_lengthens_tod_vs_legacy(spec):
    import copy
    from acdt.ai import jet as J
    base = J.jet_performance(copy.deepcopy(spec), record=False)["performance"]["field"]
    s = copy.deepcopy(spec)
    s["performance"]["field"].update(include_rotation_transition=True, rotation_time_s=2.0,
                                     transition_load_factor=1.2)
    rt = J.jet_performance(s, record=False)["performance"]["field"]
    assert rt["include_rotation_transition"] is True
    assert rt["tod_aeo"]["status"] == "assessed"
    assert rt["tod_aeo"]["tod_m"] > base["tod_aeo"]["tod_m"]
    air = rt["tod_aeo"]["airborne"]
    assert air["status"] == "assessed" and air["rotation_distance_m"] > 0
    assert "rotation_transition_segment" not in rt["unassessed"]
    assert "rotation_transition_segment" in base["unassessed"]
    # legacy path unchanged for the original example
    assert base["tod_aeo"]["note"].startswith("25.113") or "no rotation/transition" in base["tod_aeo"]["note"]


def test_rotation_opt_in_without_tR_unassessed(spec):
    import copy
    from acdt.ai import jet as J
    s = copy.deepcopy(spec)
    s["performance"]["field"]["include_rotation_transition"] = True
    s["performance"]["field"]["transition_load_factor"] = 1.2
    # rotation_time_s omitted
    f = J.jet_performance(s, record=False)["performance"]["field"]
    assert f["tod_aeo"]["status"] == "unassessed"
    assert f["tod_aeo"]["tod_m"] is None
    assert any(c["name"] == "field_rotation_transition" and c["passed"] is None for c in f["checks"])


def test_example_rotation_yaml_runs():
    from acdt.ai import jet as J
    import yaml
    from pathlib import Path
    s = yaml.safe_load((Path(__file__).resolve().parents[1] / "examples/jet/performance_field_rotation.yaml").read_text())
    f = J.jet_performance(s, record=False)["performance"]["field"]
    assert f["tod_aeo"]["airborne"]["rotation_distance_m"] == pytest.approx(158.0)
    print("RT TOD_AEO", f["tod_aeo"]["tod_m"], "legacy compare via other test")
