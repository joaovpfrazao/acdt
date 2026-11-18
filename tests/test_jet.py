# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Jet L0: classical equations, reference sanity, CLI/JSON and real MCP wiring."""
import copy
import json
import math
import os
from pathlib import Path
import subprocess
import sys

import pytest

from acdt import G0
from acdt.ai import jet as J
from acdt.core.atmosphere import isa
from acdt.domains.aircraft.jet import wave_drag, turbofan_point, flight_envelope, analyse_jet, check_reference
from acdt.domains.aircraft.weights import LB

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples" / "jet"


def test_korn_unswept_and_lock_slope():
    # Mason 2006 Eq. 7-3: supercritical kappa=.95, CL=.5, t/c=.12 -> Mdd=.78.
    r = wave_drag(0.78, sweep_deg=0)
    assert r["M_dd"] == pytest.approx(0.78)
    assert r["M_crit"] == pytest.approx(0.78-(0.1/80)**(1/3))
    assert r["dCD_dMach"] == pytest.approx(0.1)
    assert wave_drag(r["M_crit"], sweep_deg=0)["CD_wave"] == 0
    eps = 1e-6
    slope = (wave_drag(.78+eps, sweep_deg=0)["CD_wave"]-
             wave_drag(.78-eps, sweep_deg=0)["CD_wave"])/(2*eps)
    assert slope == pytest.approx(0.1, rel=1e-7)


def test_sweep_formula_and_trends():
    r = wave_drag(.79)
    c = math.cos(math.radians(25))
    assert r["M_dd"] == pytest.approx(.95/c-.12/c**2-.5/(10*c**3))
    assert wave_drag(.79, thickness_ratio=.15)["M_dd"] < r["M_dd"]
    assert wave_drag(.79, cl=.8)["M_dd"] < r["M_dd"]
    assert wave_drag(.79, technology_factor=.87)["M_dd"] < r["M_dd"]
    assert wave_drag(.85)["CD_wave"] > r["CD_wave"]


def test_engine_analytic_and_units():
    r = turbofan_point(0, 0, 100000, installation_factor=1)
    assert r["thrust_installed_N"] == pytest.approx(100000)
    # Ihme 2025 Eq. 2.77 at M=0, ISA SLS: .4 lbm/(lbf h).
    assert r["TSFC_kg_N_s"] == pytest.approx(.4/(G0*3600))
    assert r["fuel_flow_kg_s"] == pytest.approx(100000*.4/(G0*3600))
    installed = turbofan_point(0, 0, 100000, installation_factor=.9)
    assert installed["thrust_installed_N"] == pytest.approx(90000)
    assert installed["TSFC_kg_N_s"] == r["TSFC_kg_N_s"]  # already installed TSFC


@pytest.mark.parametrize("mach", [0, .2, .5, .78, .9])
def test_thrust_altitude_lapse_monotonic(mach):
    thrusts = [turbofan_point(mach, h)["thrust_installed_N"] for h in (0, 1000, 5000, 11000, 15000)]
    assert all(a > b > 0 for a, b in zip(thrusts, thrusts[1:]))


def test_engine_mach_lapse_and_ram_recovery():
    # Initial Mach lapse; no false globally monotonic constraint on Mattingly ram-pressure law.
    assert turbofan_point(0, 11000)["thrust_installed_N"] > turbofan_point(.2, 11000)["thrust_installed_N"]
    assert turbofan_point(.2, 11000)["thrust_installed_N"] > turbofan_point(.4, 11000)["thrust_installed_N"]
    assert turbofan_point(.78, 11000)["thrust_installed_N"] > turbofan_point(.4, 11000)["thrust_installed_N"]
    assert turbofan_point(.78, 11000)["TSFC_kg_N_s"] > turbofan_point(.2, 11000)["TSFC_kg_N_s"]
    # Exact non-temperature-limited branch, no omitted ram factor.
    m = .78
    expected = isa(11000).p/101325*(1+.2*m*m)**3.5*(1-.49*math.sqrt(m))*.97*120000
    assert turbofan_point(m, 11000)["thrust_installed_N"] == pytest.approx(expected)
    # Temperature-limited branch at SLS M=.9.
    r = turbofan_point(.9, 0)
    expected_alpha = r["delta0"]*(1-.49*math.sqrt(.9)-3*(r["theta0"]-1.05)/2.4)
    assert r["thrust_lapse_uninstalled"] == pytest.approx(expected_alpha)


