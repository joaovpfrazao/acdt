"""P3: point-mass mission (Anderson 1999 Ch. 5, Raymer 2018 Ch. 17), sensor and failure hooks.

The analytical cases recompute the cited identity. The 6-DOF comparison uses the same 15 % band already
accepted for k_energy (6-DOF fuel / quasi-steady fuel)."""
import math
import random
from pathlib import Path

import pytest

from acdt import G0
from acdt.core.atmosphere import isa
from acdt.domains.aircraft.flightsim.mission import load_mission
from acdt.domains.aircraft.flightsim.pointmass import Plant, PointMassMission, simulate_pointmass_mission, wind_triangle

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "examples" / "simulation" / "n0_patrol.yaml"
# Same band as test_mission.py (|k_energy − 1| < 0.15) and test_ai.py (0.85–1.15).
TOL = 0.15


def _electric(**over):
    prop = {"kind": "electric", "P_sl_W": 8000.0, "eta_cruise": 0.70, "eta_takeoff": 0.55,
            "eta_tot": 0.70, "n_engines": 1, "P_systems_W": 0.0, "battery_Wh": 5000.0}
    prop.update(over.pop("propulsion", {}))
    ac = {"source": "teste analítico", "mass_kg": 20.0, "S_m2": 1.2, "CD0": 0.03, "K": 0.04,
          "CLmax": 1.4, "propulsion": prop}
    ac.update(over)
    return ac


def _piston():
    return {"source": "teste analítico", "mass_kg": 1000.0, "S_m2": 16.0, "CD0": 0.03, "K": 0.05,
            "CLmax": 1.5, "mu_roll": 0.04, "CL_ground": 0.5, "dCD0_takeoff": 0.01, "mu_brake": 0.4,
            "propulsion": {"kind": "piston_prop", "P_sl_W": 120000.0, "eta_cruise": 0.75, "eta_takeoff": 0.55,
                           "c_p": 8.0e-8, "fuel_kg": 80.0, "n_engines": 1, "P_systems_W": 0.0}}


def _jet_glide():
    return {"source": "teste analítico", "mass_kg": 100.0, "S_m2": 10.0, "CD0": 0.02, "K": 0.05, "CLmax": 1.2,
            "propulsion": {"kind": "jet", "T_sl_N": 0.0, "c_t": 0.0, "n_engines": 1}}


def _run(aircraft, segments, **extra):
    ms = {"name": "t", "aircraft": aircraft, "segments": segments,
          "pointmass_dt": extra.pop("pointmass_dt", 1.0e6), **extra}
    return simulate_pointmass_mission(ms)


def _fly(aircraft, segments, **extra):
    """Runner left intact so the test can read the final north/east."""
    ms = {"name": "t", "aircraft": aircraft, "segments": segments,
          "pointmass_dt": extra.pop("pointmass_dt", 1.0e6), **extra}
    ms = load_mission(ms)
    sim = PointMassMission(Plant.from_n0(ms["aircraft"]), ms)
    return sim, sim.run()


# ---------------------------------------------------------------- wind triangle (Anderson 1999 Ch. 3)
def test_wind_triangle_headwind_and_crosswind():
    # from the north: steady NED = [−V, 0, 0]. Course north → pure headwind, no crab.
    head = wind_triangle(40.0, 0.0, 0.0, [-10.0, 0.0, 0.0])
    assert head["Vg"] == pytest.approx(30.0)
    assert head["crab"] == pytest.approx(0.0)
    assert head["vN"] == pytest.approx(30.0) and head["vE"] == pytest.approx(0.0)
    # from the east: steady = [0, −V, 0]. Course north → crab into the wind (positive).
    cross = wind_triangle(40.0, 0.0, 0.0, [0.0, -10.0, 0.0])
    assert cross["crab"] > 0
    assert math.sin(cross["crab"]) == pytest.approx(10.0 / 40.0)
    assert cross["Vg"] == pytest.approx(math.sqrt(40.0 ** 2 - 10.0 ** 2))
    assert wind_triangle(10.0, 0.0, 0.0, [-12.0, 0.0, 0.0]) is None


