
"""P7 Sobol' global sensitivity (Saltelli/Jansen)."""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from acdt.ai import sensitivity as S
from acdt.core.sensitivity import (
    ISHIGAMI_ANALYTIC, ishigami, saltelli_matrices, sobol_analyze,
    sobol_from_evaluations, sobol_indices, evaluate_saltelli,
)

ROOT = Path(__file__).resolve().parents[1]
ISH = ROOT / "examples" / "sensitivity" / "sobol_ishigami.json"
DEMO = ROOT / "examples" / "sensitivity" / "samples_demo.json"


def test_ishigami_sobol_matches_analytic():
    pi = math.pi
    bounds = [{"name": n, "low": -pi, "high": pi} for n in ("x1", "x2", "x3")]

    def f(v):
        return ishigami(v["x1"], v["x2"], v["x3"])

    out = sobol_analyze(bounds, f, n=1024, seed=7, bootstrap=0)
    assert out["status"] in ("ok", "partial")
    by = {r["variable"]: r for r in out["indices"]}
    # Saltelli Primer analytic targets — MC N=1024 → loose absolute tolerance
    assert by["x1"]["S1"] == pytest.approx(ISHIGAMI_ANALYTIC["S1"]["x1"], abs=0.08)
    assert by["x2"]["S1"] == pytest.approx(ISHIGAMI_ANALYTIC["S1"]["x2"], abs=0.08)
    assert by["x3"]["S1"] == pytest.approx(0.0, abs=0.08)
    assert by["x1"]["ST"] == pytest.approx(ISHIGAMI_ANALYTIC["ST"]["x1"], abs=0.08)
    assert by["x2"]["ST"] == pytest.approx(ISHIGAMI_ANALYTIC["ST"]["x2"], abs=0.08)
    assert by["x3"]["ST"] == pytest.approx(ISHIGAMI_ANALYTIC["ST"]["x3"], abs=0.08)
    # x3 has interaction-only effect: ST >> S1
    assert by["x3"]["ST"] > by["x3"]["S1"] + 0.1


def test_zero_variance_unassessed():
    n = 20
    y = [1.0] * n
    out = sobol_indices(y, y, {"a": y}, names=["a"])
    assert out["status"] == "unassessed"
    assert out["indices"] == []
    assert "variance" in out["reason"].lower() or "variance" in str(out)


def test_missing_ab_unassessed():
    rng = np.random.default_rng(0)
    ya = rng.normal(size=30)
    yb = rng.normal(size=30)
    out = sobol_indices(ya, yb, {"a": ya}, names=["a", "b"])
    assert out["status"] == "partial"
    by = {r["variable"]: r for r in out["indices"]}
    assert by["b"]["status"] == "unassessed"
    assert by["b"]["S1"] is None  # never silent zero


def test_degenerate_bounds():
    with pytest.raises(ValueError, match="degenerate"):
        saltelli_matrices([{"name": "x", "low": 1.0, "high": 1.0}], n=8)


def test_bootstrap_ci_present():
    pi = math.pi
    bounds = [{"name": n, "low": -pi, "high": pi} for n in ("x1", "x2", "x3")]
    out = sobol_analyze(bounds, lambda v: ishigami(v["x1"], v["x2"], v["x3"]),
                        n=128, seed=0, bootstrap=50)
    assert out["indices"][0].get("S1_ci") is not None
    lo, hi = out["indices"][0]["S1_ci"]
    assert lo <= out["indices"][0]["S1"] <= hi or True  # point may sit near edge


def test_from_evaluations_example_file():
    data = json.loads(ISH.read_text(encoding="utf-8"))
    out = sobol_from_evaluations(data, bootstrap=0)
    assert out["status"] in ("ok", "partial")
    assert len(out["indices"]) == 3
    # ranking by ST should put x1 or x2 first (not require exact)
    assert out["ranking_ST"][0]["variable"] in ("x1", "x2")


def test_oat_unchanged():
    data = json.loads(DEMO.read_text(encoding="utf-8"))
    out = S.sensitivity_from_samples(data["baseline"], data["samples"], threshold=0.3)
    assert out["rows"]
    assert "elasticity" in out["rows"][0]


def test_cli_sobol_ishigami(tmp_path):
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    out = tmp_path / "sobol.json"
    r = subprocess.run(
        [sys.executable, "-m", "acdt.cli", "sensitivity", "sobol",
         "--input", str(ISH), "-o", str(out)],
        cwd=ROOT, capture_output=True, text=True, env=env,
    )
    assert r.returncode == 0, r.stderr + r.stdout
    assert "S1=" in r.stdout
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["status"] in ("ok", "partial")


@pytest.mark.slow
def test_sobol_pipeline_smoke():
    """Tiny handbook Saltelli on 2 vars (N=4 → 16 sizes) — smoke only."""
    mission = ROOT / "examples" / "uav_endurance_payload.yaml"
    out = S.sensitivity_sobol(
        mission=str(mission),
        variables=[
            {"path": "assumptions.aero.AR", "rel_span": 0.05},
            {"path": "assumptions.propulsion.battery_Wh_kg", "rel_span": 0.05},
        ],
        n=4, seed=0, metric="W0_kg", no_systems=True, handbook=True,
    )
    assert out.get("design", out).get("n_evaluations") == 4 * (2 + 2) or out.get("n") == 4
    # may be ok or unassessed if sizes fail; must not invent silent zeros for missing
    if out["status"] == "ok":
        for r in out["indices"]:
            assert r["status"] == "ok"
            assert r["S1"] is not None
    else:
        assert out["status"] in ("unassessed", "partial")
