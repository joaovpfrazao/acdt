"""Fase 8c: 6-DOF próprio (Stevens & Lewis flat-earth, quaterniões, RK4), trim, linearização e solo."""
import math

import numpy as np
import pytest

from acdt import G0
from acdt.domains.aircraft.aero.avl import avl_available
from acdt.domains.aircraft.flightsim.aeromodel import (TABLE_KEYS, AeroModel, FlightModel, MassModel, Propulsion,
                                                       build_flight_model)
from acdt.domains.aircraft.flightsim.sixdof import (Controls, SixDOF, dcm_body_to_ned, euler_from_quat, linearise,
                                                    quat_from_euler, state, trim)

needs_avl = pytest.mark.requires_avl


def test_quaternion_euler_roundtrip_and_dcm():
    for ang in [(0.3, -0.2, 2.5), (-1.0, 0.7, -0.4), (0.0, 0.0, 0.0)]:
        e = quat_from_euler(*ang)
        assert np.linalg.norm(e) == pytest.approx(1.0)
        assert euler_from_quat(e) == pytest.approx(ang, abs=1e-12)
        R = dcm_body_to_ned(e)
        assert R @ R.T == pytest.approx(np.eye(3), abs=1e-12)
    # 90° yaw: body x points East
    assert dcm_body_to_ned(quat_from_euler(0, 0, math.pi / 2)) @ [1, 0, 0] == pytest.approx([0, 1, 0], abs=1e-12)


def _inert_model():
    al = [-10.0, 0.0, 10.0]
    t = {k: [[0.0] * 3] for k in TABLE_KEYS}
    a = AeroModel(S=1e-9, b=1.0, c=1.0, x_ref=0.0, alpha_deg=al, flap_deg=[0.0], tables=t, CLmax=[1.0], CD0=0.0,
                  K=0.0, flap_dCD0=[0.0], CLad=0.0, Cmad=0.0, dx_fus=0.0, limits={})
    p = Propulsion(kind="jet", P_sl=None, T_sl=0.0, eta_cruise=1, eta_takeoff=1, V_low=1, c_p=None, c_t=0.0,
                   eta_chain=1, P_sys=0)
    return FlightModel(a, p, MassModel(m=10.0, x_cg=0.0, Ixx=2.0, Iyy=3.0, Izz=4.5, Ixz=0.4, gear={"kind": "none"}))


def test_torque_free_rigid_body_conserves_angular_momentum_and_free_fall():
    sim = SixDOF(_inert_model())
    sim.ground = None
    x = state((0, 0, -1000.0), 0.0, pqr=(0.5, 1.2, -0.3))
    I = np.array([[2.0, 0, -0.4], [0, 3.0, 0], [-0.4, 0, 4.5]])
    def H(x):  # inertial angular momentum
        return dcm_body_to_ned(x[6:10]) @ (I @ x[10:13])
    H0 = H(x)
    t, dt = 0.0, 0.002
    for _ in range(2500):
        x = sim.step(t, x, Controls(), dt)
        t += dt
    assert H(x) == pytest.approx(H0, rel=1e-6, abs=1e-8)
    assert -x[2] == pytest.approx(1000.0 - 0.5 * G0 * t**2, rel=1e-6)  # free fall, no aero


@pytest.fixture(scope="module")
def c172_sim(c172_result):
    return c172_result, SixDOF(build_flight_model(c172_result))