def test_vn_exact_corners_and_units():
    r = flight_envelope(77000, 122.6, 160)
    assert r["n_limit_positive"] == 2.5
    assert r["VA_eas_m_s"] == pytest.approx(r["VS1_eas_m_s"]*math.sqrt(2.5))
    assert r["VD_eas_m_s"] == 200
    def at(v):
        return next(p for p in r["points"] if p["V_eas_m_s"] == v)
    assert at(0)["n_positive"] == at(0)["n_negative"] == 0
    assert at(r["VS1_eas_m_s"])["n_positive"] == pytest.approx(1)
    assert at(r["VA_eas_m_s"])["n_positive"] == pytest.approx(2.5)
    assert at(160)["n_negative"] == -1
    assert at(180)["n_negative"] == pytest.approx(-.5)
    assert at(200)["n_negative"] == 0
    assert at(200)["n_positive"] == 2.5
    small = flight_envelope(1500, 20, 100)
    assert small["n_limit_positive"] == pytest.approx(min(3.8, 2.1+24000/(1500/LB+10000)))
    with pytest.raises(ValueError, match="VA"):
        flight_envelope(77000, 122.6, 80)


@pytest.mark.parametrize("fn,kwargs", [
    (wave_drag, {"mach": float("nan")}), (wave_drag, {"mach": .95}),
    (wave_drag, {"mach": .8, "sweep_deg": 80}), (wave_drag, {"mach": .8, "cl": -1}),
    (turbofan_point, {"mach": .8, "altitude_m": -1}),
    (turbofan_point, {"mach": .8, "altitude_m": 16000}),
    (turbofan_point, {"mach": .8, "altitude_m": 11000, "installation_factor": 0}),
    (flight_envelope, {"mass_kg": -1, "wing_area_m2": 122, "vc_eas_m_s": 160}),
    (flight_envelope, {"mass_kg": 77000, "wing_area_m2": 122, "vc_eas_m_s": 160, "vd_ratio": 1.1}),
])
def test_invalid_inputs(fn, kwargs):
    with pytest.raises(ValueError):
        fn(**kwargs)


def test_reference_mass_budget_and_roundtrip(tmp_path):
    ref = J.load_spec(EX / "a320_ref.json")
    original = copy.deepcopy(ref)
    r = check_reference(ref)
    assert ref == original  # no mutation
    assert all(c["passed"] for c in r["checks"]), r["issues"]
    assert r["weights"]["empty_fraction"] == pytest.approx(1.02*(77000/LB)**(-.06))
    assert r["weights"]["empty_mass_kg"] == pytest.approx(38133.0373, rel=1e-6)
    assert r["reference"]["published"]["oew_kg"] == 42175
    assert r["reference"]["sources"][0]["retrieved"] == "2026-11-06"
    assert .75 < r["wave_drag"]["M_dd"] < .9
    w = r["weights"]
    assert w["empty_mass_kg"]+w["fuel_mass_kg"]+w["remaining_payload_kg"]+800 == pytest.approx(77000)
    assert 12 < r["cruise"]["L_D"] < 22
    assert json.loads(json.dumps(r, allow_nan=False)) == r
    path = tmp_path/"ref.json"
    path.write_text(json.dumps(ref))
    assert J.jet_check(str(path)) == r
    assert J.jet_analyse(EX/"transport_l0.yaml")["weights"] == w


def test_analysis_failed_checks_and_input_rejection():
    spec = J.load_spec(EX/"transport_l0.yaml")
    spec["thrust_sl_N"] = 10000
    r = analyse_jet(spec)
    assert "cruise_thrust" in r["issues"]
    assert r["checks"][0]["margin_N"] < 0
    spec["range_m"] = 2e7
    assert "mass_budget" in analyse_jet(spec)["issues"]
    spec["n_engines"] = 2.5
    with pytest.raises(ValueError, match="integer"):
        analyse_jet(spec)
    with pytest.raises(ValueError, match="missing"):
        analyse_jet({})


