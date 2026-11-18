import math

import pytest

from acdt import G0
from acdt.domains.aircraft.weights import (EmptyWeightModel, MissionLeg, PropulsionData, breguet_endurance_fraction_jet,
                          breguet_range_fraction_jet, breguet_range_fraction_prop, electric_energy_cruise,
                          electric_energy_loiter, size_takeoff_weight)

LB = 0.45359237


def test_raymer_empty_fraction_ga():
    m = EmptyWeightModel("ga_single_engine")
    assert m.fraction(1111.0) == pytest.approx(2.36 * (1111.0 / LB) ** -0.18, rel=1e-6)  # Raymer Table 3.1
    assert EmptyWeightModel(fixed_fraction=0.45).fraction(20) == 0.45


def test_breguet_forms():
    c_p = 6.76e-8  # kg/(W s) ~ 0.4 lb/(hp h)
    assert breguet_range_fraction_prop(1e6, 10, 0.8, c_p) == pytest.approx(math.exp(-1e6 * c_p * G0 / 8))
    c_t = 0.5 / 3600 / G0  # 0.5 1/h
    assert breguet_range_fraction_jet(1e6, 200, 15, c_t) == pytest.approx(math.exp(-1e6 * 0.5 / 3600 / 3000))
    assert breguet_endurance_fraction_jet(3600, 15, c_t) == pytest.approx(math.exp(-0.5 / 15))


def test_electric_energy_hepperle():
    assert electric_energy_cruise(25.0, 100e3, 15.0, 0.6) == pytest.approx(25 * G0 * 100e3 / 9)
    assert electric_energy_loiter(25.0, 3600, 20, 15.0, 0.6) == pytest.approx(25 * G0 * 20 * 3600 / 9)


def test_sizing_closure_and_infeasible():
    legs = [MissionLeg("cruise", 1.0e6, 60.0, 10.0, 2000.0)]
    prop = PropulsionData("piston_prop", eta_p=0.8)
    r = size_takeoff_weight(300.0, 0.0, legs, prop, EmptyWeightModel("ga_single_engine"))
    assert r.converged
    assert r.W0 == pytest.approx(300 / (1 - r.empty_fraction - r.fuel_fraction), rel=1e-3)
    bad = size_takeoff_weight(300.0, 0.0, legs, prop, EmptyWeightModel(fixed_fraction=0.95))
    assert not bad.converged and "infeasible" in bad.message


def test_electric_sizing_has_energy():
    legs = [MissionLeg("loiter", 7200, 22.0, 16.0, 500.0)]
    prop = PropulsionData("electric", e_spec=200 * 3600, eta_tot=0.6, dod=0.8, energy_reserve=0.2)
    r = size_takeoff_weight(3.0, 0.0, legs, prop, EmptyWeightModel(fixed_fraction=0.45), climb_alt=500)
    assert r.converged and r.energy_J > 0
    assert r.Wf == pytest.approx(r.energy_J / prop.e_spec, rel=1e-6)