def test_headwind_time_matches_transit():
    from acdt.core.concept.ops import transit
    V, w, dist_km = 50.0, 8.0, 3.0
    r = _run(_piston(), [{"type": "cruise", "distance_km": dist_km, "speed_m_s": V, "heading_deg": 0}],
             initial={"altitude_m": 0, "heading_deg": 0}, wind={"speed_m_s": w, "from_deg": 0})
    assert r["aborted"] is None, r["aborted"]
    t_out = transit(dist_km, V, w)["t_out_h"] * 3600.0
    assert r["total_time_min"] * 60.0 == pytest.approx(t_out, rel=1e-9)
    assert r["total_dist_km"] == pytest.approx(dist_km, rel=1e-9)


def test_turbulence_and_gusts_are_ignored():
    r = _run(_piston(), [{"type": "cruise", "distance_km": 1.0, "speed_m_s": 50, "heading_deg": 0}],
             initial={"altitude_m": 0},
             wind={"speed_m_s": 0, "turbulence": {"intensity": "light", "seed": 1},
                   "gusts": [{"t": 1, "amplitude_m_s": 4, "gradient_m": 30}]})
    assert r["aborted"] is None
    assert r["total_dist_km"] == pytest.approx(1.0, rel=1e-9)
    assert any("Dryden" in n or "rajada" in n for n in r["notes"])


# ---------------------------------------------------------------- performance identities
def test_cruise_fuel_matches_frozen_weight_burn():
    """One Euler step freezes the weight: ṁ = c_p·D·V/η, so fuel = c_p·D·distance/η (Anderson level flight)."""
    ac = _piston()
    plant = Plant.from_n0(ac)
    V, dist = 50.0, 4000.0
    W = ac["mass_kg"] * G0
    D, _cl = plant.drag_cl(W, V, 0.0, 1.0)
    expected = plant.c_p * D * dist / plant.eta_cruise
    seg = [{"type": "cruise", "distance_km": dist / 1000.0, "speed_m_s": V, "heading_deg": 0}]
    init = {"altitude_m": 0, "heading_deg": 0}
    one = _run(ac, seg, initial=init, pointmass_dt=1.0e6)
    assert one["aborted"] is None, one["aborted"]
    assert one["total_used_kg"] == pytest.approx(expected, rel=1e-6)
    small = _run(ac, seg, initial=init, pointmass_dt=1.0)
    assert small["total_used_kg"] == pytest.approx(expected, rel=1e-3)
    assert small["total_dist_km"] == pytest.approx(dist / 1000.0, rel=1e-9)


def test_climb_rate_matches_excess_power():
    ac = _electric(mass_kg=15, S_m2=0.8, CD0=0.03, K=0.045, CLmax=1.2,
                   propulsion={"P_sl_W": 800, "eta_cruise": 0.70, "eta_tot": 0.70, "P_systems_W": 0})
    plant = Plant.from_n0(ac)
    V, dh = 20.0, 40.0
    roc = plant.roc(ac["mass_kg"] * G0, V, 0.0)
    assert roc > 0.05
    r = _run(ac, [{"type": "climb", "to_altitude_m": dh, "speed_m_s": V}],
             initial={"altitude_m": 0, "heading_deg": 0})
    assert r["aborted"] is None, r["aborted"]
    assert r["segments"][0]["h1_m"] == pytest.approx(dh)
    assert r["total_time_min"] * 60.0 == pytest.approx(dh / roc, rel=1e-9)


def test_turn_time_is_heading_over_omega():
    V, n, dpsi = 50.0, 1.2, 180.0
    r = _run(_piston(), [{"type": "turn", "heading_change_deg": dpsi, "load_factor": n, "speed_m_s": V}],
             initial={"altitude_m": 0, "heading_deg": 0})
    assert r["aborted"] is None, r["aborted"]
    omega = G0 * math.sqrt(n * n - 1.0) / V
    assert r["total_time_min"] * 60.0 == pytest.approx(math.radians(dpsi) / omega, rel=1e-9)


def test_glide_range_is_height_times_ldmax():
    ac = _jet_glide()
    cd0, k, h = ac["CD0"], ac["K"], 1500.0
    ld = 1.0 / (2.0 * math.sqrt(cd0 * k))
    r = _run(ac, [{"type": "descent", "to_altitude_m": 0}], initial={"altitude_m": h, "heading_deg": 0})
    assert r["aborted"] is None, r["aborted"]
    assert r["total_dist_km"] * 1000.0 == pytest.approx(h * ld, rel=1e-6)
    assert r["segments"][0]["h1_m"] == pytest.approx(0.0, abs=1e-6)


