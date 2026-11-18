"""Barrier / barrier-patrol search (Koopman 1946/1980; Washburn 2002) on coverage primitives."""
from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

from acdt.ai import concept as C
from acdt.core.concept import search

EX = Path(__file__).resolve().parents[1] / "examples" / "concept"
DEMO = EX / "barrier_patrol_demo.json"
NO_W = EX / "barrier_unassessed_width.json"


def test_barrier_coverage_factor_hand_calc():
    # L=100 km, W=10 km, V=50 m/s = 180 km/h, u=5 m/s = 18 km/h, n=1
    # z = 10*180/(100*18) = 1.0
    r = search.barrier_coverage_factor(100.0, 10.0, 50.0, 5.0, 1.0)
    assert r["coverage_factor"] == pytest.approx(1.0)
    assert r["pod_random_search"] == pytest.approx(1 - math.exp(-1))
    assert r["pod_parallel_sweep"] == pytest.approx(1.0)


def test_barrier_revisit_and_close():
    # L=72 km, V=40 m/s = 144 km/h, n=1 → τ = 2*72/144 = 1.0 h
    rev = search.barrier_revisit(72.0, 40.0, 1.0)
    assert rev["revisit_h"] == pytest.approx(1.0)
    cl = search.barrier_close(72.0, 40.0, crossing_window_h=1.2, n_on_station=1.0)
    assert cl["closed"] is True
    assert cl["n_to_close"] == 1
    assert cl["L_max_closed_km"] == pytest.approx(144.0 * 1.2 / 2.0)
    cl2 = search.barrier_close(200.0, 40.0, 1.2, 1.0)
    assert cl2["closed"] is False
    assert cl2["n_to_close"] == math.ceil(2 * 200 / (144 * 1.2))


def test_barrier_search_full_demo_numbers():
    spec = json.loads(DEMO.read_text(encoding="utf-8"))
    kw = {k: v for k, v in spec.items() if not k.startswith("_")}
    r = C.barrier_search(**kw)
    assert r["fully_assessed"] is True
    assert r["revisit"]["status"] == "assessed"
    assert r["close"]["status"] == "assessed"
    assert r["pod"]["status"] == "assessed"
    assert r["continuous"]["status"] == "assessed"
    # τ = 2*80/(1*144) = 160/144 ≈ 1.111 h ≤ 1.2 → closed
    assert r["revisit"]["revisit_h"] == pytest.approx(160.0 / 144.0)
    assert r["close"]["closed"] is True
    # z = 1*20.4*144/(80*5.144*3.6)
    V, u = 40 * 3.6, 5.144 * 3.6
    z = 20.4 * V / (80.0 * u)
    assert r["pod"]["coverage_factor"] == pytest.approx(z)
    assert r["pod"]["pod_random_search"] == pytest.approx(1 - math.exp(-z))
    assert r["continuous"]["aircraft_needed_in_cycle"] >= 1
    assert not r["unassessed"]


def test_missing_sweep_width_pod_unassessed_not_pass():
    spec = json.loads(NO_W.read_text(encoding="utf-8"))
    kw = {k: v for k, v in spec.items() if not k.startswith("_")}
    r = C.barrier_search(**kw)
    assert r["pod"]["status"] == "unassessed"
    assert r["close"]["status"] == "assessed"  # revisit/close do not need W
    assert r["close"]["closed"] is True
    assert any(u["metric"] == "pod" for u in r["unassessed"])
    assert r["fully_assessed"] is False


def test_missing_speed_everything_needed_unassessed():
    r = C.barrier_search(barrier_length_km=80.0, crossing_window_h=1.2, sweep_width_km=20.0,
                         evader_speed_m_s=5.0)
    assert r["revisit"]["status"] == "unassessed"
    assert r["pod"]["status"] == "unassessed"
    assert r["fully_assessed"] is False
    metrics = {u["metric"] for u in r["unassessed"]}
    assert "revisit_and_close" in metrics and "pod" in metrics


def test_corridor_derives_window():
    # corridor 12 NM = 22.224 km, 10 kn = 5.144 m/s → T ≈ 1.20 h
    r = C.barrier_search(barrier_length_km=50.0, speed_m_s=40.0, sweep_width_km=10.0,
                         evader_speed_m_s=5.144, corridor_width_km=22.224, n_on_station=1.0)
    assert r["crossing_window_h"] == pytest.approx(22.224 / (5.144 * 3.6), rel=1e-6)
    assert r["crossing_window_source"] == "corridor_width_km / evader_speed"
    assert r["close"]["status"] == "assessed"


def test_continuous_without_endurance_unassessed():
    r = C.barrier_search(barrier_length_km=80.0, speed_m_s=40.0, turnaround_h=2.0, distance_km=162.0)
    assert any(u["metric"] == "continuous_barrier_fleet" for u in r["unassessed"])
    assert r["continuous"]["status"] == "unassessed"


def test_sweep_coverage_unchanged_without_barrier_mode():
    """Backward compatible: existing sweep_coverage API/result keys untouched."""
    r = C.sweep_coverage(area_km2=1000, sweep_width_km=10, speed_m_s=100 / 3.6, time_h=1.0)
    assert "sweep_rate_km2_h" in r and "pod_at_time" in r
    assert "barrier" not in r and "unassessed" not in r


def test_cli_barrier_demo(tmp_path):
    r = subprocess.run(
        [sys.executable, "-m", "acdt.cli", "concept", "barrier",
         "--input", str(DEMO), "-o", str(tmp_path / "out.json")],
        capture_output=True, text=True,
        env={**dict(__import__("os").environ), "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
    )
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))
    assert out["close"]["closed"] is True
    assert out["fully_assessed"] is True


def test_cli_barrier_unassessed_exit_3(tmp_path):
    r = subprocess.run(
        [sys.executable, "-m", "acdt.cli", "concept", "barrier",
         "--input", str(NO_W), "-o", str(tmp_path / "out.json")],
        capture_output=True, text=True,
        env={**dict(__import__("os").environ), "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
    )
    assert r.returncode == 3, r.stdout + r.stderr
    assert "unassessed" in r.stdout.lower()


def test_mcp_registers_barrier_search():
    names = set()
    # concept_mcp.register uses FastMCP-like API; assert the function exists and REPLAYABLE includes it
    assert "barrier_search" in C.REPLAYABLE
    assert hasattr(C, "barrier_search")
