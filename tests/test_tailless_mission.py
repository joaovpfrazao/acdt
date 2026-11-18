# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Tailless (11 nov 2026): split pre-deflection drag in the polar, yaw channel of the mission autopilot through the
drag rudder (SAS + washout + decrab heading loop), nose-wheel steering sign and bumpers in the ground model."""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import pytest

from acdt.domains.aircraft.assembly import Assembly
from acdt.domains.aircraft.assembly import tailless as T

EX = Path(__file__).resolve().parents[1] / "examples"
TL = json.loads((EX / "integration" / "flying_wing_pusher_tailless.json").read_text(encoding="utf-8"))
SA = {"eta_inner": 0.45, "eta_outer": 0.98, "cf_c": 0.40, "delta_max_deg": 60}


def _spec(**sa):
    return {"assembly": TL["assembly"], "options": {"flying_wing": {"yaw_control": "split_aileron",
                                                                    "split_aileron": {**SA, **sa}}}}


def test_bias_drag_is_mccormick_both_sides_and_opt_in():
    asm = Assembly.from_dict(TL["assembly"])
    assert T.bias_drag(_spec(), asm) is None and T.bias_deg(_spec()) == 0.0          # opt-in
    r = T.bias_drag(_spec(bias_deg=2), asm)
    g = T.split_geometry(asm, 0.45, 0.98, 0.40)
    one = T.split_drag_increment(0.40, g["S_f"] / g["S"], 2.0)                         # both leaves, one side
    assert r["status"] == "assessed" and r["dCD0"] == pytest.approx(2 * one)
    assert r["dCD0"] == pytest.approx(2 * 1.7 * 0.4 ** 1.38 * g["S_f"] / g["S"] * 2 * math.sin(math.radians(2)) ** 2)
    assert "issues" not in r
    assert "issues" in T.bias_drag(_spec(bias_deg=35), asm)                            # 2δ0 > δ_max
    miss = {"assembly": TL["assembly"], "options": {"flying_wing": {"yaw_control": "split_aileron",
                                                                    "split_aileron": {"bias_deg": 2}}}}
    assert T.bias_drag(miss, asm)["dCD0"] is None                                     # unknown ≠ zero


@pytest.fixture(scope="module")
def fm_drag_rudder(c172_result):
    """C172 flight model turned into a drag-rudder airplane (rudder channel = ΔC_n, C_Yδr = 0) — mechanics only."""
    from acdt.domains.aircraft.flightsim.aeromodel import build_flight_model
    fm = copy.deepcopy(build_flight_model(c172_result))
    a = fm.aero
    for k, v in (("CYdr", 0.0), ("Cldr", 0.0), ("Cndr", 1.0)):
        a.tables[k] = [[v] * len(a.alpha_deg) for _ in a.flap_deg]
    a.limits["rudder"] = math.degrees(0.02)
    a.yaw_drag_per_Cn = 4.0
    a.yaw_sas = {"k_beta": 0.0, "k_r": 0.075, "washout_s": 4.2, "C1": 0.014, "delta_max_deg": 60.0,
                 "rate_max_deg_s": None, "lag_s": 0.0, "delay_s": 0.0, "bias_deg": 0.0, "dt": 0.02}
    return fm


@pytest.mark.requires_avl
def test_ground_steering_follows_the_yaw_capacity(fm_drag_rudder, c172_result):
    from acdt.domains.aircraft.flightsim.aeromodel import build_flight_model
    from acdt.domains.aircraft.flightsim.sixdof import GroundModel
    g0 = GroundModel.from_model(build_flight_model(c172_result))
    assert g0.steer_ref == 0.5 and g0.steer_sign == -1.0                # conventional rudder unchanged
    g1 = GroundModel.from_model(fm_drag_rudder)
    assert g1.steer_ref == pytest.approx(0.02) and g1.steer_sign == 1.0
    fm2 = copy.deepcopy(fm_drag_rudder)
    fm2.mass.gear = {**fm2.mass.gear, "bumpers": [{"name": "tip_R", "r_body": [0.0, 5.0, 0.5]}]}
    g2 = GroundModel.from_model(fm2)
    tip = [c for c in g2.contacts if c[0] == "tip_R"][0]
    m_eff = 1 / (1 / fm2.mass.m + 25.0 / fm2.mass.Ixx)
    assert tip[2] <= m_eff * 25.0 ** 2 + 1e-6                            # stiffness capped for explicit RK4


@pytest.mark.requires_avl
def test_yaw_channel_washout_and_decrab(fm_drag_rudder):
    from acdt.domains.aircraft.flightsim.autopilot import Autopilot, design_gains
    from acdt.domains.aircraft.flightsim.sixdof import SixDOF, trim
    sim = SixDOF(fm_drag_rudder)
    tr = trim(sim, 50.0, 1000.0)
    ap = Autopilot(sim, design_gains(sim, tr, 0.0))
    assert ap.split is not None and ap.loops["beta"].kp == 0.0          # no C_Yδr → no rudder sideslip PI
    m = {"beta": 0.0, "r": 0.1, "Va": 50.0, "psi": 0.0, "alpha": math.radians(tr["alpha_deg"])}
    u0 = ap.yaw(m, 0.02)
    assert u0 < 0                                                         # damper opposes r at first
    for _ in range(int(30 / 0.02)):
        u = ap.yaw(m, 0.02)
    assert abs(u) < 0.05 * abs(u0)                                        # washout: steady turn not opposed
    ys = fm_drag_rudder.aero.yaw_sas
    ys.update({"k_psi": 0.05, "k_dpsi": 0.0, "k_ipsi": 0.0})
    ap2 = Autopilot(sim, design_gains(sim, tr, 0.0))
    u = ap2.yaw({"beta": 0.0, "r": 0.0, "Va": 50.0, "psi": -0.1, "alpha": math.radians(tr["alpha_deg"])}, 0.02,
                psi_c=0.0)
    assert u > 0                                                          # heading left of command → nose right
    for k in ("k_psi", "k_dpsi", "k_ipsi"):
        ys.pop(k)