@pytest.mark.parametrize("args", [
    ["wave-drag", "--mach", ".79"],
    ["turbofan", "--mach", ".79", "--altitude", "11000"],
    ["loads", "--mass", "77000", "--area", "122.6", "--vc", "160"],
    ["analyse", "--input", str(EX/"transport_l0.yaml")],
    ["check", "--input", str(EX/"a320_ref.json")],
])
def test_cli_json(tmp_path, args):
    output = tmp_path/"nested"/"jet.json"
    run = subprocess.run([sys.executable, "-m", "acdt.cli", "jet", *args, "-o", str(output)],
                         cwd=ROOT, text=True, capture_output=True,
                         env={**os.environ, "PYTHONPATH": str(ROOT/"src")})
    assert run.returncode == 0, run.stderr+run.stdout
    assert json.loads(output.read_text()) == json.loads(run.stdout)


def test_cli_validation_and_failed_check_exit_codes(tmp_path):
    env = {**os.environ, "PYTHONPATH": str(ROOT/"src")}
    command = [sys.executable, "-m", "acdt.cli", "jet"]
    bad = subprocess.run(command+["wave-drag", "--mach", "nan"], cwd=ROOT, env=env, capture_output=True, text=True)
    assert bad.returncode == 2
    spec = J.load_spec(EX/"transport_l0.yaml")
    spec["thrust_sl_N"] = 10000
    path, output = tmp_path/"bad.json", tmp_path/"out.json"
    path.write_text(json.dumps(spec))
    fail = subprocess.run(command+["analyse", "--input", str(path), "-o", str(output)],
                          cwd=ROOT, env=env, capture_output=True, text=True)
    assert fail.returncode == 1
    assert "cruise_thrust" in json.loads(output.read_text())["issues"]


def test_catalogue_and_mcp_registration():
    from acdt.ai import catalogue, jet_mcp
    methods = catalogue.methods()
    workflow = next(w for w in methods["workflow"] if w["stage"].startswith("subsonic jet"))
    assert set(workflow["tools"]) == {"jet_wave_drag", "jet_turbofan", "jet_loads", "jet_analyse", "jet_check", "jet_size", "jet_performance", "jet_weights"}
    modules = {m["module"]: m for m in methods["modules"]}
    assert any("2006" in ref for ref in modules["acdt.domains.aircraft.jet.wave_drag"]["references"])
    class Server:
        def __init__(self): self.tools = {}
        def tool(self, name, annotations):
            def decorate(fn):
                self.tools[name] = fn
                return fn
            return decorate
    server = Server()
    async def call(fn, *args): return fn(*args)
    jet_mcp.register(server, lambda *args: None, call)
    assert set(workflow["tools"]) == set(server.tools)
    import asyncio
    r = asyncio.run(server.tools["jet_wave_drag"](.78, sweep_deg=0))
    assert r["M_dd"] == pytest.approx(.78)


def test_real_mcp_tools():
    pytest.importorskip("mcp")
    import anyio
    from acdt.ai.mcp_server import build_server
    from mcp import Client
    async def go():
        async with Client(build_server()) as client:
            names = {t.name for t in (await client.list_tools()).tools}
            assert {"jet_wave_drag", "jet_turbofan", "jet_loads", "jet_analyse", "jet_check", "jet_size", "jet_performance", "jet_weights"} <= names
            cases = [("jet_wave_drag", {"mach": .78, "sweep_deg": 0}, "M_dd"),
                     ("jet_turbofan", {"mach": .78, "altitude_m": 11000}, "TSFC_kg_N_s"),
                     ("jet_loads", {"mass_kg": 77000, "wing_area_m2": 122.6, "vc_eas_m_s": 160}, "points"),
                     ("jet_analyse", {"spec": J.load_spec(EX/"transport_l0.yaml")}, "weights"),
                     ("jet_check", {"reference": J.load_spec(EX/"a320_ref.json")}, "reference")]
            for tool, args, key in cases:
                result = await client.call_tool(tool, args)
                assert not result.is_error, result
                data = getattr(result, "structured_content", None) or getattr(result, "structuredContent", None)
                assert key in data
    anyio.run(go)
