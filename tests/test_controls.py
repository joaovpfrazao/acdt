"""Fase 8a: dimensionamento das superfícies de comando por requisitos (Sadraey Cap. 12, MIL-F-8785C, 14 CFR 23).

Funções puras verificadas à mão; a integração (AVL) é saltada sem o binário."""
import math
from pathlib import Path

import numpy as np
import pytest

from acdt.domains.aircraft.aero.avl import avl_available
from acdt.domains.aircraft.flightsim.controls import (LB, bank_angle, flapped_ratio_required, roll_requirements,
                                                      roll_response, sadraey_crab, size_controls, steady_sideslip,
                                                      time_to_bank, trim_point)

EX = Path(__file__).parents[1] / "examples"
needs_avl = pytest.mark.requires_avl


def test_roll_response_closed_form():
    r = roll_response(Clp=-0.5, Clda=0.2, delta_rad=math.radians(20), V=50.0, rho=1.225, S=15.0, b=10.0, Ixx=1500.0)
    # p_ss b/2V = −Clda δ / Clp (Sadraey Eq. 12.45 in coefficient form)
    assert r["pb_2V"] == pytest.approx(0.2 * math.radians(20) / 0.5)
    q = 0.5 * 1.225 * 50**2
    assert r["tau"] == pytest.approx(2 * 1500 * 50 / (0.5 * q * 15 * 100))


def test_time_to_bank_inverts_bank_angle():
    p, tau = 1.2, 0.4
    t = time_to_bank(math.radians(60), p, tau)
    assert float(bank_angle(t, p, tau)) == pytest.approx(math.radians(60), rel=1e-9)
    # τ → 0: t = Δφ / p
    assert time_to_bank(1.0, 2.0, 1e-6) == pytest.approx(0.5, rel=1e-4)


def test_roll_requirements_far23_weight_schedule():
    light = {r["name"]: r["t_max"] for r in roll_requirements(2400 * LB, "cs_23", uav=False)}
    assert light["14 CFR/CS 23.157(a) descolagem"] == 5.0 and light["14 CFR/CS 23.157(c) aproximação"] == 4.0
    heavy = {r["name"]: r["t_max"] for r in roll_requirements(8000 * LB, "far_23", uav=False)}
    assert heavy["14 CFR/CS 23.157(a) descolagem"] == pytest.approx(8500 / 1300)
    assert heavy["14 CFR/CS 23.157(c) aproximação"] == pytest.approx(10800 / 2200)
    uav = roll_requirements(200.0, "uas", uav=True)
    assert len(uav) == 2 and all(r["indicative"] for r in uav)
    assert {r["t_max"] for r in uav} == {1.7, 1.3}  # MIL-F-8785C Table IXa Cat. B / C, Level 1


DER = {"CYb": -0.4, "Clb": -0.08, "Cnb": 0.07, "CYda": 0.0, "Clda": 0.2, "Cnda": -0.01,
       "CYdr": 0.15, "Cldr": 0.01, "Cndr": -0.08}


def test_steady_sideslip_equilibrium():
    beta, CL = math.radians(10), 1.0
    s = steady_sideslip(beta, CL, DER)
    da, dr, ph = s["delta_a"], s["delta_r"], s["phi"]
    assert DER["CYb"] * beta + DER["CYda"] * da + DER["CYdr"] * dr + CL * math.sin(ph) == pytest.approx(0, abs=1e-12)
    assert DER["Clb"] * beta + DER["Clda"] * da + DER["Cldr"] * dr == pytest.approx(0, abs=1e-12)
    assert DER["Cnb"] * beta + DER["Cnda"] * da + DER["Cndr"] * dr == pytest.approx(0, abs=1e-12)
    assert dr > 0  # standard signs: positive β (wind from the right) needs δr > 0 (trailing edge left)