def test_takeoff_distance_matches_raymer_and_landing_from_the_screen():
    from acdt.domains.aircraft.performance import landing_distance, takeoff_distance_integrated
    ac = _electric(mass_kg=800, S_m2=14, CD0=0.03, K=0.045, CLmax=1.6, CLmax_takeoff=1.8, CLmax_landing=2.0,
                   propulsion={"P_sl_W": 160000, "eta_cruise": 0.75, "eta_takeoff": 0.55, "eta_tot": 0.70,
                               "battery_Wh": 20000})
    plant = Plant.from_n0(ac)
    W = ac["mass_kg"] * G0
    to = takeoff_distance_integrated(plant.as_perf(), W, 0.0)
    r = _run(ac, [{"type": "takeoff"}], initial={"heading_deg": 0})
    assert r["aborted"] is None, r["aborted"]
    assert math.isfinite(r["total_time_min"]) and r["total_time_min"] > 0
    assert r["total_dist_km"] * 1000.0 == pytest.approx(to["total_50ft"], rel=1e-9)
    ld = landing_distance(plant.as_perf(), W, 0.0, 15.24, plant.mu_brake, 3.0)
    land = _run(ac, [{"type": "landing"}], initial={"altitude_m": 15.24, "heading_deg": 0})
    assert land["aborted"] is None, land["aborted"]
    assert math.isfinite(land["total_time_min"]) and land["total_time_min"] > 0
    assert land["total_dist_km"] * 1000.0 == pytest.approx(ld["total_50ft"], rel=1e-9)
    bare = _electric()
    del bare["propulsion"]["eta_takeoff"]
    with pytest.raises(ValueError, match="eta_takeoff"):
        _run(bare, [{"type": "takeoff"}])


# ---------------------------------------------------------------- sensors (core primitives, not a new model)
def test_straight_track_area_and_pod():
    from acdt.core.concept.search import pod
    h, fov, dist_km = 200.0, 60.0, 2.0
    swath = 2.0 * h * math.tan(math.radians(fov) / 2.0) / 1000.0
    r = _run(_electric(), [{"type": "cruise", "distance_km": dist_km, "speed_m_s": 30, "heading_deg": 90}],
             initial={"altitude_m": h},
             sensor={"fov_cross_deg": fov, "area_km2": 20.0})
    assert r["aborted"] is None, r["aborted"]
    assert r["sensor"]["swept_area_km2"] == pytest.approx(swath * dist_km, rel=1e-9)
    assert r["sensor"]["pod"]["pod_random_search"] == pytest.approx(pod(20.0, swath, dist_km)["pod_random_search"])
    assert r["metrics"]["area_swept_km2"] == pytest.approx(swath * dist_km, rel=1e-9)
    assert r["metrics"]["time_on_station_h"] == pytest.approx(0.0)


def test_persistent_cycle_matches_ops_cycle():
    from acdt.core.concept.ops import cycle
    r = _run(_electric(), [{"type": "cruise", "time_min": 12, "speed_m_s": 30, "on_station": True}],
             initial={"altitude_m": 200},
             sensor={"fov_cross_deg": 50, "persistent": {"t_out_h": 0.2, "t_back_h": 0.2, "turnaround_h": 0.5,
                                                         "reserve_h": 0.0}})
    assert r["aborted"] is None, r["aborted"]
    assert r["metrics"]["time_on_station_h"] == pytest.approx(0.2, rel=1e-9)
    got = r["sensor"]["persistent"]["cycle"]
    expect = cycle(0.6, 0.2, 0.2, 0.5, 0.0)
    assert got["aircraft_per_station"] == expect["aircraft_per_station"] == 6
    assert got["feasible"] is True


