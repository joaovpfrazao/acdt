"""Tailless split-aileron follow-up (10 nov 2026): hinge moments + servo selection, actuator dynamics in the SAS
loop, lateral gust, linear trim and the drag-rudder channel of the 6-DOF/JSBSim model."""
import math

import numpy as np
import pytest

from acdt.domains.aircraft.assembly import tailless_actuation as TX
from acdt.domains.aircraft.assembly import tailless_approach as TA

CAT = [{"name": "small", "torque_Nm": 2.7, "peak_torque_Nm": 5.0, "speed_deg_s": 200, "mass_kg": 0.27, "travel_deg": 45},
       {"name": "mid", "torque_Nm": 8.0, "peak_torque_Nm": 16.0, "speed_deg_s": 150, "mass_kg": 0.63},
       {"name": "big", "torque_Nm": 80.0, "peak_torque_Nm": 200.0, "speed_deg_s": 80, "mass_kg": 5.6}]


def _A4(U=40.0):
    # [β, p, r, φ] with an under-damped Dutch roll (generic numbers, test only)
    return np.array([[-0.2, 0.0, -1.0, 9.81 / U], [-5.0, -8.0, 1.0, 0.0], [2.0, -0.1, -0.05, 0.0], [0.0, 1.0, 0.0, 0.0]])


def test_split_ch_envelope_and_out_of_data():
    assert TX.split_ch(0) == pytest.approx(0.135)
    assert TX.split_ch(60) == pytest.approx(0.64)
    assert TX.split_ch(-30) == pytest.approx(0.43)
    assert TX.split_ch(22.5) == pytest.approx(0.5 * (0.30 + 0.43))
    assert TX.split_ch(61) is None            # beyond the TN 690 data → unknown, not extrapolated


def test_split_hinge_schedule_23_455():
    geom = {"eta_inner": 0.5, "eta_outer": 1.0, "semispan": 2.0, "S_f": 0.2}
    h = TX.split_hinge(geom, 60.0, 40.0, 50.0, 1.225)
    full, third = h["conditions"]
    assert full["delta_deg"] == 60 and third["delta_deg"] == pytest.approx(20)
    assert full["H_Nm"] == pytest.approx(0.64 * 0.5 * 1.225 * 40**2 * 0.2 * 0.2)
    assert h["H_max_Nm"] == max(full["H_Nm"], third["H_Nm"])
    assert TX.split_hinge(geom, 70.0, 40.0, 50.0, 1.225)["H_max_Nm"] is None


def test_select_servo_lightest_fit_ganging_travel_and_unknowns():
    assert TX.select_servo(CAT, None, 100, 1.5)["ok"] is None
    assert TX.select_servo([], 5.0, 100, 1.5)["status"] == "unassessed"
    r = TX.select_servo(CAT, 3.0, 100, 1.5)          # 4.5 N·m hold → small (G 0.9, 222 °/s)
    assert r["ok"] is True and r["servo"]["name"] == "small" and r["servo"]["n_per_surface"] == 1
    r = TX.select_servo(CAT, 20.0, 150, 1.5, H_op=5.0)  # 30 N·m hold: only big alone; 2 ganged mid → G 0.94, 160 °/s
    assert r["servo"]["name"] == "big"
    r2 = TX.select_servo(CAT, 20.0, 150, 1.5, H_op=5.0, n_max=2)
    assert r2["servo"]["name"] == "mid" and r2["servo"]["n_per_surface"] == 2
    assert r2["servo"]["mass_kg"] == pytest.approx(1.26)
    # known travel exceedance disqualifies; unknown travel stays None (not pass)
    r3 = TX.select_servo(CAT, 4.0, None, 1.5, H_op=1.0, delta_max_deg=25.0)   # small: G 1.2 → 30° ≤ 45°
    assert r3["servo"]["name"] == "small" and r3["servo"]["travel_ok"] is True and r3["ok"] is None
    r4 = TX.select_servo(CAT, 4.0, None, 1.5, H_op=1.0, delta_max_deg=40.0)   # small: 48° > 45° → mid (travel unknown)
    assert r4["servo"]["name"] == "mid" and r4["servo"]["travel_ok"] is None
    r5 = TX.select_servo(CAT, 500.0, 10, 1.5)
    assert r5["ok"] is False and r5["servo"] is None