def test_sadraey_crab_converges_and_balances():
    k = dict(rho=1.225, S=16.0, b=11.0, Ss=9.0, dc=0.3, CDy=0.6, Cnb=0.07, CYb=-0.4, Cndr=-0.08, CYdr=0.15)
    c = sadraey_crab(Vw=5.0, U=27.0, **k)
    assert c["converged"] and c["beta"] == pytest.approx(math.atan2(5, 27))
    qT = 0.5 * 1.225 * (27**2 + 25)
    dr, sg, b = c["delta_r"], c["crab"], c["beta"]
    # Sadraey Eqs. 12.105-12.115: yaw-moment and side-force balance
    assert qT * 16 * 11 * (0.07 * (b - sg) - 0.08 * dr) + c["Fw"] * 0.3 * math.cos(sg) == pytest.approx(0, abs=1e-6)
    assert c["Fw"] - qT * 16 * (-0.4 * (b - sg) + 0.15 * dr) == pytest.approx(0, abs=1e-6)


def test_flapped_ratio_inverse_raymer_12_21():
    # plain flap Δc_l,max 0.9 (Raymer Table 12.2): ΔCL = 0.9·0.9·Sf/S
    assert flapped_ratio_required(1.9, 1.5, "plain") == pytest.approx(0.4 / 0.81)
    assert flapped_ratio_required(1.4, 1.5, "plain") == 0.0
    assert math.isinf(flapped_ratio_required(2.0, 1.5, "none"))


def test_trim_point_linear_system():
    lin = {"alpha_ref": math.radians(2), "CL0": 0.4, "Cm0": 0.02, "CLa": 5.0, "Cma": -1.0, "CLde": 0.4,
           "Cmde": -1.5, "x_ref": 1.0}
    t = trim_point(lin, 0.6, x_cg=1.0, c=1.4, dx_fus=0.0)
    da, de = math.radians(t["alpha_deg"]) - lin["alpha_ref"], math.radians(t["delta_e_deg"])
    assert lin["CL0"] + 5 * da + 0.4 * de == pytest.approx(0.6)
    assert lin["Cm0"] - da - 1.5 * de == pytest.approx(0, abs=1e-12)
    # moving the CG aft by 0.1 c (k) makes Cmα less negative by CLα·k
    t2 = trim_point(lin, 0.6, x_cg=1.14, c=1.4, dx_fus=0.0)
    assert t2["Cma_cg"] == pytest.approx(-1.0 + 5.0 * 0.1)


@pytest.fixture(scope="module")
def c172_controls(c172_result, tmp_path_factory):
    return size_controls(c172_result, out_dir=tmp_path_factory.mktemp("c172ctl"))


@pytest.mark.slow
@needs_avl
def test_c172_control_sizing(c172_controls):
    c = c172_controls
    s = c.summary()
    # roll: every requirement checked and met; times are positive and below the limit
    assert c.aileron["ok_current"] and all(0 < r["t_s"] < r["t_max_s"] for r in c.aileron["current"])
    assert {r["requisito"] for r in c.aileron["current"]} >= {"14 CFR/CS 23.157(a) descolagem"}
    # elevator: rotation at V_R (tricycle) needs up elevator (TE up, negative) within the stop
    rot = c.elevator["rotation"]
    assert rot is not None and rot["delta_e_deg"] < 0 and rot["ok"]
    assert c.elevator["tail_stall"]["CLh_worst"] > 0
    # rudder: 14 CFR 23.233 crosswind 0.2 V_S0 and single engine → OEI not applicable
    cw = c.rudder["crosswind"]
    assert cw["ok"] and cw["crosswind_max_kt"] > cw["crosswind_req_kt"] > 5.0
    assert not c.rudder["oei"]["applicable"]
    # hinge moments: AVL hinge derivative of a plain flap control is negative (restoring)
    for k in ("aileron", "elevator", "rudder"):
        assert c.hinge[k]["Ch_delta_surface"] < 0 and c.hinge[k]["H_max_Nm"] > 0
    assert all(Path(p).exists() for p in s["plots"].values())
    # sized layout never smaller than the candidate floor and within Sadraey's typical bounds
    assert 0.15 <= s["layout_sized"]["aileron_span_fraction"] <= 0.5
    assert 0.15 <= s["layout_sized"]["elevator_cf_c"] <= 0.5