def test_sensor_loss_stops_area_growth():
    ac = _electric()
    seg = [{"type": "cruise", "time_min": 20.0 / 60.0, "speed_m_s": 30, "heading_deg": 0}]
    init = {"altitude_m": 200}
    sens = {"fov_cross_deg": 60}
    full = _run(ac, seg, initial=init, sensor=sens, pointmass_dt=1.0)
    lost = _run(ac, seg, initial=init, sensor=sens, pointmass_dt=1.0,
                failures={"events": [{"type": "sensor_loss", "t_s": 10.0, "response": "continue"}]})
    assert full["aborted"] is None and lost["aborted"] is None
    a_full, a_loss = full["sensor"]["swept_area_km2"], lost["sensor"]["swept_area_km2"]
    assert 0.0 < a_loss < 0.7 * a_full
    assert lost["failures"]["executed"] is True
    assert lost["failures"]["log"][0]["type"] == "sensor_loss"


# ---------------------------------------------------------------- failures
def _glide_plant():
    return _electric(mass_kg=100, S_m2=10, CD0=0.02, K=0.05, CLmax=1.2,
                     propulsion={"P_sl_W": 20000, "eta_cruise": 0.70, "eta_tot": 0.70, "P_systems_W": 0,
                                 "battery_Wh": 5000})


def test_engine_out_continue_glides_and_rtb_spirals():
    ac = _glide_plant()
    h = 1500.0
    ld = 1.0 / (2.0 * math.sqrt(ac["CD0"] * ac["K"]))
    seg = [{"type": "cruise", "time_min": 5, "speed_m_s": 30, "heading_deg": 0}]
    init = {"altitude_m": h, "heading_deg": 0}
    sim_c, cont = _fly(ac, seg, initial=init, failures={"events": [
        {"type": "engine_out", "t_s": 0, "response": "continue"}]})
    assert cont["aborted"] is None, cont["aborted"]
    assert sim_c.h == pytest.approx(0.0, abs=1e-3)
    assert sim_c.N == pytest.approx(h * ld, rel=1e-6)
    assert abs(sim_c.E) < 1.0
    assert cont["failures"]["log"][0]["response"] == "continue"
    rho = isa(h).rho
    W = ac["mass_kg"] * G0
    cl1 = math.sqrt(ac["CD0"] / ac["K"])
    V = math.sqrt(2.0 * W / (rho * ac["S_m2"] * cl1))
    n = 1.1
    R = V * V / (G0 * math.sqrt(n * n - 1.0))
    sim_r, rtb = _fly(ac, seg, initial=init, failures={"events": [
        {"type": "engine_out", "t_s": 0, "response": "rtb"}]})
    assert rtb["aborted"] is None, rtb["aborted"]
    assert sim_r.h == pytest.approx(0.0, abs=1e-3)
    assert math.hypot(sim_r.N, sim_r.E) == pytest.approx(R, rel=1e-4)
    assert rtb["failures"]["log"][0]["response"] == "rtb"
    assert rtb["failures"]["executed"] is True


def test_divert_from_low_altitude_misses_and_is_logged():
    ac = _glide_plant()
    sim, r = _fly(ac, [{"type": "cruise", "time_min": 2, "speed_m_s": 30}],
                  initial={"altitude_m": 100, "heading_deg": 0},
                  failures={"events": [{"type": "engine_out", "t_s": 0, "response": "divert",
                                        "divert_km": [40, 0]}]})
    assert r["aborted"] is None, r["aborted"]
    assert sim.h == pytest.approx(0.0, abs=1e-3)
    miss = math.hypot(40000.0 - sim.N, sim.E)
    assert miss > 10000.0
    assert any("solo" in n for n in r["notes"])
    assert r["failures"]["log"][0]["response"] == "divert"


def test_battery_factor_doubles_burn_and_clock_fires_on_the_trigger():
    ac = _electric(propulsion={"P_systems_W": 0, "payload_power_W": 0, "battery_Wh": 10000})
    seg = [{"type": "cruise", "time_min": 0.2, "speed_m_s": 30}]
    init = {"altitude_m": 200}
    base = _run(ac, seg, initial=init)
    deg = _run(ac, seg, initial=init, failures={"events": [
        {"type": "battery_degradation", "t_s": 0, "factor": 2, "response": "continue"}]})
    assert base["aborted"] is None and deg["aborted"] is None
    assert deg["total_used_Wh"] == pytest.approx(2.0 * base["total_used_Wh"], rel=1e-9)
    clock = _run(ac, [{"type": "cruise", "time_min": 0.5, "speed_m_s": 30}], initial=init, pointmass_dt=1.0,
                 failures={"events": [{"type": "link_loss", "t_s": 10.5, "response": "continue"}]})
    assert clock["failures"]["log"][0]["t_s"] == pytest.approx(10.5, abs=1e-6)
    shed = _run(ac, seg, initial=init, failures={"events": [
        {"type": "battery_degradation", "t_s": 0, "factor": 1, "remaining_fraction": 0.5, "response": "continue"}]})
    assert shed["unusable"] == pytest.approx(0.5 * 10000.0, rel=1e-9)


