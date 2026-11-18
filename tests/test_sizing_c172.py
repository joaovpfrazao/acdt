"""Sanity check against the Cessna 172S (Cessna Information Manual 172S: MTOW 2550 lb = 1157 kg,
standard empty weight 1663 lb = 754 kg, 180 hp = 134 kW, S = 16.2 m², b = 11.0 m, W/S = 71.4 kg/m²).
Conceptual methods are expected within ~±25 %; the component weight build-up within ±15 %."""
import pytest

from acdt import G0
from acdt.domains.aircraft.mission import MissionSpec
from acdt.domains.aircraft.sizing import run


@pytest.fixture(scope="module")
def c172(request):
    from pathlib import Path
    return run(MissionSpec.from_yaml(Path(__file__).parents[1] / "examples" / "cessna172_check.yaml"))


@pytest.mark.slow
def test_converged_and_feasible(c172):
    assert c172.sizing.converged and c172.converged and c172.feasible


def test_weight(c172):
    assert c172.sizing.W0 == pytest.approx(1157, rel=0.15)
    assert c172.sizing.We == pytest.approx(754, rel=0.15)        # component build-up (Raymer Ch. 15)
    assert 0.55 < c172.sizing.empty_fraction < 0.70


def test_weight_breakdown(c172):
    bd = c172.weights
    assert bd is not None and bd.empty == pytest.approx(c172.sizing.We, rel=0.02)
    g = bd.groups
    assert set(g) >= {"structure", "propulsion", "equipment"}
    assert 0.25 < g["structure"] / bd.empty < 0.60
    keys = {i.key for i in bd.items}
    assert {"wing", "fuselage", "htail", "vtail", "main_gear", "nose_gear", "engine_installed"} <= keys
    # Phase 2: Nz = 1.5 x max(manoeuvre 3.8 [CS 23.337 normal, capped], gust [CS 23.341]) from the V-n diagram
    vn = c172.structures.vn
    assert vn.n_pos == pytest.approx(3.8)
    assert bd.Nz == pytest.approx(1.5 * max(3.8, vn.n_gust_max), rel=0.01)
    assert any(r["class"] == "ga_single_engine" for r in c172.weight_cross_check)
    assert "We" in c172.history[-1] and "We_comp" in c172.history[-1]


def test_power_and_wing(c172):
    assert c172.power_sl == pytest.approx(134e3, rel=0.25)
    assert c172.S == pytest.approx(16.2, rel=0.25)
    assert c172.design_point.ws / G0 == pytest.approx(71.4, rel=0.25)


def test_aero(c172):
    assert 0.022 < c172.polar.CD0 < 0.040
    assert 9 < c172.polar.LD_max < 14
    assert 4.0 < c172.CLalpha < 5.5


def test_structures_l1_reported_with_flex_off(c172):
    l1 = c172.structures_l1
    assert l1 is not None and l1.elastic is not None and l1.elastic.applied is False
    assert 0.75 <= l1.masses["fuselage_over_raymer"] <= 1.25
