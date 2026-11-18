"""VTOL / eVTOL L0: momentum theory, sizing, architecture compare, CLI JSON."""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

from acdt.ai import vtol as V
from acdt.domains.aircraft.vtol import (climb_power, compare_architectures, hover_point, hover_power,
                                        ideal_hover_power, induced_velocity_forward, induced_velocity_hover,
                                        size_vtol)

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples" / "vtol"


def test_ideal_hover_power_analytic():
    # T = 100 N, rho = 1.225, A = 1 m² → P = 100^1.5 / sqrt(2.45)
    P = ideal_hover_power(100.0, 1.225, 1.0)
    assert P == pytest.approx(1000.0 / math.sqrt(2.45), rel=1e-12)
    # P_ideal = T v_h
    assert P == pytest.approx(100.0 * induced_velocity_hover(100.0, 1.225, 1.0), rel=1e-12)


def test_scaling_fm_disk_area_thrust():
    T, rho, A = 200.0, 1.2, 0.5
    assert hover_power(T, rho, A, 0.5) / hover_power(T, rho, A, 0.8) == pytest.approx(0.8 / 0.5)
    assert ideal_hover_power(T, rho, 4 * A) == pytest.approx(ideal_hover_power(T, rho, A) / 2)
    assert ideal_hover_power(4 * T, rho, A) == pytest.approx(8 * ideal_hover_power(T, rho, A))
    with pytest.raises(ValueError):
        hover_power(T, rho, A, 0.0)


def test_climb_and_forward_limits():
    T, rho, A = 150.0, 1.225, 0.3
    assert climb_power(T, rho, A, 0.0, 1.0) == pytest.approx(ideal_hover_power(T, rho, A))
    assert climb_power(T, rho, A, 3.0, 1.0) > ideal_hover_power(T, rho, A)
    vh = induced_velocity_hover(T, rho, A)
    assert induced_velocity_forward(T, rho, A, 0.0) == pytest.approx(vh)
    V = 30.0  # Glauert: v_i = v_h² / sqrt(V² + v_i²)
    vi = induced_velocity_forward(T, rho, A, V)
    assert vi == pytest.approx(vh ** 2 / math.sqrt(V ** 2 + vi ** 2), rel=1e-10)
    assert induced_velocity_forward(T, rho, A, 300.0) == pytest.approx(vh ** 2 / 300.0, rel=0.01)


def test_hover_point_diameter_vs_disk_loading():
    a = hover_point(5.0, 4, diameter_m=0.4)
    b = hover_point(5.0, 4, disk_loading_N_m2=a["disk_loading_N_m2"])
    assert b["diameter_m"] == pytest.approx(0.4)
    assert b["P_hover_shaft_W"] == pytest.approx(a["P_hover_shaft_W"])
    assert a["P_hover_shaft_W"] == pytest.approx(a["P_ideal_W"] / 0.70)


def test_size_energy_and_battery():
    spec = {"architecture": "multirotor", "mass_kg": 5.0, "rotors": {"n": 4, "diameter_m": 0.38, "FM": 0.7},
            "mission": {"t_hover_s": 600}, "electric": {"eta_motor": 0.85, "eta_esc": 0.95, "pack_Wh_kg": 200,
                                                        "reserve": 0.2, "dod": 0.8, "c_rate_max": 50}}
    r = size_vtol(spec)
    P_e = r["hover"]["P_hover_shaft_W"] / (0.85 * 0.95)
    assert r["energy_Wh"] == pytest.approx(P_e * 600 / 3600)
    assert r["battery_mass_kg"] == pytest.approx(r["energy_Wh"] * 1.2 / 0.8 / 200)
    assert r["battery_limiting"] == "energy"
    assert "rotors.solidity" in r["pressupostos"] and "rotors.FM" not in r["pressupostos"]
    assert r["citations"] and any("Johnson" in c for c in r["citations"])
    # low C-rate → power-limited pack
    spec["electric"]["c_rate_max"] = 1.0
    assert size_vtol(spec)["battery_limiting"] == "power"


def test_transition_present_only_for_winged():
    base = {"mass_kg": 20.0, "mission": {"t_hover_s": 60, "cruise_distance_m": 20000, "cruise_speed_m_s": 20}}
    mr = size_vtol({**base, "architecture": "multirotor"})
    lc = size_vtol({**base, "architecture": "lift_cruise"})
    assert mr["transition"]["n"] == 0
    assert lc["transition"]["n"] == 2 and 0.2 < lc["transition"]["power_factor"] < 1.5
    assert lc["transition"]["envelope"][-1]["rotor_thrust_N"] == pytest.approx(0.0, abs=1e-9)
    ov = size_vtol({**base, "architecture": "lift_cruise", "transition": {"power_factor": 1.0}})
    assert ov["transition"]["P_avg_shaft_W"] == pytest.approx(ov["hover"]["P_hover_shaft_W"])


def test_compare_ranks_architectures():
    spec = V.load_spec(EX / "lift_cruise_25kg.yaml")
    out = compare_architectures(spec, spec["compare"], spec["overrides"])
    archs = [r["architecture"] for r in out["rows"]]
    assert archs == ["multirotor", "lift_cruise", "tilt_rotor"]
    # 40 km cruise: winged architectures need less energy than edgewise multirotor
    E = {r["architecture"]: r["energy_Wh"] for r in out["rows"]}
    assert E["lift_cruise"] < E["multirotor"] and E["tilt_rotor"] < E["multirotor"]
    # higher disk loading (tilt-rotor default) → more hover power
    P = {r["architecture"]: r["P_hover_kW"] for r in out["rows"]}
    assert P["tilt_rotor"] > P["multirotor"]
    assert out["lightest_battery"] in archs
    json.dumps(out)  # JSON-serialisable


@pytest.mark.parametrize("args", [
    ["hover", "--mass", "5", "--diameter", "0.38"],
    ["size", "--input", str(EX / "quadrotor_inspection.json")],
    ["compare", "--input", str(EX / "lift_cruise_25kg.yaml")],
])
def test_cli_json(tmp_path, args):
    out = tmp_path / "v.json"
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    r = subprocess.run([sys.executable, "-m", "acdt.cli", "vtol", *args, "-o", str(out)],
                       cwd=ROOT, capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr + r.stdout
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data


def test_catalogue_lists_vtol():
    from acdt.ai import catalogue
    m = catalogue.methods()
    assert any(w["stage"].startswith("VTOL") for w in m["workflow"])
    mods = {x["module"]: x for x in m["modules"]}
    assert "acdt.domains.aircraft.vtol.momentum" in mods
    assert any("1980" in ref for ref in mods["acdt.domains.aircraft.vtol.momentum"]["references"])
