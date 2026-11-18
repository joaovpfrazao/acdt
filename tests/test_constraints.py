import math

import numpy as np
import pytest

from acdt.core.atmosphere import isa
from acdt.domains.aircraft.constraints import (AeroContext, ConstraintContext, PropContext, build_constraints, design_point,
                              plot_constraint_diagram)
from acdt.core.requirements import RequirementSet

AERO = AeroContext(CD0=0.025, K=0.045, CLmax_clean=1.4, CLmax_takeoff=1.6, CLmax_landing=1.9)


def ctx(kind="piston_prop"):
    return ConstraintContext(AERO, PropContext(kind), cruise_altitude=1500.0, cruise_speed=60.0)


def test_cruise_tw_matches_textbook():
    rs = RequirementSet.from_dict({"payload_mass": 1, "cruise_speed": {"target": 60}})
    c = build_constraints(rs, ctx("jet"))[0]
    ws = np.array([800.0])
    q = 0.5 * isa(1500).rho * 60**2
    tw = q * AERO.CD0 / 800 + AERO.K * 800 / q  # Gudmundsson 2014 Sec. 3.2 (n=1)
    assert c.tw(ws)[0] == pytest.approx(tw)


def test_turn_rate_load_factor():
    rs = RequirementSet.from_dict({"payload_mass": 1,
                                   "turn_rate": {"min": 20, "unit": "deg/s", "speed": 50}})
    c = build_constraints(rs, ctx())[0]
    n = math.sqrt(1 + (math.radians(20) * 50 / 9.80665) ** 2)
    assert f"n={n:.2f}" in c.name


def test_stall_line_and_design_point_max_wing_loading():
    rs = RequirementSet.from_dict({"payload_mass": 1, "stall_speed": {"max": 25}, "climb_rate": {"min": 3},
                                   "cruise_speed": {"target": 60}})
    cons = build_constraints(rs, ctx())
    ws_stall = 0.5 * 1.225 * 25**2 * 1.9
    dp = design_point(cons, PropContext("piston_prop"))
    assert dp.ws == pytest.approx(ws_stall, rel=1e-3)
    assert any("Perda" in a for a in dp.active)
    env_at = max(c.required(np.array([dp.ws]), PropContext("piston_prop"))[0] for c in cons if c.kind == "curve")
    assert dp.value == pytest.approx(env_at)


def test_design_point_min_power_and_infeasible_power(tmp_path):
    rs = RequirementSet.from_dict({"payload_mass": 1, "cruise_speed": {"target": 60},
                                   "climb_rate": {"min": 4}})
    cons = build_constraints(rs, ctx())
    p = PropContext("piston_prop")
    dp = design_point(cons, p, criterion="min_power")
    grid = np.linspace(100, 3000, 3000)
    env = np.max([c.required(grid, p) for c in cons], axis=0)
    assert dp.value == pytest.approx(env.min(), rel=2e-3)
    bad = design_point(cons, p, value_max=0.5 * dp.value)
    assert not bad.feasible and "Infeasible" in bad.message
    png = plot_constraint_diagram(dp, cons, tmp_path / "c.png", "t")
    assert (tmp_path / "c.png").stat().st_size > 10_000 and png


def test_ws_limit_below_range_is_infeasible():
    rs = RequirementSet.from_dict({"payload_mass": 1, "stall_speed": {"max": 5}, "cruise_speed": {"target": 60}})
    dp = design_point(build_constraints(rs, ctx()), PropContext("piston_prop"), ws_range=(50, 3000))
    assert not dp.feasible