@needs_avl
def test_trim_and_modes_match_linear_stability(c172_sim):
    res, sim = c172_sim
    # Fixed-pitch propeller (Phase 9): at 8000 ft the engine is rpm-limited (2700 rpm redline) and the 6-DOF drag
    # (own build-up, trim included) is ~3 % above the sizing polar, so 122 kt is just out of reach at full
    # throttle; trim at 95 % of the cruise speed (C172S POH: 2700 rpm at 8000 ft ≈ 80 % power, 122–124 KTAS).
    V = 0.95 * res.cruise_speed
    tr = trim(sim, V, res.cruise_altitude)
    assert tr["ok"] and 0 < tr["throttle"] <= 1.0
    lin = linearise(sim, tr["x"], tr["controls"])["modes"]
    ref_lon, ref_lat = res.dynamics["modes"]["longitudinal"], res.dynamics["modes"]["lateral"]
    # same aero data → modes within 15 % of the stability-stage linear model (Nelson Ch. 4–5)
    assert lin["short_period"]["wn"] == pytest.approx(ref_lon["short_period"]["wn"], rel=0.15)
    assert lin["phugoid"]["period_s"] == pytest.approx(ref_lon["phugoid"]["period_s"], rel=0.15)
    assert lin["dutch_roll"]["wn"] == pytest.approx(ref_lat["dutch_roll"]["wn"], rel=0.15)
    assert lin["roll"]["tau_s"] == pytest.approx(ref_lat["roll"]["tau_s"], rel=0.15)
    # trimmed state holds: 20 s open loop, altitude and speed drift small
    x, c, t = tr["x"].copy(), tr["controls"], 0.0
    for _ in range(1000):
        x = sim.step(t, x, c, 0.02)
        t += 0.02
    assert -x[2] == pytest.approx(res.cruise_altitude, abs=2.0)
    assert np.linalg.norm(x[3:6]) == pytest.approx(V, abs=0.5)


@needs_avl
def test_ground_static_load_and_takeoff_roll_vs_raymer(c172_sim):
    from acdt.domains.aircraft.performance import PerfModel, takeoff_distance_integrated
    res, sim = c172_sim
    fm = sim.fm
    x = state((0, 0, -(fm.mass.gear["h_cg"] - 0.07)), 0.0)
    c = Controls(throttle=0.0, flap=10.0)
    t = 0.0
    for _ in range(300):
        x = sim.step(t, x, c, 0.01)
        t += 0.01
    info = {}
    sim.derivatives(t, x, c, info)
    assert info["gear_load"] == pytest.approx(fm.mass.m * G0, rel=1e-3)
    # full-throttle ground roll to V_TO = 1.1 V_S,TO (no rotation) vs Raymer 17.8 with the same thrust model
    c.throttle = 1.0
    Vto = 1.1 * math.sqrt(2 * fm.mass.m * G0 / (1.225 * fm.aero.S * fm.aero.clmax(10.0)))
    x0 = x[0]
    while info["Va"] < Vto and t < 60:
        x = sim.step(t, x, c, 0.01)
        t += 0.01
        sim.derivatives(t, x, c, info)
    ref = takeoff_distance_integrated(PerfModel.from_result(res), fm.mass.m * G0)["ground_roll"]
    assert x[0] - x0 == pytest.approx(ref, rel=0.15)


@pytest.mark.requires_avl
def test_drag_has_body_side_component_with_sideslip(c172_result):
    """Wind-axis forces (11 nov 2026): with β ≠ 0 the drag contributes −D sinβ to the body side force."""
    import math
    import numpy as np
    from acdt.domains.aircraft.flightsim.aeromodel import build_flight_model
    from acdt.domains.aircraft.flightsim.sixdof import Controls, SixDOF
    fm = build_flight_model(c172_result)
    for k in ("CYb", "CYp", "CYr", "CYda", "CYdr"):
        fm.aero.tables[k] = [[0.0] * len(r) for r in fm.aero.tables[k]]
    sim = SixDOF(fm)
    V, b = 50.0, math.radians(5.0)
    x = np.zeros(14)
    x[2], x[3:6], x[6] = -1000.0, [V * math.cos(b), V * math.sin(b), 0.0], 1.0
    info = {}
    xd = sim.derivatives(0.0, x, Controls(), info)
    D = info["CD"] * info["qbar"] * fm.aero.S
    # v̇ = F_y/m − (r u − p w) = F_y/m (no rates); F_y = −D sinβ (+ gravity 0 at level attitude)
    assert xd[4] * info["m"] == pytest.approx(-D * math.sin(b), rel=1e-6)
