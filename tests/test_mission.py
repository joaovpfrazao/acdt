"""Phase 8 E: Dryden wind, classic autopilot (Beard & McLain) and the 6-DOF mission runner."""
import math

import numpy as np
import pytest

pytest.importorskip("scipy")


@pytest.fixture(scope="module")
def fm(c172_result):
    from acdt.domains.aircraft.flightsim.aeromodel import build_flight_model
    return build_flight_model(c172_result)


def test_dryden_sigma_and_band_switch():
    from acdt.domains.aircraft.flightsim.wind import WindField, dryden_parameters
    assert dryden_parameters(600.0, "moderate")["sigma"][2] == pytest.approx(3.0)
    w = WindField.from_dict({"turbulence": {"intensity": "moderate", "seed": 1}})
    dt, xs = 0.02, []
    for k in range(60000):  # 1200 s at 50 m/s, 600 m
        w.advance(k * dt, dt, 50.0, 0.0, 600.0)
        xs.append(w(k * dt, np.zeros(3)))
    s = np.std(np.array(xs), axis=0)
    assert np.all(np.abs(s - 3.0) < 0.6), s
    # crossing the 300 m band switch must not produce a jump of many sigmas (filter-state rescaling)
    w = WindField.from_dict({"turbulence": {"intensity": "light", "seed": 2}})
    prev = None
    for k in range(4000):
        h = 320.0 - 0.01 * k
        w.advance(k * dt, dt, 20.0, 0.0, h)
        cur = w(k * dt, np.zeros(3))
        if prev is not None:
            assert np.linalg.norm(cur - prev) < 1.5
        prev = cur
    with pytest.raises(ValueError):
        dryden_parameters(100.0, "severe")


@pytest.mark.requires_avl
def test_autopilot_gains(fm):
    from acdt.domains.aircraft.flightsim.autopilot import design_gains
    from acdt.domains.aircraft.flightsim.sixdof import SixDOF, trim
    sim = SixDOF(fm)
    tr = trim(sim, 50.0, 1000.0)
    g = design_gains(sim, tr, 0.0)
    assert tr["ok"]
    for k in ("kp_phi", "kd_phi", "kp_h", "ki_h", "kp_V", "ki_V"):
        assert math.isfinite(g[k]) and g[k] > 0, (k, g[k])
    # pitch gains carry the sign of a_θ3 (δe > 0 = TE down gives nose down): negative here
    assert g["kp_theta"] < 0 and g["kd_theta"] < 0
    assert 0.3 < g["K_theta_DC"] <= 1.0
    assert g["design"]["W_h"] >= 5  # successive loop closure: bandwidth separation (Beard & McLain Sec. 6.4)


@pytest.mark.slow
@pytest.mark.requires_avl
def test_short_mission_c172(fm, tmp_path):
    from acdt.domains.aircraft.flightsim.mission import simulate_mission_6dof
    ms = {"name": "curta", "dt": 0.02, "segments": [
        {"type": "takeoff", "flap": 10}, {"type": "climb", "to_altitude_m": 200},
        {"type": "cruise", "time_min": 1},  # at the climb speed: no acceleration energy
        {"type": "turn", "heading_change_deg": 180, "load_factor": 1.3},
        {"type": "descent", "to_altitude_m": 120, "speed_m_s": 40},
        {"type": "landing", "flap": 30}]}
    r = simulate_mission_6dof(fm, ms, out_dir=tmp_path, hq=False)
    assert r["aborted"] is None, r["aborted"]
    S = {s["type"]: s for s in r["segments"]}
    to, ld = S["takeoff"], S["landing"]
    # sanity bands around POH-class numbers for a C172 (ground roll ~290 m, ~500 m over 15 m; landing ~500 m)
    assert 180 < to["ground_roll_m"] < 400
    assert to["ground_roll_m"] < to["distance_to_15m_m"] < 700
    assert 300 < ld["total_from_15m_m"] < 800
    assert ld["sink_at_touchdown_m_s"] < 1.5
    assert abs(S["cruise"]["k_energy"] - 1.0) < 0.15
    assert S["turn"]["nz_max"] == pytest.approx(1.3, abs=0.35)
    assert r["quasi_steady"]["k_energy_airborne"] == pytest.approx(1.0, abs=0.15)
    for f in ("time_history", "trajectory_3d", "ground_track", "history_csv", "summary_json"):
        assert r["files"][f]


@pytest.mark.requires_avl
def test_airborne_turbulence_mission(fm):
    from acdt.domains.aircraft.flightsim.mission import simulate_mission_6dof
    ms = {"dt": 0.02, "extrapolate_after_s": 40, "initial": {"altitude_m": 800, "speed_m_s": 50},
          "wind": {"speed_m_s": 6, "from_deg": 0, "turbulence": {"intensity": "light", "seed": 5},
                   "gusts": [{"t": 10, "amplitude_m_s": 4, "gradient_m": 30}]},
          "segments": [{"type": "cruise", "time_min": 2, "speed_m_s": 50},
                       {"type": "loiter", "time_min": 3, "load_factor": 1.2}]}
    r = simulate_mission_6dof(fm, ms, hq=False)
    assert r["aborted"] is None
    cr, lo = r["segments"]
    assert abs(cr["h1_m"] - 800) < 30 and cr["extrapolated_min"] > 0
    assert lo["radial_err_rms_m"] < 0.25 * lo["radius_m"]
    assert cr["stall_time_s"] == 0.0