def test_budget_items_by_name():
    it = [{"name": "Atuadores split", "mass_kg": 1}, {"name": "servos", "mass_kg": 2}, {"name": "cablagem", "mass_kg": 3}]
    assert [i["mass_kg"] for i in TX.budget_items(it)] == [1, 2]


def test_augmented_loop_reduces_to_ideal_and_delay_degrades_damping():
    A4, U, b, q = _A4(), 40.0, 4.0, 30.0
    kb, kr = 0.0, 0.3
    ideal = TX.augmented_loop(A4, kb, kr, q, b, U, 0.0, 0.0)
    K = np.array([kb, 0.0, -kr * b / (2 * U), 0.0])
    assert np.allclose(ideal, A4 + np.outer([0, 0, q, 0], K))
    assert TX.augmented_loop(A4, kb, kr, q, b, U, 0.05, 0.1).shape == (7, 7)
    ref = [l for l in np.linalg.eigvals(ideal) if l.imag > 0][0]
    z0 = TX.dutch_roll_of(ideal, ref)["zeta"]
    z1 = TX.dutch_roll_of(TX.augmented_loop(A4, kb, kr, q, b, U, 0.0, 0.2), ref)["zeta"]
    assert z1 < z0


def test_actuator_dynamics_unknown_delay_is_level1_limit():
    r = TX.actuator_dynamics(_A4(), 0.0, 0.3, 30.0, 4.0, 40.0, "B", None, None)
    assert r["status"] == "assessed" and r["delay_s"] == TX.TIME_DELAY_LIMITS_S[0] == 0.10
    assert TX.TIME_DELAY_LIMITS_S == (0.10, 0.20, 0.25)
    r0 = TX.actuator_dynamics(_A4(), 0.0, 0.3, 30.0, 4.0, 40.0, "B", 0.0, 0.0)
    assert r0["delay_s"] == 0.0


def test_pade2_dc_gain_one():
    A, B, C, D = TX.pade2(0.1)
    assert float(np.squeeze(D - C @ np.linalg.solve(A, B))) == pytest.approx(1.0)
    assert TX.pade2(0.0) is None


def test_split_actuator_delay_rate_and_saturation():
    C1, dt = 0.01, 0.01
    a = TX.SplitActuator(C1, 60.0, 100.0, 0.0, 0.05, dt)
    outs = [a.step(0.5 * 2 * C1) for _ in range(80)]    # target sin²s = 0.5 → s = 45°
    assert outs[3] == 0.0 and outs[5] > 0.0            # 5-step transport delay
    assert a.rate_lim and a.peak_rate == pytest.approx(math.radians(100.0))
    assert math.degrees(a.s) == pytest.approx(45.0)
    assert 0 < a.n_lim / a.n_steps < 1
    b = TX.SplitActuator(C1, 30.0, None, 0.0, 0.0, dt)
    b.step(2 * C1)                                       # 90° demand clipped at 30°
    assert b.sat and math.degrees(b.s) == pytest.approx(30.0)
    assert b.dCn() == pytest.approx(2 * C1 * math.sin(math.radians(30)) ** 2)
    assert TX.SplitActuator(C1, 60, None, 0, 0, dt).step(-0.004) < 0  # signed


def test_bank_hold_gains_beard_mclain():
    kp, kd, wn = TX.bank_hold_gains(-10.0, 50.0, math.radians(25))
    assert kp == pytest.approx(25 / 15)
    assert wn == pytest.approx(math.sqrt(50 * 25 / 15))
    assert kd == pytest.approx((2 * 0.707 * wn - 10.0) / 50.0)


