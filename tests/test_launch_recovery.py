# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Opt-in catapult launch and belly landing (first order, any fixed-wing UAV)."""
from __future__ import annotations

import math
import shutil
from pathlib import Path

import pytest
import yaml

from acdt import G0
from acdt.domains.aircraft.launch_recovery import belly_landing, catapult_launch, stall_speed

EX = Path(__file__).resolve().parents[1] / "examples"
needs_avl = pytest.mark.requires_avl


def test_catapult_stroke_energy_force():
    Vs = 25.0
    c = catapult_launch(150.0, Vs, {"accel_g": 10.0, "rail_angle_deg": 10.0, "shuttle_mass_kg": 20.0,
                                    "stroke_max_m": 6.0, "airframe_nx_limit_g": 12.0, "payload_nx_limit_g": 8.0})
    V = 1.1 * Vs
    assert c["V_end_m_s"] == pytest.approx(V) and c["speed_ok"] is True
    assert c["stroke_m"] == pytest.approx(V ** 2 / (2 * 10 * G0))                     # L = V²/(2a)
    assert c["shuttle_force_N"] == pytest.approx(170 * G0 * (10 + math.sin(math.radians(10))))
    assert c["energy_kinetic_J"] == pytest.approx(0.5 * 150 * V ** 2)
    assert c["stroke_ok"] is True and c["airframe_g_ok"] is True and c["payload_g_ok"] is False
    # stroke given → acceleration; headwind counts towards airspeed; no limits → unassessed (None)
    c2 = catapult_launch(150.0, Vs, {"stroke_m": 4.0, "headwind_m_s": 5.0})
    assert c2["V_end_m_s"] == pytest.approx(V - 5.0) and c2["n_x_g"] == pytest.approx((V - 5) ** 2 / 8.0 / G0)
    assert c2["airframe_g_ok"] is None and c2["payload_g_ok"] is None and c2["stroke_ok"] is None
    # too slow at the end of the stroke
    assert catapult_launch(150.0, Vs, {"end_speed_m_s": 26.0, "accel_g": 8})["speed_ok"] is False
    # neither accel nor stroke → n_x unassessed, stroke table reported
    c3 = catapult_launch(150.0, Vs, {})
    assert c3["n_x_g"] is None and "10 g" in c3["stroke_for_g"]


def test_belly_energy_and_slide():
    b = belly_landing(150.0, 3.0, 25.0, {"mu_slide": 0.5, "n_limit": 6.0, "contact_area_m2": 0.05})
    from acdt.domains.aircraft.landing_gear import gear_load_factor, limit_descent_speed_ft_s, wing_loading_psf
    from acdt.domains.aircraft.weights_detailed import FT
    v = limit_descent_speed_ft_s(wing_loading_psf(150.0, 3.0)) * FT
    assert b["sink_rate_m_s"] == pytest.approx(v)
    assert b["n_ground_reaction"] == pytest.approx(gear_load_factor(v, 0.025, 0.5, 2 / 3))
    assert b["V_TD_m_s"] == pytest.approx(1.15 * 25.0)
    assert b["slide_distance_m"] == pytest.approx((1.15 * 25) ** 2 / (2 * 0.5 * G0))
    assert b["load_ok"] is (b["n_ground_reaction"] <= 6.0)
    assert b["contact_pressure_static_Pa"] == pytest.approx(150 * G0 / 0.05)
    b2 = belly_landing(150.0, 3.0, 25.0, {})
    assert b2["slide_distance_m"] is None and b2["load_ok"] is None and "prop_clearance" not in b2


def test_absent_option_runs_nothing():
    from acdt.domains.aircraft.mission import DEFAULT_ASSUMPTIONS
    assert DEFAULT_ASSUMPTIONS["launch_recovery"] is None


@pytest.mark.slow
@needs_avl
def test_tailless_example_catapult_and_belly():
    """Tailless pusher example with the opt-in block: catapult end speed / n_x / stroke, belly energy and the
    pusher-propeller clearance over the belly line."""
    from acdt.domains.aircraft.mission import MissionSpec
    from acdt.domains.aircraft.sizing import run as size_run
    d = yaml.safe_load((EX / "heavy" / "uav150_flying_wing_tailless.yaml").read_text(encoding="utf-8"))
    d["assumptions"]["launch_recovery"] = {"catapult": {"accel_g": 8.0, "rail_angle_deg": 10.0},
                                           "belly_landing": {"mu_slide": 0.5}}
    res = size_run(MissionSpec.from_dict(d, EX / "heavy" / "uav150_flying_wing_tailless.yaml"))
    lr = res.launch_recovery
    ck = {c.key: c for c in res.checks}
    c = lr["catapult"]
    assert c["speed_ok"] is True and c["n_x_g"] == pytest.approx(8.0)
    assert c["V_S_m_s"] == pytest.approx(stall_speed(res.sizing.W0 * G0, res.S, c["CLmax_used"]))
    assert ck["lr:catapult_speed"].ok is True and ck["lr:catapult_airframe_g"].ok is None   # no limit → unassessed
    b = lr["belly_landing"]
    assert 2.1 < b["sink_rate_m_s"] < 3.1 and b["slide_distance_m"] > 0
    pc = b["prop_clearance"]
    assert pc is not None and set(pc["clearance_by_attitude_m"]) == {"0", "5", "10"}
    assert ck["lr:belly_prop_clearance"].ok is pc["ok"]
    assert res.feasible   # lr: checks are reported, not Phase-1 feasibility
