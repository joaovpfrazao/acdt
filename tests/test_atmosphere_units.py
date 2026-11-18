import math

import pytest

from acdt.core.atmosphere import altitude_from_density, isa
from acdt.core.units import UnitError, from_si, to_si


def test_isa_sea_level():
    s = isa(0)
    assert s.T == pytest.approx(288.15)
    assert s.p == pytest.approx(101325, rel=1e-6)
    assert s.rho == pytest.approx(1.225, rel=1e-3)
    assert s.a == pytest.approx(340.29, rel=1e-3)
    assert s.mu == pytest.approx(1.789e-5, rel=1e-2)


def test_isa_11km_and_stratosphere():  # ISO 2533 table values
    assert isa(11000).T == pytest.approx(216.65, abs=0.01)
    assert isa(11000).rho == pytest.approx(0.3639, rel=2e-3)
    assert isa(15000).p == pytest.approx(12045, rel=2e-3)  # geopotential altitude


def test_density_inverse():
    for h in (0, 1500, 8000, 14000):
        assert altitude_from_density(isa(h).rho) == pytest.approx(h, abs=1.0)


def test_units():
    assert to_si(100, "kt", "speed") == pytest.approx(51.4444, rel=1e-4)
    assert to_si(1000, "ft/min", "speed") == pytest.approx(5.08, rel=1e-4)
    assert to_si(2, "h", "time") == 7200
    assert from_si(to_si(5000, "ft", "length"), "ft", "length") == pytest.approx(5000)
    assert to_si(18, "deg/s", "angular_rate") == pytest.approx(math.radians(18))
    with pytest.raises(UnitError):
        to_si(1, "furlong", "length")
    with pytest.raises(UnitError):
        to_si(1, "EUR", "currency")  # no implicit FX conversion