def test_linear_trim_and_trimmed_clmax():
    d0 = {"CL": 0.1, "Cm": 0.02, "CLa": 4.0, "Cma": -1.0, "CLde": 0.5, "Cmde": -0.4}
    a, de = TA.linear_trim(d0, 0.5)
    assert d0["CL"] + d0["CLa"] * a + d0["CLde"] * de == pytest.approx(0.5)
    assert d0["Cm"] + d0["Cma"] * a + d0["Cmde"] * de == pytest.approx(0.0, abs=1e-12)
    t = TA.trimmed_clmax(d0, math.radians(25))
    a2, de2 = TA.linear_trim(d0, t["CL"])
    assert abs(math.degrees(de2)) == pytest.approx(25.0)


def test_body_cm_derivatives_enter_trim():
    """Torenbeek NP shift C_m += C_N k changes the main trim (k = −ΔX_np/c̄)."""
    d0 = {"CL": 0.1, "Cm": 0.02, "CLa": 4.0, "Cma": -1.0, "CLde": 0.5, "Cmde": -0.4}
    k = -0.02
    db = TA.body_cm_derivatives(d0, k)
    assert db["Cm"] == pytest.approx(d0["Cm"] + d0["CL"] * k)
    assert db["Cma"] == pytest.approx(d0["Cma"] + d0["CLa"] * k)
    assert db["Cmde"] == pytest.approx(d0["Cmde"] + d0["CLde"] * k)
    a0, de0 = TA.linear_trim(d0, 0.5)
    ab, deb = TA.linear_trim(db, 0.5)
    assert de0 != deb
    assert db["Cm"] + db["Cma"] * ab + db["Cmde"] * deb == pytest.approx(0.0, abs=1e-12)


def test_drag_rudder_channel_aeromodel_and_jsbsim_xml(tmp_path):
    from acdt.domains.aircraft.flightsim.aeromodel import TABLE_KEYS, AeroModel, FlightModel, MassModel, Propulsion
    from acdt.domains.aircraft.flightsim.jsbsim_export import write_jsbsim_aircraft
    tabs = {k: [[0.0, 0.0]] for k in TABLE_KEYS}
    tabs["CLa"], tabs["CL"], tabs["Cndr"] = [[4.0, 4.0]], [[0.0, 0.7]], [[1.0, 1.0]]
    kw = dict(S=2.0, b=4.0, c=0.5, x_ref=0.0, alpha_deg=[0.0, 10.0], flap_deg=[0.0], tables=tabs, CLmax=[1.2],
              CD0=0.02, K=0.05, flap_dCD0=[0.0], CLad=0.0, Cmad=0.0, dx_fus=0.0,
              limits={"elevator": 25, "aileron": 25, "rudder": 1.0, "flap": 0})
    a0, a1 = AeroModel(**kw), AeroModel(**kw, yaw_drag_per_Cn=2.5)
    args = (0.05, 0.0, 0, 0, 0, 0, 0, 0)
    c0 = a0.coefficients(*args, 0.004, 0.0, 0.0)
    c1 = a1.coefficients(*args, 0.004, 0.0, 0.0)
    c1n = a1.coefficients(*args, -0.004, 0.0, 0.0)
    assert c1["CD"] - c0["CD"] == pytest.approx(2.5 * 0.004)
    assert c1n["CD"] == pytest.approx(c1["CD"]) and c1["Cn"] == pytest.approx(0.004)
    pr = Propulsion(kind="electric", P_sl=5000.0, T_sl=None, eta_cruise=0.7, eta_takeoff=0.5, V_low=15.0, c_p=None,
                    c_t=None, eta_chain=0.9, P_sys=0.0)
    mm = MassModel(m=50.0, x_cg=0.0, Ixx=10.0, Iyy=5.0, Izz=14.0, gear={"kind": "none", "h_cg": 0.2})
    for aero, has in ((a0, False), (a1, True)):
        p = write_jsbsim_aircraft(FlightModel(aero, pr, mm), tmp_path / ("y" if has else "n"))
        xml = open(p, encoding="utf-8").read()
        assert ("D_drag_rudder" in xml) is has
