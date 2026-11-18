import math

import pytest

from acdt.domains.aircraft.aero.drag import DragPolar, ff_body, oswald_raymer, skin_friction
from acdt.domains.aircraft.aero.lift import HighLiftDevice, clmax_clean, high_lift_summary, lift_curve_slope
from acdt.domains.aircraft.geometry import TrapezoidalWing


def test_trapezoidal_wing():
    w = TrapezoidalWing(S=16.0, AR=8.0, taper=0.5)
    assert w.span == pytest.approx(math.sqrt(128))
    assert w.c_root * (1 + 0.5) / 2 * w.span == pytest.approx(16.0)
    # Raymer Eq. 7.5: MAC = 2/3 c_r (1+λ+λ²)/(1+λ)
    assert w.mac == pytest.approx(2 / 3 * w.c_root * (1 + 0.5 + 0.25) / 1.5)
    assert w.wetted_area() == pytest.approx(2 * 16 * (1 + 0.2 * w.tc_mean), rel=0.05)


def test_lift_slope_limits():
    a = lift_curve_slope(1e4)
    assert a == pytest.approx(0.95 * 2 * math.pi, rel=2e-2)  # 2D limit
    a6 = lift_curve_slope(6.0)
    assert 4.0 < a6 < 5.0  # Helmbold/DATCOM ~4.5 /rad for AR 6


def test_clmax_and_flaps():
    assert clmax_clean(1.6) == pytest.approx(1.44)
    hl = high_lift_summary(1.6, 0.0, HighLiftDevice("slotted", 0.6))
    assert hl.CLmax_landing > hl.CLmax_clean
    assert hl.CLmax_takeoff == pytest.approx(hl.CLmax_clean + 0.8 * (hl.CLmax_landing - hl.CLmax_clean), rel=0.2)


def test_skin_friction():
    Re = 1e7
    assert skin_friction(Re) == pytest.approx(0.455 / math.log10(Re) ** 2.58, rel=1e-9)
    assert skin_friction(1e6, laminar_fraction=1.0) == pytest.approx(1.328e-3)
    assert ff_body(6.0) == pytest.approx(1 + 60 / 216 + 6 / 400)


def test_polar_ldmax():
    e = oswald_raymer(8.0)
    assert 0.7 < e < 0.85
    p = DragPolar.from_oswald(0.025, 8.0, e)
    assert p.LD_max == pytest.approx(1 / (2 * math.sqrt(0.025 * p.K)))
    assert p.CL_LDmax == pytest.approx(math.sqrt(0.025 / p.K))