def test_seed_is_reproducible_and_catalogue_without_seed_is_refused():
    ac = _electric()
    cat = [{"type": "link_loss", "t_s": 0, "response": "continue", "weight": 1},
           {"type": "sensor_loss", "t_s": 0, "response": "continue", "weight": 3}]
    seed = 7
    pick = random.Random(seed).choices(range(2), weights=[1, 3], k=1)[0]
    kw = dict(initial={"altitude_m": 200}, sensor={"fov_cross_deg": 40},
              failures={"catalogue": cat, "seed": seed})
    a = _run(ac, [{"type": "cruise", "time_min": 0.05, "speed_m_s": 30}], **kw)
    b = _run(ac, [{"type": "cruise", "time_min": 0.05, "speed_m_s": 30}], **kw)
    assert a["failures"]["log"][0]["type"] == b["failures"]["log"][0]["type"] == cat[pick]["type"]
    assert a["failures"]["seed"] == seed
    with pytest.raises(ValueError, match="seed"):
        _run(ac, [{"type": "cruise", "time_min": 0.05, "speed_m_s": 30}],
             failures={"catalogue": cat})


def test_schema_errors_and_payload_without_generator():
    with pytest.raises(ValueError, match="desconhecido"):
        _run(_electric(), [{"type": "hover", "time_min": 1}])
    with pytest.raises(ValueError, match="desconhecida"):
        _run(_electric(), [{"type": "cruise", "time_min": 0.1, "speed_m_s": 30}],
             failures={"events": [{"type": "wing_off", "t_s": 0}]})
    with pytest.raises(ValueError, match="engines_out"):
        _run(_electric(), [{"type": "cruise", "time_min": 0.1, "speed_m_s": 30}],
             initial={"altitude_m": 200},
             failures={"events": [{"type": "engine_out", "t_s": 0, "engines_out": 3, "response": "continue"}]})
    fuel = _piston()
    fuel["propulsion"]["payload_power_W"] = 200
    with pytest.raises(ValueError, match="generator_efficiency"):
        Plant.from_n0(fuel)
    with pytest.raises(ValueError, match="pointmass_dt"):
        _run(_electric(), [{"type": "cruise", "time_min": 0.1, "speed_m_s": 30}], pointmass_dt=1e-6)


def test_link_loss_continue_does_not_change_the_track():
    ac = _electric()
    seg = [{"type": "cruise", "distance_km": 1.0, "speed_m_s": 30, "heading_deg": 0}]
    init = {"altitude_m": 200}
    plain = _run(ac, seg, initial=init)
    lost = _run(ac, seg, initial=init, failures={"events": [
        {"type": "link_loss", "t_s": 0, "response": "continue"}]})
    assert lost["aborted"] is None
    assert lost["total_dist_km"] == pytest.approx(plain["total_dist_km"], rel=1e-12)
    assert lost["total_time_min"] == pytest.approx(plain["total_time_min"], rel=1e-12)
    assert "ligação" in lost["failures"]["log"][0]["action"]


# ---------------------------------------------------------------- example, CLI, MCP, 6-DOF hook
def test_example_yaml_loads_and_flies(tmp_path):
    ms = load_mission(EXAMPLE)
    assert any(s["type"] == "patrol" for s in ms["segments"])
    assert ms["aircraft"]["mass_kg"] == 15
    r = simulate_pointmass_mission(EXAMPLE, tmp_path)
    assert r["aborted"] is None, r["aborted"]
    assert r["fidelity"] == "pointmass" and r["aircraft_source"] == "n0"
    assert "1999" in r["method"] and "2018" in r["method"]
    assert r["metrics"]["time_on_station_h"] > 0
    assert r["metrics"]["area_swept_km2"] > 0
    assert any("η_tot" in n or "eta" in n.lower() or "> 1" in n for n in r["notes"])
    for name in ("summary_json", "history_csv", "time_history", "ground_track"):
        assert Path(r["files"][name]).is_file()


