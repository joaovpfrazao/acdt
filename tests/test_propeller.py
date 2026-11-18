"""Fixed-pitch propeller (BEMT map, rpm-matched operating point) and its use by sizing/performance."""
import math

import pytest

pytest.importorskip("neuralfoil")

from acdt.domains.aircraft.propeller import FixedPitchPropeller, SectionPolar, bemt, make_propeller  # noqa: E402

C172 = {"rpm_rated": 2700, "diameter_m": 1.930, "pitch_m": 1.524, "static_rpm": 2350, "blades": 2}


@pytest.fixture(scope="module")
def c172():
    return make_propeller(C172, 134.2e3, "piston_prop")


def test_bemt_map_physical(c172):
    assert c172.CT[0] > 0.08 and c172.CP[0] > 0.03
    etas = [c172.eta(j) for j in c172.J]
    assert etas[0] == 0.0 and 0.75 < max(etas) < 0.92
    jmax = c172.J[etas.index(max(etas))]
    assert 0.6 < jmax < 1.1  # peak efficiency near J ≈ P/D (0.79) + slip


def test_static_rpm_calibration_and_redline(c172):
    assert abs(c172.static_rpm() - 2350) < 10
    hi = c172.operating_point(65.0, 0.0)
    assert hi["rpm"] == pytest.approx(2700.0)                      # redline cap
    assert hi["P"] < 134.2e3                                        # engine throttled back by the pilot
    mid = c172.operating_point(38.0, 0.0)
    assert 0.55 < mid["T"] * 38.0 / 134.2e3 < 0.75                 # effective eta at V_y (vs constant 0.75)


def test_part_throttle_and_thrust_for(c172):
    th, op = c172.thrust_for(55.0, 2400.0, 1200.0)
    assert 0 < th < 1 and op["T"] == pytest.approx(1200.0, rel=1e-3)
    assert 0.6 < op["eta"] < 0.92


def test_auto_design_absorbs_rated_power_at_design_point():
    p = make_propeller({"rpm_rated": 6000, "diameter_m": 0.6, "pitch_m": "auto", "chord_075_over_D": "auto"},
                       4000.0, "piston_prop", V_design=35.0, h_design=1000.0)
    op = p.operating_point(35.0, 1000.0)
    assert op["rpm"] == pytest.approx(6000.0, rel=0.02)
    assert 0.3 < p.pitch / p.D < 1.5 and 0.02 < p.c075_D < 0.3


def test_n_props_totals():
    pol = SectionPolar.from_airfoil("clarky", 1e6)
    a = FixedPitchPropeller(1.8, 1.4, 2, 0.08, 2700, 100e3).build_map(pol)
    b = FixedPitchPropeller(1.8, 1.4, 2, 0.08, 2700, 200e3, n_props=2).build_map(pol)
    oa, ob = a.operating_point(40.0, 0.0), b.operating_point(40.0, 0.0)
    assert ob["T"] == pytest.approx(2 * oa["T"], rel=1e-6) and ob["rpm"] == pytest.approx(oa["rpm"])
    ct, cp = bemt(0.0, 1.8, 1.4, 2, 0.08, pol)
    assert math.isfinite(ct) and math.isfinite(cp)


def test_dict_roundtrip(c172):
    q = FixedPitchPropeller.from_dict(c172.to_dict())
    assert q.operating_point(40.0, 500.0)["T"] == pytest.approx(c172.operating_point(40.0, 500.0)["T"])
