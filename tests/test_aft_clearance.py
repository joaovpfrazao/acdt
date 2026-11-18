# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Dynamic aft ground clearance (Sadraey 2012 Sec. 9.5.1.3 Eq. 9.2–9.3) — generic, no AVL."""
from __future__ import annotations

import math

import numpy as np
import pytest

from acdt.domains.aircraft.flightsim.ground_clearance import AftMonitor, aft_geometry, assess_aft_clearance
from acdt.domains.aircraft.flightsim.sixdof import dcm_body_to_ned, state

# body axes x fwd, z down, relative to the CG; main contact 0.3 m aft / 0.5 m below, aft point 1.3 m aft / 0.2 m below
C = [("main_L", np.array([-0.3, -0.5, 0.5]), 1, 1, False, None),
     ("main_R", np.array([-0.3, 0.5, 0.5]), 1, 1, False, None),
     ("nose", np.array([1.0, 0.0, 0.5]), 1, 1, True, None),
     ("aft_strike", np.array([-1.3, 0.0, 0.2]), 1, 1, False, 0.5)]


def test_geometry_is_sadraey_eq_9_3():
    g = aft_geometry(C)
    assert len(g) == 1 and g[0]["AB_m"] == pytest.approx(1.0) and g[0]["H_m"] == pytest.approx(0.3)
    assert g[0]["alpha_C_deg"] == pytest.approx(math.degrees(math.atan(0.3)))   # α_C = atan(H/AB)
    assert aft_geometry([c for c in C if c[0] != "aft_strike"]) == []


def _pose(theta_deg, compression=0.0):
    """CG position so the main contact sits ``compression`` below the ground at pitch θ (pivot on the mains)."""
    th = math.radians(theta_deg)
    x = state((0.0, 0.0, 0.0), 0.0, theta=th)
    R = dcm_body_to_ned(x[6:10])
    x[2] = -(R @ C[0][1])[2] + compression
    return x, R


def test_monitor_clearance_matches_pivot_geometry():
    m = AftMonitor(C)
    for th in (0.0, 8.0, 12.0):
        x, R = _pose(th)
        m.sample(x, R, {})
    s = m.summary()
    th = math.radians(12.0)
    assert s["status"] == "assessed" and s["theta_max_near_ground_deg"] == pytest.approx(12.0)
    assert s["min_clearance_m"] == pytest.approx(0.3 * math.cos(th) - 1.0 * math.sin(th), abs=1e-9)
    # above 0.5 m the attitude is not "near the ground"
    m2 = AftMonitor(C)
    x, R = _pose(30.0)
    x[2] -= 2.0
    m2.sample(x, R, {})
    assert m2.summary()["status"] == "nao_avaliado"


def test_strike_reported_with_options():
    m = AftMonitor(C)
    x, R = _pose(18.0, compression=0.05)   # beyond α_C (16.7°) and compressed → negative clearance
    x[3:6] = [0.0, 0.0, 1.0]               # sinking 1 m/s (body ≈ NED here enough for the bumper energy)
    m.sample(x, R, {"aft_strike": 120.0})
    r = assess_aft_clearance(C, {"landing": m.summary()}, 150.0, 40.0)
    assert r["ok"] is False and "issue" in r and r["min_clearance_m"] < 0
    assert r["alpha_C_compressed_deg"] < r["alpha_C_deg"]
    o = r["options"]
    assert o["strut_extension"]["delta_h_both_legs_m"] == pytest.approx(-r["min_clearance_m"] / math.cos(math.radians(18.0)))
    tb = o["tail_bumper"]
    m_eff = 1.0 / (1.0 / 150.0 + 1.3 ** 2 / 40.0)
    assert tb["m_eff_kg"] == pytest.approx(m_eff) and tb["v_design_m_s"] > 0.5
    assert tb["P_des_N"] == pytest.approx(1.5 * 0.5 * m_eff * tb["v_design_m_s"] ** 2 / (0.5 * 0.025))
    assert o["attitude_limit"]["theta_max_near_ground_deg"] == pytest.approx(r["alpha_C_compressed_deg"] - 2.0)
    assert r["phases"]["landing"]["contact_peak_N"] == 120.0


def test_unassessed_without_aft_point_or_samples():
    assert assess_aft_clearance(C[:3], {}, 150.0, 40.0)["status"] == "nao_avaliado"
    r = assess_aft_clearance(C, {"takeoff": {"status": "nao_avaliado"}}, 150.0, 40.0)
    assert r["status"] == "nao_avaliado" and r["ok"] is None