def test_cli_pointmass_and_6dof_arity(tmp_path):
    from acdt.cli import main
    assert main(["simulate", str(EXAMPLE), "--fidelity", "pointmass", "-o", str(tmp_path / "ok")]) == 0
    assert main(["simulate", str(EXAMPLE), "--fidelity", "6dof"]) == 2
    bad = tmp_path / "bad.yaml"
    bad.write_text("name: x\naircraft: {mass_kg: 1, source: t}\nsegments: [{type: cruise, time_min: 1}]\n",
                   encoding="utf-8")
    assert main(["simulate", str(bad), "--fidelity", "pointmass", "-o", str(tmp_path / "bad")]) == 2
    slow = tmp_path / "stall.yaml"
    slow.write_text(
        "name: stall\npointmass_dt: 5\ninitial: {altitude_m: 100}\n"
        "aircraft:\n  source: t\n  mass_kg: 1000\n  S_m2: 16\n  CD0: 0.03\n  K: 0.05\n  CLmax: 1.4\n"
        "  propulsion: {kind: electric, P_sl_W: 80000, eta_cruise: 0.7, eta_takeoff: 0.5, eta_tot: 0.7}\n"
        "segments: [{type: cruise, time_min: 1, speed_m_s: 5}]\n", encoding="utf-8")
    assert main(["simulate", str(slow), "--fidelity", "pointmass", "-o", str(tmp_path / "stall")]) == 1


def test_mcp_schema_exposes_fidelity():
    import anyio
    from mcp import Client
    from acdt.ai.mcp_server import build_server

    async def schema():
        async with Client(build_server()) as c:
            tools = (await c.list_tools()).tools
            return next(t for t in tools if t.name == "simulate_mission")
    tool = anyio.run(schema)
    schema_obj = getattr(tool, "input_schema", None)
    if schema_obj is None:
        schema_obj = tool.inputSchema
    if hasattr(schema_obj, "model_dump"):
        schema_obj = schema_obj.model_dump()
    props = schema_obj["properties"]
    assert "fidelity" in props and "aircraft" in props
    assert "pointmass" in (props["fidelity"].get("description") or "")


def test_toolkit_n0_does_not_use_sizing_defaults(tmp_path, monkeypatch):
    from acdt.ai import registry
    from acdt.ai import toolkit as T
    monkeypatch.setenv("ACDT_RUNS_DIR", str(tmp_path / "runs"))
    ms = {"name": "n0", "pointmass_dt": 10, "initial": {"altitude_m": 200},
          "segments": [{"type": "cruise", "distance_km": 0.4, "speed_m_s": 30}],
          "aircraft": _electric()}
    r = T.simulate_mission(fidelity="pointmass", mission=ms)
    assert r["status"] == "done", r
    assert r["summary"]["fidelity"] == "pointmass"
    assert r["summary"]["aborted"] is None
    assumptions = registry.load(r["run_id"]).record["assumptions"]
    blob = " ".join(str(a) for a in assumptions)
    assert "não usados" in blob and "DEFAULT_ASSUMPTIONS" in blob
    with pytest.raises(T.ToolError):
        T.simulate_mission(fidelity="pointmass", mission={"name": "x", "segments": [
            {"type": "cruise", "time_min": 0.1, "speed_m_s": 30}]})


def test_6dof_hook_logs_failures_without_flying_them():
    import numpy as np
    from acdt.domains.aircraft.flightsim.mission import MissionRunner
    from acdt.domains.aircraft.flightsim.sensors import products_for_6dof
    cols = MissionRunner.COLS
    C = {k: i for i, k in enumerate(cols)}

    def row(t, n, seg):
        r = np.zeros(len(cols))
        r[C["t"]], r[C["N"]], r[C["E"]], r[C["h"]], r[C["Va"]], r[C["seg"]] = t, n, 0.0, 200.0, 40.0, seg
        return r

    H = np.vstack([row(0, 0, 0), row(5, 200, 0), row(10, 400, 0), row(20, 800, 0)])
    result = {"_H": H, "history_columns": cols, "segments": [{"type": "cruise", "t_min": 20 / 60}],
              "total_time_min": 20 / 60, "total_dist_km": 0.8}
    mission = {"sensor": {"fov_cross_deg": 60},
               "failures": {"events": [{"type": "sensor_loss", "t_s": 10, "response": "rtb"}]}}
    extra = products_for_6dof(mission, result)
    assert extra["failures"]["executed"] is False
    assert "não aplicada" in extra["failures"]["log"][0]["action"]
    assert extra["sensor"]["swept_area_km2"] > 0
    # the sample at the trigger is already off, so the swept area is only the leg that ended before it
    full = products_for_6dof({"sensor": mission["sensor"]}, result)
    assert extra["sensor"]["swept_area_km2"] < full["sensor"]["swept_area_km2"]


# ---------------------------------------------------------------- N1 and the short 6-DOF comparison (AVL)
@pytest.mark.requires_avl
def test_n1_pointmass_from_sizing(c172_result):
    r = simulate_pointmass_mission(
        {"name": "n1", "pointmass_dt": 1.0e6, "initial": {"altitude_m": 1000, "heading_deg": 0},
         "segments": [{"type": "cruise", "distance_km": 5, "speed_m_s": 50, "heading_deg": 0}]},
        res=c172_result)
    assert r["aborted"] is None, r["aborted"]
    assert r["aircraft_source"] == "sizing"
    assert r["total_dist_km"] == pytest.approx(5.0, rel=1e-9)
    assert any("modelo de voo" in n for n in r["notes"])


@pytest.mark.requires_avl
def test_consistency_pointmass_6dof(c172_result):
    """One light cruise. Range, endurance, specific range and specific endurance within TOL."""
    from acdt.domains.aircraft.flightsim.aeromodel import build_flight_model
    from acdt.domains.aircraft.flightsim.mission import simulate_mission_6dof
    fm = build_flight_model(c172_result)
    ms = {"name": "consistencia", "dt": 0.02, "extrapolate_after_s": 120, "pointmass_dt": 1.0,
          "initial": {"altitude_m": 600, "speed_m_s": 50, "heading_deg": 0},
          "segments": [{"type": "cruise", "time_min": 0.4, "speed_m_s": 50, "heading_deg": 0}],
          "sensor": {"fov_cross_deg": 40, "on_station_segments": ["cruise"]}}
    pm = simulate_pointmass_mission(ms, fm=fm)
    dof = simulate_mission_6dof(fm, ms, hq=False)
    assert pm["aborted"] is None, pm["aborted"]
    assert dof["aborted"] is None, dof["aborted"]
    assert pm["aircraft_source"] == "flight_model"
    assert "sensor" in pm and "sensor" in dof

    def rel(a, b):
        return abs(a - b) / max(abs(b), 1e-12)

    unit = pm["unit"]
    used_pm = pm["total_used_" + unit]
    used_dof = dof["total_used_" + unit]
    numbers = (f"dist km pm {pm['total_dist_km']:.6f} 6dof {dof['total_dist_km']:.6f}; "
               f"time min pm {pm['total_time_min']:.6f} 6dof {dof['total_time_min']:.6f}; "
               f"used {unit} pm {used_pm:.6g} 6dof {used_dof:.6g}")
    assert rel(pm["total_dist_km"], dof["total_dist_km"]) < TOL, numbers
    assert rel(pm["total_time_min"], dof["total_time_min"]) < TOL, numbers
    assert used_pm > 0 and used_dof > 0, numbers
    sr_pm, sr_dof = pm["total_dist_km"] / used_pm, dof["total_dist_km"] / used_dof
    se_pm, se_dof = pm["total_time_min"] / used_pm, dof["total_time_min"] / used_dof
    detail = (numbers + f"; specific range {sr_pm:.6g} vs {sr_dof:.6g}; "
              f"specific endurance {se_pm:.6g} vs {se_dof:.6g}")
    assert rel(sr_pm, sr_dof) < TOL, detail
    assert rel(se_pm, se_dof) < TOL, detail
